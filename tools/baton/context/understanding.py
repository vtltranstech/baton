"""System understanding (contracts/context-map.md section 10): the explorers' notes, graded against the code.

A context explorer works like an engineer in their first weeks: it takes one area (a module), reads its code,
tests, documents and the architecture diagrams, and writes a note saying what the area is for, every
collection, topic, endpoint and file it touches, what each business branch point decides, and what it could
not find out. The integrator joins the notes into end-to-end flows and the landscape of systems upstream and
downstream. Nothing is trusted because a model wrote it: every claim must name an edge the extractors found
and a citation that resolves, each flow step must share an area or a resource with the next, every entry
point must sit in a flow, and a blocking question with no human answer keeps the area out of `understood`.
No model call and no network here; the agents are run by the build-context-map skill.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from baton.context import domain as dm
from baton.context.product import Module, Repo
from baton.extract.repos import UNKNOWN

FOLDER = "docs/context/understanding"
AREAS = f"{FOLDER}/areas"
FLOWS = f"{FOLDER}/flows"
LANDSCAPE = f"{FOLDER}/landscape.md"
STATUS_JSON = f"{FOLDER}/status.json"
STATUS_MD = f"{FOLDER}/status.md"
ASKED_JSON = f"{FOLDER}/asked.json"
QUESTIONS_MD = "docs/context/questions.md"

VERBS = {
    "exposes": ("EXPOSES",),
    "consumes": ("CONSUMES",),
    "reads": ("READS_COLLECTION", "READS_FILE"),
    "writes": ("WRITES_COLLECTION", "WRITES_FILE"),
    "publishes": ("PUBLISHES",),
    "calls": ("CALLS_ENDPOINT",),
}
VERB_OF = {kind: verb for verb, kinds in VERBS.items() for kind in kinds}
ENTRY_VERBS = ("exposes", "consumes")
STATES = ("unexplored", "stale", "incomplete", "blocked", "understood")
DIRECTIONS = ("upstream", "downstream", "both", "none")
MIN_WORDS = 3

_HEADER = re.compile(r"<!--\s*baton:understanding\s+area=(\S+)\s+commit=(\S+)(?:\s+code=(\S+))?\s*-->")
_SEPARATOR = r"\s+(?:—|--|-)\s+"
_CLAIM = re.compile(r"^-\s+(\w+)\s+(.+?)" + _SEPARATOR + r"(.*)$")
_STEP = re.compile(r"^\d+\.\s+(\S+)\s+(\w+)\s+(.+?)" + _SEPARATOR + r"(.*)$")
_CITE = re.compile(r"\[([^\]\n]+)\](?!\()")
_QUESTION = re.compile(r"^-\s+(Q\d+)\s+\((blocking|open),\s*(PO|TL)\)\s*:\s*(.+)$")
_ANSWER = re.compile(r"^\s+answer:\s*(\S.*)$")
_CONTRA = re.compile(r"^-\s+(C\d+)\s*:\s*(.+)$")
_RESOLVED = re.compile(r"^\s+resolved:\s*(\S.*)$")
_QREF = re.compile(r"\bQ\d+\b")
_RULE = re.compile(r"\bR\d+\b")
_BP = re.compile(r"\bbp-\d+\b")
_LINE = re.compile(r"^(.*?):(\d+)(?:-\d+)?$")


def note_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", key.replace("/", "--")) + ".md"


def areas_of(repos: list[Repo]) -> dict[str, tuple[Repo, Module]]:
    return {m.key: (r, m) for r in repos for m in r.modules.values() if m.sources}


def facts(module: Module) -> dict[tuple[str, str], str]:
    """(verb, resource) -> where the extractors found it, for every edge of the module."""
    out: dict[tuple[str, str], str] = {}
    for edge in module.edges:
        verb = VERB_OF.get(str(edge.get("kind")))
        if verb:
            prov = edge.get("provenance") or {}
            out.setdefault((verb, str(edge.get("to"))), f"{prov.get('file')}:{prov.get('line')}")
    return out


def code_hash(repo: Repo, module: Module) -> str:
    """A fingerprint of the area's own source and test files: a note goes stale when they change, not when
    some other module of the same repo does."""
    digest = hashlib.sha1()
    for path in sorted(module.sources + module.tests):
        try:
            data = path.read_bytes()
        except OSError:
            data = b""
        digest.update(path.relative_to(repo.path).as_posix().encode() + b"\0" + data + b"\0")
    return digest.hexdigest()[:12]


def header(repo: Repo, module: Module) -> str:
    return (
        f"<!-- baton:understanding area={module.key} commit={repo.commit} code={code_hash(repo, module)} -->"
    )


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z]{2,}", _CITE.sub(" ", text)))


@dataclass
class Question:
    id: str
    blocking: bool
    ask: str
    text: str
    answer: str = ""

    def data(self, where: str) -> dict:
        return {
            "id": self.id,
            "blocking": self.blocking,
            "ask": self.ask,
            "text": self.text,
            "answer": self.answer,
            "where": where,
        }


def questions(lines: list[str]) -> list[Question]:
    out: list[Question] = []
    for line in lines:
        answer = _ANSWER.match(line)
        if answer and out:
            out[-1].answer = answer.group(1).strip()
            continue
        found = _QUESTION.match(line.strip())
        if found:
            out.append(Question(found[1], found[2] == "blocking", found[3], found[4].strip()))
    return out


@dataclass
class Contradiction:
    id: str
    text: str
    resolved: str = ""

    def data(self) -> dict:
        return {"id": self.id, "text": self.text, "resolved": self.resolved}


def contradictions(lines: list[str]) -> tuple[list[Contradiction], list[str]]:
    """`- C<n>: <document> says ..., the code ... [cite] [cite]`, settled by a human's
    `  resolved: <words> (<role>, <date>)` on the next line. A line saying none were found is not one."""
    out: list[Contradiction] = []
    problems: list[str] = []
    for line in lines:
        resolved = _RESOLVED.match(line)
        if resolved and out:
            out[-1].resolved = resolved.group(1).strip()
            continue
        if not line.startswith("- "):
            continue
        found = _CONTRA.match(line.strip())
        if found:
            out.append(Contradiction(found[1], found[2].strip()))
        elif not re.match(r"^-\s+(none|no contradiction)", line.strip(), re.I):
            problems.append(
                f"cannot read contradiction `{line.strip()[:70]}`: write `- C<n>: <document> says ..., "
                "the code ... [cite] [cite]`"
            )
    return out, problems


class Citations:
    """Does `[path:line]`, `[path#Section]` or `[R3]` point at something that exists?"""

    def __init__(self, central: Path, repos: list[Repo], domain: dm.Domain):
        self.central = central
        self.repos = {r.name: r for r in repos}
        self.rules = {r.id for r in domain.rules}
        self._lines: dict[Path, int] = {}

    def _count(self, path: Path) -> int:
        if path not in self._lines:
            self._lines[path] = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return self._lines[path]

    def problem(self, cite: str, repo: Repo | None) -> str | None:
        cite = cite.strip().strip("`")
        if _RULE.fullmatch(cite):
            return None if cite in self.rules else f"[{cite}] is not a rule in profile/domain.md"
        path, _, _anchor = cite.partition("#")
        found = _LINE.match(path)
        name, line = (found[1], int(found[2])) if found else (path, 0)
        bases = [self.central]
        if repo is not None:
            bases.append(repo.path)
        head, _, rest = name.partition("/")
        if head in self.repos and rest:
            bases.append(self.repos[head].path)
            candidates = [self.repos[head].path / rest] + [b / name for b in bases]
        else:
            candidates = [b / name for b in bases]
        target = next((c for c in candidates if c.is_file()), None)
        if target is None:
            return f"[{cite}] is not a file in the central repo{' or ' + repo.name if repo else ''}"
        if line and not 1 <= line <= self._count(target):
            return f"[{cite}]: {name} has {self._count(target)} lines"
        return None

    def check(self, text: str, repo: Repo | None, what: str, required: bool = True) -> list[str]:
        cites = _CITE.findall(text)
        if not cites:
            return (
                [f"{what} cites nothing: add [<file>:<line>] or [<document>#<section>]"] if required else []
            )
        return [f"{what}: {p}" for p in (self.problem(c, repo) for c in cites) if p]


@dataclass
class AreaGrade:
    key: str
    note: str
    status: str = "unexplored"
    problems: list[str] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    stale: bool = False

    def settle(self) -> None:
        if self.status == "unexplored":
            return
        blocked = any(q.blocking and not q.answer for q in self.questions) or any(
            not c.resolved for c in self.contradictions
        )
        self.status = (
            "stale"
            if self.stale
            else "incomplete"
            if self.problems
            else "blocked"
            if blocked
            else "understood"
        )

    def data(self) -> dict:
        return {
            "status": self.status,
            "note": self.note,
            "problems": self.problems,
            "questions": [q.data(self.note) for q in self.questions],
            "contradictions": [c.data() for c in self.contradictions],
        }


def grade_area(central: Path, repo: Repo, module: Module, points: list[dict], cites: Citations) -> AreaGrade:
    rel = f"{AREAS}/{note_name(module.key)}"
    grade = AreaGrade(module.key, rel)
    path = central / rel
    if not path.is_file():
        grade.problems.append(f"no note yet: write {rel}")
        return grade
    grade.status = "explored"
    text = path.read_text(encoding="utf-8", errors="replace")
    problems = grade.problems
    head = _HEADER.search(text)
    if head is None:
        problems.append(f"the first line must be {header(repo, module)}")
    elif head[1] != module.key:
        problems.append(f"the note says area={head[1]}, but it is the note for {module.key}")
    elif head[3]:
        now = code_hash(repo, module)
        if head[3] != now:
            grade.stale = True
            problems.append(
                f"the code of {module.key} changed since the note was written at {head[2]} "
                f"(code={head[3]}, now {now}): read the area again"
            )
    elif repo.commit not in ("", UNKNOWN) and head[2] != repo.commit:
        grade.stale = True
        problems.append(f"written at {head[2]}; {repo.name} is now at {repo.commit}: read the area again")
    parts = sections(text)
    grade.questions = questions(parts.get("questions", []))
    grade.contradictions, unreadable = contradictions(parts.get("contradictions", []))
    problems += unreadable
    for item in grade.contradictions:
        problems += cites.check(item.text, repo, item.id)
    asked = {q.id: q for q in grade.questions}

    def refs(line: str, where: str) -> list[str]:
        missing = [r for r in _QREF.findall(line) if r not in asked]
        return [f"{where} names {r}, which is not under ## Questions" for r in missing]

    purpose = "\n".join(parts.get("purpose", [])).strip()
    if _words(purpose) < MIN_WORDS:
        problems.append(
            "## Purpose is empty: say what this area is for and who relies on it, in business words"
        )
    else:
        problems += cites.check(purpose, repo, "## Purpose")

    truth = facts(module)
    claimed: set[tuple[str, str]] = set()
    for line in parts.get("what it touches", []):
        if not line.startswith("- "):
            continue
        found = _CLAIM.match(line.strip())
        if not found or found[1] not in VERBS:
            problems.append(
                f"cannot read `{line.strip()[:70]}`: write `- <verb> <resource> - <what it is for> "
                f"[<file>:<line>]`, verb one of {', '.join(VERBS)}"
            )
            continue
        verb, resource, rest = found[1], found[2].strip().strip("`"), found[3]
        if (verb, resource) not in truth:
            problems.append(
                f"not in the code: {verb} {resource} (the extractors found no such edge in {module.key}); "
                "remove it, or ask the Tech Lead under ## Questions"
            )
            continue
        claimed.add((verb, resource))
        if _words(rest) < MIN_WORDS:
            problems.append(f"{verb} {resource}: say what it is for, not only that it happens")
        problems += cites.check(rest, repo, f"{verb} {resource}")
        problems += refs(rest, f"{verb} {resource}")
    for verb, resource in sorted(set(truth) - claimed):
        problems.append(f"missing: {verb} {resource} (at {truth[(verb, resource)]}): say what it is for")
    if parts.get("what it touches") is None and truth:
        problems.append("## What it touches is missing")

    own = [p for p in points if f"{p.get('repo')}/{p.get('module')}" == module.key]
    lines: dict[str, str] = {}
    for line in parts.get("rules", []):
        ids = _BP.findall(line)
        if line.startswith("- ") and ids:
            lines.setdefault(ids[0], line)
    for point in own:
        line = lines.pop(point["id"], None)
        where = f"{point['id']} `{point.get('predicate', '')}` ({point.get('file')}:{point.get('line')})"
        if line is None:
            problems.append(f"missing under ## Rules: {where}: say what it decides")
            continue
        if _words(_BP.sub(" ", line)) < MIN_WORDS:
            problems.append(f"{point['id']}: say what it decides, in business words")
        problems += refs(line, point["id"])
        if point.get("status") == "mapped" and point.get("rule"):
            if point["rule"] not in _RULE.findall(line):
                problems.append(
                    f"{point['id']} is decided by {point['rule']} (profile/branch-points.yaml); name it"
                )
            continue
        asking = [asked[r] for r in _QREF.findall(line) if r in asked]
        if not asking:
            problems.append(
                f"{point['id']} has no confirmed rule: ask the Product Owner which rule decides it, under "
                "## Questions, and name the question on this line"
            )
        for question in asking:
            question.blocking = True  # only a human confirms a rule
    for stray in sorted(lines):
        problems.append(f"{stray} is not a branch point of {module.key}")
    grade.settle()
    return grade


@dataclass
class Step:
    number: int
    area: str
    verb: str
    resource: str

    @property
    def external(self) -> bool:
        return self.area.startswith("external:")


@dataclass
class FlowGrade:
    name: str
    path: str
    steps: list[Step] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems

    def data(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "valid": self.valid,
            "areas": sorted({s.area for s in self.steps}),
            "problems": self.problems,
            "questions": [q.data(self.path) for q in self.questions],
        }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def uses(src: Module, dst: Module) -> bool:
    """Does code in `src` import code in `dst` (Java packages, or relative TypeScript imports)?"""
    packages = set()
    for path in dst.sources:
        if path.suffix == ".java":
            found = re.search(r"^\s*package\s+([\w.]+)\s*;", _read(path), re.M)
            if found:
                packages.add(found.group(1))
    folders = {p.parent.resolve() for p in dst.sources}
    for path in src.sources:
        text = _read(path)
        if path.suffix == ".java":
            for name in re.findall(r"^\s*import\s+(?:static\s+)?([\w.]+)", text, re.M):
                if any(name.startswith(pkg + ".") for pkg in packages):
                    return True
            continue
        for spec in re.findall(r"""from\s+['"](\.{1,2}/[^'"]+)['"]""", text):
            target = (path.parent / spec).resolve()
            if target in folders or target.parent in folders:
                return True
    return False


def grade_flow(
    central: Path,
    path: Path,
    areas: dict[str, tuple[Repo, Module]],
    systems: set[str],
    cites: Citations,
) -> FlowGrade:
    text = _read(path)
    title = re.search(r"^#\s+(.+)$", text, re.M)
    flow = FlowGrade(title.group(1).strip() if title else path.stem, path.relative_to(central).as_posix())
    parts = sections(text)
    flow.questions = questions(parts.get("questions", []))
    asked = {q.id for q in flow.questions}
    for line in parts.get("steps", []):
        if not re.match(r"^\d+\.", line.strip()):
            continue
        found = _STEP.match(line.strip())
        if not found:
            flow.problems.append(
                f"cannot read `{line.strip()[:70]}`: write `<n>. <area> <verb> <resource> - <what happens> "
                "[<file>:<line>]`"
            )
            continue
        step = Step(len(flow.steps) + 1, found[1], found[2], found[3].strip().strip("`"))
        rest = found[4]
        flow.steps.append(step)
        where = f"step {step.number}"
        flow.problems += [
            f"{where} names {r}, which is not under ## Questions"
            for r in _QREF.findall(rest)
            if r not in asked
        ]
        if step.external:
            name = step.area.split(":", 1)[1]
            if step.verb not in VERBS:
                flow.problems.append(f"{where}: {step.verb} is not one of {', '.join(VERBS)}")
            if name.lower() not in systems:
                flow.problems.append(f"{where}: {name} is not a system in {LANDSCAPE}")
            continue
        if step.area not in areas:
            flow.problems.append(f"{where}: there is no area {step.area}")
            continue
        repo, module = areas[step.area]
        if step.verb == "uses":
            if step.resource not in areas:
                flow.problems.append(f"{where}: {step.resource} is not an area")
            elif not uses(module, areas[step.resource][1]):
                flow.problems.append(f"{where}: no code in {step.area} imports code in {step.resource}")
        elif step.verb not in VERBS:
            flow.problems.append(f"{where}: {step.verb} is not one of uses, {', '.join(VERBS)}")
        elif (step.verb, step.resource) not in facts(module):
            flow.problems.append(f"{where}: {step.area} does not {step.verb} {step.resource} in the code")
        if _words(rest) < MIN_WORDS:
            flow.problems.append(f"{where}: say what happens, in business words")
        flow.problems += cites.check(rest, repo, where)
    if len(flow.steps) < 2:
        flow.problems.append("a flow needs at least two steps under ## Steps")
    for before, after in zip(flow.steps, flow.steps[1:], strict=False):
        joined = (
            before.area == after.area
            or before.resource == after.resource
            or (before.verb == "uses" and after.area == before.resource)
        )
        if not joined:
            flow.problems.append(
                f"steps {before.number} and {after.number} are not joined: they share neither an area nor a "
                "resource (add the step in between)"
            )
    return flow


def boundary(repos: list[Repo]) -> dict[str, str]:
    """The resources where the product meets another system, and why each one counts."""
    verbs: dict[str, set[str]] = {}
    unresolved: set[str] = set()
    for repo in repos:
        unresolved |= set(repo.unresolved)
        for module in repo.modules.values():
            for verb, resource in facts(module):
                verbs.setdefault(resource, set()).add(verb)
    out = {}
    for resource, found in sorted(verbs.items()):
        kind = resource.split(":", 1)[0]
        if resource in unresolved:
            out[resource] = "the extractors could not resolve it"
        elif kind == "endpoint" and "calls" in found and "exposes" not in found:
            out[resource] = "called here, served by another system"
        elif kind == "endpoint" and "exposes" in found and "calls" not in found:
            out[resource] = "served here: who calls it?"
        elif kind in ("topic", "queue") and "publishes" in found and "consumes" not in found:
            out[resource] = "published here, consumed elsewhere"
        elif kind in ("topic", "queue") and "consumes" in found and "publishes" not in found:
            out[resource] = "consumed here, published elsewhere"
        elif kind == "collection" and "reads" in found and "writes" not in found:
            out[resource] = "read here, written by another system"
        elif kind == "collection" and "writes" in found and "reads" not in found:
            out[resource] = "written here: who reads it?"
        elif kind == "file":
            out[resource] = "a file exchanged with another system"
    return out


@dataclass
class LandscapeGrade:
    path: str
    status: str = "unexplored"
    systems: set[str] = field(default_factory=set)
    problems: dict[str, list[str]] = field(default_factory=dict)  # resource ("" = the file) -> problems
    questions: list[Question] = field(default_factory=list)

    def all_problems(self) -> list[str]:
        return [p for items in self.problems.values() for p in items]

    def data(self) -> dict:
        return {
            "status": self.status,
            "path": self.path,
            "systems": sorted(self.systems),
            "problems": self.all_problems(),
            "questions": [q.data(self.path) for q in self.questions],
        }


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def grade_landscape(central: Path, repos: list[Repo], cites: Citations) -> LandscapeGrade:
    grade = LandscapeGrade(LANDSCAPE)
    edges = boundary(repos)
    path = central / LANDSCAPE
    if not path.is_file():
        grade.problems[""] = [f"no landscape yet: write {LANDSCAPE}"]
        for resource, why in edges.items():
            grade.problems[resource] = [f"{resource} ({why}) is not in the landscape"]
        return grade
    parts = sections(_read(path))
    grade.questions = questions(parts.get("questions", []))
    answered = {q.id for q in grade.questions if q.answer}
    asked = {q.id for q in grade.questions}
    known = {r for repo in repos for m in repo.modules.values() for _, r in facts(m)}
    rows: dict[str, list[str]] = {}
    for line in parts.get("systems", []):
        cells = _cells(line)
        if not line.strip().startswith("|") or len(cells) < 5 or set(cells[0]) <= {"-", " ", ":"}:
            continue
        if cells[0].lower() == "system":
            continue
        resource = cells[3].strip("`")
        rows[resource] = cells
        if cells[0] and cells[0] != "?":
            grade.systems.add(cells[0].lower())
    for resource, cells in rows.items():
        system, direction, _how, _res, evidence = cells[:5]
        issues = grade.problems.setdefault(resource, [])
        if resource not in known:
            issues.append(f"{resource} is not a resource the extractors found")
            continue
        if not system or system == "?":
            issues.append(f"{resource}: which system is on the other side? (ask under ## Questions)")
        if direction not in DIRECTIONS:
            issues.append(f"{resource}: direction must be one of {', '.join(DIRECTIONS)}")
        named = _QREF.findall(evidence)
        issues += [f"{resource} names {q}, which is not under ## Questions" for q in named if q not in asked]
        if named and all(q in answered for q in named):
            continue
        if named:
            issues.append(
                f"{resource}: waits for the answer to {', '.join(q for q in named if q not in answered)}"
            )
            continue
        issues += cites.check(evidence, None, resource)
    for resource, why in edges.items():
        if resource not in rows:
            grade.problems.setdefault(resource, []).append(f"{resource} ({why}) is not in the landscape")
    grade.problems = {k: v for k, v in grade.problems.items() if v}
    blocked = any(q.blocking and not q.answer for q in grade.questions)
    grade.status = "incomplete" if grade.problems else "blocked" if blocked else "understood"
    return grade


def grade_all(central: Path, repos: list[Repo], domain: dm.Domain, points: list[dict]) -> dict:
    cites = Citations(central, repos, domain)
    areas = areas_of(repos)
    grades = {key: grade_area(central, repo, module, points, cites) for key, (repo, module) in areas.items()}
    landscape = grade_landscape(central, repos, cites)
    folder = central / FLOWS
    flows = [
        grade_flow(central, path, areas, landscape.systems, cites)
        for path in (sorted(folder.glob("*.md")) if folder.is_dir() else [])
    ]
    covered = {(s.area, s.verb, s.resource) for f in flows if f.valid for s in f.steps}
    in_flows = {s.area for f in flows if f.valid for s in f.steps} | {
        s.resource for f in flows if f.valid for s in f.steps if s.verb == "uses"
    }
    for key, grade in grades.items():
        if grade.status == "unexplored" or grade.stale:
            continue
        truth = facts(areas[key][1])
        entries = sorted(item for item in truth if item[0] in ENTRY_VERBS)
        for verb, resource in entries:
            if (key, verb, resource) not in covered:
                grade.problems.append(
                    f"not in any flow: {verb} {resource}: follow it end to end in {FLOWS}/<flow>.md"
                )
        if truth and not entries and key not in in_flows:
            grade.problems.append(f"in no flow: show where {key} takes part, in {FLOWS}/<flow>.md")
        grade.settle()
    counts = {state: sum(1 for g in grades.values() if g.status == state) for state in STATES}
    open_questions = (
        [q.data(g.note) for g in grades.values() for q in g.questions if not q.answer]
        + [q.data(f.path) for f in flows for q in f.questions if not q.answer]
        + [q.data(landscape.path) for q in landscape.questions if not q.answer]
    )
    return {
        "understood": bool(grades)
        and counts["understood"] == len(grades)
        and landscape.status == "understood",
        "counts": counts,
        "areas": {key: grades[key].data() for key in sorted(grades)},
        "flows": [f.data() for f in flows],
        "landscape": landscape.data(),
        "landscapeByResource": landscape.problems,
        "boundary": boundary(repos),
        "openQuestions": open_questions,
        "openContradictions": [
            {**c.data(), "where": g.note} for g in grades.values() for c in g.contradictions if not c.resolved
        ],
    }


def summary(status: dict) -> dict:
    """What the context map shows: counts, the landscape state, open questions."""
    return {
        "understood": status["understood"],
        "counts": status["counts"],
        "landscape": status["landscape"]["status"],
        "flows": sum(1 for f in status["flows"] if f["valid"]),
        "openQuestions": sum(1 for q in status["openQuestions"] if q["blocking"]),
        "openContradictions": len(status.get("openContradictions", [])),
        "areas": {k: v["status"] for k, v in status["areas"].items()},
    }


def render(status: dict) -> str:
    counts = status["counts"]
    lines = [
        "# System understanding",
        "",
        f"Generated by baton context understand from the notes under {FOLDER}/; do not edit.",
        "",
        "| State | Areas |",
        "| --- | --- |",
        *[f"| {state} | {counts[state]} |" for state in STATES],
        "",
        f"Landscape: {status['landscape']['status']}. Valid flows: "
        f"{sum(1 for f in status['flows'] if f['valid'])} of {len(status['flows'])}.",
        "",
        "## Areas",
        "",
    ]
    for key, area in status["areas"].items():
        lines += [f"### {key}: {area['status']}", ""]
        lines += [f"- {p}" for p in area["problems"]]
        waiting = [q["id"] for q in area["questions"] if q["blocking"] and not q["answer"]]
        if waiting:
            lines.append(f"- waits for a human to answer {', '.join(waiting)}")
        clashes = [c["id"] for c in area.get("contradictions", []) if not c["resolved"]]
        if clashes:
            lines.append(f"- waits for the Tech Lead to resolve {', '.join(clashes)}")
        if not area["problems"] and not waiting and not clashes:
            lines.append("- no problem found")
        lines.append("")
    lines += ["## Flows", ""]
    for flow in status["flows"]:
        lines.append(f"- {flow['name']} ({flow['path']}): {'valid' if flow['valid'] else 'not valid'}")
        lines += [f"  - {p}" for p in flow["problems"]]
    if not status["flows"]:
        lines.append(f"- none yet ({FLOWS}/<flow>.md)")
    lines += ["", "## Landscape", ""]
    lines += [f"- {p}" for p in status["landscape"]["problems"]] or ["- no problem found"]
    lines += ["", "## Open questions", ""]
    lines += [
        f"- {q['id']} ({'blocking' if q['blocking'] else 'open'}, {q['ask']}) in {q['where']}: {q['text']}"
        for q in status["openQuestions"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"


def _key(item: dict) -> str:
    return f"{item['where']}#{item['id']}"


def date_asked(central: Path, status: dict, today: str) -> None:
    """Stamp each open question and contradiction with the day a run first saw it (kept in asked.json), so
    an old one can be escalated; answered ones drop out."""
    path = central / ASKED_JSON
    try:
        seen = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        seen = {}
    now: dict[str, str] = {}
    for item in status["openQuestions"] + status.get("openContradictions", []):
        item["asked"] = now[_key(item)] = seen.get(_key(item), today)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def write(central: Path, status: dict, today: str | None = None) -> list[str]:
    folder = central / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    date_asked(central, status, today or date.today().isoformat())
    (central / STATUS_JSON).write_text(json.dumps(status, indent=1) + "\n", encoding="utf-8")
    (central / STATUS_MD).write_text(render(status), encoding="utf-8")
    return [STATUS_JSON, STATUS_MD, ASKED_JSON]


# --- briefs: what an explorer or the integrator is given to read ---------------------------------------


def brief_area(
    central: Path, repos: list[Repo], domain: dm.Domain, points: list[dict], key: str, status: dict
) -> dict:
    from baton.context import docs
    from baton.context import score as sc

    areas = areas_of(repos)
    if key not in areas:
        raise ValueError(f"no area {key}; areas: {', '.join(sorted(areas)) or '(none)'}")
    repo, module = areas[key]
    truth = facts(module)
    neighbours: dict[str, list[str]] = {}
    mine = {r for _, r in truth}
    for other, (_, mod) in areas.items():
        if other != key:
            for verb, resource in facts(mod):
                if resource in mine:
                    neighbours.setdefault(other, []).append(f"{verb} {resource}")
    edges = boundary(repos)
    return {
        "area": key,
        "repo": repo.name,
        "repoPath": str(repo.path),
        "commit": repo.commit,
        "note": f"{AREAS}/{note_name(key)}",
        "header": header(repo, module),
        "sources": [p.relative_to(repo.path).as_posix() for p in sorted(module.sources)],
        "tests": [p.relative_to(repo.path).as_posix() for p in sorted(module.tests)],
        "touches": [
            {"verb": v, "resource": r, "at": at, "boundary": edges.get(r, "")}
            for (v, r), at in sorted(truth.items())
        ],
        "branchPoints": [
            {
                "id": p["id"],
                "at": f"{p.get('file')}:{p.get('line')}",
                "predicate": p.get("predicate", ""),
                "status": p.get("status", ""),
                "rule": p.get("rule") or "",
                "proposed": p.get("proposed") or "",
            }
            for p in points
            if f"{p.get('repo')}/{p.get('module')}" == key
        ],
        "neighbours": neighbours,
        "wiki": {
            "page": f"docs/wiki/{repo.name}/{module.name}.md",
            "state": sc.wiki_state(central, repo, module.name),
        },
        "documents": [d["file"] for d in docs.mentions(central, repos, domain) if key in d["modules"]],
        "architecture": [
            p
            for p in ("docs/architecture/diagrams/diagrams.md", "docs/architecture/workspace.dsl")
            if (central / p).is_file()
        ],
        "now": status["areas"].get(key, {}),
    }


def brief_system(repos: list[Repo], status: dict) -> dict:
    areas = areas_of(repos)
    shared: dict[str, list[str]] = {}
    for key, (_, module) in areas.items():
        for verb, resource in facts(module):
            shared.setdefault(resource, []).append(f"{key} {verb}")
    return {
        "areas": {
            key: {
                "status": status["areas"].get(key, {}).get("status", "unexplored"),
                "note": f"{AREAS}/{note_name(key)}",
                "entries": [f"{v} {r}" for (v, r) in sorted(facts(m)) if v in ENTRY_VERBS],
            }
            for key, (_, m) in sorted(areas.items())
        },
        "shared": {r: who for r, who in sorted(shared.items()) if len({w.split(" ")[0] for w in who}) > 1},
        "boundary": status["boundary"],
        "flows": status["flows"],
        "landscape": status["landscape"],
        "flowsFolder": FLOWS,
        "landscapeFile": LANDSCAPE,
    }


def brief_text(brief: dict) -> str:
    """The area brief as text an agent reads."""
    if "area" not in brief:
        return json.dumps(brief, indent=1)
    lines = [
        f"Area {brief['area']} in {brief['repo']} ({brief['repoPath']}) at {brief['commit']}.",
        f"Write {brief['note']}; its first line: {brief['header']}",
        "",
        "Must explain, under ## What it touches (verb resource - what it is for [file:line]):",
    ]
    lines += [
        f"- {t['verb']} {t['resource']} (at {t['at']})"
        + (f"; crosses to another system: {t['boundary']}" if t["boundary"] else "")
        for t in brief["touches"]
    ] or ["- nothing: the extractors found no collection, topic, endpoint or file here"]
    lines += ["", "Must explain, under ## Rules (bp-id - what it decides - R<n> or Q<n>):"]
    lines += [
        f"- {p['id']} `{p['predicate']}` at {p['at']}: "
        + (
            f"decided by {p['rule']}"
            if p["rule"]
            else f"no confirmed rule{'; proposed ' + p['proposed'] if p['proposed'] else ''}: ask the PO"
        )
        for p in brief["branchPoints"]
    ] or ["- no business branch point"]
    lines += ["", "Read: " + ", ".join(brief["sources"][:40]) + (" …" if len(brief["sources"]) > 40 else "")]
    lines.append("Tests: " + (", ".join(brief["tests"][:20]) or "none"))
    lines.append(f"Wiki page: {brief['wiki']['page']} ({brief['wiki']['state']}; use it only if verified)")
    lines.append("Documents: " + (", ".join(brief["documents"]) or "none ingested"))
    lines.append("Architecture: " + (", ".join(brief["architecture"]) or "none generated"))
    lines += [f"Shares {', '.join(v)} with {k}" for k, v in sorted(brief["neighbours"].items())]
    now = brief["now"]
    if now:
        lines += ["", f"Now: {now.get('status')}"]
        lines += [f"- fix: {p}" for p in now.get("problems", [])]
        lines += [
            f"- {q['id']} ({'blocking' if q['blocking'] else 'open'}): {q['text']}"
            + (f" -> answered: {q['answer']}" if q["answer"] else "")
            for q in now.get("questions", [])
        ]
    return "\n".join(lines) + "\n"


# --- gate 0: is an area understood well enough for this track? ------------------------------------------


def accepts(area: dict, track: str, light_open: int) -> str | None:
    """None when the area is good enough for work on this track, else why not. Full: understood. Light:
    also an area blocked only by at most `light_open` open questions (never by a contradiction). A spike
    investigates, so nothing stops it."""
    status = area.get("status", "unexplored")
    if status == "understood" or track == "spike":
        return None
    waiting = [q for q in area.get("questions", []) if q["blocking"] and not q["answer"]]
    clashes = [c for c in area.get("contradictions", []) if not c["resolved"]]
    if status == "blocked":
        if track == "light" and not clashes and len(waiting) <= light_open:
            return None
        parts = []
        if waiting:
            parts.append(f"{len(waiting)} question{'s' if len(waiting) != 1 else ''} for a human")
        if clashes:
            parts.append(f"{len(clashes)} contradiction{'s' if len(clashes) != 1 else ''} for the Tech Lead")
        return f"blocked: {', '.join(parts)}"
    problems = area.get("problems") or []
    return f"{status}: {problems[0]}" if problems else status


# --- humans answer outside a session -------------------------------------------------------------------


def note_of(central: Path, ref: str) -> Path:
    """An area key (repo/module), `landscape`, `flow:<name>`, or a path under docs/context/understanding/."""
    if ref == "landscape":
        return central / LANDSCAPE
    if ref.startswith("flow:"):
        return central / FLOWS / f"{ref[5:]}.md"
    if ref.startswith(FOLDER + "/"):
        return central / ref
    return central / AREAS / note_name(ref)


def record(central: Path, ref: str, item: str, words: str, role: str, today: str) -> str:
    """Write a human's answer to Q<n>, or resolution of C<n>, under it, verbatim; returns the note's path."""
    path = note_of(central, ref)
    if not path.is_file():
        raise FileNotFoundError(f"no note {path.relative_to(central).as_posix()}")
    words = " ".join(words.split())
    if not words:
        raise ValueError("the answer is empty")
    lines = path.read_text(encoding="utf-8").splitlines()
    if re.fullmatch(r"Q\d+", item):
        head, word, section = re.compile(rf"^-\s+{item}\s+\("), "answer", "questions"
    elif re.fullmatch(r"C\d+", item):
        head, word, section = re.compile(rf"^-\s+{item}\s*:"), "resolved", "contradictions"
    else:
        raise ValueError(f"{item} is neither a question (Q<n>) nor a contradiction (C<n>)")
    current = None
    for n, line in enumerate(lines):
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1).strip().lower()
            continue
        if current == section and head.match(line.strip()):
            after = lines[n + 1] if n + 1 < len(lines) else ""
            if re.match(rf"^\s+{word}:", after):
                raise ValueError(f"{item} in {path.name} already has an {word}: {after.strip()}")
            lines.insert(n + 1, f"  {word}: {words} ({role}, {today})")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return path.relative_to(central).as_posix()
    raise ValueError(f"no {item} under ## {section.capitalize()} in {path.relative_to(central).as_posix()}")


def questions_page(status: dict, ttl_days: int, today: str) -> str:
    """Today's questions, by the person who can answer them, oldest first; past `ttl_days` they go to the
    Tech Lead as well."""
    now = date.fromisoformat(today)
    items = [{**q, "kind": "question"} for q in status["openQuestions"]] + [
        {**c, "kind": "contradiction", "ask": "TL", "blocking": True}
        for c in status.get("openContradictions", [])
    ]

    names = {area["note"]: key for key, area in status["areas"].items()}
    names[LANDSCAPE] = "landscape"
    names.update({f["path"]: "flow:" + Path(f["path"]).stem for f in status["flows"]})

    def age(item: dict) -> int:
        return (now - date.fromisoformat(item.get("asked", today))).days

    lines = [
        "# Questions from the context map",
        "",
        f"Generated by baton context questions on {today}; do not edit. Answer with "
        '`baton context answer <area or landscape or flow:name> Q<n> "<words>" --by PO|TL`, or '
        '`baton context answer <area> C<n> "<how it is resolved>" --by TL`.',
        "",
    ]
    for role, title in (("PO", "Product Owner"), ("TL", "Tech Lead")):
        mine = sorted(
            (i for i in items if i["ask"] == role), key=lambda i: (not i["blocking"], -age(i), i["where"])
        )
        lines += [f"## {title}", ""]
        for item in mine:
            state = "blocking" if item["blocking"] else "open"
            late = " OVERDUE: escalate to the Tech Lead" if age(item) > ttl_days else ""
            lines.append(
                f"- {names.get(item['where'], item['where'])} {item['id']} ({state}, asked "
                f"{item.get('asked', today)}, {age(item)} days){late}: {item['text']}"
            )
        if not mine:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines)
