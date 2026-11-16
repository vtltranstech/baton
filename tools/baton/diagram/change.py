"""A story's change as statuses on the code map: from a spec (the design) or from a diff (what was built).

The spec is applied to a copy of the world's code maps: new classes, methods, fields and calls are added, so
the walks and every diagram see the proposed code exactly as they see the real code.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from baton.diagram.codemap import Call, ClassInfo, CodeMap, FieldInfo, MethodInfo, Use
from baton.diagram.shapes import CHANGED, NEW, REMOVED, strongest
from baton.diagram.spec import RESOURCE_PREFIXES, Ref, Spec, suggest
from baton.diagram.world import World
from baton.graph.model import node_prefix

_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Change:
    methods: dict[tuple[str, str], str] = field(default_factory=dict)  # (fqcn, method) -> status
    classes: dict[str, str] = field(default_factory=dict)
    fields: dict[tuple[str, str], str] = field(default_factory=dict)
    resources: dict[str, str] = field(default_factory=dict)
    new_calls: set[tuple[str, str, str, str]] = field(default_factory=set)  # caller, method, target, method
    new_uses: set[tuple[str, str, str, str]] = field(default_factory=set)  # caller, method, kind, resource
    breaking: set[str] = field(default_factory=set)
    entries: list[tuple[str, str]] = field(default_factory=list)  # declared entry points
    source: str = ""  # "spec" or "diff"
    lines: dict[tuple[str, str], str] = field(default_factory=dict)  # (fqcn, method) -> "12-30" as built

    def class_status(self, fqcn: str) -> str:
        return self.classes.get(fqcn, "")

    def method_status(self, fqcn: str, name: str) -> str:
        return self.methods.get((fqcn, name), "")

    def touched_classes(self) -> set[str]:
        return {c for c, s in self.classes.items() if s}

    def mark_class(self, fqcn: str, status: str) -> None:
        current = self.classes.get(fqcn, "")
        if current == NEW:
            return
        self.classes[fqcn] = status if not current else strongest(current, status)


def copy_maps(world: World) -> None:
    """The spec writes into the maps; a copy keeps the cache files and other runs clean."""
    world.maps = {repo: CodeMap.from_json(cmap.to_json()) for repo, cmap in world.maps.items()}


class _Resolver:
    def __init__(self, world: World, spec: Spec, problems: list[str]):
        self.world = world
        self.spec = spec
        self.problems = problems

    def classes_named(self, name: str) -> list[str]:
        found = []
        for info in self.world.classes():
            if (
                info.fqcn == name
                or (("." not in name) and info.name == name)
                or info.fqcn.endswith("." + name)
            ):
                found.append(info.fqcn)
        return found

    def cls(self, name: str, where: str) -> str | None:
        found = self.classes_named(name)
        if len(found) == 1:
            return found[0]
        if not found:
            names = [c.name for c in self.world.classes()]
            self.problems.append(
                f"{where}: no class {name} in the code{suggest(name.rsplit('.', 1)[-1], names)}"
            )
            return None
        if self.spec.repo:
            mine = [f for f in found if self.world.map_of(f) and self.world.map_of(f).repo == self.spec.repo]
            if len(mine) == 1:
                return mine[0]
        self.problems.append(f"{where}: {name} is ambiguous; write the full name: {', '.join(found)}")
        return None

    def method(self, ref: Ref, where: str) -> tuple[str, str] | None:
        if ref.kind != "method":
            self.problems.append(f"{where}: {ref.text} is not Class#method")
            return None
        owner = self.cls(ref.owner, where)
        if owner is None:
            return None
        info = self.world.cls(owner)
        if not info.method(ref.member):
            target = self.world.implementation(owner)
            impl = self.world.cls(target)
            if impl is not None and impl.method(ref.member):
                return target, ref.member
            names = sorted({m.name for m in info.methods})
            self.problems.append(
                f"{where}: {info.name} has no method {ref.member}{suggest(ref.member, names)}"
                + ("" if names else f" ({info.name} declares no methods)")
            )
            return None
        return owner, ref.member

    def field(self, ref: Ref, where: str) -> tuple[str, str] | None:
        owner = self.cls(ref.owner, where)
        if owner is None:
            return None
        info = self.world.cls(owner)
        if not any(f.name == ref.member for f in info.fields):
            names = [f.name for f in info.fields]
            self.problems.append(
                f"{where}: {info.name} has no field {ref.member}{suggest(ref.member, names)}"
            )
            return None
        return owner, ref.member

    def resource(self, text: str, where: str, must_exist: bool) -> str | None:
        if node_prefix(text) not in RESOURCE_PREFIXES:
            self.problems.append(
                f"{where}: {text} is not a resource id (collection:, topic:, queue:, endpoint:, file:, job:)"
            )
            return None
        if must_exist and text not in self.world.nodes():
            same_kind = [n for n in self.world.nodes() if node_prefix(n) == node_prefix(text)]
            self.problems.append(f"{where}: {text} is not in the graph{suggest(text, same_kind)}")
            return None
        return text


def _repo_for(world: World, fqcn: str, hint: str) -> str | None:
    if hint:
        return hint if hint in world.maps else None
    best, best_len = None, -1
    for info in world.classes():
        common = os.path.commonprefix([info.fqcn.split("."), fqcn.split(".")])
        if len(common) > best_len:
            best, best_len = info.repo, len(common)
    return best


def _short_params(params: list[str]) -> str:
    return ", ".join(p.split(" ")[-1] for p in params)


def apply_spec(world: World, spec: Spec) -> tuple[Change, list[str]]:
    copy_maps(world)
    problems: list[str] = []
    change = Change(source="spec")
    r = _Resolver(world, spec, problems)
    # 1. new classes
    for item in spec.new_classes:
        if "." not in item.name:
            problems.append(
                f"new class {item.name}: give its full name (package.{item.name}) so it can be placed"
            )
            continue
        if world.cls(item.name):
            problems.append(f"new class {item.name} already exists: list it under changed")
            continue
        repo = _repo_for(world, item.name, item.repo or spec.repo)
        if repo is None:
            problems.append(
                f"new class {item.name}: repo {item.repo or spec.repo!r} is not in profile/project.md"
            )
            continue
        simple = item.name.rsplit(".", 1)[-1]
        kind = "interface" if item.stereotype in ("interface", "port") else "class"
        neighbour = max(
            (c for c in world.maps[repo].classes.values() if "src/main/java/" in c.file),
            key=lambda c: len(os.path.commonprefix([c.fqcn.split("."), item.name.split(".")])),
            default=None,
        )
        prefix = neighbour.file.split("src/main/java/", 1)[0] if neighbour else ""
        info = ClassInfo(
            item.name,
            simple,
            kind,
            "interface" if kind == "interface" else item.stereotype,
            f"{prefix}src/main/java/{item.name.replace('.', '/')}.java",
            0,
            0,
            repo,
        )
        world.maps[repo].add(info)
        change.classes[item.name] = NEW
    for item in spec.new_classes:
        info = world.cls(item.name) if "." in item.name else None
        if info is None or change.classes.get(info.fqcn) != NEW:
            continue
        for parent in item.implements + item.extends:
            resolved = r.cls(parent, f"new class {item.name}")
            if resolved:
                (info.implements if parent in item.implements else info.extends).append(resolved)
        for used in item.uses:
            resolved = r.cls(used, f"new class {item.name} uses")
            if resolved:
                type_name = resolved.rsplit(".", 1)[-1]
                info.fields.append(FieldInfo(type_name[0].lower() + type_name[1:], type_name, 0, True))
                change.fields[(info.fqcn, info.fields[-1].name)] = NEW
        for text in item.fields:
            name, _, type_name = text.partition(":")
            info.fields.append(FieldInfo(name.strip(), type_name.strip(), 0, False))
            change.fields[(info.fqcn, name.strip())] = NEW
        world.map_of(info.fqcn).add(info)  # reindex implementations
    # 2. new fields
    for item in spec.new_fields:
        owner = r.cls(item.ref.owner, f"new field {item.ref.text}")
        if owner is None:
            continue
        info = world.cls(owner)
        if any(f.name == item.ref.member for f in info.fields):
            problems.append(f"new field {item.ref.text} already exists: list it under changed")
            continue
        info.fields.append(FieldInfo(item.ref.member, item.type, 0, False))
        change.fields[(owner, item.ref.member)] = NEW
        change.mark_class(owner, CHANGED)
    # 3. new methods (all first, so they can call each other)
    created: list[tuple[str, MethodInfo, object]] = []
    for item in spec.new_methods:
        owner = r.cls(item.ref.owner, f"new method {item.ref.text}")
        if owner is None:
            continue
        info = world.cls(owner)
        if info.method(item.name) and change.classes.get(owner) != NEW:
            problems.append(f"new method {item.ref.text} already exists: list it under changed")
            continue
        method = MethodInfo(item.name, 0, 0, item.params, item.returns, "public")
        info.methods.append(method)
        change.methods[(owner, item.name)] = NEW
        change.mark_class(owner, CHANGED)
        created.append((owner, method, item))
    known_nodes = world.nodes()
    for owner, method, item in created:
        for order, ref in enumerate(item.calls, 1):
            target = r.method(ref, f"new method {item.ref.text} calls")
            if target:
                method.calls.append(Call(order, target[0], target[1], "field"))
                change.new_calls.add((owner, method.name, target[0], target[1]))
        for kind, resource in item.uses:
            method.uses.append(Use(kind, resource, len(item.calls) + 1))
            change.new_uses.add((owner, method.name, kind, resource))
            if resource not in known_nodes:
                change.resources[resource] = NEW
        for caller_ref in item.called_from:
            caller = r.method(caller_ref, f"new method {item.ref.text} calledFrom")
            if caller is None:
                continue
            _insert_call(
                world, change, caller, owner, method.name, item.before, r, f"new method {item.ref.text}"
            )
    # 4. changed elements
    for ref in spec.changed:
        where = f"changed {ref.text}"
        if ref.kind == "method":
            found = r.method(ref, where)
            if found:
                change.methods[found] = (
                    strongest(change.methods.get(found, ""), CHANGED) if found in change.methods else CHANGED
                )
                change.mark_class(found[0], CHANGED)
        elif ref.kind == "field":
            found = r.field(ref, where)
            if found:
                change.fields[found] = CHANGED
                change.mark_class(found[0], CHANGED)
        elif ref.kind == "class":
            found_class = r.cls(ref.owner, where)
            if found_class:
                change.mark_class(found_class, CHANGED)
        else:
            resource = r.resource(ref.text, where, must_exist=True)
            if resource:
                change.resources[resource] = CHANGED
    for item in spec.changed_methods:
        found = r.method(item.ref, f"changed {item.ref.text}")
        if found is None:
            continue
        info = world.method(*found)
        for ref in item.calls:
            target = r.method(ref, f"changed {item.ref.text} calls")
            if target and info is not None:
                info.calls.append(Call(info.end + 0.5, target[0], target[1], "field"))
                change.new_calls.add((found[0], found[1], target[0], target[1]))
        for kind, resource in item.uses:
            if info is not None:
                info.uses.append(Use(kind, resource, info.end + 0.6))
                change.new_uses.add((found[0], found[1], kind, resource))
                if resource not in known_nodes:
                    change.resources[resource] = NEW
    # 5. removed
    for ref in spec.removed:
        where = f"removed {ref.text}"
        if ref.kind == "method":
            found = r.method(ref, where)
            if found:
                change.methods[found] = REMOVED
                change.mark_class(found[0], CHANGED)
                change.breaking.add(f"class:{found[0]}")
        elif ref.kind == "field":
            found = r.field(ref, where)
            if found:
                change.fields[found] = REMOVED
                change.mark_class(found[0], CHANGED)
                change.breaking.add(f"{found[0].rsplit('.', 1)[-1]}.{found[1]}")
                change.breaking.add(f"class:{found[0]}")
        elif ref.kind == "class":
            found_class = r.cls(ref.owner, where)
            if found_class:
                change.classes[found_class] = REMOVED
                change.breaking.add(f"class:{found_class}")
        else:
            resource = r.resource(ref.text, where, must_exist=True)
            if resource:
                change.resources[resource] = REMOVED
                change.breaking.add(resource)
    # 6. declared entry points
    for text in spec.entries:
        entry = _entry(world, text, r)
        if entry:
            change.entries.append(entry)
    for case in spec.use_cases:
        if case.entry and not _entry(world, case.entry, None):
            if case.entry not in {res for _, _, _, res in change.new_uses}:
                problems.append(
                    f"useCase {case.name!r}: entry {case.entry} is not an entry point in the code or the spec"
                )
    return change, problems


def _insert_call(
    world: World, change: Change, caller, owner: str, name: str, before: Ref | None, r: _Resolver, where
):
    info = world.method(*caller)
    if info is None:
        return
    line: float
    if before is not None:
        target = r.method(before, f"{where} before")
        if target is None:
            return
        names = {target[0], *[c.target for c in info.calls if world.implementation(c.target) == target[0]]}
        match = next((c for c in info.calls if c.method == target[1] and (c.target in names)), None)
        if match is None:
            listed = ", ".join(
                f"{c.target.rsplit('.', 1)[-1]}#{c.method}" for c in info.calls if c.via != "new"
            )
            r.problems.append(
                f"{where}: before {before.text} is not a call in {caller[0].rsplit('.', 1)[-1]}#{caller[1]}"
                + (f"; its calls are {listed}" if listed else "; it makes no calls")
            )
            return
        line = match.line - 0.5
    else:
        line = max([c.line for c in info.calls] + [u.line for u in info.uses] + [info.end or 0]) + 0.5
    info.calls.append(Call(line, owner, name, "field"))
    info.calls.sort(key=lambda c: (c.line, c.method))
    change.new_calls.add((caller[0], caller[1], owner, name))
    if change.methods.get(caller) != NEW:
        change.methods[caller] = CHANGED
        change.mark_class(caller[0], CHANGED)


def _entry(world: World, text: str, r: _Resolver | None) -> tuple[str, str] | None:
    if node_prefix(text) in RESOURCE_PREFIXES:
        for info in world.classes():
            for m in info.methods:
                if any(u.resource == text and u.kind in ("EXPOSES", "CONSUMES", "RUNS_JOB") for u in m.uses):
                    return info.fqcn, m.name
        if r is not None:
            r.problems.append(f"entries: no method exposes or consumes {text}")
        return None
    if r is None:
        return None
    from baton.diagram.spec import parse_ref

    return r.method(parse_ref(text), "entries")


# -- as built: the change a diff makes -----------------------------------------------------------------------


def _git_diff(repo: Path, ref: str) -> str:
    if ref.startswith("-"):
        raise ValueError(f"refused: {ref!r} is not a git ref")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    done = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "diff",
            "--unified=0",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            ref,
            "--",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if done.returncode:
        raise ValueError(f"git diff {ref} failed in {repo}: {done.stderr.strip()}")
    return done.stdout


def changed_lines(diff: str) -> dict[str, tuple[set[int], bool]]:
    """path -> (new-side line numbers touched, file is new). A pure deletion touches the line it sat
    before."""
    out: dict[str, tuple[set[int], bool]] = {}
    current = None
    is_new = False
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current, is_new = None, False
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("+++ "):
            path = line[4:].strip()
            current = None if path == "/dev/null" else path[2:] if path.startswith("b/") else path
            if current:
                out.setdefault(current, (set(), is_new))
        elif current and (match := _HUNK.match(line)):
            start = int(match.group(3))
            count = int(match.group(4)) if match.group(4) is not None else 1
            lines = out[current][0]
            if count == 0:
                lines.add(max(start, 1))
                lines.add(start + 1)
            else:
                lines.update(range(start, start + count))
    return out


def from_diff(world: World, ref: str, only: str | None = None) -> tuple[Change, list[str]]:
    """The change as built: every method whose lines the diff touches. A method all of whose lines are new is
    new; a class in a new file is new."""
    change = Change(source="diff")
    notes: list[str] = []
    for repo, cmap in sorted(world.maps.items()):
        if only and repo != only:
            continue
        repo_path = None
        from baton.extract.repos import read_repo_table

        for item in read_repo_table(world.central):
            if item.name == repo:
                repo_path = item.path
        try:
            diff = _git_diff(repo_path, ref)
        except ValueError as exc:
            notes.append(f"{repo}: {exc}")
            continue
        for path, (lines, is_new) in sorted(changed_lines(diff).items()):
            for info in cmap.classes.values():
                if info.file != path:
                    continue
                if "/src/test/" in f"/{path}":
                    continue
                if is_new:
                    change.classes[info.fqcn] = NEW
                    for m in info.methods:
                        change.methods[(info.fqcn, m.name)] = NEW
                        change.lines[(info.fqcn, m.name)] = f"{m.start}-{m.end}"
                    continue
                hit = False
                for m in info.methods:
                    span = set(range(m.start, m.end + 1))
                    touched = span & lines
                    if not touched:
                        continue
                    hit = True
                    status = NEW if span <= lines else CHANGED
                    change.methods[(info.fqcn, m.name)] = strongest(
                        change.methods.get((info.fqcn, m.name), ""), status
                    )
                    change.lines[(info.fqcn, m.name)] = f"{min(touched)}-{max(touched)}"
                for f in info.fields:
                    if f.line in lines:
                        change.fields[(info.fqcn, f.name)] = CHANGED
                        hit = True
                if hit or (lines & set(range(info.start, info.end + 1))):
                    change.mark_class(info.fqcn, CHANGED)
    return change, notes


def conformance(declared: Change, built: Change) -> dict:
    """What was built but not declared, and declared but not built: the design drifted, or is not done."""

    def methods(change: Change) -> set[str]:
        return {f"{fqcn.rsplit('.', 1)[-1]}#{name}" for (fqcn, name), s in change.methods.items() if s}

    def classes(change: Change) -> set[str]:
        return {fqcn.rsplit(".", 1)[-1] for fqcn, s in change.classes.items() if s == NEW}

    return {
        "undeclared": sorted(methods(built) - methods(declared)),
        "notBuilt": sorted(methods(declared) - methods(built)),
        "newClassesUndeclared": sorted(classes(built) - classes(declared)),
        "newClassesNotBuilt": sorted(classes(declared) - classes(built)),
    }


__all__ = ["Change", "apply_spec", "from_diff", "conformance", "changed_lines", "_short_params"]
