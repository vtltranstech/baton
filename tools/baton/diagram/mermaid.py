"""Mermaid text for the same diagrams, for viewers that render it (GitHub, GitLab, Azure DevOps).

Generated, never hand-written: identifiers are sanitised, every label is quoted and escaped, the keyword is
line 1. The SVG next to it is the version of record; this is a convenience for Markdown viewers.
"""

from __future__ import annotations

import re

from baton.diagram.shapes import ClassDiagram, Flow, Sequence, UseCaseDiagram

_STYLE = {
    "new": "fill:#eff6ff,stroke:#2563eb,stroke-width:2px,color:#0f172a",
    "changed": "fill:#fff7ed,stroke:#ea580c,stroke-width:2px,color:#0f172a",
    "removed": "fill:#f3f4f6,stroke:#6b7280,stroke-width:2px,stroke-dasharray:4 3,color:#0f172a",
    "impacted": "fill:#fef2f2,stroke:#dc2626,stroke-width:2px,color:#0f172a",
    "touched": "fill:#ffffff,stroke:#475569,stroke-width:1px,color:#0f172a",
    "context": "fill:#ffffff,stroke:#94a3b8,stroke-width:1px,color:#0f172a",
}
_LINK = {"new": "#2563eb", "changed": "#ea580c", "removed": "#6b7280", "impacted": "#dc2626"}


def _label(text: str) -> str:
    """Inside "...": Mermaid entity codes for the characters its parser treats specially."""
    out = str(text).replace("&", "#amp;").replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")
    return out.replace("\n", " ")


def _seq_text(text: str) -> str:
    out = str(text).replace("#", "#35;").replace(";", "#59;").replace("\n", " ")
    return out.replace("<", "#lt;").replace(">", "#gt;")


class _Ids:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.ids: dict[str, str] = {}

    def __call__(self, key: str) -> str:
        if key not in self.ids:
            self.ids[key] = f"{self.prefix}{len(self.ids) + 1}"
        return self.ids[key]


def _shape(kind: str, escaped: str) -> str:
    text = f'"{escaped}"'
    return {
        "store": f"[({text})]",
        "queue": f"[[{text}]]",
        "file": f"[/{text}/]",
        "person": f"([{text}])",
        "external": f"{{{{{text}}}}}",
        "screen": f"({text})",
        "job": f"({text})",
    }.get(kind, f"[{text}]")


def flow(diagram: Flow) -> str:
    ids = _Ids("n")
    lanes = _Ids("L")
    lines = ["flowchart LR"]
    by_lane: dict[str, list] = {}
    for node in diagram.nodes:
        by_lane.setdefault(node.lane, []).append(node)
    titles = {lane.id: lane.title for lane in diagram.lanes}
    order = [lane.id for lane in diagram.lanes if lane.id in by_lane] + [
        k for k in by_lane if k not in titles
    ]
    for lane in order:
        lines.append(f'  subgraph {lanes(lane)}["{_label(titles.get(lane, lane) or "other")}"]')
        lines.append("    direction TB")
        for node in by_lane[lane]:
            label = _label(node.label) + (f"<br/><small>{_label(node.sub)}</small>" if node.sub else "")
            lines.append(f"    {ids(node.id)}{_shape(node.kind, label)}")
        lines.append("  end")
    styled: dict[int, str] = {}
    for index, link in enumerate(diagram.links):
        arrow = "-.->" if link.style in ("async", "data") else "-->"
        label = f'|"{_label(link.label)}"|' if link.label else ""
        lines.append(f"  {ids(link.src)} {arrow}{label} {ids(link.dst)}")
        if link.status in _LINK:
            styled[index] = _LINK[link.status]
    for status, style in _STYLE.items():
        lines.append(f"  classDef {status} {style}")
    for status in _STYLE:
        members = [ids(n.id) for n in diagram.nodes if n.status == status]
        if members:
            lines.append(f"  class {','.join(members)} {status}")
    for index, colour in sorted(styled.items()):
        lines.append(f"  linkStyle {index} stroke:{colour},stroke-width:2px")
    return "\n".join(lines) + "\n"


def sequence(diagram: Sequence) -> str:
    ids = _Ids("p")
    lines = ["sequenceDiagram", "  autonumber"]
    for p in diagram.participants:
        word = "actor" if p.kind == "person" else "participant"
        name = _seq_text(p.label + (f" ({p.sub.split(' / ')[-1]})" if p.sub and p.kind != "person" else ""))
        lines.append(f"  {word} {ids(p.id)} as {name}")
    starts = {f.first: f for f in diagram.fragments}
    ends = {f.last for f in diagram.fragments}
    for index, msg in enumerate(diagram.messages):
        if index in starts:
            lines.append(f"  alt {_seq_text(starts[index].label)}")
        if msg.kind == "return" and not msg.label:
            if index in ends:
                lines.append("  end")
            continue
        arrow = {"sync": "->>", "async": "-)", "return": "-->>", "error": "--x"}[msg.kind]
        text = _seq_text(msg.label or " ")
        highlight = msg.status in ("new", "changed", "removed") and msg.kind != "return"
        if highlight:
            colour = {
                "new": "rgb(219, 234, 254)",
                "changed": "rgb(255, 237, 213)",
                "removed": "rgb(229, 231, 235)",
            }
            lines.append(f"  rect {colour[msg.status]}")
        lines.append(f"  {ids(msg.src)}{arrow}{ids(msg.dst)}: {text}")
        if msg.note:
            lines.append(f"  Note right of {ids(msg.dst)}: {_seq_text(msg.note)}")
        if highlight:
            lines.append("  end")
        if index in ends:
            lines.append("  end")
    return "\n".join(lines) + "\n"


def _ident(name: str, used: dict[str, str], key: str) -> str:
    base = re.sub(r"\W", "_", name) or "X"
    if base[0].isdigit():
        base = "C" + base
    candidate, n = base, 2
    while candidate in used.values() and used.get(key) != candidate:
        candidate = f"{base}{n}"
        n += 1
    used[key] = candidate
    return candidate


def _member(text: str) -> str:
    text = re.sub(r"<([^<>]*)>", r"~\1~", text)
    text = text.replace("<", "~").replace(">", "~")
    return text.replace(": ", " ").replace(":", " ")


def classes(diagram: ClassDiagram) -> str:
    used: dict[str, str] = {}
    lines = ["classDiagram"]
    for box in diagram.boxes:
        name = _ident(box.name, used, box.id)
        lines.append(f"  class {name} {{")
        if box.stereo:
            lines.append(f"    <<{re.sub(r'[^A-Za-z ]', '', box.stereo) or 'class'}>>")
        for member in box.fields + box.methods:
            lines.append(f"    {_member(member.text)}")
        lines.append("  }")
    for rel in diagram.relations:
        if rel.src not in used or rel.dst not in used:
            continue
        arrow = {"implements": "..|>", "extends": "--|>", "creates": "..>"}.get(rel.kind, "-->")
        label = f" : {_seq_text(rel.label)}" if rel.label else ""
        lines.append(f"  {used[rel.src]} {arrow} {used[rel.dst]}{label}")
    for status, style in _STYLE.items():
        members = [used[b.id] for b in diagram.boxes if b.status == status and b.id in used]
        if members:
            lines.append(f"  classDef {status} {style}")
            lines.append(f"  class {','.join(members)} {status}")
    return "\n".join(lines) + "\n"


def entities(diagram: ClassDiagram) -> str:
    used: dict[str, str] = {}
    lines = ["erDiagram"]
    for box in diagram.boxes:
        name = _ident(box.name.upper(), used, box.id)
        lines.append(f"  {name} {{")
        for member in box.fields:
            raw = member.text.removeprefix("PK ")
            field_name, _, type_name = raw.partition(": ")
            type_word = re.sub(r"\W", "_", type_name or "string") or "string"
            key = " PK" if member.kind == "key" else ""
            note = f' "{member.status}"' if member.status else ""
            lines.append(f"    {type_word} {re.sub(r'[^A-Za-z0-9_]', '_', field_name)}{key}{note}")
        if not box.fields:
            lines.append('    string shape "not in the code yet"')
        lines.append("  }")
    return "\n".join(lines) + "\n"


def usecases(diagram: UseCaseDiagram) -> str:
    ids = _Ids("u")
    lines = ["flowchart LR"]
    for actor in diagram.actors:
        if actor.side == "left":
            lines.append(f'  {ids(actor.id)}(["{_label(actor.label)}"])')
    lines.append(f'  subgraph SYS["{_label(diagram.system)}"]')
    for case in diagram.cases:
        lines.append(f'    {ids(case.id)}(["{_label(case.label)}"])')
    lines.append("  end")
    for actor in diagram.actors:
        if actor.side != "left":
            lines.append(f'  {ids(actor.id)}["{_label(actor.label)}"]')
    for link in diagram.links:
        if link.kind == "assoc":
            lines.append(f"  {ids(link.src)} --- {ids(link.dst)}")
        else:
            lines.append(f'  {ids(link.src)} -.->|"{link.kind}"| {ids(link.dst)}')
    for status, style in _STYLE.items():
        members = [ids(c.id) for c in diagram.cases if c.status == status]
        if members:
            lines.append(f"  classDef {status} {style}")
            lines.append(f"  class {','.join(members)} {status}")
    return "\n".join(lines) + "\n"
