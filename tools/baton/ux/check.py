"""`baton ux check S`: the wireframe options and the screen spec, before a human sees them."""

from __future__ import annotations

import json
import re
from pathlib import Path

from baton import miniyaml, state_check
from baton.ux import inventory as inv
from baton.ux import spec as specs
from baton.ux import wireframe

GENERIC_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "count",
    "created",
    "date",
    "due",
    "first",
    "for",
    "from",
    "in",
    "last",
    "name",
    "no",
    "not",
    "number",
    "of",
    "on",
    "or",
    "per",
    "status",
    "the",
    "to",
    "total",
    "type",
    "updated",
    "with",
}


def norm_path(path: str) -> str:
    path = re.split(r"[?#]", path.strip(), maxsplit=1)[0].rstrip("/") or "/"
    return re.sub(r"\{[^}]*\}|:\w+|\$\{[^}]*\}", "{}", path)


def endpoints(central: Path) -> set[str] | None:
    """`METHOD /path` with parameters as `{}`, from every repo's edges; None without dependencies.yaml."""
    path = central / "profile" / "dependencies.yaml"
    try:
        data = miniyaml.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = set()
    for repo in (data or {}).get("repos") or []:
        for edge in (repo or {}).get("edges") or []:
            target = str((edge or {}).get("to", ""))
            match = re.match(r"^endpoint:(GET|POST|PUT|PATCH|DELETE)\s+(\S+)", target)
            if match:
                found.add(f"{match.group(1)} {norm_path(match.group(2))}")
    return found


def glossary(central: Path) -> set[str]:
    words: set[str] = set()
    domain = central / "profile" / "domain.md"
    text = domain.read_text(encoding="utf-8") if domain.is_file() else ""
    part = state_check.section(text, "Domain words") or ""
    for line in part.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            line.strip().startswith("|")
            and cells
            and cells[0].lower() not in ("word", "")
            and not set(cells[0]) <= set("-: ")
        ):
            words |= {w.lower() for w in re.findall(r"[A-Za-z]+", cells[0])}
    project = central / "profile" / "project.md"
    text = project.read_text(encoding="utf-8") if project.is_file() else ""
    part = state_check.section(text, "Domain words") or ""
    for word in re.findall(r"[A-Za-z]+", re.sub(r"<[^>]*>|\([^)]*\)", "", part)):
        words |= {word.lower()} | {w.lower() for w in camel(word)}
    return words


def rule_ids(central: Path) -> set[str]:
    domain = central / "profile" / "domain.md"
    text = domain.read_text(encoding="utf-8") if domain.is_file() else ""
    return set(re.findall(r"^#{2,4}[ \t]*(R\d+)\b", text, re.M))


def camel(word: str) -> list[str]:
    return re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", word)


def resolve(src: dict, known: set[str] | None, routes: set[str]) -> str | None:
    """Why a source or target does not resolve, or None."""
    kind = src.get("kind")
    if kind in ("param", "derived", "static") or src.get("new"):
        return None
    if kind == "endpoint":
        if known is None:
            return "profile/dependencies.yaml does not exist (run /onboard), so no endpoint resolves"
        key = f"{src['method']} {norm_path(src['path'])}"
        return (
            None
            if key in known
            else f"`{src['method']} {src['path']}` is not an endpoint in profile/dependencies.yaml"
        )
    if kind == "route":
        wanted = norm_path(src["path"])
        return (
            None
            if wanted in {norm_path(r) for r in routes}
            else f"route `{src['path']}` is not a known route"
        )
    return (
        f"`{src.get('text', '')}` is not a source baton reads "
        "(METHOD /path -> field, route param, query param, derived, static, new:)"
    )


def check(central: Path, story: state_check.Story) -> tuple[int, dict]:
    folder = story.design("wireframe")
    spec_path = folder / "screen-spec.md"
    if not folder.is_dir() or not spec_path.is_file():
        return 2, {
            "story": story.story_id,
            "ok": False,
            "problems": [f"{story.rel(spec_path)} does not exist"],
        }
    track = state_check.track_of(story.text()) or "full"
    spec = specs.parse(spec_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    questions: list[str] = []
    new_endpoints: list[str] = []
    if not spec.get("screen"):
        problems.append("screen-spec.md has no `# Screen: <id>` title")
    inventory = inv.collect(central)  # from the source: the yaml may predate the last build
    known, routes = endpoints(central), inv.known_routes(inventory)
    screens = central / "docs" / "architecture" / "screens"
    for other in sorted(screens.glob("*/screen-spec.md")):
        route = (specs.load(other) or {}).get("route")
        if route:
            routes.add(route)
    fields = {f["field"]: f for f in spec["fields"]}
    actions = {a["action"]: a for a in spec["actions"]}
    for name, field in fields.items():
        why = resolve(field["source"], known, routes)
        if why:
            problems.append(f"field {name}: {why}")
            questions.append(
                f"Field `{name}` ({field['label']}): where does it come from? {why} (PO or Tech Lead)"
            )
        if field["source"].get("new"):
            new_endpoints.append(field["source_text"])
    for name, action in actions.items():
        why = resolve(action["target"], known, routes)
        if why:
            problems.append(f"action {name}: {why}")
            questions.append(f"Action `{name}` ({action['label']}): what does it call? {why} (Tech Lead)")
        if action["target"].get("new"):
            new_endpoints.append(action["target_text"])
    present = {s["state"] for s in spec["states"]}
    problems += [f"state `{s}` is missing from ## States" for s in specs.STATES if s not in present]
    rules = rule_ids(central)
    problems += [f"rule {r} is not a `### {r}` in profile/domain.md" for r in spec["rules"] if r not in rules]
    words = glossary(central) | GENERIC_WORDS | {w.lower() for f in fields for w in camel(f)}
    for name, field in fields.items():
        stray = [w for w in re.findall(r"[A-Za-z]+", field["label"]) if w.lower() not in words]
        if stray:
            problems.append(
                f"field {name}: label `{field['label']}` uses {', '.join(stray)}: "
                "not a glossary word or a field "
                "name (add it to the Domain words table, or rename)"
            )
    for region in spec["regions"]:
        for item in region["items"]:
            if item not in fields and item not in actions:
                problems.append(f"region {region['region']}: `{item}` is not in ## Fields or ## Actions")
    problems += components(spec, inventory)
    if track == "light" and specs.is_new(spec):
        problems.append("a new screen is always full track: set `Track: full` (screen-of-record is new)")
    options = wireframe.options(folder)
    if not options:
        problems.append(f"{story.rel(folder)} has no option-<n>.html")
    if track == "light" and len(options) > 1:
        problems.append(
            "the light track has one wireframe, option-1.html, as a delta on the screen of record"
        )
    if track != "light":
        if len(options) > 3:
            problems.append("at most three options")
        notes = folder / "options.md"
        if not notes.is_file():
            problems.append(f"{story.rel(notes)} does not exist")
        elif not re.search(r"recommended", notes.read_text(encoding="utf-8"), re.I):
            problems.append(f"{story.rel(notes)} marks no option `(recommended)`")
    region_names = {r["region"]: r for r in spec["regions"]}
    for path in options:
        seen = wireframe.read(path)
        where = path.name
        problems += [f"{where}: {p}" for p in seen.get("problems", [])]
        problems += [
            f"{where}: region `{r}` is not in the spec"
            for r in seen.get("regions", [])
            if r not in region_names
        ]
        problems += [
            f"{where}: field `{f}` is not in the spec" for f in seen.get("fields", []) if f not in fields
        ]
        problems += [
            f"{where}: action `{a}` is not in the spec" for a in seen.get("actions", []) if a not in actions
        ]
        problems += [
            f"{where}: state `{s}` is not one of the five"
            for s in seen.get("states", [])
            if s not in specs.STATES
        ]
        if seen.get("technical"):
            problems.append(f"{where}: technical words on screen: {', '.join(seen['technical'])}")
        for region, comp in (seen.get("components") or {}).items():
            declared = (region_names.get(region) or {}).get("component") or {}
            if declared and comp != declared.get("name"):
                problems.append(f"{where}: region {region} uses {comp}, the spec says {declared.get('name')}")
        if track == "light" and not seen.get("changed"):
            problems.append(f"{where}: a light-track delta marks its changed regions with data-changed")
    result = {
        "story": story.story_id,
        "screen": spec.get("screen"),
        "track": track,
        "ok": not problems,
        "problems": problems,
        "questions": questions,
        "newEndpoints": sorted(set(new_endpoints)),
        "newComponents": sorted(
            r["component"]["name"] for r in spec["regions"] if r.get("component") and r["component"]["new"]
        ),
        "options": [p.name for p in options],
    }
    folder.joinpath("screen-spec.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
    folder.joinpath("check.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return (0 if not problems else 1), result


def components(spec: dict, inventory: dict) -> list[str]:
    lib, app = inv.known_components(inventory)
    library = inventory.get("library") or {}
    name = library.get("name")
    problems = []
    if name and not lib:
        where = ", ".join(library.get("paths") or []) or "no ui.library.path"
        problems.append(
            f"the {name} library has no components in the inventory ({where}): run baton extract --ui"
        )
    for region in spec["regions"]:
        comp = region.get("component")
        if not comp or not comp.get("name"):
            problems.append(f"region {region['region']}: names no component")
            continue
        if comp["new"]:
            if comp["name"] in lib | app:
                problems.append(f"region {region['region']}: {comp['name']} is not new: reuse it")
            if name and not comp["uses"]:
                problems.append(
                    f"region {region['region']}: New: {comp['name']} names no {name} component "
                    "it is built from"
                )
            for used in comp["uses"]:
                if lib and used not in lib:
                    problems.append(
                        f"region {region['region']}: {used} is not a {name or 'library'} component"
                    )
        elif comp["name"] not in lib | app:
            problems.append(
                f"region {region['region']}: {comp['name']} is not in the inventory"
                f"{' (' + name + ' or the app)' if name else ''}; "
                f"reuse one, or declare `New: {comp['name']} (...)`"
            )
    return problems
