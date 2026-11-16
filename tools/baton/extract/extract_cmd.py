"""Extract edges with provenance into profile/dependencies.yaml; seed aggregates.yaml and risk-zones.yaml."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.extract.pipeline import RefusedOverwrite, run_extract
from baton.extract.repos import MissingInput


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo", help="only this repo from profile/project.md; other repos' entries are kept"
    )


def run(args: argparse.Namespace) -> int:
    try:
        outcome = run_extract(Path(args.central), args.repo)
    except MissingInput as exc:
        print(f"baton extract: {exc}", file=sys.stderr)
        return 2
    except RefusedOverwrite as exc:
        print(f"baton extract: {exc}", file=sys.stderr)
        return 1
    for result in outcome["results"]:
        name = result.entry["repo"]
        for failure in result.sources.failures:
            print(
                f"baton extract: {name}: could not parse {failure['file']}: {failure['reason']}",
                file=sys.stderr,
            )
    document = outcome["document"]
    if args.json:
        print(
            json.dumps({**document, "aggregates": outcome["aggregates"], "zones": outcome["zones"]}, indent=2)
        )
        return 0
    for entry in document["repos"]:
        parser = entry.get("parser", {})
        print(
            f"{entry['repo']} @ {entry['commit']}: {len(entry['edges'])} edges, "
            f"{len(entry.get('unresolved') or [])} unresolved, "
            f"parsed by treesitter {parser.get('treesitter', 0)}, javaparser {parser.get('javaparser', 0)}, "
            f"regex {parser.get('regex', 0)}"
        )
        for target in entry.get("unresolved") or []:
            print(f"  unresolved: {target}")
    print(f"aggregates seeded or kept: {len(outcome['aggregates'])}; risk zones: {len(outcome['zones'])}")
    return 0
