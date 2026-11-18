"""Business branch points: conditionals whose predicate names a domain field (context-map.md section 2).

Java is read with tree-sitter when the `baton[treesitter]` extra is installed, else with the scanner below;
TS and TSX always with the scanner. Each point records which one found it (`provenance.extractor`); the two
Java back-ends find the same points on the fixture (tests/context).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KINDS = ("if", "switch", "ternary", "filter", "conditional-on", "query", "jsx-and")
DEFAULT_PATTERNS = (
    "status",
    "type",
    "code",
    "date",
    "period",
    "tier",
    "flag",
    "limit",
    "amount",
    "rate",
    "class",
    "family",
)
_KEYWORDS = {
    "true",
    "false",
    "null",
    "undefined",
    "new",
    "this",
    "super",
    "instanceof",
    "typeof",
    "return",
    "var",
    "let",
    "const",
    "final",
    "class",
    "void",
    "case",
    "default",
    "in",
    "of",
    "equals",
    "length",
    "size",
}
_ACCESSOR = re.compile(r"^(?:get|is|has)(?=[A-Z])")
_TOKEN = re.compile(r"[A-Za-z_$][\w$]*")
_STRING = re.compile(r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`")
_NULL_CHECK = re.compile(
    r"[\w$]+(?:\.[\w$]+(?:\(\))?)*(?:\(\))?\s*[!=]==?\s*(?:null|undefined)"
    r"|(?:null|undefined)\s*[!=]==?\s*[\w$]+(?:\.[\w$]+(?:\(\))?)*(?:\(\))?"
)


@dataclass
class Point:
    repo: str
    file: str
    line: int
    kind: str
    predicate: str
    fields: list[str]
    extractor: str
    module: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Vocabulary:
    """What makes an identifier a domain field: a domain word, a field of a stored document, or a pattern."""

    words: set[str] = field(default_factory=set)  # normalized: lower case, no separators
    document_fields: set[str] = field(default_factory=set)
    patterns: tuple[str, ...] = DEFAULT_PATTERNS

    def is_domain(self, name: str) -> bool:
        flat = normalize(name)
        if flat in self.words or name in self.document_fields:
            return True
        return any(part in self.patterns for part in split_words(name))


def normalize(text: str) -> str:
    return re.sub(r"[\s_\-]", "", text).lower()


def split_words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w.lower() for w in re.split(r"[\s_\-.]+", spaced) if w]


def field_name(token: str) -> str:
    stripped = _ACCESSOR.sub("", token)
    return stripped[0].lower() + stripped[1:] if stripped != token else token


def fields_of(predicate: str, vocabulary: Vocabulary, read_strings: bool = False) -> list[str]:
    """The domain fields a predicate names, in order. A bare null check names nothing: it guards, it decides
    no     business question. Types and constants (a capital first letter) are not fields."""
    text = predicate if read_strings else _STRING.sub('""', predicate)
    text = _NULL_CHECK.sub(" ", text)
    found: list[str] = []
    for token in _TOKEN.findall(text):
        if token in _KEYWORDS or token[0].isupper() or token[0] == "$":
            continue
        name = field_name(token)
        if name not in found and vocabulary.is_domain(name):
            found.append(name)
    return found


def squash(text: str) -> str:
    return " ".join(text.split())


# --- the scanner (Java without tree-sitter, and TS) -------------------------------------------------------


def _mask(source: str, keep_strings: bool = False) -> str:
    """Comments (and strings unless kept) blanked to spaces, newlines kept, so offsets match the source."""
    out, i, n = list(source), 0, len(source)
    while i < n:
        two = source[i : i + 2]
        if two == "//":
            end = source.find("\n", i)
            end = n if end < 0 else end
        elif two == "/*":
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
        elif source[i] in "\"'`":
            quote, end = source[i], i + 1
            if source[i : i + 3] == '"""':
                close = source.find('"""', i + 3)
                end = n if close < 0 else close + 3
            else:
                while end < n and source[end] != quote and (quote == "`" or source[end] != "\n"):
                    end += 2 if source[end] == "\\" else 1
                end = min(end + 1, n)
            if keep_strings:
                i = end
                continue
            for k in range(i + 1, end - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = end
            continue
        else:
            i += 1
            continue
        for k in range(i, end):
            if out[k] != "\n":
                out[k] = " "
        i = end
    return "".join(out)


def _closing(masked: str, start: int, opening: str = "(", closing: str = ")") -> int:
    depth = 0
    for i in range(start, len(masked)):
        if masked[i] == opening:
            depth += 1
        elif masked[i] == closing:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _ternary_start(masked: str, question: int) -> int:
    i, depth = question - 1, 0
    while i >= 0:
        ch = masked[i]
        if ch in ")]":
            depth += 1
        elif ch in "([":
            if depth == 0:
                return i + 1
            depth -= 1
        elif depth == 0:
            if ch in ";{},":
                return i + 1
            if ch == "=" and masked[i - 1 : i] not in ("=", "!", "<", ">") and masked[i + 1 : i + 2] != "=":
                return i + 1
            if ch == ":" or (ch == "&" and masked[i - 1 : i] != "&" and masked[i + 1 : i + 2] != "&"):
                return i + 1
            if masked[max(0, i - 5) : i + 1] == "return" and (i < 6 or not masked[i - 6].isalnum()):
                return i + 1
        i -= 1
    return 0


def scan(source: str, typescript: bool = False) -> list[tuple[int, str, str, bool]]:
    """(offset, kind, predicate, read strings) for every candidate conditional, in source order."""
    masked, found = _mask(source), []
    for match in re.finditer(r"\b(if|switch)\s*\(", masked):
        open_at = match.end() - 1
        close = _closing(masked, open_at)
        if close > 0:
            found.append((match.start(), match.group(1), source[open_at + 1 : close], False))
    for match in re.finditer(r"\.\s*(filter)\s*\(", masked):
        open_at = match.end() - 1
        close = _closing(masked, open_at)
        if close > 0:
            found.append((match.start(1), "filter", source[open_at + 1 : close], False))
    for match in re.finditer(r"(?<=\s)\?(?=\s)", masked):
        start = _ternary_start(masked, match.start())
        while start < match.start() and masked[start].isspace():
            start += 1
        if start < match.start():
            found.append((start, "ternary", source[start : match.start()], False))
    if typescript:
        for match in re.finditer(r"\{([^{}]+?)\s&&\s*(?=<)", masked):
            start = match.start(1) + len(match.group(1)) - len(match.group(1).lstrip())
            found.append(
                (start, "jsx-and", source[match.start(1) : match.start(1) + len(match.group(1))], False)
            )
    else:
        strings_kept = _mask(source, keep_strings=True)
        for match in re.finditer(r"@(ConditionalOn\w+|Query)\b\s*\(", strings_kept):
            open_at = match.end() - 1
            close = _closing(masked, open_at)
            if close > 0:
                kind = "query" if match.group(1) == "Query" else "conditional-on"
                found.append((match.start(), kind, source[open_at + 1 : close], True))
    return sorted(found)


# --- tree-sitter (Java) -----------------------------------------------------------------------------------


def treesitter_java(source: str) -> list[tuple[int, str, str, bool]] | None:
    """The same candidates from the syntax tree, as (line, ...) not offset; None when tree-sitter is absent or
    the file does not parse (the scanner reads it then)."""
    from baton.extract import treesitter_backend

    if not treesitter_backend.available():
        return None
    data = source.encode("utf-8")
    root = treesitter_backend._load().parse(data).root_node
    if root.has_error:
        return None

    def text(node) -> str:
        return data[node.start_byte : node.end_byte].decode("utf-8")

    def inner(node) -> str:
        body = text(node)
        return body[1:-1] if body.startswith("(") and body.endswith(")") else body

    found: list[tuple[int, str, str, bool]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.children))
        kind = node.type
        if kind == "if_statement":
            found.append((node.start_point[0] + 1, "if", inner(node.child_by_field_name("condition")), False))
        elif kind in ("switch_expression", "switch_statement"):
            condition = node.child_by_field_name("condition")
            if condition is not None:
                found.append((node.start_point[0] + 1, "switch", inner(condition), False))
        elif kind == "ternary_expression":
            condition = node.child_by_field_name("condition")
            found.append((condition.start_point[0] + 1, "ternary", text(condition), False))
        elif kind == "method_invocation":
            name = node.child_by_field_name("name")
            arguments = node.child_by_field_name("arguments")
            if name is not None and text(name) == "filter" and arguments is not None:
                found.append((name.start_point[0] + 1, "filter", inner(arguments), False))
        elif kind == "annotation":
            name = text(node.child_by_field_name("name")).rsplit(".", 1)[-1]
            arguments = node.child_by_field_name("arguments")
            if arguments is not None and (name == "Query" or name.startswith("ConditionalOn")):
                found.append(
                    (
                        node.start_point[0] + 1,
                        "query" if name == "Query" else "conditional-on",
                        inner(arguments),
                        True,
                    )
                )
    return found


def points_in(
    source: str, repo: str, path: str, vocabulary: Vocabulary, use_treesitter: bool = True
) -> list[Point]:
    """Every branch point in one file. A candidate whose predicate names no domain field is not a point."""
    typescript = path.endswith((".ts", ".tsx", ".js", ".jsx"))
    candidates = None if typescript or not use_treesitter else treesitter_java(source)
    if candidates is not None:
        extractor = "branch-points-java"
        located = candidates
    else:
        extractor = "branch-points-ts-scan" if typescript else "branch-points-java-scan"
        located = [
            (source.count("\n", 0, offset) + 1, kind, pred, strings)
            for offset, kind, pred, strings in scan(source, typescript)
        ]
    points = []
    for line, kind, predicate, read_strings in located:
        fields = fields_of(predicate, vocabulary, read_strings)
        if fields:
            points.append(Point(repo, path, line, kind, squash(predicate), fields, extractor))
    return sorted(points, key=lambda p: (p.line, p.kind, p.predicate))


# One declaration per line, spaces and tabs only: `\s` here would let the type run across lines, and a masked
# comment block (all spaces) then backtracks exponentially.
_DOCUMENT_FIELD = re.compile(
    r"^[ \t]*(?:(?:private|protected|public|static|final|transient|volatile)[ \t]+)*"
    r"[\w.$]+(?:[ \t]*<[^;=\n(){}]*>)?(?:[ \t]*\[[ \t]*\])*[ \t]+([a-z][\w$]*)[ \t]*(?:=[^;]*)?;",
    re.M,
)
_RECORD = re.compile(r"\brecord\s+\w+\s*\(([^)]*)\)")


def document_fields(source: str) -> set[str]:
    """The fields of a `@Document` class or record: stored, so a branch on one is a business branch."""
    if "@Document" not in source:
        return set()
    masked = _mask(source)
    names = set(_DOCUMENT_FIELD.findall(masked))
    for components in _RECORD.findall(masked):
        names.update(part.split()[-1] for part in components.split(",") if part.split())
    return names
