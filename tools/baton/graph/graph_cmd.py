"""Load profile/dependencies.yaml into the graph store: baton graph load [--store sqlite|age]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.graph.loader import GRAPH_FILE, LoadError, MissingInput, load_into
from baton.graph.sqlite_store import SqliteStore


def add_arguments(parser: argparse.ArgumentParser) -> None:
    verbs = parser.add_subparsers(dest="verb", required=True)
    load = verbs.add_parser("load", help="upsert nodes and edges from profile/dependencies.yaml; idempotent")
    load.add_argument(
        "--store", choices=("sqlite", "age"), default="sqlite", help="graph backend (default sqlite)"
    )
    # Accepted after the verb too; SUPPRESS keeps a value given before it.
    load.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="machine output on stdout"
    )
    load.add_argument(
        "--central", default=argparse.SUPPRESS, help="central repo path (default: current directory)"
    )


def run(args: argparse.Namespace) -> int:
    if args.store == "age":
        print("baton graph load: the age store is an interface only; use --store sqlite", file=sys.stderr)
        return 2
    store = SqliteStore(Path(args.central) / GRAPH_FILE) if _has_input(args.central) else None
    if store is None:
        print(
            f"baton graph load: {Path(args.central) / 'profile/dependencies.yaml'} not found",
            file=sys.stderr,
        )
        return 2
    try:
        summary = load_into(store, args.central)
    except MissingInput as exc:
        print(f"baton graph load: {exc}", file=sys.stderr)
        return 2
    except LoadError as exc:
        print("baton graph load: refused, nothing changed:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    finally:
        store.close()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"loaded {summary['nodes']} nodes, {summary['edges']} edges from {len(summary['repos'])} repos")
    return 0


def _has_input(central: str) -> bool:
    return (Path(central) / "profile/dependencies.yaml").is_file()
