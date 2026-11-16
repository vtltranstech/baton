"""The acceptance bar: 100 % of fixtures/*/EXPECTED.json, under both parser back-ends."""

import io
import json
from contextlib import redirect_stdout

import jsonschema
from baton import cli, miniyaml
from conftest import schema, write_project


def run_cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def edge_keys(edges):
    return sorted(
        (
            e["kind"],
            e["from"],
            e["to"],
            e["provenance"]["file"],
            e["provenance"]["line"],
            e["provenance"]["extractor"],
        )
        for e in edges
    )


def expected(root, name):
    return json.loads((root / "fixtures" / name / "EXPECTED.json").read_text())


def check_repo(entry, spec):
    assert edge_keys(entry["edges"]) == edge_keys(spec["edges"])
    assert sorted(entry["unresolved"]) == sorted(spec["unresolved"])
    assert sorted(entry["collections"], key=lambda c: c["name"]) == sorted(
        spec["collections"], key=lambda c: c["name"]
    )


def check_stack(row, spec):
    for key, value in spec["stack"].items():
        assert row.get(key) == value, key
    assert row.get("layout", {}) == spec["layout"]


def test_java_and_react_fixtures(fixture_central, root, backend):
    central = str(fixture_central)
    code, out = run_cli("extract", "--central", central, "--json")
    assert code == 0
    document = json.loads(out)
    jsonschema.validate(document, schema("dependencies"))
    by_repo = {r["repo"]: r for r in document["repos"]}
    java, react = expected(root, "sample-java-repo"), expected(root, "sample-react-repo")
    check_repo(by_repo["sample-java-repo"], java)
    check_repo(by_repo["sample-react-repo"], react)

    written = miniyaml.load_file(str(fixture_central / "profile" / "dependencies.yaml"))
    jsonschema.validate(written, schema("dependencies"))
    assert {r["repo"]: edge_keys(r["edges"]) for r in written["repos"]} == {
        k: edge_keys(v["edges"]) for k, v in by_repo.items()
    }

    aggregates = miniyaml.load_file(str(fixture_central / "profile" / "aggregates.yaml"))
    jsonschema.validate(aggregates, schema("aggregates"))
    assert sorted(aggregates["aggregates"], key=lambda a: a["name"]) == java["aggregates"]

    zones = miniyaml.load_file(str(fixture_central / "profile" / "risk-zones.yaml"))
    jsonschema.validate(zones, schema("risk-zones"))
    assert {z["name"]: sorted(z["paths"]) for z in zones["zones"]} == {
        s["reason"]: sorted(s["files"]) for s in java["riskZoneSeeds"]
    }
    assert all(z["confirmed"] is False and z["cap"] == 50 for z in zones["zones"])

    code, out = run_cli("extract-stack", "--central", central, "--json")
    assert code == 0
    stack = json.loads(out)
    jsonschema.validate(stack, schema("stack-detected"))
    rows = {r["repo"]: r for r in stack["repos"]}
    check_stack(rows["sample-java-repo"], java)
    check_stack(rows["sample-react-repo"], react)


def test_gradle_kts_variant(tmp_path, root, backend):
    variant = expected(root, "sample-java-repo")["variants"][0]
    central = tmp_path / "central"
    write_project(central, [(variant["repo"], str(root / "fixtures/sample-java-repo" / variant["path"]))])
    code, out = run_cli("extract", "--central", str(central), "--json")
    assert code == 0
    check_repo(json.loads(out)["repos"][0], variant)
    aggregates = miniyaml.load_file(str(central / "profile" / "aggregates.yaml"))
    assert aggregates["aggregates"] == variant["aggregates"]
    code, out = run_cli("extract-stack", "--central", str(central), "--json")
    check_stack(json.loads(out)["repos"][0], variant)


def test_backend_is_recorded_per_file(fixture_central, backend):
    code, out = run_cli("extract", "--central", str(fixture_central), "--json")
    assert code == 0
    parser = {r["repo"]: r for r in json.loads(out)["repos"]}["sample-java-repo"]["parser"]
    used = "regex" if backend == "no-javaparser" else backend
    assert parser[used] == 20 and parser["fallback"] == []
    assert parser["unavailable"] is (backend == "no-javaparser")
    assert parser["treesitter"] + parser["javaparser"] + parser["regex"] == 20
