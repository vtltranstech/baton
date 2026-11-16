"""A compact card for an agent: one class, method or resource, with its line ranges, what it calls, who calls
it, what data it touches and which entry points reach it. About 20 lines instead of the source files behind
them."""

from __future__ import annotations

from baton.diagram.codemap import ClassInfo, MethodInfo
from baton.diagram.spec import RESOURCE_PREFIXES, parse_ref, suggest
from baton.diagram.walk import entries_for
from baton.diagram.world import World
from baton.graph.model import node_name, node_prefix

_VERB = {
    "READS_COLLECTION": "reads",
    "WRITES_COLLECTION": "writes",
    "PUBLISHES": "publishes",
    "CONSUMES": "consumes",
    "EXPOSES": "exposes",
    "CALLS_ENDPOINT": "calls",
    "READS_FILE": "reads file",
    "WRITES_FILE": "writes file",
    "RUNS_JOB": "runs",
}


def _short(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def _entries(world: World, fqcn: str, method: str | None) -> list[str]:
    from baton.diagram.change import Change

    change = Change()
    info = world.cls(fqcn)
    names = [method] if method else [m.name for m in info.methods if m.name != info.name]
    for name in names:
        change.methods[(fqcn, name)] = "changed"
    out = []
    for entry in entries_for(world, change):
        m = world.method(*entry)
        use = m.entries[0] if m and m.entries else None
        label = f"{_short(entry[0])}#{entry[1]}"
        out.append(f"{label} ({node_name(use.resource)})" if use else label)
    return out


def _method_lines(world: World, info: ClassInfo, m: MethodInfo) -> tuple[list[str], dict]:
    lines = [
        f"  {m.signature()}  lines {m.start}-{m.end}"
        + (f"  throws {', '.join(m.throws)}" if m.throws else "")
    ]
    calls = []
    data_calls = 0
    for call in m.calls:
        if call.via == "new":
            continue
        called = world.cls(call.target)
        if called is not None and called.is_value():
            data_calls += 1  # getters on DTOs and documents: noise for a reader
            continue
        target = world.implementation(call.target)
        via = f" -> {_short(target)}" if target != call.target else ""
        calls.append(f"{_short(call.target)}#{call.method}{via}")
    uses = [f"{_VERB.get(u.kind, u.kind)} {node_name(u.resource)}" for u in m.uses]
    callers = [
        f"{caller.name}#{cm.name}"
        for caller, cm, call in world.callers(info.fqcn, m.name)
        if cm.name != caller.name and m.accepts(call.arity)
    ]
    for impl_parent in info.implements:
        callers += [
            f"{c.name}#{cm.name}"
            for c, cm, call in world.callers(impl_parent, m.name)
            if m.accepts(call.arity)
        ]
    if calls:
        lines.append(f"    calls {', '.join(dict.fromkeys(calls))}")
    if data_calls:
        lines.append(f"    ({data_calls} calls on data classes not shown)")
    if uses:
        lines.append(f"    {'; '.join(uses)}")
    if callers:
        lines.append(f"    called by {', '.join(dict.fromkeys(callers))}")
    data = {
        "name": m.name,
        "signature": m.signature(),
        "lines": [m.start, m.end],
        "calls": calls,
        "uses": uses,
        "calledBy": list(dict.fromkeys(callers)),
        "throws": m.throws,
    }
    return lines, data


def card(world: World, target: str) -> tuple[dict, list[str]]:
    if node_prefix(target) in RESOURCE_PREFIXES:
        return _resource(world, target)
    ref = parse_ref(target)
    owner = ref.owner if ref.kind in ("method", "field") else target
    matches = [
        c for c in world.classes() if c.fqcn == owner or c.name == owner or c.fqcn.endswith("." + owner)
    ]
    if not matches:
        return {}, [f"no class {owner}{suggest(owner, [c.name for c in world.classes()])}"]
    if len(matches) > 1:
        return {}, [f"{owner} is ambiguous: {', '.join(c.fqcn for c in matches)}"]
    info = matches[0]
    methods = info.methods
    if ref.kind == "method":
        methods = info.method(ref.member)
        if not methods:
            return {}, [
                f"{info.name} has no method {ref.member}{suggest(ref.member, [m.name for m in info.methods])}"
            ]
    head = f"{info.name}  <<{info.stereotype}>>  {info.repo}  {info.file}:{info.start}-{info.end}"
    lines = [head, f"  {info.fqcn}"]
    if info.implements or info.extends:
        lines.append(f"  implements/extends: {', '.join(_short(x) for x in info.implements + info.extends)}")
    impls = world.map_of(info.fqcn).impls.get(info.fqcn, [])
    if impls:
        lines.append(f"  implemented by: {', '.join(_short(x) for x in impls)}")
    if info.fields:
        lines.append(
            "  fields: "
            + " / ".join(f"{f.name}: {f.type}{' (injected)' if f.injected else ''}" for f in info.fields)
        )
    if info.uses:
        lines.append(
            "  " + "; ".join(f"{_VERB.get(u.kind, u.kind)} {node_name(u.resource)}" for u in info.uses)
        )
    if info.doc:
        lines.append(f"  document of collection {info.doc}")
    lines.append(f"  tests naming it: {', '.join(t.rsplit('/', 1)[-1] for t in info.tests) or 'none'}")
    lines.append("  methods:")
    data_methods = []
    for m in methods:
        if m.name == info.name and ref.kind != "method":
            continue
        more, data = _method_lines(world, info, m)
        lines += more
        data_methods.append(data)
    entries = _entries(world, info.fqcn, ref.member if ref.kind == "method" else None)
    lines.append(f"  reached from: {', '.join(entries) or 'no entry point found'}")
    data = {
        "class": info.fqcn,
        "stereotype": info.stereotype,
        "repo": info.repo,
        "file": info.file,
        "lines": [info.start, info.end],
        "fields": [f.__dict__ for f in info.fields],
        "methods": data_methods,
        "implements": info.implements,
        "implementedBy": impls,
        "tests": info.tests,
        "reachedFrom": entries,
    }
    return {"text": "\n".join(lines), "data": data}, []


def _resource(world: World, resource: str) -> tuple[dict, list[str]]:
    edges = world.edges_to(resource)
    if not edges:
        names = [n for n in world.nodes() if node_prefix(n) == node_prefix(resource)]
        return {}, [f"{resource} is not in the graph{suggest(resource, names)}"]
    lines = [f"{resource}"]
    rows = []
    for edge in edges:
        info, m = world.owner(edge)
        where = f"{_short(node_name(edge.src))}" + (f"#{m.name}" if m else "")
        lines.append(f"  {_VERB.get(edge.kind, edge.kind)} by {where}  ({edge.repo} {edge.file}:{edge.line})")
        rows.append({"kind": edge.kind, "by": where, "repo": edge.repo, "file": edge.file, "line": edge.line})
    entry = world.collections.get(node_name(resource))
    if entry:
        lines.append(
            f"  shape: {_short(str(entry.get('owner', '')))}; "
            f"indexes: {', '.join(map(str, entry.get('compoundIndexes') or [])) or 'none'}"
        )
    return {"text": "\n".join(lines), "data": {"resource": resource, "edges": rows}}, []
