"""baton build: the order of one story's steps, with the agents replaced by their recorded outputs."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from baton.cli import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "sample-central-repo"
QA = "docs/qa/F-100"
LEDGER = (
    "| Class | Pattern | Force | Alternative | Verification |\n| --- | --- | --- | --- | --- |\n"
    "| TotalService | plain class | AC1 | none | TotalServiceTest#ac1 |\n"
)


@pytest.fixture
def central(tmp_path):
    target = tmp_path / "c"
    shutil.copytree(FIXTURE, target)
    return target


def build(central, capsys, *args):
    code = main(["build", "FIX-1", "--central", str(central), "--json", *args])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


def story(central):
    return central / "docs" / "stories" / "F-100" / "FIX-1.md"


def edit(central, old, new):
    path = story(central)
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


def set_state(central, state, append=""):
    path = story(central)
    text = re.sub(r"^State:.*$", f"State: {state}", path.read_text(), count=1, flags=re.M)
    path.write_text(text.rstrip("\n") + "\n" + append)


# --- recorded agent outputs ---------------------------------------------------------------------------------
def architect(central, score=85, ledger=""):
    design = central / "docs" / "design" / "F-100" / "FIX-1-design.md"
    design.write_text(
        f"# Design (light): FIX-1\n\n## 4a. Pattern ledger\n{ledger}\n## 5. Confidence\nScore: {score}%\n"
    )
    set_state(central, "Designed")


def developer(central, footer=""):
    sensors = central / QA / "FIX-1-sensors"
    shutil.copytree(central / QA / "S-112-sensors", sensors, dirs_exist_ok=True)
    summary = (
        "\n## Dev summary\n- total endpoint\nSensor loops: 0\n\n## Rule ledger\n- task 1: none applied\n"
    )
    set_state(central, "In Review", summary + footer)


def checks(central):
    (central / QA / "FIX-1-diff-shape.json").write_text('{"story": "FIX-1", "sensorLoops": 0, "repos": []}\n')
    (central / QA / "FIX-1-risk.json").write_text('{"story": "FIX-1", "tier": "low", "lenses": []}\n')


def qa(central, verdict="PASS"):
    report = (central / QA / "S-112-test-report.md").read_text().replace("S-112", "FIX-1")
    (central / QA / "FIX-1-test-report.md").write_text(
        report.replace("## Verdict: PASS", f"## Verdict: {verdict}")
    )
    (central / QA / "FIX-1-triage.md").write_text("# Triage: FIX-1\n- R1 HIGH: total ignores credit lines\n")
    set_state(central, "QA Pass" if verdict == "PASS" else "QA Fail")


def security(central, heads=""):
    text = (central / QA / "S-112-security-report.md").read_text().replace("S-112", "FIX-1")
    if heads:
        text = text.replace("Commit: abc1234\n", f"Commit: abc1234\nHeads: {heads}\n")
    (central / QA / "FIX-1-security-report.md").write_text(text)


def test_a_light_story_runs_from_ready_to_the_stop_before_gate_3(central, capsys):
    code, act = build(central, capsys)
    assert (code, act["kind"], act["agent"]) == (0, "agent", "architect")
    architect(central, score=85)
    code, act = build(central, capsys, "--done", "architect")
    assert act["agent"] == "developer" and "gate 2: auto-passed (light track, confidence 85%)" in act["log"]
    assert (
        "auto-passed" in story(central).read_text() and "State: Design Approved" in story(central).read_text()
    )
    developer(central)
    code, act = build(central, capsys, "--done", "developer")
    assert (act["kind"], act["step"]) == ("do", "checks")
    assert build(central, capsys, "--done", "checks")[1]["step"] == "checks"  # refused: nothing written yet
    checks(central)
    code, act = build(central, capsys, "--done", "checks")
    assert act["agent"] == "qa"
    qa(central)
    code, act = build(central, capsys, "--done", "qa")
    assert act["agent"] == "security" and "first run" in act["text"]
    security(central)
    code, act = build(central, capsys, "--done", "security")
    assert (code, act["kind"]) == (0, "done"), act
    assert (central / QA / "FIX-1-confidence.json").is_file() and (
        central / QA / "FIX-1-evidence.md"
    ).is_file()
    steps = [s["step"] for s in json.loads((central / QA / "FIX-1-build.json").read_text())["steps"]]
    assert steps == ["deps", "architect", "gate2", "developer", "checks", "qa", "security", "confidence"]
    assert build(central, capsys)[1]["kind"] == "done"  # idempotent: nothing to redo


def test_gate_2_pauses_for_a_full_story_and_loops_on_changes(central, capsys):
    edit(central, "Track: light", "Track: full")
    build(central, capsys)
    architect(
        central,
        score=70,
        ledger=LEDGER,
    )
    code, act = build(central, capsys, "--done", "architect")
    assert (code, act["kind"], act["options"][1]) == (0, "gate", "changes (Recommended)")
    code, act = build(central, capsys, "--answer", "changes", "--by", "TL", "--note", "split the reader")
    assert act["agent"] == "architect" and "State: Design Changes Requested" in story(central).read_text()
    architect(
        central,
        score=88,
        ledger=LEDGER,
    )
    code, act = build(central, capsys, "--done", "architect")
    assert act["options"][0] == "approve (Recommended)"
    code, act = build(central, capsys, "--answer", "approve", "--by", "TL")
    assert act["agent"] == "developer" and "TL: Approved, confidence 88%" in story(central).read_text()


def test_a_prose_verification_in_the_pattern_ledger_sends_the_design_back(central, capsys):
    edit(central, "Track: light", "Track: full")
    build(central, capsys)
    architect(
        central,
        score=90,
        ledger="| Class | Pattern | Force | Alternative | Verification |\n"
        "| --- | --- | --- | --- | --- |\n| TotalService | plain class | AC1 | none | reviewed by hand |\n",
    )
    code, act = build(central, capsys, "--done", "architect")
    assert act["agent"] == "architect"
    assert "names no test or ArchUnit rule" in story(central).read_text()


def test_gate_0_pauses_and_a_tech_lead_override_is_recorded(central, capsys):
    (central / "profile" / "branch-points.yaml").write_text("points: []\n")
    code, act = build(central, capsys)
    assert (code, act["kind"], act["step"]) == (0, "skill", "gate0") and "focus F-100" in act["text"]
    edit(
        central,
        "State: Ready",
        "Gate-0-Override: hotfix, area reviewed by hand (TL, 2026-11-15)\nState: Ready",
    )
    code, act = build(central, capsys)
    assert act["agent"] == "architect" and any("overridden by the Tech Lead" in line for line in act["log"])
    gate = json.loads((central / QA / "FIX-1-build.json").read_text())["steps"][0]
    assert gate["step"] == "gate0" and gate["by"] == "TL" and gate["override"].startswith("hotfix")


def test_the_fix_loop_reads_triage_only(central, capsys):
    build(central, capsys)
    architect(central)
    build(central, capsys, "--done", "architect")
    developer(central)
    build(central, capsys, "--done", "developer")
    checks(central)
    build(central, capsys, "--done", "checks")
    qa(central, verdict="FAIL")
    code, act = build(central, capsys, "--done", "qa")
    assert act["agent"] == "developer" and act["inputs"][-1] == f"{QA}/FIX-1-triage.md"
    assert not any("lens" in path for path in act["inputs"])
    developer(central, footer="<!-- baton:provenance\nagent: developer\ncontext: FIX-1-lens-craft.md\n-->\n")
    code, act = build(central, capsys, "--done", "developer")
    assert code == 2 and "only review input" in act["text"]


def _git(repo, *args):
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    )


def test_a_commit_after_security_runs_security_again_and_refuses_approved(central, capsys):
    svc = central.parent / "invoice-service"
    _git(central.parent, "init", "-q", "-b", "main", str(svc))
    (svc / "a.txt").write_text("1\n")
    _git(svc, "add", "-A")
    _git(svc, "commit", "-qm", "seed")
    _git(svc, "checkout", "-qb", "feature/F-100-FIX-1")
    (svc / "a.txt").write_text("2\n")
    _git(svc, "commit", "-qam", "FIX-1: total")
    head = _git(svc, "rev-parse", "--short", "HEAD").stdout.strip()
    build(central, capsys)
    architect(central)
    build(central, capsys, "--done", "architect")
    developer(central)
    build(central, capsys, "--done", "developer")
    checks(central)
    build(central, capsys, "--done", "checks")
    qa(central)
    build(central, capsys, "--done", "qa")
    security(central, heads=f"invoice-service@{head}")
    code, act = build(central, capsys, "--done", "security")
    assert act["kind"] == "done", act
    (svc / "a.txt").write_text("3\n")  # a fix after the security review
    _git(svc, "commit", "-qam", "FIX-1: late fix")
    code, act = build(central, capsys)
    assert act["agent"] == "security" and "is stale" in act["text"]
    assert main(["build", "FIX-1", "--central", str(central), "--security-check"]) == 2
    from baton import state_check

    path = story(central)
    text = path.read_text() + "\n## Human findings\n- none\n"
    result = state_check.check(path, "Approved", story_text=text, central=central)
    assert not result.ok and "is stale: invoice-service" in result.missing
