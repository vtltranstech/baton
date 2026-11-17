"""UI stories: component inventory, wireframe check, options page, built-screen verify, screens of record.

baton ux inventory                 profile/ui-inventory.yaml: the org's library, every UI repo
baton ux check S                   the wireframe options and screen-spec.md; exit 1 with one line per problem
baton ux show S [--open]           <S>-wireframe/index.html: the options side by side, for gate 2a
baton ux verify S                  the built screen against the approved spec: docs/qa/<F>/<S>-ui-verify.json
baton ux diff SCREEN REF_A REF_B   two versions of a screen of record side by side (--out F.html, else stdout)
baton ux promote S                 docs/architecture/screens/<screen-id>/ after gate 3, with its history line

contracts/ui-stories.md. Exit 0 ok, 1 problems found, 2 a missing input.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from baton import state_check

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
ACTIONS = ("inventory", "check", "show", "verify", "diff", "promote")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("target", nargs="?", help="the story id; for diff, the screen id")
    parser.add_argument(
        "refs", nargs="*", help="diff: two git refs (a tag like S-010, a branch) or two files"
    )
    parser.add_argument("--open", action="store_true", help="show: open the page in the default browser")
    parser.add_argument("--out", help="diff: write the page here instead of stdout")
    parser.add_argument("--date", help="promote: the history date (default today)")


def inventory(central: Path, as_json: bool) -> int:
    from baton.ux import inventory as inv

    data = inv.collect(central)
    missing = data["library"].get("missing") or []
    path = inv.write(central, data)
    lib = data["library"]
    if as_json:
        print(json.dumps(data, indent=1))
    else:
        print(f"wrote {path.relative_to(central).as_posix()}")
        if lib.get("name"):
            print(
                f"  library {lib['name']}: {len(lib['components'])} components "
                f"from {', '.join(lib['paths']) or '-'}"
            )
        for name, repo in data["repos"].items():
            print(
                f"  {name}: {len(repo.get('components') or {})} components, "
                f"{len(repo.get('routes') or [])} routes"
            )
    for rel in missing:
        print(f"ui.library.path {rel} does not exist", file=sys.stderr)
    return EXIT_REFUSED if missing else EXIT_OK


def _story(central: Path, sid: str | None) -> state_check.Story | None:
    if not sid:
        print("baton ux: a story id is required", file=sys.stderr)
        return None
    try:
        return state_check.find_story(central, sid)
    except (FileNotFoundError, ValueError) as exc:
        print(f"baton ux: {exc}", file=sys.stderr)
        return None


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    if args.action == "inventory":
        return inventory(central, args.json)
    if args.action == "diff":
        from baton.ux import screens

        if not args.target or len(args.refs) != 2:
            print("baton ux diff SCREEN REF_A REF_B", file=sys.stderr)
            return EXIT_REFUSED
        code, page = screens.diff(central, args.target, *args.refs)
        if code:
            print(f"baton ux diff: {page}", file=sys.stderr)
        elif args.out:
            Path(args.out).write_text(page, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(page, end="")
        return code
    story = _story(central, args.target)
    if story is None:
        return EXIT_REFUSED
    if args.action == "check":
        from baton.ux import check

        code, result = check.check(central, story)
        if args.json:
            print(json.dumps(result, indent=1))
        else:
            for problem in result["problems"]:
                print(problem, file=sys.stderr)
            if code == 0:
                print(f"ok: {result['screen']} ({result['track']}), options {', '.join(result['options'])}")
        return code
    if args.action == "verify":
        from baton.ux import verify

        code, result = verify.verify(central, story)
        if args.json:
            print(json.dumps(result, indent=1))
        else:
            for m in result.get("mismatches", []):
                print(
                    f"{m['severity']} {m['kind']}: {m['what']}",
                    file=sys.stderr if m["severity"] == "HIGH" else sys.stdout,
                )
            if result.get("problem"):
                print(result["problem"], file=sys.stderr)
            print(f"{'ok' if code == 0 else 'deviates'}: {story.rel(story.qa('ui-verify.json'))}")
        return code
    from baton.ux import screens

    if args.action == "show":
        code, page = screens.show(story)
        if code:
            print(f"baton ux show: {page}", file=sys.stderr)
            return code
        print(f"wrote {story.rel(page)}")  # type: ignore[arg-type]
        if args.open:
            webbrowser.open(Path(page).resolve().as_uri())  # type: ignore[arg-type]
        return EXIT_OK
    code, message = screens.promote(central, story, args.date)
    print(message, file=sys.stderr if code else sys.stdout)
    return code
