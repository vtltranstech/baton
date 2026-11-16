"""Finds the repos a central repo names, their sources, and the commit each one is really at."""

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from baton.extract.parser import ORDER, JavaFile, ParseFailure, ast_usable, parse_java_many

BUILD_FILES = ("pom.xml", "build.gradle", "build.gradle.kts")
_NEVER_WALK = {"target", "build", "node_modules", "dist", "out", "bin"}
UNKNOWN = "unknown"


class MissingInput(Exception):
    """Exit 2: a named input does not exist."""


@dataclass
class RepoRef:
    name: str
    path: Path


def _cells(line: str) -> list[str]:
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def read_repo_table(central: Path) -> list[RepoRef]:
    """The first table in project.md with a `path` or `repo` column. A name comes from `repo`, else the path's
    last part; a path from `path`, else `../<repo>`."""
    project = central / "profile" / "project.md"
    if not project.is_file():
        raise MissingInput(f"{project} not found: the repo table lives there")
    columns: list[str] = []
    rows: list[RepoRef] = []
    for line in project.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            if rows:
                break
            columns = []
            continue
        cells = _cells(line)
        if not columns:
            lowered = [c.lower() for c in cells]
            if "path" in lowered or "repo" in lowered:
                columns = lowered
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(columns, cells, strict=False))
        path, name = row.get("path", ""), row.get("repo", "")
        if not path and not name:
            continue
        name = name or Path(path).name
        rows.append(RepoRef(name, (central / (path or f"../{name}")).resolve()))
    if not rows:
        raise MissingInput(f"{project} has no repo table (a table with a Repo or Path column)")
    return rows


def select_repos(central: Path, only: str | None) -> list[RepoRef]:
    """Every repo of the table, or the named one; a name not in the table or a missing path is exit 2."""
    repos = read_repo_table(central)
    chosen = [r for r in repos if only in (None, r.name)]
    if not chosen:
        raise MissingInput(f"repo {only!r} is not in profile/project.md")
    missing = [f"{r.name}: {r.path}" for r in chosen if not r.path.is_dir()]
    if missing:
        raise MissingInput("repo path missing: " + "; ".join(missing))
    return chosen


def git_commit(repo: Path) -> tuple[str, str]:
    """(short sha, reason when unknown). Only a repo that is its own git top level has a commit: a folder
    inside another repository would report that repository's HEAD, which says nothing about this code."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)

    try:
        top = git("rev-parse", "--show-toplevel")
    except OSError:
        return UNKNOWN, "git is not available"
    if top.returncode != 0:
        return UNKNOWN, "not a git repository"
    if Path(top.stdout.strip()).resolve() != repo.resolve():
        return UNKNOWN, f"a folder inside the git repository at {top.stdout.strip()}, not its own repository"
    head = git("rev-parse", "--short=7", "HEAD")
    if head.returncode != 0:
        return UNKNOWN, "git repository with no commits"
    return head.stdout.strip(), ""


def git_dirty(repo: Path) -> bool:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, env=env
    )
    return bool(status.stdout.strip())


def declared_modules(repo: Path) -> list[str]:
    """Modules the root build declares (recursively for Maven), repo-relative. Malformed files give none."""
    found: list[str] = []

    def maven(base: Path, prefix: str) -> None:
        try:
            root = ET.parse(base / "pom.xml").getroot()
        except (ET.ParseError, OSError):
            return
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] == "module" and element.text:
                rel = os.path.normpath(os.path.join(prefix, element.text.strip()))
                if rel not in found and (repo / rel / "pom.xml").is_file():
                    found.append(rel)
                    maven(repo / rel, rel)

    if (repo / "pom.xml").is_file():
        maven(repo, "")
    for name in ("settings.gradle", "settings.gradle.kts"):
        path = repo / name
        if path.is_file():
            text = re.sub(
                r"//[^\n]*|/\*.*?\*/", "", path.read_text(encoding="utf-8", errors="replace"), flags=re.S
            )
            for statement in re.findall(r"\binclude\b\s*\(?([^\n)]*)", text):
                for module in re.findall(r"""["']([^"']+)["']""", statement):
                    rel = module.strip(":").replace(":", "/")
                    if rel not in found and (repo / rel).is_dir():
                        found.append(rel)
    return sorted(found)


def nested_projects(repo: Path, modules: list[str]) -> list[str]:
    """Folders with their own build file that the root build does not declare: separate, not walked."""
    out: list[str] = []
    allowed = set(modules)
    for current, dirs, files in os.walk(repo):
        rel = os.path.relpath(current, repo)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in _NEVER_WALK)
        if rel != "." and rel not in allowed and any(f in files for f in BUILD_FILES):
            out.append(rel)
            dirs[:] = []
    return out


@dataclass
class Sources:
    """A repo's parsed Java, with what could not be read kept next to it."""

    repo: RepoRef
    modules: list[str] = field(default_factory=list)
    nested: list[str] = field(default_factory=list)
    main: list[JavaFile] = field(default_factory=list)
    test: list[JavaFile] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    other_languages: list[str] = field(default_factory=list)

    @property
    def module_roots(self) -> list[str]:
        return [".", *self.modules]

    def parser_record(self, use_ast: bool) -> dict:
        """Files per back-end; `fallback`: a better back-end refused it; `unavailable`: no AST parser."""
        counts = {name: sum(1 for f in self.main if f.backend == name) for name in ORDER}
        return {
            **counts,
            "fallback": sorted(f.path for f in self.main if f.fallback_reason),
            "unavailable": not use_ast,
        }


def _rel(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def load_sources(repo: RepoRef) -> Sources:
    root = repo.path
    modules = declared_modules(root)
    sources = Sources(repo, modules, nested_projects(root, modules))
    use_ast = ast_usable()
    for module in sources.module_roots:
        for kind, bucket in (("main", sources.main), ("test", sources.test)):
            base = root / module / "src" / kind / "java"
            items = []
            for path in sorted(base.rglob("*.java")) if base.is_dir() else []:
                rel = _rel(path.resolve(), root.resolve())
                if path.name in ("package-info.java", "module-info.java"):
                    continue
                try:
                    items.append((path, rel, path.read_text(encoding="utf-8")))
                except UnicodeDecodeError as exc:
                    sources.failures.append({"file": rel, "reason": str(exc)})
            for (_, rel, _), result in zip(items, parse_java_many(items, use_ast), strict=True):
                if isinstance(result, ParseFailure):
                    sources.failures.append({"file": rel, "reason": str(result)})
                else:
                    bucket.append(result)
        kotlin = root / module / "src" / "main" / "kotlin"
        if kotlin.is_dir() and any(kotlin.rglob("*.kt")):
            sources.other_languages.append(_rel(kotlin.resolve(), root.resolve()))
    return sources
