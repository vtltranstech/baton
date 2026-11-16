import json
import os
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

PYTHON = sys.executable
ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / "tools/baton/graph/mcp_server.py"


class Client:
    def __init__(self, central, env_extra=None):
        env = {**os.environ, "BATON_CENTRAL": str(central), **(env_extra or {})}
        self.process = subprocess.Popen(
            [PYTHON, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd="/",
        )
        self.next_id = 0

    def send(self, method, params=None, notification=False):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            self.next_id += 1
            message["id"] = self.next_id
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        if notification:
            return None
        reply = json.loads(self.process.stdout.readline())
        assert reply["jsonrpc"] == "2.0" and reply["id"] == message["id"]
        return reply

    def call(self, name, **arguments):
        return self.send("tools/call", {"name": name, "arguments": arguments})["result"]

    def close(self):
        self.process.stdin.close()
        code = self.process.wait(timeout=10)
        err = self.process.stderr.read()
        self.process.stdout.close()
        self.process.stderr.close()
        return code, err


@pytest.fixture
def client(central):
    instance = Client(central)
    yield instance
    assert instance.close() == (0, "")


def test_initialize_list_and_call_over_stdio(client, central, validate):
    init = client.send(
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
    )["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["name"] == "baton-graph" and "tools" in init["capabilities"]
    assert client.send("notifications/initialized", notification=True) is None
    tools = client.send("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == [
        "graph.impact",
        "graph.callers",
        "graph.context",
        "graph.ir",
        "graph.find",
        "graph.collections",
    ]
    for tool in tools:
        assert re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", tool["name"])  # SEP-986 character set
        assert tool["annotations"]["readOnlyHint"] is True
        jsonschema.Draft202012Validator.check_schema(tool["inputSchema"])
    result = client.call(
        "graph.impact", repo="ledger-loader", diff_ref=str(central / "inputs/settlement-changed.diff")
    )
    assert result["isError"] is False
    report = json.loads(result["content"][0]["text"])
    validate(report, "impact")
    assert report == json.loads((central / "expected/settlement-changed.json").read_text())
    assert result["structuredContent"] == report


def test_impact_matches_the_cli_for_the_collection_case(client, central):
    result = client.call(
        "graph.impact", repo="ledger-loader", diff_ref=str(central / "inputs/writer-changed.diff")
    )
    assert result["structuredContent"] == json.loads((central / "expected/writer-changed.json").read_text())


def test_callers_and_collections(client):
    callers = client.call("graph.callers", id="collection:accounts")["structuredContent"]["callers"]
    assert {"class:com.sample.statement.AccountReader"} <= {c["from"] for c in callers}
    assert all(set(c["provenance"]) == {"repo", "file", "line", "extractor", "commit"} for c in callers)
    rows = client.call("graph.collections", repo="statement-batch")["structuredContent"]["collections"]
    assert [r["collection"] for r in rows] == ["accounts"]
    assert [e["line"] for e in rows[0]["edges"]] == [41, 58]


def test_errors_are_protocol_shaped(client):
    assert client.send("nope/nope")["error"]["code"] == -32601
    assert client.send("tools/call", {"name": "graph.drop", "arguments": {}})["error"]["code"] == -32602
    missing = client.call("graph.callers")
    assert missing["isError"] is True and "id" in missing["content"][0]["text"]
    unknown = client.call("graph.collections", repo="nope")
    assert unknown["isError"] is True
    assert client.send("ping")["result"] == {}


def test_server_writes_nothing_to_disk(central):
    instance = Client(central)
    instance.send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert instance.call("graph.callers", id="topic:account.events")["isError"] is False
    assert instance.close() == (0, "")
    assert not (central / ".baton").exists()


def test_parse_error_keeps_the_server_alive(client):
    client.process.stdin.write("not json\n")
    client.process.stdin.flush()
    assert json.loads(client.process.stdout.readline())["error"]["code"] == -32700
    assert client.send("ping")["result"] == {}


def test_mcp_json_is_plugin_aware():
    config = json.loads((ROOT / ".mcp.json").read_text())
    server = config["mcpServers"]["graph"]
    assert server["command"] == "python3"
    assert server["args"] == ["${CLAUDE_PLUGIN_ROOT}/tools/baton/graph/mcp_server.py"]
    expanded = server["args"][0].replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
    assert Path(expanded) == SERVER and SERVER.is_file()
