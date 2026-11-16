#!/usr/bin/env python3
"""PreToolUse Write|Edit|MultiEdit|Bash: a story's State changes only when `state-check` allows it."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

from _common import run_hook, start_dir, walk  # noqa: E402
from _shell import Command, ShellParseError, flatten  # noqa: E402

READ_ONLY = {
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "ack",
    "ls",
    "wc",
    "diff",
    "stat",
    "file",
    "sort",
    "uniq",
    "cut",
    "tr",
    "jq",
    "echo",
    "printf",
    "test",
    "[",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "cd",
    "pushd",
    "popd",
    "baton",
    "true",
    "false",
    "pwd",
    "mkdir",
    "nl",
}
GIT_SAFE = {
    "add",
    "commit",
    "log",
    "diff",
    "show",
    "status",
    "blame",
    "grep",
    "ls-files",
    "rev-parse",
    "branch",
    "push",
    "fetch",
}


def is_story_path(path: str) -> bool:
    parts = [p.casefold() for p in Path(path).parts]
    for index in range(len(parts) - 1):
        if parts[index] == "docs" and parts[index + 1] == "stories":
            inner = parts[index + 2 :]
            return bool(inner) and inner[-1].endswith(".md") and "attachments" not in inner
    return False


def central_of(path: Path) -> Path:
    parts = path.parts
    for index in range(len(parts) - 2, -1, -1):
        if parts[index].casefold() == "docs" and parts[index + 1].casefold() == "stories":
            return Path(*parts[:index])
    raise ValueError(f"{path} is not under docs/stories")


def _apply_edit(text: str, old: str, new: str, replace_all: bool) -> str | None:
    if old == "" or old not in text:
        return None
    return text.replace(old, new) if replace_all else text.replace(old, new, 1)


def _proposed(tool: str, tool_input: dict, current: str | None) -> tuple[str | None, str | None]:
    """The story text after this tool call; (None, fragment) when the edit will not apply cleanly."""
    if tool == "Write":
        content = tool_input.get("content", tool_input.get("file_text"))
        if not isinstance(content, str):
            raise ValueError("Write has no content")
        return content, None
    edits = tool_input.get("edits") if tool == "MultiEdit" else [tool_input]
    text = current if current is not None else ""
    fragments = []
    applied = True
    for edit in edits or []:
        old, new = edit.get("old_string"), edit.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            raise ValueError(f"{tool} has no old_string/new_string")
        fragments.append(new)
        result = _apply_edit(text, old, new, bool(edit.get("replace_all")))
        if result is None:
            applied = False
        else:
            text = result
    return (text, None) if applied else (None, "\n".join(fragments))


UNAPPROVED = {None, "Draft", "Needs Clarification", "Ready for PO"}


def check_file(tool: str, tool_input: dict, cwd: str) -> str | None:
    from baton import state_check

    raw = tool_input.get("file_path") or tool_input.get("path")
    paths = [raw] if isinstance(raw, str) and raw else []
    if tool == "MultiEdit" and not paths:
        paths = [
            e.get("file_path")
            for e in tool_input.get("edits") or []
            if isinstance(e, dict) and e.get("file_path")
        ]
    if not paths:
        return "refused: the tool call names no file path, so the state gate cannot check it."
    joined = Path(os.path.normpath(os.path.join(cwd, paths[0])))
    real = Path(os.path.realpath(joined))
    target = joined if is_story_path(str(joined)) else real if is_story_path(str(real)) else None
    if target is None:
        return None
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    proposed, fragment = _proposed(tool, tool_input, current)
    old_state = state_check.parse_state(current).state if current is not None else None
    parsed = state_check.parse_state(proposed if proposed is not None else (fragment or ""))
    if current is not None and proposed is not None and old_state not in UNAPPROVED:
        before = state_check.parse_depends_on(current)[0] or []
        after = state_check.parse_depends_on(proposed)[0] or []
        dropped = [dep for dep in before if dep not in after]
        if dropped:
            return f"refused: this change removes {', '.join(dropped)} from `Depends-On:` on the approved story {target.name}. Only a human changes that, in their own editor."  # noqa: E501
    text_after = proposed if proposed is not None else (fragment or "")
    if state_check.OVERRIDE.findall(text_after) != state_check.OVERRIDE.findall(current or "") and (
        proposed is not None or state_check.OVERRIDE.search(fragment or "")
    ):
        return f"refused: only the Tech Lead writes `Gate-0-Override:` on {target.name}, in their own editor."
    if parsed.conflict:
        return f"refused: {target.name} would hold conflicting State lines ({parsed.conflict}). Keep exactly one."  # noqa: E501
    if proposed is None and parsed.state is None:
        return None  # the edit will fail on its own and touches no State line
    if parsed.state is None:
        if old_state is not None:
            return f"refused: this change removes the State line from {target.name}. Keep it."
        return None
    if parsed.state == old_state:
        return None
    result = state_check.check(
        target, parsed.state, story_text=proposed, central=central_of(target), old_state=old_state or "Draft"
    )
    if not result.ok:
        return f"refused: State: {parsed.state} on {target.name}: {result.missing}. Produce the artefact, do not retry the state."  # noqa: E501
    return None


def _bash_writes_story(cmd: Command, cwd: str | None) -> str | None:
    def in_stories(text: str) -> bool:
        if "docs/stories" in text.casefold():
            joined = text
        elif cwd is not None and not text.startswith("-"):
            joined = os.path.normpath(os.path.join(cwd, text))
            if not is_story_path(joined) and not is_story_path(os.path.join(joined, "x.md")):
                return False
        else:
            return False
        tail = joined.rstrip("/").rsplit("/", 1)[-1]
        if "/attachments" in joined.casefold():
            return False
        return tail.casefold().endswith(".md") or "." not in tail or any(c in tail for c in "*?[{")

    for op, word in cmd.redirects:
        if op not in ("<", "<<<", "<&") and in_stories(word.text):
            return f"redirect into {word.text}"
    if not cmd.argv or cmd.name in READ_ONLY:
        if cmd.name == "mkdir" or not cmd.argv:
            return None
        return None
    touching = [w.text for w in cmd.args if in_stories(w.text)]
    if not touching:
        return None
    if cmd.name == "git":
        words = [w.text for w in cmd.args if not w.text.startswith("-")]
        if words and words[0] in GIT_SAFE:
            return None
    if cmd.name in ("sed", "gsed") and not any(w.text.startswith(("-i", "--in-place")) for w in cmd.args):
        return None
    if cmd.name in ("awk", "gawk") and not any(w.text == "inplace" for w in cmd.args):
        return None
    if cmd.name == "find" and not any(w.text in ("-exec", "-execdir", "-ok", "-delete") for w in cmd.args):
        return None
    if cmd.name.startswith("python") and cmd.args and cmd.args[0].text.endswith("cli.py"):
        return None
    return f"`{cmd.name}` on {touching[0]}"


def check_bash(command: str, cwd: str) -> str | None:
    try:
        items = flatten(command)
    except ShellParseError as exc:
        return f"refused: the command could not be parsed ({exc}), so the state gate cannot check it."
    for cmd, here in walk(items, cwd):
        if cmd.opaque:
            return f"refused: {cmd.opaque}; the state gate cannot see what runs."
        reason = _bash_writes_story(cmd, here)
        if reason:
            return f"refused: {reason}. Change a story with the Write or Edit tool so the state gate can check it."  # noqa: E501
        for word in cmd.args:
            if re.search(r"docs/stories", word.text) and re.fullmatch(
                r"python\d?(\.\d+)?|node|ruby|perl", cmd.name
            ):
                if not cmd.args[0].text.endswith("cli.py"):
                    return "refused: inline code touching docs/stories. Use the Write or Edit tool."
    return None


def check(payload: dict) -> str | None:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    cwd = start_dir(payload)
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return "refused: tool_input.command is missing."
        return check_bash(command, cwd)
    if tool in ("Write", "Edit", "MultiEdit"):
        return check_file(tool, tool_input, cwd)
    return None


if __name__ == "__main__":
    sys.exit(run_hook("state-gate", check))
