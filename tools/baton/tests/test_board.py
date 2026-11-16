"""baton board: every story's branches in every repo, pushed or not, merged, tagged, and what is next."""

from __future__ import annotations

import json
import os
import subprocess

import pytest
from baton.board import collect
from baton.cli import main


def _git(repo, *args):
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _commit(repo, name, message):
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(message + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)


def _repo(tmp_path, name):
    origin = tmp_path / f"{name}.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = tmp_path / name
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "remote", "add", "origin", str(origin))
    return repo


@pytest.fixture
def product(tmp_path):
    central, svc = _repo(tmp_path, "central"), _repo(tmp_path, "svc")
    (central / "profile").mkdir()
    (central / "profile" / "project.md").write_text("| Repo | Path |\n| --- | --- |\n| svc | ../svc |\n")
    for sid, state in (("S-1", "Draft"), ("S-2", "Done"), ("S-3", "Ready"), ("S-4", "Draft")):
        (central / "docs" / "stories" / "F-1").mkdir(parents=True, exist_ok=True)
        story = central / "docs" / "stories" / "F-1" / f"{sid}.md"
        story.write_text(f"# {sid} Title {sid}\nState: {state}\n")
    _commit(central, "README.md", "seed")
    _commit(svc, "README.md", "seed")
    for repo in (central, svc):
        _git(repo, "push", "-q", "origin", "main")
        _git(repo, "remote", "set-head", "origin", "main")

    # S-1: pushed once, then one more commit that was never pushed.
    _git(central, "checkout", "-qb", "story/F-1-S-1")
    _commit(central, "docs/design/F-1/S-1-design.md", "S-1: design")
    _git(central, "push", "-q", "-u", "origin", "story/F-1-S-1")
    _commit(central, "docs/design/F-1/S-1-design.md", "S-1: design revised")
    # S-2: merged into main (no squash) and tagged.
    _git(central, "checkout", "-q", "main")
    _git(central, "checkout", "-qb", "story/F-1-S-2")
    _commit(central, "docs/design/F-1/S-2-design.md", "S-2: design")
    _git(central, "push", "-q", "origin", "story/F-1-S-2")
    _git(central, "checkout", "-q", "main")
    _git(central, "merge", "-q", "--no-ff", "-m", "Merge S-2", "story/F-1-S-2")
    _git(central, "push", "-q", "origin", "main")
    _git(central, "tag", "-a", "S-2", "-m", "S-2")
    # S-3: docs pushed; the code branch in svc exists only on the laptop.
    _git(central, "checkout", "-qb", "story/F-1-S-3")
    _commit(central, "docs/design/F-1/S-3-design.md", "S-3: design")
    _git(central, "push", "-q", "origin", "story/F-1-S-3")
    _git(central, "checkout", "-q", "main")
    _git(svc, "checkout", "-qb", "feature/F-1-S-3")
    _commit(svc, "src/a.txt", "S-3: first task")
    return central


def test_each_story_shows_where_its_work_is(product):
    rows = {r["story"]: r for r in collect(product)["stories"]}
    assert rows["S-1"]["central"]["status"] == "1 unpushed"
    assert rows["S-1"]["next"] == "push story/F-1-S-1 (central)"
    assert rows["S-2"]["central"]["status"] == "merged" and rows["S-2"]["tagged"]
    assert rows["S-2"]["next"] == "shipped"
    assert rows["S-3"]["central"]["status"] == "pushed"
    assert [(c["name"], c["status"]) for c in rows["S-3"]["code"]] == [("svc", "not pushed")]
    assert rows["S-3"]["next"] == "push feature/F-1-S-3 (svc)"
    assert rows["S-4"]["central"]["status"] == "none" and rows["S-4"]["code"] == []
    assert rows["S-3"]["central"]["last"]["subject"] == "S-3: design"


def test_merged_without_a_tag_asks_for_the_tag(product):
    _git(product, "tag", "-d", "S-2")
    row = next(r for r in collect(product)["stories"] if r["story"] == "S-2")
    assert row["next"] == "baton tag S-2 on the default branch"


def test_the_cli_prints_the_board_and_one_story(product, capsys):
    assert main(["board", "--central", str(product)]) == 0
    out = capsys.readouterr().out
    assert "F-1" in out and "1 unpushed" in out and "shipped" in out
    assert main(["board", "--central", str(product), "--story", "S-3"]) == 0
    out = capsys.readouterr().out
    assert "svc" in out and "feature/F-1-S-3: not pushed, local only" in out
    assert main(["board", "--central", str(product), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["base"] == "origin/main"
    assert main(["board", "--central", str(product), "--story", "S-9"]) == 2


def test_gate_0_is_read_from_the_story_branch_too(product):
    """S-5 and its context manifest live only on story/F-1-S-5, as they do until the docs PR merges."""
    _git(product, "checkout", "-qb", "story/F-1-S-5")
    (product / "docs" / "stories" / "F-1" / "S-5.md").write_text("# S-5 On its branch\nState: Draft\n")
    _commit(product, "docs/design/F-1/S-5-context.json", json.dumps({"blocking": 2, "gate": []}))
    _git(product, "checkout", "-q", "main")
    (product / "profile" / "branch-points.yaml").write_text("points: []\n")
    rows = {r["story"]: r for r in collect(product)["stories"]}
    assert rows["S-5"]["where"] == "story/F-1-S-5" and rows["S-5"]["gate"] == "blocked"
    assert rows["S-5"]["next"] == "push story/F-1-S-5 (central)"
    assert rows["S-4"]["gate"] == "not checked" and rows["S-4"]["next"] == "baton context check S-4"
