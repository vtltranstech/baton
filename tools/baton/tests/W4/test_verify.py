"""`baton verify`: every claim checked at the same commit, and `verified` only ever set by it."""

import json

import jsonschema
import pytest
from baton.wiki.page import schema_problems
from w4_helpers import (
    ALL_MODULES,
    FIXTURE,
    REPO,
    ROOT,
    commit_all,
    edit_frontmatter_line,
    frontmatter,
    page_path,
    report,
    run_cli,
    write_central,
)

BATCH = "adapters.batch"
REPOSITORY = "adapters.repository"


def verify(central, *extra):
    return run_cli("verify", REPO, "--central", str(central), *extra)


def reasons(central, module):
    entry = next(p for p in report(central)["pages"] if p["module"] == module)
    return " | ".join(entry["reasons"])


def test_true_pages_pass_and_get_verified(generated, validate_page, repo):
    assert verify(generated) == 0
    for module in ALL_MODULES:
        assert validate_page(page_path(generated, module))["verified"] is True
    data = report(generated)
    assert (data["passed"], data["failed"]) == (len(ALL_MODULES), 0)
    assert "Verified by baton verify at commit" in page_path(generated, BATCH).read_text()


def test_verify_is_idempotent(generated):
    assert verify(generated) == 0
    before = page_path(generated, BATCH).read_text()
    assert verify(generated) == 0
    assert page_path(generated, BATCH).read_text() == before


def test_planted_false_collection_fails(generated):
    edit_frontmatter_line(page_path(generated, BATCH), "collections: []", "collections: [fee_accruals]")
    assert verify(generated) == 1
    why = reasons(generated, BATCH)
    assert "claims.collections" in why and "fee_accruals" in why and "adapters.repository" in why
    assert frontmatter(page_path(generated, BATCH))["verified"] is False
    assert frontmatter(page_path(generated, REPOSITORY))["verified"] is True


def test_a_collection_nothing_reads_fails(generated):
    edit_frontmatter_line(
        page_path(generated, REPOSITORY),
        "collections: [fee_accruals, fee_schedules]",
        "collections: [fee_accruals, fee_schedules, invented]",
    )
    assert verify(generated) == 1
    assert "invented" in reasons(generated, REPOSITORY)


@pytest.mark.parametrize(
    "line,bad",
    [
        ("topics: []", "topics: [no.such.topic]"),
        ("endpoints: []", "endpoints: [GET /nope]"),
        ("calls: []", "calls: [application.port.RatePort]"),
        ("files: []", "files: [/data/nope.csv]"),
    ],
)
def test_every_claim_category_is_checked(generated, line, bad):
    edit_frontmatter_line(page_path(generated, "application.service"), line, bad)
    assert verify(generated) == 1
    assert "claims." + line.split(":")[0] in reasons(generated, "application.service")


def test_a_bare_queue_name_is_not_the_queue_claim(generated):
    path = page_path(generated, "adapters.messaging")
    text = path.read_text()
    path.write_text(text.replace("queue:FEE.ADJUSTMENT.IN", "FEE.ADJUSTMENT.IN", 1))
    assert verify(generated) == 1


def test_a_category_the_extractors_do_not_have_fails(generated):
    edit_frontmatter_line(page_path(generated, BATCH), "  files:", "  jobs: [feeAccrualJob]\n  files:")
    assert verify(generated) == 1
    assert "claims.jobs" in reasons(generated, BATCH)


def test_a_dropped_claim_fails(generated):
    path = page_path(generated, REPOSITORY)
    edit_frontmatter_line(path, "collections: [fee_accruals, fee_schedules]", "collections: [fee_accruals]")
    assert verify(generated) == 1
    why = reasons(generated, REPOSITORY)
    assert "fee_schedules" in why and "not claimed" in why


def test_unknown_commit_never_matches_unknown(tmp_path, stub):
    central = write_central(tmp_path / "central", FIXTURE)
    assert run_cli("extract", "--central", str(central)) == 0
    assert run_cli("wiki", REPO, "--central", str(central), "--module", BATCH) == 0
    page = frontmatter(page_path(central, BATCH))
    assert page["generatedFrom"] == "unknown"
    assert verify(central) == 1
    assert "commit: unknown" in reasons(central, BATCH)
    assert frontmatter(page_path(central, BATCH))["verified"] is False


def test_moved_repo_resets_verified_even_before_extract(generated, repo):
    assert verify(generated) == 0
    (repo / "README.md").write_text("moved\n")
    commit_all(repo)
    assert verify(generated) == 1
    assert "baton extract" in reasons(generated, BATCH)
    assert frontmatter(page_path(generated, BATCH))["verified"] is False


def test_moved_repo_after_extract_makes_pages_stale(generated, repo):
    assert verify(generated) == 0
    (repo / "README.md").write_text("moved\n")
    sha = commit_all(repo)
    assert run_cli("extract", "--central", str(generated)) == 0
    assert verify(generated) == 1
    assert sha in reasons(generated, BATCH) and "stale" in reasons(generated, BATCH)
    assert frontmatter(page_path(generated, BATCH))["verified"] is False


def test_uncommitted_changes_fail(generated, repo):
    (repo / "README.md").write_text("dirty\n")
    assert verify(generated) == 1
    assert "uncommitted" in reasons(generated, BATCH)


def test_edit_after_verify_fails_and_cannot_be_laundered(generated):
    assert verify(generated) == 0
    path = page_path(generated, BATCH)
    path.write_text(path.read_text().replace("Holds the module.", "Reads every table in the bank."))
    assert verify(generated) == 1
    assert "edited" in reasons(generated, BATCH)
    assert frontmatter(path)["verified"] is False
    assert verify(generated) == 1, "a second run must not bless the edit"


def test_text_appended_after_last_verified_fails(generated):
    assert verify(generated) == 0
    path = page_path(generated, BATCH)
    path.write_text(path.read_text() + "\nAlso writes the ledger.\n")
    assert verify(generated) == 1
    assert "Last verified" in reasons(generated, BATCH)


def test_hand_set_verified_on_a_false_page_is_reset(generated):
    path = page_path(generated, BATCH)
    text = (
        path.read_text()
        .replace("verified: false", "verified: true")
        .replace("collections: []", "collections: [invented]")
    )
    path.write_text(text)
    assert verify(generated) == 1
    assert frontmatter(path)["verified"] is False


@pytest.mark.parametrize(
    "content,expected",
    [
        ("no frontmatter here\n", "frontmatter"),
        ("---\nrepo: x\nverified: true\n", "frontmatter"),
        ("---\nrepo: [unterminated\n---\nbody\n", "frontmatter"),
    ],
)
def test_missing_or_broken_frontmatter_fails(generated, content, expected):
    page_path(generated, BATCH).write_text(content)
    assert verify(generated) == 1
    assert expected in reasons(generated, BATCH)


@pytest.mark.parametrize("key", ["repo", "module", "generatedFrom", "claims", "verified"])
def test_a_required_key_missing_fails(generated, key):
    path = page_path(generated, BATCH)
    lines = path.read_text().split("\n")
    end = lines.index("---", 1)
    kept, skipping = [], False
    for index, line in enumerate(lines):
        if index < end and line.startswith(f"{key}:"):
            skipping = True
            continue
        if skipping and line.startswith("  "):
            continue
        skipping = False
        kept.append(line)
    path.write_text("\n".join(kept))
    assert verify(generated) == 1
    assert key in reasons(generated, BATCH)


def test_page_for_another_module_or_repo_fails(generated):
    path = page_path(generated, BATCH)
    edit_frontmatter_line(path, f"module: {BATCH}", "module: adapters.controller")
    assert verify(generated) == 1
    assert "module" in reasons(generated, BATCH)


def test_page_for_a_module_that_does_not_exist_fails(generated):
    source = page_path(generated, BATCH).read_text().replace(f"module: {BATCH}", "module: gone.away")
    page_path(generated, "gone.away").write_text(source)
    assert verify(generated) == 1
    assert "no such module" in reasons(generated, "gone.away")


def test_report_and_json_output(generated, capsys):
    capsys.readouterr()
    assert verify(generated, "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out == report(generated)
    assert out["repo"] == REPO and out["commit"] == frontmatter(page_path(generated, BATCH))["generatedFrom"]
    assert {p["module"] for p in out["pages"]} == ALL_MODULES


def test_modules_without_a_page_are_reported_not_failed(central, stub):
    assert run_cli("wiki", REPO, "--central", str(central), "--module", BATCH) == 0
    assert verify(central) == 0
    assert "adapters.repository" in report(central)["modulesWithoutPage"]


def test_exit_2_on_missing_inputs(central, tmp_path, repo):
    assert verify(central) == 2  # no pages
    assert run_cli("verify", "no-such", "--central", str(central)) == 2
    assert run_cli("verify", REPO, "--central", str(write_central(tmp_path / "x", repo))) == 2


def test_verify_never_calls_the_model(generated, stub):
    before = len(stub())
    assert verify(generated) == 0
    assert len(stub()) == before


GOOD = {"repo": "r", "module": "m", "generatedFrom": "abc", "claims": {"topics": ["t"]}, "verified": False}


@pytest.mark.parametrize(
    "front",
    [
        GOOD,
        {k: v for k, v in GOOD.items() if k != "repo"},
        {**GOOD, "verified": "true"},
        {**GOOD, "generatedFrom": 1234567},
        {**GOOD, "claims": []},
        {**GOOD, "claims": {"topics": "t"}},
        {**GOOD, "claims": {"topics": [1]}},
        {**GOOD, "bodySha256": "x"},
    ],
)
def test_stdlib_schema_check_agrees_with_the_real_schema(front):
    schema = json.loads((ROOT / "schemas/wiki-page.json").read_text())
    valid = not list(jsonschema.Draft202012Validator(schema).iter_errors(front))
    assert (schema_problems(front) == []) == valid
