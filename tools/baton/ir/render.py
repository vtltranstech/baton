"""The IR as text for an agent: whole words, one fact per line, file:line on every class and operation.

Views: the orientation (one line per unit), a unit, a class, one operation, a resource, a search, and a
story slice. The same input always gives the same bytes.
"""

from __future__ import annotations

import re

from baton.diagram.codemap import ClassInfo
from baton.graph.model import node_name, node_prefix
from baton.ir.model import ENTRY_KINDS, IR, Effect, Op, trivial

LEGEND = (
    "IR: <stereotype> <Class> <file>:<lines>; operations indented with :<lines>. in/on/job = entry point; "
    "calls = behavioural calls in order (self = same class, ? = more than one candidate); reads/writes/"
    "emits/http = data and message effects including those reached through calls; from = entry points "
    "that reach it."
)
VERB = {
    "READS_COLLECTION": "reads",
    "WRITES_COLLECTION": "writes",
    "PUBLISHES": "emits",
    "CALLS_ENDPOINT": "http",
    "READS_FILE": "reads-file",
    "WRITES_FILE": "writes-file",
}
ENTRY_VERB = {"EXPOSES": "in", "CONSUMES": "on", "RUNS_JOB": "job"}
_ORDER = list(VERB)


def short(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def tokens(text: str) -> int:
    """Rough token count for code-like text."""
    return round(len(text) / 3.6)


def res(resource: str) -> str:
    name = node_name(resource)
    return name.split(" ", 1)[1] if node_prefix(resource) == "endpoint" and " " in name else name


def _entry(resource: str) -> str:
    name = node_name(resource)
    return name if node_prefix(resource) in ("endpoint", "job") else f"{node_prefix(resource)} {name}"


def _params(op: Op, overloaded: bool) -> str:
    if overloaded:
        return ", ".join(op.m.params)
    return ", ".join(p.rsplit(" ", 1)[-1] for p in op.m.params)


def _effect_lines(effects: list[Effect]) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for effect in effects:
        names = grouped.setdefault(effect.kind, [])
        if res(effect.resource) not in names:
            names.append(res(effect.resource))
    return [f"{VERB[k]} {', '.join(sorted(grouped[k]))}" for k in _ORDER if k in grouped]


def _calls(ir: IR, op: Op) -> str:
    order: dict[str, list[str]] = {}
    for step in ir.steps[op.key]:
        if ir.noise(step):
            continue
        owner = "self" if step.target == op.info.fqcn else short(step.target)
        names = order.setdefault(owner, [])
        label = step.method + ("?" if step.ambiguous else "")
        if label not in names:
            names.append(label)
    return "; ".join(f"{owner}.{','.join(names)}" for owner, names in order.items())


def op_lines(
    ir: IR, op: Op, *, callers: bool = False, reach: bool = False, overloaded: bool = False
) -> list[str]:
    head = f"  {op.m.name}({_params(op, overloaded)})"
    if op.m.returns and op.m.returns != "void":
        head += f": {op.m.returns}"
    lines = [f"{head}  :{op.m.start}-{op.m.end}"]
    body = []
    for use in op.m.entries:
        body.append(f"{ENTRY_VERB[use.kind]} {_entry(use.resource)}")
    calls = _calls(ir, op)
    if calls:
        body.append(f"calls {calls}")
    body += _effect_lines(ir.effects(op.key))
    if op.m.throws:
        body.append("throws " + ", ".join(op.m.throws))
    if callers:
        outside = sorted(
            {ir.ops[c].label for c, _ in ir.callers.get(op.key, []) if ir.ops[c].info.fqcn != op.info.fqcn}
        )
        if outside:
            more = f" (+{len(outside) - 6})" if len(outside) > 6 else ""
            body.append(f"called by {', '.join(outside[:6])}{more}")
    if reach and not op.is_entry():
        entries = ir.entry_points(op.key)
        if entries:
            body.append("from " + "; ".join(ir.entry_label(e) for e in entries))
    return lines + [f"    {line}" for line in body]


def _shown(ir: IR, op: Op, everything: bool) -> bool:
    if op.info.kind == "module" and not op.m.calls and not op.m.uses:
        return False  # a types-only file
    if trivial(op.m) and not op.m.entries:
        outside = any(ir.ops[c].info.fqcn != op.info.fqcn for c, _ in ir.callers.get(op.key, []))
        if not outside or op.m.name.startswith(("get", "is", "has", "set")):
            return False  # accessors and helpers nobody else calls
    return everything or op.m.visibility != "private" or bool(op.m.uses)


def class_lines(
    ir: IR,
    info: ClassInfo,
    *,
    everything: bool = False,
    callers: bool = False,
    reach: bool = False,
    only: set[str] | None = None,
) -> list[str]:
    ops = [
        op for op in ir.ops_of(info) if (op.key in only if only is not None else _shown(ir, op, everything))
    ]
    lines = [f"{info.stereotype} {info.name}  {info.file}:{info.start}-{info.end}"]
    parents = [short(x) for x in info.implements + info.extends]
    if parents:
        lines.append(
            "  implements " + ", ".join(parents[:4]) + (f" (+{len(parents) - 4})" if len(parents) > 4 else "")
        )
    injected = [short(f.type.split("<", 1)[0]) for f in info.fields if f.injected]
    if injected:
        lines.append("  injects " + ", ".join(injected))
    own = _effect_lines([e for e in _class_uses(info)])
    lines += [f"  {line}" for line in own]
    if everything and info.tests:
        names = [t.rsplit("/", 1)[-1] for t in info.tests]
        lines.append("  tests " + ", ".join(names[:4]) + (f" (+{len(names) - 4})" if len(names) > 4 else ""))
    names = [op.m.name for op in ir.ops_of(info)]
    for op in ops:
        lines += op_lines(ir, op, callers=callers, reach=reach, overloaded=names.count(op.m.name) > 1)
    return lines


def _class_uses(info: ClassInfo) -> list[Effect]:
    return [Effect(u.kind, u.resource, "", info.file, u.line) for u in info.uses if u.kind in VERB]


def unit_text(ir: IR, unit: str) -> str:
    world = ir.world
    lines = [f"unit {unit}  ({world.repo_of_unit(unit)})"]
    for info in world.classes():
        if world.unit(info) != unit or info.fqcn not in ir.by_class:
            continue
        block = class_lines(ir, info)
        if len(block) > 1 or info.stereotype in ("controller", "listener", "repository"):
            lines += block
    return "\n".join(lines) + "\n"


def orientation(ir: IR) -> str:
    """One line per unit: its entry points and the data it writes. The map an agent starts from."""
    world = ir.world
    lines = [
        LEGEND,
        "<name> = a resource name the extractor could not resolve (counted as unresolved).",
        "",
        "unit | repo | classes | entry points | writes | emits | http calls",
    ]
    for unit in world.units():
        classes = [c for c in world.classes() if world.unit(c) == unit]
        ops = [op for c in classes for op in ir.ops_of(c)]
        entries = sum(1 for op in ops for _ in op.m.entries)
        own = [e for op in ops for e in ir.effects(op.key) if e.own]
        cells = [
            _names(own, "WRITES_COLLECTION"),
            _names(own, "PUBLISHES"),
            _names(own, "CALLS_ENDPOINT", count=True),
        ]
        lines.append(
            f"{unit} | {world.repo_of_unit(unit)} | {len(classes)} | {entries} | " + " | ".join(cells)
        )
    return "\n".join(lines) + "\n"


def _names(effects: list[Effect], kind: str, count: bool = False) -> str:
    names = sorted({res(e.resource) for e in effects if e.kind == kind})
    resolved = [n for n in names if not n.startswith("<")]
    unresolved = len(names) - len(resolved)
    if count:
        return str(len(names)) if names else "-"
    text = ", ".join(resolved)
    if unresolved:
        text += ("; " if text else "") + f"{unresolved} unresolved"
    return text or "-"


def resource_text(ir: IR, resource: str) -> str:
    users = ir.users_of(resource)
    lines = [resource]
    direct = [(op, e) for op, e in users if e.own or e.kind in ENTRY_KINDS]
    through = sorted({op.label for op, e in users if not (e.own or e.kind in ENTRY_KINDS)})
    for op, effect in direct:
        verb = ENTRY_VERB.get(effect.kind) or VERB.get(effect.kind, effect.kind)
        via = f" via {effect.via}" if effect.via else ""
        lines.append(f"  {verb} {op.label}{via}  {op.info.repo} {op.info.file}:{effect.line}")
    if through:
        more = f" (+{len(through) - 12})" if len(through) > 12 else ""
        lines.append(f"  also through calls: {', '.join(through[:12])}{more}")
    entries = sorted({e for op, _ in direct for e in ir.entry_points(op.key)})
    if entries:
        lines.append("  from " + "; ".join(ir.entry_label(e) for e in entries[:10]))
    entry = ir.world.collections.get(node_name(resource))
    if entry:
        indexes = ", ".join(map(str, entry.get("compoundIndexes") or [])) or "none"
        lines.append(f"  shape {short(str(entry.get('owner', '')))}; indexes {indexes}")
    return "\n".join(lines) + "\n"


# -- search ------------------------------------------------------------------------------------------------

_STOP = set(
    "a an and are as at be by for from has have in into is it its of on or that the this to was we when with "
    "will can should must not no new add show see user users story".split()
)


def words(text: str) -> list[str]:
    """Lower-case words, camelCase and snake_case split, stop words dropped."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    found = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", text)]
    return [w for w in dict.fromkeys(found) if w not in _STOP and len(w) > 2]


def _match(query: list[str], candidate: list[str]) -> float:
    score = 0.0
    for q in query:
        if q in candidate:
            score += 1
        elif len(q) >= 4 and any(
            c.startswith(q[:4]) and (c.startswith(q) or q.startswith(c)) for c in candidate
        ):
            score += 0.6
    return score


def find(ir: IR, text: str, limit: int = 15) -> list[tuple[float, str, str]]:
    """(score, id, one-line summary) for the operations, classes and resources that best match the words."""
    query = words(text)
    if not query:
        return []
    hits: list[tuple[float, str, str]] = []
    for info in ir.world.classes():
        if info.fqcn not in ir.by_class:
            continue
        class_words = words(info.name)
        base = _match(query, class_words + words(info.file.rsplit("/", 2)[-2] if "/" in info.file else ""))
        if base:
            hits.append(
                (base + 0.2, info.name, f"{info.stereotype} {info.name}  {info.file}:{info.start}-{info.end}")
            )
        for op in ir.ops_of(info):
            entry_words = [w for u in op.m.entries for w in words(node_name(u.resource))]
            score = _match(query, words(op.m.name) + class_words + entry_words)
            if score > base and score:
                effects = "; ".join(_effect_lines(ir.effects(op.key)))
                hits.append(
                    (
                        score,
                        op.label,
                        f"op {op.label}  {info.file}:{op.m.start}-{op.m.end}"
                        + (f"  {effects}" if effects else ""),
                    )
                )
    for node in sorted(ir.world.nodes()):
        if node_prefix(node) in ("collection", "topic", "queue", "endpoint", "job") and "<" not in node:
            score = _match(query, words(node_name(node)))
            if score:
                hits.append((score + 0.1, node, f"{node}"))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return hits[:limit]


__all__ = [
    "LEGEND",
    "class_lines",
    "find",
    "op_lines",
    "orientation",
    "resource_text",
    "tokens",
    "unit_text",
    "words",
]
