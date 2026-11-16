"""Walks the code from an entry point: the call tree every story diagram is read from.

A step is a call between classes, a read or write of a collection, a message to a topic or queue, a REST
call into another repo, or a file. The walk follows the AST's calls (through an interface to its one
implementation), the graph's resource edges for each method, and across repos through endpoints and topics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from baton.diagram.change import Change
from baton.diagram.codemap import ENTRY_KINDS, ClassInfo, MethodInfo, read_write
from baton.diagram.shapes import IMPACTED, NEW, TOUCHED, strongest
from baton.diagram.world import World
from baton.graph.model import node_name, node_prefix

MAX_DEPTH = 7
MAX_STEPS = 48
COMPONENT = {
    "controller",
    "service",
    "component",
    "repository",
    "adapter",
    "client",
    "publisher",
    "listener",
    "config",
    "interface",
    "class",
    "application",
    "ui",
    "screen",
    "hook",
}
_VERB = {
    "READS_COLLECTION": "read",
    "WRITES_COLLECTION": "write",
    "PUBLISHES": "publish",
    "CONSUMES": "consume",
    "READS_FILE": "read file",
    "WRITES_FILE": "write file",
    "CALLS_ENDPOINT": "call",
}


@dataclass
class Step:
    kind: str  # call | self | data | publish | deliver | rest | entry
    src: str  # participant key: class:<fqcn>, a resource id, actor:<name>
    dst: str
    label: str
    status: str = TOUCHED
    returns: str = ""
    throws: list[str] = field(default_factory=list)
    children: list[Step] = field(default_factory=list)
    note: str = ""
    method: str = ""  # the method entered at dst, when dst is a class

    @property
    def style(self) -> str:
        if self.kind in ("publish", "deliver"):
            return "async"
        if self.kind == "data":
            return "data"
        return "sync"

    def size(self) -> int:
        return 1 + sum(c.size() for c in self.children)

    def worst(self) -> str:
        return strongest(self.status, *[c.worst() for c in self.children])


@dataclass
class Walk:
    entry: tuple[str, str]  # (fqcn, method)
    title: str  # what starts it: "POST /api/v1/...", "topic order.events", "job nightlyReportJob"
    trigger: str  # actor key that starts it
    steps: list[Step]
    collapsed: int = 0  # subtrees folded because the walk was long

    def flat(self) -> list[Step]:
        out = []

        def visit(steps):
            for step in steps:
                out.append(step)
                visit(step.children)

        visit(self.steps)
        return out


def short_sig(method: MethodInfo | None, name: str) -> str:
    if method is None:
        return f"{name}()"
    return f"{method.name}({', '.join(p.split(' ')[-1] for p in method.params)})"


class Walker:
    def __init__(self, world: World, change: Change, impacted: dict[str, list[dict]]):
        self.world = world
        self.change = change
        self.impacted = impacted  # resource id -> impact rows (other repos reading it)

    # -- statuses --

    def class_status(self, fqcn: str) -> str:
        return self.change.class_status(fqcn) or TOUCHED

    def resource_status(self, resource: str) -> str:
        return self.change.resources.get(resource, TOUCHED)

    def call_status(self, caller: str, cm: str, target: str, method: str) -> str:
        if (caller, cm, target, method) in self.change.new_calls:
            return NEW
        status = self.change.method_status(target, method)
        if not status:
            for iface, impl in ((target, self.world.implementation(target)),):
                status = self.change.method_status(impl, method) or self.change.method_status(iface, method)
        return status or TOUCHED

    # -- the walk --

    def walk(self, fqcn: str, method: str) -> Walk:
        info = self.world.cls(fqcn)
        m = self.world.method(fqcn, method)
        title, trigger, prefix = self.trigger(info, m)
        body = self.body(info, m, 1, {(fqcn, method)})
        if prefix:
            prefix[-1].children = body
            steps = prefix[:1]
            for a, b in zip(prefix, prefix[1:], strict=False):
                a.children = [b]
        else:
            steps = body
        result = Walk((fqcn, method), title, trigger, steps)
        total = sum(s.size() for s in steps)
        if total > MAX_STEPS:
            result.collapsed = _fold(steps, total)
        return result

    def trigger(self, info: ClassInfo, m: MethodInfo | None) -> tuple[str, str, list[Step]]:
        """(title, actor key, steps leading to the entry method)."""
        key = f"class:{info.fqcn}"
        entries = m.entries if m else []
        entry = entries[0] if entries else None
        persona = self.world.profile.personas[0] if self.world.profile.personas else "User"
        status = self.call_status("", "", info.fqcn, m.name if m else "")
        if entry and entry.kind == "EXPOSES":
            label = node_name(entry.resource)
            callers = [
                e for e in self.world.edges_to(entry.resource, "CALLS_ENDPOINT") if e.repo != info.repo
            ]
            if callers:
                chain = self.ui_chain(callers[0])
                steps = []
                actor = f"actor:{persona}"
                previous = actor
                for module, call_label in chain:
                    steps.append(Step("call", previous, f"class:{module}", call_label, TOUCHED))
                    previous = f"class:{module}"
                steps.append(
                    Step("rest", previous, key, label, status, _reply(m), method=m.name if m else "")
                )
                return label, actor, steps
            actor = f"actor:{persona}"
            return (
                label,
                actor,
                [Step("rest", actor, key, label, status, _reply(m), method=m.name if m else "")],
            )
        if entry and entry.kind == "CONSUMES":
            resource = entry.resource
            publishers = [e for e in self.world.edges_to(resource, "PUBLISHES")]
            steps = []
            if publishers:
                pub = publishers[0]
                source = pub.src
                trigger_key = source
                steps.append(Step("publish", source, resource, "publish", self.resource_status(resource)))
            else:
                trigger_key = f"actor:publisher of {node_name(resource)}"
                steps.append(
                    Step("publish", trigger_key, resource, "publish", self.resource_status(resource))
                )
            steps.append(
                Step(
                    "deliver",
                    resource,
                    key,
                    f"{m.name}(...)" if m else "deliver",
                    status,
                    method=m.name if m else "",
                )
            )
            return f"{node_prefix(resource)} {node_name(resource)}", trigger_key, steps
        if entry and entry.kind == "RUNS_JOB":
            actor = "actor:Scheduler"
            return (
                f"job {node_name(entry.resource)}",
                actor,
                [Step("call", actor, key, f"run {node_name(entry.resource)}", status, method=m.name)],
            )
        if m and {"Scheduled"} & set(m.annotations):
            actor = "actor:Scheduler"
            return (
                f"scheduled {info.name}#{m.name}",
                actor,
                [Step("call", actor, key, short_sig(m, m.name), status, method=m.name)],
            )
        callers = self.world.callers(info.fqcn, m.name if m else None)
        actor = "actor:caller"
        return (
            f"{info.name}#{m.name if m else '?'}",
            actor,
            [Step("call", actor, key, short_sig(m, m.name if m else "?"), status, m.returns if m else "")]
            if not callers
            else [Step("call", f"class:{callers[0][0].fqcn}", key, short_sig(m, m.name), status)],
        )

    def ui_chain(self, edge) -> list[tuple[str, str]]:
        """[(module, the call into it)] from the top screen down to the UI module that calls the endpoint."""
        cmap = self.world.maps.get(edge.repo)
        modules = [node_name(edge.src)]
        labels: list[str] = []
        while cmap is not None:
            callers = [c for c in cmap.callers(modules[0]) if c[0].fqcn not in modules]
            if not callers:
                break
            caller, _, call = callers[0]
            modules.insert(0, caller.fqcn)
            labels.insert(0, f"{call.method}()")
        return [(modules[0], "open")] + [(modules[i + 1], labels[i]) for i in range(len(labels))]

    def body(self, info: ClassInfo | None, m: MethodInfo | None, depth: int, stack: set) -> list[Step]:
        if info is None or m is None:
            return []
        key = f"class:{info.fqcn}"
        events: list[tuple[float, int, object]] = []
        for call in m.calls:
            events.append((call.line, 0, call))
        for use in m.uses:
            if use.kind not in ENTRY_KINDS:
                events.append((use.line, 1, use))
        if info.stereotype == "config" and any(u.kind == "RUNS_JOB" for u in m.uses):
            for other in info.methods:  # a batch job's steps are wired by bean methods, not calls
                if other is not m:
                    for use in other.uses:
                        if use.kind not in ENTRY_KINDS:
                            events.append((use.line, 1, use))
        steps: list[Step] = []
        for _, kind, item in sorted(events, key=lambda e: (e[0], e[1])):
            if kind == 0:
                step = self.call_step(info, m, item, depth, stack)
            else:
                step = self.use_step(key, info, m, item, depth, stack)
            if step is not None:
                steps.append(step)
        return steps

    def call_step(self, info: ClassInfo, m: MethodInfo, call, depth: int, stack: set) -> Step | None:
        if call.via == "new":
            return None
        target = self.world.implementation(call.target)
        tcls = self.world.cls(target)
        if tcls is None or tcls.is_value():
            return None
        status = self.call_status(info.fqcn, m.name, call.target, call.method)
        if tcls.stereotype not in COMPONENT and status == TOUCHED:
            return None
        if call.via in ("param", "local") and tcls.stereotype in ("class", "dto") and status == TOUCHED:
            return None
        tm = self.world.method(target, call.method) or self.world.method(call.target, call.method)
        if call.via == "self":
            step = Step(
                "self",
                f"class:{info.fqcn}",
                f"class:{info.fqcn}",
                short_sig(tm, call.method),
                status,
                method=call.method,
            )
        else:
            step = Step(
                "call",
                f"class:{info.fqcn}",
                f"class:{target}",
                short_sig(tm, call.method),
                status,
                tm.returns if tm else "",
                list(tm.throws) if tm else [],
                method=call.method,
            )
        key = (target, call.method)
        if tm is not None and depth < MAX_DEPTH and key not in stack:
            step.children = self.body(tcls, tm, depth + 1, stack | {key})
        elif tm is None or not (tm.calls or tm.uses):
            verb = read_write(tcls, call.method)
            if verb:
                for use in tcls.uses:
                    if use.kind in ("READS_COLLECTION", "WRITES_COLLECTION"):
                        step.children.append(
                            Step(
                                "data",
                                f"class:{target}",
                                use.resource,
                                f"{call.method} -> {_VERB[verb]}",
                                self.resource_status(use.resource),
                            )
                        )
                        break
        return step

    def use_step(self, key: str, info: ClassInfo, m: MethodInfo, use, depth: int, stack: set) -> Step | None:
        resource = use.resource
        is_new = (info.fqcn, m.name, use.kind, resource) in self.change.new_uses
        status = NEW if is_new else self.resource_status(resource)
        if use.kind in ("READS_COLLECTION", "WRITES_COLLECTION", "READS_FILE", "WRITES_FILE"):
            step = Step("data", key, resource, _VERB[use.kind], status)
            if use.kind in ("WRITES_COLLECTION", "WRITES_FILE"):
                self.notes_for(step, resource)
            return step
        if use.kind == "PUBLISHES":
            step = Step("publish", key, resource, "publish", status)
            for edge in self.world.edges_to(resource, "CONSUMES"):
                consumer, cm = self.world.owner(edge)
                if consumer is None:
                    continue
                other = self.world.unit_of(edge.repo, edge.file) != self.world.unit(info)
                hit = resource in self.impacted or other and self.change.resources.get(resource)
                cstatus = IMPACTED if hit and other else self.class_status(consumer.fqcn)
                step.children.append(
                    Step(
                        "deliver",
                        resource,
                        f"class:{consumer.fqcn}",
                        f"{cm.name}(...)" if cm else "deliver",
                        cstatus,
                        note=f"in {self.world.unit_of(edge.repo, edge.file)}" if other else "",
                    )
                )
            return step
        if use.kind == "CALLS_ENDPOINT":
            providers = self.world.edges_to(resource, "EXPOSES")
            label = node_name(resource)
            if providers:
                provider, pm = self.world.owner(providers[0])
                if provider is not None:
                    step = Step(
                        "rest",
                        key,
                        f"class:{provider.fqcn}",
                        label,
                        status,
                        pm.returns if pm else "",
                        method=pm.name if pm else "",
                    )
                    pkey = (provider.fqcn, pm.name if pm else "")
                    if pm is not None and depth < MAX_DEPTH - 1 and pkey not in stack:
                        step.children = self.body(provider, pm, depth + 1, stack | {pkey})
                    return step
            return Step("rest", key, resource, label, status)
        return None

    def notes_for(self, step: Step, resource: str) -> None:
        rows = self.impacted.get(resource, [])
        repos = sorted({row["unit"] for row in rows})
        if repos:
            step.note = "read by " + ", ".join(repos)
            if step.status == TOUCHED and any(row.get("breaking") for row in rows):
                step.status = IMPACTED


def _reply(m: MethodInfo | None) -> str:
    if m is None or m.returns in ("", "void"):
        return "200"
    return f"200 {m.returns}"


def _fold(steps: list[Step], total: int) -> int:
    """Long walks: fold the deepest subtrees that change nothing until the walk fits."""
    folded = 0

    def candidates(items, depth):
        for step in items:
            if step.children and step.worst() in (TOUCHED,) and depth >= 2:
                yield depth, step
            yield from candidates(step.children, depth + 1)

    for _depth, step in sorted(candidates(steps, 1), key=lambda c: -c[0]):
        if total <= MAX_STEPS:
            break
        removed = step.size() - 1
        step.children = []
        step.note = step.note or "... unchanged, folded"
        total -= removed
        folded += 1
    return folded


def entries_for(world: World, change: Change) -> list[tuple[str, str]]:
    """The entry points whose walks reach something this story changes: declared ones first, else found by
    walking callers up from every changed method to a method that something outside the code starts."""
    if change.entries:
        return list(dict.fromkeys(change.entries))
    targets: set[tuple[str, str]] = {k for k, s in change.methods.items() if s}
    for fqcn, status in change.classes.items():
        if status and not any(k[0] == fqcn for k in targets):
            info = world.cls(fqcn)
            if info:
                targets |= {(fqcn, m.name) for m in info.methods if m.visibility in ("public", "")}
    for resource, status in change.resources.items():
        if status:
            for info in world.classes():
                for m in info.methods:
                    if any(u.resource == resource for u in m.uses):
                        targets.add((info.fqcn, m.name))
    found: list[tuple[str, str]] = []
    for target in sorted(targets):
        seen = {target}
        frontier = [target]
        roots = []
        while frontier:
            fqcn, name = frontier.pop(0)
            m = world.method(fqcn, name)
            callers = world.callers(fqcn, name)
            info = world.cls(fqcn)
            if info is not None:
                for parent in info.implements:
                    callers += world.callers(parent, name)
            if (m is not None and m.is_entry()) or not callers:
                roots.append((fqcn, name))
                continue
            for caller, cm, _ in callers:
                key = (caller.fqcn, cm.name)
                if key not in seen and cm.name != caller.name:  # constructors are not entry paths
                    seen.add(key)
                    frontier.append(key)
        for root in roots:
            if root not in found:
                found.append(root)
    entries = [e for e in found if (world.method(*e) and world.method(*e).is_entry())]
    rest = [e for e in found if e not in entries]
    return entries + [e for e in rest if not entries]
