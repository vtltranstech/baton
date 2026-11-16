"""state-check per contracts/states.md: one test per row, both sides; run through the CLI where it matters."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from baton import state_check

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "tools" / "baton" / "cli.py"
BASE = "# S-1 t\nFeature: F-1\nDepends-On: none\nTrack: {track}\nState: Draft\n"


@pytest.fixture
def story(tmp_path):
    central = tmp_path / "c"
    path = central / "docs" / "stories" / "F-1" / "S-1-some-slug.md"
    path.parent.mkdir(parents=True)
    path.write_text(BASE.format(track="light"))
    return path


def qa(path, name, text=""):
    target = path.parents[3] / "docs" / "qa" / "F-1" / f"S-1-{name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return target


def outcome(path, state, text=None):
    return state_check.check(path, state, story_text=text)


GREEN = "Tests run: 5, Failures: 0, Errors: 0, Skipped: 0\n"


@pytest.mark.parametrize(
    "state",
    [
        "Blocked",
        "Needs Clarification",
        "Design Changes Requested",
        "Draft",
        "Blocked — awaiting Q1",
        "blocked",
    ],
)
def test_backward_states_always_allowed(story, state):
    assert outcome(story, state).ok


@pytest.mark.parametrize("state", ["Ready for PO", "Ready"])
def test_readiness(story, state):
    assert "Readiness" in outcome(story, state).missing
    story.write_text(story.read_text() + "## Readiness\nscore 1.0\n")
    assert outcome(story, state).ok


def test_readiness_mentioned_in_prose_is_not_the_section(story):
    story.write_text(story.read_text() + "See ## Readiness in the other story\n")
    assert not outcome(story, "Ready").ok


def test_designed_light_full_spike(story):
    central = story.parents[3]
    design = central / "docs" / "design" / "F-1"
    assert not outcome(story, "Designed").ok
    design.mkdir(parents=True)
    (design / "S-1-design.md").write_text("x")
    assert outcome(story, "Designed").ok
    full = BASE.format(track="full (escalated: new field)")
    result = outcome(story, "Designed", full)
    assert not result.ok and "S-1.dsl" in result.missing
    (design / "S-1.dsl").write_text("x")
    assert outcome(story, "Designed", full).ok
    spike = BASE.format(track="spike")
    assert "findings" in outcome(story, "Designed", spike).missing
    (design / "S-1-findings.md").write_text("x")
    assert outcome(story, "Designed", spike).ok


def test_no_track_is_treated_as_full(story):
    (story.parents[3] / "docs" / "design" / "F-1").mkdir(parents=True)
    (story.parents[3] / "docs" / "design" / "F-1" / "S-1-design.md").write_text("x")
    assert "dsl" in outcome(story, "Designed", "Depends-On: none\nState: Draft\n").missing


@pytest.mark.parametrize(
    "body,ok",
    [
        ("## Design review\nApproved by the TL\n", True),
        ("## Design review\nauto-passed (hotfix), confidence 90%\n", True),
        ("## Design review\nChanges requested\n", False),
        ("## Design review\nNot Approved\n", False),
        ("## Design review\nnot Approved yet\n", False),
        ("## Other\nApproved\n", False),
        ("Approved\n## Design review\nblocked\n## Next\nApproved\n", False),
        ("", False),
    ],
)
def test_design_approved(story, body, ok):
    assert outcome(story, "Design Approved", BASE.format(track="light") + body).ok is ok


REVIEW_READY = BASE.format(track="light") + "## Dev summary\nx\n## Rule ledger\nx\n"


@pytest.mark.parametrize(
    "archunit,ok",
    [
        (None, False),
        ("", False),
        ("BUILD SUCCESS\n", False),
        (GREEN, True),
        ("Tests run: 5, Failures: 1, Errors: 0\n", False),
        ("Tests run: 5, Failures: 0, Errors: 2\n", False),
        (GREEN + "Tests run: 3, Failures: 1, Errors: 0\n", False),
        ("Tests run: 0, Failures: 0, Errors: 0\n", False),
    ],
)
def test_in_review_archunit(story, archunit, ok):
    qa(story, "sensors/pmd.xml", "<pmd/>")
    if archunit is not None:
        qa(story, "sensors/archunit.txt", archunit)
    assert outcome(story, "In Review", REVIEW_READY).ok is ok


@pytest.mark.parametrize("sensor", ["pmd.xml", "checkstyle.xml", "eslint.json"])
def test_in_review_needs_one_other_sensor(story, sensor):
    qa(story, "sensors/archunit.txt", GREEN)
    assert "pmd.xml" in outcome(story, "In Review", REVIEW_READY).missing
    qa(story, f"sensors/{sensor}", "x")
    assert outcome(story, "In Review", REVIEW_READY).ok


@pytest.mark.parametrize("heading", ["Dev summary", "Rule ledger"])
def test_in_review_needs_story_sections(story, heading):
    qa(story, "sensors/archunit.txt", GREEN)
    qa(story, "sensors/pmd.xml", "x")
    text = REVIEW_READY.replace(f"## {heading}\n", "")
    assert heading in outcome(story, "In Review", text).missing


@pytest.mark.parametrize(
    "report,ok",
    [
        (None, False),
        ("## Verdict: FAIL\n", False),
        ("## Verdict: PASS | FAIL\n", False),  # the unfilled template
        ("Verdict: PASS\n", False),
        ("## Verdict: PASS\n", True),
    ],
)
def test_qa_pass(story, report, ok):
    if report is not None:
        qa(story, "test-report.md", report)
    assert outcome(story, "QA Pass").ok is ok


def test_qa_fail_needs_a_report(story):
    assert not outcome(story, "QA Fail").ok
    qa(story, "test-report.md", "## Verdict: FAIL\n")
    assert outcome(story, "QA Fail").ok


def approved_setup(story, human="none\n", security="## Verdict: CLEAR\n", confidence=True):
    qa(story, "test-report.md", f"## Verdict: PASS\n\n## Human findings\n{human}")
    if security is not None:
        qa(story, "security-report.md", security)
    if confidence:
        qa(story, "confidence.json", "{}")


def test_approved_all_present(story):
    approved_setup(story)
    assert outcome(story, "Approved").ok


def test_approved_needs_qa_pass(story):
    qa(story, "test-report.md", "## Verdict: FAIL\n\n## Human findings\nnone\n")
    qa(story, "security-report.md", "## Verdict: CLEAR\n")
    qa(story, "confidence.json", "{}")
    assert "Verdict: PASS" in outcome(story, "Approved").missing


def test_approved_security_missing(story):
    approved_setup(story, security=None)
    assert "security-report" in outcome(story, "Approved").missing


@pytest.mark.parametrize("text", ["## Verdict: BLOCKED\n", "Verdict: BLOCKED", "verdict: blocked"])
def test_approved_security_blocked(story, text):
    approved_setup(story, security=text)
    assert "BLOCKED" in outcome(story, "Approved").missing


def test_approved_confidence_missing(story):
    approved_setup(story, confidence=False)
    assert "confidence.json" in outcome(story, "Approved").missing


@pytest.mark.parametrize(
    "human",
    ["", "\n\n", '(Senior Engineer, gate 3 — findings or "none")\n', "- \n", "TBD\n", "<!-- later -->\n"],
)
def test_approved_human_findings_placeholder(story, human):
    approved_setup(story, human=human)
    assert "Human findings" in outcome(story, "Approved").missing


@pytest.mark.parametrize("human", ["none\n", "- D3 looks wrong at A.java:12\n"])
def test_approved_human_findings_real(story, human):
    approved_setup(story, human=human)
    assert outcome(story, "Approved").ok


def test_documented_light_and_full(story):
    central = story.parents[3]
    assert "change-note" in outcome(story, "Documented").missing
    note = central / "docs" / "changes" / "F-1" / "S-1-change-note.md"
    note.parent.mkdir(parents=True)
    note.write_text("x")
    assert outcome(story, "Documented").ok
    full = BASE.format(track="full")
    assert "workspace.dsl" in outcome(story, "Documented", full).missing
    workspace = central / "docs" / "architecture" / "workspace.dsl"
    workspace.parent.mkdir(parents=True)
    workspace.write_text("x")
    design = central / "docs" / "design" / "F-1" / "S-1-design.md"
    design.parent.mkdir(parents=True)
    design.write_text("x")
    os.utime(workspace, (1000, 1000))
    os.utime(design, (2000, 2000))
    assert "older" in outcome(story, "Documented", full).missing
    os.utime(workspace, (2000, 2000))
    assert outcome(story, "Documented", full).ok


@pytest.mark.parametrize(
    "line,ok",
    [
        ("PR: https://example.invalid/pr/1\n", True),
        ("PR: none\n", False),
        ("PR:\n", False),
        ("see https://example.invalid\n", False),
        ("", False),
    ],
)
def test_done(story, line, ok):
    assert outcome(story, "Done", BASE.format(track="light") + line).ok is ok


@pytest.mark.parametrize("state", ["Aproved", "Finished", "", "Readyish"])
def test_unknown_state_refused(story, state):
    assert not outcome(story, state).ok


def test_backlog_story_uses_backlog_as_feature(tmp_path):
    path = tmp_path / "docs" / "stories" / "backlog" / "S-9.md"
    path.parent.mkdir(parents=True)
    path.write_text("Depends-On: none\nState: Draft\n")
    result = state_check.check(path, "QA Pass")
    assert "docs/qa/backlog/S-9-test-report.md" in result.missing


def test_outside_docs_stories_refused(tmp_path):
    (tmp_path / "x.md").write_text("State: Draft\n")
    assert not state_check.check(tmp_path / "x.md", "Done").ok


@pytest.mark.parametrize(
    "text,expected",
    [
        ("State: In Review\n", "In Review"),
        ("state: approved\n", "Approved"),
        ("STATE:  Ready for PO\n", "Ready for PO"),
        ("**State:** Done\n", "Done"),
        ("State: Blocked — needs refinement session\n", "Blocked"),
        ("State: Ready\n", "Ready"),
        ("no line\n", None),
    ],
)
def test_parse_state(text, expected):
    assert state_check.parse_state(text).state == expected


def test_parse_state_conflict():
    assert state_check.parse_state("State: Draft\nState: Done\n").conflict


def cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(CLI), "state-check", *args], capture_output=True, text=True, cwd=cwd
    )


def test_cli_exit_codes_and_message(story):
    story.write_text(story.read_text().replace("State: Draft", "State: In Review"))
    done = cli(str(story), "QA Pass")
    assert done.returncode == 2
    assert "test-report.md" in done.stderr
    story.write_text(story.read_text().replace("State: In Review", "State: Draft"))
    story.write_text(story.read_text() + "## Readiness\nx\n")
    assert cli(str(story), "Ready for PO").returncode == 0


def test_cli_central_relative_and_json(story):
    central = story.parents[3]
    story.write_text(story.read_text().replace("State: Draft", "State: Documented"))
    done = cli("--central", str(central), "--json", "docs/stories/F-1/S-1-some-slug.md", "Done")
    assert done.returncode == 2
    assert json.loads(done.stdout) == {
        "ok": False,
        "state": "Done",
        "missing": "the story has no `PR:` line with a URL",
    }


def test_help_first_line_is_accurate():
    done = subprocess.run([sys.executable, str(CLI), "state-check", "--help"], capture_output=True, text=True)
    assert done.returncode == 0 and "story_file" in done.stdout


def test_an_archived_story_is_still_found(tmp_path):
    """Depends-On a story of an archived feature (contracts/versioning.md section 5) still resolves."""
    from baton.state_check import find_story

    path = tmp_path / "docs" / "archive" / "F-002" / "stories" / "S-010.md"
    path.parent.mkdir(parents=True)
    path.write_text("# S-010 Done thing\nState: Done\n")
    story = find_story(tmp_path, "S-010")
    assert (story.feature, story.story_id, story.path) == ("F-002", "S-010", path)
