"""One story's diagrams, all read from the same walks so they can never disagree with each other or the
code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from baton.diagram.change import Change
from baton.diagram.codemap import ClassInfo, MethodInfo
from baton.diagram.shapes import (
    CHANGED,
    CONTEXT,
    IMPACTED,
    NEW,
    REMOVED,
    TOUCHED,
    Actor,
    Box,
    ClassDiagram,
    Flow,
    Fragment,
    Lane,
    Link,
    Member,
    Message,
    Node,
    Participant,
    Relation,
    Sequence,
    UseCase,
    UseCaseDiagram,
    UseCaseLink,
    strongest,
)
from baton.diagram.shapes import merge_label as _merge
from baton.diagram.spec import Spec
from baton.diagram.walk import Step, Walk, Walker, entries_for
from baton.diagram.world import World
from baton.graph.model import PAIRS, node_name, node_prefix

MAX_WALKS = 5
MAX_LLD = 14
_VIS = {"public": "+", "protected": "#", "private": "-", "package": "~", "": "+"}
_HTTP = {"GET": "View", "POST": "Submit", "PUT": "Update", "PATCH": "Update", "DELETE": "Delete"}


@dataclass
class StoryDiagrams:
    story: str
    title: str
    source: str
    flow: Flow
    sequences: list[Sequence]
    lld: ClassDiagram
    data: ClassDiagram | None
    usecases: UseCaseDiagram
    touch: list[dict]
    impacted: list[dict]
    unknown: list[str]
    walks: list[Walk]
    more_entries: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    conformance: dict | None = None
    commits: str = ""


# -- participants --------------------------------------------------------------------------------------------


class Cast:
    """What each participant key looks like, and which lane it sits in."""

    def __init__(self, world: World, change: Change):
        self.world = world
        self.change = change
        self.status: dict[str, str] = {}

    def bump(self, key: str, status: str) -> None:
        self.status[key] = strongest(self.status.get(key, ""), status) if key in self.status else status

    def label(self, key: str) -> str:
        if key.startswith("actor:"):
            return key[6:]
        if key.startswith("class:"):
            info = self.world.cls(key[6:])
            return info.name if info else key[6:].rsplit(".", 1)[-1]
        return node_name(key)

    def kind(self, key: str) -> str:
        if key.startswith("actor:"):
            name = key[6:]
            return (
                "person"
                if name not in ("Scheduler", "caller") and not name.startswith("publisher of")
                else "external"
            )
        prefix = node_prefix(key)
        if prefix == "collection":
            return "store"
        if prefix in ("topic", "queue"):
            return "queue"
        if prefix == "file":
            return "file"
        if prefix in ("endpoint",):
            return "external"
        if prefix == "job":
            return "job"
        info = self.world.cls(key[6:])
        if info and info.stereotype == "screen":
            return "screen"
        return "component"

    def sub(self, key: str, with_repo: bool = False) -> str:
        if key.startswith("actor:"):
            return "person" if self.kind(key) == "person" else "system"
        prefix = node_prefix(key)
        if prefix == "class":
            info = self.world.cls(key[6:])
            if info is None:
                return ""
            methods = [name for (fqcn, name), s in self.change.methods.items() if fqcn == info.fqcn and s]
            text = info.stereotype
            if methods and self.status.get(key) in (CHANGED, NEW):
                text += " - " + ", ".join(f"{name}()" for name in sorted(methods)[:2])
            if with_repo:
                text = f"{self.world.unit(info)} - {text}"
            return text
        if prefix == "collection":
            return f"collection - {self.world.datastore()}"
        if prefix in ("topic", "queue"):
            return f"{prefix} - {self.world.broker(key)}"
        if prefix == "endpoint":
            return "REST endpoint, provider not in the graph"
        return prefix

    def lane(self, key: str) -> str:
        if key.startswith("actor:"):
            return "people"
        prefix = node_prefix(key)
        if prefix == "class":
            info = self.world.cls(key[6:])
            return f"unit:{self.world.unit(info)}" if info else "external"
        return {"collection": "data", "topic": "messaging", "queue": "messaging", "file": "files"}.get(
            prefix, "external"
        )

    def participant_status(self, key: str) -> str:
        if key in self.status:
            return self.status[key]
        if key.startswith("class:"):
            return self.change.class_status(key[6:]) or TOUCHED
        if key.startswith("actor:"):
            return TOUCHED
        return self.change.resources.get(key, TOUCHED)


# -- the build -----------------------------------------------------------------------------------------------


def _impact(world: World, change: Change) -> tuple[dict[str, list[dict]], list[dict], list[str]]:
    """Blast radius per contracts/graph.md, walked between deployable units (a monorepo's modules count as
    separate units, so one service's change reaches the others), depth 2."""
    from baton.graph.model import DOCUMENT_EXTRACTOR, PRODUCER_KIND_OF_RESOURCE, unknown_edge_message

    by_src: dict[str, list] = {}
    by_dst: dict[tuple[str, str], list] = {}
    for edge in world.edges:
        by_src.setdefault(edge.src, []).append(edge)
        by_dst.setdefault((edge.kind, edge.dst), []).append(edge)

    def unit_of(edge) -> str:
        return world.unit_of(edge.repo, edge.file)

    seeds: dict[str, set[tuple[str, str, bool]]] = {}
    breaking = change.breaking
    for fqcn, status in change.classes.items():
        info = world.cls(fqcn)
        if not status or info is None:
            continue
        node = f"class:{fqcn}"
        for edge in by_src.get(node, []):
            if edge.kind in PAIRS:
                seeds.setdefault(world.unit(info), set()).add((edge.kind, edge.dst, node in breaking))
            elif edge.extractor == DOCUMENT_EXTRACTOR:
                seeds.setdefault(world.unit(info), set()).add(
                    ("WRITES_COLLECTION", edge.dst, node in breaking)
                )
    resources = {r for r, s in change.resources.items() if s}
    resources |= {res for _c, _m, kind, res in change.new_uses if kind in PAIRS}
    for resource in resources:
        kind = PRODUCER_KIND_OF_RESOURCE.get(node_prefix(resource))
        if kind is None:
            continue
        owners = {unit_of(e) for e in by_dst.get((kind, resource), [])}
        for caller, _m, _kind, res in change.new_uses:
            info = world.cls(caller)
            if res == resource and info is not None:
                owners.add(world.unit(info))
        for owner in owners or {""}:
            seeds.setdefault(owner, set()).add((kind, resource, resource in breaking))
    found: dict[tuple[str, str, str, str], dict] = {}
    unknown: set[str] = set()
    for source in sorted(seeds):
        frontier = set(seeds[source])
        visited = {source}
        for depth in (1, 2):
            reached: dict[str, bool] = {}
            for kind, resource, is_breaking in sorted(frontier):
                consumers = by_dst.get((PAIRS[kind], resource), [])
                if not consumers:
                    unknown.add(unknown_edge_message(resource, kind))
                for edge in consumers:
                    unit = unit_of(edge)
                    if unit == source:
                        continue
                    row = found.setdefault(
                        (unit, resource, edge.file, edge.repo),
                        {"lines": set(), "breaking": False, "from": source},
                    )
                    row["lines"].add(edge.line)
                    row["breaking"] = row["breaking"] or is_breaking
                    reached[unit] = reached.get(unit, False) or is_breaking
            frontier = set()
            if depth == 1:
                for unit, is_breaking in reached.items():
                    if unit in visited:
                        continue
                    visited.add(unit)
                    for edge in world.edges:
                        if edge.kind in PAIRS and unit_of(edge) == unit:
                            frontier.add((edge.kind, edge.dst, is_breaking))
    rows: list[dict] = []
    by_resource: dict[str, list[dict]] = {}
    for (unit, via, file, repo), row in sorted(found.items()):
        low, high = min(row["lines"]), max(row["lines"])
        item = {
            "repo": repo,
            "unit": unit,
            "via": via,
            "file": file,
            "lines": str(low) if low == high else f"{low}-{high}",
            "breaking": row["breaking"],
            "from": row["from"],
        }
        rows.append(item)
        by_resource.setdefault(via, []).append(item)
    return by_resource, rows, sorted(unknown)


def build(
    world: World, change: Change, story: str, title: str, source: str, spec: Spec | None
) -> StoryDiagrams:
    impacted, impact_rows, unknown = _impact(world, change)
    walker = Walker(world, change, impacted)
    entries = entries_for(world, change)
    walks = [walker.walk(*entry) for entry in entries[:MAX_WALKS]]
    more = [f"{e[0].rsplit('.', 1)[-1]}#{e[1]}" for e in entries[MAX_WALKS:]]
    cast = Cast(world, change)
    for walk in walks:
        for step in walk.flat():
            cast.bump(step.src, cast.participant_status(step.src))
            cast.bump(step.dst, step.status if step.status == IMPACTED else cast.participant_status(step.dst))
    heading = f"{story} {title}".strip()
    subtitle = f"generated by `baton diagram` from {source} - {world.commits()}"
    flow = _flow(world, change, cast, walks, impact_rows, heading, subtitle)
    sequences = [_sequence(cast, walk, heading, subtitle, i) for i, walk in enumerate(walks, 1)]
    lld = _lld(world, change, heading, subtitle)
    data = _data(world, change, walks, heading, subtitle)
    usecases = _usecases(world, change, cast, walks, spec, impact_rows, heading, subtitle)
    touch = _touch(world, change, walks)
    notes = []
    if world.missing:
        notes.append("not checked out, so not drawn: " + ", ".join(world.missing))
    if not walks:
        notes.append("no entry point reaches the change: name one under `entries:` in the spec")
    for walk in walks:
        if walk.collapsed:
            notes.append(
                f"{walk.title}: {walk.collapsed} unchanged sub-flows folded to keep the sequence readable"
            )
    return StoryDiagrams(
        story,
        title,
        source,
        flow,
        sequences,
        lld,
        data,
        usecases,
        touch,
        impact_rows,
        unknown,
        walks,
        more,
        notes,
        commits=world.commits(),
    )


# -- flow with impacts ---------------------------------------------------------------------------------------


def _flow(world, change, cast: Cast, walks, impact_rows, heading, subtitle) -> Flow:
    nodes: dict[str, Node] = {}
    links: dict[tuple[str, str, str], Link] = {}

    def node(key: str) -> None:
        if key not in nodes:
            nodes[key] = Node(
                key,
                cast.label(key),
                cast.kind(key),
                cast.participant_status(key),
                cast.sub(key),
                cast.lane(key),
            )

    def link(src: str, dst: str, label: str, status: str, style: str) -> None:
        node(src)
        node(dst)
        k = (src, dst, style)
        if k not in links:
            links[k] = Link(src, dst, label, status, style)
            return
        current = links[k]
        _merge(current, label)
        current.status = strongest(current.status, status)

    for walk in walks:
        for step in walk.flat():
            if step.kind == "self":
                node(step.src)
                continue
            if step.kind == "data":
                label = step.label.split(" -> ")[-1]
            elif step.kind in ("call", "self") and "(" in step.label:
                label = step.label.split("(", 1)[0] + "()"
            else:
                label = step.label
            link(step.src, step.dst, label, step.status, step.style)
    for row in impact_rows:
        cmap = world.maps.get(row["repo"])
        consumer = next((c for c in cmap.classes.values() if c.file == row["file"]), None) if cmap else None
        if consumer is None:
            continue
        key = f"class:{consumer.fqcn}"
        cast.status[key] = IMPACTED
        via = row["via"]
        if node_prefix(via) == "endpoint":
            provider = next((e for e in world.edges_to(via, "EXPOSES")), None)
            if provider is not None:
                link(key, provider.src, node_name(via), IMPACTED, "sync")
        else:
            style = "async" if node_prefix(via) in ("topic", "queue") else "data"
            verb = {"collection": "reads", "file": "reads"}.get(node_prefix(via), "consumes")
            link(via, key, verb + (" - breaking" if row.get("breaking") else ""), IMPACTED, style)
        nodes[key].status = IMPACTED
    for key, item in nodes.items():
        item.status = cast.participant_status(key) if item.status != IMPACTED else IMPACTED
        item.sub = cast.sub(key)
    lanes = [Lane("people", "People & triggers")]
    impacted_units = {row["unit"] for row in impact_rows}
    present = {cast.lane(k)[5:] for k in nodes if cast.lane(k).startswith("unit:")}
    for unit in world.units():
        if unit not in present:
            continue
        unchanged = all(nodes[k].status == IMPACTED for k in nodes if cast.lane(k) == f"unit:{unit}")
        tag = " - impacted" if unit in impacted_units and unchanged else ""
        lanes.append(Lane(f"unit:{unit}", unit, world.repo_tech(world.repo_of_unit(unit)) + tag))
    lanes += [
        Lane("data", "Data", world.datastore()),
        Lane(
            "messaging",
            "Messaging",
            ", ".join(sorted({world.broker(k) for k in nodes if node_prefix(k) in ("topic", "queue")})),
        ),
        Lane("files", "Files", "inbound / outbound"),
        Lane("external", "External", "outside the graph"),
    ]
    counts = {s: sum(1 for n in nodes.values() if n.status == s) for s in (NEW, CHANGED, IMPACTED)}
    parts = [f"{counts[NEW]} new", f"{counts[CHANGED]} changed"]
    if counts[IMPACTED]:
        parts.append(f"{counts[IMPACTED]} in other repos affected")
    caption = (
        f"Reading: {', '.join(parts)}; every other box is on the path but unchanged. "
        "Labels on arrows are the methods called or the data moved."
    )
    return Flow(
        f"{heading} - flow with impacts", subtitle, lanes, list(nodes.values()), list(links.values()), caption
    )


# -- sequences -----------------------------------------------------------------------------------------------


def _sequence(cast: Cast, walk: Walk, heading: str, subtitle: str, number: int) -> Sequence:
    participants: dict[str, Participant] = {}
    messages: list[Message] = []
    fragments: list[Fragment] = []

    def part(key: str) -> None:
        if key not in participants:
            participants[key] = Participant(
                key,
                cast.label(key),
                cast.sub(key, with_repo=len(cast.world.maps) > 1),
                cast.kind(key),
                cast.participant_status(key) if cast.status.get(key) != IMPACTED else IMPACTED,
            )

    def emit(step: Step) -> None:
        part(step.src)
        part(step.dst)
        kind = "async" if step.style == "async" else "sync"
        messages.append(Message(step.src, step.dst, step.label, kind, step.status, step.note))
        for child in step.children:
            emit(child)
        if step.kind in ("call", "rest"):
            for thrown in step.throws:
                fragments.append(Fragment("alt", f"{thrown} thrown", len(messages), len(messages)))
                messages.append(Message(step.dst, step.src, f"throws {thrown}", "error", step.status))
            returns = "" if step.returns in ("", "void") else step.returns
            messages.append(
                Message(step.dst, step.src, returns, "return", step.status if returns else TOUCHED)
            )

    part(walk.trigger)
    for step in walk.steps:
        emit(step)
    numbered = [m for m in messages if m.kind not in ("return", "error")]
    changed = [str(i) for i, m in enumerate(numbered, 1) if m.status in (NEW, CHANGED, REMOVED)]
    impacted = [str(i) for i, m in enumerate(numbered, 1) if m.status == IMPACTED]
    caption = (
        f"Steps {', '.join(changed)} are what this story adds or changes."
        if changed
        else "No step on this path changes."
    )
    if impacted:
        caption += f" Steps {', '.join(impacted)} reach other repos."
    return Sequence(
        f"{heading} - sequence {number}: {walk.title}",
        f"entry {cast.label('class:' + walk.entry[0])}#{walk.entry[1]} - {subtitle}",
        list(participants.values()),
        messages,
        fragments,
        caption,
    )


# -- low-level design ----------------------------------------------------------------------------------------


def _param(text: str) -> str:
    type_name, _, name = text.rpartition(" ")
    return f"{name}: {type_name}" if type_name else text


def _method_row(m: MethodInfo, status: str) -> Member:
    params = ", ".join(_param(p) for p in m.params)
    tail = f": {m.returns}" if m.returns and m.returns != "void" else ""
    return Member(f"{_VIS.get(m.visibility, '+')} {m.name}({params}){tail}", status, "method")


def _lld(world: World, change: Change, heading: str, subtitle: str) -> ClassDiagram:
    focus = [f for f, s in change.classes.items() if s and world.cls(f) and not world.cls(f).is_value()]
    focus.sort(key=lambda f: (change.classes[f] != NEW, f))
    boxes: dict[str, Box] = {}
    relations: list[Relation] = []

    def collapsed(fqcn: str) -> None:
        if fqcn in boxes or len(boxes) >= MAX_LLD:
            return
        info = world.cls(fqcn)
        if info is None or info.is_value():
            return
        boxes[fqcn] = Box(fqcn, info.name, info.stereotype, CONTEXT, collapsed=True)

    for fqcn in focus:
        info = world.cls(fqcn)
        status = change.classes[fqcn]
        where = f"{info.file.rsplit('/src/main/java/', 1)[-1].split('src/main/java/')[-1]}"
        where = f"{world.unit(info)} - {where}" + (f":{info.start}-{info.end}" if info.start else " (new)")
        box = Box(fqcn, info.name, info.stereotype, status, where)
        for f in info.fields:
            fstatus = change.fields.get((fqcn, f.name), "")
            if status == NEW:
                fstatus = NEW
            box.fields.append(Member(f"{'- ' if f.injected else ''}{f.name}: {f.type}", fstatus, "field"))
        for m in info.methods:
            mstatus = change.methods.get((fqcn, m.name), "")
            if status == NEW:
                mstatus = NEW
            if m.name == info.name and not mstatus:
                continue  # constructors only when they change
            box.methods.append(_method_row(m, mstatus))
        boxes[fqcn] = box
    for fqcn in focus:
        info = world.cls(fqcn)
        for f in info.fields:
            target = _field_target(world, info, f.type)
            if target and target != fqcn:
                collapsed(target)
                if target in boxes:
                    fstatus = change.fields.get((fqcn, f.name), "")
                    relations.append(Relation(fqcn, target, "uses", f.name, fstatus or CONTEXT))
        for parent in info.implements + info.extends:
            if world.cls(parent):
                collapsed(parent)
                if parent in boxes:
                    kind = "implements" if parent in info.implements else "extends"
                    relations.append(Relation(fqcn, parent, kind, "", CONTEXT))
        cmap = world.map_of(fqcn)
        for impl in cmap.impls.get(fqcn, []) if cmap else []:
            collapsed(impl)
            if impl in boxes:
                relations.append(Relation(impl, fqcn, "implements", "", CONTEXT))
        for m in info.methods:
            for call in m.calls:
                key = (fqcn, m.name, call.target, call.method)
                if key in change.new_calls and not any(
                    r.src == fqcn and r.dst == call.target for r in relations
                ):
                    collapsed(call.target)
                    if call.target in boxes:
                        relations.append(Relation(fqcn, call.target, "uses", f"{call.method}()", NEW))
            if change.methods.get((fqcn, m.name)) in (CHANGED, NEW, REMOVED):
                for caller, cm, _call in world.callers(fqcn, m.name)[:3]:
                    if caller.fqcn == fqcn or cm.name == caller.name:
                        continue
                    collapsed(caller.fqcn)
                    if caller.fqcn in boxes and not any(
                        r.src == caller.fqcn and r.dst == fqcn for r in relations
                    ):
                        relations.append(Relation(caller.fqcn, fqcn, "uses", f"{m.name}()", CONTEXT))
    caption = (
        "Highlighted rows are what this story adds or changes; other boxes are collaborators one hop away, "
        "shown without members."
        if focus
        else "No class changes: this story changes data or configuration only."
    )
    return ClassDiagram(
        f"{heading} - low-level design", subtitle, list(boxes.values()), relations, False, caption
    )


def _field_target(world: World, info: ClassInfo, type_name: str) -> str | None:
    base = re.split(r"[<\[]", type_name, maxsplit=1)[0]
    cmap = world.map_of(info.fqcn)
    if cmap is None:
        return None
    candidates = cmap.by_name.get(base, [])
    if len(candidates) == 1:
        return candidates[0]
    package = info.fqcn.rsplit(".", 1)[0]
    same = [c for c in candidates if c.startswith(package)]
    return same[0] if len(same) == 1 else None


# -- data model ----------------------------------------------------------------------------------------------


def _data(
    world: World, change: Change, walks: list[Walk], heading: str, subtitle: str
) -> ClassDiagram | None:
    collections: dict[str, str] = {}
    for walk in walks:
        for step in walk.flat():
            for key in (step.src, step.dst):
                if node_prefix(key) == "collection":
                    collections[node_name(key)] = (
                        strongest(collections.get(node_name(key), ""), step.status)
                        if node_name(key) in collections
                        else step.status
                    )
    for resource, status in change.resources.items():
        if node_prefix(resource) == "collection" and status:
            collections[node_name(resource)] = status
    docs: dict[str, ClassInfo] = {}
    for info in world.classes():
        if info.doc:
            docs.setdefault(info.doc, info)
        if info.doc and change.class_status(info.fqcn):
            collections.setdefault(info.doc, CHANGED)
    if not collections:
        return None
    boxes = []
    for name in sorted(collections):
        info = docs.get(name)
        status = change.resources.get(f"collection:{name}", "")
        if info is not None and change.class_status(info.fqcn):
            status = status or CHANGED
        entry = world.collections.get(name, {})
        indexes = entry.get("compoundIndexes") or []
        sub = f"{info.name} - {world.unit(info)}" if info else "new collection: shape in the design note"
        if indexes:
            sub += f" - indexes: {', '.join(str(i) for i in indexes)}"
        box = Box(f"collection:{name}", name, "collection", status or TOUCHED, sub)
        if info is not None:
            for f in info.fields:
                fstatus = change.fields.get((info.fqcn, f.name), "")
                kind = "key" if f.name in ("id", "_id") else "field"
                text = f"{'PK ' if kind == 'key' else ''}{f.name}: {f.type}"
                box.fields.append(Member(text, fstatus, kind))
        boxes.append(box)
    return ClassDiagram(
        f"{heading} - data model",
        subtitle,
        boxes,
        [],
        True,
        "Collections read or written on this story's paths, with their document fields. "
        "Highlighted fields change.",
    )


# -- use cases -----------------------------------------------------------------------------------------------


def _humanize(name: str) -> str:
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)
    text = " ".join(words).lower()
    return text[:1].upper() + text[1:] if text else name


def _case_label(walk: Walk) -> str:
    title = walk.title
    match = re.match(r"(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", title)
    if match:
        parts = [
            p
            for p in match.group(2).split("/")
            if p and not p.startswith("{") and not re.match(r"v\d+$|api$", p)
        ]
        noun = parts[-1].replace("-", " ") if parts else "resource"
        return f"{_HTTP[match.group(1)]} {noun}"
    if title.startswith(("topic ", "queue ")):
        return f"Handle {title.split(' ', 1)[1]}"
    if title.startswith("job "):
        return f"Run {title.split(' ', 1)[1]}"
    return _humanize(walk.entry[1])


def _usecases(world, change, cast: Cast, walks, spec, impact_rows, heading, subtitle) -> UseCaseDiagram:
    actors: dict[str, Actor] = {}
    cases: list[UseCase] = []
    links: list[UseCaseLink] = []

    def actor(name: str, kind: str, side: str = "left") -> str:
        key = f"actor:{name}"
        actors.setdefault(key, Actor(key, name, kind, side))
        return key

    walk_of_entry = {}
    for walk in walks:
        status = walk_status(walk)
        walk_of_entry[walk.title] = (walk, status)
    if spec is not None and spec.use_cases:
        for i, item in enumerate(spec.use_cases):
            walk = next(
                (
                    w
                    for w in walks
                    if item.entry and (w.title == node_name(item.entry) or item.entry.endswith(w.title))
                ),
                None,
            )
            status = walk_status(walk) if walk else (NEW if item.entry in change.resources else TOUCHED)
            if walk is None and any(item.entry == res for *_x, res in change.new_uses):
                status = NEW
            case_id = f"uc{i}"
            cases.append(UseCase(case_id, item.name, status, node_name(item.entry) if item.entry else ""))
            if item.actor:
                links.append(UseCaseLink(actor(item.actor, "person"), case_id))
        for i, item in enumerate(spec.use_cases):
            for included in item.includes:
                j = next((k for k, c in enumerate(spec.use_cases) if c.name == included), None)
                if j is not None:
                    links.append(UseCaseLink(f"uc{i}", f"uc{j}", "include"))
    else:
        for i, walk in enumerate(walks):
            case_id = f"uc{i}"
            cases.append(UseCase(case_id, _case_label(walk), walk_status(walk), walk.title))
            trigger = walk.trigger
            if trigger.startswith("actor:"):
                name = trigger[6:]
                kind = "person" if cast.kind(trigger) == "person" else "system"
                links.append(UseCaseLink(actor(name, kind), case_id))
            else:
                info = world.cls(trigger[6:]) if trigger.startswith("class:") else None
                links.append(
                    UseCaseLink(actor(world.unit(info) if info else cast.label(trigger), "system"), case_id)
                )
    by_repo: dict[str, set[str]] = {}
    for row in impact_rows:
        by_repo.setdefault(row["unit"], set()).add(row["via"])
    for repo, vias in sorted(by_repo.items()):
        key = actor(repo, "system", "right")
        for i, walk in enumerate(walks):
            touched = {s.dst for s in walk.flat()} | {s.src for s in walk.flat()}
            if touched & vias and i < len(cases):
                links.append(UseCaseLink(key, cases[i].id))
    caption = (
        "Who starts each behaviour this story touches (left) and which other systems are affected (right)."
    )
    return UseCaseDiagram(
        f"{heading} - use cases", subtitle, world.profile.name, list(actors.values()), cases, links, caption
    )


def walk_status(walk: Walk | None) -> str:
    if walk is None:
        return TOUCHED
    statuses = [s.status for s in walk.flat()]
    if statuses and statuses[0] == NEW:
        return NEW
    worst = strongest(*statuses) if statuses else TOUCHED
    return CHANGED if worst in (NEW, CHANGED, REMOVED) else (IMPACTED if worst == IMPACTED else TOUCHED)


# -- touch points --------------------------------------------------------------------------------------------


def _touch(world: World, change: Change, walks: list[Walk]) -> list[dict]:
    reached: dict[str, list[str]] = {}

    def mark(key: str, title: str) -> None:
        reached.setdefault(key, [])
        if title not in reached[key]:
            reached[key].append(title)

    for walk in walks:
        mark(f"{walk.entry[0]}#{walk.entry[1]}", walk.title)
        for step in walk.flat():
            for key in (step.src, step.dst):
                mark(key, walk.title)
            if step.method and step.dst.startswith("class:"):
                mark(f"{step.dst[6:]}#{step.method}", walk.title)
                impl = world.implementation(step.dst[6:])
                mark(f"{impl}#{step.method}", walk.title)
    rows = []
    for (fqcn, name), status in sorted(change.methods.items()):
        if not status:
            continue
        info = world.cls(fqcn)
        m = world.method(fqcn, name)
        lines = change.lines.get((fqcn, name)) or (f"{m.start}-{m.end}" if m and m.start else "new")
        row = _row(
            info,
            f"{info.name}#{name}" if info else f"{fqcn}#{name}",
            status,
            lines,
            reached,
            fqcn,
            _unit(world, info),
        )
        row["reachedFrom"] = reached.get(f"{fqcn}#{name}", [])
        rows.append(row)
    for (fqcn, name), status in sorted(change.fields.items()):
        info = world.cls(fqcn)
        if not status or info is None or change.classes.get(fqcn) == NEW:
            continue
        f = next((x for x in info.fields if x.name == name), None)
        rows.append(
            _row(
                info,
                f"{info.name}.{name}",
                status,
                str(f.line) if f and f.line else "new",
                reached,
                fqcn,
                _unit(world, info),
            )
        )
    for fqcn, status in sorted(change.classes.items()):
        info = world.cls(fqcn)
        if info is None or not status:
            continue
        has_member = any(k[0] == fqcn for k, s in change.methods.items() if s)
        if status == NEW or not has_member:
            lines = "new" if status == NEW else f"{info.start}-{info.end}"
            rows.append(_row(info, info.name, status, lines, reached, fqcn, _unit(world, info)))
    for resource, status in sorted(change.resources.items()):
        if status:
            rows.append(
                {
                    "status": status,
                    "repo": "",
                    "element": resource,
                    "file": "",
                    "lines": "",
                    "reachedFrom": reached.get(resource, []),
                    "tests": [],
                }
            )
    order = {NEW: 0, CHANGED: 1, REMOVED: 2}
    return sorted(rows, key=lambda r: (order.get(r["status"], 3), r["repo"], r["element"]))


def _unit(world: World, info: ClassInfo | None) -> str:
    return world.unit(info) if info else ""


def _row(
    info: ClassInfo | None, element: str, status: str, lines: str, reached: dict, fqcn: str, unit: str = ""
) -> dict:
    return {
        "status": status,
        "repo": unit,
        "element": element,
        "file": info.file if info else "",
        "lines": lines,
        "reachedFrom": reached.get(f"class:{fqcn}", []),
        "tests": [t.rsplit("/", 1)[-1] for t in (info.tests if info else [])],
    }
