"""The fixture central repo: every state holds, every planted violation is refused, FIX-1 walks to Done.

This is the deterministic part of /build. Each state change goes through the real state-gate hook, as the
Edit call an agent would make; it first asserts the refusal without the artefact, then the pass with it.
No model runs here, and the interactive WAITs at the gates are not exercised.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from baton import state_check

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-central-repo"
CLI = ROOT / "tools" / "baton" / "cli.py"
STATES = {
    "S-101": "Draft",
    "S-102": "Needs Clarification",
    "S-103": "Ready for PO",
    "S-104": "Ready",
    "S-105": "Designed",
    "S-106": "Design Approved",
    "S-107": "Design Changes Requested",
    "S-108": "Blocked",
    "S-109": "In Review",
    "S-110": "QA Pass",
    "S-111": "QA Fail",
    "S-112": "Approved",
    "S-113": "Documented",
    "S-114": "Done",
}


def baton(central, *args):
    return subprocess.run(
        [sys.executable, str(CLI), args[0], "--central", str(central), *args[1:]],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("story_id,state", STATES.items())
def test_one_story_per_state_and_it_holds(central_copy, story_id, state):
    path = central_copy / "docs" / "stories" / "F-100" / f"{story_id}.md"
    assert state_check.parse_state(path.read_text()).state == state
    assert baton(central_copy, "state-check", str(path), state).returncode == 0


def test_every_state_in_the_contract_has_a_story():
    assert set(STATES.values()) == set(state_check.STATES)


VIOLATIONS = json.loads((FIXTURE / "planted" / "violations.json").read_text())


@pytest.mark.parametrize("item", VIOLATIONS, ids=[v["id"] for v in VIOLATIONS])
def test_planted_violation_is_blocked_with_a_clear_message(
    central_copy, tmp_path, run_hook, repo_factory, item
):
    subprocess.run(["git", "init", "-q", "-b", "feature/F-100-S-199", str(central_copy)], check=True)
    main_repo = repo_factory(tmp_path / "svc-on-main")
    text = json.dumps(item["input"]).replace("$MAIN_REPO", str(main_repo))
    tool_input = json.loads(text)
    if "file_path" in tool_input:
        tool_input["file_path"] = str(central_copy / tool_input["file_path"])
    cwd = main_repo if item["cwd"] == "$MAIN_REPO" else central_copy
    done = run_hook(item["hook"], item["tool"], tool_input, cwd, project=central_copy)
    assert done.returncode == 2, item["id"]
    assert item["expect"] in done.stderr, done.stderr


def test_planted_story_really_has_no_archunit():
    assert not (FIXTURE / "docs" / "qa" / "F-100" / "S-199-sensors" / "archunit.txt").exists()


class Walk:
    def __init__(self, central, run_hook):
        self.central, self.run_hook = central, run_hook
        self.story = central / "docs" / "stories" / "F-100" / "FIX-1.md"
        self.walk = central / "walk" / "FIX-1"
        self.qa = central / "docs" / "qa" / "F-100"

    def move(self, new, extra=""):
        """The Edit an agent makes; applied only when the hook lets it through."""
        text = self.story.read_text()
        old = state_check.parse_state(text).state
        payload = {
            "file_path": str(self.story),
            "old_string": f"State: {old}\n",
            "new_string": f"State: {new}\n{extra}",
        }
        done = self.run_hook("state_gate", "Edit", payload, self.central, project=self.central)
        if done.returncode == 0:
            self.story.write_text(text.replace(payload["old_string"], payload["new_string"], 1))
        return done

    def refused_then_allowed(self, new, produce, needle):
        before = self.move(new)
        assert before.returncode == 2 and needle in before.stderr, before.stderr
        produce()
        after = self.move(new)
        assert after.returncode == 0, after.stderr

    def put(self, name, target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.walk / name, target)

    def append(self, text):
        with self.story.open("a") as handle:
            handle.write(text)


def test_fix_1_walks_every_state_to_done(central_copy, run_hook, validate):
    walk = Walk(central_copy, run_hook)
    qa = walk.qa
    design_dir = central_copy / "docs" / "design" / "F-100"

    # architect
    walk.refused_then_allowed(
        "Designed", lambda: walk.put("design.md", design_dir / "FIX-1-design.md"), "FIX-1-design.md"
    )
    # gate 2: auto-pass recorded by /build
    walk.refused_then_allowed(
        "Design Approved",
        lambda: walk.append("\n## Design review\nauto-passed (light track, confidence 90%)\n"),
        "Design review",
    )
    # developer
    assert "archunit.txt" in walk.move("In Review").stderr
    walk.put("archunit.txt", qa / "FIX-1-sensors" / "archunit.txt")
    assert "pmd.xml" in walk.move("In Review").stderr
    walk.put("pmd.xml", qa / "FIX-1-sensors" / "pmd.xml")
    assert "Dev summary" in walk.move("In Review").stderr
    walk.append("\n## Dev summary\nAdded the total.\n")
    assert "Rule ledger" in walk.move("In Review").stderr
    walk.append("\n## Rule ledger\n- task 1: stack.md layering\n")
    assert walk.move("In Review").returncode == 0
    # /build step 3
    for name in ("diff-shape.json", "diff-shape.md", "impact.json", "mutation.json"):
        walk.put(name, qa / f"FIX-1-{name}")
    # qa and security
    walk.refused_then_allowed(
        "QA Pass",
        lambda: [walk.put(n, qa / f"FIX-1-{n}") for n in ("test-report.md", "triage.md")],
        "FIX-1-test-report.md",
    )
    walk.put("security-report.md", qa / "FIX-1-security-report.md")
    # gate 3 needs confidence.json and human findings
    assert "confidence.json" in walk.move("Approved").stderr

    # /build step 6a
    done = baton(central_copy, "confidence", "FIX-1", "--json")
    assert done.returncode == 0, done.stderr
    document = json.loads(done.stdout)
    validate(document, "confidence.json")
    assert document["story"] == "FIX-1" and document["missing"] == []
    # design auto-pass 8 of 10, sensors one loop 6 of 10, everything else full
    assert document["raw"] == 94 and document["score"] == 94 and document["lane"] == "fast"
    assert baton(central_copy, "evidence", "FIX-1").returncode == 0
    assert (qa / "FIX-1-evidence.md").is_file()

    assert "Human findings" in walk.move("Approved").stderr
    report = qa / "FIX-1-test-report.md"
    report.write_text(report.read_text().split("## Human findings")[0] + "## Human findings\nnone\n")
    assert walk.move("Approved").returncode == 0

    # documentation and release
    change = central_copy / "docs" / "changes" / "F-100" / "FIX-1-change-note.md"
    walk.refused_then_allowed("Documented", lambda: walk.put("change-note.md", change), "change-note")
    walk.refused_then_allowed("Done", lambda: walk.append("\nPR: https://example.invalid/pr/1\n"), "PR:")
    assert state_check.parse_state(walk.story.read_text()).state == "Done"


def test_full_track_documented_needs_the_promoted_workspace(central_copy):
    story = central_copy / "docs" / "stories" / "F-100" / "S-113.md"
    text = story.read_text().replace("Track: light", "Track: full")
    design = central_copy / "docs" / "design" / "F-100" / "S-113-design.md"
    workspace = central_copy / "docs" / "architecture" / "workspace.dsl"
    os.utime(workspace, (1000, 1000))
    os.utime(design, (2000, 2000))
    result = state_check.check(story, "Documented", story_text=text)
    assert not result.ok and "older" in result.missing


def project_words():
    """One shared list, so core tests never need to spell a project word."""
    words = ROOT / "tools/baton/tests/project_words.py"
    spec = importlib.util.spec_from_file_location("project_words", words)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.PROJECT_WORDS is None:
        pytest.skip("no project word list (tools/baton/tests/project-words.local.txt or BATON_PROJECT_WORDS)")
    return module.PROJECT_WORDS


@pytest.mark.parametrize("folder", ["fixtures/sample-central-repo", "templates", "hooks", "docs", ".claude-plugin"])  # noqa: E501
def test_no_project_words(folder):
    words = project_words()
    for path in (ROOT / folder).rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store":
            assert not words.search(path.read_text()), path
