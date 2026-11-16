"""Lift the code map into operations and effects.

An operation is one method, keyed by its signature so overloads stay apart. Its effects are the data and
message resources it reads, writes, publishes, consumes or calls over HTTP, found directly in its body or
through the behavioural calls it makes (an interface call follows its one implementation). Calls into data
carriers (DTOs, documents, records, enums) and trivial accessors are noise for this purpose and are left out.
Everything is computed from the AST and the graph edges; nothing is guessed. A call the AST cannot place on
one overload or one implementation lands on every candidate and is marked ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from baton.diagram.codemap import ClassInfo, MethodInfo, read_write
from baton.diagram.world import World
from baton.graph.model import node_name

EFFECT_KINDS = (
    "READS_COLLECTION",
    "WRITES_COLLECTION",
    "PUBLISHES",
    "CALLS_ENDPOINT",
    "READS_FILE",
    "WRITES_FILE",
)
ENTRY_KINDS = ("EXPOSES", "CONSUMES", "RUNS_JOB")
_SCHEDULED = {"Scheduled", "EventListener", "KafkaListener", "JmsListener", "RabbitListener", "SqsListener"}
_ACCESSOR = re.compile(r"^(get|is|has|set|with)[A-Z_]")


@dataclass
class Effect:
    kind: str
    resource: str  # node id, e.g. collection:approvals
    via: str  # "" when the operation does it itself, else the first call that leads to it (Class#method)
    file: str
    line: int
    own: bool = False  # in the operation's own body or a repository call it makes itself


@dataclass
class Op:
    info: ClassInfo
    m: MethodInfo

    @property
    def key(self) -> str:
        return op_key(self.info, self.m)

    @property
    def label(self) -> str:
        return f"{self.info.name}#{self.m.name}"

    def is_entry(self) -> bool:
        return bool(self.m.entries) or bool(_SCHEDULED & set(self.m.annotations))


def op_key(info: ClassInfo, m: MethodInfo) -> str:
    types = ",".join(p.rsplit(" ", 1)[0] for p in m.params)
    return f"{info.fqcn}#{m.name}({types})"


def _types(m: MethodInfo) -> tuple[str, ...]:
    return tuple(p.rsplit(" ", 1)[0].split("<", 1)[0] for p in m.params)


def behavioural(info: ClassInfo | None) -> bool:
    return info is not None and not info.is_value() and info.stereotype != "config"


def trivial(m: MethodInfo) -> bool:
    """A getter, setter or one-line delegate with no data effect of its own."""
    return not m.uses and len(m.calls) <= 1 and m.end - m.start <= 3


@dataclass
class Step:
    target: str  # the class as called (an interface stays the interface)
    method: str
    line: int
    ops: list[str] = field(default_factory=list)  # operation keys it can land on
    ambiguous: bool = False


class IR:
    """Operations, the steps between them, effects (direct and lifted) and callers. Built once per world."""

    def __init__(self, world: World):
        self.world = world
        self.ops: dict[str, Op] = {}
        self.by_class: dict[str, list[str]] = {}
        for info in world.classes():
            if info.kind != "module" and not behavioural(info):
                continue
            for m in info.methods:
                if m.name == info.name and info.kind != "module":
                    continue  # constructors wire, they do not act
                op = Op(info, m)
                self.ops[op.key] = op
                self.by_class.setdefault(info.fqcn, []).append(op.key)
        self.steps: dict[str, list[Step]] = {key: self._steps(op) for key, op in self.ops.items()}
        self.callers: dict[str, list[tuple[str, int]]] = {}
        for key, steps in self.steps.items():
            for step in steps:
                for target in step.ops:
                    if target != key:
                        self.callers.setdefault(target, []).append((key, step.line))
        self._effects: dict[str, list[Effect]] = {}

    # -- calls ---------------------------------------------------------------------------------------------

    def _candidates(self, target: str) -> tuple[list[str], bool]:
        """The classes a call on `target` can run in: the class, or the implementations of an interface."""
        cmap = self.world.map_of(target)
        if cmap is None:
            return [], False
        impls = cmap.impls.get(target, [])
        info = cmap.classes[target]
        if info.kind == "interface" and impls:
            return impls, len(impls) > 1
        return [target], False

    def _resolve(self, target: str, method: str, arity: int) -> tuple[list[str], bool]:
        info = self.world.cls(target)
        if info is not None and info.kind == "module":  # a TypeScript file: its one body holds every export
            return list(self.by_class.get(target, [])), False
        classes, ambiguous = self._candidates(target)
        declared = {
            _types(self.ops[k].m)
            for k in self.by_class.get(target, [])
            if self.ops[k].m.name == method and self.ops[k].m.accepts(arity)
        }
        found: list[str] = []
        for fqcn in classes:
            keys = [k for k in self.by_class.get(fqcn, []) if self.ops[k].m.name == method]
            fitting = [k for k in keys if self.ops[k].m.accepts(arity)]
            if fqcn != target and declared:  # through an interface: the overload it declares
                fitting = [k for k in fitting if _types(self.ops[k].m) in declared] or fitting
            found += fitting or keys  # an unmarked varargs overload still counts
            if len(fitting or keys) > 1:
                ambiguous = True
        if not found and target in self.by_class:  # an interface method with no implementation in the repo
            found = [k for k in self.by_class[target] if self.ops[k].m.name == method]
        return found, ambiguous

    def _steps(self, op: Op) -> list[Step]:
        out = []
        for call in op.m.calls:
            if call.method == "<init>":
                continue
            info = self.world.cls(call.target)
            if not behavioural(info):
                continue
            ops, ambiguous = self._resolve(call.target, call.method, call.arity)
            if not ops and info.stereotype != "repository" and _ACCESSOR.match(call.method):
                continue
            out.append(Step(call.target, call.method, call.line, ops, ambiguous))
        return out

    def noise(self, step: Step) -> bool:
        """A call worth hiding from a reader: it lands only on trivial methods that reach no data."""
        info = self.world.cls(step.target)
        if info is not None and info.stereotype == "repository":
            return False
        reach = self._reach()
        return bool(step.ops) and all(trivial(self.ops[k].m) and not reach[k] for k in step.ops)

    # -- effects -------------------------------------------------------------------------------------------

    def _repository(self, step: Step) -> list[Effect]:
        """A call into a Spring Data repository reads or writes the collections the repository is bound to."""
        info = self.world.cls(step.target)
        if info is None or info.stereotype != "repository":
            return []
        kind = read_write(info, step.method)
        return [
            Effect(kind, use.resource, "", info.file, use.line)
            for use in info.uses
            if use.resource.startswith("collection:")
        ]

    def _own(self, key: str) -> list[Effect]:
        """What the operation does itself, a repository call counted as its own read or write."""
        op = self.ops[key]
        out = [
            Effect(u.kind, u.resource, "", op.info.file, u.line, True)
            for u in op.m.uses
            if u.kind in EFFECT_KINDS
        ]
        for step in self.steps[key]:
            hop = f"{_short(step.target)}#{step.method}"
            out += [
                Effect(e.kind, e.resource, hop, op.info.file, step.line, True) for e in self._repository(step)
            ]
        return out

    def _reach(self) -> dict[str, set[tuple[str, str]]]:
        """(kind, resource) reachable from each operation. Strongly connected components first, so recursion
        and mutual calls get exact results, then each component unions its successors."""
        if hasattr(self, "_reached"):
            return self._reached
        index: dict[str, int] = {}
        low: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        component: dict[str, int] = {}
        members: list[list[str]] = []
        counter = 0
        succ = {key: [t for step in steps for t in step.ops] for key, steps in self.steps.items()}
        for root in self.ops:
            if root in index:
                continue
            work = [(root, 0)]
            while work:
                node, i = work.pop()
                if i == 0:
                    index[node] = low[node] = counter
                    counter += 1
                    stack.append(node)
                    on_stack.add(node)
                targets = succ[node]
                if i < len(targets):
                    work.append((node, i + 1))
                    nxt = targets[i]
                    if nxt not in index:
                        work.append((nxt, 0))
                    elif nxt in on_stack:
                        low[node] = min(low[node], index[nxt])
                    continue
                for t in targets:
                    if t in on_stack:
                        low[node] = min(low[node], low[t])
                if low[node] == index[node]:
                    group = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component[member] = len(members)
                        group.append(member)
                        if member == node:
                            break
                    members.append(group)
        # Tarjan emits components in reverse topological order: successors are complete before callers.
        reach_of: list[set[tuple[str, str]]] = []
        for group in members:
            found: set[tuple[str, str]] = set()
            for member in group:
                found |= {(e.kind, e.resource) for e in self._own(member)}
                for step in self.steps[member]:
                    for t in step.ops:
                        if component[t] != component[member]:
                            found |= reach_of[component[t]]
            reach_of.append(found)
        self._reached = {key: reach_of[component[key]] for key in self.ops}
        return self._reached

    def effects(self, key: str) -> list[Effect]:
        """Every effect of an operation: its own, then those reached through its calls, each with the first
        call that leads to it."""
        if key in self._effects:
            return self._effects[key]
        reach = self._reach()
        op = self.ops[key]
        out: dict[tuple[str, str], Effect] = {}
        for effect in self._own(key):
            out.setdefault((effect.kind, effect.resource), effect)
        for step in self.steps[key]:
            hop = f"{_short(step.target)}#{step.method}"
            for target in step.ops:
                for kind, resource in sorted(reach[target]):
                    out.setdefault((kind, resource), Effect(kind, resource, hop, op.info.file, step.line))
        result = sorted(out.values(), key=lambda e: (e.kind, e.resource))
        self._effects[key] = result
        return result

    # -- reach ---------------------------------------------------------------------------------------------

    def entry_points(self, key: str, limit: int = 8) -> list[str]:
        """The entry operations (endpoint, listener, job, schedule) whose calls reach this one."""
        if self.ops[key].is_entry():
            return [key]
        seen, todo, found = {key}, [key], []
        while todo and len(found) < limit:
            current = todo.pop(0)
            for caller, _line in self.callers.get(current, []):
                if caller in seen:
                    continue
                seen.add(caller)
                if self.ops[caller].is_entry():
                    found.append(caller)
                else:
                    todo.append(caller)
        return sorted(found)[:limit]

    def entry_label(self, key: str) -> str:
        op = self.ops[key]
        if op.m.entries:
            return f"{_entry_text(op.m.entries[0].resource)} ({op.label})"
        tag = next((a for a in op.m.annotations if a in _SCHEDULED), "entry")
        return f"@{tag} ({op.label})"

    # -- lookups -------------------------------------------------------------------------------------------

    def implementations(self, key: str) -> list[str]:
        """For an interface operation, the operations that implement it; else none."""
        op = self.ops[key]
        if op.info.kind != "interface":
            return []
        found, _ = self._resolve(op.info.fqcn, op.m.name, len(op.m.params))
        return [k for k in found if k != key]

    def ops_of(self, info: ClassInfo) -> list[Op]:
        return [self.ops[k] for k in self.by_class.get(info.fqcn, [])]

    def users_of(self, resource: str) -> list[tuple[Op, Effect]]:
        """Operations with an effect on (or an entry at) a resource, direct users first."""
        out = []
        for key, op in self.ops.items():
            for use in op.m.uses:
                if use.resource == resource and use.kind in ENTRY_KINDS:
                    out.append((op, Effect(use.kind, resource, "", op.info.file, use.line)))
            for effect in self.effects(key):
                if effect.resource == resource:
                    out.append((op, effect))
        return sorted(out, key=lambda item: (bool(item[1].via), item[1].kind, item[0].key))


def _short(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def _entry_text(resource: str) -> str:
    if resource.startswith("endpoint:"):
        return resource.split(":", 1)[1]
    return resource


def resource_name(resource: str) -> str:
    return node_name(resource)
