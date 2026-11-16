import json
import os
import subprocess
from pathlib import Path

import pytest
from baton.graph.diffing import (
    DiffError,
    changes_from_unified,
    class_id_from_path,
    git_diff,
    parse_file_list,
    parse_unified,
)
from baton.graph.loader import load_into
from baton.graph.model import Edge
from baton.graph.sqlite_store import SqliteStore

ACCOUNTS_READER_A = {
    "repo": "account-service",
    "via": "collection:accounts",
    "file": "src/main/java/com/sample/account/AccountRepository.java",
    "lines": "14",
    "team": "accounts-team",
}
ACCOUNTS_READER_S = {
    "repo": "statement-batch",
    "via": "collection:accounts",
    "file": "src/main/java/com/sample/statement/AccountReader.java",
    "lines": "41-58",
    "team": "statements-team",
}
# account-service is reached at depth 1, so what it exposes is walked at depth 2.
ENDPOINT_CALLER = {
    "repo": "statement-batch",
    "via": "endpoint:GET /api/v1/accounts/{id}",
    "file": "src/main/java/com/sample/statement/AccountClient.java",
    "lines": "52",
    "team": "statements-team",
}


def _impact(cli, central, validate, name, repo="ledger-loader"):
    code, out, err = cli(
        "impact",
        "--central",
        str(central),
        "--repo",
        repo,
        "--diff",
        str(central / "inputs" / name),
        "--json",
    )
    assert code == 0, err
    report = json.loads(out)
    validate(report, "impact")
    expected = central / "expected" / (Path(name).stem + ".json")
    assert report == json.loads(expected.read_text())
    return report


def test_writer_change_returns_exact_file_lines(cli, central, validate):
    report = _impact(cli, central, validate, "writer-changed.diff")
    assert report["changedSymbols"] == ["class:com.sample.loader.AccountWriter"]
    assert report["impacted"] == [
        {**ACCOUNTS_READER_A, "breaking": False},
        {**ACCOUNTS_READER_S, "breaking": False},
        {**ENDPOINT_CALLER, "breaking": False},
    ]
    # Depth 2: statement-batch publishes statement.ready and ledger-loader, the source, consumes it: in graph.
    assert report["unknownEdges"] == []


def test_planted_unknown_edge(cli, central, validate):
    report = _impact(cli, central, validate, "settlement-changed.diff")
    assert report["impacted"] == []
    assert report["unknownEdges"] == ["queue:SETTLEMENT.IN has no known consumer in graph"]


def test_removed_field_is_breaking_and_named_like_the_contract(cli, central, validate):
    report = _impact(cli, central, validate, "field-removed.diff")
    assert report["changedSymbols"] == [
        "AccountDoc.billingFamily",
        "AccountDoc.billingGroup",
        "AccountDoc.nickname",
    ]
    assert report["impacted"][0] == {**ACCOUNTS_READER_A, "breaking": True}
    assert all(row["breaking"] for row in report["impacted"])


def test_endpoint_signature_change_is_breaking_and_reaches_depth_two(cli, central, validate):
    report = _impact(cli, central, validate, "endpoint-signature.diff", repo="account-service")
    assert report["changedSymbols"] == [
        "class:com.sample.account.AccountController",
        "endpoint:GET /api/v1/accounts/{id}",
    ]
    assert report["impacted"][1] == {**ENDPOINT_CALLER, "breaking": True}
    # statement-batch -> statement.ready -> ledger-loader is depth 2; ledger-loader's outputs are depth 3,
    # so its unconsumed SETTLEMENT.IN is not reported.
    assert {"repo": "ledger-loader", "via": "topic:statement.ready", "breaking": True} == {
        k: report["impacted"][0][k] for k in ("repo", "via", "breaking")
    }
    assert report["impacted"][0]["file"].endswith("StatementReadyListener.java")
    assert report["impacted"][0]["lines"] == "12"
    assert report["unknownEdges"] == []


def test_shared_topic_and_file_via_design_list(cli, central, validate):
    (central / "list.txt").write_text(
        "src/main/java/com/sample/loader/AccountEventPublisher.java\n"
        "src/main/java/com/sample/loader/AccountExtractWriter.java\n"
    )
    code, out, _ = cli(
        "impact",
        "--central",
        str(central),
        "--repo",
        "ledger-loader",
        "--diff",
        str(central / "list.txt"),
        "--json",
    )
    assert code == 0
    report = json.loads(out)
    validate(report, "impact")
    direct = {(r["repo"], r["via"], r["file"].rsplit("/", 1)[-1], r["lines"]) for r in report["impacted"]}
    assert ("account-service", "topic:account.events", "AccountEventListener.java", "22") in direct
    assert ("statement-batch", "topic:account.events", "StatementListener.java", "18") in direct
    assert ("statement-batch", "file:outbound/accounts-*.csv", "AccountExtractReader.java", "25") in direct


def test_design_file_list_bullets_other_repos_and_unknown_paths(cli, central, validate):
    report = _impact(cli, central, validate, "design-files.txt")
    assert report["changedSymbols"] == [
        "class:com.sample.loader.AccountEventPublisher",
        "class:com.sample.loader.NewThing",
    ]
    assert {r["via"] for r in report["impacted"]} >= {"topic:account.events"}


def test_design_list_declares_breaking_and_resources(cli, central, validate):
    (central / "l.txt").write_text("breaking: AccountDoc.status\ntopic:account.events\n")
    code, out, _ = cli(
        "impact",
        "--central",
        str(central),
        "--repo",
        "ledger-loader",
        "--diff",
        str(central / "l.txt"),
        "--json",
    )
    report = json.loads(out)
    validate(report, "impact")
    assert code == 0
    assert (
        "AccountDoc.status" in report["changedSymbols"] and "topic:account.events" in report["changedSymbols"]
    )
    by_via = {(r["repo"], r["via"]): r["breaking"] for r in report["impacted"]}
    assert by_via[("account-service", "collection:accounts")] is True
    assert by_via[("account-service", "topic:account.events")] is False


def test_empty_list_gives_empty_report(cli, central, validate):
    (central / "empty.txt").write_text("# nothing yet\n")
    code, out, _ = cli(
        "impact",
        "--central",
        str(central),
        "--repo",
        "ledger-loader",
        "--diff",
        str(central / "empty.txt"),
        "--json",
    )
    report = json.loads(out)
    validate(report, "impact")
    assert code == 0
    assert (report["changedSymbols"], report["impacted"], report["unknownEdges"]) == ([], [], [])


def _git(cwd, *args):
    # Tests run inside the pre-commit hook too, where GIT_DIR and GIT_INDEX_FILE name the real repository.
    # Without this scrub `git init` and `git add` act on that repository instead of the temporary one.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=env,
    )


def test_git_diff_ignores_inherited_git_environment(monkeypatch, repo_checkout, tmp_path):
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "not-a-repo"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "not-an-index"))
    assert "AccountDoc.java" in git_diff(repo_checkout, "HEAD~1")


@pytest.fixture
def repo_checkout(central):
    repo = central.parent / "ledger-loader"
    source = repo / "src/main/java/com/sample/loader"
    source.mkdir(parents=True)
    (source / "AccountDoc.java").write_text(
        "package com.sample.loader;\npublic class AccountDoc {\n"
        "    private String status;\n    private int age;\n}\n"
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (source / "AccountDoc.java").write_text(
        "package com.sample.loader;\npublic class AccountDoc {\n    private int age;\n}\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "drop status")
    return repo


@pytest.mark.parametrize("ref", ["HEAD~1", "HEAD~1..HEAD", "main~1...main"])
def test_git_ref_is_diffed_in_the_sibling_repo(cli, central, validate, repo_checkout, ref):
    code, out, err = cli(
        "impact", "--central", str(central), "--repo", "ledger-loader", "--diff", ref, "--json"
    )
    assert code == 0, err
    report = json.loads(out)
    validate(report, "impact")
    assert report["changedSymbols"] == ["AccountDoc.status"]
    assert report["impacted"][0]["breaking"] is True


def test_bad_ref_missing_repo_and_option_injection_exit_2(cli, central, repo_checkout, tmp_path):
    base = ["impact", "--central", str(central), "--repo", "ledger-loader"]
    assert cli(*base, "--diff", "no-such-ref")[0] == 2
    assert cli("impact", "--central", str(central), "--repo", "account-service", "--diff", "HEAD")[0] == 2
    assert cli("impact", "--central", str(central), "--repo", "nope", "--diff", "HEAD")[0] == 2
    assert cli("impact", "--central", str(tmp_path), "--repo", "x", "--diff", "HEAD")[0] == 2
    with pytest.raises(DiffError):
        git_diff(repo_checkout, "--output=/tmp/x")


def test_out_writes_the_file_and_text_mode_prints_file_lines(cli, central, validate, tmp_path):
    out_file = tmp_path / "docs/qa/F-1/S-1-impact.json"
    code, out, _ = cli(
        "impact",
        "--central",
        str(central),
        "--repo",
        "ledger-loader",
        "--diff",
        str(central / "inputs/settlement-changed.diff"),
        "--out",
        str(out_file),
    )
    assert code == 0 and "queue:SETTLEMENT.IN" in out
    validate(json.loads(out_file.read_text()), "impact")


def _chain(n):
    """r0 -> r1 -> ... -> r(n-1) through topics t0, t1, ..."""
    store = SqliteStore()
    edges = []
    for i in range(n):
        edges.append(
            Edge("PUBLISHES", f"class:p.P{i}", f"topic:t{i}", f"r{i}", f"P{i}.java", 1, "kafka-template", "c")
        )
        if i:
            edges.append(
                Edge(
                    "CONSUMES",
                    f"class:p.C{i}",
                    f"topic:t{i - 1}",
                    f"r{i}",
                    f"C{i}.java",
                    2,
                    "kafka-listener",
                    "c",
                )
            )
    store.upsert_nodes(sorted({n for e in edges for n in (e.src, e.dst)}))
    store.upsert_edges(edges)
    return store


def test_walk_stops_at_depth_two():
    report = _chain(5).impact(["class:p.P0"], source_repo="r0")
    assert [row["repo"] for row in report["impacted"]] == ["r1", "r2"]
    assert report["unknownEdges"] == []


def test_unknown_from_a_depth_one_repo_is_reported_from_depth_two_is_not():
    assert _chain(2).impact(["class:p.P0"], source_repo="r0")["unknownEdges"] == [
        "topic:t1 has no known consumer in graph"
    ]
    assert _chain(3).impact(["class:p.P0"], source_repo="r0")["unknownEdges"] == []


def test_cycle_terminates_and_never_reports_the_source():
    store = _chain(2)
    store.upsert_edges(
        [Edge("CONSUMES", "class:p.C0", "topic:t1", "r0", "C0.java", 3, "kafka-listener", "c")]
    )
    report = store.impact(["class:p.P0"], source_repo="r0")
    assert [row["repo"] for row in report["impacted"]] == ["r1"]


def test_consumer_side_with_no_producer_is_unknown(central):
    store = SqliteStore()
    edges = [
        Edge(
            "CALLS_ENDPOINT",
            "class:a.Client",
            "endpoint:${base}/x",
            "r",
            "C.java",
            4,
            "rest-client-base-url",
            "c",
        )
    ]
    store.upsert_nodes(["class:a.Client", "endpoint:${base}/x"])
    store.upsert_edges(edges)
    assert store.impact(["class:a.Client"], source_repo="r")["unknownEdges"] == [
        "endpoint:${base}/x has no known provider in graph"
    ]


def test_same_class_name_in_another_repo_is_not_seeded():
    store = SqliteStore()
    edges = [
        Edge("PUBLISHES", "class:a.X", "topic:mine", "r1", "X.java", 1, "kafka-template", "c"),
        Edge("PUBLISHES", "class:a.X", "topic:theirs", "r2", "X.java", 1, "kafka-template", "c"),
    ]
    store.upsert_nodes(["class:a.X", "topic:mine", "topic:theirs"])
    store.upsert_edges(edges)
    assert store.impact(["class:a.X"], source_repo="r1")["unknownEdges"] == [
        "topic:mine has no known consumer in graph"
    ]


def test_parse_unified_tracks_hunks_and_ignores_dashes_inside():
    text = (
        "--- a/x/A.java\n+++ b/x/A.java\n@@ -3,2 +3 @@\n--- not a header\n-other\n+new\n"
        "--- a/x/B.java\n+++ /dev/null\n@@ -7 +0,0 @@\n-gone\n"
    )
    files = parse_unified(text)
    assert [f.path for f in files] == ["x/A.java", "x/B.java"]
    assert files[0].removed == [(3, "-- not a header"), (4, "other")]
    assert files[1].removed == [(7, "gone")]


def _java_diff(path, removed=(), added=()):
    body = "".join(f"-{r}\n" for r in removed) + "".join(f"+{a}\n" for a in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -1,{len(removed)} +1,{len(added)} @@\n{body}"


@pytest.mark.parametrize(
    "removed, added, breaking",
    [
        (["    private String a;"], [], True),
        (["    private String a;"], ["    private String b;"], True),
        (["    private String a;"], ["    private Integer a;"], False),
        (["    private String a;"], ["  private String a;"], False),
        (['    private static final String A = "x";'], [], False),
        (["    String local = compute();"], [], False),
        (["public record R(String a, int b) {"], ["public record R(String a) {"], True),
        (["public record R(String a) {"], ["public record R(String a, int b) {"], False),
    ],
)
def test_field_rules(removed, added, breaking):
    store = SqliteStore()
    changes = changes_from_unified(_java_diff("src/main/java/x/R.java", removed, added), store, "r")
    assert ("class:x.R" in changes.breaking) is breaking


def test_mapping_removed_and_topic_literal_renamed_are_breaking(central, store):
    path = "src/main/java/com/sample/account/AccountController.java"
    changes = changes_from_unified(
        _java_diff(path, ['    @GetMapping("/{id}")'], ['    @GetMapping("/by-id/{id}")']),
        store,
        "account-service",
    )
    assert "endpoint:GET /api/v1/accounts/{id}" in changes.breaking
    path = "src/main/java/com/sample/loader/AccountEventPublisher.java"
    changes = changes_from_unified(
        _java_diff(path, ['send("account.events", e);'], ['send("account.v2", e);']), store, "ledger-loader"
    )
    assert "topic:account.events" in changes.breaking


def test_non_source_paths_derive_nothing():
    assert class_id_from_path("src/test/java/a/ATest.java") is None
    assert class_id_from_path("README.md") is None
    assert class_id_from_path("mod/src/main/java/a/B.java") == "class:a.B"


def test_parse_file_list_notes_other_repo():
    paths, ids, breaking, ignored = parse_file_list(
        "- ../r/a/B.java — why\n../other/C.java\n./d/E.java\nqueue:Q\nbreaking: X.y\n", "r"
    )
    assert (paths, ids, breaking, ignored) == (
        ["a/B.java", "d/E.java"],
        ["queue:Q"],
        ["X.y"],
        ["../other/C.java"],
    )


def test_load_uses_the_same_rows_for_a_rerun(central):
    first = SqliteStore()
    load_into(first, central)
    assert first.impact(["collection:accounts"], source_repo="ledger-loader") == first.impact(
        ["collection:accounts"], source_repo="ledger-loader"
    )
