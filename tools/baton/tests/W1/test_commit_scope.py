"""commit_scope: on story/<F>-<S> in the central repo, a commit holds only that story's artefacts."""

from pathlib import Path

import pytest

from .conftest import git, make_repo


@pytest.fixture
def central(tmp_path):
    repo = make_repo(tmp_path / "central")
    (repo / "profile" / "sensors").mkdir(parents=True)
    (repo / "profile" / "project.md").write_text("| Key | Value |\n| --- | --- |\n")
    files = [
        "docs/stories/F-002/S-010.md",
        "docs/stories/F-002/S-011.md",
        "docs/design/F-002/S-010-design.md",
        "docs/qa/F-002/S-011-test-report.md",
        "docs/qa/F-002/S-010-sensors/archunit.txt",
        "docs/stories/F-003/S-020.md",
        "docs/status.md",
        "docs/metrics.md",
        "docs/architecture/workspace.dsl",
        "profile/domain.md",
        "profile/sensors/README.md",
    ]
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    git(repo, "checkout", "-qb", "story/F-002-S-010")
    for name in files:
        (repo / name).write_text("changed\n")
    return repo


def run(run_hook, cwd: Path, command: str):
    return run_hook("commit_scope", "Bash", {"command": command}, cwd)


ALLOWED = [
    "git add docs/stories/F-002/S-010.md docs/design/F-002/S-010-design.md "
    "&& git commit -m 'S-010: design (architect, 80%)'",
    "git add docs/qa/F-002/S-010-sensors && git commit -m 'S-010: build'",
    "git add docs/status.md docs/metrics.md docs/architecture/workspace.dsl profile/domain.md "
    "profile/sensors/README.md && git commit -m 'S-010: change note'",
    "git commit -m 'S-010: nothing staged'",
    "git status",
]

REFUSED = [
    ("git add docs/qa/F-002/S-011-test-report.md && git commit -m x", "belongs to S-011"),
    ("git add docs/stories/F-003/S-020.md && git commit -m x", "feature F-003"),
    ("git add -A && git commit -m x", "belongs to S-011"),
    ("git add . && git commit -m x", "belongs to S-011"),
    ("git commit -am 'S-010: all'", "belongs to S-011"),
    ("git commit -m 'S-010: path' docs/stories/F-002/S-011.md", "belongs to S-011"),
    ("git rm -q docs/stories/F-002/S-011.md && git commit -m x", "belongs to S-011"),
]


@pytest.mark.parametrize("command", ALLOWED)
def test_own_artefacts_and_shared_files_pass(run_hook, central, command):
    done = run(run_hook, central, command)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize(("command", "why"), REFUSED)
def test_another_storys_files_are_refused(run_hook, central, command, why):
    done = run(run_hook, central, command)
    assert done.returncode == 2 and why in done.stderr, done.stderr


def test_already_staged_files_count(run_hook, central):
    git(central, "add", "docs/qa/F-002/S-011-test-report.md")
    done = run(run_hook, central, "git commit -m 'S-010: x'")
    assert done.returncode == 2 and "S-011" in done.stderr


def test_from_a_subfolder_and_with_dash_c(run_hook, central):
    sub = central / "docs" / "stories" / "F-002"
    assert run(run_hook, sub, "git add S-011.md && git commit -m x").returncode == 2
    other = central.parent
    command = "git -C central add docs/stories/F-002/S-011.md && git -C central commit -m x"
    assert run(run_hook, other, command).returncode == 2


def test_other_branches_and_repos_are_not_its_business(run_hook, central, tmp_path):
    git(central, "checkout", "-q", "-b", "feature/F-002-S-010")
    assert run(run_hook, central, "git add -A && git commit -m x").returncode == 0
    service = make_repo(tmp_path / "service", "story/F-002-S-010")
    (service / "S-011.md").write_text("y")
    assert run(run_hook, service, "git add -A && git commit -m x").returncode == 0


def test_a_story_branch_must_name_the_story(run_hook, central):
    git(central, "checkout", "-q", "-b", "story/whatever")
    done = run(run_hook, central, "git commit -m x")
    assert done.returncode == 2 and "story/<feature-id>-<story-id>" in done.stderr


def test_a_backlog_story(run_hook, tmp_path):
    repo = make_repo(tmp_path / "c")
    (repo / "profile").mkdir()
    (repo / "profile" / "project.md").write_text("x")
    for name in ("docs/stories/backlog/S-050.md", "docs/stories/backlog/S-051.md"):
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("x")
    git(repo, "checkout", "-q", "-b", "story/backlog-S-050")
    assert run(run_hook, repo, "git add docs/stories/backlog/S-050.md && git commit -m x").returncode == 0
    assert run(run_hook, repo, "git add docs/stories/backlog/S-051.md && git commit -m x").returncode == 2
