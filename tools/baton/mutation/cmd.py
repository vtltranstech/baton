"""Run PIT on the classes a diff changed and report mutation.json (a confidence signal, not a gate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from baton.mutation import pit

EXIT_OK, EXIT_REFUSED = 0, 2
DEFAULT_TIMEOUT_SECONDS = 1800


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="repo name, from profile/project.md or ../<repo>")
    parser.add_argument("--diff", required=True, help="git ref or range, e.g. main...HEAD")
    parser.add_argument("--out", help="also write mutation.json here, e.g. docs/qa/<F>/<S>-mutation.json")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
                        help="seconds before the build counts as not run (default %(default)s)")


def _table_path(central: Path, name: str) -> str | None:
    """The `path` cell of the repo's row in the first table of project.md with repo and path columns."""
    project = central / "profile" / "project.md"
    if not project.is_file():
        return None
    columns: list[str] = []
    for line in project.read_text().splitlines():
        if not line.strip().startswith("|"):
            columns = []
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        lowered = [cell.lower() for cell in cells]
        if "repo" in lowered and "path" in lowered:
            columns = lowered
        elif columns and len(cells) == len(columns) and cells[columns.index("repo")] == name:
            return cells[columns.index("path")]
    return None


def resolve_repo(central: Path, name: str) -> Path:
    return (central / (_table_path(central, name) or f"../{name}")).resolve()


def _summary(result: dict) -> str:
    classes = ", ".join(result["changedClasses"]) or "none"
    if result["notRun"]:
        return f"mutation not run: {result['reason']}\nchanged classes: {classes}"
    return (f"mutation score {result['score']:.2f}: killed {result['killed']}, "
            f"survived {result['survived']}, no coverage {result['noCoverage']}\n"
            f"changed classes: {classes}")


def run(args: argparse.Namespace) -> int:
    repo = resolve_repo(Path(args.central), args.repo)
    if not repo.is_dir():
        print(f"baton mutation: repo {args.repo} not found at {repo}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        result = pit.measure(repo, args.repo, args.diff, args.timeout)
    except pit.DiffError as exc:
        print(f"baton mutation: cannot diff {args.diff} in {repo}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    text = json.dumps(result, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    print(text if args.json else _summary(result))
    return EXIT_OK
