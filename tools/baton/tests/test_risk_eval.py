"""baton risk (tier before QA), baton eval (time, tokens and lens yield from local transcripts), and
diff-line mutation scoring."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from baton import evaluate, reads, risk
from baton.cli import main
from baton.mutation import pit

STORY = "# S-1 Title\nTrack: {track}\nEstimate: {estimate}\nLabels: {labels}\nState: In Review\n"
POINT = {"element": "FeeService#accrue", "file": "src/main/java/a/FeeService.java", "lines": "10-20",
         "reachedFrom": [], "repo": "svc", "status": "changed", "tests": []}


class Product:
    def __init__(self, root: Path):
        self.root = root
        (root / "docs/stories/F-1").mkdir(parents=True)
        (root / "docs/design/F-1/S-1-diagrams").mkdir(parents=True)
        (root / "docs/qa/F-1").mkdir(parents=True)
        (root / "profile").mkdir()
        (root / "profile/risk-zones.yaml").write_text(
            'zones:\n  - name: money\n    paths: ["**/payments/**"]\n    cap: 50\n    confirmed: true\n'
        )
        self.story()
        self.design([POINT])
        self.note("none")

    def story(self, track="light", estimate="S", labels="bug"):
        (self.root / "docs/stories/F-1/S-1.md").write_text(
            STORY.format(track=track, estimate=estimate, labels=labels)
        )

    def design(self, points, impacted=()):
        (self.root / "docs/design/F-1/S-1-diagrams/diagrams.json").write_text(
            json.dumps({"story": "S-1", "touchPoints": points, "impacted": list(impacted)})
        )

    def note(self, rules):
        (self.root / "docs/design/F-1/S-1-design.md").write_text(
            f"# Design (light): S-1\n\n## 1. Change\nFix the guard.\nRules touched: {rules}\n\n## 2. Impact\n"
        )

    def diff(self, files, repo="svc", **extra):
        doc = {"story": "S-1", "repos": [{"repo": repo, "files": files}], **extra}
        (self.root / "docs/qa/F-1/S-1-diff-shape.json").write_text(json.dumps(doc))

    def assess(self):
        return risk.assess(self.root, "S-1")


@pytest.fixture
def product(tmp_path):
    return Product(tmp_path)


def test_a_small_single_repo_change_is_low_with_two_lenses(product):
    result = product.assess()
    assert result["tier"] == "low" and result["reasons"] == []
    assert result["lenses"] == ["conformance", "verification-gap"]


def test_a_low_story_that_names_a_rule_keeps_the_domain_lens(product):
    product.note("Accrual uses the period key (domain.md: Invariants)")
    assert product.assess()["lenses"] == ["conformance", "verification-gap", "domain"]


@pytest.mark.parametrize(
    "change,why",
    [
        (lambda p: p.story(track="full"), "full track"),
        (lambda p: p.story(estimate="M"), "estimate M"),
        (lambda p: p.design([POINT, {**POINT, "element": "collection:waivers", "file": "", "repo": ""}]),
         "design adds or changes collection:waivers"),
        (lambda p: p.design([POINT, {**POINT, "repo": "other"}]), "design spans 2 repos"),
        (lambda p: p.diff(["src/main/java/a/FeeService.java"], writesCollections=["audit"]),
         "diff writes collection audit, not in the design"),
    ],
)
def test_medium(product, change, why):
    change(product)
    result = product.assess()
    assert result["tier"] == "medium" and why in [r["why"] for r in result["reasons"]]
    assert len(result["lenses"]) == 5


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.story(labels="bug, data-model"),
        lambda p: p.design([{**POINT, "status": "removed"}]),
        lambda p: p.design([{**POINT, "file": "src/main/java/a/payments/Pay.java"}]),
        lambda p: p.design([POINT], impacted=[{"repo": "reports"}]),
        lambda p: p.diff(["src/main/java/a/payments/Pay.java"]),  # the build went where the design did not
        lambda p: p.diff(["src/main/java/a/FeeService.java"], breakingContract=["GET /x removed"]),
        lambda p: p.diff(["src/main/java/a/FeeService.java"], newDependencies=["g:a:1"]),
    ],
)
def test_high(product, change):
    change(product)
    assert product.assess()["tier"] == "high"


def test_no_design_touch_points_is_not_low(product):
    (product.root / "docs/design/F-1/S-1-diagrams/diagrams.json").unlink()
    assert product.assess()["tier"] == "medium"


def test_cli_writes_risk_json(product, capsys):
    assert main(["risk", "S-1", "--central", str(product.root)]) == 0
    assert "S-1: low risk" in capsys.readouterr().out
    written = json.loads((product.root / "docs/qa/F-1/S-1-risk.json").read_text())
    assert written["tier"] == "low"
    assert main(["risk", "S-9", "--central", str(product.root)]) == 2


# -- eval -------------------------------------------------------------------------------------------------


def transcript(
    folder: Path, agent_id: str, agent_type: str, prompt: str, start: str, end: str, tokens: int
) -> None:
    sub = folder / "sess-1" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    meta = {"agentType": agent_type, "description": "d"}
    (sub / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))
    usage = {"input_tokens": tokens, "cache_read_input_tokens": 0, "output_tokens": 10}
    lines = [
        {"type": "user", "timestamp": start, "message": {"role": "user", "content": prompt}},
        # one API message split into two transcript lines: its usage must count once
        {"type": "assistant", "timestamp": start, "message": {"id": f"m-{agent_id}", "usage": usage,
         "content": [{"type": "tool_use", "name": "Read"}]}},
        {"type": "assistant", "timestamp": end, "message": {"id": f"m-{agent_id}", "usage": usage,
         "content": [{"type": "text", "text": "done"}]}},
    ]
    (sub / f"agent-{agent_id}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


@pytest.fixture
def evaluated(product, tmp_path):
    folder = tmp_path / "transcripts"
    day = "2026-11-05T"
    transcript(folder, "a1", "architect", "Design S-1 now", day + "10:00:00Z", day + "10:10:00Z", 1000)
    transcript(folder, "a2", "developer", "Build S-1", "2026-11-05T10:30:00Z", "2026-11-05T10:50:00Z", 3000)
    transcript(folder, "a3", "general-purpose", "lens on /tmp/review/S-1.diff", "2026-11-05T10:51:00Z",
               "2026-11-05T10:55:00Z", 500)
    transcript(folder, "a4", "general-purpose", "lens on /tmp/review/S-1.diff", "2026-11-05T10:52:00Z",
               "2026-11-05T10:56:00Z", 500)
    transcript(folder, "a9", "architect", "Design S-7 elsewhere", "2026-11-05T09:00:00Z",
               "2026-11-05T09:05:00Z", 100)
    (product.root / ".baton").mkdir()
    rows = [{"agent_id": "a2", "tool": "Read", "file": "svc/A.java", "tokens": 50}] * 3
    rows.append({"agent_id": "a1", "tool": "Read", "file": "svc/A.java", "tokens": 50})
    (product.root / ".baton/reads.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (product.root / "docs/qa/F-1/S-1-triage.md").write_text(
        "## Findings by lens\n| Finding | Verdict | Lenses |\n| --- | --- | --- |\n"
        "| F1 | high | edge-case |\n| F2 | medium | edge-case+conformance |\n| F3 | low | craft |\n"
        "\n## Counts\nHIGH: 1\nMEDIUM: 1\nLOW: 1\n"
    )
    return product, folder


def test_eval_times_tokens_waits_and_rereads(evaluated):
    product, folder = evaluated
    agents = evaluate.load_agents(folder, evaluate.story_ids(product.root) | {"S-7"})
    s = evaluate.summarize(product.root, "S-1", agents, evaluate.load_reads(product.root), gap=2)
    order = [a["agent"] for a in s["agents"]]
    assert order == ["architect", "developer", "general-purpose", "general-purpose"]
    assert s["byAgent"]["developer"] == {"runs": 1, "minutes": 20.0, "tokensIn": 3000, "tokensOut": 10}
    assert s["spanMinutes"] == 56.0
    assert s["agentMinutes"] == 35.0  # 10 + 20 + the two overlapping lenses, 10:51-10:56, as 5
    assert s["waits"] == [{"minutes": 20.0, "before": "developer"}]
    developer = next(a for a in s["agents"] if a["agent"] == "developer")
    assert (developer["reads"], developer["rereads"]) == (3, 2)
    assert s["lenses"]["edge-case"] == {"findings": 2, "unique": 1, "uniqueHighMedium": 1}
    assert s["lenses"]["conformance"] == {"findings": 1, "unique": 0, "uniqueHighMedium": 0}
    assert s["lenses"]["craft"]["unique"] == 1 and s["lenses"]["craft"]["uniqueHighMedium"] == 0


def test_eval_cli(evaluated, capsys):
    product, folder = evaluated
    code = main(["eval", "S-1", "--central", str(product.root), "--transcripts", str(folder)])
    out = capsys.readouterr().out
    assert code == 0 and "S-1  risk -  span 56.0 min = agents 35.0 + waiting 20.0" in out
    assert "waited 20.0 min before developer" in out and "edge-case" in out
    assert main(["eval", "--central", str(product.root), "--transcripts", str(folder / "none")]) == 2
    assert main(["eval", "S-1", "--central", str(product.root), "--transcripts", str(folder / "none")]) == 1


def test_project_dir_follows_claude_codes_naming(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert evaluate.project_dir(Path("/Users/me/work/my_central.v2")) == (
        tmp_path / "projects" / "-Users-me-work-my-central-v2"
    )


def test_reads_story_finds_the_agents_of_a_story(evaluated, monkeypatch):
    product, folder = evaluated
    monkeypatch.setattr(evaluate, "project_dir", lambda central: folder)
    agents = reads.story_agents(product.root, "S-1")
    assert agents == {"a1", "a2", "a3", "a4"}
    rows = reads.select(reads.load(product.root), None, "S-1", False, agents)
    assert len(rows) == 4


# -- mutation on changed lines ---------------------------------------------------------------------------

REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<mutations>
<mutation status='KILLED'><mutatedClass>a.b.Fee</mutatedClass><lineNumber>3</lineNumber></mutation>
<mutation status='SURVIVED'><mutatedClass>a.b.Fee</mutatedClass><lineNumber>4</lineNumber></mutation>
<mutation status='SURVIVED'><mutatedClass>a.b.Fee</mutatedClass><lineNumber>1</lineNumber></mutation>
<mutation status='SURVIVED'><mutatedClass>a.b.Fee$In</mutatedClass><lineNumber>5</lineNumber></mutation>
</mutations>
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.t", *args], cwd=repo, check=True,
                   capture_output=True)


def test_only_changed_non_logging_lines_count(tmp_path):
    repo = tmp_path / "svc"
    source = repo / "src/main/java/a/b/Fee.java"
    source.parent.mkdir(parents=True)
    source.write_text("package a.b;\nclass Fee {\n}\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    source.write_text("package a.b;\nclass Fee {\n  int x = 1;\n  int y = 2;\n  log.info(\"y\");\n}\n")
    git(repo, "commit", "-qam", "change")
    lines = pit.changed_lines(repo, "HEAD~1")
    assert lines == {"src/main/java/a/b/Fee.java": {3, 4, 5}}
    report = tmp_path / "mutations.xml"
    report.write_text(REPORT)
    counts = pit.count_mutations([report], ["a.b.Fee"], lines, repo)
    assert counts == {"killed": 1, "survived": 1, "noCoverage": 0}  # line 1 unchanged, line 5 is logging
    assert pit.count_mutations([report], ["a.b.Fee"]) == {"killed": 1, "survived": 3, "noCoverage": 0}


def test_pit_runs_threaded_with_history(tmp_path):
    repo = tmp_path / "svc"
    repo.mkdir()
    (repo / "pom.xml").write_text("<project><!-- pitest-maven --></project>")
    (repo / "mvnw").write_text("#!/bin/sh\n")
    command, _, reason = pit.plan(repo, ["a.b.Fee"])
    assert reason is None and "-DwithHistory=true" in command
    assert any(arg.startswith("-Dthreads=") and int(arg.split("=")[1]) >= 1 for arg in command)
