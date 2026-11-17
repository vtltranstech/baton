"""Check a story state change against its prerequisite artefacts (contracts/states.md).

Stdlib only. Used by `baton state-check` and by the state-gate hook.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

STATES = [
    "Draft",
    "Needs Clarification",
    "Ready for PO",
    "Ready",
    "Designed",
    "Design Approved",
    "Design Changes Requested",
    "Blocked",
    "In Review",
    "QA Pass",
    "QA Fail",
    "Approved",
    "Documented",
    "Done",
]
ALWAYS_ALLOWED = {"Draft", "Blocked", "Needs Clarification", "Design Changes Requested"}
_STATE_LINE = re.compile(r"^[ \t]*[*_]*state[*_]*[ \t]*:[*_]*[ \t]*(.*?)[ \t]*$", re.I | re.M)
_ID = re.compile(r"^([A-Za-z]+-\d+)")
_STORY_ID = re.compile(r"[A-Za-z]+-\d+")
_DEPENDS_LINE = re.compile(r"^[*_]*Depends-On[*_]*[ \t]*:[*_]*[ \t]*(.*?)[ \t]*$", re.I | re.M)
BEFORE_WORK = {"Ready for PO", "Ready"}
# Forward moves only; ALWAYS_ALLOWED states can be entered from anywhere.
NEXT_STATES = {
    "Draft": {"Ready for PO"},
    "Needs Clarification": {"Ready for PO"},
    "Ready for PO": {"Ready"},
    "Ready": {"Designed"},
    "Designed": {"Design Approved"},
    "Design Approved": {"In Review"},
    "Design Changes Requested": {"Designed"},
    "Blocked": {"Ready for PO", "Ready", "Designed", "Design Approved", "In Review"},
    "In Review": {"QA Pass", "QA Fail"},
    "QA Fail": {"In Review"},
    "QA Pass": {"Approved"},
    "Approved": {"Documented"},
    "Documented": {"Done"},
    "Done": set(),
}


def normalize_state(value: str) -> str | None:
    """Map free text after `State:` to a contract state: `Blocked — awaiting Q1` is Blocked."""
    cleaned = re.sub(r"\s+", " ", value.replace("*", "").replace("_", " ")).strip().casefold()
    for state in sorted(STATES, key=len, reverse=True):
        lowered = state.casefold()
        if cleaned == lowered or re.match(re.escape(lowered) + r"(\s*[—–\-:(]|\s+\W)", cleaned):
            return state
    return None


@dataclass
class ParsedState:
    state: str | None
    conflict: str | None = None


def parse_state(text: str) -> ParsedState:
    """Every State line must agree; an unknown value is returned as written and is refused later."""
    found = [match.group(1) for match in _STATE_LINE.finditer(text)]
    if not found:
        return ParsedState(None)
    states = [normalize_state(value) or value for value in found]
    if len(set(states)) > 1:
        return ParsedState(states[0], " vs ".join(sorted(set(states))))
    return ParsedState(states[0])


def section(text: str, heading: str) -> str | None:
    """Body of `## <heading>`, up to the next `##` heading; None when absent."""
    match = re.search(rf"^##[ \t]+{re.escape(heading)}\b[^\n]*\n?", text, re.M | re.I)
    if not match:
        return None
    rest = text[match.end() :]
    following = re.search(r"^##[ \t]", rest, re.M)
    return rest[: following.start()] if following else rest


def track_of(text: str) -> str | None:
    match = re.search(r"^Track:[ \t]*(\w+)", text, re.M | re.I)
    value = match.group(1).lower() if match else None
    return value if value in ("light", "full", "spike") else None


@dataclass
class Story:
    central: Path
    feature: str
    story_id: str
    path: Path
    ref: str | None = None  # the story/<F>-<S> branch it is read from when this working tree lacks it

    def text(self) -> str:
        """The story file: from disk, or from its story branch (contracts/versioning.md section 1)."""
        if self.ref is None:
            return self.path.read_text(encoding="utf-8")
        done = _git(self.central, "show", f"{self.ref}:{self.rel(self.path)}")
        if done is None or done.returncode != 0:
            raise FileNotFoundError(f"{self.rel(self.path)} is not on {self.ref}")
        return done.stdout

    def read(self, path: Path) -> str | None:
        """Any file of the story: from disk, else from its story branch; None when neither has it."""
        if path.is_file():
            return path.read_text(encoding="utf-8")
        if self.ref is None:
            return None
        done = _git(self.central, "show", f"{self.ref}:{self.rel(path)}")
        return done.stdout if done is not None and done.returncode == 0 else None

    def qa(self, suffix: str) -> Path:
        return self.central / "docs" / "qa" / self.feature / f"{self.story_id}-{suffix}"

    def design(self, suffix: str = "design.md") -> Path:
        return self.central / "docs" / "design" / self.feature / f"{self.story_id}-{suffix}"

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.central).as_posix()
        except ValueError:
            return path.as_posix()


def story_from_path(path: Path, central: Path | None = None) -> Story:
    path = Path(os.path.abspath(path))
    parts = path.parts
    for index in range(len(parts) - 3, -1, -1):
        if parts[index].casefold() == "docs" and parts[index + 1].casefold() == "stories":
            if index + 3 != len(parts) - 1:
                break
            root = Path(*parts[:index]) if index else Path(parts[0])
            match = _ID.match(path.stem)
            return Story(
                Path(central) if central else root,
                parts[index + 2],
                match.group(1) if match else path.stem,
                path,
            )
    raise ValueError(f"{path} is not docs/stories/<feature>/<story>.md")


_BRANCH = re.compile(r"^story/(.+)-([A-Za-z]+-\d+)$")


def _git(central: Path, *args: str) -> subprocess.CompletedProcess | None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        return subprocess.run(
            ["git", "-C", str(central), *args], capture_output=True, text=True, env=env, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return None


def branch_stories(central: Path) -> list[Story]:
    """Stories that live only on a `story/<F>-<S>` branch, local branches first, then `origin/`.

    Each story's files stay on its branch until its docs PR merges, so one working tree shows only the
    default branch and the checked-out story; this is how every other story is still found.
    """
    central = Path(central)
    done = _git(
        central, "for-each-ref", "--format=%(refname:short)", "refs/heads/story/",
        "refs/remotes/origin/story/",
    )
    if done is None or done.returncode != 0:
        return []
    found: dict[str, Story] = {}
    for ref in done.stdout.split():
        match = _BRANCH.match(ref.removeprefix("origin/"))
        if not match or match.group(2) in found:
            continue
        feature, story_id = match.group(1), match.group(2)
        listing = _git(central, "ls-tree", "--name-only", ref, f"docs/stories/{feature}/")
        names = listing.stdout.split() if listing and listing.returncode == 0 else []
        for name in names:
            stem = Path(name).stem
            if name.endswith(".md") and (stem == story_id or stem.startswith(story_id + "-")):
                found[story_id] = Story(central, feature, story_id, central / name, ref)
                break
    return list(found.values())


def find_story(central: Path, story_id: str) -> Story:
    """`S-010` finds S-010.md or S-010-slug.md under docs/stories/<any>/; refuses an ambiguous id."""
    root = Path(central) / "docs" / "stories"
    found = [
        p for p in sorted(root.glob("*/*.md")) if p.stem == story_id or p.stem.startswith(story_id + "-")
    ]
    if not found:
        # A finished feature moved to docs/archive/<F>/stories/ (contracts/versioning.md section 5).
        archived = [
            p
            for p in sorted((Path(central) / "docs" / "archive").glob("*/stories/*.md"))
            if p.stem == story_id or p.stem.startswith(story_id + "-")
        ]
        if len(archived) == 1:
            match = _ID.match(archived[0].stem)
            story = match.group(1) if match else story_id
            return Story(Path(central), archived[0].parts[-3], story, archived[0])
        on_branch = [story for story in branch_stories(Path(central)) if story.story_id == story_id]
        if on_branch:
            return on_branch[0]
        raise FileNotFoundError(f"no story {story_id} under {root}, in the archive or on a story/ branch")
    if len(found) > 1:
        raise FileNotFoundError(f"story id {story_id} is ambiguous: {[p.name for p in found]}")
    return story_from_path(found[0], Path(central))


def archunit_status(path: Path) -> tuple[bool, str]:
    """Green means every `Tests run:` line ran something and shows no failure or error."""
    if not path.is_file():
        return False, "archunit.txt not present"
    runs = re.findall(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)", path.read_text(errors="replace")
    )
    if not runs:
        return False, "archunit.txt has no `Tests run:` line"
    if any(int(failed) or int(errors) for _, failed, errors in runs):
        return False, "archunit.txt shows failures or errors"
    if sum(int(total) for total, _, _ in runs) == 0:
        return False, "archunit.txt shows zero tests run"
    return True, f"archunit.txt green ({sum(int(r[0]) for r in runs)} tests)"


def _human_findings_filled(report: str) -> bool:
    body = section(report, "Human findings")
    if body is None:
        return False
    for line in body.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if (
            not line
            or line.startswith(("(", "<!--", "<"))
            or line.casefold() in ("tbd", "todo", "n/a", "pending")
        ):
            continue
        return True
    return False


def _approved_design(text: str) -> bool:
    body = section(text, "Design review")
    if body is None:
        return False
    return bool(re.search(r"(?<![Nn]ot )(?<![Uu]n)\bApproved\b|auto-passed", body))


def parse_depends_on(text: str) -> tuple[list[str] | None, str | None]:
    """(ids, problem) from the `Depends-On:` line; ids is None when there is no line."""
    match = _DEPENDS_LINE.search(text)
    if not match:
        return None, None
    value = re.split(r"\s+[—–#]\s*|\s+-\s+", match.group(1), maxsplit=1)[0].strip()
    if value.casefold() == "none":
        return [], None
    tokens = [token.strip() for token in value.split(",") if token.strip()]
    bad = [token for token in tokens if not _STORY_ID.fullmatch(token)]
    if bad or not tokens:
        return None, f"`Depends-On: {match.group(1)}` must be story ids separated by commas, or `none`"
    return list(dict.fromkeys(tokens)), None


def _depends_of(central: Path, story_id: str) -> list[str]:
    try:
        text = find_story(central, story_id).text()
    except (FileNotFoundError, OSError):
        return []
    return parse_depends_on(text)[0] or []


def _cycle(central: Path, start: str, depends: list[str]) -> list[str] | None:
    """The first path from a dependency back to `start`, or None."""
    seen: set[str] = set()
    stack = [[start, dep] for dep in depends]
    while stack:
        path = stack.pop()
        if path[-1] == start:
            return path
        if path[-1] not in seen:
            seen.add(path[-1])
            stack.extend(path + [dep] for dep in _depends_of(central, path[-1]))
    return None


def unfinished_dependencies(story: Story, depends: list[str]) -> list[tuple[str, str]]:
    """(id, state) of each dependency that is not Done; a missing story is refused earlier."""
    waiting = []
    for dep in depends:
        state = parse_state(find_story(story.central, dep).text()).state
        if state != "Done":
            waiting.append((dep, state or "no State line"))
    return waiting


def dependency_problem(story: Story, new_state: str, text: str) -> str | None:
    """Every forward state needs a valid `Depends-On:`; work from Designed on needs them Done."""
    depends, problem = parse_depends_on(text)
    if problem:
        return problem
    if depends is None:
        return "the story has no `Depends-On:` line (story ids separated by commas, or `none`)"
    for dep in depends:
        if dep == story.story_id:
            return f"{story.story_id} lists itself under `Depends-On:`"
        try:
            find_story(story.central, dep)
        except FileNotFoundError as exc:
            return f"`Depends-On: {dep}`: {exc}"
    loop = _cycle(story.central, story.story_id, depends)
    if loop:
        return f"`Depends-On:` makes a loop, so no story could ever start: {' -> '.join(loop)}"
    if new_state in BEFORE_WORK:
        return None
    waiting = unfinished_dependencies(story, depends)
    if waiting:
        listed = ", ".join(f"{dep} ({state})" for dep, state in waiting)
        return f"{story.story_id} depends on {listed}. Finish and merge it first; work cannot start until it is Done"  # noqa: E501
    return None


def order_problem(old_state: str, new_state: str, text: str) -> str | None:
    """A move that skips a step, per contracts/states.md, or None."""
    if new_state == old_state or new_state in ALWAYS_ALLOWED:
        return None
    if old_state not in NEXT_STATES:
        return f"the current State `{old_state}` is not in contracts/states.md; a human must correct it"
    allowed = NEXT_STATES[old_state]
    if track_of(text) == "spike" and old_state == "Design Approved" and new_state == "Documented":
        return None
    if new_state not in allowed:
        nexts = ", ".join(sorted(allowed)) or "nothing further"
        return f"`{old_state}` cannot move to `{new_state}`; the next step is {nexts}"
    if old_state == "Blocked" and new_state == "In Review" and not _approved_design(text):
        return "a Blocked story can reach `In Review` only with an approved `## Design review`"
    return None


# Gate 0 override (contracts/agent-enhancements.md section 3): the Tech Lead's own line in the story header.
# Agents never write it; the state-gate hook refuses an agent edit that adds or changes it.
OVERRIDE = re.compile(
    r"^Gate-0-Override:[ \t]*(\S.*?)[ \t]*\((?:TL|Tech Lead),[ \t]*(\d{4}-\d{2}-\d{2})\)[ \t]*$", re.M
)


def gate_override(text: str) -> str | None:
    """The recorded reason when the Tech Lead overrode gate 0 for this story, else None."""
    match = OVERRIDE.search(text or "")
    return f"{match.group(1)} (TL, {match.group(2)})" if match else None


# The Tech Lead switches gate 0 off for the whole product, e.g. while the context map cannot be built:
# a row `| gate0 | off: <reason> (TL, YYYY-MM-DD) |` in profile/project.md. Recorded like the story override,
# shown as `off` on the board; the state-gate hook refuses an agent edit that adds, changes or removes it.
GATE_OFF = re.compile(
    r"^\|[ \t]*gate0[ \t]*\|[ \t]*off:[ \t]*(\S.*?)[ \t]*"
    r"\((?:TL|Tech Lead),[ \t]*(\d{4}-\d{2}-\d{2})\)[ \t]*\|",
    re.M | re.I,
)


def gate_off(central: Path) -> str | None:
    """The recorded reason when the Tech Lead switched gate 0 off for the product, else None."""
    try:
        text = (Path(central) / "profile" / "project.md").read_text(encoding="utf-8")
    except OSError:
        return None
    match = GATE_OFF.search(text)
    return f"{match.group(1)} (TL, {match.group(2)})" if match else None


def context_gate(story: Story, track: str | None, text: str | None = None) -> str | None:
    refused = _context_gate(story, track)
    return None if refused and gate_override(text or "") else refused


def _context_gate(story: Story, track: str | None) -> str | None:
    """Gate 0 (contracts/context-map.md section 10.5): once the product has a context map, a story moves to
    Ready or Designed only with a context manifest, no blocking gap in it, and every area it changes still
    understood well enough for its track (an area goes stale when its code changes after the check)."""
    central = story.central
    if not (central / "profile" / "branch-points.yaml").is_file() or gate_off(central):
        return None
    manifest = story.design("context.json")
    text = story.read(manifest)
    if text is None:
        return (f"{story.rel(manifest)} does not exist: the product has a context map, so run "
                f"baton context check {story.story_id} first (gate 0)")
    try:
        data = json.loads(text)
        blocking = int(data.get("blocking", 0))
    except (ValueError, TypeError, AttributeError):
        return f"{story.rel(manifest)} cannot be read (run baton context check {story.story_id})"
    if blocking:
        return (f"{story.rel(manifest)} lists {blocking} blocking context gap(s); answer them, then "
                f"run baton context check {story.story_id}")
    seen = data.get("gate")
    if seen is None:
        return (f"{story.rel(manifest)} was written before gate 0; run baton context check {story.story_id}")
    if not seen:
        return None
    from baton.context import understanding as us

    path = central / us.STATUS_JSON
    try:
        areas = json.loads(path.read_text(encoding="utf-8"))["areas"]
    except (OSError, ValueError, KeyError, TypeError):
        return f"{us.STATUS_JSON} is missing or unreadable; run baton context check {story.story_id}"
    light_open = int(data.get("lightOpenQuestions", 2))
    for key in sorted(seen):
        refused = us.accepts(areas.get(key, {"status": "unexplored"}), track or "full", light_open)
        if refused:
            return (f"{key} is now {refused}; run /build-context-map focus {story.feature}, then "
                    f"baton context check {story.story_id}")
    return None


def labels_of(text: str) -> set[str]:
    match = re.search(r"^Labels:[ \t]*(.*)$", text, re.M | re.I)
    return {p.strip().lower() for p in (match.group(1) if match else "").split(",") if p.strip()} - {"none"}


def wireframe_problem(story: Story, track: str | None, text: str) -> str | None:
    """A `ui` story is Designed only on an approved wireframe (full) or its delta (light); ui-stories.md 1."""
    if "ui" not in labels_of(text):
        return None
    folder = story.design("wireframe")
    if not (folder / "screen-spec.md").is_file():
        return f"a ui story needs {story.rel(folder / 'screen-spec.md')}"
    if track == "light":
        delta = folder / "option-1.html"
        return None if delta.is_file() else f"a light ui story needs the delta wireframe {story.rel(delta)}"
    if not (folder / "approved.html").is_file():
        return f"a ui story needs {story.rel(folder / 'approved.html')} (gate 2a: the PO picks an option)"
    if not re.search(r"approved", section(text, "Wireframe approval") or "", re.I):
        return "the story's `## Wireframe approval` does not record the PO's choice"
    return None


def missing_prerequisite(story: Story, new_state: str, text: str) -> str | None:
    """The first missing prerequisite, per contracts/states.md, or None."""
    track = track_of(text)
    if new_state in ALWAYS_ALLOWED:
        return None
    if new_state in STATES:
        problem = dependency_problem(story, new_state, text)
        if problem:
            return problem
    if new_state in ("Ready for PO", "Ready"):
        if section(text, "Readiness") is None:
            return "the story has no `## Readiness` section (run /ready)"
        return context_gate(story, track, text)
    if new_state == "Designed":
        problem = context_gate(story, track, text)
        if problem:
            return problem
        problem = wireframe_problem(story, track, text)
        if problem:
            return problem
        finding = "findings.md" if track == "spike" else "design.md"
        if not story.design(finding).is_file():
            return f"{story.rel(story.design(finding))} does not exist"
        dsl = story.central / "docs" / "design" / story.feature / f"{story.story_id}.dsl"
        if track not in ("light", "spike") and not dsl.is_file():
            return f"full track needs {story.rel(dsl)}"
        return None
    if new_state == "Design Approved":
        if _approved_design(text):
            return None
        return "the story's `## Design review` does not contain `Approved` or `auto-passed`"
    if new_state == "In Review":
        sensors = story.qa("sensors")
        ok, why = archunit_status(sensors / "archunit.txt")
        if not ok:
            return f"{story.rel(sensors / 'archunit.txt')}: {why}"
        if not any((sensors / name).is_file() for name in ("pmd.xml", "checkstyle.xml", "eslint.json")):
            return f"{story.rel(sensors)} needs one of pmd.xml, checkstyle.xml, eslint.json"
        for heading in ("Dev summary", "Rule ledger"):
            if section(text, heading) is None:
                return f"the story has no `## {heading}` section"
        return None
    report = story.qa("test-report.md")
    if new_state == "QA Fail":
        return None if report.is_file() else f"{story.rel(report)} does not exist"
    if new_state in ("QA Pass", "Approved"):
        if not report.is_file():
            return f"{story.rel(report)} does not exist"
        report_text = report.read_text(errors="replace")
        if not re.search(r"^##[ \t]*Verdict:[ \t]*PASS[ \t]*$", report_text, re.M):
            return f"{story.rel(report)} does not contain `## Verdict: PASS`"
        if new_state == "QA Pass":
            return None
        security = story.qa("security-report.md")
        if not security.is_file():
            return f"{story.rel(security)} does not exist"
        if re.search(r"Verdict:[ \t]*BLOCKED", security.read_text(errors="replace"), re.I):
            return f"{story.rel(security)} says Verdict: BLOCKED"
        stale = security_stale(story, security.read_text(errors="replace"))
        if stale:
            return stale
        if not story.qa("confidence.json").is_file():
            return f"{story.rel(story.qa('confidence.json'))} does not exist (run baton confidence)"
        if not _human_findings_filled(report_text):
            return f"{story.rel(report)}: `## Human findings` has no non-placeholder line"
        return None
    if new_state == "Documented":
        note = story.central / "docs" / "changes" / story.feature / f"{story.story_id}-change-note.md"
        if not note.is_file():
            return f"{story.rel(note)} does not exist"
        if track not in ("light", "spike"):
            workspace = story.central / "docs" / "architecture" / "workspace.dsl"
            design = story.design()
            if not workspace.is_file():
                return f"{story.rel(workspace)} does not exist"
            if design.is_file() and workspace.stat().st_mtime < design.stat().st_mtime:
                older = f"{story.rel(workspace)} is older than {story.rel(design)}"
                return f"{older} (promote the candidate workspace)"
        return None
    if new_state == "Done":
        if re.search(r"^[*_]*PR[*_]*:[*_]*[ \t]*\S*https?://\S+", text, re.M):
            return None
        return "the story has no `PR:` line with a URL"
    return f"`{new_state}` is not a state in contracts/states.md"


_HEADS = re.compile(r"^Heads:[ \t]*(.+)$", re.M)


def code_heads(story: Story) -> dict[str, str]:
    """The head of `feature/<F>-<S>` in every repo of the repo table that has it (local, else origin)."""
    from baton.extract.repos import read_repo_table

    try:
        repos = read_repo_table(story.central)
    except Exception:  # no project.md or no repo table: nothing to compare
        return {}
    branch, heads = f"feature/{story.feature}-{story.story_id}", {}
    for repo in repos:
        if repo.path == Path(story.central).resolve() or not (repo.path / ".git").exists():
            continue
        for ref in (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"):
            done = _git(repo.path, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}")
            if done is not None and done.returncode == 0:
                heads[repo.name] = done.stdout.strip()
                break
    return heads


def recorded_heads(text: str) -> dict[str, str]:
    """`Heads: repo@sha, repo@sha` from a report or a Dev summary."""
    match = _HEADS.search(text or "")
    pairs = [part.strip().strip("`").split("@", 1) for part in match.group(1).split(",")] if match else []
    return {name.strip(): sha.strip() for name, sha in (p for p in pairs if len(p) == 2) if sha.strip()}


def security_stale(story: Story, report: str) -> str | None:
    """Security runs last: a branch head that moved after the report makes it stale."""
    current = code_heads(story)
    if not current:
        return None
    rel = story.rel(story.qa("security-report.md"))
    seen = recorded_heads(report)
    if not seen:
        return f"{rel} records no `Heads:` line; run the security agent again (baton build {story.story_id})"
    for name, sha in sorted(current.items()):
        old = seen.get(name)
        if not old or not (sha.startswith(old) or old.startswith(sha)):
            return (f"{rel} is stale: {name} is at {sha[:7]}, the report reviewed {old or 'nothing'}; "
                    f"run the security agent again (baton build {story.story_id})")
    return None


@dataclass
class Result:
    ok: bool
    state: str
    missing: str | None = None


def check(
    story_path, new_state: str, story_text: str | None = None, central=None, old_state: str | None = None
) -> Result:
    """`story_text` lets the hook judge the story as it will be after the pending edit.

    `old_state`, when given, also checks the move against the order of states."""
    state = normalize_state(new_state)
    if state is None:
        return Result(False, new_state, f"`{new_state}` is not a state in contracts/states.md")
    try:
        story = story_from_path(Path(story_path), Path(central) if central else None)
    except ValueError as exc:
        return Result(False, state, str(exc))
    if story_text is None:
        if not story.path.is_file():
            return Result(False, state, f"{story_path} does not exist")
        story_text = story.path.read_text(encoding="utf-8")
    missing = order_problem(old_state, state, story_text) if old_state else None
    missing = missing or missing_prerequisite(story, state, story_text)
    return Result(missing is None, state, missing)


def add_arguments(parser) -> None:
    parser.add_argument("story_file", help="docs/stories/<F>/<S>.md (absolute, or relative to --central)")
    parser.add_argument("new_state", help='the state to move to, e.g. "In Review"')


def run(args) -> int:
    path = Path(args.story_file)
    central = Path(args.central)
    if not path.is_absolute() and not path.exists() and (central / path).exists():
        path = central / path
    old_state = parse_state(path.read_text(encoding="utf-8")).state if path.is_file() else None
    result = check(path, args.new_state, old_state=old_state)
    if args.json:
        print(json.dumps({"ok": result.ok, "state": result.state, "missing": result.missing}))
    if result.ok:
        if not args.json:
            print(f"ok: {result.state}")
        return 0
    print(f"refused: {result.state}: {result.missing}", file=sys.stderr)
    return 2
