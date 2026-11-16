"""The code as operations and effects, in compact text for agents (read-only; no model, no network).

baton ir show                     one line per unit: entry points, data written, events emitted
baton ir show <unit>              every behavioural class and operation of a unit
baton ir show OrderService        a class: injected types, tests, operations with calls, effects, callers
baton ir show OrderService#place  one operation, with its callers and the entry points that reach it
baton ir show collection:orders   who reads, writes, publishes or consumes a resource
baton ir find loyalty discount    the operations, classes and resources that match the words
baton ir slice S-010 [--write]    the story's context pack (.baton/context/S-010.md with --write)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.diagram.spec import RESOURCE_PREFIXES, SpecError, parse_ref, suggest
from baton.extract.repos import MissingInput
from baton.graph.loader import LoadError
from baton.graph.model import node_prefix

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("show", "find", "slice"))
    parser.add_argument(
        "target", nargs="*", help="show: unit, class, Class#method or resource; find: words; slice: story id"
    )
    parser.add_argument("--all", action="store_true", help="show: also private helpers and trivial methods")
    parser.add_argument("--limit", type=int, default=15, help="find: how many hits (default 15)")
    parser.add_argument("--budget", type=int, default=3000, help="slice: token budget (default 3000)")
    parser.add_argument("--write", action="store_true", help="slice: also write .baton/context/<story>.md")


def build(central: Path):
    from baton.diagram.world import load_world
    from baton.ir.model import IR

    return IR(load_world(central))


def show(ir, target: str, everything: bool = False) -> tuple[str, list[str]]:
    from baton.ir import render

    world = ir.world
    if not target:
        return render.orientation(ir), []
    if target in world.units():
        return render.LEGEND + "\n\n" + render.unit_text(ir, target), []
    if node_prefix(target) in RESOURCE_PREFIXES:
        if not any(target in (e.src, e.dst) for e in world.edges):
            names = [n for n in world.nodes() if node_prefix(n) == node_prefix(target)]
            return "", [f"{target} is not in the graph{suggest(target, names)}"]
        return render.resource_text(ir, target), []
    ref = parse_ref(target)
    owner = ref.owner if ref.kind in ("method", "field") else target
    matches = [
        c for c in world.classes() if c.fqcn == owner or c.name == owner or c.fqcn.endswith("." + owner)
    ]
    if not matches:
        names = [c.name for c in world.classes()] + world.units()
        return "", [f"no unit or class {owner}{suggest(owner, names)}"]
    if len(matches) > 1:
        return "", [f"{owner} is ambiguous: {', '.join(c.fqcn for c in matches)}"]
    info = matches[0]
    if info.fqcn not in ir.by_class:
        return "", [f"{info.name} is a {info.stereotype}: data, not behaviour; read its file {info.file}"]
    only = None
    if ref.kind == "method":
        only = {op.key for op in ir.ops_of(info) if op.m.name == ref.member}
        if not only:
            names = [op.m.name for op in ir.ops_of(info)]
            return "", [f"{info.name} has no method {ref.member}{suggest(ref.member, names)}"]
    lines = render.class_lines(
        ir, info, everything=everything or only is not None, callers=True, reach=True, only=only
    )
    return "\n".join(lines) + "\n", []


def _slice(ir, central: Path, story_id: str, budget: int):
    from baton import state_check
    from baton.ir import slice as slice_mod

    found = state_check.find_story(central, story_id)
    spec = found.design("change.yaml")
    if spec.is_file():
        pack = slice_mod.from_spec(ir, found.story_id, spec)
    else:
        pack = slice_mod.from_words(
            ir, found.story_id, found.path.read_text(encoding="utf-8", errors="replace")
        )
    return found.story_id, slice_mod.render_pack(ir, pack, budget)


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    target = " ".join(args.target)
    try:
        ir = build(central)
        if args.action == "show":
            text, problems = show(ir, target, args.all)
            if problems:
                for problem in problems:
                    print(f"baton ir: {problem}", file=sys.stderr)
                return EXIT_FAILED
            print(
                json.dumps({"target": target, "text": text}) if args.json else text,
                end="" if not args.json else "\n",
            )
            return EXIT_OK
        if args.action == "find":
            from baton.ir import render

            if not target:
                print("baton ir find: give some words", file=sys.stderr)
                return EXIT_REFUSED
            hits = render.find(ir, target, args.limit)
            if args.json:
                print(
                    json.dumps(
                        [{"score": round(s, 2), "id": i, "line": line} for s, i, line in hits], indent=1
                    )
                )
            else:
                print("\n".join(line for _, _, line in hits) or "no match")
            return EXIT_OK if hits else EXIT_FAILED
        if not target:
            print("baton ir slice: give a story id, e.g. S-010", file=sys.stderr)
            return EXIT_REFUSED
        story, text = _slice(ir, central, target, args.budget)
        if args.write:
            from baton.ir.slice import write

            path = write(central, story, text)
            print(f"wrote {path.relative_to(central).as_posix()}", file=sys.stderr)
        print(
            json.dumps({"story": story, "text": text}) if args.json else text,
            end="" if not args.json else "\n",
        )
        return EXIT_OK
    except SpecError as exc:
        for problem in exc.problems:
            print(f"baton ir: {problem}", file=sys.stderr)
        return EXIT_FAILED
    except (MissingInput, FileNotFoundError) as exc:
        print(f"baton ir: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except LoadError as exc:
        print(f"baton ir: {exc}", file=sys.stderr)
        return EXIT_FAILED
