#!/usr/bin/env python3
"""PostToolUse Write|Edit|MultiEdit: a Markdown file under docs/ must pass `baton doclint`.

The write has happened; exit 2 hands the problems back to the agent so it fixes them in the next edit.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

from _common import central_dir, run_hook  # noqa: E402

from baton.doclint import check  # noqa: E402


def lint(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(target, str) or not target.endswith(".md"):
        return None
    central = central_dir(payload)
    path = Path(target) if os.path.isabs(target) else Path(payload.get("cwd") or central) / target
    try:
        rel = path.resolve().relative_to(central).as_posix()
    except ValueError:
        return None
    if not rel.startswith("docs/") or not path.is_file():
        return None
    problems = check(path.read_text(encoding="utf-8", errors="replace"), rel)
    if not problems:
        return None
    shown = "\n".join(f"  {p}" for p in problems[:15])
    more = f"\n  ... and {len(problems) - 15} more" if len(problems) > 15 else ""
    return (
        f"{rel} breaks the doc-style skill; fix it now (non-ASCII: `baton doclint --fix {rel}`):\n{shown}{more}"
    )


if __name__ == "__main__":
    sys.exit(run_hook("doc-lint", lint))
