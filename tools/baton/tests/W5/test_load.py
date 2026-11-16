import pytest
from baton import miniyaml
from baton.graph.loader import GRAPH_FILE, LoadError, load_into, open_for_reading, parse_dependencies
from baton.graph.model import Edge
from baton.graph.sqlite_store import SqliteStore


def test_fixture_conforms_to_the_schema(central, validate):
    validate(miniyaml.load_file(str(central / "profile/dependencies.yaml")), "dependencies")


def test_load_recovers_every_edge_with_provenance(store):
    edges = store.edges()
    assert len([e for e in edges if e.kind != "OWNED_BY"]) == 16
    edge = next(e for e in edges if e.src.endswith("account.AccountRepository"))
    assert edge.provenance() == {
        "repo": "account-service",
        "file": "src/main/java/com/sample/account/AccountRepository.java",
        "line": 14,
        "extractor": "spring-data-generic",
        "commit": "b2c3d4e",
    }


def test_reload_is_idempotent(central, cli):
    path = central / GRAPH_FILE
    assert cli("graph", "load", "--central", str(central))[0] == 0
    first = SqliteStore(path).dump()
    assert cli("graph", "load", "--central", str(central))[0] == 0
    second = SqliteStore(path).dump()
    assert first == second
    assert len(first["edges"]) == 19  # 16 + 3 OWNED_BY


def test_edge_removed_from_the_code_leaves_the_graph(central, store):
    deps = central / "profile/dependencies.yaml"
    lines = deps.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if "class:com.sample.account.AccountRepository" in line)
    del lines[index - 1 : index + 3]
    deps.write_text("\n".join(lines) + "\n")
    load_into(store, central)
    assert not [e for e in store.edges() if "AccountRepository" in e.src]
    assert ("class:com.sample.account.AccountRepository", "Class") not in store.dump()["nodes"]


def test_repo_absent_from_a_partial_file_is_kept(central, store):
    deps = central / "profile/dependencies.yaml"
    deps.write_text("generated: x\nrepos:\n  - repo: ledger-loader\n    commit: a\n    edges:\n")
    load_into(store, central)
    assert "account-service" in store.repos()
    assert not [e for e in store.edges("ledger-loader") if e.kind != "OWNED_BY"]


@pytest.mark.parametrize(
    "provenance, reason",
    [
        ("", "provenance is mandatory"),
        ("provenance: {line: 3, extractor: x}", "provenance.file"),
        ("provenance: {file: a.java, extractor: x}", "provenance.line"),
        ("provenance: {file: a.java, line: 3}", "provenance.extractor"),
    ],
)
def test_edge_without_provenance_is_rejected_and_nothing_changes(central, cli, provenance, reason):
    assert cli("graph", "load", "--central", str(central))[0] == 0
    before = SqliteStore(central / GRAPH_FILE).dump()
    (central / "profile/dependencies.yaml").write_text(
        "generated: x\nrepos:\n  - repo: r\n    commit: abc\n    edges:\n"
        "      - kind: PUBLISHES\n        from: class:a.B\n        to: topic:t\n"
        f"        {provenance}\n"
    )
    code, _, err = cli("graph", "load", "--central", str(central))
    assert code == 1 and reason in err
    assert SqliteStore(central / GRAPH_FILE).dump() == before


def test_missing_repo_commit_is_rejected_even_with_good_edge_fields():
    document = {
        "repos": [
            {
                "repo": "r",
                "edges": [
                    {
                        "kind": "PUBLISHES",
                        "from": "class:a.B",
                        "to": "topic:t",
                        "provenance": {"file": "f", "line": 1, "extractor": "x"},
                    }
                ],
            }
        ]
    }
    with pytest.raises(LoadError) as caught:
        parse_dependencies(document)
    assert any("commit" in p for p in caught.value.problems)


@pytest.mark.parametrize("field, value", [("kind", "NOPE"), ("to", "kafka:t"), ("from", "a.B")])
def test_off_contract_edge_is_rejected(field, value):
    edge = {
        "kind": "PUBLISHES",
        "from": "class:a.B",
        "to": "topic:t",
        "provenance": {"file": "f", "line": 1, "extractor": "x"},
    }
    edge[field] = value
    with pytest.raises(LoadError):
        parse_dependencies({"repos": [{"repo": "r", "commit": "c", "edges": [edge]}]})


def test_cli_missing_input_and_age_exit_2(tmp_path, central, cli):
    assert cli("graph", "load", "--central", str(tmp_path))[0] == 2
    code, _, err = cli("graph", "load", "--store", "age", "--central", str(central))
    assert code == 2 and "interface only" in err


def test_cli_accepts_shared_flags_before_and_after_the_verb(central, cli):
    assert cli("graph", "--central", str(central), "load")[0] == 0
    code, out, _ = cli("graph", "load", "--central", str(central), "--json")
    assert code == 0 and '"repos"' in out


def test_age_store_is_only_an_interface():
    from baton.graph.age_store import AgeStore

    with pytest.raises(NotImplementedError):
        AgeStore()


def test_store_primitives(store):
    assert [e.repo for e in store.neighbours("topic:account.events", ["CONSUMES"], "in")] == [
        "account-service",
        "statement-batch",
    ]
    assert (
        store.neighbours("class:com.sample.loader.AccountWriter", None, "out")[0].dst == "collection:accounts"
    )
    assert isinstance(store.edges()[0], Edge)
    assert store.team_of("ledger-loader") == "ledger-team"
    with pytest.raises(ValueError):
        store.neighbours("x", None, "sideways")


def test_stale_graph_is_refreshed_and_read_only_open_does_not_write(central, cli):
    assert cli("graph", "load", "--central", str(central))[0] == 0
    graph = central / GRAPH_FILE
    deps = central / "profile/dependencies.yaml"
    deps.write_text(deps.read_text() + "  - repo: extra\n    commit: z\n    edges:\n")
    before = graph.read_bytes()
    memory = open_for_reading(central, writable=False)
    assert graph.read_bytes() == before
    memory.close()
    writable = open_for_reading(central)
    assert writable.get_meta("dependencies_sha256")
    writable.close()
    assert graph.read_bytes() != before
