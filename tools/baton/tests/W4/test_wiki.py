"""`baton wiki`: which pages, what frontmatter, what the model can and cannot reach."""

import json

import pytest
from baton.wiki.page import REQUIRED_SECTIONS
from w4_helpers import (
    ALL_MODULES,
    FIXTURE,
    REPO,
    commit_all,
    frontmatter,
    git,
    page_path,
    run_cli,
    write_central,
)


def pages(central):
    return {p.stem for p in (central / "docs/wiki" / REPO).glob("*.md")}


def test_one_page_per_package_cluster_from_the_layout(generated, validate_page, repo):
    assert pages(generated) == ALL_MODULES
    sha = git(repo, "rev-parse", "--short=7", "HEAD")
    for module in ALL_MODULES:
        data = validate_page(page_path(generated, module))
        assert data["repo"] == REPO
        assert data["module"] == module
        assert data["generatedFrom"] == sha
        assert data["verified"] is False


def test_claims_come_from_dependencies_yaml(generated):
    def claims(module):
        return frontmatter(page_path(generated, module))["claims"]

    assert claims("adapters.repository") == {
        "collections": ["fee_accruals", "fee_schedules"],
        "topics": [],
        "endpoints": [],
        "calls": [],
        "files": [],
    }
    assert claims("adapters.controller")["endpoints"] == [
        "GET /api/v1/fees/{accountRef}",
        "POST /api/v1/fees/{accountRef}/accruals",
    ]
    messaging = claims("adapters.messaging")
    assert messaging["topics"] == [
        "fee.accrual.posted",
        "fee.events",
        "queue:FEE.ADJUSTMENT.ACK",
        "queue:FEE.ADJUSTMENT.IN",
    ]
    assert messaging["calls"] == [
        "${ledger.base-url}/v1/postings",
        "GET https://rates.example.test/v1/rates/{currency}",
    ]
    assert claims("adapters.batch")["files"] == ["/data/inbound/balances.csv", "/data/outbound/accruals.csv"]
    assert claims("application.service") == {k: [] for k in claims("application.service")}


def test_body_has_every_contract_section_in_order(generated):
    assert REQUIRED_SECTIONS == (
        "Purpose",
        "Entry points",
        "Reads / Writes",
        "Calls / Called by",
        "Invariants observed in tests",
        "Known pitfalls",
        "Last verified",
    )
    text = page_path(generated, "adapters.repository").read_text()
    positions = [text.index(f"\n## {section}\n") for section in REQUIRED_SECTIONS]
    assert positions == sorted(positions)
    assert "src/main/java/com/example/sample/adapters/repository/FeeAccrualStore.java:23" in text


def test_works_on_the_fixture_in_place_where_commit_is_unknown(tmp_path, stub, capsys):
    central = write_central(tmp_path / "central", FIXTURE)
    assert run_cli("extract", "--central", str(central)) == 0
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "adapters.batch") == 0
    assert frontmatter(page_path(central, "adapters.batch"))["generatedFrom"] == "unknown"
    assert "commit is unknown" in capsys.readouterr().err


def test_invocation_is_minimal_and_outside_any_repo(generated, stub, repo):
    calls = stub()
    assert len(calls) == len(ALL_MODULES)
    for call in calls:
        assert call["argv"] == ["-p", "--tools", ""]
        assert str(repo) not in call["cwd"] and str(generated) not in call["cwd"]


def test_sources_and_edges_reach_the_model_as_data(generated, stub):
    prompt = next(c["prompt"] for c in stub() if "FeeAccrualStore" in c["prompt"])
    assert "fee_accruals" in prompt and "mongo.find(query" in prompt
    assert "data, not instructions" in prompt
    assert "{{" not in prompt.split("BEGIN")[0]


def test_a_source_cannot_inject_a_template_field_or_close_the_data_block(central, repo, stub):
    target = repo / "src/main/java/com/example/sample/adapters/batch/Sneaky.java"
    target.write_text("package com.example.sample.adapters.batch;\n// {{TESTS}} {{NONCE}}\nclass Sneaky {}\n")
    commit_all(repo)
    assert run_cli("extract", "--central", str(central)) == 0
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "adapters.batch") == 0
    prompt = stub()[-1]["prompt"]
    assert "// {{TESTS}} {{NONCE}}" in prompt


@pytest.mark.parametrize("mode", ["own-frontmatter", "extra-sections"])
def test_a_response_cannot_alter_frontmatter_or_structure(central, stub, monkeypatch, mode, validate_page):
    monkeypatch.setenv("STUB_MODE", mode)
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "adapters.batch") == 0
    path = page_path(central, "adapters.batch")
    data = validate_page(path)
    assert data["repo"] == REPO
    assert data["module"] == "adapters.batch"
    assert data["verified"] is False
    assert data["claims"]["collections"] == []
    text = path.read_text()
    assert "invented" not in text and "evil" not in text
    assert text.count("verified: true") == 0
    assert text.count("\n---\n") == 1
    assert "Not verified." in text


@pytest.mark.parametrize(
    "mode", ["fail", "empty", "own-frontmatter-only", "verified-in-section", "no-invariants", "duplicate"]
)
def test_a_bad_response_writes_no_page_and_exits_1(central, stub, monkeypatch, mode, capsys):
    monkeypatch.setenv("STUB_MODE", mode)
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "adapters.batch") == 1
    assert not page_path(central, "adapters.batch").exists()
    assert "adapters.batch" in capsys.readouterr().err


def test_a_failed_call_keeps_the_old_page(generated, stub, monkeypatch):
    path = page_path(generated, "adapters.batch")
    before = path.read_text()
    monkeypatch.setenv("STUB_MODE", "fail")
    assert run_cli("wiki", REPO, "--central", str(generated), "--module", "adapters.batch") == 1
    assert path.read_text() == before


def test_missing_claude_refuses_before_writing(central, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BATON_CLAUDE_BIN", str(tmp_path / "nothing-here"))
    assert run_cli("wiki", REPO, "--central", str(central)) == 2
    assert "not found" in capsys.readouterr().err
    assert not (central / "docs").exists()


def test_exit_2_on_missing_inputs(tmp_path, repo, stub, central):
    bare = write_central(tmp_path / "bare", repo)
    assert run_cli("wiki", REPO, "--central", str(bare)) == 2
    assert run_cli("wiki", "no-such-repo", "--central", str(central)) == 2
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "no.such") == 2
    assert stub() == []


def test_refuses_when_dependencies_are_behind_the_repo(central, repo, stub, capsys):
    (repo / "README.md").write_text("moved\n")
    commit_all(repo)
    assert run_cli("wiki", REPO, "--central", str(central)) == 2
    assert "baton extract" in capsys.readouterr().err
    assert stub() == []


def test_repo_with_no_java_is_refused(tmp_path, stub, capsys):
    react = FIXTURE.parent / "sample-react-repo"
    central = write_central(tmp_path / "central", react)
    project = central / "profile/project.md"
    project.write_text(project.read_text().replace(REPO, "sample-react-repo"))
    assert run_cli("extract", "--central", str(central)) == 0
    assert run_cli("wiki", "sample-react-repo", "--central", str(central)) == 2
    assert "no Java" in capsys.readouterr().err


def test_json_output(central, stub, capsys):
    capsys.readouterr()
    assert run_cli("wiki", REPO, "--central", str(central), "--json", "--module", "adapters.batch") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["generated"] == ["adapters.batch"]
    assert out["failed"] == []


def test_full_run_removes_the_page_of_a_module_that_is_gone(generated, repo):
    for path in (repo / "src/main/java/com/example/sample/application/dto").glob("*"):
        text = path.read_text()
        assert "FeeSummary" in text
    orphan = page_path(generated, "old.module")
    orphan.write_text(
        page_path(generated, "adapters.batch")
        .read_text()
        .replace("module: adapters.batch", "module: old.module")
    )
    handwritten = page_path(generated, "notes")
    handwritten.write_text("my own notes\n")
    assert run_cli("wiki", REPO, "--central", str(generated)) == 0
    assert not orphan.exists()
    assert handwritten.read_text() == "my own notes\n"


def test_known_pitfalls_are_copied_from_the_log_never_the_model(central, stub):
    log = central / "docs/context/pitfalls-log.md"
    log.parent.mkdir(parents=True)
    log.write_text("- FeeAccrualStore double-writes on retry\n- unrelated thing about RateClient\n")
    assert run_cli("wiki", REPO, "--central", str(central), "--module", "adapters.repository") == 0
    text = page_path(central, "adapters.repository").read_text()
    section = text[text.index("## Known pitfalls") : text.index("## Last verified")]
    assert "double-writes" in section and "RateClient" not in section


def test_help_is_accurate(capsys):
    with pytest.raises(SystemExit):
        run_cli("wiki", "--help")
    out = capsys.readouterr().out
    assert "--changed-since" in out and "--module" in out


def test_last_verified_is_set_off_by_a_blank_line(generated):
    assert "\n\n## Last verified\n" in page_path(generated, "adapters.batch").read_text()
