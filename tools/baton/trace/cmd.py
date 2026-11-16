"""One HTML page per feature: how it became stories, designs, code, reviews and a PR. No model.

baton trace F-002                 writes docs/trace/F-002.html
baton trace F-002 --story S-010   the page opens on S-010
baton trace F-002 --open          and opens it in the default browser
baton trace F-002 --json          prints trace.json instead of writing the page

A view only: it reads the artefacts under docs/ and profile/ and the provenance footers the agents
leave in them (contracts/trace.md). A missing artefact shows as "not produced"; it never fails the page.
Exit 0 on success, 2 when the feature has neither a feature note nor a stories folder.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from baton.trace.collect import Collector

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
TEMPLATE = Path(__file__).with_name("template.html")
SCHEMA = Path(__file__).resolve().parents[3] / "schemas" / "trace.json"  # absent in a pipx copy: not checked
PLACEHOLDER = "/*__TRACE__*/null"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("feature", help="feature id, e.g. F-002")
    parser.add_argument("--story", help="story the page opens on")
    parser.add_argument("--open", action="store_true", help="open the page in the default browser")


def schema_problems(document, schema: dict, root: dict | None = None, where: str = "$") -> list[str]:
    """The JSON Schema subset schemas/trace.json uses: type, enum, required, properties, items,
    additionalProperties and local $ref."""
    root = root or schema
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return schema_problems(document, target, root, where)
    problems = []
    kinds = schema.get("type")
    if kinds:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        checks = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if not any(checks[kind](document) for kind in kinds):
            return [f"{where}: expected {' or '.join(kinds)}"]
    if "enum" in schema and document not in schema["enum"]:
        problems.append(f"{where}: {document!r} not one of {schema['enum']}")
    if isinstance(document, dict):
        for key in schema.get("required", []):
            if key not in document:
                problems.append(f"{where}: missing {key}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties")
        for key, value in document.items():
            if key in properties:
                problems += schema_problems(value, properties[key], root, f"{where}.{key}")
            elif isinstance(extra, dict):
                problems += schema_problems(value, extra, root, f"{where}.{key}")
    if isinstance(document, list) and isinstance(schema.get("items"), dict):
        for index, value in enumerate(document):
            problems += schema_problems(value, schema["items"], root, f"{where}[{index}]")
    return problems


def render(trace: dict) -> str:
    payload = json.dumps(trace, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/").replace("<!--", "<\\!--").replace(" ", "\\u2028").replace(
        " ", "\\u2029"
    )
    title = f"{trace['feature']['id']} trace"
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace(PLACEHOLDER, payload, 1)
    return page.replace("<title>Feature trace</title>", f"<title>{title}</title>", 1)


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    collector = Collector(central, args.feature)
    if not collector.exists():
        print(
            f"baton trace: no docs/features/{args.feature}*.md and no docs/stories/{args.feature}/",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    ids = [p.stem for p in collector.story_paths]
    if args.story and not any(i == args.story or i.startswith(args.story + "-") for i in ids):
        print(f"baton trace: {args.story} is not a story of {args.feature}", file=sys.stderr)
        return EXIT_REFUSED
    trace = collector.collect(args.story)
    if SCHEMA.is_file():
        problems = schema_problems(trace, json.loads(SCHEMA.read_text(encoding="utf-8")))
        if problems:
            print("baton trace: trace.json does not match schemas/trace.json:", file=sys.stderr)
            print("\n".join(f"  {p}" for p in problems[:20]), file=sys.stderr)
            return EXIT_FAILED
    if args.json:
        print(json.dumps(trace, indent=1, ensure_ascii=False))
        return EXIT_OK
    out = central / "docs" / "trace" / f"{args.feature}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(trace), encoding="utf-8")
    figures = trace["figures"]
    print(
        f"{args.feature}: {figures['storiesDone']}/{figures['storiesTotal']} stories done, "
        f"{figures['gatesPassed']}/{figures['gatesTotal']} gates passed, {figures['fixLoops']} fix loops"
    )
    print(f"wrote {out.relative_to(central).as_posix()}")
    if args.open:
        webbrowser.open(out.as_uri())
    return EXIT_OK
