"""Shared helpers for W1 tests: hooks are always exercised through a real subprocess and real JSON."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# A git pre-commit hook exports GIT_DIR and friends. Left in place, every `git -C <tmp>` in a test would
# act on the real repository. This once wrote test config into the shared .git/config, so it stays first.
for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ROOT / "hooks"
FIXTURE = ROOT / "fixtures" / "sample-central-repo"
SCHEMAS = ROOT / "schemas"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def _run(hook, tool, tool_input, cwd, project=None):
    env = dict(GIT_ENV)
    if project:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": str(cwd)}
    return subprocess.run(
        [sys.executable, str(HOOKS / f"{hook}.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


@pytest.fixture
def run_hook():
    return _run


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=GIT_ENV)


def make_repo(path, branch="main"):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    (path / "a.txt").write_text("a\n")
    git(path, "add", "a.txt")
    git(path, "commit", "-qm", "init")
    if branch != "main":
        git(path, "checkout", "-qb", branch)
    return path


@pytest.fixture
def repo_factory():
    return make_repo


@pytest.fixture
def repos(tmp_path):
    """tmp/central on a feature branch, tmp/on-main on main, tmp/on-feature on a feature branch."""
    central = make_repo(tmp_path / "central", "feature/F-1-S-1")
    (central / "profile").mkdir()
    (central / "profile" / "project.md").write_text(
        "| Key | Value |\n| --- | --- |\n| test.env.uri.var | TEST_URI |\n"
    )
    make_repo(tmp_path / "on-main")
    make_repo(tmp_path / "on-feature", "feature/x")
    return tmp_path


@pytest.fixture
def central_copy(tmp_path):
    """A writable copy of the fixture central repo, with stable mtimes for the Documented check."""
    import shutil

    target = tmp_path / "central"
    shutil.copytree(FIXTURE, target)
    workspace = target / "docs" / "architecture" / "workspace.dsl"
    now = workspace.stat().st_mtime + 100
    os.utime(workspace, (now, now))
    return target


@pytest.fixture
def validate():
    import jsonschema

    def check(document, schema_name):
        schema = json.loads((SCHEMAS / schema_name).read_text())
        jsonschema.validate(document, schema)

    return check
