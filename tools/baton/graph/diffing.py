"""Derives changed symbols from a diff deterministically (documented rule by rule in graph/README.md)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from baton.graph.model import node_kind, node_name, node_prefix

_MODIFIERS = r"(?:private|protected|public)\s+(?:(?:final|transient|volatile)\s+)*"
_FIELD = re.compile(
    rf"^\s*(?:@\w+(?:\([^)]*\))?\s+)*{_MODIFIERS}[\w.<>,\[\]? ]+?\s+(\w+)\s*(?:=[^;]*)?;\s*(?://.*)?$"
)
_RECORD = re.compile(r"\brecord\s+\w+\s*(?:<[^>]*>)?\s*\(([^)]*)\)")
_MAPPING = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:(?:value|path)\s*=\s*)?\{?\s*"([^"]*)"'
)
_SIGNATURE = re.compile(r"@(?:PathVariable|RequestParam|RequestBody|RequestHeader)\b")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@")
_JAVA_SOURCE = re.compile(r"^(?:.*/)?src/main/(?:java|kotlin)/(.+)\.(?:java|kt)$")
_DIFF_HEAD = ("diff --git ", "--- ", "+++ ", "@@ ")


class DiffError(Exception):
    pass


@dataclass
class FileChange:
    path: str
    removed: list[tuple[int, str]] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


@dataclass
class Changes:
    ids: set[str] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)
    breaking: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)


def _strip_prefix(path: str) -> str:
    path = path.split("\t", 1)[0].strip()
    return path[2:] if path.startswith(("a/", "b/")) else path


def parse_unified(text: str) -> list[FileChange]:
    files: dict[str, FileChange] = {}
    current: FileChange | None = None
    old_path = ""
    old_line = old_left = new_left = 0

    def open_file(path: str) -> FileChange:
        return files.setdefault(path, FileChange(path))

    for line in text.splitlines():
        if old_left or new_left:  # inside a hunk: its header says exactly how many lines belong to it
            if line.startswith("-"):
                if current is not None:
                    current.removed.append((old_line, line[1:]))
                old_line, old_left = old_line + 1, old_left - 1
            elif line.startswith("+"):
                if current is not None:
                    current.added.append(line[1:])
                new_left -= 1
            elif line.startswith(" "):
                old_line, old_left, new_left = old_line + 1, old_left - 1, new_left - 1
            continue
        if line.startswith("diff --git "):
            old_path = ""
            match = re.match(r"diff --git (\S+) (\S+)$", line)
            current = open_file(_strip_prefix(match.group(2))) if match else None
        elif line.startswith("rename to "):
            current = open_file(line[len("rename to ") :].strip())
        elif line.startswith("--- "):
            old_path = _strip_prefix(line[4:])
        elif line.startswith("+++ "):
            new_path = _strip_prefix(line[4:])
            current = open_file(old_path if new_path == "/dev/null" else new_path)
        elif match := _HUNK.match(line):
            old_line = int(match.group(1))
            old_left = int(match.group(2)) if match.group(2) is not None else 1
            new_left = int(match.group(3)) if match.group(3) is not None else 1
    return [files[path] for path in sorted(files)]


def looks_unified(text: str) -> bool:
    return any(line.startswith(_DIFF_HEAD) for line in text.splitlines())


def parse_file_list(text: str, repo: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """(paths, node ids, breaking symbols, ignored paths of other repos) from a design file list.

    One entry per line, an optional `- ` bullet, anything after whitespace ignored. `#` starts a comment.
    Entries: a repo-relative path, `../<repo>/path`, a node id (`topic:x`), or `breaking: <symbol>` where
    symbol is a node id or `Class.field`: a design has no code to diff, so removals are declared this way.
    """
    paths: list[str] = []
    ids: list[str] = []
    breaking: list[str] = []
    ignored: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("- ", "* ")):
            line = line[2:].strip()
        if line.lower().startswith("breaking:"):
            breaking.append(line.split(":", 1)[1].strip())
            continue
        if node_kind(line) and node_prefix(line) != "repo":
            ids.append(line)
            continue
        token = re.split(r"\s+(?:—|–|-)\s+|\s+", line, maxsplit=1)[0]
        pure = PurePosixPath(token)
        if pure.parts[:1] == ("..",) and len(pure.parts) > 2:
            if pure.parts[1] != repo:
                ignored.append(token)
                continue
            token = str(PurePosixPath(*pure.parts[2:]))
        paths.append(token.removeprefix("./"))
    return paths, ids, breaking, ignored


def _fields_in(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for line in lines:
        if " static " in line:
            continue
        match = _FIELD.match(line)
        if match:
            names.add(match.group(1))
            continue
        record = _RECORD.search(line)
        if record:
            for component in record.group(1).split(","):
                if component.strip():
                    names.add(component.split()[-1])
    return names


def class_id_from_path(path: str) -> str | None:
    match = _JAVA_SOURCE.match(path)
    if not match:
        return None
    relative = match.group(1)
    return (
        None if relative.endswith(("package-info", "module-info")) else "class:" + relative.replace("/", ".")
    )


def _classes_for(path: str, edges_by_file: dict) -> set[str]:
    classes = {edge.src for edge in edges_by_file.get(path, []) if node_prefix(edge.src) == "class"}
    derived = class_id_from_path(path)
    return classes or ({derived} if derived else set())


def _apply_file_change(change: FileChange, edges_by_file: dict, result: Changes) -> None:
    classes = _classes_for(change.path, edges_by_file)
    if not classes:
        return
    stem = PurePosixPath(change.path).stem
    added_set = {line.strip() for line in change.added}
    # A line both removed and added is a move or whitespace change, not a change of meaning.
    removed = [(n, text) for n, text in change.removed if text.strip() not in added_set]
    removed_set = {text.strip() for _, text in change.removed}
    added = [text for text in change.added if text.strip() not in removed_set]
    old_fields = _fields_in([text for _, text in removed])
    new_fields = _fields_in(added)
    gone = old_fields - new_fields
    result.ids |= classes
    if old_fields | new_fields:
        result.symbols |= {f"{stem}.{name}" for name in old_fields | new_fields}
    else:
        result.symbols |= classes
    if gone:
        result.breaking |= classes
        result.symbols |= {f"{stem}.{name}" for name in gone}
    edges = edges_by_file.get(change.path, [])
    _endpoint_changes(edges, removed, added, result)
    _messaging_changes(edges, removed, added, result)


def _mark_breaking(result: Changes, node_id: str) -> None:
    result.ids.add(node_id)
    result.symbols.add(node_id)
    result.breaking.add(node_id)


def _endpoint_changes(edges, removed, added, result: Changes) -> None:
    exposed = sorted((e for e in edges if e.kind == "EXPOSES"), key=lambda e: e.line)
    if not exposed:
        return
    added_mappings = {m.groups() for text in added for m in [_MAPPING.search(text)] if m}
    for line_no, text in removed:
        mapping = _MAPPING.search(text)
        if mapping and mapping.groups() not in added_mappings:
            verb, literal = mapping.groups()
            for edge in exposed:
                method, _, path = node_name(edge.dst).partition(" ")
                if path.endswith(literal) and (verb == "Request" or method == verb.upper()):
                    _mark_breaking(result, edge.dst)
        if _SIGNATURE.search(text):
            preceding = [edge for edge in exposed if edge.line <= line_no]
            if preceding:
                _mark_breaking(result, preceding[-1].dst)


def _messaging_changes(edges, removed, added, result: Changes) -> None:
    added_text = "\n".join(added)
    for edge in edges:
        if edge.kind != "PUBLISHES":
            continue
        literal = f'"{node_name(edge.dst)}"'
        if literal not in added_text and any(literal in text for _, text in removed):
            _mark_breaking(result, edge.dst)


def changes_from_unified(text: str, store, repo: str) -> Changes:
    result = Changes()
    edges_by_file: dict[str, list] = {}
    for edge in store.edges(repo):
        edges_by_file.setdefault(edge.file, []).append(edge)
    for change in parse_unified(text):
        _apply_file_change(change, edges_by_file, result)
    return result


def _resolve_field(symbol: str, store, repo: str) -> set[str]:
    simple = symbol.split(".")[0]
    return {
        edge.src
        for edge in store.edges(repo)
        if node_prefix(edge.src) == "class" and edge.src.rsplit(".", 1)[-1] == simple
    }


def changes_from_list(text: str, store, repo: str) -> Changes:
    paths, ids, breaking, ignored = parse_file_list(text, repo)
    result = Changes()
    edges_by_file: dict[str, list] = {}
    for edge in store.edges(repo):
        edges_by_file.setdefault(edge.file, []).append(edge)
    for path in paths:
        classes = _classes_for(path, edges_by_file)
        result.ids |= classes
        result.symbols |= classes
    result.ids |= set(ids)
    result.symbols |= set(ids)
    for symbol in breaking:
        result.symbols.add(symbol)
        targets = {symbol} if node_kind(symbol) else _resolve_field(symbol, store, repo)
        result.ids |= targets
        result.breaking |= targets
        if not targets:
            result.notes.append(f"breaking symbol {symbol} matches nothing in {repo}")
    result.notes += [f"ignored, belongs to another repo: {path}" for path in ignored]
    return result


def git_diff(repo_dir: Path, ref: str) -> str:
    if ref.startswith("-"):
        raise DiffError(f"refused: {ref!r} is not a git ref")
    if not repo_dir.is_dir():
        raise DiffError(f"repo checkout not found: {repo_dir}")
    # Inside a git hook GIT_DIR and friends point at the hook's repo, not the one named by -C.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    done = subprocess.run(
        [
            "git",
            "-C",
            str(repo_dir),
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "-M",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            ref,
            "--",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if done.returncode:
        raise DiffError(f"git diff {ref} failed in {repo_dir}: {done.stderr.strip()}")
    return done.stdout


def derive_changes(diff: str, store, repo: str, central: str | Path, cwd: Path | None = None) -> Changes:
    """`diff` is an existing file (unified diff or design file list), otherwise a git ref in ../<repo>."""
    central = Path(central)
    for candidate in (Path(cwd or Path.cwd()) / diff, central / diff):
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            if looks_unified(text):
                return changes_from_unified(text, store, repo)
            return changes_from_list(text, store, repo)
    return changes_from_unified(git_diff((central / ".." / repo).resolve(), diff), store, repo)


def compute_impact(store, repo: str, diff: str, central: str | Path) -> tuple[dict, list[str]]:
    changes = derive_changes(diff, store, repo, central)
    report = store.impact(changes.ids, source_repo=repo, breaking=changes.breaking, symbols=changes.symbols)
    return report, changes.notes
