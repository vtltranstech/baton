"""Install or upgrade the framework into a project's .claude/ (the copied install; no plugin needed).

baton install --central ../my-project            install or upgrade; prints what changed
baton install --central ../my-project --check    what an upgrade would change; writes nothing, exit 1 if any
baton install --central ../my-project --force    also replace files edited in the project's copy
baton install --from ../central ...              copy from another install (or a framework clone)

The source is the framework clone, or any project that already has it installed: run its own
`.claude/tools/baton/cli.py install --central ../other-project`, or point `--from` at either. From pipx
(which has no agents or templates) `--from` or BATON_FRAMEWORK is required.

Copies agents/, skills/, hooks/, sensors/, templates/ and tools/baton/ (without tests) under .claude/, and
records each file's hash in .claude/baton-install.json. An upgrade replaces what it installed, removes what
the framework dropped, and never touches a file it did not install. A file edited in the project since the
last install is a conflict: reported, left alone, exit 1, unless --force. Project files are only added to,
never overwritten: CLAUDE.md and profile/* when missing; the baton hooks in .claude/settings.json (other
settings and hooks kept); the graph server in .mcp.json unless --no-mcp; .gitignore and .gitattributes
lines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
FRAMEWORK = Path(__file__).resolve().parents[2]
MANIFEST = ".claude/baton-install.json"
LEGACY_MANIFEST = ".claude/harness-install.json"  # before the renames; read once, then removed
LEGACY_MANIFESTS = (".claude/pod-install.json", LEGACY_MANIFEST)  # newest first
LEGACY_TOOLS = (".claude/tools/pod/", ".claude/tools/harness/")
OWNED = ("agents", "skills", "hooks", "sensors", "templates", "tools/baton")
_SKIP_DIRS = {"__pycache__", "tests", "build", ".pytest_cache", ".ruff_cache"}
_SKIP_SUFFIXES = (".pyc", ".egg-info")
# Written by /onboard from the project's own code; a copy of the template would be another project's data.
GENERATED_PROFILE = {"dependencies.yaml", "aggregates.yaml", "stack-detected.md"}
_HOOK_RUNNER = ".claude/hooks/run-hook"
GITIGNORE = (".baton/", "__pycache__/", "target/", "node_modules/", "pit-reports/", "surefire-reports/")
GITATTRIBUTES = (".claude/hooks/run-hook text eol=lf", "*.sh text eol=lf", "*.py text eol=lf")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--check", action="store_true", help="report what would change; write nothing")
    parser.add_argument("--force", action="store_true", help="also replace files edited in the project")
    parser.add_argument(
        "--from",
        dest="source",
        help="framework checkout to copy from (default: BATON_FRAMEWORK, else the one this runs from)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="do not add the graph MCP server to .mcp.json (agents use the same `baton` commands)",
    )
    parser.add_argument(
        "--python", help="interpreter command for the graph MCP server (default: python3; py -3 on Windows)"
    )


@dataclass
class Plan:
    new: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)  # edited in the project since the last install
    adopted: list[str] = field(default_factory=list)  # present before any manifest: replaced, listed
    files: dict[str, str] = field(default_factory=dict)  # dest rel -> sha of the new content

    def changes(self) -> bool:
        return bool(self.new or self.updated or self.removed or self.conflicts)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(framework: Path = FRAMEWORK) -> dict[str, Path]:
    """Destination path under the central repo -> framework file."""
    out = {}
    for owned in OWNED:
        root = framework / owned
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or any(
                part in _SKIP_DIRS or part.endswith(_SKIP_SUFFIXES) for part in rel.parts
            ):
                continue
            if path.name == ".DS_Store" or path.suffix == ".pyc":
                continue
            out[f".claude/{owned}/{rel.as_posix()}"] = path
    return out


def read_manifest(central: Path) -> dict:
    path = next((central / p for p in (MANIFEST, *LEGACY_MANIFESTS) if (central / p).is_file()), None)
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def plan(central: Path, force: bool, framework: Path = FRAMEWORK) -> Plan:
    previous = read_manifest(central).get("files") or {}
    result = Plan()
    for rel, src in sources(framework).items():
        new_sha = sha(src)
        result.files[rel] = new_sha
        dest = central / rel
        if not dest.is_file():
            result.new.append(rel)
            continue
        current = sha(dest)
        if current == new_sha:
            result.unchanged.append(rel)
        elif rel in previous and current != previous[rel] and not force:
            result.conflicts.append(rel)
        else:
            if rel not in previous and previous == {}:
                result.adopted.append(rel)
            result.updated.append(rel)
    for rel, old_sha in sorted(previous.items()):
        if rel in result.files:
            continue
        dest = central / rel
        if not dest.is_file():
            continue
        if sha(dest) != old_sha and not force:
            result.conflicts.append(rel)
        else:
            result.removed.append(rel)
    return result


def _commit(framework: Path) -> str:
    """The framework version: a copied install passes on the one it was installed from."""
    record = next((framework / n for n in ("baton-install.json", "pod-install.json", "harness-install.json")
                   if (framework / n).is_file()), framework / "baton-install.json")
    if record.is_file():
        try:
            return str(json.loads(record.read_text(encoding="utf-8")).get("framework") or "unknown")
        except ValueError:
            pass
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=framework, capture_output=True, text=True, check=True
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=framework, capture_output=True, text=True
        )
        return done.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def apply(central: Path, result: Plan, framework: Path = FRAMEWORK) -> None:
    src = sources(framework)
    for rel in result.new + result.updated:
        dest = central / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src[rel], dest)  # keeps the executable bit of hooks/run-hook
    for rel in result.removed:
        (central / rel).unlink()
    previous = read_manifest(central).get("files") or {}
    kept = {rel: previous[rel] for rel in result.conflicts if rel in previous}  # left as they were
    manifest = {
        "framework": _commit(framework),
        "installed": date.today().isoformat(),
        "files": {**kept, **{rel: s for rel, s in result.files.items() if rel not in result.conflicts}},
    }
    path = central / MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name in LEGACY_MANIFESTS:
        if (central / name).is_file():
            (central / name).unlink()


# -- project files: add, never overwrite --------------------------------------------------------------------


def merge_settings(existing: dict, template: dict) -> dict:
    """The template's hooks replace the baton hooks; its env keys are added when missing; the rest stays."""
    merged = dict(existing)
    hooks = {event: list(entries) for event, entries in (existing.get("hooks") or {}).items()}
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            own = [h for h in entry.get("hooks", []) if _HOOK_RUNNER not in json.dumps(h)]
            if own:
                kept.append({**entry, "hooks": own})
        hooks[event] = kept
    for event, entries in template.get("hooks", {}).items():
        hooks[event] = hooks.get(event, []) + entries
    merged["hooks"] = {event: entries for event, entries in hooks.items() if entries}
    env = dict(existing.get("env") or {})
    for key, value in (template.get("env") or {}).items():
        env.setdefault(key, value)  # a value the project set itself is kept
    if env:
        merged["env"] = env
    return merged


def mcp_server(python: str | None) -> dict:
    words = (python or ("py -3" if os.name == "nt" else "python3")).split()
    return {"command": words[0], "args": [*words[1:], ".claude/tools/baton/graph/mcp_server.py"]}


def _lines(path: Path, wanted: tuple[str, ...]) -> list[str]:
    have = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    return [line for line in wanted if line not in have]


def project_files(
    central: Path, python: str | None, write: bool, framework: Path = FRAMEWORK, mcp: bool = True
) -> list[str]:
    """What the install adds to the project outside .claude/'s owned folders; writes it when `write`."""
    done = []
    templates = framework / "templates"
    for src, rel in [(templates / "CLAUDE.md", "CLAUDE.md")] + [
        (p, f"profile/{p.name}")
        for p in sorted((templates / "profile").glob("*"))
        if p.is_file() and p.name not in GENERATED_PROFILE
    ]:
        if not (central / rel).exists():
            done.append(f"created {rel}")
            if write:
                (central / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, central / rel)
    settings = central / ".claude/settings.json"
    template = json.loads((templates / "settings.json").read_text(encoding="utf-8"))
    existing = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
    merged = merge_settings(existing, template)
    if merged != existing:
        done.append(f"{'updated' if existing else 'created'} .claude/settings.json (baton hooks)")
        if write:
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    mcp_json = central / ".mcp.json"
    config = json.loads(mcp_json.read_text(encoding="utf-8")) if mcp_json.is_file() else {}
    servers = dict(config.get("mcpServers") or {})
    old = servers.get("graph") if mcp else None
    if isinstance(old, dict) and any(t in str(a) for a in old.get("args") or [] for t in LEGACY_TOOLS):
        # installed before a rename: same interpreter, the server's new path
        args = [str(a) for a in old["args"]]
        for legacy_tools in LEGACY_TOOLS:
            args = [a.replace(legacy_tools, ".claude/tools/baton/") for a in args]
        old["args"] = args
        done.append("updated .mcp.json (graph server moved to .claude/tools/baton)")
        if write:
            mcp_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if mcp and "graph" not in servers:  # a hand-tuned entry (another interpreter, an absolute path) is kept
        servers["graph"] = mcp_server(python)
        done.append(f"{'updated' if config else 'created'} .mcp.json (graph server)")
        if write:
            mcp_json.write_text(
                json.dumps({**config, "mcpServers": servers}, indent=2) + "\n", encoding="utf-8"
            )
    for name, wanted in ((".gitignore", GITIGNORE), (".gitattributes", GITATTRIBUTES)):
        missing = _lines(central / name, wanted)
        if missing:
            done.append(f"added to {name}: {', '.join(missing)}")
            if write:
                path = central / name
                text = path.read_text(encoding="utf-8") if path.is_file() else ""
                path.write_text(
                    text + ("" if not text or text.endswith("\n") else "\n") + "\n".join(missing) + "\n"
                )
    return done


def _show(result: Plan, project: list[str], check: bool) -> str:
    verb = "would " if check else ""
    lines = [
        f"{len(result.new)} new, {len(result.updated)} updated, {len(result.removed)} removed, "
        f"{len(result.unchanged)} unchanged, {len(result.conflicts)} conflicts"
    ]
    for action, items in (("add", result.new), ("update", result.updated), ("remove", result.removed)):
        lines += [f"  {verb}{action} {rel}" for rel in items[:40]]
        if len(items) > 40:
            lines.append(f"  ... and {len(items) - 40} more to {action}")
    if result.adopted:
        lines.append(f"  {len(result.adopted)} files predate any install record and are replaced")
    for rel in result.conflicts:
        lines.append(
            f"  conflict {rel}: edited in this project since the last install; kept (--force replaces)"
        )
    lines += [f"  {verb}{line}" for line in project]
    return "\n".join(lines) + "\n"


def is_checkout(path: Path) -> bool:
    return (path / "templates" / "settings.json").is_file() and (path / "agents").is_dir()


def framework_root(source: str | None) -> tuple[Path | None, list[Path]]:
    """--from, else BATON_FRAMEWORK, else where this file sits: a framework clone or an installed .claude/.
    A project folder given as the source means its .claude/. A pipx copy is neither."""
    names = ("BATON_FRAMEWORK", "POD_FRAMEWORK", "HARNESS_FRAMEWORK")  # the last two: older names
    named = next((os.environ[n] for n in names if os.environ.get(n)), None)
    tried = [Path(p).expanduser().resolve() for p in (source, named) if p]
    if not source:
        tried.append(FRAMEWORK)
    for path in tried:
        for candidate in (path, path / ".claude"):
            if is_checkout(candidate):
                return candidate, tried
        if source:
            break  # a named source that is not one is reported, not replaced
    return None, tried


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    framework, tried = framework_root(getattr(args, "source", None))
    if framework is None:
        print(
            f"baton install: nothing to install from at {', '.join(str(t) for t in tried)}: a source needs "
            "agents/ and templates/settings.json (a framework clone, or a project's .claude/ installed by "
            "`baton install`; a hand-copied .claude/ has no templates/, so run one install from the clone "
            "first). From pipx: `baton install --from <clone or project> --central <target>`.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if central in (framework, framework.parent) or framework in central.parents:
        print(
            "baton install: the target is the framework itself; give --central <central repo>",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    if not central.is_dir():
        print(f"baton install: {central} is not a folder", file=sys.stderr)
        return EXIT_REFUSED
    result = plan(central, args.force, framework)
    project = project_files(
        central,
        args.python,
        write=not args.check,
        framework=framework,
        mcp=not getattr(args, "no_mcp", False),
    )
    if not args.check:
        apply(central, result, framework)
    if args.json:
        data = {k: getattr(result, k) for k in ("new", "updated", "removed", "conflicts", "adopted")}
        print(json.dumps({**data, "unchanged": len(result.unchanged), "project": project}, indent=1))
    else:
        print(_show(result, project, args.check), end="")
    if result.conflicts:
        return EXIT_FAILED
    return EXIT_FAILED if args.check and (result.changes() or project) else EXIT_OK
