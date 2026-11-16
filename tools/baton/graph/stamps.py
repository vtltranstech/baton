"""Story and feature stamps on the architecture of record (contracts/versioning.md section 3).

`baton c4` regenerates docs/architecture/workspace.dsl from the graph, so stamps written into the model
would be lost on the next run and reported as drift. This module keeps them deterministic:

- `extract(dsl)`: the stamps per element identifier and per relationship (`src -> dst "label"`).
- `strip(dsl)`: the model without stamps, which is what the graph projection is compared with.
- `apply(dsl, stamps)`: put stamps back onto a freshly generated model.
- `promote(old, new, story, feature, date)`: stamp what a story added or changed, carry every older stamp,
  and list what it removed.

A stamp is a `tags "<feature>"` line and a `properties` block of `"baton.*"` keys, both direct children
of the element or relationship. Other tags and properties are the generator's and are left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KEYS = ("baton.story", "baton.feature", "baton.since", "baton.changed-by")
_ELEMENT = re.compile(r"^(\s*)(\w+)\s*=\s*(person|softwareSystem|container|component)\b(.*?)\s*(\{)?\s*$")
_RELATION = re.compile(r'^(\s*)(\w+)\s*->\s*(\w+)\s*("(?:[^"\\]|\\.)*")?(.*?)\s*(\{)?\s*$')
_FEATURE = re.compile(r"^[A-Z][A-Za-z]*-[A-Za-z0-9]+$")
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


@dataclass
class Stamp:
    tags: list[str] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)

    def empty(self) -> bool:
        return not self.tags and not self.props


@dataclass
class _Item:
    key: str
    kind: str  # element | relationship
    start: int  # line index of the declaration
    end: int | None  # line index of the closing brace, None when the item has no block
    indent: str
    decl: str  # the declaration without the block brace, whitespace-normalised
    stamp_lines: list[int] = field(default_factory=list)
    stamp: Stamp = field(default_factory=Stamp)


def _braces(line: str) -> int:
    text = _QUOTED.sub('""', line.split("//", 1)[0])
    return text.count("{") - text.count("}")


def _stamp_lines(lines: list[str], start: int, end: int) -> tuple[list[int], Stamp]:
    """Direct children of the block between start and end that are stamps."""
    found, stamp, depth, index = [], Stamp(), 0, start + 1
    while index < end:
        line = lines[index].strip()
        if depth == 0 and line.startswith("tags "):
            values = _QUOTED.findall(line)
            if values and all(_FEATURE.match(v) for v in values):
                found.append(index)
                stamp.tags += [v for v in values if v not in stamp.tags]
        if depth == 0 and line.startswith("properties"):
            close = index
            if _braces(line) > 0:
                level = _braces(line)
                while level > 0 and close + 1 < end:
                    close += 1
                    level += _braces(lines[close])
            body = " ".join(part.strip() for part in lines[index: close + 1])
            values = _QUOTED.findall(body)
            pairs = dict(zip(values[0::2], values[1::2], strict=False))
            if pairs and all(key.startswith(("baton.", "pod.", "harness.")) for key in pairs):
                found.extend(range(index, close + 1))
                # pod.* and harness.* are the names before the renames; they are read and rewritten as baton.*
                stamp.props.update({re.sub(r"^(?:pod|harness)\.", "baton.", k): v for k, v in pairs.items()})
            index = close + 1
            continue
        depth += _braces(lines[index])
        index += 1
    return found, stamp


def parse(dsl: str) -> list[_Item]:
    lines = dsl.split("\n")
    items: list[_Item] = []
    for index, line in enumerate(lines):
        if line.strip().startswith("//"):
            continue
        element = _ELEMENT.match(line)
        relation = None if element else _RELATION.match(line)
        if not element and not relation:
            continue
        if element:
            indent, key, opens = element.group(1), element.group(2), element.group(5)
            decl = f"{key} = {element.group(3)}{element.group(4)}"
            kind = "element"
        else:
            indent, opens = relation.group(1), relation.group(6)
            key = f"{relation.group(2)} -> {relation.group(3)} {relation.group(4) or ''}".strip()
            decl = f"{key}{relation.group(5)}"
            kind = "relationship"
        end = None
        if opens:
            level, end = 1, index
            while level > 0 and end + 1 < len(lines):
                end += 1
                level += _braces(lines[end])
        item = _Item(key, kind, index, end, indent, " ".join(decl.split()))
        if end is not None:
            item.stamp_lines, item.stamp = _stamp_lines(lines, index, end)
        items.append(item)
    return items


def extract(dsl: str) -> dict[str, Stamp]:
    return {item.key: item.stamp for item in parse(dsl) if not item.stamp.empty()}


def strip(dsl: str) -> str:
    """The model without stamps; a block left empty by it collapses back to one line."""
    lines = dsl.split("\n")
    drop: set[int] = set()
    collapse: dict[int, int] = {}
    for item in parse(dsl):
        if not item.stamp_lines:
            continue
        drop.update(item.stamp_lines)
        inner = [i for i in range(item.start + 1, item.end) if i not in drop and lines[i].strip()]
        if not inner:
            collapse[item.start] = item.end
    out = []
    skip_to = -1
    for index, line in enumerate(lines):
        if index <= skip_to or index in drop:
            continue
        if index in collapse:
            out.append(line.rstrip()[:-1].rstrip())
            skip_to = collapse[index]
            continue
        out.append(line)
    return "\n".join(out)


def render(stamp: Stamp, indent: str) -> list[str]:
    lines = []
    if stamp.tags:
        lines.append(f"{indent}tags " + " ".join(f'"{tag}"' for tag in stamp.tags))
    if stamp.props:
        lines.append(f"{indent}properties {{")
        for key in [k for k in KEYS if k in stamp.props] + sorted(k for k in stamp.props if k not in KEYS):
            lines.append(f'{indent}    "{key}" "{stamp.props[key]}"')
        lines.append(f"{indent}}}")
    return lines


def apply(dsl: str, stamps: dict[str, Stamp]) -> str:
    """Stamps onto a model that has none (a fresh projection). Unchanged when there is nothing to apply."""
    if not stamps:
        return dsl
    lines = dsl.split("\n")
    inserts: dict[int, list[str]] = {}
    opened: set[int] = set()
    closes: dict[int, str] = {}
    for item in parse(dsl):
        stamp = stamps.get(item.key)
        if not stamp or stamp.empty():
            continue
        inserts[item.start] = render(stamp, item.indent + "    ")
        if item.end is None:
            opened.add(item.start)
            closes[item.start] = item.indent + "}"
    out = []
    for index, line in enumerate(lines):
        if index in opened:
            out.append(line.rstrip() + " {")
            out.extend(inserts[index])
            out.append(closes[index])
            continue
        out.append(line)
        if index in inserts:
            out.extend(inserts[index])
    return "\n".join(out)


@dataclass
class Promotion:
    dsl: str
    added_elements: list[str]
    added_relationships: list[str]
    changed: list[str]
    removed: list[str]


def promote(old: str | None, new: str, story: str, feature: str, date: str) -> Promotion:
    """Stamp the new projection: carry older stamps, mark what `story` added or changed, list removals."""
    before = {item.key: item for item in parse(strip(old))} if old else {}
    carried = extract(old) if old else {}
    stamps: dict[str, Stamp] = {}
    added_elements, added_relationships, changed = [], [], []
    for item in parse(new):
        old_stamp = carried.get(item.key) or Stamp()
        stamp = Stamp(list(old_stamp.tags), dict(old_stamp.props))
        previous = before.get(item.key)
        if old is not None and previous is None:
            props = {"baton.story": story, "baton.feature": feature, "baton.since": date}
            stamp = Stamp([feature], props)
            (added_elements if item.kind == "element" else added_relationships).append(item.key)
        elif previous is not None and previous.decl != item.decl:
            by = [s for s in stamp.props.get("baton.changed-by", "").split(",") if s]
            if story not in by and stamp.props.get("baton.story") != story:
                by.append(story)
            if by:
                stamp.props["baton.changed-by"] = ",".join(by)
            if feature not in stamp.tags:
                stamp.tags.append(feature)
            changed.append(item.key)
        if not stamp.empty():
            stamps[item.key] = stamp
    removed = [key for key in before if key not in {item.key for item in parse(new)}]
    return Promotion(apply(new, stamps), added_elements, added_relationships, changed, removed)


def changelog(text: str | None, date: str, feature: str, story: str, promotion: Promotion) -> str:
    """docs/architecture/CHANGELOG.md with one row for this promotion and one per removal."""
    header = [
        "# Architecture changelog",
        "",
        "| Date | Feature | Story | Elements | Relationships | Changed | Removed | Change |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    removed_header = ["", "## Removed", "", "| Date | Element | Removed by |", "| --- | --- | --- |"]
    lines = (text or "\n".join(header) + "\n").rstrip("\n").split("\n")
    row = (
        f"| {date} | {feature} | {story} | +{len(promotion.added_elements)} elements "
        f"| +{len(promotion.added_relationships)} relationships | ~{len(promotion.changed)} changed "
        f"| {len(promotion.removed)} removed | changes/{story}.md |"
    )
    first_table_end = None
    for index, line in enumerate(lines):
        if line.startswith("| Date | Feature"):
            first_table_end = index + 1
            while first_table_end < len(lines) and lines[first_table_end].startswith("|"):
                first_table_end += 1
            break
    if first_table_end is None:
        lines += header[2:]
        first_table_end = len(lines)
    lines.insert(first_table_end, row)
    if promotion.removed:
        if "## Removed" not in lines:
            lines += removed_header
        for key in promotion.removed:
            lines.append(f"| {date} | {key.replace('|', '/')} | removed-by {story} |")
    return "\n".join(lines) + "\n"


def tagged(dsl: str, feature: str) -> list[str]:
    """Element identifiers and relationship keys stamped with the feature."""
    return [
        item.key
        for item in parse(dsl)
        if feature in item.stamp.tags or item.stamp.props.get("baton.feature") == feature
    ]
