"""`baton context check <story | feature>`: is the context good enough for this story (context-map.md section
5.2), or is the system understood well enough to accept this feature (section 10.5)?

Seeds are looked up, never inferred: collections, topics and endpoints from dependencies.yaml and domain words
from the word table, as they are written in the story's title and ACs. The scope is the modules that touch a
seed, widened two hops through shared resources. The manifest says what the architect loads; the gaps go into
the story's `## Open questions`, phrased for the person who can answer them.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from baton import state_check
from baton.context import branch_points as bp
from baton.context import docs
from baton.context import domain as dm
from baton.context import score as sc
from baton.context.product import MAP_JSON, Module, Repo, Settings

TAG = "[context]"


def _resources(module: Module) -> set[str]:
    return {str(e.get("to")) for e in module.edges}


def _phrase(word: str) -> re.Pattern:
    parts = [re.escape(p) for p in re.split(r"[\s_\-]+", word.strip()) if p]
    return re.compile(r"(?i)\b" + r"[\s_\-]*".join(parts) + r"s?\b")


def seeds_of(text: str, repos: list[Repo], domain: dm.Domain) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {"collections": set(), "topics": set(), "endpoints": set(), "words": set()}
    for repo in repos:
        for edge in repo.edges:
            target = str(edge.get("to", ""))
            kind, _, name = target.partition(":")
            if kind == "collection" and _phrase(name).search(text):
                found["collections"].add(target)
            elif kind in ("topic", "queue") and re.search(rf"(?i)\b{re.escape(name)}\b", text):
                found["topics"].add(target)
            elif kind == "endpoint":
                path = name.split(" ", 1)[-1]
                if "${" not in path and len(path) > 1 and path in text:
                    found["endpoints"].add(target)
    for word in domain.words:
        if _phrase(word.word).search(text):
            found["words"].add(word.word)
    return {k: sorted(v) for k, v in found.items()}


def scope_of(
    repos: list[Repo], seeds: dict[str, list[str]], hops: int = 2
) -> tuple[list[Module], list[Module]]:
    """(the modules that touch a seed, those plus every module within `hops` shared resources of them)."""
    modules = [m for r in repos for m in r.modules.values() if m.sources]
    wanted = set(seeds["collections"] + seeds["topics"] + seeds["endpoints"])
    changed = [m for m in modules if _resources(m) & wanted]
    scope = {m.key: m for m in changed}
    frontier = list(changed)
    for _ in range(hops):
        reach = set().union(*(_resources(m) for m in frontier)) if frontier else set()
        frontier = [m for m in modules if m.key not in scope and _resources(m) & reach]
        scope.update({m.key: m for m in frontier})
    return changed, sorted(scope.values(), key=lambda m: m.key)


def gate(
    status: dict, changed: list[Module], scope: list[Module], track: str, light_open: int, feature: str
) -> tuple[list[dict], dict[str, str]]:
    """Gate 0 (contracts/context-map.md section 10.5): every area the work changes must be understood well
    enough for its track, and the systems at their edges named. Areas within two hops are listed, open.
    Returns the gaps and, per changed area, the status it had, so the state gate can tell if it moved."""
    from baton.context import understanding as us

    changed_keys = {m.key for m in changed}
    gaps: list[dict] = []
    seen: dict[str, str] = {}

    def gap(kind: str, ask: str, question: str, blocking: bool, **extra) -> None:
        gaps.append({"kind": kind, "ask": ask, "question": question, "blocking": blocking, **extra})

    for module in scope:
        area = status["areas"].get(module.key, {"status": "unexplored", "problems": [], "questions": []})
        mine = module.key in changed_keys
        if mine:
            seen[module.key] = area["status"]
        if area["status"] == "understood":
            continue
        refused = us.accepts(area, track, light_open)
        blocking = mine and refused is not None
        gap(
            "not-understood",
            "TL",
            f"{module.key} is {refused or area['status']}. Run /build-context-map focus {feature}.",
            blocking,
            module=module.key,
        )
        for question in area["questions"]:
            if question["blocking"] and not question["answer"]:
                gap(
                    "question",
                    question["ask"],
                    f"{question['text']} ({question['id']} in {question['where']})",
                    blocking,
                    module=module.key,
                )
        for clash in area.get("contradictions", []):
            if not clash["resolved"]:
                gap(
                    "contradiction",
                    "TL",
                    f"{clash['text']} ({clash['id']} in {area['note']})",
                    blocking,
                    module=module.key,
                )
    if track != "spike":
        mine = {r for m in changed for _, r in us.facts(m)}
        for resource, problems in sorted(status["landscapeByResource"].items()):
            if resource in mine:
                gap("boundary-unknown", "TL", problems[0], True, resource=resource)
    return gaps, seen


def _covers(text: str, fields: list[str]) -> bool:
    flat = bp.normalize(text)
    return all(bp.normalize(f) in flat for f in fields)


def check(
    central: Path,
    story_id: str,
    repos: list[Repo],
    domain: dm.Domain,
    points: list[dict],
    settings: Settings,
    status: dict | None = None,
) -> dict:
    story = state_check.find_story(central, story_id)
    text = story.text()
    track = state_check.track_of(text) or "full"
    title = re.search(r"^#\s+(.+)$", text, re.M)
    seed_text = "\n".join(
        [title.group(1) if title else "", state_check.section(text, "Acceptance criteria") or ""]
    )
    seeds = seeds_of(seed_text, repos, domain)
    changed, scope = scope_of(repos, seeds)
    changed_keys = {m.key for m in changed}
    by_repo = {r.name: r for r in repos}
    blocking_kinds = (
        set() if track == "spike" else set(settings.blocking.get(track, settings.blocking["full"]))
    )
    gaps: list[dict] = []

    def gap(kind: str, ask: str, question: str, **extra) -> None:
        gaps.append(
            {"kind": kind, "ask": ask, "question": question, "blocking": kind in blocking_kinds, **extra}
        )

    words = {w.word: w for w in domain.words}
    for word in seeds["words"]:
        if not words[word].defined:
            gap(
                "undefined-word",
                "PO",
                f'What does "{word}" mean in this product? The story uses it and '
                "profile/domain.md has no confirmed definition.",
            )
    if not changed:
        gap(
            "no-seed",
            "TL",
            "Which module will this story change? Its title and ACs name no collection, topic "
            "or endpoint the extractors know.",
        )
    pages, profiles, rules, now = [], [], set(), datetime.now(UTC)
    for module in scope:
        repo = by_repo[module.repo]
        state = sc.wiki_state(central, repo, module.name)
        pages.append(
            {"module": module.key, "page": f"docs/wiki/{repo.name}/{module.name}.md", "state": state}
        )
        if state != "verified":
            gap(
                "page-unverified",
                "TL",
                f"The wiki page for {module.key} is {state} at {repo.commit}; run "
                f"`baton wiki {repo.name}` and `baton verify {repo.name}` before design.",
                module=module.key,
            )
        for name, kinds in sorted(sc.collections_of(module.edges).items()):
            state = sc.profile_state(central, name, settings.max_age_days, now)
            if state == "profiled":
                profiles.append(f"docs/data-profile/{name}.json")
            elif "WRITES_COLLECTION" in kinds and module.key in changed_keys:
                gap(
                    "unprofiled-write",
                    "TL",
                    f"{module.key} writes collection {name}, which has no current data "
                    "profile: run `baton profile` for it, or say the ACs do not depend on its data.",
                    module=module.key,
                )
            else:
                gap(
                    "unprofiled-collection",
                    "TL",
                    f"Collection {name} ({module.key}) has no current data profile.",
                    module=module.key,
                )
        unresolved = set(repo.unresolved)
        for edge in module.edges:
            if str(edge.get("to")) in unresolved:
                prov = edge.get("provenance") or {}
                gap(
                    "unresolved-edge-out",
                    "TL",
                    f"{edge.get('from')} calls {edge.get('to')}, which the "
                    "extractors could not resolve. Which system is it?",
                    module=module.key,
                    at=f"{repo.name}/{prov.get('file')}:{prov.get('line')}",
                )
        for point in points:
            if f"{point['repo']}/{point['module']}" != module.key:
                continue
            if point["status"] == "mapped":
                rules.add(point["rule"])
                continue
            if _covers(seed_text, point["fields"]):
                continue
            kind = (
                "undocumented-branch-in-changed-module"
                if module.key in changed_keys
                else "undocumented-branch"
            )
            proposed = (
                f" Proposed: {point['proposed']} ({point['confidence']})." if point.get("proposed") else ""
            )
            gap(
                kind,
                "PO",
                f"What rule decides `{point['predicate']}`? ({point['id']}, fields: "
                f"{', '.join(point['fields'])}).{proposed}",
                module=module.key,
                at=f"{point['repo']}/{point['file']}:{point['line']}",
            )
    for repo_name in sorted({m.repo for m in scope}):
        if not by_repo[repo_name].owner:
            gap(
                "owner-unknown",
                "TL",
                f"Who owns {repo_name}? There is no CODEOWNERS and no Owner in profile/project.md.",
            )
    for rule in domain.confirmed_rules():
        if any(bp.normalize(f) in bp.normalize(seed_text) for f in rule.fields):
            rules.add(rule.id)
    from baton.context import understanding as us

    found, seen = gate(
        status or us.grade_all(central, repos, domain, points),
        changed,
        scope,
        track,
        settings.light_open_questions,
        story.feature,
    )
    gaps += found
    blocking = [g for g in gaps if g["blocking"]]
    return {
        "story": story.story_id,
        "feature": story.feature,
        "track": track,
        "gate": seen,
        "lightOpenQuestions": settings.light_open_questions,
        "path": story.rel(story.path),
        "local": story.ref is None,
        "seeds": seeds,
        "changed": sorted(changed_keys),
        "scope": [m.key for m in scope],
        "load": {
            "pages": pages,
            "rules": sorted(rules),
            "profiles": profiles,
            "graph": [e for m in scope for e in _edge_lines(m)],
            "documents": [
                {"source": d["source"], "file": d["file"]}
                for d in docs.mentions(central, repos, domain)
                if set(d["modules"]) & {m.key for m in scope} or set(d["words"]) & set(seeds["words"])
            ],
            **_notes(central, [m.key for m in scope]),
        },
        "gaps": gaps,
        "blocking": len(blocking),
    }


def _edge_lines(module: Module) -> list[str]:
    return [f"{e.get('from')} {e.get('kind')} {e.get('to')}" for e in module.edges]


def manifest(result: dict) -> str:
    load = result["load"]
    lines = [
        f"# {result['story']} context manifest",
        "",
        f"Generated by baton context check. Track: {result['track']}. Blocking gaps: {result['blocking']}.",
        "The architect and the review lenses load exactly what is listed under Load.",
        "",
        "## Seeds",
        "",
    ]
    for kind, values in result["seeds"].items():
        lines.append(f"- {kind}: {', '.join(values) if values else '(none)'}")
    lines += [
        "",
        "## Scope",
        "",
        f"- changed: {', '.join(result['changed']) or '(none found)'}",
        f"- within two hops: {', '.join(result['scope']) or '(none)'}",
        "",
        "## Load",
        "",
    ]
    lines += [f"- page: {p['page']} ({p['state']})" for p in load["pages"]]
    lines += [f"- rule: {r} (profile/domain.md)" for r in load["rules"]]
    lines += [f"- data profile: {p}" for p in load["profiles"]]
    lines += [f"- edge: {e}" for e in load["graph"]]
    lines += [f"- document: {d['file']} (from {d['source']})" for d in load.get("documents", [])]
    lines += [f"- understanding: {n}" for n in load.get("notes", [])]
    lines += [f"- flow: {f}" for f in load.get("flows", [])]
    if not any(load.values()):
        lines.append("- nothing: the story reaches no known module")
    lines += ["", "## Gaps", ""]
    for item in result["gaps"]:
        where = f" ({item['at']})" if item.get("at") else ""
        lines.append(
            f"- {'blocking' if item['blocking'] else 'open'} - {sc.ASK[item['ask']]}: {item['question']}"
            f"{where}"
        )
    if not result["gaps"]:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def update_questions(text: str, gaps: list[dict]) -> str:
    """Replace this tool's earlier `## Open questions` lines with the current gaps; a human's lines stay."""
    wanted = [
        f"- {TAG} {sc.ASK[g['ask']]}: {g['question']}{' (blocks Ready)' if g['blocking'] else ''}"
        for g in gaps
    ]
    match = re.search(r"^##[ \t]+Open questions\b[^\n]*\n", text, re.M | re.I)
    if match is None:
        if not wanted:
            return text
        return text.rstrip("\n") + "\n\n## Open questions\n" + "\n".join(wanted) + "\n"
    rest = text[match.end() :]
    following = re.search(r"^##[ \t]", rest, re.M)
    body = rest[: following.start()] if following else rest
    kept = [ln for ln in body.splitlines() if not ln.startswith(f"- {TAG} ")]
    while kept and not kept[-1].strip():
        kept.pop()
    new_body = "\n".join(kept + wanted)
    new_body = (new_body + "\n" if new_body else "") + ("\n" if following else "")
    return text[: match.end()] + new_body + (rest[following.start() :] if following else "")


def write(central: Path, result: dict, domain_score: float | None) -> list[str]:
    folder = central / "docs" / "design" / result["feature"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"{result['story']}-context"
    stem.with_suffix(".md").write_text(manifest(result), encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    wrote = [
        f"docs/design/{result['feature']}/{result['story']}-context.md",
        f"docs/design/{result['feature']}/{result['story']}-context.json",
    ]
    if result["local"]:
        path = central / result["path"]
        text = path.read_text(encoding="utf-8")
        updated = update_questions(text, result["gaps"])
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            wrote.append(result["path"])
        clarifications = len(re.findall(r"\bQ:", state_check.section(updated, "Clarifications") or ""))
    else:
        clarifications = 0
    map_path = central / MAP_JSON
    if map_path.is_file():
        data = json.loads(map_path.read_text(encoding="utf-8"))
        trend = [t for t in data.get("trend") or [] if t.get("story") != result["story"]]
        trend.append({"story": result["story"], "domain": domain_score, "clarifications": clarifications})
        data["trend"] = trend
        map_path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
        (central / "docs" / "context" / "context-map.md").write_text(sc.render(data), encoding="utf-8")
        wrote.append(MAP_JSON)
    return wrote


# --- features: is the system understood well enough to accept one? (section 10.5) ------------------------


def _notes(central: Path, keys: list[str]) -> dict[str, list[str]]:
    """The explorers' notes for these areas and the flows that pass through them, where they exist."""
    from baton.context import understanding as us

    names = [us.note_name(k) for k in keys]
    notes = [f"{us.AREAS}/{n}" for n in names if (central / us.AREAS / n).is_file()]
    flows = []
    folder = central / us.FLOWS
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        steps = us.sections(path.read_text(encoding="utf-8", errors="replace")).get("steps", [])
        if any(re.search(rf"^\d+\.\s+{re.escape(k)}\s", s.strip()) for k in keys for s in steps):
            flows.append(path.relative_to(central).as_posix())
    out: dict[str, list[str]] = {}
    if notes:
        out["notes"] = notes
    if flows:
        out["flows"] = flows
    if notes and (central / us.LANDSCAPE).is_file():
        out["landscape"] = [us.LANDSCAPE]
    return out


FEATURE_ID = re.compile(r"^F-\d+$")


def find_feature(central: Path, feature_id: str) -> Path:
    root = central / "docs" / "features"
    found = [
        p for p in sorted(root.glob("*.md")) if p.stem == feature_id or p.stem.startswith(feature_id + "-")
    ]
    if not found:
        raise FileNotFoundError(f"no feature {feature_id} under docs/features/")
    if len(found) > 1:
        raise ValueError(f"{feature_id} is ambiguous: {', '.join(p.name for p in found)}")
    return found[0]


def check_feature(
    central: Path,
    feature_id: str,
    repos: list[Repo],
    domain: dm.Domain,
    points: list[dict],
    track: str = "full",
    light_open: int = 2,
    status: dict | None = None,
) -> dict:
    """The areas the feature changes must be understood, with the systems at their edges named; the areas
    within two hops are listed, and their gaps are open, not blocking."""
    from baton.context import understanding as us

    path = find_feature(central, feature_id)
    text = path.read_text(encoding="utf-8", errors="replace")
    seeds = seeds_of(text, repos, domain)
    changed, scope = scope_of(repos, seeds)
    changed_keys = {m.key for m in changed}
    status = status or us.grade_all(central, repos, domain, points)
    gaps: list[dict] = []

    def gap(kind: str, ask: str, question: str, blocking: bool, **extra) -> None:
        gaps.append({"kind": kind, "ask": ask, "question": question, "blocking": blocking, **extra})

    if not changed:
        gap(
            "no-seed",
            "TL",
            f"Which modules will {feature_id} change? Its note names no collection, topic or endpoint the "
            "extractors know.",
            True,
        )
    words = {w.word: w for w in domain.words}
    for word in seeds["words"]:
        if not words[word].defined:
            gap("undefined-word", "PO", f'What does "{word}" mean? {feature_id} uses it undefined.', True)
    found, seen = gate(status, changed, scope, track, light_open, feature_id)
    gaps += found
    blocking = [g for g in gaps if g["blocking"]]
    return {
        "feature": feature_id,
        "track": track,
        "gate": seen,
        "path": path.relative_to(central).as_posix(),
        "seeds": seeds,
        "changed": sorted(changed_keys),
        "scope": [m.key for m in scope],
        "load": _notes(central, [m.key for m in scope]),
        "gaps": gaps,
        "blocking": len(blocking),
    }


def feature_manifest(result: dict) -> str:
    load = result["load"]
    lines = [
        f"# {result['feature']} understanding manifest",
        "",
        f"Generated by baton context check. Blocking gaps: {result['blocking']}. The feature is accepted for "
        "story drafting only with none.",
        "",
        "## Scope",
        "",
        f"- changed: {', '.join(result['changed']) or '(none found)'}",
        f"- within two hops: {', '.join(result['scope']) or '(none)'}",
        "",
        "## Load",
        "",
    ]
    lines += [f"- understanding: {n}" for n in load.get("notes", [])]
    lines += [f"- flow: {f}" for f in load.get("flows", [])]
    lines += [f"- landscape: {f}" for f in load.get("landscape", [])]
    if not load:
        lines.append("- nothing yet: no area of this feature has been explored")
    lines += ["", "## Gaps", ""]
    for item in result["gaps"]:
        state = "blocking" if item["blocking"] else "open"
        lines.append(f"- {state} - {sc.ASK[item['ask']]}: {item['question']}")
    if not result["gaps"]:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def write_feature(central: Path, result: dict) -> list[str]:
    folder = central / "docs" / "design" / result["feature"]
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"{result['feature']}-context"
    stem.with_suffix(".md").write_text(feature_manifest(result), encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return [
        f"docs/design/{result['feature']}/{result['feature']}-context.md",
        f"docs/design/{result['feature']}/{result['feature']}-context.json",
    ]
