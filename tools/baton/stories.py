"""Every story of the product, wherever it lives: this working tree, the archive, or its story/ branch.

baton stories                one line per story: id, feature, State, where, title
baton stories --feature F    only that feature
baton stories --json         the same as JSON

Each story's files stay on `story/<F>-<S>` until its docs PR merges (contracts/versioning.md section 1),
so a working tree alone shows the default branch and the checked-out story. /standup, /sprint-review,
/sprint and /deliver list stories with this command instead of reading docs/stories/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from baton import state_check

EXIT_OK = 0


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feature", help="only this feature id")


def collect(central: Path, feature: str | None = None, on_branch: list | None = None) -> list[dict]:
    """Every story here, archived, or only on its story branch (`on_branch`: branch_stories, if read)."""
    central = Path(central)
    stories: list[state_check.Story] = []
    for path in sorted((central / "docs" / "stories").glob("*/*.md")):
        if state_check._ID.match(path.stem):
            stories.append(state_check.story_from_path(path, central))
    for path in sorted((central / "docs" / "archive").glob("*/stories/*.md")):
        match = state_check._ID.match(path.stem)
        if match:
            stories.append(state_check.Story(central, path.parts[-3], match.group(1), path))
    seen = {story.story_id for story in stories}
    if on_branch is None:
        on_branch = state_check.branch_stories(central)
    stories += [story for story in on_branch if story.story_id not in seen]
    rows = []
    for story in stories:
        if feature and story.feature != feature:
            continue
        try:
            text = story.text()
        except (FileNotFoundError, OSError):
            continue
        title = re.search(r"^#\s+(?:[A-Za-z]+-\d+\s+)?(.+)$", text, re.M)
        where = story.ref or ("archive" if "archive" in story.path.relative_to(central).parts else "here")
        rows.append({
            "story": story.story_id,
            "feature": story.feature,
            "state": state_check.parse_state(text).state,
            "where": where,
            "path": story.rel(story.path),
            "title": title.group(1).strip() if title else None,
        })
    return sorted(rows, key=lambda r: (r["feature"], r["story"]))


def run(args: argparse.Namespace) -> int:
    rows = collect(Path(args.central).resolve(), args.feature)
    if args.json:
        print(json.dumps(rows, indent=1))
        return EXIT_OK
    if not rows:
        print("no stories", file=sys.stderr)
        return EXIT_OK
    for row in rows:
        state, title = str(row["state"]), row["title"] or ""
        print(f"{row['story']:<8} {row['feature']:<10} {state:<22} {row['where']:<28} {title}")
    return EXIT_OK
