"""Diagrams from the code (AST) and a change spec: SVG + Markdown + HTML; no model, no network, no plugin.

baton diagram story S-010            design diagrams from docs/design/<F>/S-010-change.yaml
baton diagram story S-010 --check    check the spec against the code only, write nothing
baton diagram story S-010 --diff main
                                       as-built diagrams from the diff, and what drifted from the spec
baton diagram architecture           the project's context, container and component views
baton diagram context FeeService     a compact card of a class, method or resource for an agent to read
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.diagram import draw_class, draw_flow, draw_sequence, draw_usecase, mermaid, output
from baton.diagram.change import Change, apply_spec, conformance, copy_maps, from_diff
from baton.diagram.spec import SpecError
from baton.diagram.spec import load as load_spec
from baton.extract.repos import MissingInput
from baton.graph.loader import LoadError
from baton.graph.model import node_name

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("story", "architecture", "context"), help="what to draw")
    parser.add_argument(
        "target", nargs="?", help="story id (story), or a class / Class#method / resource (context)"
    )
    parser.add_argument("--spec", help="change spec (default docs/design/<F>/<S>-change.yaml)")
    parser.add_argument(
        "--check", action="store_true", help="story: check the spec against the code, write nothing"
    )
    parser.add_argument("--diff", metavar="REF", help="story: draw what was built: git diff REF in each repo")
    parser.add_argument("--repo", help="story --diff / architecture: only this repo")
    parser.add_argument("--out", help="output folder (default per action)")


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    try:
        if args.action == "story":
            return _story(args, central)
        if args.action == "architecture":
            from baton.diagram import arch

            return arch.run(args, central)
        return _context(args, central)
    except (MissingInput, FileNotFoundError) as exc:
        print(f"baton diagram: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except LoadError as exc:
        print(f"baton diagram: {exc}", file=sys.stderr)
        return EXIT_FAILED


# -- story -------------------------------------------------------------------------------------------------


def _story_title(path: Path) -> str:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            text = line[2:].strip()
            return (
                text.split(":", 1)[1].strip()
                if text.lower().startswith(("story", "s-")) and ":" in text
                else text
            )
    return ""


def _story(args, central: Path) -> int:
    from baton import state_check
    from baton.diagram import story as story_mod
    from baton.diagram.world import load_world

    if not args.target:
        print("baton diagram story: give a story id, e.g. S-010", file=sys.stderr)
        return EXIT_REFUSED
    found = state_check.find_story(central, args.target)
    spec_path = Path(args.spec) if args.spec else found.design("change.yaml")
    if not spec_path.is_absolute():
        spec_path = (central / spec_path) if not spec_path.is_file() else spec_path.resolve()
    spec = None
    if spec_path.is_file():
        try:
            spec = load_spec(spec_path)
        except SpecError as exc:
            return _problems(args, exc.problems, spec_path, central)
        if spec.story != found.story_id:
            return _problems(
                args, [f"the spec is for {spec.story}, not {found.story_id}"], spec_path, central
            )
    elif not args.diff:
        print(
            f"baton diagram story: {found.rel(spec_path)} not found. Write it first (see the "
            "design-diagram skill), or pass --diff REF to draw what was built.",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    world = load_world(central)
    declared: Change | None = None
    problems: list[str] = []
    if spec is not None:
        declared, problems = apply_spec(world, spec)
        if problems:
            return _problems(args, problems, spec_path, central)
    if args.check:
        message = {
            "spec": found.rel(spec_path),
            "ok": True,
            "problems": [],
            "entries": _entry_titles(world, declared),
        }
        print(
            json.dumps(message, indent=2)
            if args.json
            else f"{found.rel(spec_path)}: ok; entry points: {', '.join(message['entries']) or 'none found'}"
        )
        return EXIT_OK
    title = (spec.title if spec and spec.title else "") or _story_title(found.path)
    if args.diff:
        built_world = load_world(central)
        copy_maps(built_world)
        built, notes = from_diff(built_world, args.diff, args.repo)
        source = f"git diff {args.diff}"
        diagrams = story_mod.build(built_world, built, found.story_id, title, source, spec)
        diagrams.notes = notes + diagrams.notes
        if declared is not None:
            diagrams.conformance = conformance(declared, built)
        out = Path(args.out) if args.out else found.qa("as-built")
    else:
        source = found.rel(spec_path)
        diagrams = story_mod.build(world, declared, found.story_id, title, source, spec)
        out = Path(args.out) if args.out else found.design("diagrams")
    if not out.is_absolute():
        out = central / out
    files = output.write(out, story_set(diagrams, found.rel(out)))
    summary = {
        "story": found.story_id,
        "out": found.rel(out),
        "files": files,
        "entries": [w.title for w in diagrams.walks],
        "touchPoints": len(diagrams.touch),
        "impactedRepos": sorted({r["unit"] for r in diagrams.impacted}),
        "conformance": diagrams.conformance,
        "notes": diagrams.notes,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(
            f"wrote {found.rel(out)}/ ({len(files)} files): open diagrams.md in the VS Code preview "
            "or index.html"
        )
        for walk in diagrams.walks:
            print(f"  sequence: {walk.title}")
        if diagrams.conformance:
            c = diagrams.conformance
            for key, label in (
                ("undeclared", "built but not in the spec"),
                ("notBuilt", "in the spec, not built"),
            ):
                if c[key]:
                    print(f"  {label}: {', '.join(c[key])}")
        for note in diagrams.notes:
            print(f"  note: {note}")
    return EXIT_OK


def _entry_titles(world, change) -> list[str]:
    from baton.diagram.walk import entries_for

    return [f"{fqcn.rsplit('.', 1)[-1]}#{name}" for fqcn, name in entries_for(world, change)]


def _problems(args, problems: list[str], spec_path: Path, central: Path) -> int:
    try:
        shown = spec_path.relative_to(central).as_posix()
    except ValueError:
        shown = str(spec_path)
    if args.json:
        print(json.dumps({"spec": shown, "ok": False, "problems": problems}, indent=2))
    else:
        print(f"{shown}: {len(problems)} problem(s), nothing written", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
    return EXIT_FAILED


def _md(text: str) -> str:
    return str(text).replace("|", "\\|")


def story_set(d, out_rel: str) -> output.DiagramSet:
    from baton.diagram.shapes import CHANGED, NEW, REMOVED

    counts = {s: sum(1 for r in d.touch if r["status"] == s) for s in (NEW, CHANGED, REMOVED)}
    others = sorted({r["unit"] for r in d.impacted})
    intro = "\n".join(
        [
            "| Source | Code | New | Changed | Removed | Other repos affected |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| `{d.source}` | {d.commits} | {counts[NEW]} | {counts[CHANGED]} | {counts[REMOVED]} | "
            f"{', '.join(others) or 'none'} |",
            "",
            "> [!NOTE] Blue = new, orange = changed, red = other repo affected, grey = unchanged.",
        ]
    )
    rows = [
        "| Status | Element | Service | Where | Reached from | Tests that name it |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in d.touch:
        where = f"`{r['file']}:{r['lines']}`" if r["file"] else "-"
        reached = _md(", ".join(r["reachedFrom"])) or (
            "no entry point reaches it" if "#" in r["element"] else "-"
        )
        rows.append(
            f"| **{r['status']}** | `{_md(r['element'])}` | {r['repo'] or '-'} | {where} | "
            f"{reached} | {_md(', '.join(r['tests'])) or 'none'} |"
        )
    tables = [("Touch points", "\n".join(rows) if d.touch else "Nothing changes.")]
    blast = ["| Service | Through | File:lines | Breaking |", "| --- | --- | --- | --- |"]
    for r in d.impacted:
        blast.append(
            f"| {r['unit']} | `{_md(r['via'])}` | `{r['file']}:{r['lines']}` | "
            f"{'**yes**' if r['breaking'] else 'no'} |"
        )
    blast_text = "\n".join(blast) if d.impacted else "No other repo reads or calls what this story changes."
    if d.unknown:
        blast_text += "\n\nUnknown edges (the other side is not in the graph): " + "; ".join(
            f"`{u}`" for u in d.unknown
        )
    tables.append(("Blast radius", blast_text))
    if d.conformance:
        c = d.conformance
        lines = ["| Check | Elements |", "| --- | --- |"]
        for key, label in (
            ("undeclared", "built, not in the spec"),
            ("notBuilt", "in the spec, not built"),
            ("newClassesUndeclared", "new classes not in the spec"),
            ("newClassesNotBuilt", "new classes in the spec, not built"),
        ):
            lines.append(f"| {label} | {', '.join(f'`{x}`' for x in c[key]) or 'none'} |")
        tables.append(("Design conformance", "\n".join(lines)))
    sections = [
        output.Section(
            "1. Flow with impacts",
            "flow.svg",
            draw_flow.draw(d.flow),
            mermaid.flow(d.flow),
            "Every component, collection, topic and repo on the paths this story touches.",
        )
    ]
    for i, seq in enumerate(d.sequences, 1):
        sections.append(
            output.Section(
                f"2.{i} Sequence: {d.walks[i - 1].title}",
                f"sequence-{i}.svg",
                draw_sequence.draw(seq),
                mermaid.sequence(seq),
                seq.caption,
                2,
            )
        )
    sections.append(
        output.Section(
            "3. Low-level design", "lld.svg", draw_class.draw(d.lld), mermaid.classes(d.lld), d.lld.caption
        )
    )
    if d.data is not None:
        sections.append(
            output.Section(
                "4. Data model",
                "data-model.svg",
                draw_class.draw(d.data),
                mermaid.entities(d.data),
                d.data.caption,
            )
        )
    sections.append(
        output.Section(
            "5. Use cases",
            "use-cases.svg",
            draw_usecase.draw(d.usecases),
            mermaid.usecases(d.usecases),
            d.usecases.caption,
        )
    )
    notes = list(d.notes)
    if d.more_entries:
        notes.append("also reached from (not drawn): " + ", ".join(d.more_entries))
    summary = {
        "story": d.story,
        "title": d.title,
        "source": d.source,
        "entries": [
            {"entry": f"{e[0]}#{e[1]}", "title": w.title} for w, e in ((w, w.entry) for w in d.walks)
        ],
        "touchPoints": d.touch,
        "impacted": d.impacted,
        "unknownEdges": d.unknown,
        "conformance": d.conformance,
        "notes": notes,
    }
    return output.DiagramSet(
        f"{d.story} {d.title} - diagrams".strip(), intro, sections, tables, notes, summary
    )


# -- context -----------------------------------------------------------------------------------------------


def _context(args, central: Path) -> int:
    from baton.diagram.context import card
    from baton.diagram.world import load_world

    if not args.target:
        print("baton diagram context: name a class, Class#method or a resource id", file=sys.stderr)
        return EXIT_REFUSED
    world = load_world(central)
    result, problems = card(world, args.target)
    if problems:
        for problem in problems:
            print(f"baton diagram context: {problem}", file=sys.stderr)
        return EXIT_FAILED
    print(json.dumps(result["data"], indent=2, sort_keys=True) if args.json else result["text"])
    return EXIT_OK


__all__ = ["add_arguments", "run", "story_set", "node_name"]
