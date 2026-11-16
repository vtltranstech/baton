"""Write docs/qa/<F>/<S>-evidence.md from the artefacts present (contracts/confidence.md layout).

Stdlib only. Never reads profile/confidence-weights.yaml. Every value names the file it came from, and
anything absent is listed under What was NOT done rather than described.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from baton import confidence, state_check
from baton.confidence import read_json
from baton.state_check import Story, section

SECTIONS = (
    "Story",
    "Design",
    "Build",
    "Verification",
    "Security",
    "Blast radius",
    "Confidence",
    "What was NOT done",
    "Links",
)
EXPECTED = (
    "diff-shape.json",
    "sensors/archunit.txt",
    "mutation.json",
    "test-report.md",
    "triage.md",
    "security-report.md",
    "impact.json",
    "confidence.json",
)


def _text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _story(story: Story, text: str) -> list[str]:
    src = story.rel(story.path)
    title = re.search(r"^#\s+(.*)$", text, re.M)
    out = [f"- Title: {title.group(1) if title else 'not stated'} (source: {src})"]
    for key in ("Track", "Estimate"):
        out.append(f"- {key}: {confidence.header_value(text, key) or 'not stated'} (source: {src})")
    owner = confidence.header_value(text, "PO")
    owner_src = src
    if not owner:
        for feature in sorted((story.central / "docs" / "features").glob(f"{story.feature}*.md")):
            owner = confidence.header_value(feature.read_text(encoding="utf-8"), "Owner")
            owner_src = story.rel(feature)
    out.append(f"- PO: {owner or 'not stated'} (source: {owner_src})")
    return out


def _design(story: Story, text: str) -> list[str]:
    src = story.rel(story.path)
    path = story.design()
    if not path.is_file() and story.design("findings.md").is_file():
        path = story.design("findings.md")
    note = _text(path)
    rel = story.rel(path)
    out = []
    if note is None:
        out.append(f"- Design note: not present (source: {rel})")
    else:
        score = re.search(r"^Score:\s*(\d+)\s*%", note, re.M)
        out.append(f"- Confidence: {score.group(1) + '%' if score else 'not stated'} (source: {rel})")
    review = section(text, "Design review")
    if review is None:
        out.append(f"- Review outcome: not present (source: {src})")
    else:
        if "auto-passed" in review:
            outcome = "auto-passed"
        elif re.search(r"(?<![Nn]ot )\bApproved\b", review):
            outcome = "approved"
        else:
            outcome = "not approved"
        rounds = 1 + len(re.findall(r"changes requested", review, re.I))
        out += [f"- Review outcome: {outcome} (source: {src})", f"- Rounds: {rounds} (source: {src})"]
    diagrams, _ = read_json(story.design("diagrams") / "diagrams.json")
    if diagrams:
        rows = diagrams.get("touchPoints") or []
        counts = {k: sum(1 for r in rows if r.get("status") == k) for k in ("new", "changed", "removed")}
        repos = sorted({r.get("repo") for r in diagrams.get("impacted") or []})
        source = f"{story.rel(story.design('diagrams'))}/diagrams.json"
        out.append(
            f"- Design diagrams: {counts['new']} new, {counts['changed']} changed, "
            f"{counts['removed']} removed; "
            f"blast radius {', '.join(repos) or 'none'} (source: {source})"
        )
    elif note is not None:
        delta = re.search(r"^C4 delta:\s*(.*)$", note, re.M)
        if delta:
            out.append(f"- C4 delta: {delta.group(1)} (source: {rel})")
        else:
            out.append(f"- Design diagrams: not generated (source: {story.rel(story.design('diagrams'))})")
    built, _ = read_json(story.qa("as-built") / "diagrams.json")
    if built and built.get("conformance"):
        c = built["conformance"]
        undeclared = c.get("undeclared", []) + c.get("newClassesUndeclared", [])
        missing = c.get("notBuilt", []) + c.get("newClassesNotBuilt", [])
        out.append(
            f"- Design conformance: built but not designed {', '.join(undeclared) or 'none'}; "
            f"designed but not built {', '.join(missing) or 'none'} "
            f"(source: {story.rel(story.qa('as-built'))}/diagrams.json)"
        )
    return out


def _build(story: Story) -> list[str]:
    rel = story.rel(story.qa("diff-shape.json"))
    diff, why = read_json(story.qa("diff-shape.json"))
    out = []
    if diff is None:
        out.append(f"- Diff shape: {why} (source: {rel})")
    else:
        out += [
            "| Repo | Branch | Commits | Lines added | Lines deleted | Files | Source |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for repo in diff.get("repos") or []:
            cells = [
                repo.get("repo"),
                repo.get("branch"),
                repo.get("commits"),
                repo.get("linesAdded"),
                repo.get("linesDeleted"),
                len(repo.get("files") or []),
                rel,
            ]
            out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
        loops = diff.get("sensorLoops")
        out += ["", f"- Sensor loops: {loops if loops is not None else 'not stated'} (source: {rel})"]
    folder = story.qa("sensors")
    out += ["", "| Sensor | Result | Detail | Source |", "| --- | --- | --- | --- |"]
    names = {
        "archunit": "archunit.txt",
        "pmd": "pmd.xml",
        "checkstyle": "checkstyle.xml",
        "eslint": "eslint.json",
    }
    for name, (state, detail) in confidence.sensor_status(folder).items():
        out.append(f"| {name} | {state} | {_cell(detail)} | {story.rel(folder / names[name])} |")
    return out


def _verification(story: Story) -> list[str]:
    path = story.qa("test-report.md")
    rel = story.rel(path)
    report = _text(path)
    out = []
    if report is None:
        out.append(f"- Test report: not present (source: {rel})")
    else:
        rows = confidence.ac_table(report)
        out += ["| AC | Test | Result | Evidence | Source |", "| --- | --- | --- | --- | --- |"]
        for row in rows:
            cells = [row.get(k, "") for k in ("ac", "test", "result", "evidence")] + [rel]
            out.append("| " + " | ".join(_cell(c) for c in cells) + " |")
        out.append("")
        checks = section(report, "Data checks run")
        lines = [ln.strip().lstrip("- ") for ln in (checks or "").splitlines() if ln.strip()]
        out += [f"- Data check: {line} (source: {rel})" for line in lines] or [
            f"- Data checks: none listed (source: {rel})"
        ]
        for key in ("Conformance", "Craft", "Domain fidelity"):
            out.append(f"- {key}: {confidence.header_value(report, key) or 'not stated'} (source: {rel})")
        verdict = re.search(r"^##[ \t]*Verdict:[ \t]*(.*)$", report, re.M)
        out.append(f"- QA verdict: {verdict.group(1) if verdict else 'not stated'} (source: {rel})")
    documents, bad = confidence.per_repo(story, "mutation")
    mutation_rel = story.rel(story.qa("mutation.json"))
    out += [f"- Mutation score: {item} (source: {mutation_rel})" for item in bad]
    if not documents and not bad:
        out.append(f"- Mutation score: not present (source: {mutation_rel})")
    for path, mutation in documents:
        source = story.rel(path)
        if mutation.get("notRun") or mutation.get("score") is None:
            reason = mutation.get("reason") or "no reason given"
            out.append(f"- Mutation score: not run, {reason} (source: {source})")
        else:
            out.append(f"- Mutation score: {mutation['score']} (source: {source})")
    for lens in sorted(story.qa("sensors").parent.glob(f"{story.story_id}-lens-*.md")):
        name = lens.stem.split("-lens-")[-1]
        verdict = re.search(
            r"^(?:##\s*)?Verdict:\s*(.*)$", lens.read_text(encoding="utf-8", errors="replace"), re.M
        )
        shown = verdict.group(1) if verdict else "no verdict line"
        out.append(f"- Lens {name}: {shown} (source: {story.rel(lens)})")
    triage_path = story.qa("triage.md")
    triage_rel = story.rel(triage_path)
    triage = _text(triage_path)
    counts = confidence.triage_counts(triage) if triage is not None else None
    if counts is None:
        state = "not present" if triage is None else "no ## Counts block"
        out.append(f"- Triage: {state} (source: {triage_rel})")
    else:
        shown = f"HIGH {counts['HIGH']}, MEDIUM {counts['MEDIUM']}, LOW {counts['LOW']}"
        out.append(f"- Triage: {shown} (source: {triage_rel})")
    return out


def _security(story: Story) -> list[str]:
    path = story.qa("security-report.md")
    rel = story.rel(path)
    report = _text(path)
    if report is None:
        return [f"- Security report: not present (source: {rel})"]
    verdict = re.search(r"Verdict:[ \t]*(.*)$", report, re.M)
    out = [f"- Verdict: {verdict.group(1).strip() if verdict else 'not stated'} (source: {rel})"]
    findings = 0
    for line in report.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells and cells[0].isdigit():
            findings += 1
            out.append(f"- Finding {cells[0]}: {' / '.join(cells[1:])} (source: {rel})")
    if not findings:
        out.append(f"- Findings: none listed (source: {rel})")
    return out


def _blast(story: Story) -> list[str]:
    documents, bad = confidence.per_repo(story, "impact")
    rel = story.rel(story.qa("impact.json"))
    out = [f"- Impact: {item} (source: {rel})" for item in bad]
    if not documents and not bad:
        return [f"- Impact: not present (source: {rel})"]
    table = ["| Repo | Via | File | Lines | Breaking | Source |", "| --- | --- | --- | --- | --- | --- |"]
    edges = []
    for path, impact in documents:
        source = story.rel(path)
        if impact.get("notRun"):
            out.append(f"- Impact: not run (source: {source})")
            continue
        for entry in impact.get("impacted") or []:
            cells = [entry.get(k) for k in ("repo", "via", "file", "lines", "breaking")] + [source]
            table.append("| " + " | ".join(_cell(c) for c in cells) + " |")
        edges += [f"- Unknown edge: {edge} (source: {source})" for edge in impact.get("unknownEdges") or []]
    return [*out, *table, "", *(edges or [f"- Unknown edges: none (source: {rel})"])]


def _confidence(story: Story, document: dict | None, why: str | None) -> list[str]:
    rel = story.rel(story.qa("confidence.json"))
    if document is None:
        return [f"- Confidence: {why} (source: {rel})"]
    out = [
        f"- Score: {document.get('score')} (source: {rel})",
        f"- Raw before caps: {document.get('raw')} (source: {rel})",
        f"- Lane: {document.get('lane')} (source: {rel})",
    ]
    caps = document.get("caps") or []
    out += [f"- Cap {c.get('name')}: {c.get('cap')}, {c.get('evidence')} (source: {rel})" for c in caps]
    if not caps:
        out.append(f"- Caps: none (source: {rel})")
    signals = document.get("signals") or {}
    ranked = sorted(
        signals.items(), key=lambda kv: (kv[1]["points"] / kv[1]["max"] if kv[1].get("max") else 0, kv[0])
    )
    for name, signal in ranked[:3]:
        shown = f"{signal.get('points')}/{signal.get('max')}, {signal.get('evidence')}"
        out.append(f"- Lowest signal {name}: {shown} (source: {rel})")
    return out


def _not_done(story: Story, document: dict | None) -> list[str]:
    rel = story.rel(story.qa("confidence.json"))
    if document is not None:
        items = [(name, rel) for name in document.get("missing") or []]
    else:
        items = [(name, story.rel(story.qa(name))) for name in EXPECTED if not story.qa(name).exists()]
    return [f"- Missing input: {name} (source: {source})" for name, source in items] + [
        "- End-to-end test not executed"
    ]


def _links(story: Story, evidence: Path) -> list[str]:
    central = story.central
    paths = [
        story.path,
        story.design(),
        story.design("findings.md"),
        central / "docs" / "design" / story.feature / f"{story.story_id}.dsl",
        central / "docs" / "changes" / story.feature / f"{story.story_id}-change-note.md",
    ]
    folder = central / "docs" / "qa" / story.feature
    if folder.is_dir():
        for item in sorted(folder.glob(f"{story.story_id}-*")):
            paths += sorted(p for p in item.rglob("*") if p.is_file()) if item.is_dir() else [item]
    links = sorted({story.rel(p) for p in paths if p.is_file() and p != evidence})
    return [f"- [{link}]({link})" for link in links]


def render(story: Story, evidence: Path) -> str:
    text = story.path.read_text(encoding="utf-8")
    document, why = read_json(story.qa("confidence.json"))
    parts = {
        "Story": _story(story, text),
        "Design": _design(story, text),
        "Build": _build(story),
        "Verification": _verification(story),
        "Security": _security(story),
        "Blast radius": _blast(story),
        "Confidence": _confidence(story, document, why),
        "What was NOT done": _not_done(story, document),
        "Links": _links(story, evidence),
    }
    lines = [f"# Evidence: {story.story_id}", ""]
    for name in SECTIONS:
        lines += [f"## {name}", *parts[name], ""]
    return "\n".join(lines)


def add_arguments(parser) -> None:
    parser.add_argument("story_id", help="the story id, e.g. S-010")


def run(args) -> int:
    try:
        story = state_check.find_story(Path(args.central), args.story_id)
    except FileNotFoundError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    path = story.qa("evidence.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    from baton.doclint import to_ascii

    path.write_text(to_ascii(render(story, path)), encoding="utf-8")
    if args.json:
        print(json.dumps({"story": story.story_id, "path": story.rel(path), "sections": list(SECTIONS)}))
    else:
        print(story.rel(path))
    return 0
