"""`baton context build`: branch points into profile/branch-points.yaml, drafts into profile/domain-drafts.md.

Nothing here writes a rule. A branch point's `rule:` is a human's (the build keeps it); a miner's draft stays
`confirmed: false` until a human edits it, and /ready or /onboard refresh moves it into domain.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from baton import state_check, stories
from baton.context import branch_points as bp
from baton.context import docs
from baton.context import domain as dm
from baton.context.product import (
    DRAFTS_FILE,
    Repo,
    Settings,
    load_points,
    point_key,
    stored_predicate,
    vocabulary,
    write_points,
)

_TEST_METHOD = re.compile(r"@Test\b[^;{]*?\bvoid\s+(\w+)\s*\(")
_DISPLAY = re.compile(r"@DisplayName\(\s*\"((?:\\.|[^\"\\])*)\"\s*\)")
_TS_TEST = re.compile(r"\b(?:it|test)\(\s*(['\"`])(.+?)\1")
_CLARIFICATION = re.compile(r"^-\s*(\S+)\s+Q:\s*(.+?)\s+A:\s*(.+)$")
_DRAFT_HEAD = re.compile(r"^### [RW]-draft-\d+", re.M)


def extract(repos: list[Repo], vocab: bp.Vocabulary, use_treesitter: bool = True) -> list[bp.Point]:
    points: list[bp.Point] = []
    for repo in repos:
        for name, module in sorted(repo.modules.items()):
            for path in module.sources:
                rel = path.relative_to(repo.path).as_posix()
                found = bp.points_in(
                    path.read_text(encoding="utf-8", errors="replace"), repo.name, rel, vocab, use_treesitter
                )
                for point in found:
                    point.module = name
                points += found
    return sorted(points, key=lambda p: (p.repo, p.file, p.line, p.kind, p.predicate))


def propose(fields: list[str], rules: list[dm.Rule]) -> tuple[str, str] | None:
    """The confirmed rule whose `fields:` overlap the point's most, as (rule id, `field-overlap n/m`)."""
    have = {bp.normalize(f) for f in fields}
    best = None
    for rule in rules:
        if not rule.indexable:
            continue
        want = {bp.normalize(f) for f in rule.fields}
        hits = len(have & want)
        if hits and (best is None or (hits / len(want), hits) > (best[0], best[1])):
            best = (hits / len(want), hits, rule.id, len(want))
    return (best[2], f"field-overlap {best[1]}/{best[3]}") if best else None


def merge(
    points: list[bp.Point], stored: list[dict] | None, domain: dm.Domain, commits: dict[str, str]
) -> list[dict]:
    """The points as written: a point the file already had keeps its id, its human `rule:` and `contested`."""
    previous = {point_key(e): e for e in stored or []}
    numbers = [int(m.group(1)) for e in stored or [] if (m := re.match(r"bp-(\d+)$", str(e.get("id"))))]
    next_id = max(numbers, default=0) + 1
    confirmed = {r.id for r in domain.confirmed_rules()}
    out = []
    for point in points:
        predicate = stored_predicate(point.predicate)
        old = previous.get((point.repo, point.file, " ".join(predicate.split())), {})
        if old.get("id"):
            ident = str(old["id"])
        else:
            ident, next_id = f"bp-{next_id:04d}", next_id + 1
        rule = old.get("rule") or None
        if old.get("status") == "contested":
            status = "contested"
        else:
            status = "mapped" if rule in confirmed else "undocumented"
        entry = {
            "id": ident,
            "repo": point.repo,
            "module": point.module,
            "file": point.file,
            "line": point.line,
            "kind": point.kind,
            "predicate": predicate,
            "fields": point.fields,
            "rule": rule,
            "status": status,
        }
        if status != "mapped":
            proposal = propose(point.fields, domain.confirmed_rules())
            if proposal:
                entry["proposed"], entry["confidence"] = proposal
        entry["provenance"] = {"extractor": point.extractor, "commit": commits.get(point.repo, "unknown")}
        out.append(entry)
    return out


@dataclass
class Draft:
    text: str
    fields: list[str]
    source: str
    module: str
    miner: str
    extra: list[str] = field(default_factory=list)
    kind: str = "rule"  # or "word": text is the word, definition its meaning
    definition: str = ""

    @property
    def key(self) -> str:
        return draft_key(self.source, next((e for e in self.extra if e.startswith("quote: ")), ""))


def draft_key(source: str, quote: str) -> str:
    """What makes a draft the same draft across builds: its source, and its quote when it has one (a human
    corrects the title, never the quote)."""
    return f"{source.strip()}|{quote.strip()}"


def _humanize(name: str) -> str:
    words = bp.split_words(name)
    words = [w for w in words if not re.fullmatch(r"ac\d+|test", w)] or words
    return " ".join(words).capitalize()


def _cited(domain: dm.Domain) -> str:
    return " ".join(r.source for r in domain.confirmed_rules())


def mine_tests(repos: list[Repo], vocab: bp.Vocabulary, domain: dm.Domain) -> list[Draft]:
    cited, drafts = _cited(domain), []
    for repo in repos:
        for name, module in sorted(repo.modules.items()):
            for path in module.tests:
                text = path.read_text(encoding="utf-8", errors="replace")
                if path.suffix == ".java":
                    found = list(_TEST_METHOD.finditer(text))
                    for index, match in enumerate(found):
                        method = match.group(1)
                        if re.search(rf"\b{re.escape(path.stem)}\.{re.escape(method)}\b", cited):
                            continue
                        end = found[index + 1].start() if index + 1 < len(found) else len(text)
                        display = _DISPLAY.search(text[max(0, match.start() - 200) : match.start() + 200])
                        fields = bp.fields_of(text[match.end() : end], vocab)
                        if fields:
                            drafts.append(
                                Draft(
                                    display.group(1) if display else _humanize(method),
                                    fields,
                                    f"test {path.stem}.{method}",
                                    f"{repo.name}/{name}",
                                    "test-name",
                                )
                            )
                else:
                    for match in _TS_TEST.finditer(text):
                        fields = bp.fields_of(match.group(2), vocab, read_strings=True)
                        label = f"test {path.name}: {match.group(2)}"
                        if fields and match.group(2) not in cited:
                            drafts.append(
                                Draft(match.group(2), fields, label, f"{repo.name}/{name}", "test-name")
                            )
    return drafts


def mine_points(points: list[dict]) -> list[Draft]:
    """One draft per module and field set, for undocumented points no confirmed rule is proposed for."""
    groups: dict[tuple[str, tuple[str, ...]], list[dict]] = {}
    for point in points:
        if point["status"] == "undocumented" and not point.get("proposed"):
            key = (f"{point['repo']}/{point['module']}", tuple(sorted(point["fields"])))
            groups.setdefault(key, []).append(point)
    drafts = []
    for (module, fields), members in sorted(groups.items()):
        first = members[0]
        where = [f"{p['repo']}/{p['file']}:{p['line']}" for p in members]
        drafts.append(
            Draft(
                f"Rule behind `{first['predicate']}`",
                list(fields),
                f"branch-point {', '.join(p['id'] for p in members)}",
                module,
                "branch-point",
                [f"at: {', '.join(where)}"],
            )
        )
    return drafts


def mine_clarifications(central: Path, vocab: bp.Vocabulary) -> list[Draft]:
    drafts = []
    for row in stories.collect(central):
        try:
            text = state_check.find_story(central, row["story"]).text()
        except (FileNotFoundError, OSError):
            continue
        for line in (state_check.section(text, "Clarifications") or "").splitlines():
            match = _CLARIFICATION.match(line.strip())
            if not match or "-> domain.md" in line:
                continue
            answer = match.group(3).strip()
            drafts.append(
                Draft(
                    answer,
                    bp.fields_of(match.group(2) + " " + answer, vocab),
                    f"{row['story']} clarification {match.group(1)}",
                    row["feature"],
                    "clarification",
                    [f"question: {match.group(2).strip()}"],
                )
            )
    return drafts


def mine_documents(central: Path, vocab: bp.Vocabulary, domain: dm.Domain) -> list[Draft]:
    """Word and rule drafts from the ingested sources (baton context ingest), grouped per document."""
    drafts = []
    for document in docs.sources(central):
        group = f"document {document['source']}"
        mined = docs.mine_document(central, document, vocab, domain)
        for word, definition, cite in mined.words:
            drafts.append(Draft(word, [], cite, group, "doc", [f"quote: {word}"], "word", definition))
        for sentence, fields, cite in mined.rules:
            drafts.append(
                Draft(sentence, fields, cite, group, "doc", [f"quote: {' '.join(sentence.split())}"])
            )
    return drafts


def kept_drafts(central: Path) -> list[str]:
    """Draft blocks a human set `confirmed: true` in and nobody has moved yet: kept word for word."""
    path = central / DRAFTS_FILE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    starts = [m.start() for m in _DRAFT_HEAD.finditer(text)]
    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = re.split(r"(?m)^#{1,2} ", text[start:end][4:])[0]
        block = "### " + block.rstrip() + "\n"
        if re.search(r"(?mi)^confirmed:\s*true\s*$", block):
            blocks.append(block)
    return blocks


def render_drafts(drafts: list[Draft], kept: list[str]) -> str:
    kept_keys = set()
    for block in kept:
        source = re.search(r"(?m)^source:\s*(.+)$", block)
        quote = re.search(r"(?m)^quote: .+$", block)
        kept_keys.add(draft_key(source.group(1) if source else "", quote.group(0) if quote else ""))
    lines = [
        "# Domain drafts",
        "",
        "Generated by baton context build (contracts/context-map.md section 4). Nothing here is a rule or a "
        "definition yet. To confirm one, correct its title (and definition) and set `confirmed: true`; "
        "/ready or /onboard refresh then moves an R-draft into profile/domain.md as the next R<n>, and a "
        "W-draft into its Domain words table, and deletes it here. Leave `source:` and `quote:` as they are. "
        "A draft at `confirmed: false` is a gap, never coverage.",
        "",
        "## Confirmed, waiting to move into domain.md",
        "",
    ]
    lines += [block.rstrip() + "\n" for block in kept] or ["(none)", ""]
    by_module: dict[str, list[Draft]] = {}
    for draft in drafts:
        if draft.key not in kept_keys:
            by_module.setdefault(draft.module, []).append(draft)
    numbers = {"rule": 0, "word": 0}
    for module in sorted(by_module):
        lines += [f"## {module}", ""]
        for draft in by_module[module]:
            numbers[draft.kind] += 1
            letter = "W" if draft.kind == "word" else "R"
            lines.append(f"### {letter}-draft-{numbers[draft.kind]:03d} - {' '.join(draft.text.split())}")
            if draft.kind == "word":
                lines.append(f"definition: {draft.definition}")
            else:
                lines.append(f"fields: {', '.join(draft.fields)}")
            lines += [
                f"source: {draft.source}",
                *draft.extra,
                f"drafted-by: baton context build ({draft.miner} miner)",
                "confirmed: false",
                "",
            ]
    if not by_module:
        lines += [
            "No drafts: every branch point is mapped or has a proposed rule, and no test or answer is "
            "unmined.",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def run_build(
    central: Path, repos: list[Repo], domain: dm.Domain, settings: Settings, use_treesitter: bool = True
) -> dict:
    vocab = vocabulary(repos, [w.word for w in domain.words], settings)
    points = extract(repos, vocab, use_treesitter)
    merged = merge(points, load_points(central), domain, {r.name: r.commit for r in repos})
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_points(central, merged, generated)
    drafts = (
        mine_points(merged)
        + mine_tests(repos, vocab, domain)
        + mine_clarifications(central, vocab)
        + mine_documents(central, vocab, domain)
    )
    kept = kept_drafts(central)
    path = central / DRAFTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_drafts(drafts, kept)
    path.write_text(rendered, encoding="utf-8")
    by_extractor: dict[str, int] = {}
    for point in merged:
        name = point["provenance"]["extractor"]
        by_extractor[name] = by_extractor.get(name, 0) + 1
    return {
        "branchPoints": len(merged),
        "mapped": sum(p["status"] == "mapped" for p in merged),
        "undocumented": sum(p["status"] == "undocumented" for p in merged),
        "contested": sum(p["status"] == "contested" for p in merged),
        "extractors": by_extractor,
        "drafts": len(re.findall(r"(?m)^confirmed: false$", rendered)),
        "confirmedDraftsWaiting": len(kept),
        "wrote": [str(p) for p in ("profile/branch-points.yaml", DRAFTS_FILE)],
    }
