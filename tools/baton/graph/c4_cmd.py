"""C4 model from the graph: writes docs/architecture/workspace.dsl, or with --check exits 1 on drift.

Story and feature stamps (contracts/versioning.md section 3) survive every run and are ignored by --check.
`--story S` stamps what the story added or changed and appends a line to docs/architecture/CHANGELOG.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from baton.graph.c4 import drift, dynamic_view_problems, extract_dynamic_views
from baton.graph.loader import LoadError, MissingInput, open_for_reading
from baton.graph.profile_files import read_profile
from baton.graph.stamps import apply, changelog, extract, promote, strip
from baton.state_check import find_story

WORKSPACE = "docs/architecture/workspace.dsl"
CHANGELOG = "docs/architecture/CHANGELOG.md"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--check",
        action="store_true",
        help="diff the projection against workspace.dsl, keeping per-story dynamic views; exit 1 on drift",
    )
    parser.add_argument(
        "--story",
        help="promote for this story: stamp what it added or changed, append to architecture/CHANGELOG.md",
    )
    parser.add_argument("--date", help="stamp date, YYYY-MM-DD (default: today, UTC)")


def run(args: argparse.Namespace) -> int:
    path = Path(args.central) / WORKSPACE
    existing = path.read_text(encoding="utf-8") if path.is_file() else None
    if args.check and existing is None:
        print(f"baton c4: {path} not found", file=sys.stderr)
        return 2
    try:
        store = open_for_reading(args.central)
    except MissingInput as exc:
        print(f"baton c4: {exc}", file=sys.stderr)
        return 2
    except LoadError as exc:
        print(f"baton c4: {exc}", file=sys.stderr)
        return 1
    views = extract_dynamic_views(existing) if existing else []
    try:
        generated = store.export_c4(read_profile(args.central), views)
    finally:
        store.close()
    problems = dynamic_view_problems(generated, views)
    if args.check:
        return _report_check(args, strip(existing), generated, problems)
    if problems:
        print("baton c4: not written, the kept dynamic views would no longer validate:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    promotion = None
    if args.story:
        try:
            feature = find_story(Path(args.central), args.story).feature
        except FileNotFoundError as exc:
            print(f"baton c4: {exc}", file=sys.stderr)
            return 2
        date = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
        promotion = promote(existing, generated, args.story, feature, date)
        generated = promotion.dsl
        log = Path(args.central) / CHANGELOG
        old_log = log.read_text(encoding="utf-8") if log.is_file() else None
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(changelog(old_log, date, feature, args.story, promotion), encoding="utf-8")
    elif existing:
        generated = apply(generated, extract(existing))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generated, encoding="utf-8")
    if promotion:
        counts = {
            "elements": len(promotion.added_elements),
            "relationships": len(promotion.added_relationships),
            "changed": len(promotion.changed),
            "removed": len(promotion.removed),
        }
        if args.json:
            print(json.dumps({"path": WORKSPACE, "story": args.story, **counts,
                              "added": promotion.added_elements + promotion.added_relationships,
                              "changedItems": promotion.changed, "removedItems": promotion.removed},
                             indent=2, sort_keys=True))
        else:
            print(
                f"wrote {path}: +{counts['elements']} elements, +{counts['relationships']} relationships, "
                f"~{counts['changed']} changed, {counts['removed']} removed; appended {CHANGELOG}"
            )
        return 0
    if args.json:
        print(json.dumps({"path": WORKSPACE, "dynamicViewsKept": len(views)}, indent=2, sort_keys=True))
    else:
        print(f"wrote {path} ({len(views)} dynamic views kept)")
    return 0


def _report_check(args, existing: str, generated: str, problems: list[str]) -> int:
    diff = drift(existing, generated)
    clean = not diff and not problems
    if args.json:
        print(json.dumps({"drift": not clean, "diff": diff, "problems": problems}, indent=2, sort_keys=True))
    elif clean:
        print("no drift")
    if not clean:
        for line in problems + diff:
            print(line, file=sys.stderr)
        return 1
    return 0
