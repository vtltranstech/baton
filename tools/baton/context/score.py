"""`baton context score`: coverage per layer and per module, readiness statements, gaps (section 5.1 and 7).

A layer's score is covered units over units, unweighted. Layers are never averaged into one number: a 0.9
structural and a 0.2 domain must not read as 0.55.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from baton import miniyaml
from baton.context import docs
from baton.context import domain as dm
from baton.context.product import DRAFTS_FILE, MAP_JSON, MAP_MD, POINTS_FILE, Module, Repo, Settings
from baton.extract.repos import UNKNOWN

LAYERS = ("structural", "behavioural", "domain", "operational", "intent")
_RULE_TEST = re.compile(r"(?i)(?:^|_)ac\d|rule|(?:^|_)r\d+(?:_|$)")
_TEST_NAME = re.compile(r"@Test\b[^;{]*?\bvoid\s+(\w+)\s*\(|\b(?:it|test)\(\s*['\"`](.+?)['\"`]")
ASK = {"PO": "Product Owner", "TL": "Tech Lead"}
RAISE = {
    "structural": "run `baton wiki <repo>` then `baton verify <repo>`; name the systems behind unresolved "
    "edges in /onboard",
    "behavioural": "run `baton profile` for each unprofiled collection; name a rule or AC in at least one "
    "test per module",
    "domain": "map each undocumented branch point to a confirmed rule (`rule:` in "
    "profile/branch-points.yaml) or confirm a draft in profile/domain-drafts.md; ingest the old documents "
    "(`baton context ingest`) so their rules and words become drafts",
    "operational": "fill owners in profile/project.md or add CODEOWNERS; install the sensors; "
    "name the test env",
    "intent": "give each feature note an Outcome and a Scope; give each open decision an owner and a story "
    "or ADR",
}


def ratio(covered: int, total: int) -> float | None:
    return round(covered / total, 2) if total else None


def _git_head(central: Path) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(central), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    return done.stdout.strip() if done.returncode == 0 else UNKNOWN


def wiki_state(central: Path, repo: Repo, module: str) -> str:
    """`verified` (at the repo's commit), `stale`, `unverified` or `missing`."""
    path = central / "docs" / "wiki" / repo.name / f"{module.replace('/', '.')}.md"
    if not path.is_file():
        path = central / "docs" / "wiki" / repo.name / f"{module}.md"
    if not path.is_file():
        return "missing"
    text = path.read_text(encoding="utf-8", errors="replace")
    end = text.find("\n---\n", 3)
    try:
        front = miniyaml.loads(text[4 : end + 1]) if text.startswith("---\n") and end > 0 else {}
    except ValueError:
        front = {}
    if not isinstance(front, dict) or front.get("verified") is not True:
        return "unverified"
    return (
        "verified" if repo.commit != UNKNOWN and str(front.get("generatedFrom")) == repo.commit else "stale"
    )


def profile_state(central: Path, collection: str, max_age_days: int, now: datetime) -> str:
    """`profiled`, `stale`, `unprofiled` or `missing` for docs/data-profile/<collection>.json."""
    path = central / "docs" / "data-profile" / f"{collection}.json"
    if not path.is_file():
        return "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sampled = datetime.fromisoformat(str(data["sampledAt"]).replace("Z", "+00:00"))
    except (ValueError, KeyError, TypeError):
        return "unprofiled"
    if data.get("unprofiled"):
        return "unprofiled"
    return "profiled" if (now - sampled).days <= max_age_days else "stale"


def rule_tests(module: Module) -> list[str]:
    names = []
    for path in module.tests:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _TEST_NAME.finditer(text):
            name = match.group(1) or match.group(2)
            if _RULE_TEST.search(name):
                names.append(f"{path.stem}.{name}")
        if "@DisplayName" in text:
            names.append(f"{path.stem} @DisplayName")
    return names


def collections_of(edges: list[dict]) -> dict[str, set[str]]:
    """collection -> the edge kinds that touch it (READS_COLLECTION / WRITES_COLLECTION)."""
    out: dict[str, set[str]] = {}
    for edge in edges:
        target = str(edge.get("to", ""))
        if target.startswith("collection:"):
            out.setdefault(target.removeprefix("collection:"), set()).add(str(edge.get("kind")))
    return out


def _feature_complete(text: str) -> list[str]:
    from baton.state_check import section

    missing = []
    summary = section(text, "Outcome") or section(text, "Problem") or section(text, "Business summary")
    if not (summary or "").strip() or (summary or "").strip().startswith(("What is", "<")):
        missing.append("business summary (## Outcome)")
    scope = section(text, "Scope")
    if not (scope or "").strip() or (scope or "").strip() == "- ...":
        missing.append("scope (## Scope for this release)")
    return missing


def compute(
    central: Path,
    repos: list[Repo],
    domain: dm.Domain,
    points: list[dict],
    settings: Settings,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(UTC)
    gaps: list[dict] = []
    by_module: dict[str, dict] = {}

    def gap(layer: str, module: str, kind: str, text: str, ask: str, **extra) -> None:
        gaps.append({"layer": layer, "module": module, "kind": kind, "text": text, "ask": ask, **extra})

    # structural
    modules = verified = edges = unresolved = 0
    for repo in repos:
        if not repo.extracted:
            gap(
                "structural",
                repo.name,
                "not-extracted",
                f"{repo.name} has no entry in profile/dependencies.yaml: run /onboard (baton onboard)",
                "TL",
            )
        bad = set(repo.unresolved)
        for name, module in sorted(repo.modules.items()):
            if not module.sources:
                continue
            modules += 1
            state = wiki_state(central, repo, name)
            verified += state == "verified"
            if state != "verified":
                gap(
                    "structural",
                    module.key,
                    "page-unverified",
                    f"the wiki page for {module.key} is {state} at commit {repo.commit}: run "
                    f"`baton wiki {repo.name}` and `baton verify {repo.name}`",
                    "TL",
                )
            loose = [e for e in module.edges if str(e.get("to")) in bad]
            for edge in loose:
                prov = edge.get("provenance") or {}
                gap(
                    "structural",
                    module.key,
                    "unresolved-edge",
                    f"{edge.get('from')} -> {edge.get('to')} could not be resolved: which system is it?",
                    "TL",
                    file=f"{repo.name}/{prov.get('file')}",
                    line=prov.get("line"),
                )
            by_module[module.key] = {
                "structural": ratio(
                    (state == "verified") + len(module.edges) - len(loose), 1 + len(module.edges)
                ),
                "page": state,
                "edges": len(module.edges),
                "unresolved": len(loose),
            }
        edges += len(repo.edges)
        unresolved += sum(str(e.get("to")) in bad for e in repo.edges)
    structural = {
        "score": ratio(verified + edges - unresolved, modules + edges),
        "modules": modules,
        "verified": verified,
        "edges": edges,
        "unresolved": unresolved,
    }

    # behavioural
    collections: dict[str, set[str]] = {}
    for repo in repos:
        for name, kinds in collections_of(repo.edges).items():
            collections.setdefault(name, set()).update(kinds)
    states = {name: profile_state(central, name, settings.max_age_days, now) for name in collections}
    for name, state in sorted(states.items()):
        if state != "profiled":
            gap(
                "behavioural",
                f"collection:{name}",
                "unprofiled-collection",
                f"collection {name} has no current data profile ({state}): run `baton profile` for it",
                "TL",
            )
    with_tests = 0
    for repo in repos:
        for _, module in sorted(repo.modules.items()):
            if not module.sources:
                continue
            named = rule_tests(module)
            with_tests += bool(named)
            touched = collections_of(module.edges)
            fresh = sum(states.get(c) == "profiled" for c in touched)
            by_module[module.key]["behavioural"] = ratio(bool(named) + fresh, 1 + len(touched))
            if not named:
                gap(
                    "behavioural",
                    module.key,
                    "no-rule-test",
                    f"no test in {module.key} names a rule or AC (ac1_..., rule..., @DisplayName)",
                    "TL",
                )
    profiled = sum(s == "profiled" for s in states.values())
    behavioural = {
        "score": ratio(profiled + with_tests, len(collections) + modules),
        "collections": len(collections),
        "profiled": profiled,
        "modulesWithRuleTests": with_tests,
    }

    # domain
    for point in points:
        key = f"{point['repo']}/{point['module']}"
        entry = by_module.setdefault(key, {})
        entry["branchPoints"] = entry.get("branchPoints", 0) + 1
        entry["mapped"] = entry.get("mapped", 0) + (point["status"] == "mapped")
        if point["status"] != "mapped":
            proposed = (
                f"; proposed {point['proposed']} ({point['confidence']})" if point.get("proposed") else ""
            )
            gap(
                "domain",
                key,
                f"{point['status']}-branch",
                f"what rule decides `{point['predicate']}`? (fields: {', '.join(point['fields'])}{proposed})",
                "PO",
                file=f"{point['repo']}/{point['file']}",
                line=point["line"],
                id=point["id"],
            )
    for entry in by_module.values():
        if entry.get("branchPoints"):
            entry["domain"] = ratio(entry["mapped"], entry["branchPoints"])
    for word in domain.words:
        if not word.defined:
            gap(
                "domain",
                "words",
                "undefined-word",
                f'what does "{word.word}" mean in this product? (no confirmed definition in '
                "profile/domain.md Domain words)",
                "PO",
            )
    with_test = 0
    test_names = " ".join(n for r in repos for m in r.modules.values() for n in rule_tests(m))
    for rule in domain.rules:
        tested = (
            "test" in rule.source.lower()
            or "data-check" in rule.source.lower()
            or bool(re.search(rf"(?i)(?:^|[._\s]){rule.id}(?:_|\b)", test_names))
        )
        with_test += tested
        if not rule.indexable:
            gap(
                "domain",
                "rules",
                "rule-not-indexable",
                f"{rule.id} has no `fields:` line, so no branch point "
                f"can map to it (profile/domain.md line {rule.line})",
                "PO",
            )
        elif rule.is_draft:
            gap(
                "domain",
                "rules",
                "rule-draft",
                f"{rule.id} has no `source:` or is not `confirmed: true` "
                f"(profile/domain.md line {rule.line})",
                "PO",
            )
    mapped = sum(p["status"] == "mapped" for p in points)
    domain_layer = {
        "score": ratio(mapped, len(points)),
        "branchPoints": len(points),
        "mapped": mapped,
        "undocumented": sum(p["status"] == "undocumented" for p in points),
        "contested": sum(p["status"] == "contested" for p in points),
        "words": len(domain.words),
        "wordsDefined": sum(w.defined for w in domain.words),
        "rules": len(domain.rules),
        "rulesWithTest": with_test,
    }

    # operational
    project = central / "profile" / "project.md"
    env = (
        re.search(r"^\|\s*test\.env\s*\|\s*([^|]*)\|", project.read_text(encoding="utf-8"), re.M)
        if project.is_file()
        else None
    )
    env_known = bool(env and env.group(1).strip() and not env.group(1).strip().startswith("<"))
    passed = int(env_known)
    owners = sensors = 0
    for repo in repos:
        row = repo.stack
        for column in ("build cmd", "test cmd"):
            known = row.get(column, UNKNOWN) not in (UNKNOWN, "")
            passed += known
            if not known:
                gap(
                    "operational",
                    repo.name,
                    "command-unknown",
                    f"the {column} of {repo.name} is not detected: which command does CI run?",
                    "TL",
                )
        owners += bool(repo.owner)
        if not repo.owner:
            gap(
                "operational",
                repo.name,
                "owner-unknown",
                f"who owns {repo.name}? (no CODEOWNERS and no Owner column in profile/project.md)",
                "TL",
            )
        installed = row.get("archunit") == "installed" or any(
            (repo.path / f).is_file() for f in ("eslint.config.js", "eslint.config.mjs", ".eslintrc.json")
        )
        sensors += installed
        if not installed:
            gap(
                "operational",
                repo.name,
                "sensors-missing",
                f"{repo.name} has no ArchUnit or ESLint sensor installed (profile/stack-detected.md)",
                "TL",
            )
    if not env_known:
        gap(
            "operational",
            "product",
            "test-env-unknown",
            "which environment do tests run against? (test.env in profile/project.md)",
            "TL",
        )
    passed += owners + sensors
    operational = {
        "score": ratio(passed, 4 * len(repos) + 1),
        "repos": len(repos),
        "ownersKnown": owners,
        "sensorsInstalled": sensors,
        "testEnv": "named" if env_known else "missing",
    }

    # intent
    features = sorted((central / "docs" / "features").glob("F-*.md"))
    complete = 0
    for path in features:
        missing = _feature_complete(path.read_text(encoding="utf-8", errors="replace"))
        complete += not missing
        if missing:
            gap(
                "intent",
                path.stem,
                "feature-incomplete",
                f"docs/features/{path.name} has no {' and no '.join(missing)}",
                "PO",
            )
    owned = sum(d.owned for d in domain.decisions)
    for decision in domain.decisions:
        if not decision.owned:
            gap(
                "intent",
                "decisions",
                "decision-unowned",
                f"open decision without an owner and a story or ADR: "
                f"{decision.text} (profile/domain.md line {decision.line})",
                "PO",
            )
    intent = {
        "score": ratio(complete + owned, len(features) + len(domain.decisions)),
        "features": len(features),
        "featuresComplete": complete,
        "openDecisions": len(domain.decisions),
        "owned": owned,
    }

    documents = docs.mentions(central, repos, domain)
    for document in documents:
        for key in document["modules"]:
            by_module.setdefault(key, {}).setdefault("documents", []).append(document["source"])
    for skipped in docs.skipped(central):
        gap(
            "domain",
            "documents",
            "document-unreadable",
            f"{skipped['source']}: not read: {skipped['reason']}",
            "TL",
        )
    readiness, interview = _readiness(by_module, points)
    return {
        "computedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": _git_head(central),
        "repos": {r.name: r.commit for r in repos},
        "layers": {
            "structural": structural,
            "behavioural": behavioural,
            "domain": domain_layer,
            "operational": operational,
            "intent": intent,
        },
        "byModule": dict(sorted(by_module.items())),
        "readiness": readiness,
        "interviewOrder": interview,
        "gaps": gaps,
        "drafts": _count_drafts(central),
        "documents": documents,
        "trend": [],
    }


def _readiness(by_module: dict[str, dict], points: list[dict]) -> tuple[list[dict], list[str]]:
    """Per module: ready for light stories when no edge in it is unresolved; for full stories when, besides,
    every branch point in it is mapped. As far as the code can tell (section 11)."""
    out, weight = [], {}
    for key, entry in sorted(by_module.items()):
        if "page" not in entry:
            continue
        open_points = entry.get("branchPoints", 0) - entry.get("mapped", 0)
        edges = (
            [f"{entry['unresolved']} unresolved edge{'s' if entry['unresolved'] != 1 else ''}"]
            if entry.get("unresolved")
            else []
        )
        branches = (
            [
                f"domain {entry.get('domain')}: {open_points} undocumented branch point"
                f"{'s' if open_points != 1 else ''}"
            ]
            if open_points
            else []
        )
        out.append({"scope": key, "track": "light", "ready": not edges, "why": "; ".join(edges)})
        out.append(
            {
                "scope": key,
                "track": "full",
                "ready": not (edges or branches),
                "why": "; ".join(branches + edges),
            }
        )
        weight[key] = open_points * (entry.get("edges", 0) + 1)
    interview = [k for k in sorted(weight, key=lambda k: (-weight[k], k)) if weight[k]]
    return out, interview


def _count_drafts(central: Path) -> dict:
    path = central / DRAFTS_FILE
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {
        "file": DRAFTS_FILE,
        "awaiting": len(re.findall(r"(?mi)^confirmed:\s*false\s*$", text)),
        "confirmedNotMoved": len(re.findall(r"(?mi)^confirmed:\s*true\s*$", text)),
    }


def statements(data: dict) -> list[str]:
    rows = data["readiness"]
    full = [r["scope"] for r in rows if r["track"] == "full" and r["ready"]]
    light = [r["scope"] for r in rows if r["track"] == "light" and r["ready"] and r["scope"] not in full]
    lines = []
    if full:
        lines.append(f"Ready for light and full stories in {', '.join(full)}.")
    for scope in light:
        why = next(r["why"] for r in rows if r["scope"] == scope and r["track"] == "full")
        lines.append(f"Ready for light stories in {scope}; not for full stories: {why}.")
    for row in rows:
        if row["track"] == "light" and not row["ready"]:
            why = next(r["why"] for r in rows if r["scope"] == row["scope"] and r["track"] == "full")
            lines.append(f"Not ready for stories in {row['scope']}: {why}.")
    if not rows:
        lines.append("No modules found yet: run /onboard so the extractors can list them.")
    lines.append(
        "Ready as far as the code can tell: rules that never reached code or tests show up only as "
        "findings and clarifications."
    )
    return lines


def render(data: dict) -> str:
    layers = data["layers"]

    def covered(name: str) -> str:
        layer = layers[name]
        if name == "structural":
            return (
                f"{layer['verified']}/{layer['modules']} pages verified, "
                f"{layer['edges'] - layer['unresolved']}/{layer['edges']} edges resolved"
            )
        if name == "behavioural":
            return (
                f"{layer['profiled']}/{layer['collections']} collections profiled, "
                f"{layer['modulesWithRuleTests']}/{layers['structural']['modules']} modules with a rule test"
            )
        if name == "domain":
            return (
                f"{layer['mapped']}/{layer['branchPoints']} branch points mapped, "
                f"{layer['wordsDefined']}/{layer['words']} words defined, "
                f"{layer['rulesWithTest']}/{layer['rules']} rules tested"
            )
        if name == "operational":
            return (
                f"{layer['ownersKnown']}/{layer['repos']} owners, {layer['sensorsInstalled']}/"
                f"{layer['repos']} sensors, test env {layer['testEnv']}"
            )
        return (
            f"{layer['featuresComplete']}/{layer['features']} features complete, {layer['owned']}/"
            f"{layer['openDecisions']} decisions owned"
        )

    source = {
        "structural": "docs/wiki/, profile/dependencies.yaml",
        "behavioural": "docs/data-profile/, the repos' tests",
        "domain": f"{POINTS_FILE}, profile/domain.md",
        "operational": "profile/stack-detected.md, profile/project.md",
        "intent": "docs/features/, profile/domain.md",
    }
    lines = [
        "# Context map",
        "",
        f"Generated by baton context score at {data['computedAt']} (central commit {data['commit']}; repos: "
        + ", ".join(f"{k} {v}" for k, v in data["repos"].items())
        + f"). Rendered from {MAP_JSON}; do not edit.",
        "",
        "## Readiness",
        "",
        *[f"- {line}" for line in statements(data)],
        "",
        "## Scorecard",
        "",
        "| Layer | Score | Covered | From |",
        "| --- | --- | --- | --- |",
    ]
    for name in LAYERS:
        score = layers[name]["score"]
        lines.append(f"| {name} | {'n/a' if score is None else score} | {covered(name)} | {source[name]} |")
    lines += ["", "Each layer stands alone; they are never averaged.", ""]
    known = data.get("understanding")
    if known:
        counts = known["counts"]
        lines += [
            "## System understanding",
            "",
            ("Understood: every area and the landscape. " if known["understood"] else "Not understood yet. ")
            + ", ".join(
                f"{counts[s]} {s}" for s in ("understood", "blocked", "incomplete", "stale", "unexplored")
            )
            + f"; landscape {known['landscape']}; {known['flows']} valid flows; {known['openQuestions']} "
            "blocking questions open (docs/context/understanding/status.md).",
            "",
        ]
    lines += ["## Trend", ""]
    if data["trend"]:
        lines += ["| Story | Domain score | Clarification questions |", "| --- | --- | --- |"]
        lines += [f"| {t['story']} | {t['domain']} | {t.get('clarifications', 0)} |" for t in data["trend"]]
    else:
        lines.append("No story checked yet (`baton context check <story>` adds a row).")
    lines += ["", "## Interview order", ""]
    lines += [f"{i}. {m}" for i, m in enumerate(data["interviewOrder"], 1)] or [
        "Nothing to ask about the code."
    ]
    lines += ["", "## Gaps by module", ""]
    groups: dict[str, list[dict]] = {}
    for item in data["gaps"]:
        groups.setdefault(item["module"], []).append(item)
    for module in sorted(groups):
        lines += [f"### {module}", ""]
        for item in groups[module]:
            where = f" ({item['file']}:{item['line']})" if item.get("file") else ""
            lines.append(f"- {ASK[item['ask']]}: {item['text']}{where}")
        lines.append("")
    if not groups:
        lines += ["None.", ""]
    lines += ["## Documents", ""]
    if data.get("documents"):
        lines += [
            "| Document | Kind | Modules | Collections, topics, endpoints | Domain words |",
            "| --- | --- | --- | --- | --- |",
        ]
        for d in data["documents"]:
            cells = [", ".join(d[k]) or "-" for k in ("modules", "resources", "words")]
            lines.append(
                f"| [{d['source']}]({d['file'].removeprefix('docs/context/')}) | {d['kind']} | "
                + " | ".join(cells)
                + " |"
            )
    else:
        lines.append(
            "None ingested (`baton context ingest --from <folder>` reads Confluence exports, Word, "
            "PowerPoint, Excel, Markdown, text and CSV)."
        )
    lines.append("")
    drafts = data["drafts"]
    lines += [
        "## Drafts awaiting confirmation",
        "",
        f"{drafts['awaiting']} in {drafts['file']}; {drafts['confirmedNotMoved']} confirmed and not yet "
        "moved into profile/domain.md.",
        "",
        "## How to raise a score",
        "",
    ]
    lines += [f"- {name}: {RAISE[name]}." for name in LAYERS]
    return "\n".join(lines) + "\n"


MODULES_DIR = "docs/context/modules"


def render_module(key: str, data: dict, points: list[dict]) -> str:
    """One module's context map: what is known about it and what is missing, each line citing its file."""
    entry = data["byModule"].get(key, {})
    repo, _, module = key.partition("/")
    own = [p for p in points if f"{p['repo']}/{p['module']}" == key]
    lines = [
        f"# Context map: {key}",
        "",
        f"Generated by baton context score at {data['computedAt']}; rendered from {MAP_JSON}. Do not edit.",
        "",
        "| Layer | Score |",
        "| --- | --- |",
    ]
    lines += [f"| {name} | {entry.get(name, 'n/a')} |" for name in ("structural", "behavioural", "domain")]
    ready = {r["track"]: r for r in data["readiness"] if r["scope"] == key}
    lines += ["", "## Readiness", ""]
    for track in ("light", "full"):
        if track in ready:
            row = ready[track]
            lines.append(f"- {track}: {'ready' if row['ready'] else 'not ready: ' + row['why']}")
    lines += [
        "",
        "## Wiki page",
        "",
        f"- docs/wiki/{repo}/{module}.md ({entry.get('page', 'missing')})",
        "",
        "## Rules in code",
        "",
    ]
    for point in own:
        rule = point["rule"] if point["status"] == "mapped" else point["status"]
        lines.append(
            f"- {point['id']} `{point['predicate']}` -> {rule} ({repo}/{point['file']}:{point['line']})"
        )
    if not own:
        lines.append("- no business branch points")
    lines += ["", "## Documents that mention it", ""]
    lines += [f"- {d}" for d in entry.get("documents", [])] or ["- none ingested"]
    lines += ["", "## Gaps", ""]
    own_gaps = [g for g in data["gaps"] if g["module"] == key]
    lines += [f"- {ASK[g['ask']]}: {g['text']}" for g in own_gaps] or ["- none"]
    return "\n".join(lines) + "\n"


def write(central: Path, data: dict, points: list[dict] | None = None) -> None:
    previous = central / MAP_JSON
    if previous.is_file():
        try:
            data["trend"] = json.loads(previous.read_text(encoding="utf-8")).get("trend") or []
        except ValueError:
            pass
    previous.parent.mkdir(parents=True, exist_ok=True)
    previous.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    (central / MAP_MD).write_text(render(data), encoding="utf-8")
    if points is None:
        return
    folder = central / MODULES_DIR
    folder.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for key, entry in data["byModule"].items():
        if "page" in entry:
            name = re.sub(r"[^A-Za-z0-9._-]+", "-", key.replace("/", "--")) + ".md"
            wanted.add(name)
            (folder / name).write_text(render_module(key, data, points), encoding="utf-8")
    for stale in folder.glob("*.md"):
        if stale.name not in wanted:
            stale.unlink()
