"""W2's real output through the graph worktree's real loader. Skips if neither tree holds that code."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import ROOT, git

W5_TOOLS = ROOT.parent / "baton-W5" / "tools" / "baton"
LAUNCH = """
import sys
import baton
{extra}
from baton import cli
sys.exit(cli.main(sys.argv[1:]))
"""


def _launcher():
    in_tree = (ROOT / "tools/baton/graph/loader.py").is_file()
    if in_tree:
        return LAUNCH.format(extra="")
    if (W5_TOOLS / "graph" / "loader.py").is_file():
        return LAUNCH.format(extra=f"baton.__path__.append({str(W5_TOOLS)!r})")
    pytest.skip("graph code is neither in this tree nor in a sibling baton-W5 checkout")


def baton_run(central, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["PYTHONPATH"] = str(ROOT / "tools")
    return subprocess.run(
        [sys.executable, "-c", _launcher(), *argv, *(["--allow-sample"] if argv[:1] == ("onboard",) else []), "--central", str(central)],  # noqa: E501
        capture_output=True,
        text=True,
        env=env,
        cwd=central,
    )


def test_fixture_output_loads_and_c4_generates(fixture_central):
    done = baton_run(fixture_central, "onboard")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["ran"]["c4"] == {"status": "ok", "exit": 0}
    assert (fixture_central / "docs/architecture/workspace.dsl").is_file()
    load = baton_run(fixture_central, "graph", "load", "--json")
    assert load.returncode == 0, load.stderr
    loaded = json.loads(load.stdout)
    assert loaded["repos"] == ["sample-java-repo", "sample-react-repo"] and loaded["edges"] == 17
    assert baton_run(fixture_central, "c4", "--check").returncode == 0


def _java(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)


@pytest.fixture
def two_repos(tmp_path):
    provider, caller = tmp_path / "provider", tmp_path / "caller"
    _java(provider, "pom.xml", "<project/>")
    _java(caller, "pom.xml", "<project/>")
    _java(
        provider,
        "src/main/java/com/p/Api.java",
        """package com.p;
@RestController
public class Api {
    private final KafkaTemplate<String, String> kafka = null;
    private final MongoTemplate mongo = null;
    @GetMapping("/v1/rates/{currency}")
    public String rate(String currency) { return "1"; }
    public void change(String r) { kafka.send("rates.changed", r); mongo.insert(r, "rates"); }
}
""",
    )
    _java(
        caller,
        "src/main/java/com/c/Client.java",
        """package com.c;
@Component
public class Client {
    private final RestClient rest;
    private final MongoTemplate mongo = null;
    public Client(RestClient.Builder b, @Value("${rates.base-url}") String baseUrl) {
        this.rest = b.baseUrl(baseUrl).build();
    }
    public String get(String c) { return rest.get().uri("/v1/rates/{currency}", c).retrieve().body(); }
    @KafkaListener(topics = "rates.changed")
    public void on(String m) { mongo.find(m, String.class, "rates"); }
}
""",
    )
    _java(caller, "src/main/resources/application.yml", "rates:\n  base-url: https://rates.example.test\n")
    for repo in (provider, caller):
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", "x")
    central = tmp_path / "central"
    (central / "profile").mkdir(parents=True)
    (central / "profile/project.md").write_text(
        "## Repos\n| Path | What it is | Team |\n| --- | --- | --- |\n"
        "| `../provider` | p | a |\n| `../caller` | c | b |\n"
    )
    assert baton_run(central, "onboard").returncode == 0
    return central, tmp_path


def _impact(central, tmp_path, node):
    diff = tmp_path / "design.txt"
    diff.write_text(node + "\n")
    done = baton_run(central, "impact", "--repo", "provider", "--diff", str(diff), "--json")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.parametrize("node", ["topic:rates.changed", "collection:rates"])
def test_topics_and_collections_join_across_repos(two_repos, node):
    central, tmp_path = two_repos
    report = _impact(central, tmp_path, node)
    assert [i["repo"] for i in report["impacted"]] == ["caller"]
    assert report["impacted"][0]["file"] == "src/main/java/com/c/Client.java" and report["unknownEdges"] == []


def test_a_rest_call_joins_across_repos(two_repos):
    central, tmp_path = two_repos
    report = _impact(central, tmp_path, "endpoint:GET /v1/rates/{currency}")
    assert [i["repo"] for i in report["impacted"]] == ["caller"]


def test_rest_call_join_clears_the_false_unknowns_and_links_the_containers(two_repos):
    central, tmp_path = two_repos
    report = _impact(central, tmp_path, "endpoint:GET /v1/rates/{currency}")
    assert report["impacted"][0]["file"] == "src/main/java/com/c/Client.java"
    assert report["unknownEdges"] == []
    assert "Unknown provider" not in (central / "docs/architecture/workspace.dsl").read_text()


def test_a_react_call_reaches_the_java_service_through_the_graph(fixture_central):
    assert baton_run(fixture_central, "onboard").returncode == 0
    assert baton_run(fixture_central, "graph", "load").returncode == 0
    connection = sqlite3.connect(fixture_central / ".baton/graph.sqlite")
    tables = [r[0] for r in connection.execute("select name from sqlite_master where type='table'")]
    assert "edges" in tables
    rows = connection.execute(
        "select repo, kind from edges where dst = 'endpoint:GET /api/v1/fees/{accountRef}'"
    ).fetchall()
    assert {("sample-react-repo", "CALLS_ENDPOINT"), ("sample-java-repo", "EXPOSES")} <= set(rows)
