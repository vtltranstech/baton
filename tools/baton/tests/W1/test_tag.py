"""baton tag: an annotated tag on the default branch; refused elsewhere or when the tag exists."""

import subprocess

import pytest
from baton.cli import main

from .conftest import GIT_ENV, git, make_repo


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    for key in ("GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL"):
        monkeypatch.setenv(key, GIT_ENV[key])


def tags(repo):
    return subprocess.run(["git", "-C", str(repo), "tag", "-n1"], capture_output=True, text=True).stdout


def test_tags_main_with_the_story_title(tmp_path, capsys):
    repo = make_repo(tmp_path / "central")
    (repo / "docs" / "stories" / "F-002").mkdir(parents=True)
    (repo / "docs" / "stories" / "F-002" / "S-010.md").write_text("# S-010 Apply a loyalty discount\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "S-010: trace regenerated; PR x")
    assert main(["tag", "S-010", "--central", str(repo)]) == 0
    assert "S-010: Apply a loyalty discount" in tags(repo)
    kind = subprocess.run(["git", "-C", str(repo), "cat-file", "-t", "S-010"], capture_output=True, text=True)
    assert kind.stdout.strip() == "tag"
    assert "git push origin S-010" in capsys.readouterr().out


def test_refuses_an_existing_tag(tmp_path, capsys):
    repo = make_repo(tmp_path / "central")
    assert main(["tag", "F-002", "--central", str(repo)]) == 0
    assert main(["tag", "F-002", "--central", str(repo)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_refuses_off_main(tmp_path, capsys):
    repo = make_repo(tmp_path / "central", "story/F-002-S-010")
    assert main(["tag", "S-010", "--central", str(repo)]) == 2
    assert "story/F-002-S-010" in capsys.readouterr().err
    assert tags(repo) == ""


def test_refuses_a_bad_id_and_no_repository(tmp_path):
    assert main(["tag", "v1.0", "--central", str(tmp_path)]) == 2
    assert main(["tag", "S-010", "--central", str(tmp_path)]) == 2


def test_follows_a_default_branch_that_is_not_main(tmp_path, capsys):
    repo = make_repo(tmp_path / "central")
    git(repo, "branch", "-m", "main", "develop")
    git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    assert main(["tag", "S-010", "--central", str(repo)]) == 0
    git(repo, "checkout", "-qb", "main")
    assert main(["tag", "S-011", "--central", str(repo)]) == 2
    assert "(develop)" in capsys.readouterr().err
