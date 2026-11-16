#!/usr/bin/env python3
"""PreToolUse Bash: no datastore URI literals; database clients only through the profile's test variable."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import central_dir, run_hook, start_dir, walk  # noqa: E402
from _shell import Command, ShellParseError, Word, flatten  # noqa: E402

# A scheme followed by the start of a host. A bare scheme (`grep -rn "mongodb://" src`) names no server,
# cannot connect to anything, and is how the security agent looks for secrets, so it is allowed.
URI = re.compile(
    r"(?i)\b(mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb|sqlserver)://(?=[^\s\"'`)>|;&,]|$(?!))"
    r"|\bjdbc:[a-z]"
)
CLIENTS = {
    "mongosh",
    "mongo",
    "mongodump",
    "mongorestore",
    "mongoimport",
    "mongoexport",
    "psql",
    "pg_dump",
    "pg_restore",
    "mysql",
    "mariadb",
    "mysqldump",
    "sqlcmd",
}
MONGO_SHELLS = {"mongosh", "mongo"}
REMOTE_RUNNERS = {"docker", "podman", "kubectl", "oc", "ssh", "nerdctl"}
TARGET_FLAGS = {"--host", "-h", "--port", "-p", "-H", "-S", "--server", "--uri", "--dbname"}
WRITE_OPS = re.compile(
    r"\b(insert\w*|update\w*|delete\w*|remove|drop\w*|replaceOne|bulkWrite|findOneAnd\w*|renameCollection"
    r"|createCollection|createIndex\w*|runCommand|adminCommand|eval)\s*\(|\$(out|merge)\b"
)
VAR_ROW = re.compile(r"^\|\s*test\.env\.uri\.var\s*\|\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*\|", re.M)
PREFIX = "refused: "


def _uri_in(command: str, items: list) -> str | None:
    found = URI.search(command)
    if found:
        return found.group(0)
    for item in items:
        if isinstance(item, Command):
            for word in item.argv + list(item.env.values()) + [w for _, w in item.redirects]:
                found = URI.search(word.text)
                if found:
                    return found.group(0)
    return None


def test_env_var(payload: dict) -> str | None:
    path = central_dir(payload) / "profile" / "project.md"
    if not path.is_file():
        return None
    match = VAR_ROW.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def _client_in(cmd: Command) -> tuple[str | None, list[Word]]:
    if cmd.name in CLIENTS:
        return cmd.name, cmd.args
    if cmd.name in REMOTE_RUNNERS:
        for index, word in enumerate(cmd.args):
            if os.path.basename(word.text).lower() in CLIENTS:
                return os.path.basename(word.text).lower(), cmd.args[index + 1 :]
    return None, []


def _scripts_of(args: list[Word], cwd) -> tuple[list[str], str | None]:
    """The text of every script file a client would run; a reason when one cannot be inspected."""
    texts, reason = [], None
    index = 0
    candidates = []
    while index < len(args):
        word = args[index]
        if word.text in ("-f", "--file") and index + 1 < len(args):
            candidates.append(args[index + 1])
            index += 1
        elif word.text.endswith((".js", ".mongodb", ".sql")):
            candidates.append(word)
        index += 1
    for word in candidates:
        path = None if word.dynamic or cwd is None else Path(cwd, os.path.expanduser(word.text))
        if path is None or not path.is_file():
            reason = f"script {word.text} cannot be read, so its operations cannot be checked."
        else:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return texts, reason


def _check_client(client: str, args: list[Word], cmd: Command, cwd, allowed, assigned) -> str | None:
    if allowed is None:
        return PREFIX + (
            f"`{client}` needs the test-environment variable, but profile/project.md is missing or has no "
            "`test.env.uri.var` row. Run /onboard or fix the profile."
        )
    if allowed in assigned:
        return (
            PREFIX + f"${allowed} is reassigned in this command; it must come from the environment unchanged."
        )
    expanded = {name for word in args for name in word.vars}
    if allowed not in expanded:
        return (
            PREFIX + f"`{client}` may only connect through ${allowed} (profile/project.md: test.env.uri.var)."
        )
    others = expanded - {allowed}
    if others:
        return (
            PREFIX
            + f"`{client}` uses other variables ({', '.join(sorted(others))}); only ${allowed} is allowed."
        )
    if any(w.dynamic and not w.vars for w in args):
        return PREFIX + f"`{client}` has an argument only known at run time, so its target cannot be checked."
    for word in args:
        flag = word.text.split("=")[0]
        if flag in TARGET_FLAGS:
            return PREFIX + f"`{client} {flag}` overrides the target; only ${allowed} is allowed."
    if client in MONGO_SHELLS:
        if cmd.piped is not None or any(op == "<" for op, _ in cmd.redirects):
            return (
                PREFIX
                + f"`{client}` reading stdin or a file redirect cannot be checked. Use --eval or a script path."  # noqa: E501
            )
        scripts, unreadable = _scripts_of(args, cwd)
        if unreadable:
            return PREFIX + unreadable
        text = " ".join(
            [w.text for w in args]
            + cmd.heredocs
            + [w.text for op, w in cmd.redirects if op == "<<<"]
            + scripts
        )
        found = WRITE_OPS.search(text)
        if found:
            return (
                PREFIX + f"`{found.group(0).rstrip('( ')}` is a write operation; data checks are read-only."
            )
    return None


def evaluate(command: str, cwd: str, allowed: str | None) -> str | None:
    assigned: set[str] = set()
    try:
        items = flatten(command, assigned=assigned)
    except ShellParseError as exc:
        return PREFIX + f"the command could not be parsed ({exc}), so it cannot be checked. Simplify it."
    uri = _uri_in(command, items)
    if uri:
        return PREFIX + f"literal datastore URI (`{uri}...`). Use the variable named in profile/project.md."
    for cmd, here in walk(items, cwd):
        if cmd.opaque:
            return PREFIX + f"{cmd.opaque}; the hook cannot see what runs."
        client, args = _client_in(cmd)
        if client:
            reason = _check_client(client, args, cmd, here, allowed, assigned)
            if reason:
                return reason
    return None


def check(payload: dict) -> str | None:
    if payload.get("tool_name", "Bash") != "Bash":
        return None
    command = payload.get("tool_input", {}).get("command")
    if not isinstance(command, str):
        return PREFIX + "tool_input.command is missing."
    return evaluate(command, start_dir(payload), test_env_var(payload))


if __name__ == "__main__":
    sys.exit(run_hook("protect-env", check))
