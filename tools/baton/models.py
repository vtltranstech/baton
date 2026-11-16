"""Which model each role runs on for one story, from profile/models.yaml. No model is called.

baton models S-010          the resolved model per role and the implementer / reviewer pairing
baton models S-010 --json   the same as JSON
baton models --check        validate profile/models.yaml only (rule 1 on every track)

contracts/models-and-activation.md section 3. The skill that launches an agent passes the model this
prints; agents keep `model: inherit`. Rule 1: a reviewer is never a weaker model than the role it reviews,
including the developer's escalations. Rule 2: it differs whenever rule 1 allows. A file that breaks
rule 1 is refused (exit 2). Without profile/models.yaml the framework defaults apply and say so.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from baton import miniyaml
from baton.confidence import header_value, project_value, read_json
from baton.state_check import find_story, section, track_of

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
ORDER = ("cheap", "fast", "strong")
TRACKS = ("light", "full", "spike")
ROLES = ("story-drafter", "architect", "developer", "design-lenses", "review-lenses", "qa", "security",
         "documentation", "release")
# (reviewer, implementer): rule 1 holds per track for each pair.
REVIEWS = (("design-lenses", "architect"), ("review-lenses", "developer"), ("security", "developer"))
DEFAULTS = {
    "version": 1,
    "aliases": {"fast": "sonnet", "strong": "opus", "cheap": "haiku"},
    "roles": {
        "story-drafter": {"light": "fast", "full": "fast", "spike": "fast"},
        "architect": {"light": "fast", "full": "strong", "spike": "strong"},
        "developer": {"light": "fast", "full": "fast", "spike": "fast"},
        "design-lenses": {"light": "strong", "full": "strong", "spike": "strong"},
        "review-lenses": {"light": "strong", "full": "strong", "spike": "strong"},
        "qa": {"light": "fast", "full": "fast", "spike": "fast"},
        "security": {"light": "strong", "full": "strong", "spike": "strong"},
        "documentation": {"light": "cheap", "full": "fast", "spike": "fast"},
        "release": {"light": "cheap", "full": "cheap", "spike": "cheap"},
    },
    "escalation": {"developer_after_qa_fail": "strong", "developer_when_diff_shape_flags": "strong"},
    "rules": {
        "reviewer_never_weaker_than_implementer": True,
        "reviewer_differs_from_implementer_when_possible": True,
    },
}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("story", nargs="?", help="story id, e.g. S-010")
    parser.add_argument("--check", action="store_true", help="validate profile/models.yaml only")


def load(central: Path) -> tuple[dict, str]:
    path = Path(central) / "profile" / "models.yaml"
    if not path.is_file():
        return DEFAULTS, "framework defaults (no profile/models.yaml)"
    return miniyaml.load_file(str(path)) or {}, "profile/models.yaml"


def problems(doc: dict) -> list[str]:
    """Shape errors and rule-1 violations; empty when the file is usable."""
    found = []
    aliases = doc.get("aliases") if isinstance(doc.get("aliases"), dict) else {}
    for alias in ORDER:
        if not str(aliases.get(alias) or "").strip():
            found.append(f"aliases.{alias} is missing")
    roles = doc.get("roles") if isinstance(doc.get("roles"), dict) else {}
    for role in ROLES:
        tracks = roles.get(role)
        if not isinstance(tracks, dict):
            found.append(f"roles.{role} is missing")
            continue
        for track in TRACKS:
            if tracks.get(track) not in ORDER:
                found.append(f"roles.{role}.{track} must be one of {', '.join(ORDER)}")
    escalation = doc.get("escalation") or {}
    for key, value in escalation.items():
        if value not in ORDER:
            found.append(f"escalation.{key} must be one of {', '.join(ORDER)}")
    if found:
        return found
    for reviewer, implementer in REVIEWS:
        for track in TRACKS:
            authors = [roles[implementer][track]]
            if implementer == "developer":
                authors += [v for v in escalation.values() if v in ORDER]
            strongest = max(authors, key=ORDER.index)
            if ORDER.index(roles[reviewer][track]) < ORDER.index(strongest):
                found.append(
                    f"rule 1: {reviewer} ({roles[reviewer][track]}) reviews {implementer} "
                    f"({strongest}) on the {track} track; a reviewer is never weaker than its implementer"
                )
    if (doc.get("rules") or {}).get("reviewer_never_weaker_than_implementer") is False:
        found.append("rules.reviewer_never_weaker_than_implementer cannot be switched off")
    return found


def escalations(story) -> list[str]:
    """Which developer escalations apply now: a failed QA loop, or diff-shape flags."""
    applied = []
    report = story.qa("test-report.md")
    status = (story.central / "docs" / "status.md")
    loops = 0
    if status.is_file():
        pattern = rf"^\|\s*{re.escape(story.story_id)}\s*\|[^|]*\|\s*(\d+)\s*\|"
        row = re.search(pattern, status.read_text(), re.M)
        loops = int(row.group(1)) if row else 0
    if loops or (report.is_file() and re.search(r"^##\s*Verdict:\s*FAIL", report.read_text(), re.M)):
        applied.append("developer_after_qa_fail")
    diff, _ = read_json(story.qa("diff-shape.json"))
    if diff:
        text = story.text()
        estimate = (header_value(text, "Estimate") or "").strip().upper()[:1]
        limit = project_value(story.central, f"estimate.lines.{estimate}") if estimate else None
        repos = diff.get("repos") or []
        lines = sum(int(r.get("linesAdded", 0)) + int(r.get("linesDeleted", 0)) for r in repos)
        over = bool(limit and limit.isdigit() and lines > int(limit))
        if diff.get("newDependencies") or over:
            applied.append("developer_when_diff_shape_flags")
    return applied


def resolve(doc: dict, track: str, applied: list[str]) -> dict[str, dict]:
    aliases, roles, escalation = doc["aliases"], doc["roles"], doc.get("escalation") or {}
    out = {}
    for role in ROLES:
        alias = roles[role][track]
        why = None
        if role == "developer":
            for key in applied:
                target = escalation.get(key)
                if target and ORDER.index(target) > ORDER.index(alias):
                    alias, why = target, key
        out[role] = {"alias": alias, "model": aliases[alias], "escalated": why}
    return out


def pairing(resolved: dict) -> list[str]:
    """The implementer / reviewer pairs, with whether they differ (rule 2)."""
    lines = []
    for reviewer, implementer in REVIEWS:
        a, b = resolved[implementer], resolved[reviewer]
        same = a["alias"] == b["alias"]
        note = "independent by context only" if same else "different models"
        lines.append(f"{implementer} by {a['model']}, reviewed by {b['model']} ({reviewer}; {note})")
    return lines


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    try:
        doc, source = load(central)
    except (ValueError, OSError) as exc:
        print(f"baton models: profile/models.yaml cannot be read ({exc})", file=sys.stderr)
        return EXIT_REFUSED
    wrong = problems(doc)
    if wrong:
        print(f"baton models: refused, {source}:", file=sys.stderr)
        print("\n".join(f"  {w}" for w in wrong), file=sys.stderr)
        return EXIT_REFUSED
    if args.check or not args.story:
        print(f"{source}: valid; reviewers are never weaker than what they review on any track")
        return EXIT_OK
    try:
        story = find_story(central, args.story)
        text = story.text()
    except FileNotFoundError as exc:
        print(f"baton models: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    spike = (header_value(text, "Jira-Type") or "").lower() == "spike"
    track = track_of(text) or ("spike" if spike else "full")
    applied = escalations(story) if section(text, "Dev summary") is not None else []
    resolved = resolve(doc, track, applied)
    result = {"story": story.story_id, "track": track, "source": source, "escalations": applied,
              "roles": resolved, "pairing": pairing(resolved)}
    if args.json:
        print(json.dumps(result, indent=1))
        return EXIT_OK
    print(f"{story.story_id} ({track} track) - {source}")
    for role, value in resolved.items():
        extra = f"  (escalated: {value['escalated']})" if value["escalated"] else ""
        print(f"  {role:<14} {value['alias']:<7} {value['model']}{extra}")
    for line in result["pairing"]:
        print(f"  {line}")
    return EXIT_OK
