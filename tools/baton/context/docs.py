"""The doc miner and the document map: what the ingested sources (docs/context/sources/) say, and where.

Mining is string matching, never interpretation:
- a word: a glossary-table row, a `Term: definition` line under a Glossary/Definitions/Terms heading, or a
  sentence `A <Term> is|means|refers to ...` whose Term is a domain word or in Title Case;
- a rule: a sentence with a normative word (must, shall, never, only if, ...) that names a domain field.
Each draft cites `<original file>#<heading>` and stays `confirmed: false`. The document map lists, per source,
the modules, collections, endpoints and domain words it mentions, so a story's manifest can name the documents
that speak about its scope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from baton.context import branch_points as bp
from baton.context import domain as dm
from baton.context.ingest import INDEX_JSON

MAX_DRAFTS_PER_DOCUMENT = 200
_NORMATIVE = re.compile(
    r"(?i)\b(must|must not|shall|shall not|should not|never|always|only if|only when|cannot|can not|"
    r"may not|not allowed|is required|are required|is mandatory|at least|at most|no later than)\b"
)
_GLOSSARY = re.compile(r"(?i)glossary|definitions?|terms|terminology|vocabulary")
_DEFINES = re.compile(
    r"^(?:An?|The)?\s*(?P<term>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){0,3})\s+"
    r"(?:is defined as|is|means|refers to|represents)\s+(?P<definition>.{8,})$"
)
_TERM_LINE = re.compile(
    r"^[-*]?\s*(?:\*\*)?(?P<term>[A-Za-z][\w -]{1,40}?)(?:\*\*)?\s*[:–—-]\s+"
    r"(?P<definition>.{8,})$"
)
_TERM_COLUMNS = ("term", "word", "name", "acronym", "field")
_DEFINITION_COLUMNS = ("definition", "meaning", "description", "explanation")


@dataclass
class Section:
    source: str  # the original file, as cited
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)

    @property
    def cite(self) -> str:
        return f"{self.source}#{self.heading}" if self.heading else self.source


def sources(central: Path) -> list[dict]:
    path = central / INDEX_JSON
    if not path.is_file():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("documents") or [])
    except (ValueError, AttributeError):
        return []


def sections(central: Path, document: dict) -> list[Section]:
    path = central / document["file"]
    if not path.is_file():
        return []
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    cited = document.get("origin") or document["source"]
    out = [Section(cited, "")]
    title_seen = False
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", block)
        if heading and "\n" not in block:
            if not title_seen:
                title_seen = True  # the file-name title the ingest wrote
                continue
            out.append(Section(cited, heading.group(1).strip()))
        elif block.startswith("|"):
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in block.splitlines()]
            out[-1].tables.append([r for r in rows if not all(set(c) <= set("-: ") for c in r)])
        else:
            out[-1].paragraphs.extend(ln.strip() for ln in block.splitlines() if ln.strip())
    return [s for s in out if s.paragraphs or s.tables]


def sentences(paragraph: str) -> list[str]:
    text = re.sub(r"^[-*\d.)\s]+", "", paragraph).strip()
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()]


def _title_case(term: str) -> bool:
    words = term.split()
    return all(w[0].isupper() for w in words) and len(words) <= 4


@dataclass
class Mined:
    words: list[tuple[str, str, str]] = field(default_factory=list)  # (word, definition, cite)
    rules: list[tuple[str, list[str], str]] = field(default_factory=list)  # (sentence, fields, cite)


def mine_document(central: Path, document: dict, vocab: bp.Vocabulary, domain: dm.Domain) -> Mined:
    known = {bp.normalize(w.word): w for w in domain.words}
    mined, seen = Mined(), set()

    def word(term: str, definition: str, cite: str) -> None:
        term = term.strip(" *`")
        key = bp.normalize(term)
        existing = known.get(key)
        if key in seen or (existing and existing.defined) or len(term) < 2:
            return
        seen.add(key)
        mined.words.append((term, " ".join(definition.split()), cite))

    for section in sections(central, document):
        glossary = bool(_GLOSSARY.search(section.heading))
        for table in section.tables:
            header = [c.lower() for c in table[0]] if table else []
            term_at = next((i for i, c in enumerate(header) if c in _TERM_COLUMNS), None)
            def_at = next((i for i, c in enumerate(header) if c in _DEFINITION_COLUMNS), None)
            if term_at is not None and def_at is not None:
                for row in table[1:]:
                    if len(row) > max(term_at, def_at) and row[term_at] and row[def_at]:
                        word(row[term_at], row[def_at], section.cite)
        for paragraph in section.paragraphs:
            line = _TERM_LINE.match(paragraph)
            if glossary and line:
                word(line.group("term"), line.group("definition"), section.cite)
                continue
            for sentence in sentences(paragraph):
                defines = _DEFINES.match(sentence)
                if defines:
                    term = defines.group("term")
                    if bp.normalize(term) in known or _title_case(term):
                        word(term, defines.group("definition"), section.cite)
                if _NORMATIVE.search(sentence):
                    fields = bp.fields_of(sentence, vocab, read_strings=True)
                    key = bp.normalize(sentence)
                    if fields and key not in seen:
                        seen.add(key)
                        mined.rules.append((sentence, fields, section.cite))
    mined.words = mined.words[:MAX_DRAFTS_PER_DOCUMENT]
    mined.rules = mined.rules[:MAX_DRAFTS_PER_DOCUMENT]
    return mined


def mentions(central: Path, repos: list, domain: dm.Domain) -> list[dict]:
    """Per ingested document: the modules, collections, endpoints and domain words its text names."""
    names: dict[str, set[str]] = {}  # module key -> names that point at it
    resources: set[str] = set()
    for repo in repos:
        for key, module in repo.modules.items():
            if not module.sources:
                continue
            alias = {key.split("/")[-1].split(".")[-1]} | {p.stem for p in module.sources if len(p.stem) >= 6}
            names[module.key] = {a for a in alias if len(a) >= 4}
            resources |= {str(e.get("to")) for e in module.edges}
    out = []
    for document in sources(central):
        path = central / document["file"]
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        modules = sorted(
            k for k, alias in names.items() if any(re.search(rf"(?i)\b{re.escape(a)}\b", text) for a in alias)
        )
        found = []
        for target in sorted(resources):
            kind, _, name = target.partition(":")
            probe = name.split(" ", 1)[-1] if kind == "endpoint" else name
            if probe and "${" not in probe and re.search(rf"(?i)(?<![\w/]){re.escape(probe)}(?![\w])", text):
                found.append(target)
        words = sorted(
            w.word
            for w in domain.words
            if re.search(r"(?i)\b" + r"[\s_-]*".join(map(re.escape, w.word.split())) + r"s?\b", text)
        )
        out.append(
            {
                "source": document["source"],
                "file": document["file"],
                "kind": document.get("kind"),
                "modules": modules,
                "resources": found,
                "words": words,
            }
        )
    return out


def skipped(central: Path) -> list[dict]:
    """Files ingest could not read, and the parts of read files it left unread (images, scanned pages)."""
    path = central / INDEX_JSON
    if not path.is_file():
        return []
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []
    out = list(index.get("skipped") or [])
    for document in index.get("documents") or []:
        out += [{"source": document["source"], "reason": w} for w in document.get("warnings") or []]
    return out
