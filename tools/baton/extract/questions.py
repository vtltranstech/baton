"""The open questions: what extraction could not answer, per the gap table in the plan's section 3."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from urllib.parse import urlsplit

from baton.extract.repos import UNKNOWN

_OWNERSHIP_FILES = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", "catalog-info.yaml")
_UNRESOLVED_GAP = {"endpoint": 5, "topic": 6, "queue": 6, "file": 7, "job": 7, "collection": 3}
_MAX_BATCH = 8


def _section(text: str, title: str) -> str:
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("#"):
            if inside:
                break
            inside = line.lstrip("#").strip().lower().startswith(title)
            continue
        if inside:
            lines.append(line)
    return "\n".join(lines).strip()


def read_answers(central: Path) -> dict[str, str]:
    """`## Onboard answers` in project.md: `| question id | answer |`. Answered means not asked again."""
    path = central / "profile" / "project.md"
    answers = {}
    for line in _section(path.read_text(encoding="utf-8"), "onboard answers").splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) >= 2 and cells[1] and set(cells[0]) - set("-: "):
            answers[cells[0]] = cells[1]
    answers.pop("id", None)
    return answers


def _matches(path: str, pattern: str) -> bool:
    if path == pattern or fnmatch.fnmatch(path, pattern):
        return True
    return fnmatch.fnmatch(path, pattern.replace("**/", "")) if pattern.startswith("**/") else False


def _words(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).lower()


def _seeds(results) -> tuple[list[str], list[str]]:
    glossary, invariants = set(), set()
    for result in results:
        glossary |= {c["name"] for c in result.entry["collections"]}
        for parsed in result.sources.main:
            if ".dto" in f".{parsed.package}":
                glossary |= {t.name for t in parsed.types}
        for parsed in result.sources.test:
            for decl in parsed.types:
                if decl.name.endswith("ArchitectureTest"):
                    continue
                for method in decl.methods:
                    names = {a.name: a for a in method.annotations}
                    display = names.get("DisplayName")
                    if display is not None and display.args.get("value") is not None:
                        invariants.add(display.args["value"].value)
                    elif names.keys() & {"Test", "ParameterizedTest"}:
                        invariants.add(_words(method.name))
    return sorted(glossary), sorted(invariants)


def build_questions(central: Path, outcome: dict) -> tuple[list[dict], list[str], list[str]]:
    """(open questions, ids already answered, warnings)."""
    results, rows = outcome["results"], outcome["rows"]
    project = (central / "profile" / "project.md").read_text(encoding="utf-8")
    domain_path = central / "profile" / "domain.md"
    domain = domain_path.read_text(encoding="utf-8") if domain_path.is_file() else ""
    questions: list[dict] = []
    warnings: list[str] = []

    def ask(qid: str, gap: int, text: str, writes_to: str, repo: str | None = None, **more) -> None:
        item = {"id": qid, "gap": gap, "ask": text, "writesTo": writes_to}
        if repo:
            item["repo"] = repo
        item.update({k: v for k, v in more.items() if v})
        questions.append(item)

    _repo_questions(results, rows, ask, warnings, project)
    _graph_questions(results, ask, domain)
    _review_questions(outcome, ask, domain)
    glossary, invariants = _seeds(results)
    if not _section(project, "domain words"):
        ask("domain-words", 9, "Define up to ten domain terms.", "profile/project.md", seeds=glossary)
    if not _section(domain, "invariants"):
        ask(
            "invariants",
            10,
            "Which of these are real business invariants? Add any the tests miss.",
            "profile/domain.md",
            seeds=invariants,
        )
    if "jira." not in project:
        ask("jira-conventions", 13, "Jira status names and the opt-in label?", "profile/project.md")

    answers = read_answers(central)
    answered = sorted(q["id"] for q in questions if q["id"] in answers)
    remaining = sorted((q for q in questions if q["id"] not in answers), key=lambda q: (q["gap"], q["id"]))
    return remaining, answered, sorted(set(warnings))


def _team_column(project: str) -> bool:
    for line in project.splitlines():
        if line.lstrip().startswith("|") and "path" in line.lower():
            return "team" in [c.strip().lower() for c in line.strip().strip("|").split("|")]
    return False


def _repo_questions(results, rows, ask, warnings, project) -> None:
    row_of = {r["repo"]: r for r in rows}
    for result in results:
        name = result.entry["repo"]
        row = row_of[name]
        root = result.sources.repo.path
        is_java = row["build"] in ("maven", "gradle")
        if result.entry["commit"] == UNKNOWN:
            ask(
                f"commit:{name}",
                1,
                f"No commit can be recorded: {result.commit_reason}. Is this path right?",
                "profile/project.md",
                name,
            )
        if result.dirty:
            warnings.append(
                f"{name}: working tree has uncommitted changes; edges may not match the recorded commit"
            )
        fields = (
            ["build"]
            if row["build"] == UNKNOWN
            else (["java", "springBoot", "packageRoot"] if is_java else ["buildCmd", "testCmd", "ui"])
        )
        if row["build"] != UNKNOWN and is_java:
            fields += ["buildCmd", "testCmd"]
        for key in fields:
            if row.get(key) == UNKNOWN:
                ask(
                    f"stack:{name}:{key}",
                    1,
                    f"{key} could not be detected for {name}. What is it?",
                    "profile/stack-detected.md (rerun after fixing the build file) or profile/project.md",
                    name,
                )
        layout_notes = [p for p in row["problems"] if p.startswith("layout:")]
        for problem in row["problems"]:
            if not problem.startswith("layout:"):
                ask(
                    f"build-file:{name}:{problem}",
                    1,
                    f"{problem}. How should this repo be read?",
                    "profile/project.md",
                    name,
                )
        if result.sources.main and any(v == UNKNOWN for v in row.get("layout", {}).values()):
            ask(
                f"layout:{name}",
                2,
                "The layer map could not be settled. Which package is which layer?",
                "profile/project.md",
                name,
                detected=row.get("layout"),
                detail=layout_notes,
            )
        for failure in result.sources.failures:
            ask(
                f"parse-failure:{name}:{failure['file']}",
                5,
                f"{failure['file']} could not be parsed, so no edge comes from it. Fix or describe it.",
                "profile/project.md",
                name,
                detail=failure["reason"],
            )
        for directory in result.sources.other_languages:
            ask(
                f"other-language:{name}:{directory}",
                5,
                f"{directory} holds Kotlin, which the extractors do not read. What does it connect to?",
                "profile/project.md",
                name,
            )
        for nested in result.sources.nested:
            warnings.append(
                f"{name}: {nested} has its own build file and is not a declared module: not extracted"
            )
        warnings += [f"{name}: {note}" for note in result.notes]
        _config_questions(result, name, ask)
        ownership = _team_column(project) or any((root / f).is_file() for f in _OWNERSHIP_FILES)
        if not ownership:
            ask(
                f"ownership:{name}",
                12,
                f"Which team owns {name}, and on which channel?",
                "profile/project.md",
                name,
            )
        if is_java:
            keys = {k for c in result.configs.values() for k in c.keys}
            if not any(k.startswith("resilience4j") or "timeout" in k.lower() for k in keys):
                ask(
                    f"nfr-defaults:{name}",
                    14,
                    "No timeout or retry config found. Accept the defaults or override?",
                    "profile/project.md",
                    name,
                )
            if not row["testcontainers"]:
                ask(
                    f"integration-tests:{name}",
                    15,
                    "No Testcontainers in the build. Where do integration tests run?",
                    "profile/project.md",
                    name,
                )


def _config_questions(result, name, ask) -> None:
    for config in result.configs.values():
        for file, reason in config.errors.items():
            ask(
                f"config-unreadable:{name}:{file}",
                5,
                f"{file} could not be read, so placeholders that may live there stay open.",
                "the file itself",
                name,
                detail=reason,
            )
        for key, values in sorted(config.used_overrides.items()):
            ask(
                f"profile-override:{name}:{key}",
                5,
                f"{key} differs by profile; edges use the base value. Which systems do the others point at?",
                "profile/project.md",
                name,
                values=values,
            )
    result.profile_only = {k: v for c in result.configs.values() for k, v in c.used_only_in_profile.items()}


def _graph_questions(results, ask, domain) -> None:
    edges = [(r.entry["repo"], e) for r in results for e in r.entry["edges"]]
    for result in results:
        name = result.entry["repo"]
        for node in result.entry["unresolved"]:
            prefix = node.split(":", 1)[0]
            candidates = {k: v for k, v in result.profile_only.items() if "${" + k in node}
            ask(
                f"unresolved:{name}:{node}",
                _UNRESOLVED_GAP.get(prefix, 5),
                f"{node} could not be resolved from the code or config. Which system or value is it?",
                "profile/project.md",
                name,
                onlyInProfiles=candidates,
            )
        if result.entry["collections"]:
            ask(
                f"shared-collections:{name}",
                3,
                "Are any of these collections shared with other apps?",
                "profile/project.md",
                name,
                seeds=[c["name"] for c in result.entry["collections"]],
            )
    still_open = {node for r in results for node in r.entry["unresolved"]}
    kinds_by_node: dict[str, set[str]] = {}
    for _, edge in edges:
        kinds_by_node.setdefault(edge["to"], set()).add(edge["kind"])
    for node, kinds in sorted(kinds_by_node.items()):
        prefix = node.split(":", 1)[0]
        if node in still_open:
            continue
        if prefix in ("topic", "queue") and len(kinds) == 1:
            side = "consumes" if "PUBLISHES" in kinds else "publishes to"
            ask(
                f"messaging-peer:{node}",
                6,
                f"Which system {side} {node}? No repo here does.",
                "profile/domain.md",
            )
        elif prefix == "file" and len(kinds) == 1:
            side = "reads" if "WRITES_FILE" in kinds else "produces"
            ask(
                f"file-peer:{node}",
                7,
                f"Which system {side} {node}, and on what schedule?",
                "profile/domain.md",
            )
        elif prefix == "job":
            ask(f"job-schedule:{node}", 7, f"What runs {node}, and on what schedule?", "profile/domain.md")
    known = _section(domain, "external systems")
    bases = set()
    for _, edge in edges:
        if edge["kind"] == "CALLS_ENDPOINT" and edge["to"] not in still_open:
            parts = urlsplit(edge["to"].split(" ", 1)[1])
            if parts.scheme and parts.netloc:
                bases.add(f"{parts.scheme}://{parts.netloc}")
    for base in sorted(bases):
        if urlsplit(base).netloc not in known:
            ask(
                f"external-system:{base}",
                16,
                f"What system is {base}?",
                "profile/domain.md section External systems",
            )


def _review_questions(outcome, ask, domain) -> None:
    aggregates, zones = outcome["aggregates"], outcome["zones"]
    pending = [a["name"] for a in aggregates if a.get("confirmed") is False]
    if pending:
        ask(
            "confirm-aggregates",
            4,
            "Tech Lead: confirm or edit these aggregate boundaries, then set confirmed: true.",
            "profile/aggregates.yaml",
            seeds=pending,
        )
    known_roots = {f"class:{d[0].fqcn}" for r in outcome["results"] for d in r.documents}
    for entry in aggregates:
        if entry.get("confirmed") is not False and entry.get("root") not in known_roots:
            ask(
                f"stale-aggregate:{entry.get('root')}",
                4,
                f"Confirmed aggregate {entry.get('name')} has no @Document root in the code now. Keep it?",
                "profile/aggregates.yaml",
            )
    pending = [z["name"] for z in zones if z.get("confirmed") is False]
    if pending:
        ask(
            "confirm-risk-zones",
            11,
            "Tech Lead: confirm or edit these risk zones, then set confirmed: true.",
            "profile/risk-zones.yaml",
            seeds=pending,
        )
    reviewed = {z.get("name"): z for z in zones if z.get("confirmed") is not False}
    for seed in outcome["zone_seeds"]:
        zone = reviewed.get(seed["name"])
        if zone is None:
            continue
        uncovered = [p for p in seed["paths"] if not any(_matches(p, g) for g in zone.get("paths") or [])]
        if uncovered:
            ask(
                f"risk-zone-new-paths:{seed['name']}",
                11,
                f"The reviewed zone {seed['name']} does not cover these paths. Add them?",
                "profile/risk-zones.yaml",
                seeds=uncovered,
            )
    if "mastering" not in domain.lower():
        ask(
            "mastering-boundaries",
            11,
            "Which writes go back to a system of record? They become risk zones.",
            "profile/risk-zones.yaml",
        )


def batches(questions: list[dict]) -> list[list[str]]:
    """Question ids in interview batches: at most eight at a time, in gap order."""
    ids = [q["id"] for q in questions]
    return [ids[i : i + _MAX_BATCH] for i in range(0, len(ids), _MAX_BATCH)]
