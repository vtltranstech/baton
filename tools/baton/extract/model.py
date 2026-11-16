"""The parser-independent view of a Java file. Both back-ends produce this; extractors read only this."""

from __future__ import annotations

from dataclasses import dataclass, field


class ParseFailure(Exception):
    """The file cannot be read as Java by this back-end."""


@dataclass(frozen=True)
class Expr:
    """kind: str (value), name (dotted value), cls (value), concat (items), array (items),
    new (value = type, items = args), other (anything a target cannot be read from)."""

    kind: str
    value: str = ""
    items: tuple[Expr, ...] = ()


OTHER = Expr("other")


@dataclass
class Annotation:
    name: str
    line: int
    args: dict[str, Expr] = field(default_factory=dict)  # a single unnamed argument is under "value"


@dataclass(frozen=True)
class TypeRef:
    name: str  # simple name, no package
    args: tuple[str, ...] = ()  # simple names of the type arguments


@dataclass
class Var:
    name: str
    type: TypeRef
    line: int
    annotations: list[Annotation] = field(default_factory=list)
    final: bool = False
    init: Expr | None = None


@dataclass
class Call:
    name: str
    args: tuple[Expr, ...]
    line: int


@dataclass
class Chain:
    """`root.a(..).b(..)` or `new T(..).a(..)`. root is "" for an unqualified call; `this.` is dropped."""

    root: str
    calls: list[Call] = field(default_factory=list)
    new: Expr | None = None
    new_line: int = 0
    method: Method | None = None


@dataclass
class Method:
    name: str
    line: int
    annotations: list[Annotation] = field(default_factory=list)
    params: list[Var] = field(default_factory=list)
    locals: list[Var] = field(default_factory=list)
    end: int = 0  # last line; 0 when the back-end cannot tell
    returns: str = ""  # declared return type in short form; "" for a constructor or when unknown
    visibility: str = ""  # public | protected | private | package; "" when unknown


@dataclass
class TypeDecl:
    name: str
    fqcn: str
    kind: str  # class | interface | enum | record | annotation
    line: int
    annotations: list[Annotation] = field(default_factory=list)
    extends: list[TypeRef] = field(default_factory=list)
    implements: list[TypeRef] = field(default_factory=list)
    fields: list[Var] = field(default_factory=list)  # record components included
    methods: list[Method] = field(default_factory=list)
    chains: list[Chain] = field(default_factory=list)
    outer: TypeDecl | None = None
    end: int = 0  # last line; 0 when the back-end cannot tell

    def annotation(self, *names: str) -> Annotation | None:
        return next((a for a in self.annotations if a.name in names), None)


@dataclass
class JavaFile:
    path: str  # repo-relative
    package: str = ""
    imports: list[str] = field(default_factory=list)
    static_imports: list[str] = field(default_factory=list)
    types: list[TypeDecl] = field(default_factory=list)  # flat, nested types included
    source: str = ""  # comment-free text, for token searches
    backend: str = ""
    fallback_reason: str = ""


def unescape(text: str) -> str:
    """Java string escapes; only the ones a name or path could plausibly hold need care."""
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "'": "'", "\\": "\\", "s": " "}
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == "\n":  # a text block's line continuation
                i += 2
                continue
            if nxt == "u" and i + 5 < len(text):
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)
