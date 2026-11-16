#!/usr/bin/env python3
"""PreToolUse Bash: on a central-repo story/<F>-<S> branch, a commit holds only that story's artefacts.

contracts/versioning.md section 1. The staged files, plus what a `git add`, `git mv` or a removal earlier in
the same command stages, and `-a` or pathspecs on the commit itself, must not touch another story's or
another feature's folders. Shared files are always allowed: docs/status.md, docs/metrics.md,
docs/architecture/*, profile/domain.md, profile/sensors/README.md. Service repos and other branches are
not this hook's business (protect_main guards main).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import run_hook, start_dir, walk  # noqa: E402
from _shell import ShellParseError, flatten  # noqa: E402

PREFIX = "refused: "
STAGING = ("add", "mv", "r" "m")  # git subcommands that stage; the last is git's removal
SHARED = ("docs/status.md", "docs/metrics.md", "profile/domain.md", "profile/sensors/README.md")
SHARED_DIRS = ("docs/architecture/",)
STORY_KINDS = ("stories", "design", "qa", "changes")
BRANCH = re.compile(r"^story/(.+)-([A-Za-z]+-\d+)$")
STORY_ID = re.compile(r"^([A-Za-z]+-\d+)(?:[-.]|$)")
WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
COMMIT_VALUE = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
                "--author", "--date", "--fixup", "--squash", "-t", "--template", "--cleanup",
                "--trailer", "--pathspec-from-file"}


def _git(repo: str, *args: str) -> subprocess.CompletedProcess | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, env=env, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None


def _lines(done: subprocess.CompletedProcess | None) -> list[str]:
    return [line for line in (done.stdout.splitlines() if done and done.returncode == 0 else []) if line]


def owner(path: str) -> tuple[str | None, str | None]:
    """(feature, story) a central-repo path belongs to; None for a part it does not name."""
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "docs" and parts[1] in STORY_KINDS:
        story = STORY_ID.match(parts[3]) if len(parts) > 3 else None
        return parts[2], story.group(1) if story else None
    if len(parts) >= 4 and parts[0] == "docs" and parts[1] == "archive":
        story = STORY_ID.match(parts[4]) if len(parts) > 4 else None
        return parts[2], story.group(1) if story else None
    if len(parts) == 3 and parts[:2] == ["docs", "trace"] and parts[2].endswith(".html"):
        return parts[2][: -len(".html")], None
    return None, None


def problem(path: str, feature: str, story: str) -> str | None:
    if path in SHARED or path.startswith(SHARED_DIRS):
        return None
    other_feature, other_story = owner(path)
    if other_feature is not None and other_feature != feature:
        return f"{path} is in feature {other_feature}'s folder"
    if other_story is not None and other_story.casefold() != story.casefold():
        return f"{path} belongs to {other_story}"
    return None


def _split(args: list) -> tuple[dict, list]:
    """git's global options (-C dirs) and the rest."""
    found = {"C": [], "dynamic": False}
    index = 0
    while index < len(args) and args[index].text.startswith("-"):
        key, _, value = args[index].text.partition("=")
        if key in WITH_VALUE and not value:
            index += 1
            if index < len(args):
                value = args[index].text
                found["dynamic"] = found["dynamic"] or args[index].dynamic
        if key == "-C":
            found["C"].append(value)
        index += 1
    return found, args[index:]


def _paths(words: list, repo_cwd: str, top: str, skip_values: set[str] | tuple = ()) -> list[str]:
    out, skip, literal = [], False, False
    for word in words:
        text = word.text
        if skip:
            skip = False
            continue
        if not literal and text == "--":
            literal = True
            continue
        if not literal and text.startswith("-"):
            if text in skip_values:
                skip = True
            continue
        absolute = os.path.normpath(os.path.join(repo_cwd, text))
        out.append(os.path.relpath(absolute, top).replace(os.sep, "/"))
    return out


def _commits_all(args: list) -> bool:
    """`-a`, `--all`, or `a` among combined short flags (`-am`)."""
    for word in args:
        text = word.text
        if text == "--all" or (text.startswith("-") and not text.startswith("--") and "a" in text[1:]):
            return True
        if text in COMMIT_VALUE:
            break  # what follows is a value, not a flag
    return False


def _all_changes(top: str, under: str) -> list[str]:
    status = _lines(_git(top, "status", "--porcelain", "-uall", "--", under or "."))
    paths = []
    for line in status:
        entry = line[3:]
        paths += [p.strip('"') for p in entry.split(" -> ")]
    return paths


def evaluate(command: str, cwd: str) -> str | None:
    try:
        items = flatten(command)
    except ShellParseError as exc:
        return PREFIX + f"the command could not be parsed ({exc}), so its commit scope cannot be checked."
    pending: dict[str, list[str]] = {}
    for cmd, here in walk(items, cwd):
        if not cmd.argv or cmd.name not in ("git", "git.exe"):
            continue
        globals_, rest = _split(cmd.args)
        if not rest or here is None or globals_["dynamic"]:
            continue
        repo_cwd = here
        for step in globals_["C"]:
            repo_cwd = os.path.normpath(os.path.join(repo_cwd, os.path.expanduser(step)))
        top_done = _git(repo_cwd, "rev-parse", "--show-toplevel")
        if not top_done or top_done.returncode != 0:
            continue
        top = top_done.stdout.strip()
        if not os.path.isfile(os.path.join(top, "profile", "project.md")):
            continue  # not the central repo
        sub, args = rest[0].text, rest[1:]
        under = os.path.relpath(repo_cwd, top).replace(os.sep, "/")
        under = "" if under == "." else under
        if sub in STAGING:
            flags = {w.text for w in args}
            if sub == "add" and flags & {"-A", "--all", "-u", "--update"}:
                pending.setdefault(top, []).extend(_all_changes(top, ""))
            else:
                paths = _paths(args, repo_cwd, top)
                for path in paths:
                    if path in ("", ".") or os.path.isdir(os.path.join(top, path)):
                        pending.setdefault(top, []).extend(_all_changes(top, "" if path == "." else path))
                    else:
                        pending.setdefault(top, []).append(path)
            continue
        if sub != "commit":
            continue
        branch_done = _git(top, "symbolic-ref", "--short", "-q", "HEAD")
        branch = branch_done.stdout.strip() if branch_done and branch_done.returncode == 0 else ""
        if not branch.startswith("story/"):
            continue
        match = BRANCH.match(branch)
        if not match:
            return (
                PREFIX
                + f"branch {branch} does not name a story. Central-repo story branches are story/<feature-id>-<story-id>."  # noqa: E501
            )
        feature, story = match.group(1), match.group(2)
        staged = _lines(_git(top, "diff", "--cached", "--name-only"))
        if _commits_all(args):
            staged += _lines(_git(top, "diff", "--name-only"))
        staged += _paths(args, repo_cwd, top, COMMIT_VALUE)
        staged += pending.get(top, [])
        wrong = sorted({p for p in (problem(path, feature, story) for path in staged) if p})
        if wrong:
            return (
                PREFIX
                + f"on {branch} a commit holds only {story}'s artefacts and the shared files "
                + f"({', '.join(SHARED)}, docs/architecture/*). This one would include: {'; '.join(wrong)}. "
                + "Unstage them with `git restore --staged <path>` and commit them on their own story branch."
            )
    return None


def check(payload: dict) -> str | None:
    if payload.get("tool_name", "Bash") != "Bash":
        return None
    command = payload.get("tool_input", {}).get("command")
    if not isinstance(command, str):
        return PREFIX + "tool_input.command is missing."
    return evaluate(command, start_dir(payload))


if __name__ == "__main__":
    sys.exit(run_hook("commit-scope", check))
