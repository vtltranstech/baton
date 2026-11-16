"""Read-only MCP server (stdio JSON-RPC) over the graph: graph.impact, graph.callers, graph.collections,
graph.context, graph.ir, graph.find."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Run as a script: drop the script's own directory and make the `baton` package importable.
    sys.path[0] = str(Path(__file__).resolve().parents[2])

from baton.graph.diffing import DiffError, compute_impact  # noqa: E402
from baton.graph.loader import LoadError, MissingInput, open_for_reading  # noqa: E402

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}


def _tool(name: str, description: str, properties: dict) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {key: {"type": "string", "description": text} for key, text in properties.items()},
            "required": list(properties),
            "additionalProperties": False,
        },
        "annotations": _READ_ONLY,
    }


TOOLS = [
    _tool(
        "graph.impact",
        "Blast radius of a change: impact.json (impacted file:line per repo, unknown edges, breaking).",
        {
            "repo": "the repo the change is in",
            "diff_ref": "unified diff or design file list path, or a git ref / range diffed in ../<repo>",
        },
    ),
    _tool(
        "graph.callers",
        "Every edge pointing at a node, with provenance. Ids per contract: class:<fqcn>, collection:<name>, "
        "endpoint:<METHOD> <path>, topic:<name>, queue:<name>, file:<pattern>, job:<name>.",
        {"id": "the node id"},
    ),
    _tool(
        "graph.context",
        "A compact card read from the code's AST: a class (simple name or FQCN), Class#method, or a "
        "resource id. Line ranges, signatures, what it calls, who calls it, data it reads and writes, "
        "tests that name it, and the entry points that reach it. Read this before opening source files.",
        {"name": "class, Class#method, or a resource id such as collection:<name>"},
    ),
    _tool(
        "graph.ir",
        "The code as operations and effects (the IR), the cheapest way to read code. Empty name: one line "
        "per unit. A unit, a class, Class#method or a resource id: its operations with line ranges, the "
        "calls they make, the data they read and write (also through calls), the events they emit, who calls "
        "them and the entry points that reach them. Read this before opening any source file.",
        {"name": "empty, a unit, a class, Class#method, or a resource id such as collection:<name>"},
    ),
    _tool(
        "graph.find",
        "The operations, classes and resources whose names match some words, each with file:lines and its "
        "effects. Use it to find where a story lands instead of grepping.",
        {"words": "words from the story, e.g. 'cancel order refund payment'"},
    ),
    _tool(
        "graph.collections",
        "Collections a repo touches, each with the reading and writing classes and file:line.",
        {"repo": "the repo name"},
    ),
]


def central_dir() -> str:
    return os.environ.get("BATON_CENTRAL") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


class ToolError(Exception):
    pass


def _call(name: str, arguments: dict, central: str):
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None:
        raise KeyError(name)
    for key in tool["inputSchema"]["required"]:
        if not isinstance(arguments.get(key), str) or (not arguments[key] and name != "graph.ir"):
            raise ToolError(f"{name}: argument {key} is required")
    if name in ("graph.ir", "graph.find"):
        from baton.ir import cmd as ir_cmd
        from baton.ir import render

        ir = ir_cmd.build(Path(central))
        if name == "graph.find":
            hits = render.find(ir, arguments["words"])
            if not hits:
                raise ToolError(f"nothing matches {arguments['words']!r}")
            return {"text": "\n".join(line for _, _, line in hits), "hits": [i for _, i, _ in hits]}
        text, problems = ir_cmd.show(ir, arguments["name"].strip())
        if problems:
            raise ToolError("; ".join(problems))
        return {"text": text}
    if name == "graph.context":
        from baton.diagram.context import card
        from baton.diagram.world import load_world

        result, problems = card(load_world(Path(central)), arguments["name"])
        if problems:
            raise ToolError("; ".join(problems))
        return {"text": result["text"], **result["data"]}
    store = open_for_reading(central, writable=False)
    try:
        if name == "graph.callers":
            return {"id": arguments["id"], "callers": store.callers(arguments["id"])}
        repo = arguments["repo"]
        if repo not in store.repos():
            raise ToolError(f"repo {repo} is not in the graph")
        if name == "graph.collections":
            return {"repo": repo, "collections": store.collections(repo)}
        report, _notes = compute_impact(store, repo, arguments["diff_ref"], central)
        return report
    finally:
        store.close()


def _tool_result(payload) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
        "structuredContent": payload,
        "isError": False,
    }


def handle(request: dict, central: str) -> dict | None:
    method, request_id = request.get("method"), request.get("id")
    if "id" not in request:
        return None  # a notification
    if method == "initialize":
        asked = (request.get("params") or {}).get("protocolVersion")
        result = {
            "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "baton-graph", "version": "0.2.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params") or {}
        try:
            result = _tool_result(_call(params.get("name"), params.get("arguments") or {}, central))
        except KeyError:
            return _error(request_id, -32602, f"unknown tool: {params.get('name')}")
        except (ToolError, DiffError, MissingInput, LoadError) as exc:
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    else:
        return _error(request_id, -32601, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(central: str | None = None, stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    central = central or central_dir()
    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"parse error: {exc}")
        else:
            if isinstance(request, dict):
                response = handle(request, central)
            else:
                response = _error(None, -32600, "invalid request")
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
