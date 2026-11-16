"""Shared plumbing for the baton hooks: read the PreToolUse JSON, fail closed, report on stderr."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path


def run_hook(name: str, check: Callable[[dict], str | None], stream=None) -> int:
    """Exit codes as Claude Code reads them: 0 lets the call go on, 2 blocks and shows stderr."""
    try:
        raw = (stream or sys.stdin).read()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("tool_input", {}), dict):
            raise ValueError("expected a JSON object with a tool_input object")
    except (ValueError, OSError) as exc:
        print(f"baton {name}: refused, the hook could not read the tool call ({exc}).", file=sys.stderr)
        return 2
    try:
        reason = check(payload)
    except Exception as exc:  # noqa: BLE001 - a crashing gate must not open the gate
        print(f"baton {name}: refused, the hook failed ({type(exc).__name__}: {exc}).", file=sys.stderr)
        return 2
    if reason:
        print(f"baton {name}: {reason}", file=sys.stderr)
        return 2
    return 0


def start_dir(payload: dict) -> str:
    return payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def central_dir(payload: dict) -> Path:
    """The product's central repo: the project dir, else the nearest parent holding profile/ or docs/."""
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project and (Path(project) / "profile").is_dir():
        return Path(project).resolve()
    here = Path(start_dir(payload)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "profile" / "project.md").is_file() or (candidate / "docs" / "stories").is_dir():
            return candidate
    return Path(project).resolve() if project else here


def resolve_cd(cwd: str | None, target: str | None, dynamic: bool = False) -> str | None:
    """Follow one `cd`; None means the directory can no longer be known."""
    if cwd is None or dynamic:
        return None
    if target is None:
        return os.path.expanduser("~")
    if target == "-":
        return None
    target = os.path.expanduser(target)
    return os.path.normpath(os.path.join(cwd, target))


def walk(items: list, cwd: str | None):
    """Yield (command, cwd) in order; `cd` persists except across subshell markers."""
    from _shell import Command  # local import keeps the module importable without sys.path games

    stack: list[str | None] = []
    for item in items:
        if item == "(":
            stack.append(cwd)
        elif item == ")":
            cwd = stack.pop() if stack else cwd
        elif isinstance(item, Command):
            if item.name in ("cd", "pushd", "chdir"):
                words = [w for w in item.args if w.text not in ("-L", "-P", "--")]
                cwd = resolve_cd(cwd, words[0].text if words else None, bool(words and words[0].dynamic))
            elif item.name == "popd":
                cwd = None
            yield item, cwd
