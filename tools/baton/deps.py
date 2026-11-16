"""Show which stories can start and which wait for a `Depends-On:` story to be Done."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from baton import state_check

_PR_LINE = re.compile(r"^[*_]*PR[*_]*:[*_]*[ \t]*\S*?(https?://\S+)", re.M)


def add_arguments(parser) -> None:
    parser.add_argument("story", nargs="?", help="a story id such as S-010; omit to list every open story")


def _read(story: state_check.Story) -> str:
    return story.text()


def _check_one(central: Path, story_id: str) -> dict:
    story = state_check.find_story(central, story_id)
    text = _read(story)
    # `Designed` is the first state of real work, so it asks the same question the hook will ask.
    problem = state_check.dependency_problem(story, "Designed", text)
    depends = state_check.parse_depends_on(text)[0] or []
    merged_check = []
    if problem is None:
        for dep in depends:
            dep_text = _read(state_check.find_story(central, dep))
            merged_check.append({"story": dep, "prs": _PR_LINE.findall(dep_text)})
    return {"story": story_id, "ok": problem is None, "problem": problem, "dependsOn": merged_check}


def _all_stories(central: Path) -> list[state_check.Story]:
    root = central / "docs" / "stories"
    stories = []
    for path in sorted(root.glob("*/*.md")):
        if state_check._ID.match(path.stem):
            stories.append(state_check.story_from_path(path, central))
    here = {story.story_id for story in stories}
    stories += [story for story in state_check.branch_stories(central) if story.story_id not in here]
    return stories


def _open_in_order(central: Path) -> list[dict]:
    """Unfinished stories, each after the stories it depends on; a broken story carries its problem."""
    rows: dict[str, dict] = {}
    for story in _all_stories(central):
        text = _read(story)
        state = state_check.parse_state(text).state
        if state == "Done":
            continue
        # `Ready` asks only whether the list is valid; waiting is worked out below.
        broken = state_check.dependency_problem(story, "Ready", text)
        depends = state_check.parse_depends_on(text)[0] or []
        waiting = []
        for dep in depends:
            try:
                waiting.extend(state_check.unfinished_dependencies(story, [dep]))
            except FileNotFoundError:
                pass
        rows[story.story_id] = {
            "story": story.story_id,
            "state": state,
            "waitingOn": [dep for dep, _ in waiting],
            "problem": broken,
        }
    ordered: list[dict] = []
    placed: set[str] = set()

    def place(story_id: str, trail: tuple[str, ...]) -> None:
        if story_id in placed or story_id in trail or story_id not in rows:
            return
        for dep in rows[story_id]["waitingOn"]:
            place(dep, trail + (story_id,))
        placed.add(story_id)
        ordered.append(rows[story_id])

    for story_id in rows:
        place(story_id, ())
    return ordered


def run(args) -> int:
    central = Path(args.central)
    if args.story:
        try:
            result = _check_one(central, args.story)
        except FileNotFoundError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result))
        if not result["ok"]:
            print(f"refused: {result['problem']}", file=sys.stderr)
            return 2
        if not args.json:
            print(f"ok: {args.story} can start")
            for dep in result["dependsOn"]:
                print(f"  {dep['story']} is Done: {', '.join(dep['prs']) or 'no PR line'}")
        return 0
    rows = _open_in_order(central)
    if args.json:
        print(json.dumps(rows))
    else:
        for row in rows:
            if row["problem"]:
                note = f"BROKEN: {row['problem']}"
            elif row["waitingOn"]:
                note = f"waiting on {', '.join(row['waitingOn'])}"
            else:
                note = "can start"
            print(f"{row['story']}\t{row['state']}\t{note}")
    broken = [row for row in rows if row["problem"]]
    for row in broken:
        print(f"refused: {row['story']}: {row['problem']}", file=sys.stderr)
    return 2 if broken else 0
