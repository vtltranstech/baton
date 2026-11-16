"""baton context (contracts/context-map.md) on fixtures/sample-context: 12 planted branch points, 5 mapped."""

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from baton import cli, miniyaml, state_check
from baton.context import branch_points as bp
from baton.context import build, check, score
from baton.context import domain as dm
from baton.context.product import load_points, load_repos, load_settings
from baton.extract import treesitter_backend

for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-context"
EXPECTED = json.loads((FIXTURE / "EXPECTED.json").read_text())
GRACE = 'What does "Grace Period" mean in this product?'


@pytest.fixture
def product(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "p")
    return tmp_path / "p" / "central"


def context_cli(central: Path, *args: str) -> int:
    return cli.main(["context", "--central", str(central), *args])


def built(central: Path, use_treesitter: bool = True) -> dict:
    return build.run_build(
        central, load_repos(central), dm.load(central), load_settings(central), use_treesitter
    )


def understood(central: Path) -> None:
    """The explorers' notes of the example: billing understood, pricing blocked (gate 0 lets billing pass)."""
    target = central / "docs" / "context" / "understanding"
    shutil.copytree(FIXTURE / "understanding-example", target)
    (target / "README.md").unlink()


def computed(central: Path) -> dict:
    return score.compute(
        central, load_repos(central), dm.load(central), load_points(central), load_settings(central)
    )


def _backends():
    return ["treesitter", "scan"] if treesitter_backend.available() else ["scan"]


@pytest.mark.parametrize("backend", _backends())
def test_every_planted_branch_point_is_found_and_nothing_else(product, backend):
    built(product, use_treesitter=backend == "treesitter")
    found = [
        {"file": p["file"], "line": p["line"], "kind": p["kind"], "fields": p["fields"], "rule": p["rule"]}
        for p in load_points(product)
    ]
    assert found == EXPECTED["branchPoints"]
    extractor = "branch-points-java" if backend == "treesitter" else "branch-points-java-scan"
    assert {p["provenance"]["extractor"] for p in load_points(product)} == {extractor}


def test_scanner_reads_typescript_and_skips_guards_comments_and_strings():
    source = (
        "export function Row({ invoice, status }: Props) {\n"
        "  // if (invoice.status === 'X') is a comment\n"
        "  if (invoice == null) { return null; }\n"
        '  if (invoice.status === "OVERDUE") { return null; }\n'
        "  const label = status === 'PAID' ? 'paid' : 'open';\n"
        "  return <div>{invoice.amountDue > 0 && <Badge/>}"
        "{rows.filter(x => x.tier === 'GOLD').length}</div>;\n"
        "}\n"
    )
    vocab = bp.Vocabulary(words={"invoice"})
    found = [(p.line, p.kind, p.fields) for p in bp.points_in(source, "ui", "src/Row.tsx", vocab)]
    assert found == [
        (4, "if", ["invoice", "status"]),
        (5, "ternary", ["status"]),
        (6, "filter", ["tier"]),
        (6, "jsx-and", ["invoice", "amountDue"]),
    ]
    assert bp.fields_of('x.equals("status")', vocab) == []
    assert bp.fields_of('name = "pricing.tier.enabled"', vocab, read_strings=True) == ["tier"]


def test_domain_md_is_read_as_an_index(product):
    domain = dm.load(product)
    assert [r.id for r in domain.confirmed_rules()] == ["R1", "R2", "R3", "R4", "R5"]
    r6 = domain.rule("R6")
    assert r6 is not None and not r6.indexable and r6.is_draft
    assert domain.rule("R5").fields == ["expiryDate", "periodStart"]
    words = {w.word: w.defined for w in domain.words}
    assert words == {"Invoice": True, "Customer": True, "Tier": True, "Grace Period": False}
    assert [d.owned for d in domain.decisions] == [True, False]
    template = dm.parse((ROOT / "templates" / "profile" / "domain.md").read_text())
    assert template.rules == [] and template.words == []


def test_build_keeps_ids_and_human_mappings_and_proposes_rules(product):
    summary = built(product)
    assert (summary["branchPoints"], summary["mapped"], summary["undocumented"]) == (12, 5, 7)
    first = (product / "profile" / "branch-points.yaml").read_text()
    points = load_points(product)
    query = next(p for p in points if p["kind"] == "query")
    assert query["proposed"] == "R2" and query["confidence"] == "field-overlap 1/1"
    built(product)
    again = (product / "profile" / "branch-points.yaml").read_text()
    assert first.split("\n", 3)[3] == again.split("\n", 3)[3]  # all but the generated line
    path = product / "profile" / "branch-points.yaml"
    text = path.read_text().replace(
        "    rule: null\n    status: undocumented", "    rule: null\n    status: contested", 1
    )
    path.write_text(text)
    built(product)
    assert sum(p["status"] == "contested" for p in load_points(product)) == 1


def test_branch_points_file_matches_its_schema(product):
    jsonschema = pytest.importorskip("jsonschema")
    built(product)
    document = miniyaml.loads((product / "profile" / "branch-points.yaml").read_text())
    jsonschema.validate(document, json.loads((ROOT / "schemas" / "branch-points.json").read_text()))
    settings = miniyaml.loads((ROOT / "templates" / "profile" / "context.yaml").read_text())
    jsonschema.validate(settings, json.loads((ROOT / "schemas" / "context.json").read_text()))


def test_drafts_stay_unconfirmed_and_a_confirmed_one_survives_a_rebuild(product):
    built(product)
    drafts = product / "profile" / "domain-drafts.md"
    text = drafts.read_text()
    assert "\nconfirmed: true" not in text and "drafted-by: baton context build (branch-point miner)" in text
    assert "source: test InvoiceReminderTest.paidInvoiceIsNotReminded" in text
    assert "ac1_overdueInvoiceIsReminded" not in text  # R1 cites it already
    start = text.index("### R-draft-", text.index("## shop-service/pricing"))
    end = text.index("confirmed: false", start)
    drafts.write_text(text[:end] + "confirmed: true" + text[end + len("confirmed: false") :])
    kept = text[start:end].splitlines()[0]
    built(product)
    after = drafts.read_text()
    confirmed = after.split("## Confirmed, waiting to move into domain.md")[1].split("\n## ")[0]
    assert kept in confirmed and after.count(kept.split(" - ", 1)[1]) == 1


def test_scores_per_layer_and_readiness(product):
    built(product)
    data = computed(product)
    layers = data["layers"]
    assert (layers["domain"]["mapped"], layers["domain"]["branchPoints"], layers["domain"]["score"]) == (
        5,
        12,
        0.42,
    )
    assert layers["structural"] == {"score": 0.6, "modules": 2, "verified": 1, "edges": 3, "unresolved": 1}
    assert "overall" not in data and set(layers) == set(score.LAYERS)
    assert data["interviewOrder"] == ["shop-service/pricing"]
    lines = score.statements(data)
    assert lines[0] == "Ready for light and full stories in shop-service/billing."
    assert lines[1].startswith("Not ready for stories in shop-service/pricing:")
    assert "7 undocumented branch points" in lines[1]
    assert lines[-1].startswith("Ready as far as the code can tell")


def test_scores_are_deterministic(product):
    built(product)
    now = datetime(2026, 11, 13, tzinfo=UTC)
    args = (product, load_repos(product), dm.load(product), load_points(product), load_settings(product))
    assert score.compute(*args, now=now) == score.compute(*args, now=now)


def test_score_writes_the_map_and_refuses_before_a_build(product):
    assert context_cli(product, "score") == 2
    assert context_cli(product, "build") == 0
    assert context_cli(product, "score") == 0
    rendered = (product / "docs" / "context" / "context-map.md").read_text()
    for heading in (
        "## Readiness",
        "## Scorecard",
        "## Trend",
        "## Gaps by module",
        "## Drafts awaiting confirmation",
        "## How to raise a score",
    ):
        assert heading in rendered
    assert "PriceResolver.java:27" in rendered


def test_a_light_story_blocks_on_its_undefined_word_until_the_po_defines_it(product):
    understood(product)
    assert context_cli(product, "build") == 0 and context_cli(product, "score") == 0
    assert context_cli(product, "check", "S-001") == 2
    story = product / "docs" / "stories" / "F-001" / "S-001.md"
    assert f"- [context] Product Owner: {GRACE}" in story.read_text()
    result = json.loads((product / "docs" / "design" / "F-001" / "S-001-context.json").read_text())
    assert result["blocking"] == 1 and [g["kind"] for g in result["gaps"]] == ["undefined-word"]
    assert result["scope"] == ["shop-service/billing"] and result["load"]["rules"] == ["R1", "R2", "R4"]
    moved = state_check.check(story, "Ready for PO", story.read_text() + "\n## Readiness\n9/9\n", product)
    assert not moved.ok and "blocking context gap" in moved.missing
    domain = product / "profile" / "domain.md"
    domain.write_text(
        domain.read_text().replace(
            "| Grace Period |  | false |",
            "| Grace Period | Days after the due date before a reminder | true |",
        )
    )
    assert context_cli(product, "check", "S-001") == 0
    assert "[context]" not in story.read_text()
    moved = state_check.check(story, "Ready for PO", story.read_text() + "\n## Readiness\n9/9\n", product)
    assert moved.ok
    trend = json.loads((product / "docs" / "context" / "context-map.json").read_text())["trend"]
    assert [t["story"] for t in trend] == ["S-001"] and trend[0]["domain"] == 0.42


def test_a_spike_never_blocks_but_lists_the_same_gaps(product):
    built(product)
    assert context_cli(product, "check", "S-002") == 0
    result = json.loads((product / "docs" / "design" / "F-001" / "S-002-context.json").read_text())
    assert [(g["kind"], g["blocking"]) for g in result["gaps"]] == [
        ("undefined-word", False),
        ("not-understood", False),
    ]
    assert GRACE in result["gaps"][0]["question"]


def test_a_full_story_blocks_on_undocumented_branch_points_in_the_module_it_changes(product):
    built(product)
    result = check.check(
        product, "S-003", load_repos(product), dm.load(product), load_points(product), load_settings(product)
    )
    kinds = [g["kind"] for g in result["gaps"] if g["blocking"]]
    assert kinds.count("undocumented-branch-in-changed-module") == 6  # the 7th is about the Tier the ACs name
    assert "unresolved-edge-out" in kinds and result["changed"] == ["shop-service/pricing"]


def test_no_write_writes_nothing(product):
    built(product)
    before = sorted(p.relative_to(product).as_posix() for p in product.rglob("*"))
    story = (product / "docs" / "stories" / "F-001" / "S-001.md").read_text()
    assert context_cli(product, "check", "S-001", "--no-write") == 2
    assert sorted(p.relative_to(product).as_posix() for p in product.rglob("*")) == before
    assert (product / "docs" / "stories" / "F-001" / "S-001.md").read_text() == story


def test_once_there_is_a_context_map_a_story_never_checked_is_refused(product):
    story = product / "docs" / "stories" / "F-001" / "S-001.md"
    moved = state_check.check(story, "Ready for PO", story.read_text() + "\n## Readiness\n9/9\n", product)
    assert not moved.ok and "run baton context check S-001 first (gate 0)" in moved.missing
    (product / "profile" / "branch-points.yaml").unlink()
    assert state_check.check(story, "Ready for PO", story.read_text() + "\n## Readiness\n9/9\n", product).ok
