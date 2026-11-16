"""A story cannot start until every story in its `Depends-On:` line is Done."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from baton import state_check

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools" / "baton" / "cli.py"
HOOK = ROOT / "hooks" / "state_gate.py"


def write_story(central, story_id, depends="none", state="Ready", extra=""):
    path = central / "docs" / "stories" / "F-1" / f"{story_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = "" if depends is None else f"Depends-On: {depends}\n"
    path.write_text(
        f"# {story_id} t\nFeature: F-1\n{line}Track: light\nState: {state}\n{extra}\n## Readiness\nok\n"
    )
    return path


def design_note(central, story_id):
    note = central / "docs" / "design" / "F-1" / f"{story_id}-design.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("note")


def deps(central, *args):
    return subprocess.run(
        [sys.executable, str(CLI), "deps", "--central", str(central), *args],
        capture_output=True,
        text=True,
    )


def test_waits_until_the_dependency_is_done(tmp_path):
    write_story(tmp_path, "S-1", state="In Review")
    path = write_story(tmp_path, "S-2", "S-1")
    design_note(tmp_path, "S-2")
    result = state_check.check(path, "Designed")
    assert not result.ok and "S-1 (In Review)" in result.missing
    write_story(tmp_path, "S-1", state="Done", extra="PR: https://x/1\n")
    assert state_check.check(path, "Designed").ok


@pytest.mark.parametrize("state", ["Design Approved", "In Review", "QA Pass", "Approved", "Done"])
def test_every_later_state_also_waits(tmp_path, state):
    write_story(tmp_path, "S-1", state="Ready")
    path = write_story(tmp_path, "S-2", "S-1")
    assert "depends on S-1" in state_check.check(path, state).missing


def test_a_story_can_be_approved_while_its_dependency_is_open(tmp_path):
    write_story(tmp_path, "S-1", state="Draft")
    path = write_story(tmp_path, "S-2", "S-1", state="Draft")
    assert state_check.check(path, "Ready").ok


def test_backward_states_stay_allowed_while_waiting(tmp_path):
    write_story(tmp_path, "S-1", state="Draft")
    assert state_check.check(write_story(tmp_path, "S-2", "S-1"), "Blocked").ok


def test_the_line_is_required(tmp_path):
    assert "no `Depends-On:` line" in state_check.check(write_story(tmp_path, "S-1", None), "Ready").missing


@pytest.mark.parametrize(
    "value",
    ["<story ids that must be Done first, separated by commas, or none>", "maybe later", "S-1 S-2", ""],
)
def test_a_placeholder_or_free_text_is_refused(tmp_path, value):
    write_story(tmp_path, "S-1")
    assert "must be story ids" in state_check.check(write_story(tmp_path, "S-2", value), "Ready").missing


def test_unknown_story_and_self_reference_are_refused(tmp_path):
    assert "no story S-9" in state_check.check(write_story(tmp_path, "S-2", "S-9"), "Ready").missing
    assert "lists itself" in state_check.check(write_story(tmp_path, "S-3", "S-3"), "Ready").missing


def test_a_loop_is_refused_at_approval(tmp_path):
    write_story(tmp_path, "S-1", "S-3")
    write_story(tmp_path, "S-3", "S-2")
    result = state_check.check(write_story(tmp_path, "S-2", "S-1"), "Ready")
    assert "makes a loop" in result.missing


def test_dependency_in_another_feature_and_slugged_name(tmp_path):
    other = tmp_path / "docs" / "stories" / "backlog" / "S-7-some-slug.md"
    other.parent.mkdir(parents=True)
    other.write_text("# S-7\nDepends-On: none\nState: Done\n")
    path = write_story(tmp_path, "S-2", "S-7, S-7 ")
    design_note(tmp_path, "S-2")
    assert state_check.check(path, "Designed").ok


def test_note_after_the_ids_is_allowed(tmp_path):
    write_story(tmp_path, "S-1")
    assert state_check.parse_depends_on("Depends-On: S-1, S-2 — uses its API\n")[0] == ["S-1", "S-2"]
    assert state_check.parse_depends_on("Depends-On: None\n")[0] == []


def test_deps_command_for_one_story(tmp_path):
    write_story(tmp_path, "S-1", state="QA Pass")
    write_story(tmp_path, "S-2", "S-1")
    done = deps(tmp_path, "S-2")
    assert done.returncode == 2 and "S-1 (QA Pass)" in done.stderr
    write_story(tmp_path, "S-1", state="Done", extra="PR: https://x/1\n")
    done = deps(tmp_path, "S-2")
    assert done.returncode == 0 and "https://x/1" in done.stdout
    assert deps(tmp_path, "S-404").returncode == 2


def test_deps_command_lists_dependencies_first(tmp_path):
    write_story(tmp_path, "S-1", "S-2")
    write_story(tmp_path, "S-2", "S-3")
    write_story(tmp_path, "S-3")
    write_story(tmp_path, "S-4", state="Done", extra="PR: https://x/4\n")
    rows = json.loads(deps(tmp_path, "--json").stdout)
    assert [row["story"] for row in rows] == ["S-3", "S-2", "S-1"]
    assert rows[0]["waitingOn"] == [] and rows[1]["waitingOn"] == ["S-3"]


def test_deps_command_reports_a_broken_list(tmp_path):
    write_story(tmp_path, "S-1", "S-2")
    write_story(tmp_path, "S-2", "S-1")
    done = deps(tmp_path)
    assert done.returncode == 2 and "makes a loop" in done.stderr


def hook(central, tool_input):
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    payload = {"tool_name": "Edit", "tool_input": tool_input, "cwd": str(central)}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=central,
    )


def edit(path, old, new):
    return {"file_path": str(path), "old_string": old, "new_string": new}


def test_hook_refuses_the_state_while_waiting(tmp_path):
    write_story(tmp_path, "S-1")
    path = write_story(tmp_path, "S-2", "S-1")
    design_note(tmp_path, "S-2")
    done = hook(tmp_path, edit(path, "State: Ready", "State: Designed"))
    assert done.returncode == 2 and "depends on S-1" in done.stderr


def test_hook_refuses_dropping_a_dependency_after_approval(tmp_path):
    write_story(tmp_path, "S-1")
    path = write_story(tmp_path, "S-2", "S-1")
    done = hook(tmp_path, edit(path, "Depends-On: S-1", "Depends-On: none"))
    assert done.returncode == 2 and "removes S-1" in done.stderr
    assert hook(tmp_path, edit(path, "Depends-On: S-1", "Depends-On: S-1, S-3")).returncode == 0


def test_hook_allows_changing_dependencies_before_approval(tmp_path):
    write_story(tmp_path, "S-1")
    path = write_story(tmp_path, "S-2", "S-1", state="Draft")
    assert hook(tmp_path, edit(path, "Depends-On: S-1", "Depends-On: none")).returncode == 0


@pytest.mark.parametrize(
    "old,new",
    [
        ("Draft", "Ready"),
        ("Draft", "Done"),
        ("Ready", "In Review"),
        ("Designed", "In Review"),
        ("In Review", "Approved"),
        ("QA Fail", "Approved"),
        ("QA Pass", "Done"),
        ("Approved", "Done"),
        ("Done", "Ready"),
    ],
)
def test_a_step_cannot_be_skipped(old, new):
    assert "cannot move" in state_check.order_problem(old, new, "Track: full\n")


@pytest.mark.parametrize(
    "old,new",
    [
        ("Draft", "Ready for PO"),
        ("Needs Clarification", "Ready for PO"),
        ("Ready for PO", "Ready"),
        ("Ready", "Designed"),
        ("Designed", "Design Approved"),
        ("Design Changes Requested", "Designed"),
        ("Design Approved", "In Review"),
        ("In Review", "QA Pass"),
        ("In Review", "QA Fail"),
        ("QA Fail", "In Review"),
        ("QA Pass", "Approved"),
        ("Approved", "Documented"),
        ("Documented", "Done"),
        ("Done", "Blocked"),
        ("QA Pass", "Blocked"),
        ("Designed", "Design Changes Requested"),
        ("Ready", "Ready"),
    ],
)
def test_the_normal_moves_are_allowed(old, new):
    assert state_check.order_problem(old, new, "Track: full\n") is None


def test_only_a_spike_goes_from_design_approved_to_documented():
    assert state_check.order_problem("Design Approved", "Documented", "Track: spike\n") is None
    assert "cannot move" in state_check.order_problem("Design Approved", "Documented", "Track: full\n")


def test_blocked_cannot_be_a_shortcut_to_in_review():
    assert "approved" in state_check.order_problem("Blocked", "In Review", "Track: full\n")
    approved = "## Design review\nApproved\n"
    assert state_check.order_problem("Blocked", "In Review", approved) is None
    assert "cannot move" in state_check.order_problem("Blocked", "Done", approved)


def test_an_unknown_current_state_needs_a_human():
    assert "a human must correct it" in state_check.order_problem("Aproved", "Done", "")


def test_hook_refuses_a_skip_even_when_the_files_exist(tmp_path):
    path = write_story(tmp_path, "S-1", state="Draft", extra="PR: https://x/1\n")
    done = hook(tmp_path, edit(path, "State: Draft", "State: Done"))
    assert done.returncode == 2 and "cannot move" in done.stderr


def test_cli_refuses_a_skip(tmp_path):
    path = write_story(tmp_path, "S-1", state="Draft", extra="PR: https://x/1\n")
    done = subprocess.run(
        [sys.executable, str(CLI), "state-check", "--central", str(tmp_path), str(path), "Done"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2 and "cannot move" in done.stderr
