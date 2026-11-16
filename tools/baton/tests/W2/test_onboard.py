"""`baton onboard`: the questions the fixture cannot answer, nothing else written, refresh shows a diff."""

import argparse
import io
import json
import sys
import types
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import jsonschema
import pytest
from baton import cli, miniyaml
from baton.extract.pipeline import GENERATED_FILES
from conftest import copy_fixture, git, schema, write_project

FIXTURE_QUESTIONS = {
    "stack:sample-react-repo:testCmd",
    "shared-collections:sample-java-repo",
    "confirm-aggregates",
    "unresolved:sample-java-repo:endpoint:${ledger.base-url}/v1/postings",
    "messaging-peer:queue:FEE.ADJUSTMENT.ACK",
    "messaging-peer:queue:FEE.ADJUSTMENT.IN",
    "messaging-peer:topic:fee.accrual.posted",
    "messaging-peer:topic:fee.events",
    "file-peer:file:/data/inbound/balances.csv",
    "file-peer:file:/data/outbound/accruals.csv",
    "job-schedule:job:feeAccrualJob",
    "domain-words",
    "invariants",
    "confirm-risk-zones",
    "mastering-boundaries",
    "ownership:sample-java-repo",
    "ownership:sample-react-repo",
    "jira-conventions",
    "nfr-defaults:sample-java-repo",
    "integration-tests:sample-java-repo",
    "external-system:https://rates.example.test",
}
NOT_OWN_GIT_REPO = {"commit:sample-java-repo", "commit:sample-react-repo"}


def onboard(central, *more):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["onboard", "--allow-sample", "--central", str(central), *more])
    return code, out.getvalue(), err.getvalue()


def report_of(central, *more):
    code, out, err = onboard(central, *more)
    assert code == 0, err
    return json.loads(out)


def tree(path: Path) -> set[str]:
    return {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}


@pytest.fixture
def own_git_central(tmp_path, root):
    """The fixtures copied out so each is its own git repo, which is what a real product looks like."""
    copy_fixture(root / "fixtures/sample-java-repo", tmp_path / "sample-java-repo")
    copy_fixture(root / "fixtures/sample-react-repo", tmp_path / "sample-react-repo")
    for name in ("sample-java-repo", "sample-react-repo"):
        git(tmp_path / name, "init", "-q")
        git(tmp_path / name, "add", "-A")
        git(tmp_path / name, "commit", "-qm", "base")
    central = tmp_path / "central"
    write_project(
        central, [("sample-java-repo", "../sample-java-repo"), ("sample-react-repo", "../sample-react-repo")]
    )
    return central


def test_exactly_the_questions_the_fixture_cannot_answer(own_git_central, backend):
    report = report_of(own_git_central)
    assert {q["id"] for q in report["questions"]} == FIXTURE_QUESTIONS


def test_in_place_fixtures_also_say_they_have_no_commit_of_their_own(fixture_central, backend):
    report = report_of(fixture_central)
    assert {q["id"] for q in report["questions"]} == FIXTURE_QUESTIONS | NOT_OWN_GIT_REPO


def test_every_question_says_what_it_is_and_where_the_answer_goes(own_git_central):
    for question in report_of(own_git_central)["questions"]:
        assert question["ask"] and question["writesTo"] and 1 <= question["gap"] <= 16


def test_seeds_come_from_the_code(own_git_central, backend):
    by_id = {q["id"]: q for q in report_of(own_git_central)["questions"]}
    assert by_id["domain-words"]["seeds"] == ["FeeSummary", "fee_accruals", "fee_schedules"]
    assert "fee below the minimum is raised to the minimum" in by_id["invariants"]["seeds"]
    assert by_id["confirm-aggregates"]["seeds"] == ["FeeAccrual", "FeeSchedule"]
    assert not any("rchitecture" in seed for seed in by_id["invariants"]["seeds"])


def test_stdout_is_json_and_only_listed_files_are_written(fixture_central, root):
    before_fixture = tree(root / "fixtures/sample-java-repo")
    before = tree(fixture_central)
    report_of(fixture_central)
    # onboard runs c4, which writes the workspace and the git-ignored graph (skills/onboard step 2a).
    c4_files = {"docs/architecture/workspace.dsl", ".baton/graph.sqlite"}
    assert tree(fixture_central) - before == set(GENERATED_FILES) | c4_files
    assert tree(root / "fixtures/sample-java-repo") == before_fixture


def test_all_generated_files_validate(fixture_central):
    report_of(fixture_central)
    profile = fixture_central / "profile"
    jsonschema.validate(miniyaml.load_file(str(profile / "dependencies.yaml")), schema("dependencies"))
    jsonschema.validate(miniyaml.load_file(str(profile / "aggregates.yaml")), schema("aggregates"))
    jsonschema.validate(miniyaml.load_file(str(profile / "risk-zones.yaml")), schema("risk-zones"))
    table = (profile / "stack-detected.md").read_text().splitlines()
    assert table[0].split("|")[1].strip() == "repo" and table[0].split("|")[-2].strip() == "build-file sha256"
    assert len([ln for ln in table if ln.startswith("| sample-")]) == 2


def test_interview_batches_are_at_most_eight(own_git_central):
    report = report_of(own_git_central, "--interview")
    assert all(len(batch) <= 8 for batch in report["batches"])
    assert [i for batch in report["batches"] for i in batch] == [q["id"] for q in report["questions"]]
    assert "batches" not in report_of(own_git_central)


def test_an_answer_written_back_is_not_asked_again(own_git_central):
    first = report_of(own_git_central)
    assert "ownership:sample-react-repo" in [q["id"] for q in first["questions"]]
    project = own_git_central / "profile/project.md"
    project.write_text(
        project.read_text() + "\n## Onboard answers\n| id | answer |\n| --- | --- |\n"
        "| `ownership:sample-react-repo` | ui-team |\n| jira-conventions | |\n"
    )
    second = report_of(own_git_central)
    ids = [q["id"] for q in second["questions"]]
    assert "ownership:sample-react-repo" not in ids and second["answered"] == ["ownership:sample-react-repo"]
    assert "jira-conventions" in ids  # a blank answer is not an answer


def test_filled_profile_sections_close_their_questions(own_git_central):
    project = own_git_central / "profile/project.md"
    project.write_text(project.read_text() + "\n## Domain words\nFee, Accrual\n\njira.project: X\n")
    (own_git_central / "profile/domain.md").write_text(
        "## Invariants\n- a fee is never negative\n\n## Mastering\nnone\n\n"
        "## External systems\n| Name | What |\n| --- | --- |\n| Rates | rates.example.test |\n"
    )
    ids = {q["id"] for q in report_of(own_git_central)["questions"]}
    assert not ids & {
        "domain-words",
        "invariants",
        "jira-conventions",
        "mastering-boundaries",
        "external-system:https://rates.example.test",
    }


def test_confirming_the_seeds_closes_their_questions(own_git_central):
    report_of(own_git_central)
    for name in ("aggregates.yaml", "risk-zones.yaml"):
        path = own_git_central / "profile" / name
        path.write_text(path.read_text().replace("confirmed: false", "confirmed: true"))
    ids = {q["id"] for q in report_of(own_git_central)["questions"]}
    assert not ids & {"confirm-aggregates", "confirm-risk-zones"}


def test_a_team_column_answers_ownership(tmp_path):
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/pom.xml").write_text("<project/>")
    central = tmp_path / "central"
    (central / "profile").mkdir(parents=True)
    (central / "profile/project.md").write_text("## Repos\n| Path | Team |\n| --- | --- |\n| ../svc | t |\n")
    assert not [q for q in report_of(central)["questions"] if q["id"].startswith("ownership")]


def test_codeowners_answers_ownership(tmp_path):
    (tmp_path / "svc/.github").mkdir(parents=True)
    (tmp_path / "svc/.github/CODEOWNERS").write_text("* @team\n")
    central = tmp_path / "central"
    write_project(central, [("svc", "../svc")])
    assert not [q for q in report_of(central)["questions"] if q["id"].startswith("ownership")]


# -- c4 --------------------------------------------------------------------------------


def fake_c4(monkeypatch, code, calls):
    def run(args):
        print("noise on stdout")
        calls.append(args.central)
        return code

    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--check", action="store_true")

    module = types.SimpleNamespace(add_arguments=add_arguments, run=run)
    monkeypatch.setitem(sys.modules, "baton.graph", types.ModuleType("baton.graph"))
    monkeypatch.setitem(sys.modules, "baton.graph.c4_cmd", module)


def test_c4_absent_is_reported_not_fatal(fixture_central, monkeypatch):
    monkeypatch.setitem(sys.modules, "baton.graph.c4_cmd", None)
    report = report_of(fixture_central)
    assert report["ran"]["c4"]["status"] == "not built yet"


def test_c4_present_is_run_and_its_stdout_stays_out_of_the_json(fixture_central, monkeypatch):
    calls = []
    fake_c4(monkeypatch, 0, calls)
    report = report_of(fixture_central)
    assert report["ran"]["c4"] == {"status": "ok", "exit": 0} and calls == [str(fixture_central)]


def test_c4_failure_is_exit_1_with_the_questions_still_printed(fixture_central, monkeypatch):
    fake_c4(monkeypatch, 2, [])
    code, out, _ = onboard(fixture_central)
    assert code == 1
    report = json.loads(out)
    assert report["ran"]["c4"] == {"status": "failed", "exit": 2} and report["questions"]


# -- refresh --------------------------------------------------------------------------------


def test_refresh_with_no_change_reports_none(own_git_central, backend):
    report_of(own_git_central)
    refresh = report_of(own_git_central, "--refresh")["refresh"]
    assert refresh == {"changed": False, "files": {}, "edgesAdded": [], "edgesRemoved": [], "commits": {}}


def test_refresh_shows_new_and_removed_edges_and_the_commit_move(own_git_central, tmp_path, backend):
    report_of(own_git_central)
    repo = tmp_path / "sample-java-repo"
    old = git(repo, "rev-parse", "--short=7", "HEAD")
    publisher = repo / "src/main/java/com/example/sample/adapters/messaging/AccrualPublisher.java"
    publisher.write_text(publisher.read_text().replace("fee.accrual.posted", "fee.accrual.renamed"))
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "rename")
    new = git(repo, "rev-parse", "--short=7", "HEAD")
    refresh = report_of(own_git_central, "--refresh")["refresh"]
    prefix = (
        "sample-java-repo: PUBLISHES class:com.example.sample.adapters.messaging.AccrualPublisher -> topic:"
    )
    assert refresh["changed"] is True
    assert refresh["edgesAdded"] == [prefix + "fee.accrual.renamed"]
    assert refresh["edgesRemoved"] == [prefix + "fee.accrual.posted"]
    assert refresh["commits"] == {"sample-java-repo": {"from": old, "to": new}}
    diff = refresh["files"]["profile/dependencies.yaml"]
    assert (
        "-        to: topic:fee.accrual.posted" in diff and "+        to: topic:fee.accrual.renamed" in diff
    )
    assert "generated:" not in diff


def test_refresh_keeps_human_review(own_git_central):
    report_of(own_git_central)
    path = own_git_central / "profile/aggregates.yaml"
    path.write_text(path.read_text().replace("confirmed: false", "confirmed: true"))
    refresh = report_of(own_git_central, "--refresh")["refresh"]
    assert "profile/aggregates.yaml" not in refresh["files"]
    assert "confirmed: true" in path.read_text()


def test_first_run_with_refresh_reports_the_new_files(fixture_central):
    refresh = report_of(fixture_central, "--refresh")["refresh"]
    assert set(refresh["files"]) == set(GENERATED_FILES) | {"docs/architecture/workspace.dsl"}


# -- templates --------------------------------------------------------------------------------


def test_templates_validate(root):
    base = root / "templates/profile"
    jsonschema.validate(miniyaml.load_file(str(base / "dependencies.yaml")), schema("dependencies"))
    jsonschema.validate(miniyaml.load_file(str(base / "aggregates.yaml")), schema("aggregates"))
    jsonschema.validate(miniyaml.load_file(str(base / "risk-zones.yaml")), schema("risk-zones"))
    assert "| repo | build | build cmd |" in (base / "stack-detected.md").read_text()


def test_skill_keeps_the_base_rules_and_uses_the_extractors(root):
    text = (root / "skills/onboard/SKILL.md").read_text()
    for kept in (
        "the human approves every write",
        "A run must never go silent",
        "open a ledger",
        "in batches of at most eight questions, recall not review",
        "Never commit.",
        "## record",
        "git log --diff-filter=DR --name-only",
        "Audit ends smaller or equal.",
    ):
        assert kept in text, kept
    for added in (
        "baton onboard --interview",
        "baton onboard --refresh",
        "## Onboard answers",
        "not built yet",
    ):
        assert added in text, added
