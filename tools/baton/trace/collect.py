"""Read a feature's artefacts into the trace.json object (contracts/trace.md section 4). Stdlib only.

Every parser is tolerant: a missing or unreadable artefact becomes null or "not_produced", never an
error. The collector quotes the artefacts; it does not summarise them.
"""

from __future__ import annotations

import base64
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from baton.confidence import (
    ac_table,
    header_value,
    project_value,
    read_json,
    sensor_status,
    triage_counts,
)
from baton.graph.stamps import tagged
from baton.state_check import Story, branch_stories, normalize_state, section, track_of

NODES = (
    "feature", "stories", "gate1", "design", "designLenses", "gate2",
    "build", "sensors", "qa", "confidence", "gate3", "docs", "merged",
)
FOOTER_KEYS = (
    "agent", "skills", "profile", "context", "graph", "model", "commit", "started", "finished", "tokens",
)
LIST_KEYS = {"skills", "profile", "context"}
MAIN_ORDER = (
    "Draft", "Ready for PO", "Ready", "Designed", "Design Approved",
    "In Review", "QA Fail", "QA Pass", "Approved", "Documented", "Done",
)
TECH_WORDS = re.compile(
    r"\b(mongo\w*|kafka|spring|java|react|endpoint|api|sql|json|rest|microservice|database|collection)\b",
    re.I,
)
# the second and third names in the group: before the renames
_FOOTER = re.compile(r"<!--\s*(?:baton|pod|harness):provenance\b(.*?)-->", re.S)
_KEY = re.compile(r"(?:^|(?<=\s))([A-Za-z][\w-]*):(?=\s|$)")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)Z?)?")
_PR = re.compile(r"^PR:[ \t]*(\S+)", re.M)


# ---------- small helpers ----------

def _read(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def when(value: str | None) -> datetime | None:
    """A date or ISO timestamp anywhere in the text, as an aware UTC datetime."""
    match = _DATE.search(value or "")
    if not match:
        return None
    stamp = match.group(1) + "T" + (match.group(2) or "00:00")
    if len(stamp) == 16:
        stamp += ":00"
    try:
        return datetime.fromisoformat(stamp).replace(tzinfo=UTC)
    except ValueError:
        return None


def _iso(moment: datetime | None) -> str | None:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def _split(value: str) -> list[str]:
    """Comma-separated, but not inside parentheses: `domain.md#rules(R3,R7), project.md#repos`."""
    parts, depth, current = [], 0, ""
    for char in value:
        depth += char == "("
        depth -= char == ")"
        if char == "," and depth <= 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    parts.append(current.strip())
    return [p for p in parts if p and p.lower() not in ("none", "-")]


def heading_section(text: str | None, name: str) -> str | None:
    """`## <name>` with or without a section number (`## 4a. Pattern ledger`)."""
    if not text:
        return None
    match = re.search(rf"^##[ \t]+(?:\d+[a-z]?\.[ \t]*)?{re.escape(name)}\b[^\n]*\n?", text, re.M | re.I)
    if not match:
        return None
    rest = text[match.end():]
    following = re.search(r"^##[ \t]", rest, re.M)
    return (rest[: following.start()] if following else rest).strip()


def _strip_footer(text: str) -> str:
    return _FOOTER.sub("", text)


def bullets(body: str | None) -> list[str]:
    return [
        re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip()
        for line in _strip_footer(body or "").splitlines()
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line)
    ]


def table(body: str | None) -> list[dict[str, str]]:
    """The first Markdown table in body, as rows keyed by the lower-cased header."""
    rows, header = [], None
    for line in (body or "").splitlines():
        if not line.lstrip().startswith("|"):
            if header is not None:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            header = [cell.casefold() for cell in cells]
        elif not all(set(cell) <= set("-: ") for cell in cells):
            rows.append(dict(zip(header, cells, strict=False)))
    return rows


def _first_paragraph(body: str | None) -> str | None:
    for block in re.split(r"\n\s*\n", _strip_footer(body or "").strip()):
        block = block.strip()
        if block and not block.startswith(("#", "|", "<!--")):
            return " ".join(line.strip() for line in block.splitlines())
    return None


# ---------- provenance footer (contracts/trace.md section 2) ----------

def provenance_blocks(text: str | None) -> list[dict]:
    blocks = []
    for match in _FOOTER.finditer(text or ""):
        block: dict = {}
        more: dict = {}
        for line in match.group(1).splitlines():
            line = line.strip()
            keys = [m for m in _KEY.finditer(line) if m.start() == 0 or m.group(1) in FOOTER_KEYS]
            for index, key in enumerate(keys):
                end = keys[index + 1].start() if index + 1 < len(keys) else len(line)
                name, value = key.group(1), line[key.end(): end].strip()
                if name in LIST_KEYS:
                    block[name] = _split(value)
                elif name == "tokens":
                    digits = re.sub(r"[^\d]", "", value)
                    block[name] = int(digits) if digits else None
                elif name in FOOTER_KEYS:
                    block[name] = value or None
                else:
                    more[name] = value
        if more:
            block["more"] = more
        if block:
            blocks.append(block)
    return blocks


def provenance(text: str | None, agent: str | None = None) -> dict | None:
    """The footer the named agent left in the file (the last one when several); else the last footer."""
    blocks = provenance_blocks(text)
    if not blocks:
        return None
    if agent:
        own = [b for b in blocks if (b.get("agent") or "").lower() == agent]
        if own:
            return own[-1]
    return blocks[-1]


def _minutes(prov: dict | None) -> float | None:
    if not prov:
        return None
    start, end = when(prov.get("started")), when(prov.get("finished"))
    if start and end and end >= start:
        return round((end - start).total_seconds() / 60, 1)
    return None


# ---------- a story, live or archived ----------

KINDS = ("stories", "design", "qa", "changes")


@dataclass
class TraceStory(Story):
    """A story whose artefacts sit under docs/<kind>/<F>/, or under docs/archive/<F>/<kind>/ once the
    feature is archived (contracts/versioning.md section 5)."""

    archived: bool = False

    def folder(self, kind: str) -> Path:
        if self.archived:
            return self.central / "docs" / "archive" / self.feature / kind
        return self.central / "docs" / kind / self.feature

    def qa(self, suffix: str) -> Path:
        return self.folder("qa") / f"{self.story_id}-{suffix}"

    def design(self, suffix: str = "design.md") -> Path:
        return self.folder("design") / f"{self.story_id}-{suffix}"

    def change_note(self) -> Path:
        return self.folder("changes") / f"{self.story_id}-change-note.md"


# ---------- the node shape ----------

def node(state: str, path: str | None, who: dict | None, metric: str | None = None,
         prov: dict | None = None, at: datetime | None = None, data: dict | None = None) -> dict:
    return {
        "state": state,
        "path": path,
        "who": who,
        "metric": metric,
        "provenance": prov,
        "at": _iso(at or (when(prov.get("finished")) if prov else None)),
        "minutes": _minutes(prov),
        "data": data or {},
    }


def _agent(name: str) -> dict:
    return {"kind": "agent", "name": name}


def _human(name: str) -> dict:
    return {"kind": "human", "name": name}


def _tool(name: str) -> dict:
    return {"kind": "tool", "name": name}


def _missing(who: dict | None = None) -> dict:
    return node("not_produced", None, who)


# ---------- the collector ----------

class Collector:
    def __init__(self, central: Path, feature_id: str):
        self.central = Path(central).resolve()
        self.feature_id = feature_id
        self.feature_path = self._feature_file()
        live = sorted((self.central / "docs" / "stories" / feature_id).glob("*.md"))
        archived = sorted((self.central / "docs" / "archive" / feature_id / "stories").glob("*.md"))
        names = {p.name for p in live}
        self.story_paths = live + [p for p in archived if p.name not in names]
        self.branch_roots: dict[Path, str] = {}  # a temporary copy of a story branch's docs -> the branch
        ids = (re.match(r"([A-Za-z]+-\d+)", p.stem) for p in self.story_paths)
        here = {m.group(1) for m in ids if m}
        for story in branch_stories(self.central):
            if story.feature == feature_id and story.story_id not in here:
                root = self._copy_branch(story.ref, story.story_id)
                if root:
                    self.story_paths.append(root / story.rel(story.path))
        self.status_loops = self._status_loops()

    def _copy_branch(self, ref: str, story_id: str) -> Path | None:
        """The story's files from its story/ branch, copied to a temporary root (removed after collect)."""
        kinds = [f"docs/{kind}/{self.feature_id}" for kind in KINDS]
        listing = _git_out(self.central, "ls-tree", "-r", "--name-only", ref, "--", *kinds)
        if listing is None:
            return None
        root = Path(tempfile.mkdtemp(prefix="trace-"))
        for name in listing.decode().split("\n"):
            leaf = name.rsplit("/", 1)[-1]
            if not name or not (leaf.startswith(story_id + "-") or leaf.startswith(story_id + ".")
                                or f"/{story_id}-" in name):
                continue
            body = _git_out(self.central, "show", f"{ref}:{name}")
            if body is not None:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
        self.branch_roots[root] = ref
        return root

    def root_of(self, path: Path) -> tuple[Path, str | None]:
        for root, ref in self.branch_roots.items():
            if path.is_relative_to(root):
                return root, ref
        return self.central, None

    def rel(self, path: Path | None) -> str | None:
        if path is None:
            return None
        for root in (self.central, *self.branch_roots):
            if path.is_relative_to(root):
                return path.relative_to(root).as_posix()
        return path.as_posix()

    def _feature_file(self) -> Path | None:
        folder = self.central / "docs" / "features"
        found = sorted(folder.glob(f"{self.feature_id}.md")) + sorted(folder.glob(f"{self.feature_id}-*.md"))
        return found[0] if found else None

    def exists(self) -> bool:
        return self.feature_path is not None or bool(self.story_paths)

    def _status_loops(self) -> dict[str, int]:
        rows = table(_read(self.central / "docs" / "status.md"))
        loops = {}
        for row in rows:
            value = re.sub(r"[^\d]", "", row.get("loops", ""))
            if row.get("story") and value:
                loops[row["story"].strip()] = int(value)
        return loops

    # ----- people -----

    def people(self, feature_owner: str | None) -> dict:
        def value(key: str) -> str | None:
            found = project_value(self.central, key)
            return found if found and not found.startswith(("<", "(")) else None

        return {
            "po": value("people.po") or feature_owner,
            "techLead": value("people.tech-lead"),
            "seniorEngineer": value("people.senior-engineer"),
        }

    # ----- feature -----

    def feature(self) -> tuple[dict, dict]:
        text = _read(self.feature_path)
        if text is None:
            return {"id": self.feature_id, "title": None, "state": None, "author": None, "date": None,
                    "summary": None, "scope": []}, _missing(_human("PO"))
        title = re.search(rf"^#\s+(?:{re.escape(self.feature_id)}\s+)?(.+)$", text, re.M)
        owner = header_value(text, "Owner") or header_value(text, "Author")
        prov = provenance(text)
        date = when(header_value(text, "Date") or header_value(text, "Created")) or (
            when(prov.get("started")) if prov else None
        )
        summary = _first_paragraph(heading_section(text, "Outcome")) or _first_paragraph(
            heading_section(text, "Problem")
        )
        scope = bullets(heading_section(text, "Scope for this release")) or bullets(
            heading_section(text, "What the user can do")
        )
        business = " ".join(
            heading_section(text, name) or "" for name in ("Problem", "Outcome", "What the user can do")
        )
        info = {
            "id": self.feature_id,
            "title": title.group(1).strip() if title else None,
            "state": None,
            "author": owner,
            "date": _iso(date),
            "summary": summary,
            "scope": scope,
        }
        data = {
            "summary": summary,
            "scope": scope,
            "problem": _first_paragraph(heading_section(text, "Problem")),
            "noTechWords": not TECH_WORDS.search(business),
        }
        who = _human(f"PO {owner}" if owner else "PO")
        return info, node("done", self.rel(self.feature_path), who, "feature note", prov, date, data)

    # ----- one story -----

    def story(self, path: Path, feature_node: dict, rows: list[dict]) -> dict:
        match = re.match(r"([A-Za-z]+-\d+)", path.stem)
        root, ref = self.root_of(path)
        story = TraceStory(
            root, self.feature_id, match.group(1) if match else path.stem, path,
            archived="archive" in path.relative_to(root).parts,
        )
        text = _read(path) or ""
        state = normalize_state(header_value(text, "State") or "") or (header_value(text, "State") or "")
        title = re.search(r"^#\s+(?:[A-Za-z]+-\d+\s+)?(.+)$", text, re.M)
        readiness = section(text, "Readiness")
        score = re.search(r"Score:\s*(\d+\s*/\s*\d+|[\d.]+%?)", readiness or "")
        nodes = {"feature": feature_node}
        nodes["stories"] = self._stories_node(story, text, rows)
        nodes["gate1"] = self._gate1(story, text, state, readiness)
        nodes["design"] = self._design(story, text)
        nodes["designLenses"] = self._design_lenses(story)
        nodes["gate2"] = self._gate2(text)
        nodes["build"] = self._build(story, text)
        nodes["sensors"] = self._sensors(story)
        qa = self._qa(story)
        nodes["qa"] = qa
        nodes["confidence"] = self._confidence(story)
        nodes["gate3"] = self._gate3(story, state, nodes["confidence"])
        nodes["docs"] = self._docs(story, text)
        nodes["merged"] = self._merged(text, state)
        loops = self.status_loops.get(story.story_id, 0)
        if qa["state"] == "failed" or state == "QA Fail":
            loops = max(loops, 1)
        acs = self._acs(text, qa)
        return {
            "id": story.story_id,
            "title": title.group(1).strip() if title else story.story_id,
            "path": self.rel(path),
            "jiraType": header_value(text, "Jira-Type"),
            "labels": _split(header_value(text, "Labels") or ""),
            "track": track_of(text),
            "estimate": (header_value(text, "Estimate") or None),
            "state": state or None,
            "readiness": score.group(1).replace(" ", "") if score else None,
            "loops": loops,
            "branch": ref,
            "acs": acs,
            "clarifications": clarifications(text),
            "openQuestions": bullets(section(text, "Open questions")),
            "nodes": nodes,
            "timeline": timeline(nodes),
        }

    def _stories_node(self, story: Story, text: str, rows: list[dict]) -> dict:
        prov = provenance(text, "story-drafter")
        human = (header_value(text, "Author") or "").lower().startswith("human")
        who = _human("human author") if human else _agent("story-drafter")
        state = "done" if section(text, "Readiness") is not None else "in_progress"
        return node(state, self.rel(story.path), who, f"{len(rows)} stories", prov, None, {"stories": rows})

    def _gate1(self, story: Story, text: str, state: str, readiness: str | None) -> dict:
        design = story.design().is_file() or story.design("findings.md").is_file()
        passed = design or (state in MAIN_ORDER and MAIN_ORDER.index(state) >= MAIN_ORDER.index("Ready"))
        at = when(readiness)
        if not passed:
            waiting = state in ("Ready for PO", "Needs Clarification")
            state_word = "in_progress" if waiting else "not_produced"
            return node(state_word, None, _human("PO"), state or None, None, at)
        data = {"decision": "Ready", "by": "PO", "readiness": readiness and readiness.strip()}
        return node("done", self.rel(story.path), _human("PO"), "Ready", None, at, data)

    def _design(self, story: Story, text: str) -> dict:
        path = story.design()
        if not path.is_file():
            path = story.design("findings.md")
        note = _read(path)
        if note is None:
            return _missing(_agent("architect"))
        challenge = heading_section(note, "Challenge round") or ""
        labels = {}
        for label in ("Strawman", "Where the strawman fails", "Chosen design", "Domain fit", "Rules touched"):
            match = re.search(rf"\*\*{label}:?\*\*:?\s*(.*?)(?=\n\s*\*\*[A-Z]|\Z)", challenge, re.S)
            if match:
                labels[label] = match.group(1).strip()
        rules = labels.get("Rules touched")
        if rules is None:
            match = re.search(r"^Rules touched:\s*(.*)$", note, re.M)
            rules = match.group(1).strip() if match else None
        confidence_body = heading_section(note, "Confidence") or ""
        score = re.search(r"Score:\s*(\d+)\s*%", confidence_body)
        why = re.search(r"Why:\s*(.*?)(?=Reviewer should check:|\Z)", confidence_body, re.S)
        check = re.search(r"Reviewer should check:\s*(.*)", confidence_body, re.S)
        diagrams = story.design("diagrams")
        touch, _ = read_json(diagrams / "diagrams.json")
        points = (touch or {}).get("touchPoints") or []
        delta = Counter(str(point.get("status")) for point in points if point.get("status"))
        added = [
            str(point.get("element"))
            for point in (touch or {}).get("touchPoints") or []
            if point.get("status") in ("new", "removed")
        ]
        flow = diagrams / "flow.svg"
        candidate = story.folder("design") / f"{story.story_id}.dsl"
        revision = re.search(r"Revision:\s*(\d+)", note)
        data = {
            "track": track_of(note) or track_of(text),
            "revision": int(revision.group(1)) if revision else None,
            "challenge": {
                "strawman": labels.get("Strawman"),
                "failures": labels.get("Where the strawman fails"),
                "chosen": labels.get("Chosen design"),
            },
            "change": _first_paragraph(heading_section(note, "Change")) or _first_paragraph(
                heading_section(note, "Approach")
            ),
            "rulesTouched": rules,
            "flowSvg": _svg_data_uri(flow),
            "diagrams": self.rel(diagrams / "diagrams.md") if (diagrams / "diagrams.md").is_file() else None,
            "c4Delta": {
                "new": delta.get("new", 0),
                "changed": delta.get("changed", 0),
                "removed": delta.get("removed", 0),
                "added": added,
                "candidate": self.rel(candidate) if candidate.is_file() else None,
            } if touch else None,
            "ledger": table(heading_section(note, "Pattern ledger")),
            "files": bullets(
                heading_section(note, "Repos and files") or heading_section(note, "Files and tasks")
            ),
            "confidence": int(score.group(1)) if score else None,
            "why": (bullets(why.group(1)) or [why.group(1).strip()]) if why and why.group(1).strip() else [],
            "reviewerCheck": (bullets(check.group(1)) or (
                [check.group(1).strip()] if check.group(1).strip() else []
            )) if check else [],
        }
        metric = f"confidence {data['confidence']}%" if data["confidence"] is not None else "design note"
        prov = provenance(note, "architect")
        return node("done", self.rel(path), _agent("architect"), metric, prov, None, data)

    def _design_lenses(self, story: Story) -> dict:
        folder = story.design("reviews")
        files = sorted(folder.glob("review-*.md")) if folder.is_dir() else []
        if not files:
            return _missing(_agent("design-review-lenses"))
        lenses = []
        for path in files:
            body = _read(path) or ""
            verdict = re.search(r"verdict\W+(clear|findings|blocking)", body, re.I) or re.search(
                r"\b(clear|blocking|findings)\b", body, re.I
            )
            blocking = re.search(r"blocking\W+(\d+)", body, re.I)
            lenses.append({
                "name": path.stem.removeprefix("review-"),
                "verdict": verdict.group(1).lower() if verdict else None,
                "blocking": int(blocking.group(1)) if blocking else None,
                "summary": _first_paragraph(re.sub(r"^.*verdict.*$", "", body, flags=re.M | re.I)),
                "path": self.rel(path),
            })
        blocked = sum(1 for lens in lenses if lens["verdict"] == "blocking")
        metric = f"{len(lenses)} lenses, {blocked} blocking"
        prov = provenance(_read(files[0]))
        return node("done", self.rel(folder), _agent("design-review-lenses"), metric, prov, None,
                    {"lenses": lenses, "freshContext": True})

    def _gate2(self, text: str) -> dict:
        body = section(text, "Design review")
        if body is None:
            return _missing(_human("Tech Lead"))
        decisions = []
        for line in _strip_footer(body).splitlines():
            low = line.lower()
            decision = (
                "Auto-passed" if "auto-pass" in low
                else "Blocked" if re.search(r"\bblock", low)
                else "Changes requested" if "change" in low
                else "Approved" if "approve" in low
                else None
            )
            if decision:
                decisions.append((decision, when(line), line.strip()))
        if not decisions:
            data = {"text": body.strip()}
            return node("in_progress", None, _human("Tech Lead"), "waiting", None, None, data)
        decision, at, _ = decisions[-1]
        state = {"Approved": "done", "Auto-passed": "done", "Blocked": "failed"}.get(decision, "in_progress")
        who = _tool("auto-pass") if decision == "Auto-passed" else _human("Tech Lead")
        data = {"decision": decision, "rounds": len(decisions), "text": _strip_footer(body).strip()}
        return node(state, None, who, f"{decision} · round {len(decisions)}", None, at, data)

    def _build(self, story: Story, text: str) -> dict:
        diff, _ = read_json(story.qa("diff-shape.json"))
        summary = section(text, "Dev summary")
        if diff is None and summary is None:
            return _missing(_agent("developer"))
        repos = []
        for repo in (diff or {}).get("repos") or []:
            name = str(repo.get("repo", ""))
            branch = repo.get("branch") or f"feature/{story.feature}-{story.story_id}"
            repos.append({
                "repo": name,
                "branch": branch,
                "commits": repo.get("commits"),
                "commitList": _git_commits(self.central.parent / name, branch),
                "linesAdded": repo.get("linesAdded"),
                "linesDeleted": repo.get("linesDeleted"),
                "files": [str(f) for f in repo.get("files") or []],
            })
        added = sum(int(r.get("linesAdded") or 0) for r in repos)
        deleted = sum(int(r.get("linesDeleted") or 0) for r in repos)
        estimate = (header_value(text, "Estimate") or "").strip().upper()[:1] or None
        limit = project_value(self.central, f"estimate.lines.{estimate}") if estimate else None
        shape_md = _read(story.qa("diff-shape.md"))
        data = {
            "repos": repos,
            "linesAdded": added,
            "linesDeleted": deleted,
            "estimate": estimate,
            "estimateLines": int(limit) if limit and limit.isdigit() else None,
            "newDependencies": (diff or {}).get("newDependencies") or [],
            "breakingContract": (diff or {}).get("breakingContract") or [],
            "yagniCount": (diff or {}).get("yagniCount"),
            "sensorLoops": (diff or {}).get("sensorLoops"),
            "flags": [line for line in bullets(shape_md) if "flag" in line.lower()],
            "devSummary": _strip_footer(summary or "").strip() or None,
        }
        files = sum(len(r["files"]) for r in repos)
        plural = "s" if files != 1 else ""
        metric = f"+{added} / -{deleted} lines, {files} file{plural}" if diff else "dev summary"
        path = story.qa("diff-shape.json") if diff else story.path
        prov = provenance(text, "developer")
        return node("done" if diff else "in_progress", self.rel(path), _agent("developer"), metric, prov,
                    None, data)

    def _sensors(self, story: Story) -> dict:
        folder = story.qa("sensors")
        mutation = _mutation(story)
        if not folder.is_dir():
            return _missing(_tool("sensors"))
        status = sensor_status(folder)
        names = {
            "archunit": "archunit.txt",
            "pmd": "pmd.xml",
            "checkstyle": "checkstyle.xml",
            "eslint": "eslint.json",
        }
        tools = [
            {"tool": tool, "result": result, "detail": why, "path": self.rel(folder / names[tool]),
             "mandatory": tool == "archunit"}
            for tool, (result, why) in status.items()
        ]
        arch = status["archunit"][0]
        red = [t["tool"] for t in tools if t["result"] != "green" and t["tool"] != "archunit"]
        state = "done" if arch == "green" and not red else "failed"
        metric = f"ArchUnit {arch}" + (f", {', '.join(red)} red" if red else "")
        return node(state, self.rel(folder), _tool("sensors"), metric, None, None,
                    {"tools": tools, "mutation": mutation})

    def _qa(self, story: Story) -> dict:
        report_path = story.qa("test-report.md")
        report = _read(report_path)
        triage_path = story.qa("triage.md")
        triage = _read(triage_path)
        security_path = story.qa("security-report.md")
        security = _read(security_path)
        if report is None and triage is None:
            return _missing(_agent("qa"))
        verdict = re.search(r"^##\s*Verdict:\s*(PASS|FAIL)", report or "", re.M | re.I)
        counts = triage_counts(triage) if triage else None
        lens_rows = table(heading_section(triage, "Findings by lens"))
        dismissed = len(re.findall(r"verdict:\s*(?:false|maybe-false)", triage or "", re.I))
        lenses = []
        for path in sorted(story.folder("qa").glob(f"{story.story_id}-lens-*.md")):
            body = _read(path) or ""
            lenses.append({
                "name": path.stem.split("-lens-", 1)[1],
                "summary": _first_paragraph(re.sub(r"^#.*$", "", body, flags=re.M)),
                "path": self.rel(path),
            })
        risk, _ = read_json(story.qa("risk.json"))
        sec_verdict = re.search(r"Verdict:\s*([A-Z]+)", security or "")
        severities = Counter(
            (row.get("severity (critical/high/medium/low)") or row.get("severity") or "").strip().title()
            for row in table(security)
            if (row.get("finding") or "").strip()
        )
        data = {
            "verdict": verdict.group(1).upper() if verdict else None,
            "conformance": header_value(report or "", "Conformance"),
            "craft": header_value(report or "", "Craft"),
            "domainFidelity": header_value(report or "", "Domain fidelity"),
            "acTable": ac_table(report or ""),
            "dataChecks": bullets(section(report or "", "Data checks run")),
            "defects": [
                d for d in bullets(section(report or "", "Defects")) if d.strip("() ").lower() != "none"
            ],
            "humanFindings": _strip_footer(section(report or "", "Human findings") or "").strip() or None,
            "triage": {**(counts or {}), "dismissed": dismissed} if counts else None,
            "findingsByLens": lens_rows,
            "lenses": lenses,
            "risk": {"tier": risk.get("tier"), "lenses": risk.get("lenses")} if risk else None,
            "security": {
                "verdict": sec_verdict.group(1) if sec_verdict else None,
                "findings": {k: v for k, v in severities.items() if k},
                "path": self.rel(security_path),
            } if security else None,
            "triagePath": self.rel(triage_path) if triage else None,
            "reviewModel": (provenance(triage) or {}).get("model") if triage else None,
        }
        high = (counts or {}).get("HIGH")
        metric = " · ".join(x for x in (data["verdict"], f"{high} HIGH" if high is not None else None) if x)
        state = {"FAIL": "failed", "PASS": "done"}.get(data["verdict"] or "", "in_progress")
        prov = provenance(report, "qa") or provenance(triage)
        return node(state, self.rel(report_path if report else triage_path), _agent("qa"), metric or None,
                    prov, None, data)

    def _confidence(self, story: Story) -> dict:
        path = story.qa("confidence.json")
        doc, _ = read_json(path)
        if doc is None:
            return _missing(_tool("baton confidence"))
        signals = [
            {"name": name, "points": s.get("points"), "max": s.get("max"), "evidence": s.get("evidence")}
            for name, s in (doc.get("signals") or {}).items()
            if isinstance(s, dict)
        ]
        evidence = story.qa("evidence.md")
        data = {
            "score": doc.get("score"),
            "raw": doc.get("raw"),
            "lane": doc.get("lane"),
            "caps": doc.get("caps") or [],
            "signals": signals,
            "missing": doc.get("missing") or [],
            "evidence": self.rel(evidence) if evidence.is_file() else None,
        }
        metric = f"score {doc.get('score')} · {doc.get('lane')}"
        at = when(doc.get("computedAt"))
        return node("done", self.rel(path), _tool("baton confidence"), metric, None, at, data)

    def _gate3(self, story: Story, state: str, confidence: dict) -> dict:
        report = _read(story.qa("test-report.md"))
        findings = _strip_footer(section(report or "", "Human findings") or "").strip()
        if state not in ("Approved", "Documented", "Done"):
            waiting = state == "QA Pass"
            return node("in_progress" if waiting else "not_produced", None, _human("Tech Lead"))
        lane = confidence.get("data", {}).get("lane")
        read = "evidence.md only" if lane == "fast" else "the diff and the reports"
        data = {
            "decision": "Approved", "by": "Tech Lead", "read": read, "lane": lane, "humanFindings": findings
        }
        return node("done", None, _human("Tech Lead"), "Approved", None, when(findings), data)

    def _docs(self, story: Story, text: str) -> dict:
        path = story.change_note()
        note = _read(path)
        pr = _PR.search(text)
        metrics = self._metric_rows(story.story_id)
        if note is None:
            return _missing(_agent("documentation"))
        arch = re.search(r"^\s*[-*]?\s*\**Architecture:?\**:?\s*(.*)$", _strip_footer(note), re.M | re.I)
        adrs = sorted(set(re.findall(r"ADR-\d+[\w-]*", note)))
        data = {
            "whatChanged": bullets(heading_section(note, "What changed")),
            "architecture": arch.group(1).strip() if arch else None,
            "adrs": [self._adr(a) for a in adrs],
            "pr": pr.group(1) if pr else None,
            "docsPr": (re.search(r"^Docs PR:[ \t]*(\S+)", text, re.M) or [None, None])[1],
            "metrics": metrics,
        }
        metric = "PR " + ("open" if pr else "pending")
        prov = provenance(note, "documentation")
        return node("done", self.rel(path), _agent("documentation"), metric, prov, None, data)

    def _adr(self, name: str) -> dict:
        number = "-".join(name.split("-")[:2])
        found = sorted((self.central / "docs" / "decisions").glob(f"{number}*.md"))
        return {"id": name, "path": self.rel(found[0]) if found else None}

    def _metric_rows(self, story_id: str) -> list[dict]:
        text = _read(self.central / "docs" / "metrics.md") or ""
        found = []
        for name in ("Calibration", "Build", "Delivery"):
            for row in table(section(text, name)):
                if row.get("story", "").strip() == story_id:
                    found.append({"table": name, "row": row})
        return found

    def _merged(self, text: str, state: str) -> dict:
        pr = _PR.search(text)
        if state != "Done":
            return _missing(_tool("git"))
        outcome = header_value(text, "Outcome")
        data = {"pr": pr.group(1) if pr else None, "outcome": outcome}
        return node("done", None, _tool("git"), "merged", None, None, data)

    def _acs(self, text: str, qa: dict) -> list[dict]:
        rows = {row.get("ac"): row for row in qa.get("data", {}).get("acTable") or []}
        acs = []
        for line in bullets(section(text, "Acceptance criteria")):
            match = re.match(r"\**(AC\d+)\**:?\s*(.*)", line)
            if not match:
                continue
            row = rows.get(match.group(1)) or {}
            acs.append({
                "id": match.group(1),
                "text": match.group(2).strip(),
                "test": row.get("test"),
                "result": row.get("result"),
                "evidence": row.get("evidence"),
            })
        return acs

    # ----- knowledge -----

    def knowledge(self, stories: list[dict], start: datetime | None) -> dict:
        domain_text = _read(self.central / "profile" / "domain.md") or ""
        lines = []
        for story in stories:
            for item in story["clarifications"]:
                if item.get("domainLine"):
                    text = item["domainLine"]
                    lines.append({
                        "id": item.get("domainId"),
                        "text": text,
                        "story": story["id"],
                        "approvedBy": "PO",
                        "inDomain": text.rstrip(".").lower() in domain_text.lower(),
                    })
        ids = {s["id"] for s in stories}
        rules = []
        for row in table(_read(self.central / "profile" / "sensors" / "README.md")):
            if not row.get("rule"):
                continue
            added = when(row.get("added"))
            mentions = any(sid in row.get("incident / reason", "") for sid in ids)
            if mentions or (start and added and added >= start):
                rules.append({
                    "name": row.get("rule"),
                    "kind": row.get("kind"),
                    "repo": row.get("repo"),
                    "incident": row.get("incident / reason"),
                    "added": row.get("added"),
                })
        return {"domainLines": lines, "rules": rules, "architecture": self._architecture(stories)}

    def _architecture(self, stories: list[dict]) -> dict:
        elements = relationships = removed = changed = 0
        added: list[str] = []
        lines = []
        log = self.central / "docs" / "architecture" / "CHANGELOG.md"
        rows = [r for r in table(_read(log)) if r.get("feature", "").strip() == self.feature_id]
        workspace = _read(self.central / "docs" / "architecture" / "workspace.dsl")
        if rows:
            def count(row: dict, column: str) -> int:
                found = re.search(r"\d+", row.get(column, ""))
                return int(found.group()) if found else 0

            for row in rows:
                elements += count(row, "elements")
                relationships += count(row, "relationships")
                changed += count(row, "changed")
                removed += count(row, "removed")
                lines.append({"story": row.get("story"), "line": " ".join(
                    row.get(c, "") for c in ("elements", "relationships", "changed", "removed")
                )})
            added = tagged(workspace or "", self.feature_id)
        for story in ([] if rows else stories):
            line = story["nodes"]["docs"]["data"].get("architecture")
            if not line or line.lower().startswith("unchanged"):
                continue
            lines.append({"story": story["id"], "line": line})
            parts = re.findall(r"([+-]\d+)\s+(element|relationship)s?\s*(?:\(([^)]*)\))?", line)
            for count, kind, names in parts:
                number = int(count)
                if number < 0:
                    removed += -number
                elif kind == "element":
                    elements += number
                else:
                    relationships += number
                if number > 0 and names:
                    added.extend(n.strip() for n in names.split(",") if n.strip())
        after = _c4_counts(workspace) if workspace else None
        before = (
            {
                "elements": after["elements"] - elements,
                "relationships": after["relationships"] - relationships,
            }
            if after
            else None
        )
        return {
            "before": before,
            "after": after,
            "addedElements": elements,
            "addedRelationships": relationships,
            "removed": removed,
            "changed": changed,
            "added": added,
            "changelog": self.rel(log) if rows else None,
            "lines": lines,
            "workspace": "docs/architecture/workspace.dsl" if workspace else None,
        }

    # ----- the whole page -----

    def collect(self, selected: str | None = None) -> dict:
        try:
            return self._collect(selected)
        finally:
            for root in self.branch_roots:
                shutil.rmtree(root, ignore_errors=True)

    def _collect(self, selected: str | None) -> dict:
        info, feature_node = self.feature()
        rows = [_story_row(path, self.rel(path)) for path in self.story_paths]
        stories = [self.story(path, feature_node, rows) for path in self.story_paths]
        start = when(info.get("date")) or _earliest(stories)
        done = [s for s in stories if s["state"] == "Done"]
        info["state"] = "Done" if stories and len(done) == len(stories) else "In progress"
        scores = [
            s["nodes"]["confidence"]["data"].get("score")
            for s in stories
            if isinstance(s["nodes"]["confidence"]["data"].get("score"), int | float)
        ]
        lanes = Counter(
            s["nodes"]["confidence"]["data"].get("lane") for s in stories if s["nodes"]["confidence"]["data"]
        )
        gates = [s["nodes"][g]["state"] == "done" for s in stories for g in ("gate1", "gate2", "gate3")]
        end = _latest(done) if done else None
        figures = {
            "storiesDone": len(done),
            "storiesTotal": len(stories),
            "gatesPassed": sum(gates),
            "gatesTotal": len(gates),
            "leadTimeHours": round((end - start).total_seconds() / 3600, 1) if start and end else None,
            "fixLoops": sum(s["loops"] for s in stories),
            "confidenceMedian": statistics.median(scores) if scores else None,
            "lane": lanes.most_common(1)[0][0] if lanes else None,
        }
        return {
            "version": 1,
            "generated": _iso(datetime.now(UTC)),
            "root": self.central.as_posix(),
            "selected": selected,
            "feature": info,
            "people": self.people(info.get("author")),
            "figures": figures,
            "stories": stories,
            "knowledge": self.knowledge(stories, start),
        }


# ---------- functions shared by the collector ----------

def clarifications(text: str) -> list[dict]:
    """`## Clarifications`: `Q: ... A: ...` lines; `-> domain.md: <rule>` (or `-> domain.md R12: <rule>`)
    marks an answer the PO added to profile/domain.md."""
    body = _strip_footer(section(text, "Clarifications") or "")
    found = []
    for line in bullets(body) or [line.strip() for line in body.splitlines() if line.strip()]:
        qa = re.search(r"Q:\s*(.*?)\s*A:\s*(.*)", line)
        if not qa:
            continue
        answer, domain, domain_id = qa.group(2), None, None
        marker = re.search(r"(?:->|→)\s*domain(?:\.md)?\s*([A-Z]+-?\d+)?\s*:?\s*(.*)$", answer, re.I)
        if marker:
            answer = answer[: marker.start()].strip()
            domain_id, domain = marker.group(1), marker.group(2).strip() or None
        found.append({
            "q": qa.group(1).strip(),
            "a": answer.strip(),
            "date": _iso(when(line[: qa.start()])),
            "domainLine": domain,
            "domainId": domain_id,
        })
    return found


def timeline(nodes: dict) -> list[dict]:
    events = []
    for name in NODES:
        item = nodes.get(name) or {}
        prov = item.get("provenance") or {}
        start = when(prov.get("started"))
        at = item.get("at")
        if not at and not start:
            continue
        kind = (item.get("who") or {}).get("kind", "agent")
        events.append({"artefact": name, "at": at or _iso(start), "start": _iso(start), "kind": kind})
    events.sort(key=lambda e: e["at"] or "")
    return events


def _story_row(path: Path, rel: str | None) -> dict:
    text = _read(path) or ""
    title = re.search(r"^#\s+(?:[A-Za-z]+-\d+\s+)?(.+)$", text, re.M)
    score = re.search(r"Score:\s*(\d+\s*/\s*\d+|[\d.]+%?)", section(text, "Readiness") or "")
    match = re.match(r"([A-Za-z]+-\d+)", path.stem)
    return {
        "id": match.group(1) if match else path.stem,
        "title": title.group(1).strip() if title else None,
        "jiraType": header_value(text, "Jira-Type"),
        "labels": header_value(text, "Labels"),
        "track": track_of(text),
        "estimate": header_value(text, "Estimate"),
        "state": header_value(text, "State"),
        "readiness": score.group(1).replace(" ", "") if score else None,
        "path": rel,
    }


def _events(stories: list[dict]) -> list[datetime]:
    moments = []
    for story in stories:
        for event in story["timeline"]:
            for key in ("start", "at"):
                moment = when(event.get(key))
                if moment:
                    moments.append(moment)
    return moments


def _earliest(stories: list[dict]) -> datetime | None:
    moments = _events(stories)
    return min(moments) if moments else None


def _latest(stories: list[dict]) -> datetime | None:
    moments = _events(stories)
    return max(moments) if moments else None


def _mutation(story: TraceStory) -> dict | None:
    paths = [story.qa("mutation.json")] + sorted(story.folder("qa").glob(f"{story.story_id}-mutation-*.json"))
    found = []
    for path in paths:
        doc, _ = read_json(path)
        if doc:
            found.append({
                "repo": doc.get("repo"),
                "score": doc.get("score"),
                "scope": doc.get("scope"),
                "notRun": bool(doc.get("notRun")),
                "reason": doc.get("reason"),
                "path": path.relative_to(story.central).as_posix(),
            })
    return {"runs": found} if found else None


def _git_out(central: Path, *args: str) -> bytes | None:
    try:
        command = ["git", "-C", str(central), *args]
        done = subprocess.run(command, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _svg_data_uri(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size > 2_000_000:
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _c4_counts(dsl: str) -> dict:
    body = re.sub(r"(?s)\bviews\s*\{.*", "", dsl)
    elements = len(re.findall(r"=\s*(?:person|softwareSystem|container|component)\b", body))
    relationships = len(re.findall(r"^\s*[\w.]+\s*->\s*[\w.]+", body, re.M))
    return {"elements": elements, "relationships": relationships}


def _git_commits(repo: Path, branch: str) -> list[dict]:
    if not (repo / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%h%x09%s", "-n", "30", f"main..{branch}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        commits.append({"sha": sha, "subject": subject})
    return commits

