"""Lint the agents and skills of the core: blueprints, handoffs, hooks, activation, the fix-loop rule.

baton agents check            every agents/*.md and skills/*/SKILL.md; exit 1 with one line per problem
baton agents check --root P   another core checkout (default: the one this command ships in)

Deterministic (contracts/agent-enhancements.md section 13): every agent opens with a `## Blueprint`
(Trigger, Input, Action, Output, Handoff, Outcome, Never, once each); every Input is a path or a manifest;
every Handoff is a gate or a skill that exists; every Outcome is a row of docs/roles.md; every `Never` names
hooks that exist; every agent states the provenance footer rule (the context agents carry their note header
instead); every skill declares how it activates; the developer keeps the triage-only fix-loop rule.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK, EXIT_FAILED = 0, 1
FIELDS = ("Trigger", "Input", "Action", "Output", "Handoff", "Outcome", "Never")
ROOT = Path(__file__).resolve().parents[2]
_PATHLIKE = re.compile(r"^(?:[\w.<>${}*-]+/|[\w.<>-]+\.(?:md|yaml|yml|json|dsl|txt|xml)\b|\.[\w-]+/)")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=("check",), help="check: lint agents and skills")
    parser.add_argument("--root", help="the core checkout to lint (default: this one)")


def front(text: str) -> dict[str, str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}
    body = text[4 : text.index("\n---\n", 4)]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^([\w-]+):[ \t]*(.*)$", body, re.M)}


def as_list(value: str) -> list[str]:
    return [v.strip().strip("\"'") for v in value.strip("[]").split(",") if v.strip()]


def blueprint(text: str) -> tuple[dict[str, str], list[str]]:
    """The blueprint fields, and what is wrong with their shape."""
    body = text[text.index("\n---\n", 4) + 5 :] if text.startswith("---\n") else text
    if not body.lstrip("\n").startswith("## Blueprint"):
        return {}, ["does not open with `## Blueprint` right after the frontmatter"]
    block = body.lstrip("\n").split("\n\n", 1)[0]
    fields: dict[str, str] = {}
    problems = []
    for match in re.finditer(r"^-[ \t]+(\w+):[ \t]*(.*)$", block, re.M):
        name, value = match.group(1), match.group(2).strip()
        if name in fields:
            problems.append(f"blueprint has {name} twice")
        fields[name] = value
    problems += [f"blueprint has no {name}" for name in FIELDS if not fields.get(name)]
    problems += [
        f"blueprint field {name} is not one of {', '.join(FIELDS)}" for name in fields if name not in FIELDS
    ]
    return fields, problems


def outcomes(root: Path) -> set[str]:
    try:
        text = (root / "docs" / "roles.md").read_text(encoding="utf-8")
    except OSError:
        return set()
    part = re.search(r"^## Outcomes\b(.*?)(?=^## |\Z)", text, re.M | re.S)
    rows = [
        line.strip().strip("|").split("|")[0].strip()
        for line in (part.group(1) if part else "").splitlines()
        if line.strip().startswith("|")
    ]
    return {row for row in rows if row and row != "Outcome" and not set(row) <= set("-: ")}


def check_agent(path: Path, root: Path, known_outcomes: set[str]) -> list[str]:
    text = path.read_text(encoding="utf-8")
    fields, problems = blueprint(text)
    for item in (i.strip() for i in fields.get("Input", "").split(";") if i.strip()):
        if not (item.lower().startswith("manifest") or _PATHLIKE.match(item)):
            problems.append(f"Input `{item}` is not a path or a manifest")
    handoff = fields.get("Handoff", "")
    skill = re.match(r"^/([a-z][\w-]*)", handoff)
    if handoff and not re.match(r"^gate [0-3]\b", handoff) and not skill:
        problems.append(f"Handoff `{handoff}` is not a gate (gate 0-3) or a skill (/name)")
    if skill and not (root / "skills" / skill.group(1) / "SKILL.md").is_file():
        problems.append(f"Handoff names /{skill.group(1)}, which is not a skill")
    outcome = fields.get("Outcome")
    if outcome and outcome not in known_outcomes:
        problems.append(f"Outcome `{outcome}` is not a row of docs/roles.md ## Outcomes")
    never = fields.get("Never", "")
    hooks = re.search(r"\(hooks:[ \t]*([^)]*)\)", never)
    if never and not hooks:
        problems.append("Never does not list the hooks that apply, as `(hooks: a, b)`")
    for hook in as_list(hooks.group(1)) if hooks else []:
        if not (root / "hooks" / f"{hook}.py").is_file():
            problems.append(f"Never names hook {hook}, which is not in hooks/")
    if outcome != "Understood system" and "provenance footer" not in text:
        problems.append("does not state the provenance footer rule")
    if path.stem == "developer" and not re.search(r"triage\.md`?,? the consolidated|only review input", text):
        problems.append("lost the fix-loop rule: the triage file is the only review input")
    return [f"{path.relative_to(root)}: {p}" for p in problems]


def stay_invocable(root: Path) -> set[str]:
    """Skills the activation contract keeps model-invocable (its rows whose mechanism says they stay)."""
    try:
        text = (root / "contracts" / "models-and-activation.md").read_text(encoding="utf-8")
    except OSError:
        return set()
    names: set[str] = set()
    for line in text.splitlines():
        cells = line.strip().strip("|").split("|")
        if len(cells) >= 2 and re.search(r"stay (model-)?invocable", cells[1]):
            for span in re.findall(r"`([^`]+)`", cells[0]):
                names |= set(re.findall(r"(?<![\w-])/?([a-z][\w-]*)", span))
    return names


def check_skills(root: Path) -> list[str]:
    preloaded: set[str] = set()
    for agent in sorted((root / "agents").glob("*.md")):
        preloaded |= set(as_list(front(agent.read_text(encoding="utf-8")).get("skills", "")))
    invocable, problems = stay_invocable(root), []
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        meta, name = front(path.read_text(encoding="utf-8")), path.parent.name
        if not meta:
            problems.append(f"{path.relative_to(root)}: no frontmatter")
            continue
        human_only = meta.get("disable-model-invocation") == "true"
        if human_only and name in invocable:
            problems.append(f"{path.relative_to(root)}: chained skill must stay model-invocable")
        if not (human_only or "paths" in meta or name in preloaded or name in invocable):
            problems.append(
                f"{path.relative_to(root)}: declares no activation (disable-model-invocation, paths, "
                "an agent's skills: list, or a stay-invocable row in contracts/models-and-activation.md)"
            )
    return problems


def check(root: Path) -> list[str]:
    known = outcomes(root)
    problems = [] if known else ["docs/roles.md: no ## Outcomes table"]
    for path in sorted((root / "agents").glob("*.md")):
        problems += check_agent(path, root, known)
    return problems + check_skills(root)


def run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else ROOT
    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        agents = len(list((root / "agents").glob("*.md")))
        skills = len(list((root / "skills").glob("*/SKILL.md")))
        print(f"ok: {agents} agents, {skills} skills")
    return EXIT_FAILED if problems else EXIT_OK
