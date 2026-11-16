"""`profile/domain.md` read as an index (context-map.md section 3): rules, domain words, open decisions.

The format is additive: prose stays prose. A rule is a `### R<n> - title` heading followed by key lines
(`fields:`, `source:`, `confirmed:`); a word is a row of the `| word | definition | confirmed |` table under
`## Domain words`. Words listed only in `profile/project.md` (the older place) count as words with no
definition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_RULE = re.compile(r"^###[ \t]+(R\d+)\b[ \t]*[-:—–]*[ \t]*(.*)$")
_KEY = re.compile(r"^(fields|source|confirmed):[ \t]*(.*)$", re.I)
_STORY = re.compile(r"\b[A-Z]+-\d+\b")


@dataclass
class Rule:
    id: str
    title: str
    line: int
    fields: list[str] = field(default_factory=list)
    source: str = ""
    confirmed: bool = False

    @property
    def indexable(self) -> bool:
        return bool(self.fields)

    @property
    def is_draft(self) -> bool:
        return not (self.source and self.confirmed)


@dataclass
class Word:
    word: str
    definition: str = ""
    confirmed: bool = False
    where: str = "profile/domain.md"

    @property
    def defined(self) -> bool:
        return bool(self.definition.strip()) and self.confirmed


@dataclass
class Decision:
    text: str
    line: int

    @property
    def owned(self) -> bool:
        """An owner and somewhere it is being settled: a story or an ADR."""
        low = self.text.lower()
        return "owner:" in low and (bool(_STORY.search(self.text)) or "adr" in low)


@dataclass
class Domain:
    rules: list[Rule] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def confirmed_rules(self) -> list[Rule]:
        return [r for r in self.rules if not r.is_draft]


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "yes")


def _sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """(heading, first body line index, end index) for each `## ` section."""
    heads = [(i, ln[3:].strip()) for i, ln in enumerate(lines) if ln.startswith("## ")]
    return [
        (name, i + 1, heads[k + 1][0] if k + 1 < len(heads) else len(lines))
        for k, (i, name) in enumerate(heads)
    ]


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse(text: str) -> Domain:
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    lines = text.splitlines()
    domain = Domain()
    current: Rule | None = None
    for index, line in enumerate(lines):
        heading = _RULE.match(line)
        if heading:
            current = Rule(heading.group(1), heading.group(2).strip(), index + 1)
            domain.rules.append(current)
            continue
        if line.startswith("#"):
            current = None
            continue
        key = _KEY.match(line.strip()) if current else None
        if key:
            name, value = key.group(1).lower(), key.group(2).strip()
            if name == "fields":
                current.fields = [f.strip() for f in value.split(",") if f.strip()]
            elif name == "source":
                current.source = value
            else:
                current.confirmed = _truthy(value)
    for name, start, end in _sections(lines):
        low = name.lower()
        if low.startswith("domain words"):
            columns: list[str] = []
            for line in lines[start:end]:
                if not line.strip().startswith("|"):
                    continue
                cells = _cells(line)
                if not columns:
                    columns = [c.lower() for c in cells]
                    continue
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                row = dict(zip(columns, cells, strict=False))
                if row.get("word"):
                    domain.words.append(
                        Word(row["word"], row.get("definition", ""), _truthy(row.get("confirmed", "")))
                    )
        elif low.startswith("open decisions"):
            for index in range(start, end):
                item = lines[index].strip()
                if item.startswith(("- ", "* ")) and len(item) > 2:
                    domain.decisions.append(Decision(item[2:].strip(), index + 1))
    return domain


def project_words(text: str) -> list[str]:
    """The `## Domain words` list of profile/project.md: comma- or line-separated, placeholders skipped."""
    lines = text.splitlines()
    for name, start, end in _sections(lines):
        if name.lower().startswith("domain words"):
            body = " ,".join(ln.strip().lstrip("-* ") for ln in lines[start:end] if ln.strip())
            words = [w.strip() for w in body.split(",")]
            return [w for w in words if w and not w.startswith(("<", "(")) and "|" not in w]
    return []


def load(central: Path) -> Domain:
    path = central / "profile" / "domain.md"
    domain = parse(path.read_text(encoding="utf-8")) if path.is_file() else Domain()
    project = central / "profile" / "project.md"
    if project.is_file():
        known = {w.word.lower() for w in domain.words}
        for word in project_words(project.read_text(encoding="utf-8")):
            if word.lower() not in known:
                known.add(word.lower())
                domain.words.append(Word(word, where="profile/project.md"))
    return domain
