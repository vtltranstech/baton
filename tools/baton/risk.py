"""A story's risk tier (low | medium | high) from its design and its diff, decided before QA. No model.

baton risk S-010            print the tier and why; writes docs/qa/<F>/<S>-risk.json

It reads the change spec's touch points (docs/design/<F>/<S>-diagrams/diagrams.json, written by
`baton diagram story`), the story's Track, Labels and Estimate, profile/risk-zones.yaml and, once the
developer has finished, -diff-shape.json. The planned and the built change are both checked, so a story
whose diff grows past its design cannot stay low. The tier decides how many review lenses QA runs; it
never skips a gate, the security review or a test. A low story runs conformance and verification-gap,
plus domain fidelity when its design names a business rule under `Rules touched`.

- high: a risk-zone path, something removed or a breaking contract, another repo affected, a new
  dependency, or a label that forces design review (new-api, data-model, batch-job, jira.labels.extra)
- medium: full track, more than one repo, a new or changed collection, topic, endpoint or file, an
  estimate other than S, or no design touch points to check
- low: none of the above
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from baton import miniyaml
from baton.confidence import diff_files, glob_regex, header_value, project_value, read_json
from baton.state_check import find_story, track_of

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
TIERS = ("low", "medium", "high")
MANDATORY_LABELS = {"new-api", "data-model", "batch-job"}
RESOURCES = ("collection:", "topic:", "endpoint:", "file:", "queue:")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("story", help="story id, e.g. S-010")


def _labels(text: str) -> set[str]:
    value = header_value(text, "Labels") or ""
    return {label.strip().lower() for label in value.replace(";", ",").split(",") if label.strip()}


def rules_touched(design_note: Path) -> bool:
    """Whether the design note's `Rules touched:` names any domain rule (anything but none / n/a / empty)."""
    if not design_note.is_file():
        return True  # unknown: keep the domain lens
    text = design_note.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^[*_]*Rules touched:?[*_]*:?[ \t]*(.*?)(?=^\s*$|^#|\Z)", text, re.M | re.S | re.I)
    if not match:
        return True
    body = re.sub(r"[*_`]", "", match.group(1)).strip().strip(".").lower()
    return body not in ("", "none", "n/a", "not applicable", "-")


def _zones(central: Path) -> list[dict]:
    path = central / "profile" / "risk-zones.yaml"
    if not path.is_file():
        return []
    try:
        return (miniyaml.load_file(str(path)) or {}).get("zones") or []
    except (ValueError, AttributeError):
        return []


def _zone_of(file: str, zones: list[dict]) -> str | None:
    for zone in zones:
        if any(glob_regex(str(p)).match(file) for p in zone.get("paths") or []):
            return str(zone.get("name") or "risk zone")
    return None


def assess(central: Path, story_id: str) -> dict:
    story = find_story(central, story_id)
    text = story.path.read_text(encoding="utf-8", errors="replace")
    reasons: list[dict] = []

    def add(level: str, why: str) -> None:
        reasons.append({"level": level, "why": why})

    labels = _labels(text)
    extra = {x.strip().lower() for x in (project_value(central, "jira.labels.extra") or "").split(",")}
    forced = sorted(labels & (MANDATORY_LABELS | {x for x in extra if x and not x.startswith("<")}))
    if forced:
        add("high", f"label {', '.join(forced)} forces design review")
    if track_of(text) == "full":
        add("medium", "full track")
    estimate = (header_value(text, "Estimate") or "").strip().upper()[:1]
    if estimate and estimate != "S":
        add("medium", f"estimate {estimate}")

    zones = _zones(central)
    diagrams_path = story.design("diagrams") / "diagrams.json"
    design, why_not = read_json(diagrams_path)
    planned_repos: set[str] = set()
    if design is None:
        add("medium", f"{story.rel(diagrams_path)} {why_not}: the design's touch points cannot be checked")
    else:
        for point in design.get("touchPoints") or []:
            element, status = str(point.get("element", "")), str(point.get("status", ""))
            if point.get("repo"):
                planned_repos.add(str(point["repo"]))
            if status == "removed":
                add("high", f"design removes {element}")
            if element.startswith(RESOURCES) and status in ("new", "changed"):
                add("medium", f"design adds or changes {element}")
            zone = _zone_of(str(point.get("file") or ""), zones) if point.get("file") else None
            if zone:
                add("high", f"design touches {point['file']} ({zone})")
        if design.get("impacted"):
            add("high", f"other repos affected: {len(design['impacted'])}")
    if len(planned_repos) > 1:
        add("medium", f"design spans {len(planned_repos)} repos")

    diff_path = story.qa("diff-shape.json")
    diff, _ = read_json(diff_path)
    if diff:
        built = diff_files(diff)
        repos = {repo for repo, _ in built if repo}
        if len(repos) > 1:
            add("medium", f"diff spans {len(repos)} repos")
        for _, file in built:
            zone = _zone_of(file, zones)
            if zone:
                add("high", f"diff touches {file} ({zone})")
        for item in diff.get("breakingContract") or []:
            add("high", f"breaking contract: {item}")
        for item in diff.get("newDependencies") or []:
            add("high", f"new dependency: {item}")
        planned = {str(p.get("element")) for p in (design or {}).get("touchPoints") or []}
        for item in diff.get("writesCollections") or []:
            if f"collection:{item}" not in planned:
                add("medium", f"diff writes collection {item}, not in the design")

    tier = max((r["level"] for r in reasons), key=TIERS.index, default="low")
    lenses = ["edge-case", "verification-gap", "craft", "conformance", "domain"]
    if tier == "low":
        lenses = ["conformance", "verification-gap"]
        if rules_touched(story.design()):
            lenses.append("domain")  # the design names business rules: keep the lens that checks them
    return {
        "story": story.story_id,
        "tier": tier,
        "lenses": lenses,
        "reasons": reasons,
        "inputs": {"design": design is not None, "diff": diff is not None},
    }


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    try:
        result = assess(central, args.story)
    except FileNotFoundError as exc:
        print(f"baton risk: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    story = find_story(central, args.story)
    out = story.qa("risk.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=1))
        return EXIT_OK
    print(f"{result['story']}: {result['tier']} risk - QA review lenses: {', '.join(result['lenses'])}")
    for reason in result["reasons"]:
        print(f"  {reason['level']:<6} {reason['why']}")
    if not result["reasons"]:
        print("  nothing raises it: one repo, no risk zone, no new resource, estimate S")
    print(f"wrote {story.rel(out)}")
    return EXIT_OK
