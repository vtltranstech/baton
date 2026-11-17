#!/usr/bin/env python3
"""PostToolUse Read|Grep|Glob|Bash: append one line per call to .baton/reads.jsonl for `baton reads`.

Never blocks and never fails the call: any problem is swallowed. Records which agent read what and roughly
how many tokens came back, never the content. A Bash call keeps only its first two words (`baton ir`,
`mvn -q`) so arguments, which can hold secrets, stay out of the log. The story is BATON_STORY, else the
one on the central repo's checked-out `story/<F>-<S>` branch.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from _common import central_dir  # noqa: E402

LOG = ".baton/reads.jsonl"
_BRANCH = re.compile(r"^ref: refs/heads/story/.+-([A-Za-z]+-\d+)\s*$")


def branch_story(central: Path) -> str:
    """The story of the central repo's checked-out `story/<F>-<S>` branch, read from .git/HEAD (no git call)."""
    git = central / ".git"
    if git.is_file():  # a worktree: `gitdir: <path>`
        line = git.read_text(encoding="utf-8", errors="replace").strip()
        if not line.startswith("gitdir:"):
            return ""
        git = Path(line.removeprefix("gitdir:").strip())
        git = git if git.is_absolute() else central / git
    head = git / "HEAD"
    if not head.is_file():
        return ""
    match = _BRANCH.match(head.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def record(payload: dict) -> dict | None:
    tool = payload.get("tool_name") or ""
    if tool not in ("Read", "Grep", "Glob", "Bash"):
        return None
    tool_input = payload.get("tool_input") or {}
    central = central_dir(payload)
    row = {
        "ts": round(time.time(), 3),
        "session": payload.get("session_id") or "",
        "agent": payload.get("agent_type") or "main",
        "agent_id": payload.get("agent_id") or "",
        "tool": tool,
        "story": os.environ.get("BATON_STORY")
        or os.environ.get("POD_STORY")
        or os.environ.get("HARNESS_STORY")
        or "",
    }
    if not row["story"]:
        try:
            row["story"] = branch_story(central)
        except OSError:
            pass
    target = tool_input.get("file_path") or tool_input.get("path") or ""
    if isinstance(target, str) and target:
        path = Path(target) if os.path.isabs(target) else Path(payload.get("cwd") or central) / target
        try:
            row["file"] = path.resolve().relative_to(central.parent).as_posix()
        except (ValueError, OSError):
            row["file"] = path.name
    if tool in ("Grep", "Glob"):
        row["pattern"] = str(tool_input.get("pattern") or "")[:80]
    if tool == "Bash":
        row["cmd"] = " ".join(str(tool_input.get("command") or "").split()[:2])[:40]
    if tool == "Read" and (tool_input.get("offset") or tool_input.get("limit")):
        row["partial"] = True
    response = payload.get("tool_response")
    row["tokens"] = len(response if isinstance(response, str) else json.dumps(response or "")) // 4
    return row


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        row = record(payload) if isinstance(payload, dict) else None
        if row:
            log = central_dir(payload) / LOG
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:  # noqa: BLE001 - logging must never get in the way of the work
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
