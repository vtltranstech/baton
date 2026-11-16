"""Detect each repo's stack from its build files and write profile/stack-detected.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.extract.pipeline import render_stack, run_stack
from baton.extract.repos import MissingInput


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", help="only this repo from profile/project.md; other rows are kept")


def run(args: argparse.Namespace) -> int:
    try:
        result = run_stack(Path(args.central), args.repo)
    except MissingInput as exc:
        print(f"baton extract-stack: {exc}", file=sys.stderr)
        return 2
    for row in result["_rows"]:
        for problem in row["problems"]:
            print(f"baton extract-stack: {row['repo']}: {problem}", file=sys.stderr)
    if args.json:
        print(json.dumps({"generated": result["generated"], "repos": result["repos"]}, indent=2))
    else:
        print(render_stack(result["repos"], result["generated"]), end="")
    return 0
