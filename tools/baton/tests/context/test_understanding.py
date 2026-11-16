"""System understanding (contracts/context-map.md section 10): the explorers' notes graded against the code,
and the feature gate. The notes are fixtures/sample-context/understanding-example, written as an explorer
would; every test changes one thing in them and checks the grader catches it."""

import json
import os
import shutil
from pathlib import Path

import pytest
from baton import cli
from baton.context import understanding as us

for _name in [name for name in os.environ if name.startswith("GIT_")]:
    del os.environ[_name]

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-context"
BILLING = "docs/context/understanding/areas/shop-service--billing.md"
PRICING = "docs/context/understanding/areas/shop-service--pricing.md"
LANDSCAPE = "docs/context/understanding/landscape.md"
JAVA = "src/main/java/com/example/shop"


@pytest.fixture
def product(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "p")
    central = tmp_path / "p" / "central"
    assert context_cli(central, "build") == 0
    return central


@pytest.fixture
def explored(product):
    target = product / us.FOLDER
    shutil.copytree(FIXTURE / "understanding-example", target)
    (target / "README.md").unlink()
    return product


def context_cli(central: Path, *args: str) -> int:
    return cli.main(["context", "--central", str(central), *args])


def status(central: Path) -> dict:
    assert context_cli(central, "understand") == 0
    return json.loads((central / us.STATUS_JSON).read_text())


def edit(central: Path, rel: str, old: str, new: str) -> None:
    path = central / rel
    text = path.read_text()
    assert old in text, old
    path.write_text(text.replace(old, new, 1))


def add_edge(central: Path, kind: str, source: str, target: str, file: str, line: int) -> None:
    edit(
        central,
        "profile/dependencies.yaml",
        "    edges:\n",
        f'    edges:\n      - kind: {kind}\n        from: {source}\n        to: "{target}"\n'
        f"        provenance: {{file: {file}, line: {line}, extractor: test}}\n",
    )


def test_before_anyone_explores_nothing_is_understood_and_the_feature_is_not_accepted(product, capsys):
    data = status(product)
    assert data["counts"]["unexplored"] == 2 and not data["understood"]
    assert data["landscape"]["status"] == "unexplored"
    assert set(data["boundary"]) == {
        "collection:invoices",
        "collection:prices",
        "endpoint:GET ${rates.base-url}/rates",
    }
    capsys.readouterr()
    assert context_cli(product, "check", "F-001") == 2
    out = capsys.readouterr().out
    assert "shop-service/billing is unexplored" in out and "not accepted yet" in out
    assert (product / "docs" / "design" / "F-001" / "F-001-context.md").is_file()


def test_the_brief_lists_what_an_explorer_must_explain(product, capsys):
    capsys.readouterr()
    assert context_cli(product, "brief", "shop-service/billing") == 0
    out = capsys.readouterr().out
    assert "<!-- baton:understanding area=shop-service/billing commit=fx00001 code=" in out
    assert f"writes collection:invoices (at {JAVA}/billing/InvoiceStore.java:14)" in out
    assert "bp-0001" in out and "decided by R1" in out
    assert context_cli(product, "brief", "shop-service/nowhere") == 1
    capsys.readouterr()
    assert context_cli(product, "brief", "system") == 0
    assert (
        '"endpoint:GET ${rates.base-url}/rates": "the extractors could not resolve it"'
        in capsys.readouterr().out
    )


def test_the_example_billing_is_understood_pricing_waits_for_the_po_and_f001_is_accepted(explored, capsys):
    data = status(explored)
    assert data["areas"]["shop-service/billing"] == {
        **data["areas"]["shop-service/billing"],
        "status": "understood",
        "problems": [],
    }
    pricing = data["areas"]["shop-service/pricing"]
    assert pricing["status"] == "blocked" and pricing["problems"] == []
    assert sum(1 for q in pricing["questions"] if q["blocking"] and not q["answer"]) == 6
    assert data["landscape"]["status"] == "understood"
    assert data["landscape"]["systems"] == ["catalogue", "rates", "reporting"]
    assert [f["valid"] for f in data["flows"]] == [True, True]
    capsys.readouterr()
    assert context_cli(explored, "check", "F-001") == 0
    assert "accepted for story drafting" in capsys.readouterr().out
    manifest = (explored / "docs" / "design" / "F-001" / "F-001-context.md").read_text()
    assert f"- understanding: {BILLING}" in manifest
    assert "- flow: docs/context/understanding/flows/invoice-storage.md" in manifest


def test_a_feature_on_a_blocked_area_waits_for_the_answers(explored, capsys):
    feature = explored / "docs" / "features" / "F-002-price-review.md"
    feature.write_text("# F-002 Review the prices\n\n## Outcome\nThe prices are reviewed every quarter.\n")
    capsys.readouterr()
    assert context_cli(explored, "check", "F-002") == 2
    out = capsys.readouterr().out
    assert "shop-service/pricing is blocked: 6 questions for a human" in out
    assert "BLOCKING Product Owner: What makes a price promotional" in out
    note = explored / PRICING
    text = note.read_text()
    for n in range(1, 7):
        marker = f"- Q{n} (blocking, PO):"
        start = text.index(marker)
        end = text.index("\n", start)
        text = text[: end + 1] + f"  answer: rule given by the Product Owner ({n})\n" + text[end + 1 :]
    note.write_text(text)
    assert status(explored)["areas"]["shop-service/pricing"]["status"] == "understood"
    assert context_cli(explored, "check", "F-002") == 0


def test_a_claim_the_code_does_not_make_is_caught(explored):
    edit(
        explored,
        BILLING,
        "## Rules",
        f"- publishes topic:invoice-issued - tells the mail service [{JAVA}/billing/InvoiceStore.java:14]\n\n"
        "## Rules",
    )
    area = status(explored)["areas"]["shop-service/billing"]
    assert area["status"] == "incomplete"
    assert any(p.startswith("not in the code: publishes topic:invoice-issued") for p in area["problems"])


def test_a_missing_edge_a_bad_citation_and_a_wrong_rule_are_caught(explored):
    edit(
        explored, BILLING, f"[{JAVA}/billing/InvoiceStore.java:14]", f"[{JAVA}/billing/InvoiceStore.java:99]"
    )
    edit(explored, BILLING, "are reminded (R1)", "are reminded (R2)")
    problems = status(explored)["areas"]["shop-service/billing"]["problems"]
    assert any(
        p.endswith(f"[{JAVA}/billing/InvoiceStore.java:99]: {JAVA}/billing/InvoiceStore.java has 16 lines")
        for p in problems
    ), problems
    assert "bp-0001 is decided by R1 (profile/branch-points.yaml); name it" in problems
    edit(explored, BILLING, "- writes collection:invoices", "- nothing")
    problems = status(explored)["areas"]["shop-service/billing"]["problems"]
    assert any(p.startswith("missing: writes collection:invoices") for p in problems)


def test_an_unmapped_branch_point_needs_a_question_and_the_question_blocks(explored):
    edit(explored, PRICING, "used; which rule says so? (Q1)", "used, as everyone knows")
    problems = status(explored)["areas"]["shop-service/pricing"]["problems"]
    assert any(p.startswith("bp-0006 has no confirmed rule") for p in problems)


def test_an_open_question_marked_open_on_an_unmapped_point_still_blocks(explored):
    edit(explored, PRICING, "- Q1 (blocking, PO):", "- Q1 (open, PO):")
    area = status(explored)["areas"]["shop-service/pricing"]
    assert next(q for q in area["questions"] if q["id"] == "Q1")["blocking"] is True


def test_a_note_written_at_an_older_commit_is_stale(explored):
    edit(explored, "profile/dependencies.yaml", "commit: fx00001", "commit: fx00002")
    data = status(explored)
    assert data["areas"]["shop-service/billing"]["status"] == "stale"
    assert "read the area again" in data["areas"]["shop-service/billing"]["problems"][0]


def test_a_merge_makes_stale_only_the_areas_whose_code_changed(explored):
    repo = explored.parent / "shop-service"
    for rel, module in ((BILLING, "billing"), (PRICING, "pricing")):
        key = f"shop-service/{module}"
        line = us.header(*next((r, m) for k, (r, m) in us.areas_of(_repos(explored)).items() if k == key))
        path = explored / rel
        text = path.read_text()
        path.write_text(line + text[text.index("\n") :])
    edit(explored, "profile/dependencies.yaml", "commit: fx00001", "commit: fx00002")
    data = status(explored)
    assert data["areas"]["shop-service/billing"]["status"] == "understood"
    assert data["areas"]["shop-service/pricing"]["status"] == "blocked"
    source = repo / JAVA / "pricing" / "PriceResolver.java"
    source.write_text(source.read_text() + "\n// reviewed\n")
    data = status(explored)
    assert data["areas"]["shop-service/billing"]["status"] == "understood"
    pricing = data["areas"]["shop-service/pricing"]
    assert pricing["status"] == "stale"
    assert pricing["problems"][0].startswith("the code of shop-service/pricing changed")


def _repos(central: Path) -> list:
    from baton.context import product

    return product.load_repos(central)


def test_flow_steps_must_be_joined_by_a_shared_area_or_resource(explored):
    edit(
        explored,
        "docs/context/understanding/flows/order-pricing.md",
        "1. external:Catalogue writes collection:prices",
        "1. external:Catalogue writes collection:catalogue",
    )
    flow = next(f for f in status(explored)["flows"] if f["path"].endswith("order-pricing.md"))
    assert not flow["valid"]
    assert any(p.startswith("steps 1 and 2 are not joined") for p in flow["problems"])


def test_a_uses_step_needs_an_import(explored):
    edit(
        explored,
        "docs/context/understanding/flows/invoice-storage.md",
        "2. external:Reporting",
        f"2. shop-service/billing uses shop-service/pricing - billing asks pricing for the amount "
        f"[{JAVA}/billing/InvoiceTotals.java:9]\n3. external:Reporting",
    )
    flow = next(f for f in status(explored)["flows"] if f["path"].endswith("invoice-storage.md"))
    assert "step 2: no code in shop-service/billing imports code in shop-service/pricing" in flow["problems"]


def test_every_entry_point_must_be_followed_end_to_end(explored):
    add_edge(
        explored,
        "EXPOSES",
        "class:com.example.shop.billing.InvoiceStore",
        "endpoint:POST /invoices",
        f"{JAVA}/billing/InvoiceStore.java",
        13,
    )
    edit(
        explored,
        BILLING,
        "## Rules",
        "- exposes endpoint:POST /invoices - checkout hands over each new invoice here "
        f"[{JAVA}/billing/InvoiceStore.java:13]\n\n## Rules",
    )
    data = status(explored)
    billing = data["areas"]["shop-service/billing"]
    assert billing["status"] == "incomplete"
    assert billing["problems"][0].startswith("not in any flow: exposes endpoint:POST /invoices")
    assert any(
        "endpoint:POST /invoices (served here: who calls it?)" in p for p in data["landscape"]["problems"]
    )
    edit(
        explored,
        "docs/context/understanding/flows/invoice-storage.md",
        "1. shop-service/billing writes",
        "1. external:Checkout calls endpoint:POST /invoices - checkout sends the new invoice\n"
        "2. shop-service/billing exposes endpoint:POST /invoices - billing accepts it "
        f"[{JAVA}/billing/InvoiceStore.java:13]\n3. shop-service/billing writes",
    )
    edit(
        explored,
        LANDSCAPE,
        "| Rates |",
        "| Checkout | upstream | http | endpoint:POST /invoices | "
        f"[shop-service/{JAVA}/billing/InvoiceStore.java:13] |\n"
        "| Rates |",
    )
    data = status(explored)
    assert data["areas"]["shop-service/billing"]["status"] == "understood", data["areas"]
    assert data["landscape"]["status"] == "understood"


def test_an_unknown_system_in_the_landscape_keeps_the_feature_out(explored, capsys):
    edit(explored, LANDSCAPE, "| Reporting | downstream", "| ? | downstream")
    edit(
        explored,
        "docs/context/understanding/flows/invoice-storage.md",
        "external:Reporting",
        "external:Accounts",
    )
    capsys.readouterr()
    assert context_cli(explored, "check", "F-001") == 2
    assert "collection:invoices: which system is on the other side?" in capsys.readouterr().out


def test_the_context_map_shows_the_understanding_and_the_story_manifest_loads_the_notes(explored):
    assert context_cli(explored, "score") == 0
    text = (explored / "docs" / "context" / "context-map.md").read_text()
    assert "## System understanding" in text and "1 understood, 1 blocked" in text
    assert context_cli(explored, "check", "S-001") in (0, 2)
    manifest = (explored / "docs" / "design" / "F-001" / "S-001-context.md").read_text()
    assert f"- understanding: {BILLING}" in manifest


def test_the_grader_makes_no_model_or_network_call():
    source = (ROOT / "tools" / "baton" / "context" / "understanding.py").read_text()
    for forbidden in ("urllib", "http.client", "socket", "requests", "subprocess", "anthropic", "claude -p"):
        assert forbidden not in source


CLASH = (
    "\n## Contradictions\n- C1: docs/legacy/notes.txt says paid invoices are reminded too, the code skips "
    f"them [docs/legacy/notes.txt] [{JAVA}/billing/InvoiceReminder.java:1]\n"
)


def test_a_contradiction_blocks_its_area_until_the_tech_lead_resolves_it(explored, capsys):
    path = explored / BILLING
    path.write_text(path.read_text() + CLASH)
    billing = status(explored)["areas"]["shop-service/billing"]
    assert billing["status"] == "blocked" and billing["contradictions"][0]["id"] == "C1"
    capsys.readouterr()
    assert context_cli(explored, "check", "F-001") == 2
    assert context_cli(explored, "check", "F-001", "--track", "light") == 2
    assert "paid invoices are reminded too" in capsys.readouterr().out
    assert (
        context_cli(explored, "answer", "shop-service/billing", "C1", "the note is out of date", "--by", "TL")
        == 0
    )
    assert "  resolved: the note is out of date (TL, " in path.read_text()
    assert status(explored)["areas"]["shop-service/billing"]["status"] == "understood"
    assert context_cli(explored, "check", "F-001") == 0


def test_a_contradiction_must_be_written_so_it_can_be_resolved(explored):
    path = explored / BILLING
    path.write_text(path.read_text() + "\n## Contradictions\n- the wiki says otherwise\n")
    problems = status(explored)["areas"]["shop-service/billing"]["problems"]
    assert any(p.startswith("cannot read contradiction `- the wiki says otherwise`") for p in problems)


def test_light_work_may_start_with_a_few_questions_open_full_work_may_not(explored):
    feature = explored / "docs" / "features" / "F-002-price-review.md"
    feature.write_text("# F-002 Review the prices\n\n## Outcome\nThe prices are reviewed every quarter.\n")
    assert context_cli(explored, "check", "F-002", "--track", "light") == 2  # six open, two allowed
    for n in range(1, 5):
        assert (
            context_cli(explored, "answer", "shop-service/pricing", f"Q{n}", f"rule {n}", "--by", "PO") == 0
        )
    assert context_cli(explored, "check", "F-002", "--track", "light") == 0
    assert context_cli(explored, "check", "F-002") == 2
    assert context_cli(explored, "check", "F-002", "--track", "spike") == 0


def test_an_answer_is_written_verbatim_once(explored, capsys):
    words = "Only ACTIVE prices count; a price is active from its start date"
    assert context_cli(explored, "answer", "shop-service/pricing", "Q1", words, "--by", "PO") == 0
    text = (explored / PRICING).read_text()
    marker = "- Q1 (blocking, PO):"
    after = text[text.index(marker) :].splitlines()[1]
    assert after.startswith(f"  answer: {words} (PO, ")
    capsys.readouterr()
    assert context_cli(explored, "answer", "shop-service/pricing", "Q1", "again", "--by", "PO") == 2
    assert "already has an answer" in capsys.readouterr().err
    assert context_cli(explored, "answer", "shop-service/pricing", "Q9", "x", "--by", "PO") == 2
    assert context_cli(explored, "answer", "shop-service/pricing", "Q2", "no role") == 2
    assert context_cli(explored, "answer", "landscape", "Q1", "already answered", "--by", "TL") == 2


def test_questions_are_listed_by_person_and_old_ones_escalate(explored):
    from baton.context import product

    repos = product.load_repos(explored)
    grade = lambda: us.grade_all(  # noqa: E731
        explored, repos, us.dm.load(explored), product.load_points(explored) or []
    )
    us.write(explored, grade(), today="2026-11-01")
    first = grade()
    us.write(explored, first, today="2026-11-10")
    page = us.questions_page(first, 3, "2026-11-10")
    assert "## Product Owner" in page and "## Tech Lead" in page
    assert "shop-service/pricing Q1 (blocking, asked 2026-11-01, 9 days) OVERDUE" in page
    assert context_cli(explored, "questions") == 0
    assert (explored / us.QUESTIONS_MD).is_file()


def test_the_state_gate_refuses_ready_when_an_area_slipped_after_the_check(explored):
    from baton import state_check

    domain = explored / "profile" / "domain.md"
    domain.write_text(
        domain.read_text().replace(
            "| Grace Period |  | false |",
            "| Grace Period | Days after the due date before a reminder | true |",
        )
    )
    story = explored / "docs" / "stories" / "F-001" / "S-001.md"
    assert context_cli(explored, "check", "S-001") == 0
    ready = story.read_text() + "\n## Readiness\n9/9\n"
    assert state_check.check(story, "Ready for PO", ready, explored).ok
    edit(explored, "profile/dependencies.yaml", "commit: fx00001", "commit: fx00002")
    assert context_cli(explored, "understand") == 0
    moved = state_check.check(story, "Ready for PO", ready, explored)
    assert not moved.ok and "shop-service/billing is now stale" in moved.missing
    assert "/build-context-map focus F-001" in moved.missing
