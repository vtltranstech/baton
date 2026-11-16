"""Blast radius of a change across repos: impact.json from a diff, design file list or git ref."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.graph.diffing import DiffError, compute_impact
from baton.graph.loader import LoadError, MissingInput, open_for_reading


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="the repo the change is in")
    parser.add_argument(
        "--diff",
        required=True,
        metavar="FILE|REF",
        help="unified diff file, design file list, or a git ref / range diffed in ../<repo>",
    )
    parser.add_argument("--out", help="also write impact.json here (/build: docs/qa/<F>/<S>-impact.json)")


def run(args: argparse.Namespace) -> int:
    try:
        store = open_for_reading(args.central)
    except MissingInput as exc:
        print(f"baton impact: {exc}", file=sys.stderr)
        return 2
    except LoadError as exc:
        print(f"baton impact: {exc}", file=sys.stderr)
        return 1
    try:
        if args.repo not in store.repos():
            print(f"baton impact: repo {args.repo} is not in the graph", file=sys.stderr)
            return 2
        report, notes = compute_impact(store, args.repo, args.diff, args.central)
    except DiffError as exc:
        print(f"baton impact: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
    for note in notes:
        print(f"baton impact: {note}", file=sys.stderr)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        _print_human(report)
    return 0


def _print_human(report: dict) -> None:
    print(f"{report['sourceRepo']}: {len(report['changedSymbols'])} changed symbols")
    for row in report["impacted"]:
        flag = " BREAKING" if row["breaking"] else ""
        print(f"  {row['repo']} via {row['via']}: {row['file']}:{row['lines']}{flag}")
    for unknown in report["unknownEdges"]:
        print(f"  unknown: {unknown}")
    if not report["impacted"] and not report["unknownEdges"]:
        print("  nothing impacted")
