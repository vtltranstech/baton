"""Run one story from Ready to the stop before gate 3, one step at a time (contracts/agent-enhancements.md 3).

baton build S                    run the deterministic steps, then print the one an agent or a human does
baton build S --done STEP        that step returned: check what it wrote, record it, print the next
baton build S --answer approve|changes|block --by TL [--note "..."]   the gate 2 decision
baton build S --answer option-2|changes|block --by PO [--note "..."]  gate 2a, a `ui` story's wireframe
baton build S --from STEP        forget STEP and every later step, then as plain
baton build S --status           the steps recorded so far
baton build S --security-check   exit 2 when the security report is missing, BLOCKED or older than a
                                 branch head, or confidence.json is missing (the release agent runs it
                                 before any PR)

Claude Code runs the agents; this command owns the order. The `/build` skill loops: run `baton build S`,
do what it prints (run the named agent, run a skill, ask the gate question), then report back with
`--done` or `--answer`. Each step is recorded in `docs/qa/<F>/<S>-build.json` with the code branch heads it
saw, so a step is skipped while its outputs exist and the code has not moved, and security runs again
after any later commit. Exit 0: an action is printed, or the story reached the stop before gate 3.
Exit 2: refused or stopped, with the reason.

A story labelled `ui` gets its wireframe first (contracts/ui-stories.md): the architect in UI mode, `baton ux
check`, the UX lens, then gate 2a (the PO picks an option), then the technical design. On the light track the
wireframe is one delta and gate 2a and gate 2 are one question to the PO and the Tech Lead.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from baton import state_check
from baton.confidence import header_value, project_value

EXIT_OK, EXIT_REFUSED = 0, 2
STEPS = (
    "gate0",
    "deps",
    "wireframe",
    "ux-check",
    "ux-lens",
    "gate2a",
    "architect",
    "gate2",
    "developer",
    "checks",
    "qa",
    "security",
    "confidence",
)
ANSWERS = ("approve", "changes", "block", "option-1", "option-2", "option-3")
MAX_CHECK_FAILURES = 3
MANDATORY_LABELS = {"new-api", "data-model", "batch-job"}
MAX_DESIGN_ROUNDS = MAX_FIX_LOOPS = 2
_LENS_FILE = re.compile(r"-lens-[\w-]+\.md")
_VERIFIES = re.compile(r"\b\w+(?:Test|Tests|IT)\b(?:#\w+)?|ArchUnit|ArchitectureTest")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("story_id", help="the story id, e.g. S-010")
    parser.add_argument("--done", metavar="STEP", choices=STEPS, help="the step that just returned")
    parser.add_argument("--answer", choices=ANSWERS, help="the gate 2 decision, or gate 2a's option")
    parser.add_argument("--by", choices=("TL", "SE", "PO", "PO+TL"), help="who decided (with --answer)")
    parser.add_argument("--note", default="", help="the reason or the changes asked for (with --answer)")
    parser.add_argument("--from", dest="from_step", metavar="STEP", choices=STEPS, help="redo from this step")
    parser.add_argument("--status", action="store_true", help="print the recorded steps")
    parser.add_argument("--security-check", action="store_true", help="exit 2 when security is not current")


@dataclass
class Action:
    kind: str  # agent | skill | gate | do | done | stop
    step: str
    text: str
    agent: str | None = None
    inputs: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    then: str | None = None
    log: list[str] = field(default_factory=list)

    @property
    def exit(self) -> int:
        return EXIT_REFUSED if self.kind == "stop" else EXIT_OK


class Build:
    def __init__(self, central: Path, story: state_check.Story):
        self.central, self.story = central, story
        self.sid, self.feature = story.story_id, story.feature
        self.path = story.qa("build.json")
        self.log: list[str] = []

    # --- the ledger ---------------------------------------------------------------------------------------
    def steps(self) -> list[dict]:
        try:
            return list(json.loads(self.path.read_text(encoding="utf-8")).get("steps", []))
        except (OSError, ValueError, AttributeError):
            return []

    def record(self, step: str, by: str = "baton", **extra) -> None:
        steps = self.steps() + [{"step": step, "at": _now(), "by": by, "heads": self.heads(), **extra}]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"story": self.sid, "steps": steps}, indent=1) + "\n", encoding="utf-8"
        )

    def forget_from(self, step: str) -> None:
        later = set(STEPS[STEPS.index(step) :])
        kept = [s for s in self.steps() if s.get("step") not in later]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"story": self.sid, "steps": kept}, indent=1) + "\n", encoding="utf-8"
        )

    def last(self, step: str) -> dict | None:
        return next((s for s in reversed(self.steps()) if s.get("step") == step), None)

    def pos(self, step: str, **match) -> int:
        """Index of the last `step` entry whose fields match (a callable tests the value); -1 if none."""
        for index in range(len(self.steps()) - 1, -1, -1):
            entry = self.steps()[index]
            if entry.get("step") != step:
                continue
            if all(v(entry.get(k)) if callable(v) else entry.get(k) == v for k, v in match.items()):
                return index
        return -1

    def current(self, step: str) -> bool:
        """Recorded, and the code has not moved since."""
        seen = self.last(step)
        return seen is not None and seen.get("heads", {}) == self.heads()

    def heads(self) -> dict[str, str]:
        return state_check.code_heads(self.story)

    def loops(self) -> int:
        return sum(1 for s in self.steps() if s.get("step") == "developer" and s.get("loop"))

    # --- the story ----------------------------------------------------------------------------------------
    def text(self) -> str:
        return self.story.text()

    def state(self) -> str | None:
        return state_check.parse_state(self.text()).state

    def track(self) -> str:
        return state_check.track_of(self.text()) or "full"

    def rel(self, path: Path) -> str:
        return self.story.rel(path)

    def write_state(self, new_state: str, heading: str, lines: list[str]) -> str | None:
        """Append to `## <heading>` and move the State, through the same check as the state-gate hook."""
        text = self.text()
        body = "\n".join(lines) + "\n"
        if state_check.section(text, heading) is None:
            text = text.rstrip("\n") + f"\n\n## {heading}\n{body}"
        else:
            match = re.search(rf"^##[ \t]+{re.escape(heading)}\b[^\n]*\n", text, re.M)
            rest = text[match.end() :]
            following = re.search(r"^##[ \t]", rest, re.M)
            cut = match.end() + (following.start() if following else len(rest))
            text = text[:cut].rstrip("\n") + "\n" + body + ("\n" + text[cut:] if following else "")
        text = re.sub(r"^State:[ \t]*.*$", f"State: {new_state}", text, count=1, flags=re.M)
        result = state_check.check(
            self.story.path, new_state, story_text=text, central=self.central, old_state=self.state()
        )
        if not result.ok:
            return result.missing
        self.story.path.write_text(text, encoding="utf-8")
        return None

    def append(self, heading: str, lines: list[str]) -> None:
        """Append to `## <heading>` without moving the State (gate 2a)."""
        text = self.text()
        body = "\n".join(lines) + "\n"
        part = re.search(rf"^##[ \t]+{re.escape(heading)}\b[^\n]*\n", text, re.M)
        if part is None:
            text = text.rstrip("\n") + f"\n\n## {heading}\n{body}"
        else:
            rest = text[part.end() :]
            following = re.search(r"^##[ \t]", rest, re.M)
            cut = part.end() + (following.start() if following else len(rest))
            text = text[:cut].rstrip("\n") + "\n" + body + ("\n" + text[cut:] if following else "")
        self.story.path.write_text(text, encoding="utf-8")

    # --- deterministic steps ------------------------------------------------------------------------------
    def cli(self, *argv: str) -> tuple[int, str]:
        from baton.cli import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = main([*argv, "--central", str(self.central)])
            except SystemExit as exc:
                code = int(exc.code or 0)
        return code, out.getvalue().strip()

    def gate0(self) -> Action | None:
        off = state_check.gate_off(self.central)
        if off:
            self.log.append(f"gate 0: off for the product by the Tech Lead: {off}")
            if self.last("gate0") is None:
                self.record("gate0", by="TL", override=off, scope="product")
            return None
        if not (self.central / "profile" / "branch-points.yaml").is_file():
            return None
        code, out = self.cli("context", "check", self.sid, "--track", self.track())
        if code == 0:
            self.log.append(f"gate 0: accepted ({self.track()})")
            if not self.current("gate0"):
                self.record("gate0")
            return None
        override = state_check.gate_override(self.text())
        if override:
            self.log.append(f"gate 0: refused, overridden by the Tech Lead: {override}")
            self.record("gate0", by="TL", override=override)
            return None
        return Action(
            "skill",
            "gate0",
            f"gate 0 refused {self.sid}: run the build-context-map skill with "
            f"`focus {self.feature}`, then `baton build {self.sid}` again; if it still refuses, stop "
            f"and report the questions and who must answer them.\n{_tail(out)}",
            then=f"baton build {self.sid}",
        )

    def deps(self) -> Action | None:
        code, out = self.cli("deps", self.sid)
        if code != 0:
            return Action("stop", "deps", f"{self.sid} waits for other stories:\n{_tail(out)}")
        if not self.current("deps"):
            self.record("deps")
        return None

    def confidence(self) -> Action | None:
        for argv in (
            ("confidence", self.sid),
            ("evidence", self.sid),
            ("trace", self.feature, "--story", self.sid),
        ):
            code, out = self.cli(*argv)
            if code != 0:
                return Action("stop", "confidence", f"baton {' '.join(argv)} exited {code}:\n{_tail(out)}")
            self.log.append(f"baton {argv[0]}: done")
        self.record("confidence")
        return None

    # --- gate 2 -------------------------------------------------------------------------------------------
    def design(self) -> Path:
        return self.story.design("findings.md" if self.track() == "spike" else "design.md")

    def design_confidence(self) -> int | None:
        try:
            text = self.design().read_text(encoding="utf-8")
        except OSError:
            return None
        part = re.search(
            r"^##[ \t]+(?:\d+[a-z]?\.[ \t]*)?Confidence\b[^\n]*\n(.*?)(?=^##[ \t]|\Z)", text, re.M | re.S
        )
        found = re.search(r"(\d{1,3})[ \t]*%", part.group(1) if part else "") or re.search(
            r"confidence[ \t]+(\d{1,3})[ \t]*%", text, re.I
        )
        return int(found.group(1)) if found else None

    def ledger_problems(self) -> list[str]:
        """Pattern ledger rows whose Verification cell is prose, not a test or an ArchUnit rule."""
        try:
            text = self.design().read_text(encoding="utf-8")
        except OSError:
            return []
        part = re.search(
            r"^##[ \t]+(?:\d+[a-z]?\.[ \t]*)?Pattern ledger\b[^\n]*\n(.*?)(?=^##[ \t]|\Z)", text, re.M | re.S
        )
        problems = []
        for line in (part.group(1) if part else "").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not line.strip().startswith("|") or len(cells) < 5 or set("".join(cells)) <= set("-: "):
                continue
            if cells[0].lower() == "class":
                continue
            if not _VERIFIES.search(cells[4]):
                problems.append(f"{cells[0]}: Verification `{cells[4]}` names no test or ArchUnit rule")
        return problems

    def labels(self) -> set[str]:
        value = header_value(self.text(), "Labels") or ""
        return {part.strip().lower() for part in value.split(",") if part.strip() and part.strip() != "none"}

    # --- a `ui` story: wireframe, ux check, UX lens, gate 2a (contracts/ui-stories.md) ---------------------
    def ui(self) -> bool:
        return "ui" in self.labels()

    def wireframe(self, name: str = "") -> Path:
        folder = self.story.design("wireframe")
        return folder / name if name else folder

    def wireframe_inputs(self) -> list[str]:
        paths = [self.wireframe("screen-spec.md")]
        paths.append(self.wireframe("approved.html" if self.track() != "light" else "option-1.html"))
        return [self.rel(p) for p in paths if p.is_file()]

    def recommended(self) -> int | None:
        try:
            text = self.wireframe("options.md").read_text(encoding="utf-8")
        except OSError:
            return None
        for line in text.splitlines():
            found = re.search(r"option[ -]?(\d)", line, re.I)
            if found and re.search(r"recommended", line, re.I):
                return int(found.group(1))
        return None

    def ui_steps(self) -> Action | None:
        """The next wireframe step of a `ui` story in Ready or Design Changes Requested; None when done."""
        if not self.ui():
            return None
        light = self.track() == "light"
        wire = self.pos("wireframe")
        redo = max(
            self.pos("ux-check", ok=False),
            self.pos("gate2a", answer="changes"),
            self.pos("gate2", answer="changes") if light else -1,
        )
        if wire == -1 or redo > wire:
            failures = sum(1 for s in self.steps() if s.get("step") == "ux-check" and s.get("ok") is False)
            if failures >= MAX_CHECK_FAILURES:
                return Action(
                    "stop", "ux-check", f"the wireframe failed baton ux check {failures} times: a human looks"
                )
            last = self.steps()[redo] if redo > wire and redo >= 0 else {}
            why = f" Redo it: {last.get('note')}" if last.get("note") else ""
            manifest = self.story.design("context.md")
            extra = [
                self.central / "profile" / "ui-inventory.yaml",
                self.central / "docs" / "architecture" / "screens" / "index.md",
                self.central / ".claude" / "templates" / "ui" / "wireframe.html",
            ]
            what = "one wireframe as a delta on the screen of record" if light else "up to three options"
            return Action(
                "agent",
                "wireframe",
                f"UI mode: {what} and screen-spec.md for {self.sid} in {self.rel(self.wireframe())}/, "
                "every region built from the "
                f"component library (contracts/ui-stories.md section 2).{why}",
                agent="architect",
                inputs=[self.rel(self.story.path)] + [self.rel(p) for p in [manifest, *extra] if p.is_file()],
                then=f"baton build {self.sid} --done wireframe",
            )
        if self.pos("ux-check") < wire:
            code, out = self.cli("ux", "check", self.sid)
            if code != 0:
                problems = [line for line in out.splitlines() if line.strip()]
                self.record("ux-check", ok=False, note="; ".join(problems[:6]))
                self.log.append(f"baton ux check: {len(problems)} problems, back to the architect")
                return self.ui_steps()
            self.record("ux-check", ok=True)
            self.log.append("baton ux check: ok")
        if light:
            return None
        checked = self.pos("ux-check", ok=True)
        if self.pos("ux-lens") < checked:
            return Action(
                "do",
                "ux-lens",
                f"run the UX lens of the design-review-lenses skill on {self.sid} (role skill "
                "ux-checklist): it "
                f"writes {self.rel(self.story.design('reviews') / 'ux.md')}",
                inputs=[
                    self.rel(p) for p in sorted(self.wireframe().glob("*")) if p.suffix in (".html", ".md")
                ],
                then=f"baton build {self.sid} --done ux-lens",
            )
        if self.pos("gate2a", answer=lambda a: str(a or "").startswith("option")) < self.pos("ux-lens"):
            self.cli("ux", "show", self.sid)
            options = sorted(p.stem for p in self.wireframe().glob("option-*.html"))
            best = self.recommended()
            designer = (project_value(self.central, "ui.designer") or "").strip()
            who = "the PO" + (f" with {designer}" if designer and designer.lower() != "none" else "")
            return Action(
                "gate",
                "gate2a",
                f"Wireframes for {self.sid} are ready: open {self.rel(self.wireframe('index.html'))} "
                f"(`baton ux show {self.sid} --open`); the UX lens is at "
                f"{self.rel(self.story.design('reviews') / 'ux.md')}. Gate 2a is {who}'s.",
                options=[f"{o}{' (Recommended)' if best and o == f'option-{best}' else ''}" for o in options]
                + ["changes", "block"],
                then=f'baton build {self.sid} --answer <option-n|changes|block> --by PO --note "<words>"',
            )
        return None

    def answer_wireframe(self, choice: str, by: str | None, note: str) -> Action:
        if self.track() == "light":
            return Action("stop", "gate2a", "the light track answers wireframe and design together at gate 2")
        pending = self.ui_steps()
        if pending is None or pending.step != "gate2a":
            return Action("stop", "gate2a", f"there is no gate 2a question open for {self.sid}")
        if by not in ("PO", "PO+TL"):
            return Action("stop", "gate2a", "gate 2a is the PO's: --by PO")
        rounds = sum(1 for s in self.steps() if s.get("step") == "gate2a" and s.get("answer") == "changes")
        if choice.startswith("option"):
            chosen = self.wireframe(f"{choice}.html")
            if not chosen.is_file():
                return Action("stop", "gate2a", f"{self.rel(chosen)} does not exist")
            self.wireframe("approved.html").write_bytes(chosen.read_bytes())
            self.append(
                "Wireframe approval",
                [
                    f"- {_today()} {by}: {choice.replace('-', ' ').title()} approved"
                    + (f" - {note}" if note else "")
                ],
            )
        elif choice == "changes" and rounds < MAX_DESIGN_ROUNDS:
            self.append(
                "Wireframe approval", [f"- {_today()} {by}: Changes requested (round {rounds + 1}): {note}"]
            )
        elif choice in ("changes", "block"):
            line = f"- {_today()} {by}: " + (
                f"still not approved after {rounds} rounds - {note}"
                if choice == "changes"
                else f"Blocked - {note}"
            )
            missing = self.write_state("Blocked", "Wireframe approval", [line])
            if missing:
                return Action("stop", "gate2a", f"refused: {missing}")
        else:
            return Action("stop", "gate2a", f"gate 2a takes option-<n>, changes or block, not {choice}")
        self.record("gate2a", by=by, answer=choice, note=note)
        return self.next()

    def gate2(self) -> Action | None:
        problems = self.ledger_problems() if self.track() == "full" else []
        if problems:
            missing = self.write_state(
                "Design Changes Requested",
                "Design review",
                [f"- {_today()} baton: changes requested - pattern ledger: " + "; ".join(problems)],
            )
            if missing:
                return Action("stop", "gate2", f"cannot send the design back: {missing}")
            self.record("gate2", answer="changes", note="pattern ledger")
            return self.next()
        score, labels, track = self.design_confidence(), self.labels(), self.track()
        extra = {
            x.strip().lower() for x in (project_value(self.central, "jira.labels.extra") or "").split(",")
        }
        mandatory = sorted(labels & (MANDATORY_LABELS | (extra - {""})))
        threshold = int(
            re.sub(r"\D", "", project_value(self.central, "track.auto-pass.confidence") or "") or 80
        )
        if self.ui() and track == "light":
            return Action(
                "gate",
                "gate2",
                f"Wireframe delta and design for {self.sid} (light track): "
                f"{', '.join(self.wireframe_inputs() + [self.rel(self.design())])}, confidence "
                f"{score if score is not None else '?'}%. "
                "One question for the PO and the Tech Lead together.",
                options=["approve (wireframe + design)", "changes", "block"],
                then=f'baton build {self.sid} --answer <approve|changes|block> --by PO+TL --note "<words>"',
            )
        if track == "light" and not mandatory and ("hotfix" in labels or (score or 0) >= threshold):
            why = "hotfix" if "hotfix" in labels else f"light track, confidence {score}%"
            missing = self.write_state(
                "Design Approved",
                "Design review",
                [f"- {_today()} auto-passed ({why}) - reviewer may still open {self.rel(self.design())}"],
            )
            if missing:
                return Action("stop", "gate2", f"auto-pass refused: {missing}")
            self.record("gate2", answer="auto-pass", note=why)
            self.log.append(f"gate 2: auto-passed ({why})")
            return self.next()
        recommended = "approve" if (score or 0) >= threshold and not mandatory else "changes"
        prompt = (
            f"Design for {self.sid} ({track}) is ready at {self.rel(self.design())}, confidence "
            f"{score if score is not None else '?'}%."
            + (f" Mandatory review: {', '.join(mandatory)}." if mandatory else "")
        )
        return Action(
            "gate",
            "gate2",
            prompt,
            options=[
                f"approve{' (Recommended)' if recommended == 'approve' else ''}",
                f"changes{' (Recommended)' if recommended == 'changes' else ''}",
                "block",
            ],
            then=f'baton build {self.sid} --answer <approve|changes|block> --by TL --note "<words>"',
        )

    def answer(self, choice: str, by: str | None, note: str) -> Action:
        if self.ui() and self.state() in ("Ready", "Design Changes Requested"):
            return self.answer_wireframe(choice, by, note)
        if choice.startswith("option"):
            return Action(
                "stop", "gate2", f"{choice} answers gate 2a, and {self.sid} has no wireframe question open"
            )
        if self.ui() and self.track() == "light" and by != "PO+TL":
            return Action(
                "stop", "gate2", "a light `ui` story's wireframe and design are one answer: --by PO+TL"
            )
        if self.state() != "Designed":
            return Action(
                "stop", "gate2", f"{self.sid} is {self.state()}, not Designed: there is no gate 2 to answer"
            )
        if not by:
            return Action("stop", "gate2", "--answer needs --by (who decided)")
        rounds = sum(
            1
            for s in self.steps()
            if s.get("step") == "gate2" and s.get("answer") == "changes" and s.get("by") != "baton"
        )
        score = self.design_confidence()
        if choice == "approve" and self.ui() and self.track() == "light":
            delta = self.wireframe("option-1.html")
            if delta.is_file():
                self.wireframe("approved.html").write_bytes(delta.read_bytes())
            self.append("Wireframe approval", [f"- {_today()} {by}: delta approved with the design"])
        if choice == "approve":
            line, state = (
                f"- {_today()} {by}: Approved, confidence {score}%" + (f" - {note}" if note else ""),
                "Design Approved",
            )
        elif choice == "changes" and rounds >= MAX_DESIGN_ROUNDS:
            line, state = f"- {_today()} {by}: still not approved after {rounds} rounds - {note}", "Blocked"
        elif choice == "changes":
            line, state = (
                f"- {_today()} {by}: Changes requested (round {rounds + 1}): {note}",
                "Design Changes Requested",
            )
        else:
            line, state = f"- {_today()} {by}: Blocked - {note}", "Blocked"
        missing = self.write_state(state, "Design review", [line])
        if missing:
            return Action("stop", "gate2", f"refused: {missing}")
        self.record("gate2", by=by, answer=choice, note=note)
        return self.next()

    # --- the sequence -------------------------------------------------------------------------------------
    def story_inputs(self) -> list[str]:
        return [self.rel(self.story.path), self.rel(self.design())]

    def next(self) -> Action:
        state = self.state()
        if self.story.ref is not None:
            return Action(
                "stop", "gate0", f"{self.sid} lives on {self.story.ref}: check that branch out first"
            )
        if state in ("Draft", "Needs Clarification", "Ready for PO"):
            return Action(
                "skill",
                "gate0",
                f"{self.sid} is {state}: run the ready skill on it first (gate 1); "
                "nothing is built from an unapproved story",
                then=f"baton build {self.sid}",
            )
        if state in ("Approved", "Documented", "Done"):
            return Action("done", "confidence", f"{self.sid} is {state}: past /build (/sprint-review, /ship)")
        if state == "Blocked":
            security = self.story.qa("security-report.md")
            blocked = security.is_file() and re.search(
                r"Verdict:[ \t]*BLOCKED", security.read_text(errors="replace")
            )
            if blocked and self.loops() < MAX_FIX_LOOPS:
                return self.developer(fix=[self.rel(security)])
            return Action("stop", "developer", f"{self.sid} is Blocked; a human unblocks it")
        if state in ("Ready", "Design Changes Requested"):
            waiting = self.gate0() or self.deps() or self.ui_steps()
            if waiting:
                return waiting
            manifest = self.story.design("context.md")
            inputs = [self.rel(self.story.path)] + ([self.rel(manifest)] if manifest.is_file() else [])
            inputs += self.wireframe_inputs() if self.ui() else []
            return Action(
                "agent",
                "architect",
                f"design {self.sid} ({self.track()} track)",
                agent="architect",
                inputs=inputs,
                then=f"baton build {self.sid} --done architect",
            )
        if state == "Designed":
            return self.gate2()
        if state == "Design Approved":
            return self.developer()
        if state == "In Review":
            if not (self.current("checks") and self.story.qa("diff-shape.json").is_file()):
                return Action(
                    "do",
                    "checks",
                    "after the developer: the diff-shape files, impact, mutation, the "
                    "as-built diagrams and `baton risk`, exactly as the build skill's developer step "
                    "says",
                    then=f"baton build {self.sid} --done checks",
                )
            return Action(
                "agent",
                "qa",
                f"verify {self.sid}",
                agent="qa",
                inputs=self.story_inputs() + [self.rel(self.story.qa("risk.json"))],
                then=f"baton build {self.sid} --done qa",
            )
        if state == "QA Fail":
            if self.loops() >= MAX_FIX_LOOPS:
                return Action(
                    "stop",
                    "developer",
                    f"{self.sid} failed QA after {MAX_FIX_LOOPS} fix loops: the "
                    "Senior Engineer looks before another run",
                )
            triage = self.story.qa("triage.md")
            if not triage.is_file():
                return Action(
                    "stop", "qa", f"{self.rel(triage)} does not exist: the fix loop reads only triage"
                )
            return self.developer(fix=[self.rel(triage)])
        if state == "QA Pass":
            security = self.story.qa("security-report.md")
            stale = None
            if security.is_file():
                stale = state_check.security_stale(self.story, security.read_text(errors="replace"))
            if not security.is_file() or stale or not self.current("security"):
                why = (
                    "first run" if not security.is_file() else (stale or "the code moved since the last run")
                )
                return Action(
                    "agent",
                    "security",
                    f"security review of {self.sid} ({why})",
                    agent="security",
                    inputs=self.story_inputs(),
                    then=f"baton build {self.sid} --done security",
                )
            if not (self.current("confidence") and self.story.qa("confidence.json").is_file()):
                stopped = self.confidence()
                if stopped:
                    return stopped
            return Action(
                "done",
                "confidence",
                f"{self.sid} is QA Pass with a current security report and "
                f"its evidence: gate 3 is the Tech Lead's at /sprint-review",
            )
        return Action("stop", "gate0", f"{self.sid} has no State /build knows ({state})")

    def developer(self, fix: list[str] | None = None) -> Action:
        inputs = self.story_inputs() + (fix or [f".baton/context/{self.sid}.md"])
        what = f"fix loop {self.loops() + 1}: fix only what {fix[0]} lists" if fix else f"build {self.sid}"
        return Action(
            "agent",
            "developer",
            what,
            agent="developer",
            inputs=inputs,
            then=f"baton build {self.sid} --done developer",
        )

    def done(self, step: str) -> Action:
        problem = self.check_done(step)
        if problem:
            return Action("stop", step, f"--done {step} refused: {problem}")
        extra = {}
        if step == "developer" and self.state() == "In Review" and self.last("qa") is not None:
            extra["loop"] = self.loops() + 1
        self.record(step, by="agent", **extra)
        return self.next()

    def check_done(self, step: str) -> str | None:
        state = self.state()
        if step == "architect":
            if not self.design().is_file():
                return f"{self.rel(self.design())} does not exist"
            return None if state == "Designed" else f"the story is {state}, not Designed"
        if step == "wireframe":
            if not self.wireframe("screen-spec.md").is_file():
                return f"{self.rel(self.wireframe('screen-spec.md'))} does not exist"
            if not any(self.wireframe().glob("option-*.html")):
                return f"{self.rel(self.wireframe())} has no option-<n>.html"
            return None
        if step == "ux-lens":
            lens = self.story.design("reviews") / "ux.md"
            return None if lens.is_file() else f"{self.rel(lens)} does not exist"
        if step == "developer":
            if state != "In Review":
                return f"the story is {state}, not In Review"
            if self.last("qa") is not None:
                footer = _footer(self.text(), "developer")
                if _LENS_FILE.search(footer):
                    return (
                        "the fix loop read a lens file (provenance footer); its only review input is "
                        f"{self.rel(self.story.qa('triage.md'))}"
                    )
            return None
        if step == "checks":
            missing = [
                self.rel(p)
                for p in (self.story.qa("diff-shape.json"), self.story.qa("risk.json"))
                if not p.is_file()
            ]
            return f"missing {', '.join(missing)}" if missing else None
        if step == "qa":
            if not self.story.qa("test-report.md").is_file():
                return f"{self.rel(self.story.qa('test-report.md'))} does not exist"
            return (
                None if state in ("QA Pass", "QA Fail") else f"the story is {state}, not QA Pass or QA Fail"
            )
        if step == "security":
            report = self.story.qa("security-report.md")
            if not report.is_file():
                return f"{self.rel(report)} does not exist"
            return state_check.security_stale(self.story, report.read_text(errors="replace"))
        return f"{step} is run by baton build itself; run `baton build {self.sid}`"

    def security_check(self) -> str | None:
        report = self.story.qa("security-report.md")
        if not report.is_file():
            return f"{self.rel(report)} does not exist"
        text = report.read_text(errors="replace")
        if re.search(r"Verdict:[ \t]*BLOCKED", text):
            return f"{self.rel(report)} says Verdict: BLOCKED"
        stale = state_check.security_stale(self.story, text)
        if stale:
            return stale
        if not self.story.qa("confidence.json").is_file():
            return f"{self.rel(self.story.qa('confidence.json'))} does not exist (run baton confidence)"
        return None


def _footer(text: str, agent: str) -> str:
    for match in re.finditer(r"<!--\s*baton:provenance(.*?)-->", text, re.S):
        if re.search(rf"^agent:[ \t]*{re.escape(agent)}\b", match.group(1), re.M):
            return match.group(1)
    return ""


def _tail(out: str, lines: int = 12) -> str:
    return "\n".join(out.splitlines()[-lines:])


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def render(action: Action) -> str:
    lines = [*action.log, f"{action.kind.upper()} {action.step}: {action.text}"]
    if action.agent:
        lines.append(f"  agent: {action.agent} (model from `baton models`)")
    lines += [f"  input: {path}" for path in action.inputs]
    lines += [f"  option: {option}" for option in action.options]
    if action.then:
        lines.append(f"  then: {action.then}")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    try:
        story = state_check.find_story(central, args.story_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"baton build: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    build = Build(central, story)
    if args.status:
        for step in build.steps():
            extra = " ".join(f"{k}={v}" for k, v in step.items() if k not in ("step", "at", "by", "heads"))
            print(f"{step['at']} {step['step']:<11} {step['by']:<6} {extra}".rstrip())
        return EXIT_OK
    if args.security_check:
        problem = build.security_check()
        print(
            f"refused: {problem}" if problem else "ok: security current, confidence present",
            file=sys.stderr if problem else sys.stdout,
        )
        return EXIT_REFUSED if problem else EXIT_OK
    if args.from_step:
        build.forget_from(args.from_step)
    if args.answer:
        action = build.answer(args.answer, args.by, args.note)
    elif args.done:
        action = build.done(args.done)
    else:
        action = build.next()
    action.log = build.log + action.log
    if args.json:
        print(json.dumps({**asdict(action), "exit": action.exit}, indent=1))
    else:
        print(render(action), file=sys.stderr if action.kind == "stop" else sys.stdout)
    return action.exit
