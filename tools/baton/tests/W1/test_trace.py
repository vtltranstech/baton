"""baton trace: parsers, the fixture feature F-FIX, the schema, the golden trace.json and the page."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from baton.cli import main
from baton.trace.cmd import render, schema_problems
from baton.trace.collect import Collector, clarifications, provenance, provenance_blocks

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-central-repo"
SCHEMA = json.loads((ROOT / "schemas" / "trace.json").read_text())
GOLDEN = Path(__file__).with_name("data") / "trace-F-FIX.json"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@pytest.fixture
def central(tmp_path):
    target = tmp_path / "central"
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture
def trace(central):
    return Collector(central, "F-FIX").collect()


def story(trace, story_id):
    return next(s for s in trace["stories"] if s["id"] == story_id)


# ---------- provenance footer ----------

FOOTER = """text
<!-- baton:provenance
agent: architect
skills: design-diagram, standards
profile: domain.md#rules-touched(R3,R7), project.md#repos
graph: impact.json (2 repos, 0 unknown edges)
started: 2026-11-04T09:12:00Z  finished: 2026-11-04T09:31:00Z
tokens: 41,200
reviewer: someone
-->
<!-- baton:provenance
agent: developer
skills: standards
-->
"""


def test_footer_keys_lists_and_two_keys_on_one_line():
    block = provenance(FOOTER, "architect")
    assert block["skills"] == ["design-diagram", "standards"]
    assert block["profile"] == ["domain.md#rules-touched(R3,R7)", "project.md#repos"]
    assert block["graph"] == "impact.json (2 repos, 0 unknown edges)"
    assert block["started"] == "2026-11-04T09:12:00Z" and block["finished"] == "2026-11-04T09:31:00Z"
    assert block["tokens"] == 41200
    assert block["more"] == {"reviewer": "someone"}


def test_footer_picks_the_named_agent_else_the_last():
    assert len(provenance_blocks(FOOTER)) == 2
    assert provenance(FOOTER, "developer")["agent"] == "developer"
    assert provenance(FOOTER, "qa")["agent"] == "developer"
    assert provenance("no footer here") is None


def test_clarification_marks_a_domain_line():
    text = "## Clarifications\n- 2026-11-02 Q: When? A: After 30 days. -> domain.md: Overdue after 30 days.\n"
    (item,) = clarifications(text)
    assert item["q"] == "When?" and item["a"] == "After 30 days."
    assert item["domainLine"] == "Overdue after 30 days." and item["date"] == "2026-11-02T00:00:00Z"


# ---------- the fixture feature ----------

def test_done_story_has_every_node(trace):
    done = story(trace, "S-151")
    states = {name: node["state"] for name, node in done["nodes"].items()}
    assert states == dict.fromkeys(done["nodes"], "done")
    assert done["nodes"]["gate2"]["data"]["decision"] == "Approved"
    assert done["nodes"]["gate3"]["at"] == "2026-11-05T09:30:00Z"
    assert done["nodes"]["confidence"]["data"]["score"] == 86
    assert done["nodes"]["design"]["provenance"]["agent"] == "architect"
    assert done["nodes"]["design"]["minutes"] == 40
    assert done["nodes"]["design"]["data"]["flowSvg"].startswith("data:image/svg+xml;base64,")
    assert [a["result"] for a in done["acs"]] == ["PASS", "PASS", "PASS"]


def test_failed_story_shows_the_loop_and_missing_mutation(trace):
    failed = story(trace, "S-152")
    assert failed["loops"] == 1
    assert failed["nodes"]["qa"]["state"] == "failed" and failed["nodes"]["qa"]["data"]["verdict"] == "FAIL"
    assert failed["nodes"]["sensors"]["data"]["mutation"] is None
    assert failed["nodes"]["confidence"]["state"] == "not_produced"
    assert failed["state"] == "Designed"
    assert failed["nodes"]["gate2"]["data"]["decision"] == "Changes requested"
    assert failed["nodes"]["gate2"]["data"]["rounds"] == 2
    assert failed["nodes"]["design"]["provenance"] is None


def test_figures_and_knowledge(trace):
    assert trace["figures"] == {
        "storiesDone": 1, "storiesTotal": 2, "gatesPassed": 4, "gatesTotal": 6,
        "leadTimeHours": 82.3, "fixLoops": 1, "confidenceMedian": 86, "lane": "senior",
    }
    knowledge = trace["knowledge"]
    assert [line["story"] for line in knowledge["domainLines"]] == ["S-151"]
    assert knowledge["domainLines"][0]["inDomain"] is True
    assert [rule["name"] for rule in knowledge["rules"]] == ["Overdue queries name billingPeriod"]
    arch = knowledge["architecture"]
    assert (arch["addedElements"], arch["addedRelationships"], arch["changed"]) == (2, 3, 0)
    assert arch["changelog"] == "docs/architecture/CHANGELOG.md"
    assert arch["added"][:2] == ["overdueJob", "notices"] and len(arch["added"]) == 5
    assert arch["before"] == {"elements": 4, "relationships": 2}
    assert arch["after"] == {"elements": 6, "relationships": 5}


def test_trace_matches_the_schema(trace):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(SCHEMA).validate(trace)
    assert schema_problems(trace, SCHEMA) == []


def test_stdlib_schema_check_catches_what_jsonschema_catches(trace):
    jsonschema = pytest.importorskip("jsonschema")
    broken = json.loads(json.dumps(trace))
    broken["stories"][0]["nodes"]["qa"]["state"] = "maybe"
    del broken["figures"]["fixLoops"]
    assert schema_problems(broken, SCHEMA)
    assert list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(broken))


def _normalised(trace: dict) -> dict:
    trace = json.loads(json.dumps(trace))
    trace["generated"] = None
    trace["root"] = "<central>"
    return trace


def test_golden_trace(trace):
    """Regenerate with BATON_UPDATE_GOLDEN=1 after an intended change, and review the diff."""
    actual = _normalised(trace)
    if os.environ.get("BATON_UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(actual, indent=1, ensure_ascii=False) + "\n")
    assert actual == json.loads(GOLDEN.read_text())


def test_architecture_falls_back_to_the_change_note(central):
    (central / "docs" / "architecture" / "CHANGELOG.md").unlink()
    arch = Collector(central, "F-FIX").collect()["knowledge"]["architecture"]
    assert (arch["addedElements"], arch["addedRelationships"]) == (2, 3)
    assert arch["changelog"] is None and "overdueJob -> db" in arch["added"]


def test_an_archived_feature_traces_the_same(central, trace):
    """contracts/versioning.md section 5: /ship moves a finished feature to docs/archive/<F>/."""
    archive = central / "docs" / "archive" / "F-FIX"
    archive.mkdir(parents=True)
    for kind in ("stories", "design", "qa", "changes"):
        shutil.move(central / "docs" / kind / "F-FIX", archive / kind)
    moved = Collector(central, "F-FIX").collect()
    assert moved["figures"] == trace["figures"]
    assert moved["knowledge"] == trace["knowledge"]
    done = story(moved, "S-151")
    assert {n: v["state"] for n, v in done["nodes"].items()} == {
        n: v["state"] for n, v in story(trace, "S-151")["nodes"].items()
    }
    assert done["nodes"]["qa"]["path"] == "docs/archive/F-FIX/qa/S-151-test-report.md"


# ---------- tolerance ----------

def test_missing_artefacts_never_break_the_page(tmp_path):
    central = tmp_path / "bare"
    (central / "docs" / "stories" / "F-300").mkdir(parents=True)
    (central / "docs" / "stories" / "F-300" / "S-301.md").write_text("# S-301 Bare\nState: Draft\n")
    (central / "docs" / "stories" / "F-300" / "S-302.md").write_text("")
    trace = Collector(central, "F-300").collect()
    assert schema_problems(trace, SCHEMA) == []
    states = {n["state"] for s in trace["stories"] for n in s["nodes"].values()}
    assert states <= {"not_produced", "in_progress"}
    assert "undefined" not in json.dumps(trace)


def _dom(page: Path, profile: Path) -> tuple[str, str]:
    done = subprocess.run(
        [str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
         "--virtual-time-budget=3000", "--dump-dom", page.as_uri()],
        capture_output=True, text=True, timeout=60, check=False,
    )
    dom = re.sub(r"(?s)<(script|style).*?</\1>", "", done.stdout)
    return dom, re.sub(r"<[^>]+>", " ", dom)


def test_script_breakout_is_escaped(central):
    path = central / "docs" / "stories" / "F-FIX" / "S-152.md"
    path.write_text(path.read_text().replace("Show the overdue list", "</script><script>alert(1)</script>"))
    page = render(Collector(central, "F-FIX").collect())
    payload = page.split("window.TRACE = ", 1)[1].split(";\n</script>", 1)[0]
    assert "</script>" not in payload and json.loads(payload.replace("<\\/", "</"))


# ---------- the command ----------

def test_command_writes_the_page(central, capsys):
    assert main(["trace", "F-FIX", "--story", "S-152", "--central", str(central)]) == 0
    page = (central / "docs" / "trace" / "F-FIX.html").read_text()
    assert "<title>F-FIX trace</title>" in page and '"selected":"S-152"' in page
    assert "/*__TRACE__*/" not in page
    assert "wrote docs/trace/F-FIX.html" in capsys.readouterr().out


def test_command_refuses_an_unknown_feature_or_story(central, capsys):
    assert main(["trace", "F-999", "--central", str(central)]) == 2
    assert main(["trace", "F-FIX", "--story", "S-101", "--central", str(central)]) == 2


@pytest.mark.skipif(not CHROME.is_file(), reason="Google Chrome is not installed")
def test_page_renders_in_a_browser(central, tmp_path):
    assert main(["trace", "F-FIX", "--story", "S-152", "--central", str(central)]) == 0
    dom, text = _dom(central / "docs" / "trace" / "F-FIX.html", tmp_path / "c")
    assert len(re.findall(r'data-node="', dom)) == 13
    assert "undefined" not in text and "NaN" not in text
    assert "FAIL" in text and "fix loops" in text


@pytest.mark.skipif(not CHROME.is_file(), reason="Google Chrome is not installed")
def test_a_bare_feature_renders_in_a_browser(tmp_path):
    central = tmp_path / "bare"
    (central / "docs" / "stories" / "F-300").mkdir(parents=True)
    (central / "docs" / "stories" / "F-300" / "S-301.md").write_text("# S-301 Bare\nState: Draft\n")
    assert main(["trace", "F-300", "--central", str(central)]) == 0
    dom, text = _dom(central / "docs" / "trace" / "F-300.html", tmp_path / "c")
    assert len(re.findall(r'data-node="', dom)) == 13
    assert "undefined" not in text and "NaN" not in text and "not produced" in text


def _git(repo, *args):
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def test_a_story_on_its_own_branch_is_still_traced(central, trace):
    """S-152's files live only on story/F-FIX-S-152."""
    s152 = [p for p in central.rglob("*S-152*") if p.is_file()]
    _git(central, "init", "-q", "-b", "main")
    _git(central, "add", "-A")
    _git(central, "commit", "-qm", "seed")
    _git(central, "checkout", "-qb", "story/F-FIX-S-152")
    _git(central, "checkout", "-q", "main")
    _git(central, "rm", "-rq", *[str(p.relative_to(central)) for p in s152])
    _git(central, "commit", "-qm", "S-152 lives on its branch")
    assert not (central / "docs" / "stories" / "F-FIX" / "S-152.md").exists()
    moved = Collector(central, "F-FIX").collect()
    branch = story(moved, "S-152")
    assert branch["branch"] == "story/F-FIX-S-152"
    assert {n: v["state"] for n, v in branch["nodes"].items()} == {
        n: v["state"] for n, v in story(trace, "S-152")["nodes"].items()
    }
    assert branch["nodes"]["qa"]["path"] == "docs/qa/F-FIX/S-152-test-report.md"
    assert moved["figures"]["fixLoops"] == trace["figures"]["fixLoops"]

    from baton.state_check import find_story
    from baton.stories import collect

    assert find_story(central, "S-152").ref == "story/F-FIX-S-152"
    assert "State: Designed" in find_story(central, "S-152").text()
    rows = {row["story"]: row for row in collect(central, "F-FIX")}
    assert rows["S-152"]["where"] == "story/F-FIX-S-152" and rows["S-151"]["where"] == "here"
