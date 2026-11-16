#!/usr/bin/env python3
"""PreToolUse Bash: no commit or push on main, master or the default branch; no merge, force or deletion."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import run_hook, start_dir, walk  # noqa: E402
from _shell import Command, ShellParseError, Word, flatten  # noqa: E402

PROTECTED = {"main", "master"}
COMMIT_LIKE = {"commit", "cherry-pick", "revert", "am", "rebase"}
GLOBAL_WITH_VALUE = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--config-env",
    "--super-prefix",
    "--attr-source",
    "--list-cmds",
}
PUSH_WITH_VALUE = {
    "--repo",
    "--receive-pack",
    "--exec",
    "-o",
    "--push-option",
    "--signed",
    "--recurse-submodules",
}
PREFIX = "refused: "


class _State:
    def __init__(self, cwd):
        self.cwd = cwd
        self.branch_after: dict[str, str | None] = {}  # git dir -> branch after a checkout in this chain
        self.env: dict[str, Word] = {}


def _git(repo_dir, env_extra, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(env_extra)
    try:
        return subprocess.run(
            ["git", "-C", repo_dir, *args], capture_output=True, text=True, env=env, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _is_protected(name: str | None, extra: frozenset = frozenset()) -> bool:
    if not name:
        return False
    name = name.casefold()
    for prefix in ("refs/heads/", "heads/"):
        name = name.removeprefix(prefix)
    return name in PROTECTED or name in extra


class _Target:
    """The repository one git invocation acts on, and what we can say about its current branch."""

    def __init__(self, state: _State, cwd, cmd: Command, globals_: dict):
        self.state = state
        self.unknown = cwd is None or globals_["dynamic"]
        self.dir = cwd
        for step in globals_["C"]:
            self.dir = (
                None
                if self.dir is None
                else os.path.normpath(os.path.join(self.dir, os.path.expanduser(step)))
            )
        self.env = {}
        for source in (state.env, cmd.env):
            for key in ("GIT_DIR", "GIT_WORK_TREE"):
                if key in source:
                    if source[key].dynamic:
                        self.unknown = True
                    self.env[key] = source[key].text
        if globals_["git_dir"]:
            self.env["GIT_DIR"] = globals_["git_dir"]
        if "GIT_DIR" in self.env and self.dir and not self.unknown:
            self.env["GIT_DIR"] = os.path.normpath(os.path.join(self.dir, self.env["GIT_DIR"]))

    def key(self) -> str | None:
        if self.unknown or self.dir is None or not os.path.isdir(self.dir):
            return None
        done = _git(self.dir, self.env, "rev-parse", "--absolute-git-dir")
        return done.stdout.strip() if done and done.returncode == 0 else None

    def protected(self) -> frozenset:
        """The repository's default branch (origin/HEAD), protected like main whatever its name."""
        if self.unknown or self.dir is None or not os.path.isdir(self.dir):
            return frozenset()
        done = _git(self.dir, self.env, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
        if not done or done.returncode != 0:
            return frozenset()
        return frozenset({done.stdout.strip().split("/", 1)[-1].casefold()})

    def current(self):
        """(known, branch). branch "" = detached or not a repository, so there is nothing to protect."""
        if self.unknown or self.dir is None:
            return False, None
        if not os.path.isdir(self.dir):
            return False, None
        key = self.key()
        if key is None:
            return True, ""
        if key in self.state.branch_after:
            branch = self.state.branch_after[key]
            return branch is not None, branch
        done = _git(self.dir, self.env, "symbolic-ref", "--short", "-q", "HEAD")
        if done is None:
            return False, None
        return True, done.stdout.strip() if done.returncode == 0 else ""


def _parse_globals(args: list[Word]):
    info = {"C": [], "git_dir": None, "dynamic": False, "alias": False}
    index = 0
    while index < len(args):
        word = args[index]
        text = word.text
        if not text.startswith("-"):
            break
        key, _, value = text.partition("=")
        if key in GLOBAL_WITH_VALUE and not value:
            index += 1
            if index >= len(args):
                break
            value_word = args[index]
            value, dynamic = value_word.text, value_word.dynamic
        else:
            dynamic = word.dynamic
        if key in ("-C", "--git-dir", "--work-tree"):
            info["dynamic"] = info["dynamic"] or dynamic
        if key == "-C":
            info["C"].append(value)
        elif key == "--git-dir":
            info["git_dir"] = value
        elif key in ("-c", "--config-env") and value.lower().startswith("alias."):
            info["alias"] = True
        index += 1
    return info, args[index:]


def _has_short(words: list[Word], letter: str) -> bool:
    return any(w.text.startswith("-") and not w.text.startswith("--") and letter in w.text[1:] for w in words)


def _flag(words: list[Word], *names: str) -> bool:
    return any(w.text.split("=")[0] in names for w in words)


def _check_push(args: list[Word], target: _Target) -> str | None:
    if _flag(args, "--force", "--force-with-lease", "--force-if-includes") or _has_short(
        [w for w in args if not w.text.startswith("--") and w.text != "-o"], "f"
    ):
        return PREFIX + "force-push is never allowed from an agent; history is not rewritten. Ask a human."
    if _flag(args, "--delete", "--prune", "--mirror", "--all", "--branches") or _has_short(
        [w for w in args if w.text != "-o"], "d"
    ):
        return (
            PREFIX
            + "`git push` with --delete/--prune/--mirror/--all can touch main or tags. Name one feature branch."  # noqa: E501
        )
    positional, skip = [], False
    for word in args:
        if skip:
            skip = False
        elif word.text in PUSH_WITH_VALUE:
            skip = True
        elif not word.text.startswith("-"):
            positional.append(word)
    if any(w.dynamic or w.glob for w in positional):
        return (
            PREFIX
            + "cannot tell which branch this `git push` targets (a value is only known at run time). Name the feature branch literally."  # noqa: E501
        )
    known, branch = target.current()
    refspecs = positional[1:]
    if not refspecs:
        if not known:
            return (
                PREFIX
                + "cannot tell which branch this `git push` targets. Name the feature branch literally."
            )
        if _is_protected(branch, target.protected()):
            return (
                PREFIX
                + f"this `git push` would update {branch}. Pushing to main or master is for humans; push a feature branch."  # noqa: E501
            )
        if target.dir and branch and not target.env:
            mode = _git(target.dir, {}, "config", "--get", "push.default")
            merge = _git(target.dir, {}, "config", "--get", f"branch.{branch}.merge")
            if (
                mode
                and merge
                and mode.stdout.strip() in ("upstream", "tracking")
                and _is_protected(merge.stdout.strip(), target.protected())
            ):
                return (
                    PREFIX
                    + f"branch {branch} pushes to {merge.stdout.strip()}. Pushing to main or master is for humans."  # noqa: E501
                )
        return None
    for spec in refspecs:
        text = spec.text
        if text.startswith("+"):
            return PREFIX + f"`{text}` is a force-push; never allowed from an agent. Ask a human."
        source, colon, dest = text.partition(":")
        if colon and not dest:
            dest = source
        if colon and not source:
            return PREFIX + f"`{text}` deletes a remote ref; never allowed from an agent. Ask a human."
        if not colon:
            dest = source
        if dest in ("HEAD", "@"):
            if not known:
                return PREFIX + "cannot tell which branch HEAD is. Name the feature branch literally."
            dest = branch
        if _is_protected(dest, target.protected()):
            return (
                PREFIX
                + f"`git push` to {dest} (`{text}`). Pushing to main or master is for humans; push a feature branch."  # noqa: E501
            )
    return None


def _simulate_switch(sub: str, args: list[Word], target: _Target) -> str | None:
    positional, new_branch, force_new = [], None, False
    index = 0
    while index < len(args):
        word = args[index]
        if word.text == "--":
            positional = None
            break
        if word.text in ("-b", "-c", "-B", "-C", "--orphan", "--create", "--force-create"):
            force_new = word.text in ("-B", "-C", "--force-create")
            index += 1
            if index < len(args):
                new_branch = args[index]
        elif not word.text.startswith("-"):
            positional.append(word)
        index += 1
    key = target.key()
    if new_branch is not None:
        if force_new and _is_protected(new_branch.text, target.protected()):
            return (
                PREFIX
                + f"`git {sub} {new_branch.text}` would reset {new_branch.text}. Only humans move main or master."  # noqa: E501
            )
        if key:
            target.state.branch_after[key] = None if new_branch.dynamic else new_branch.text
    elif positional and key:
        first = positional[0]
        target.state.branch_after[key] = None if first.dynamic else first.text
    return None


def _check_git(cmd: Command, state: _State, cwd, depth: int = 0) -> str | None:
    globals_, rest = _parse_globals(cmd.args)
    if globals_["alias"]:
        return PREFIX + "`git -c alias....` can hide any git command. Run the git command directly."
    if not rest:
        return None
    if rest[0].dynamic:
        return (
            PREFIX
            + "the git subcommand is only known at run time, so the hook cannot check it. Write it literally."
        )
    target = _Target(state, cwd, cmd, globals_)
    sub, args = rest[0].text, rest[1:]
    if sub == "push":
        return _check_push(args, target)
    if sub == "merge":
        if _flag(args, "--abort", "--quit"):
            return None
        return PREFIX + "`git merge` is never run by an agent; a human merges the PR."
    if sub == "pull":
        if _flag(args, "--ff-only"):
            return None
        if _flag(args, "--rebase") or _has_short(args, "r"):
            sub = "rebase"
        else:
            return (
                PREFIX
                + "`git pull` can create a merge and agents never merge. Use `git pull --ff-only` or `git fetch`."  # noqa: E501
            )
    if sub in COMMIT_LIKE:
        if sub == "rebase" and _flag(args, "--abort", "--quit"):
            return None
        known, branch = target.current()
        if not known:
            return (
                PREFIX
                + f"cannot tell which repository or branch this `git {sub}` runs on. Use a literal path and a feature branch."  # noqa: E501
            )
        if _is_protected(branch, target.protected()):
            return (
                PREFIX
                + f"`git {sub}` on {branch} in {target.dir}. Create the story branch first: git checkout -b feature/<feature-id>-<story-id>."  # noqa: E501
            )
        return None
    if sub == "branch":
        if _flag(args, "--delete") and _flag(args, "--force") or _has_short(args, "D"):
            return PREFIX + "`git branch -D` destroys unmerged work; a human deletes branches."
        moving = _flag(args, "--move", "--copy", "--force", "--delete") or any(
            w.text.startswith("-") and not w.text.startswith("--") and set(w.text[1:]) & set("mMcCfd")
            for w in args
        )
        names = [w.text for w in args if not w.text.startswith("-")]
        if moving and any(_is_protected(n, target.protected()) for n in names):
            return PREFIX + "this `git branch` changes main or master. Only humans move them."
        return None
    if sub == "tag":
        if _flag(args, "--delete") or _has_short(args, "d"):
            return PREFIX + "`git tag -d` deletes a release marker; a human does this."
        return None
    if sub == "update-ref":
        protected = target.protected()
        if any(_is_protected(w.text, protected) or w.dynamic for w in args if not w.text.startswith("-")):
            return PREFIX + "`git update-ref` on main or master. Only humans move them."
        return None
    if sub in ("checkout", "switch"):
        return _simulate_switch(sub, args, target)
    if depth == 0 and target.dir and not target.unknown and os.path.isdir(target.dir):
        alias = _git(target.dir, target.env, "config", "--get", f"alias.{sub}")
        if alias and alias.returncode == 0 and alias.stdout.strip():
            return _check_alias(alias.stdout.strip(), args, cmd, state, cwd, depth)
    return None


def _check_alias(text: str, args: list[Word], cmd: Command, state: _State, cwd, depth: int) -> str | None:
    tail = " ".join(shlex.quote(w.text) for w in args)
    code = f"{text[1:]} {tail}" if text.startswith("!") else f"git {text} {tail}"
    return _evaluate(code, state, cwd, depth + 1)


def _check_forge(cmd: Command) -> str | None:
    words = [w.text for w in cmd.args]
    if cmd.name in ("gh", "glab"):
        if len(words) >= 2 and words[0] in ("pr", "mr") and words[1] == "merge":
            return PREFIX + f"`{cmd.name} {words[0]} merge` is a merge; a human merges the PR."
        if words and words[0] == "api" and any(w.rstrip("/").endswith("/merge") for w in words):
            return PREFIX + "this API call merges a pull request; a human merges the PR."
    return None


def _evaluate(command: str, state: _State, cwd, depth: int = 0) -> str | None:
    items = flatten(command)
    state.env = {}
    for cmd, here in walk(items, cwd):
        if cmd.opaque:
            return PREFIX + f"{cmd.opaque}; the hook cannot see what runs. Write the git command directly."
        if not cmd.argv:
            for key in ("GIT_DIR", "GIT_WORK_TREE"):
                if key in cmd.env:
                    state.env[key] = cmd.env[key]
            continue
        if cmd.name == "export":
            for word in cmd.args:
                key, sep, value = word.text.partition("=")
                if sep and key in ("GIT_DIR", "GIT_WORK_TREE"):
                    state.env[key] = Word(value, word.raw, word.dynamic)
        reason = _check_forge(cmd)
        if reason:
            return reason
        first = cmd.argv[0]
        is_git = cmd.name in ("git", "git.exe") or first.text.endswith("/git")
        guessed = (
            first.dynamic
            and cmd.args
            and cmd.args[0].text
            in (
                "push",
                "merge",
                "pull",
                "commit",
                "branch",
                "tag",
                "rebase",
                "cherry-pick",
                "revert",
                "am",
                "update-ref",
            )
        )
        if guessed:
            return (
                PREFIX
                + "the program name is only known at run time and the arguments look like git. Write it literally."  # noqa: E501
            )
        if is_git:
            reason = _check_git(cmd, state, here, depth)
            if reason:
                return reason
    return None


def evaluate(command: str, cwd: str) -> str | None:
    try:
        return _evaluate(command, _State(cwd), cwd)
    except ShellParseError as exc:
        return PREFIX + f"the command could not be parsed ({exc}), so it cannot be checked. Simplify it."


def check(payload: dict) -> str | None:
    if payload.get("tool_name", "Bash") != "Bash":
        return None
    command = payload.get("tool_input", {}).get("command")
    if not isinstance(command, str):
        return PREFIX + "tool_input.command is missing."
    return evaluate(command, start_dir(payload))


if __name__ == "__main__":
    sys.exit(run_hook("protect-main", check))
