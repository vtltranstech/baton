"""Read `screen-spec.md` (contracts/ui-stories.md section 3) into a dict, its JSON twin.

The header is `key: value` lines under `# Screen: <id>`; every other part is a `## ` section, tables read by
their header row (a separator row is optional).
"""

from __future__ import annotations

import re
from pathlib import Path

STATES = ("loading", "empty", "error", "partial", "no-permission")
HEADER_KEYS = ("persona", "task", "area", "route", "entry-points", "screen-of-record", "files")
_SOURCE = re.compile(r"^(?:(new):\s*)?(GET|POST|PUT|PATCH|DELETE)\s+(\S+)(?:\s*(?:->|→)\s*(.+))?$", re.I)
_PARAM = re.compile(r"^(route|query)\s+param\s*(?:->|→)\s*(\S+)", re.I)
_ROUTE = re.compile(r"^(?:(new):\s*)?route:\s*(\S+)", re.I)
_RULE = re.compile(r"\bR\d+\b")


def _cells(line: str) -> list[str]:
    return [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]


def _sections(text: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for match in re.finditer(r"^##[ \t]+(.+?)[ \t]*\n(.*?)(?=^##[ \t]|\Z)", text, re.M | re.S):
        parts[match.group(1).strip().lower()] = match.group(2)
    return parts


def table(body: str) -> list[dict[str, str]]:
    """Rows of the first table in `body`, keyed by the header's lowercased first word."""
    rows, header = [], None
    for line in body.splitlines():
        if not line.strip().startswith("|"):
            if header and rows:
                break
            continue
        cells = _cells(line)
        if header is None:
            header = [(c.split() or [""])[0].lower().rstrip(":") for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(dict(zip(header, cells, strict=False)))
    return rows


def names(cell: str) -> list[str]:
    return [n.strip() for n in re.split(r"[,;]", cell or "") if n.strip() and n.strip() not in ("-", "none")]


def source(value: str) -> dict:
    """{kind: endpoint|param|route|derived|static|unknown, new, method, path, field}."""
    value = (value or "").strip().strip("`")
    match = _SOURCE.match(value)
    if match:
        return {
            "kind": "endpoint",
            "new": bool(match.group(1)),
            "method": match.group(2).upper(),
            "path": match.group(3),
            "field": (match.group(4) or "").strip() or None,
        }
    match = _PARAM.match(value)
    if match:
        return {"kind": "param", "new": False, "param": match.group(1).lower(), "field": match.group(2)}
    match = _ROUTE.match(value)
    if match:
        return {"kind": "route", "new": bool(match.group(1)), "path": match.group(2)}
    lowered = value.lower()
    if lowered.startswith("derived"):
        return {"kind": "derived", "new": False}
    if lowered in ("static", "constant"):
        return {"kind": "static", "new": False}
    return {"kind": "unknown", "new": False, "text": value}


def component(cell: str) -> dict:
    """`Name`, or `New: Name (library: A, B)` -> {name, new, uses}."""
    cell = (cell or "").strip().strip("`")
    match = re.match(r"^new:\s*(\w+)\s*(?:\((?:[^:)]*:)?\s*([^)]*)\))?", cell, re.I)
    if match:
        return {"name": match.group(1), "new": True, "uses": names(match.group(2) or "")}
    return {"name": cell, "new": False, "uses": []}


def parse(text: str) -> dict:
    title = re.search(r"^#[ \t]+Screen:[ \t]*([\w.-]+)", text, re.M)
    head = text.split("\n## ", 1)[0]
    header = {}
    for key in HEADER_KEYS + ("baton.story", "baton.feature", "baton.since"):
        found = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", head, re.M | re.I)
        if found:
            header[key] = re.sub(r"\s+\(.*\)$", "", found.group(1)).strip()
    parts = _sections(text)
    regions = []
    for row in table(parts.get("regions", "")):
        items = names(row.get("fields", ""))
        regions.append(
            {
                "region": row.get("region", ""),
                "purpose": row.get("purpose", ""),
                "items": items,
                "component": component(row.get("component", "")) if row.get("component") else None,
            }
        )
    fields = [
        {
            "field": r.get("field", ""),
            "label": r.get("label", ""),
            "source": source(r.get("source", "")),
            "source_text": r.get("source", ""),
            "format": r.get("format", ""),
            "rules": _RULE.findall(r.get("rule", "")),
        }
        for r in table(parts.get("fields", ""))
    ]
    actions = [
        {
            "action": r.get("action", ""),
            "label": r.get("label", ""),
            "target": source(r.get("target") or r.get("endpoint", "")),
            "target_text": r.get("target") or r.get("endpoint", ""),
            "permission": r.get("permission", ""),
        }
        for r in table(parts.get("actions", ""))
    ]
    states = [
        {"state": r.get("state", "").lower(), "when": r.get("when", ""), "shows": r.get("shows", "")}
        for r in table(parts.get("states", ""))
    ]
    rules_body = next((v for k, v in parts.items() if k.startswith("validation")), "")
    return {
        "screen": title.group(1) if title else None,
        **{k.replace("-", "_").replace(".", "_"): v for k, v in header.items()},
        "regions": regions,
        "fields": fields,
        "actions": actions,
        "states": states,
        "rules": sorted(set(_RULE.findall(rules_body)) | {r for f in fields for r in f["rules"]}),
    }


def load(path: Path) -> dict | None:
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def is_new(spec: dict) -> bool:
    return (spec.get("screen_of_record") or "new").strip().lower() in ("new", "")
