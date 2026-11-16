#!/usr/bin/env python3
"""PreToolUse Read|Grep|Bash|Write|Edit: profile/confidence-weights.yaml never reaches a model."""

from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import central_dir, run_hook, start_dir, walk  # noqa: E402
from _shell import Command, ShellParseError, Word, flatten  # noqa: E402

FILENAME = "confidence-weights.yaml"
MENTION = re.compile(r"confidence[-_ ]?weights", re.I)
MESSAGE = "refused: profile/confidence-weights.yaml is owned by the Senior Engineer; edit outside Claude. "
INTERPRETERS = {
    "python",
    "python2",
    "python3",
    "node",
    "nodejs",
    "deno",
    "bun",
    "ruby",
    "perl",
    "php",
    "lua",
    "osascript",
}
CODE_READS = re.compile(
    r"\bopen\b|\bglob\b|listdir|scandir|\bwalk\b|readFile|read_text|File\.read|readdir|\bcat\b", re.I
)
RECURSIVE_ALWAYS = {"rg", "ripgrep", "ag", "ack", "tar", "gtar", "zip", "rsync", "scp", "7z", "cpio"}
GREPS = {"grep", "egrep", "fgrep", "ggrep"}
COPIES = {"cp", "gcp"}


def _expand_braces(text: str) -> list[str]:
    match = re.search(r"\{([^{}]*)\}", text)
    if not match:
        return [text]
    out = []
    for part in match.group(1).split(","):
        out += _expand_braces(text[: match.start()] + part + text[match.end() :])
    return out


def _is_weights_path(path: str) -> bool:
    return os.path.basename(path).casefold() == FILENAME


def glob_hits(pattern: str, cwd: str | None, central: Path) -> bool:
    """Can this shell glob expand to the weights file?"""
    target = str(central / "profile" / FILENAME).casefold()
    for candidate in _expand_braces(pattern):
        candidate = candidate.casefold()
        if (
            fnmatch.fnmatchcase(FILENAME, os.path.basename(candidate))
            and "/" not in candidate
            and cwd is None
        ):
            return True
        if cwd is not None:
            joined = os.path.normpath(os.path.join(cwd.casefold(), candidate))
            if fnmatch.fnmatchcase(target, joined):
                return True
            head = os.path.dirname(joined)
            if fnmatch.fnmatchcase(os.path.basename(target), os.path.basename(joined)) and (
                head == os.path.dirname(target) or fnmatch.fnmatchcase(os.path.dirname(target), head)
            ):
                return True
        elif "/" in candidate and fnmatch.fnmatchcase("profile/" + FILENAME, candidate.lstrip("./")):
            return True
    return False


def _covers(path: str | None, central: Path) -> bool:
    """Would reading this directory tree include the weights file?"""
    if path is None:
        return True
    real = os.path.realpath(path).casefold()
    profile = os.path.realpath(central / "profile").casefold()
    if profile == real or profile.startswith(real.rstrip("/") + "/"):
        return True
    return os.path.isfile(os.path.join(path, FILENAME)) or os.path.isfile(
        os.path.join(path, "profile", FILENAME)
    )


def _join(cwd: str | None, text: str) -> str | None:
    if os.path.isabs(text):
        return text
    if text.startswith("~"):
        return os.path.expanduser(text)
    return None if cwd is None else os.path.normpath(os.path.join(cwd, text))


def _paths(args: list[Word]) -> list[Word]:
    return [w for w in args if not w.text.startswith("-")]


def _recursive_reader(cmd: Command, cwd: str | None, central: Path) -> str | None:
    name, args = cmd.name, cmd.args
    flags = [w.text for w in args if w.text.startswith("-")]
    short = "".join(f[1:] for f in flags if not f.startswith("--"))
    narrow = any(f.split("=")[0] in ("--include", "--glob", "-g", "--type", "-t", "--iglob") for f in flags)
    if name in GREPS:
        if not (
            "r" in short
            or "R" in short
            or any(f in ("--recursive", "--dereference-recursive") for f in flags)
        ):
            return None
        roots = _paths(args)[1:] or [Word(".", ".")]
    elif name in ("rg", "ripgrep", "ag", "ack"):
        roots = _paths(args)[1:] or [Word(".", ".")]
    elif name in RECURSIVE_ALWAYS:
        roots = _paths(args) or [Word(".", ".")]
    elif name in COPIES:
        if not (
            "r" in short or "R" in short or "a" in short or "--recursive" in flags or "--archive" in flags
        ):
            return None
        roots = _paths(args)[:-1]
    elif name == "git" and args:
        words = _paths(args)
        if not words or words[0].text not in ("grep", "archive", "bundle", "ls-tree"):
            return None
        if words[0].text == "ls-tree":
            return None
        roots = words[2:] or [Word(".", ".")]
    else:
        return None
    if narrow:
        return None
    for root in roots:
        if root.dynamic:
            return f"`{name}` over a path only known at run time could read it."
        if root.glob:
            if glob_hits(root.text, cwd, central) or glob_hits(root.text.rstrip("/") + "/*", cwd, central):
                return f"`{name}` over `{root.text}` would read it."
            continue
        if _covers(_join(cwd, root.text), central):
            return (
                f"`{name}` over `{root.text}` includes profile/. Search a narrower path (docs/, ../<repo>) or "  # noqa: E501
                "filter by file type."
            )
    return None


def _find_reads(cmd: Command, cwd: str | None, central: Path) -> str | None:
    """`find ... -exec cat` and `find ... | xargs cat` read what they find, unless -name rules the file out."""
    source = cmd
    if cmd.name == "find":
        if not any(w.text in ("-exec", "-execdir", "-ok", "-okdir") for w in cmd.args):
            return None
    elif cmd.argv and cmd.argv[-1].text == "$XARGS" and cmd.piped is not None and cmd.piped.name == "find":
        source = cmd.piped
    else:
        return None
    roots = []
    for word in source.args:
        if word.text.startswith("-"):
            break
        roots.append(word)
    for index, word in enumerate(source.args[:-1]):
        if word.text in ("-name", "-iname"):
            if not fnmatch.fnmatchcase(FILENAME, source.args[index + 1].text.casefold()):
                return None
    for root in roots or [Word(".", ".")]:
        if root.dynamic or _covers(_join(cwd, root.text), central):
            return f"`find` over `{root.text}` runs a command on what it finds and could read it."
    return None


def _code_text(cmd: Command) -> str | None:
    base = re.sub(r"[0-9.]+$", "", cmd.name)
    if base not in INTERPRETERS and cmd.name not in INTERPRETERS:
        return None
    parts = list(cmd.heredocs) + [w.text for op, w in cmd.redirects if op == "<<<"]
    for index, word in enumerate(cmd.args):
        if re.fullmatch(r"-[a-zA-Z]*[ce]|--eval|--exec|-p|-pe|-ne", word.text) and index + 1 < len(cmd.args):
            parts.append(cmd.args[index + 1].text)
    return "\n".join(parts) if parts else None


def evaluate_bash(command: str, cwd: str, central: Path) -> str | None:
    if MENTION.search(command):
        return MESSAGE + "The command names it."
    try:
        items = flatten(command)
    except ShellParseError as exc:
        return f"refused: the command could not be parsed ({exc}), so it cannot be checked. Simplify it."
    for cmd, here in walk(items, cwd):
        if cmd.opaque:
            return f"refused: {cmd.opaque}; the hook cannot see what runs."
        words = cmd.argv + list(cmd.env.values()) + [w for _, w in cmd.redirects]
        for word in words:
            if MENTION.search(word.text):
                return MESSAGE + "The command spells its name indirectly."
            if word.glob and glob_hits(word.text.split("=", 1)[-1], here, central):
                return MESSAGE + f"`{word.text}` can expand to it."
            if word.dynamic and word.text.casefold().replace("./", "").startswith("profile/"):
                return MESSAGE + f"`{word.text}` under profile/ is only known at run time."
        for text in cmd.heredocs:
            if MENTION.search(text):
                return MESSAGE + "A heredoc names it."
        code = _code_text(cmd)
        if code is not None and (
            re.search(r"confiden|weights", code, re.I)
            or ("profile" in code.lower() and CODE_READS.search(code))
        ):
            return MESSAGE + "Inline code would read the profile; `baton confidence` is the only reader."
        reason = _recursive_reader(cmd, here, central) or _find_reads(cmd, here, central)
        if reason:
            return MESSAGE + reason
    return None


def _grep_tool(tool_input: dict, cwd: str, central: Path) -> str | None:
    path = tool_input.get("path")
    filter_glob = tool_input.get("glob")
    if isinstance(path, str) and path:
        joined = _join(cwd, path)
        if (
            _is_weights_path(path)
            or MENTION.search(path)
            or (joined and _is_weights_path(os.path.realpath(joined)))
        ):
            return MESSAGE
        if os.path.isfile(joined or "") or not _covers(joined, central):
            return None
    else:
        if not _covers(cwd, central):
            return None
    if isinstance(filter_glob, str) and filter_glob:
        for candidate in _expand_braces(filter_glob):
            if fnmatch.fnmatchcase(FILENAME, os.path.basename(candidate).casefold()):
                return MESSAGE + f"Grep with glob `{filter_glob}` would read it."
        return None
    kind = tool_input.get("type")
    if isinstance(kind, str) and kind and kind.lower() not in ("yaml", "yml"):
        return None
    return MESSAGE + (
        "Grep over this path would read it; pass a narrower `path` (docs/, ../<repo>) or a `glob` such as `*.md`."  # noqa: E501
    )


def check(payload: dict) -> str | None:
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    cwd = start_dir(payload)
    central = central_dir(payload)
    if tool == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return "refused: tool_input.command is missing."
        return evaluate_bash(command, cwd, central)
    if tool == "Grep":
        return _grep_tool(tool_input, cwd, central)
    if tool == "Glob":
        return None  # returns file names only, never content
    paths = [tool_input.get(key) for key in ("file_path", "path", "notebook_path")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            paths.append(edit.get("file_path") or edit.get("path"))
    for path in paths:
        if not isinstance(path, str) or not path:
            continue
        joined = _join(cwd, path) or path
        if _is_weights_path(path) or MENTION.search(path) or _is_weights_path(os.path.realpath(joined)):
            return MESSAGE
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit") and not any(
        isinstance(p, str) and p for p in paths
    ):
        return "refused: the tool call names no file path, so it cannot be checked."
    return None


if __name__ == "__main__":
    sys.exit(run_hook("protect-weights", check))
