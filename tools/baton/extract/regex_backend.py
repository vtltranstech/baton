"""The fallback back-end (decision D1): a token-regex scanner, stdlib only.

It understands what javalang 0.13 cannot (records, text blocks, sealed types) and tolerates syntax it does
not know. Unbalanced brackets or an unterminated literal make it refuse the file: partial structure is not
reported as fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from baton.extract.model import (
    OTHER,
    Annotation,
    Call,
    Chain,
    Expr,
    JavaFile,
    Method,
    ParseFailure,
    TypeDecl,
    TypeRef,
    Var,
    unescape,
)

NAME = "regex"
_TOKEN = re.compile(
    r"""(?P<ws>\s+)|(?P<comment>//[^\n]*|/\*.*?\*/)|(?P<block>\"\"\".*?(?<!\\)\"\"\")"""
    r"""|(?P<str>"(?:\\.|[^"\\\n])*")|(?P<chr>'(?:\\.|[^'\\\n])+')"""
    r"""|(?P<id>[A-Za-z_$][\w$]*)|(?P<num>\d[\w.]*)|(?P<op>::|->|\.\.\.|.)""",
    re.S,
)
_MODIFIERS = {
    "public",
    "protected",
    "private",
    "static",
    "final",
    "abstract",
    "native",
    "synchronized",
    "transient",
    "volatile",
    "strictfp",
    "default",
    "sealed",
}
_KEYWORDS = _MODIFIERS | {
    "if",
    "else",
    "for",
    "while",
    "do",
    "switch",
    "case",
    "return",
    "throw",
    "try",
    "catch",
    "finally",
    "new",
    "instanceof",
    "class",
    "interface",
    "enum",
    "import",
    "package",
    "extends",
    "implements",
    "throws",
    "void",
    "super",
    "this",
    "break",
    "continue",
    "assert",
    "yield",
    "true",
    "false",
    "null",
    "boolean",
    "int",
    "long",
    "byte",
    "short",
    "char",
    "float",
    "double",
}
_PRIMITIVES = {"boolean", "int", "long", "byte", "short", "char", "float", "double", "void", "var"}
_PAIRS = {"(": ")", "{": "}", "[": "]"}


@dataclass
class Tok:
    kind: str
    value: str
    line: int


def tokenize(source: str) -> list[Tok]:
    tokens, line = [], 1
    for match in _TOKEN.finditer(source):
        kind, text = match.lastgroup, match.group()
        if kind not in ("ws", "comment"):
            if kind == "op" and text in ('"', "'"):
                raise ParseFailure(f"unterminated literal at line {line}")
            if kind == "op" and text == "/" and source.startswith("/*", match.start()):
                raise ParseFailure(f"unterminated comment at line {line}")
            tokens.append(Tok(kind, text, line))
        line += text.count("\n")
    return tokens


def _block_value(raw: str) -> str:
    body = raw[3:-3]
    lines = body.split("\n")[1:]
    content = [ln for ln in lines if ln.strip()]
    margin = min((len(ln) - len(ln.lstrip()) for ln in content), default=0)
    return unescape("\n".join(ln[margin:].rstrip() for ln in lines))


class _Scanner:
    def __init__(self, path: str, source: str):
        self.toks = tokenize(source)
        self.close = self._match_brackets()
        self.file = JavaFile(path=path, backend=NAME)
        self.pending_type: TypeDecl | None = None

    def _match_brackets(self) -> dict[int, int]:
        pairs, stack = {}, []
        for i, tok in enumerate(self.toks):
            if tok.kind != "op":
                continue
            if tok.value in _PAIRS:
                stack.append(i)
            elif tok.value in _PAIRS.values():
                if not stack or _PAIRS[self.toks[stack[-1]].value] != tok.value:
                    raise ParseFailure(f"unbalanced {tok.value!r} at line {tok.line}")
                pairs[stack.pop()] = i
        if stack:
            raise ParseFailure(f"unclosed {self.toks[stack[-1]].value!r} at line {self.toks[stack[-1]].line}")
        return pairs

    def val(self, i: int) -> str:
        return self.toks[i].value if 0 <= i < len(self.toks) else ""

    def is_id(self, i: int) -> bool:
        return 0 <= i < len(self.toks) and self.toks[i].kind == "id"

    def is_name(self, i: int) -> bool:
        return self.is_id(i) and self.val(i) not in _KEYWORDS

    # -- file ---------------------------------------------------------------------------------------------

    def parse(self) -> JavaFile:
        i, end = 0, len(self.toks)
        while i < end:
            i = self._skip_annotations_collect(i)[1]
            if self.val(i) == "package":
                j = self._until(i, ";")
                self.file.package = "".join(t.value for t in self.toks[i + 1 : j])
                i = j + 1
            elif self.val(i) == "import":
                j = self._until(i, ";")
                text = [t.value for t in self.toks[i + 1 : j]]
                if text[:1] == ["static"]:
                    self.file.static_imports.append("".join(text[1:]))
                else:
                    self.file.imports.append("".join(text))
                i = j + 1
            else:
                break
        i = 0 if not (self.file.package or self.file.imports) else self._after_header()
        self._members(i, end, None)
        self.file.source = " ".join(t.value for t in self.toks)
        return self.file

    def _after_header(self) -> int:
        last = 0
        for i, tok in enumerate(self.toks):
            if tok.value in ("package", "import") and tok.kind == "id":
                last = self._until(i, ";") + 1
            elif tok.value == "{":
                break
        return last

    def _until(self, i: int, value: str) -> int:
        while i < len(self.toks) and self.val(i) != value:
            i += 1
        return i

    # -- annotations --------------------------------------------------------------------------------------

    def _skip_annotations_collect(self, i: int) -> tuple[list[Annotation], int]:
        found = []
        while self.val(i) == "@" and self.val(i + 1) != "interface":
            line = self.toks[i].line
            j = i + 1
            name = self.val(j)
            while self.val(j + 1) == "." and self.is_id(j + 2):
                j += 2
                name = self.val(j)
            j += 1
            args: dict[str, Expr] = {}
            if self.val(j) == "(":
                close = self.close[j]
                for start, stop in self._split(j + 1, close):
                    if self.is_id(start) and self.val(start + 1) == "=":
                        args[self.val(start)] = self._expr(start + 2, stop)
                    else:
                        args["value"] = self._expr(start, stop)
                j = close + 1
            found.append(Annotation(name, line, args))
            i = j
        return found, i

    # -- expressions --------------------------------------------------------------------------------------

    def _split(self, start: int, stop: int, sep: str = ",") -> list[tuple[int, int]]:
        parts, i, begin, angle = [], start, start, 0
        while i < stop:
            value = self.val(i)
            if value in _PAIRS and self.toks[i].kind == "op":
                i = self.close[i] + 1
                continue
            if value == sep and angle <= 0:
                parts.append((begin, i))
                begin = i + 1
            elif sep == "," and value == "<" and self._generic_end(i) is not None:
                i = self._generic_end(i) + 1
                continue
            i += 1
        if begin < stop:
            parts.append((begin, stop))
        return parts

    def _expr(self, start: int, stop: int) -> Expr:
        parts = self._split(start, stop, "+")
        if len(parts) > 1:
            if any(self.toks[k].value == "?" for k in range(start, stop) if self.toks[k].kind == "op"):
                return OTHER
            return Expr("concat", items=tuple(self._term(a, b) for a, b in parts))
        return self._term(start, stop)

    def _term(self, start: int, stop: int) -> Expr:
        if start >= stop:
            return OTHER
        tok = self.toks[start]
        if stop - start == 1:
            if tok.kind == "str":
                return Expr("str", unescape(tok.value[1:-1]))
            if tok.kind == "block":
                return Expr("str", _block_value(tok.value))
        if tok.value == "{" and self.close.get(start) == stop - 1:
            return Expr("array", items=tuple(self._expr(a, b) for a, b in self._split(start + 1, stop - 1)))
        if tok.value == "new" and tok.kind == "id":
            ref, j = self._type_ref(start + 1)
            if ref and self.val(j) == "(" and self.close[j] == stop - 1:
                args = tuple(self._expr(a, b) for a, b in self._split(j + 1, self.close[j]))
                return Expr("new", ref.name, args)
            return OTHER
        i, names = start, []
        while i < stop and self.is_id(i) and self.val(i) not in (_KEYWORDS - {"this", "class"}):
            names.append(self.val(i))
            i += 1
            if i < stop and self.val(i) == ".":
                i += 1
            else:
                break
        if i == stop and names:
            if names[-1] == "class" and len(names) >= 2:
                return Expr("cls", names[-2])
            if names[0] == "this":
                names = names[1:]
            return Expr("name", ".".join(names)) if names else OTHER
        return OTHER

    # -- types --------------------------------------------------------------------------------------------

    def _generic_end(self, i: int) -> int | None:
        """Index of the `>` matching the `<` at i when this is a type-argument list, else None."""
        depth, j = 0, i
        while j < len(self.toks):
            value = self.val(j)
            if value == "<":
                depth += 1
            elif value == ">":
                depth -= 1
                if depth == 0:
                    return j
            elif not (self.is_id(j) or value in (",", ".", "?", "&", "[", "]", "@")):
                return None
            j += 1
        return None

    def _type_ref(self, i: int) -> tuple[TypeRef | None, int]:
        if not self.is_id(i) or (self.val(i) in _KEYWORDS and self.val(i) not in _PRIMITIVES):
            return None, i
        name = self.val(i)
        j = i + 1
        args: tuple[str, ...] = ()
        while True:
            if self.val(j) == "<":
                end = self._generic_end(j)
                if end is None:
                    break
                args = self._type_args(j + 1, end)
                j = end + 1
            if self.val(j) == "." and self.is_id(j + 1) and self.val(j + 1) not in _KEYWORDS:
                name = self.val(j + 1)
                j += 2
                continue
            break
        while self.val(j) == "[" and self.val(j + 1) == "]":
            j += 2
        if self.val(j) == "...":
            j += 1
        return TypeRef(name, args), j

    def _type_args(self, start: int, stop: int) -> tuple[str, ...]:
        """Top-level type arguments as simple names; `?` and bounds are read as the bound."""
        out = []
        for a, b in self._split(start, stop):
            k = a
            while k < b and self.val(k) in ("?", "extends", "super", "@"):
                k += 1
            ref, _ = self._type_ref(k)
            out.append(ref.name if ref else "?")
        return tuple(out)

    def _type_list(self, i: int) -> tuple[list[TypeRef], int]:
        out = []
        while True:
            ref, j = self._type_ref(i)
            if ref is None:
                return out, i
            out.append(ref)
            i = j
            if self.val(i) != ",":
                return out, i
            i += 1

    def _is_type_start(self, i: int) -> bool:
        value = self.val(i)
        if self.val(i - 1) == ".":
            return False
        if value in ("class", "interface", "enum") or (value == "@" and self.val(i + 1) == "interface"):
            return True
        return value == "record" and self.is_name(i + 1) and self.val(i + 2) in ("(", "<")

    def _type(self, i: int, outer: TypeDecl | None, annotations: list[Annotation]) -> int:
        kind = self.val(i)
        if kind == "@":
            kind, i = "annotation", i + 1
        name_at = i + 1
        name = self.val(name_at)
        outer_name = outer.fqcn if outer else self.file.package
        fqcn = f"{outer_name}.{name}" if outer_name else name
        decl = TypeDecl(name, fqcn, kind, self.toks[i].line, annotations, outer=outer)
        self.file.types.append(decl)
        j = name_at + 1
        if self.val(j) == "<":
            end = self._generic_end(j)
            j = end + 1 if end is not None else j
        if kind == "record" and self.val(j) == "(":
            close = self.close[j]
            decl.fields.extend(self._params(j + 1, close))
            j = close + 1
        while self.val(j) != "{" and j < len(self.toks):
            word = self.val(j)
            if word == "extends":
                decl.extends, j = self._type_list(j + 1)
            elif word == "implements":
                decl.implements, j = self._type_list(j + 1)
            else:
                j += 1
        if j >= len(self.toks):
            raise ParseFailure(f"type {name} has no body")
        close = self.close[j]
        decl.end = self.toks[close].line
        start = j + 1
        if kind == "enum":
            start = self._enum_constants_end(start, close)
        self._members(start, close, decl)
        return close + 1

    def _enum_constants_end(self, i: int, stop: int) -> int:
        while i < stop:
            if self.val(i) in _PAIRS and self.toks[i].kind == "op":
                i = self.close[i] + 1
                continue
            if self.val(i) == ";":
                return i + 1
            i += 1
        return stop

    # -- members ------------------------------------------------------------------------------------------

    def _members(self, i: int, stop: int, owner: TypeDecl | None) -> None:
        while i < stop:
            annotations, static_final = [], [False, False]
            while True:
                found, j = self._skip_annotations_collect(i)
                annotations += found
                i = j
                value = self.val(i)
                if value == "non" and self.val(i + 1) == "-" and self.val(i + 2) == "sealed":
                    i += 3
                elif self.is_id(i) and value in _MODIFIERS and self.val(i + 1) not in ("(", "=", ";"):
                    static_final[0] |= value == "static"
                    static_final[1] |= value == "final"
                    i += 1
                else:
                    break
            if i >= stop:
                return
            if self._is_type_start(i):
                i = self._type(i, owner, annotations)
                continue
            if self.val(i) == "{":
                if owner is not None:
                    self._body(i + 1, self.close[i], owner, None)
                i = self.close[i] + 1
                continue
            if self.val(i) == ";" or owner is None:
                i += 1
                continue
            if self.val(i) == "<":
                end = self._generic_end(i)
                i = end + 1 if end is not None else i + 1
            i = self._member(i, stop, owner, annotations, static_final[1])

    def _member(self, i: int, stop: int, owner: TypeDecl, annotations: list[Annotation], final: bool) -> int:
        ref, j = self._type_ref(i)
        if ref is None:
            return i + 1
        if self.val(j) == "(":  # constructor
            return self._method(ref.name, self.toks[i].line, j, stop, owner, annotations)
        if self.val(j) == "{":  # compact record constructor
            self._body(j + 1, self.close[j], owner, None)
            return self.close[j] + 1
        if not self.is_id(j):
            return j + 1 if j == i else j
        if self.val(j + 1) == "(":
            return self._method(self.val(j), self.toks[j].line, j + 1, stop, owner, annotations)
        return self._field(
            ref, j, stop, owner, annotations, final or owner.kind in ("interface", "annotation")
        )

    def _method(
        self, name: str, line: int, paren: int, stop: int, owner: TypeDecl, annotations: list[Annotation]
    ) -> int:
        method = Method(name, line, annotations)
        owner.methods.append(method)
        close = self.close[paren]
        method.params = self._params(paren + 1, close)
        i = close + 1
        while i < stop and self.val(i) not in ("{", ";", ","):
            i += 1
        if self.val(i) == "{":
            method.end = self.toks[self.close[i]].line
            self._body(i + 1, self.close[i], owner, method)
            return self.close[i] + 1
        method.end = self.toks[min(i, len(self.toks) - 1)].line
        return i + 1

    def _params(self, start: int, stop: int) -> list[Var]:
        out = []
        for a, b in self._split(start, stop):
            annotations, final = [], False
            i = a
            while i < b:
                found, j = self._skip_annotations_collect(i)
                annotations += found
                i = j
                if self.val(i) == "final":
                    final = True
                    i += 1
                elif not found:
                    break
            ref, j = self._type_ref(i)
            if ref and self.is_id(j):
                out.append(Var(self.val(j), ref, self.toks[j].line, annotations, final))
        return out

    def _field(
        self, ref: TypeRef, i: int, stop: int, owner: TypeDecl, annotations: list[Annotation], final: bool
    ) -> int:
        end = i
        while end < stop and self.val(end) != ";":
            if self.val(end) in _PAIRS and self.toks[end].kind == "op":
                end = self.close[end]
            end += 1
        for a, b in self._declarators(i, end):
            var = Var(self.val(a), ref, self.toks[a].line, annotations, final)
            eq = next((k for k in range(a, b) if self.val(k) == "="), None)
            if eq is not None:
                var.init = self._expr(eq + 1, b)
                self._body(eq + 1, b, owner, None)
            owner.fields.append(var)
        return end + 1

    def _declarators(self, start: int, stop: int) -> list[tuple[int, int]]:
        """`a = 1, b` splits; a comma inside an initializer's generics does not (`_split` skips those)."""
        return self._split(start, stop)

    # -- bodies -------------------------------------------------------------------------------------------

    def _body(self, i: int, stop: int, owner: TypeDecl, method: Method | None) -> None:
        pending: list[Annotation] = []
        while i < stop:
            tok = self.toks[i]
            if tok.value == "@" and tok.kind == "op":
                pending, i = self._skip_annotations_collect(i)
                continue
            if self._is_type_start(i):
                i = self._type(i, owner, pending)
                pending = []
                continue
            if tok.kind in ("str", "block") and self.val(i + 1) == ".":
                i = self._chain(i, stop, owner, method)
                continue
            if tok.kind != "id":
                i += 1
                continue
            if tok.value == "new":
                i = self._chain(i, stop, owner, method)
                continue
            if tok.value in _KEYWORDS and tok.value != "this":
                i += 1
                continue
            if self.val(i - 1) in (".", "::"):
                i += 1
                continue
            local = self._local(i, stop, owner, method, pending)
            if local is not None:
                i, pending = local, []
                continue
            i = self._chain(i, stop, owner, method)
            pending = []

    def _local(
        self, i: int, stop: int, owner: TypeDecl, method: Method | None, annotations: list[Annotation]
    ) -> int | None:
        ref, j = self._type_ref(i)
        if (
            ref is None
            or j >= stop
            or not self.is_name(j)
            or self.val(j + 1) not in ("=", ";", ":", ",", ")")
        ):
            return None
        var = Var(self.val(j), ref, self.toks[j].line, annotations, self.val(i - 1) == "final")
        if self.val(j + 1) == "=":
            end = j + 2
            while end < stop and self.val(end) != ";":
                if self.val(end) in _PAIRS and self.toks[end].kind == "op":
                    end = self.close[end]
                end += 1
            var.init = self._expr(j + 2, end)
        if method is not None:
            method.locals.append(var)
        return j + 1

    def _chain(self, i: int, stop: int, owner: TypeDecl, method: Method | None) -> int:
        chain = Chain("", method=method)
        if self.toks[i].kind in ("str", "block"):
            i += 1
        elif self.val(i) == "new":
            ref, j = self._type_ref(i + 1)
            if ref is None or self.val(j) != "(":
                return i + 1
            close = self.close[j]
            chain.new = Expr("new", ref.name, self._args(j, close, owner, method))
            chain.new_line = self.toks[i].line
            i = close + 1
            if self.val(i) == "{":  # anonymous class body
                self._members(i + 1, self.close[i], owner)
                i = self.close[i] + 1
        else:
            names, j = [], i
            while self.is_id(j) and (self.val(j) not in _KEYWORDS or self.val(j) == "this"):
                names.append(self.val(j))
                if self.val(j + 1) == "." and self.is_id(j + 2):
                    j += 2
                else:
                    j += 1
                    break
            if not names:
                return i + 1
            if self.val(j) == "(":
                chain.root = ".".join(n for n in names[:-1] if n != "this")
                close = self.close[j]
                chain.calls.append(
                    Call(names[-1], self._args(j, close, owner, method), self.toks[j - 1].line)
                )
                i = close + 1
            else:
                chain.root = ".".join(n for n in names if n != "this")
                i = j
        while self.val(i) == ".":
            j = i + 1
            if self.val(j) == "<":
                end = self._generic_end(j)
                if end is None:
                    break
                j = end + 1
            if not self.is_id(j):
                break
            if self.val(j + 1) == "(":
                close = self.close[j + 1]
                chain.calls.append(
                    Call(self.val(j), self._args(j + 1, close, owner, method), self.toks[j].line)
                )
                i = close + 1
            else:
                i = j + 1
        if chain.calls or chain.new:
            owner.chains.append(chain)
        return max(i, 0)

    def _args(self, paren: int, close: int, owner: TypeDecl, method: Method | None) -> tuple[Expr, ...]:
        self._body(paren + 1, close, owner, method)
        return tuple(self._expr(a, b) for a, b in self._split(paren + 1, close))


def parse(source: str, path: str) -> JavaFile:
    return _Scanner(path, source).parse()
