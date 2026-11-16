"""evidence.md: mechanical checks of the contract's layout, its citations, and the weights never being read."""  # noqa: E501

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parents[4] / "tools" / "baton" / "cli.py"
SECTIONS = [
    "Story",
    "Design",
    "Build",
    "Verification",
    "Security",
    "Blast radius",
    "Confidence",
    "What was NOT done",
    "Links",
]
QA = "docs/qa/F-100"


def run(central, *args):
    return subprocess.run(
        [sys.executable, str(CLI), *args[:1], "--central", str(central), *args[1:]],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def rendered(central_copy):
    assert run(central_copy, "confidence", "S-114").returncode == 0
    assert run(central_copy, "evidence", "S-114").returncode == 0
    return central_copy, (central_copy / QA / "S-114-evidence.md").read_text()


def headings(text):
    return re.findall(r"^## (.*)$", text, re.M)


def data_lines(text):
    """Lines holding a value: everything but headings, table rules, Links and the fixed e2e line."""
    body = text.split("## Links")[0]
    for line in body.splitlines():
        if not line.strip() or line.startswith("#") or set(line) <= set("|- "):
            continue
        if line == "- End-to-end test not executed":
            continue
        if line.startswith("| ") and line.split("|")[-2].strip() in ("Source",):
            continue
        yield line


def test_sections_exact_and_in_order(rendered):
    assert headings(rendered[1]) == SECTIONS


def test_every_value_line_cites_an_existing_file(rendered):
    central, text = rendered
    for line in data_lines(text):
        found = re.findall(r"source: ([^)]+)\)", line) or [line.split("|")[-2].strip()]
        path = found[-1]
        assert path.startswith(("docs/", "profile/")), line
        assert (central / path).exists(), f"{line}: {path} does not exist"


def test_numbers_match_the_artefacts(rendered):
    central, text = rendered
    confidence = json.loads((central / QA / "S-114-confidence.json").read_text())
    assert f"- Score: {confidence['score']} (source: {QA}/S-114-confidence.json)" in text
    assert f"- Lane: {confidence['lane']} (source: {QA}/S-114-confidence.json)" in text
    assert (
        f"| invoice-service | feature/F-100-S-114 | 2 | 120 | 10 | 2 | {QA}/S-114-diff-shape.json |" in text
    )
    assert "- Mutation score: 0.85" in text
    assert "- Triage: HIGH 0, MEDIUM 0, LOW 1" in text
    assert "- Confidence: 90% (source: docs/design/F-100/S-114-design.md)" in text
    assert "- Rounds: 1 (source: docs/stories/F-100/S-114.md)" in text
    assert "| archunit | green | archunit.txt green (7 tests) |" in text
    assert "| AC1 | ac1_totalIsSumOfLines | PASS |" in text
    assert "- Verdict: FINDINGS" in text and "- Finding 1: Verbose error text" in text


def test_lowest_three_signals_are_shown(central_copy):
    (central_copy / QA / "S-114-mutation.json").unlink()
    (central_copy / QA / "S-114-impact.json").unlink()
    assert run(central_copy, "confidence", "S-114").returncode == 0
    assert run(central_copy, "evidence", "S-114").returncode == 0
    text = (central_copy / QA / "S-114-evidence.md").read_text()
    lines = re.findall(r"^- Lowest signal (\w+): ", text, re.M)
    assert len(lines) == 3 and {"blast_radius", "mutation"} <= set(lines)


def test_links_list_every_artefact_that_exists(rendered):
    central, text = rendered
    links = text.split("## Links")[1]
    for path in (central / QA).glob("S-114-*"):
        if path.is_file() and path.name != "S-114-evidence.md":
            assert f"{QA}/{path.name}" in links
    assert f"{QA}/S-114-sensors/archunit.txt" in links
    assert "docs/changes/F-100/S-114-change-note.md" in links
    assert "S-114-evidence.md" not in links


def test_not_done_lists_every_missing_input_and_e2e(central_copy):
    for name in ("mutation.json", "impact.json", "triage.md"):
        (central_copy / QA / f"S-114-{name}").unlink()
    assert run(central_copy, "confidence", "S-114").returncode == 0
    assert run(central_copy, "evidence", "S-114").returncode == 0
    text = (central_copy / QA / "S-114-evidence.md").read_text()
    section = text.split("## What was NOT done")[1].split("## Links")[0]
    missing = json.loads((central_copy / QA / "S-114-confidence.json").read_text())["missing"]
    assert missing
    for name in missing:
        assert f"- Missing input: {name} " in section
    assert "- End-to-end test not executed" in section


def test_without_confidence_json_it_says_so(central_copy):
    (central_copy / QA / "S-110-confidence.json").unlink(missing_ok=True)
    assert run(central_copy, "evidence", "S-110").returncode == 0
    text = (central_copy / QA / "S-110-evidence.md").read_text()
    assert headings(text) == SECTIONS
    assert "- Confidence: not present" in text
    assert "- Missing input: confidence.json" in text


def test_a_bare_story_renders_without_inventing_anything(central_copy):
    assert run(central_copy, "evidence", "S-101").returncode == 0
    text = (central_copy / QA / "S-101-evidence.md").read_text()
    assert headings(text) == SECTIONS
    for phrase in (
        "Test report: not present",
        "Security report: not present",
        "Impact: not present",
        "Mutation score: not present",
        "Triage: not present",
        "Diff shape: not present",
    ):
        assert phrase in text
    for line in data_lines(text):
        assert "source:" in line or line.split("|")[-2].strip().startswith("docs/"), line


def test_evidence_never_reads_the_weights(central_copy):
    assert run(central_copy, "confidence", "S-114").returncode == 0
    (central_copy / "profile" / "confidence-weights.yaml").unlink()
    assert run(central_copy, "evidence", "S-114").returncode == 0


def test_evidence_source_has_no_weights_path():
    source = (CLI.parent / "evidence.py").read_text()
    assert "weights.yaml" not in source.replace("Never reads profile/confidence-weights.yaml", "")


def test_rerun_is_idempotent(rendered):
    central, text = rendered
    assert run(central, "evidence", "S-114").returncode == 0
    assert (central / QA / "S-114-evidence.md").read_text() == text


def test_unknown_story_refused_and_json_form(central_copy):
    assert run(central_copy, "evidence", "S-404").returncode == 2
    done = run(central_copy, "evidence", "S-114", "--json")
    assert json.loads(done.stdout)["sections"] == SECTIONS


def test_help_text_is_the_docstring():
    done = subprocess.run([sys.executable, str(CLI), "--help"], capture_output=True, text=True)
    assert "Compute the gate-3 confidence score" in done.stdout
    assert "Write docs/qa/<F>/<S>-evidence.md" in done.stdout
    assert "Check a story state change" in done.stdout
