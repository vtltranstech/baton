"""The first-choice back-end for Java: tree-sitter, in process, when the optional `baton[treesitter]` extra is
installed (contracts/models-and-activation.md section 1).

It builds the same model as helpers/AstDump.java, node for node, so the extractors cannot tell the two apart;
tests/W2/test_parsers.py holds them to that. A file with a syntax error is refused, not half-read: the next
back-end takes it, and a file none can read becomes a question.
"""

from __future__ import annotations

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
from baton.extract.regex_backend import _block_value

NAME = "treesitter"
_TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}
_LOCAL_TYPES = {"class_declaration", "interface_declaration", "record_declaration"}
_ANNOTATIONS = {"annotation", "marker_annotation"}
_LITERALS = {"string_literal", "character_literal"}
_COMMENTS = {"line_comment", "block_comment"}
_PRIMITIVES = {"integral_type", "floating_point_type", "boolean_type", "void_type"}
_parser = None


def _load():
    global _parser
    if _parser is None:
        import tree_sitter
        import tree_sitter_java

        _parser = tree_sitter.Parser(tree_sitter.Language(tree_sitter_java.language()))
    return _parser


def available() -> bool:
    try:
        _load()
    except (ImportError, OSError, ValueError):
        return False
    return True


def version() -> str:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as installed

    try:
        return f"tree-sitter {installed('tree-sitter')}, tree-sitter-java {installed('tree-sitter-java')}"
    except PackageNotFoundError:
        return ""


def parse(source: str, path: str) -> JavaFile:
    try:
        tree = _load().parse(source.encode("utf-8"))
    except (ImportError, OSError, ValueError) as exc:
        raise ParseFailure(f"tree-sitter did not load: {exc}") from exc
    root = tree.root_node
    if root.has_error:
        raise ParseFailure(f"syntax error at line {_first_error(root)}")
    return _Builder(path).file(root)


def _first_error(node) -> int:
    for child in node.children:
        if child.is_error or child.is_missing:
            return _line(child)
        if child.has_error:
            return _first_error(child)
    return _line(node)


# -- tree helpers -------------------------------------------------------------------------------------------


def _line(node) -> int:
    return node.start_point[0] + 1


def _end(node) -> int:
    return node.end_point[0] + 1


def _text(node) -> str:
    return node.text.decode("utf-8")


def _modifiers(node):
    return next((c for c in node.children if c.type == "modifiers"), None)


def _has(node, keyword: str) -> bool:
    modifiers = _modifiers(node)
    return bool(modifiers) and any(c.type == keyword for c in modifiers.children)


def _string(node) -> str:
    raw = _text(node)
    if raw.startswith('"""'):
        return _block_value(raw)
    return unescape(raw[1:-1])


def _anonymous_body(node):
    return next((c for c in node.named_children if c.type == "class_body"), None)


def _is_this(node) -> bool:
    """`this` and `Outer.this`, which JavaParser reads as one ThisExpr."""
    return node.type == "this" or (
        node.type == "field_access" and node.child_by_field_name("field").type == "this"
    )


def _is_super(node) -> bool:
    return node.type == "super" or (
        node.type == "field_access" and node.child_by_field_name("field").type == "super"
    )


def _unwrap(node):
    while node.type == "parenthesized_expression":
        node = node.named_children[0]
    return node


def _dotted(node) -> str | None:
    """`a.b.c` and `this.a` as a dotted name; None for anything else."""
    if node.type == "identifier":
        return _text(node)
    if node.type == "field_access":
        field, scope = node.child_by_field_name("field"), node.child_by_field_name("object")
        if field.type in ("this", "super"):
            return None
        if _is_this(scope):
            return _text(field)
        inner = _dotted(scope)
        return None if inner is None else f"{inner}.{_text(field)}"
    return None


def _strip_type(node):
    """The type under annotations: `@NonNull String` is String."""
    while node.type == "annotated_type":
        node = next(c for c in node.named_children if c.type not in _ANNOTATIONS)
    return node


def _class_name(node) -> str | None:
    """The simple name of a class type, or None for a primitive, array or wildcard."""
    node = _strip_type(node)
    if node.type == "generic_type":
        node = node.named_children[0]
    if node.type == "type_identifier":
        return _text(node)
    if node.type == "scoped_type_identifier":
        return _text([c for c in node.named_children if c.type == "type_identifier"][-1])
    return None


def _type_args(node) -> list:
    node = _strip_type(node)
    if node.type != "generic_type":
        return []
    arguments = next((c for c in node.named_children if c.type == "type_arguments"), None)
    return [] if arguments is None else [_strip_type(a) for a in arguments.named_children]


def _element(node):
    node = _strip_type(node)
    while node.type == "array_type":
        node = _strip_type(node.child_by_field_name("element"))
    return node


def _simple_name(node) -> str:
    node = _element(node)
    if node.type == "wildcard":
        bound = [c for c in node.named_children if c.type not in _ANNOTATIONS]
        return _simple_name(bound[0]) if bound else "?"
    name = _class_name(node)
    return name if name is not None else _text(node)


def _type_ref(node) -> TypeRef:
    node = _element(node)
    name = _class_name(node)
    if name is None:
        return TypeRef(_text(node), ())
    return TypeRef(name, tuple(_simple_name(a) for a in _type_args(node)))


def _short_type(node) -> str:
    """The declared type as written in short form: `Optional<FeeScheduleDoc>`, `List<String>[]`, `void`."""
    node = _strip_type(node)
    if node.type == "array_type":
        dims = node.child_by_field_name("dimensions")
        return _short_type(node.child_by_field_name("element")) + "[]" * _text(dims).count("[")
    if node.type == "wildcard":
        bound = [c for c in node.named_children if c.type not in _ANNOTATIONS]
        extends = any(c.type == "extends" for c in node.children)
        return f"? extends {_short_type(bound[0])}" if bound and extends else "?"
    name = _class_name(node)
    if name is None:
        return _text(node)
    if node.type == "generic_type":
        return f"{name}<{', '.join(_short_type(a) for a in _type_args(node))}>"
    return name


def _type_list(node) -> list[TypeRef]:
    if node is None:
        return []
    types = next((c for c in node.named_children if c.type == "type_list"), node)
    return [_type_ref(t) for t in types.named_children if t.type not in _ANNOTATIONS]


# -- the model ----------------------------------------------------------------------------------------------


class _Builder:
    def __init__(self, path: str):
        self.path = path
        self.package = ""
        self.types: list[TypeDecl] = []

    def file(self, root) -> JavaFile:
        imports, statics = [], []
        for node in root.named_children:
            if node.type == "package_declaration":
                name = next(c for c in node.named_children if c.type in ("identifier", "scoped_identifier"))
                self.package = _text(name)
            elif node.type == "import_declaration":
                name = next(c for c in node.named_children if c.type in ("identifier", "scoped_identifier"))
                text = _text(name) + (".*" if any(c.type == "asterisk" for c in node.children) else "")
                (statics if any(c.type == "static" for c in node.children) else imports).append(text)
        for node in root.named_children:
            if node.type in _TYPES:
                self.type(node, None)
        return JavaFile(
            path=self.path,
            package=self.package,
            imports=imports,
            static_imports=statics,
            types=self.types,
            source=" ".join(self._tokens(root)),
            backend=NAME,
        )

    def _tokens(self, node):
        if node.type in _COMMENTS:
            return
        if node.type in _LITERALS or not node.children:
            if node.type == "@interface":  # one token here, two in JavaParser
                yield from ("@", "interface")
            elif node.end_byte > node.start_byte:
                yield _text(node)
            return
        for child in node.children:
            yield from self._tokens(child)

    # declarations

    def type(self, node, outer: TypeDecl | None) -> None:
        name = node.child_by_field_name("name")
        prefix = outer.fqcn if outer else self.package
        kind = _TYPES[node.type]
        decl = TypeDecl(
            _text(name),
            f"{prefix}.{_text(name)}" if prefix else _text(name),
            kind,
            _line(name),
            self.annotations(_modifiers(node)),
            outer=outer,
            end=_end(node),
        )
        self.types.append(decl)
        if kind == "interface":
            extends = next((c for c in node.children if c.type == "extends_interfaces"), None)
            decl.extends = _type_list(extends)
        elif kind == "class":
            superclass = node.child_by_field_name("superclass")
            decl.extends = [_type_ref(superclass.named_children[-1])] if superclass else []
        if kind != "annotation":
            decl.implements = _type_list(node.child_by_field_name("interfaces"))
        if kind == "record":
            for component in node.child_by_field_name("parameters").named_children:
                if component.type == "formal_parameter":
                    decl.fields.append(self.param(component, final=False))
        body = node.child_by_field_name("body")
        if kind == "enum":
            for constant in (c for c in body.named_children if c.type == "enum_constant"):
                arguments = constant.child_by_field_name("arguments")
                for arg in arguments.named_children if arguments else ():
                    self.walk(arg, decl, None)
                constant_body = constant.child_by_field_name("body")
                for member in constant_body.named_children if constant_body else ():
                    self.member(member, decl)
            body = next((c for c in body.named_children if c.type == "enum_body_declarations"), None)
        for member in body.named_children if body else ():
            self.member(member, decl)

    def member(self, node, owner: TypeDecl) -> None:
        kind = node.type
        if kind in _TYPES:
            self.type(node, owner)
        elif kind in ("field_declaration", "constant_declaration"):
            final = _has(node, "final") or owner.kind in ("interface", "annotation")
            annotations_node = _modifiers(node)
            type_node = node.child_by_field_name("type")
            for declarator in node.children_by_field_name("declarator"):
                value = declarator.child_by_field_name("value")
                init = None
                if value is not None:
                    init = self.expr(value)
                    self.walk(value, owner, None)
                owner.fields.append(
                    Var(
                        _text(declarator.child_by_field_name("name")),
                        _type_ref(type_node),
                        _line(node),
                        self.annotations(annotations_node),
                        final,
                        init,
                    )
                )
        elif kind == "method_declaration":
            method = self.method(node, owner, _short_type(node.child_by_field_name("type")))
            body = node.child_by_field_name("body")
            if body is not None:
                self.walk(body, owner, method)
        elif kind in ("constructor_declaration", "compact_constructor_declaration"):
            method = self.method(node, owner, "")
            self.walk(node.child_by_field_name("body"), owner, method)
        elif kind in ("static_initializer", "block"):
            self.walk(node, owner, None)

    def method(self, node, owner: TypeDecl, returns: str) -> Method:
        parameters = node.child_by_field_name("parameters")
        params = [
            self.param(p, final=_has(p, "final"))
            for p in (parameters.named_children if parameters else ())
            if p.type in ("formal_parameter", "spread_parameter")
        ]
        method = Method(
            _text(node.child_by_field_name("name")),
            _line(node),
            self.annotations(_modifiers(node)),
            params,
            [],
            _end(node),
            returns,
            self.visibility(node, owner.kind),
        )
        owner.methods.append(method)
        return method

    def param(self, node, final: bool) -> Var:
        if node.type == "spread_parameter":
            parts = [c for c in node.named_children if c.type != "modifiers"]
            type_node = next(c for c in parts if c.type != "variable_declarator")
            name = next(c for c in parts if c.type == "variable_declarator").child_by_field_name("name")
        else:
            type_node, name = node.child_by_field_name("type"), node.child_by_field_name("name")
        return Var(_text(name), _type_ref(type_node), _line(node), self.annotations(_modifiers(node)), final)

    @staticmethod
    def visibility(node, kind: str) -> str:
        for keyword in ("public", "protected", "private"):
            if _has(node, keyword):
                return keyword
        return "public" if kind in ("interface", "annotation") else "package"

    def annotations(self, modifiers) -> list[Annotation]:
        out = []
        for node in modifiers.named_children if modifiers else ():
            if node.type not in _ANNOTATIONS:
                continue
            name = node.child_by_field_name("name")
            if name.type == "scoped_identifier":
                name = name.child_by_field_name("name")
            args: dict[str, Expr] = {}
            arguments = node.child_by_field_name("arguments")
            for arg in arguments.named_children if arguments else ():
                if arg.type == "element_value_pair":
                    args[_text(arg.child_by_field_name("key"))] = self.expr(arg.child_by_field_name("value"))
                elif arg.type not in _COMMENTS:
                    args["value"] = self.expr(arg)
            out.append(Annotation(_text(name), _line(node), args))
        return out

    # expressions

    def expr(self, node) -> Expr:
        node = _unwrap(node)
        kind = node.type
        if kind == "string_literal":
            return Expr("str", _string(node))
        dotted = _dotted(node)
        if dotted is not None:
            return Expr("name", dotted)
        if kind == "class_literal":
            type_node = node.named_children[0]
            if type_node.type != "array_type" and type_node.type in _PRIMITIVES:
                return OTHER
            return Expr("cls", _simple_name(type_node))
        if kind == "binary_expression" and node.child_by_field_name("operator").type == "+":
            items: list[Expr] = []
            self.flatten(node, items)
            return Expr("concat", "", tuple(items))
        if kind in ("array_initializer", "element_value_array_initializer"):
            values = [v for v in node.named_children if v.type not in _COMMENTS]
            return Expr("array", "", tuple(self.expr(v) for v in values))
        if kind == "object_creation_expression" and _anonymous_body(node) is None:
            return self.created(node)
        return OTHER

    def created(self, node) -> Expr:
        arguments = node.child_by_field_name("arguments")
        items = tuple(self.expr(a) for a in arguments.named_children if a.type not in _COMMENTS)
        return Expr("new", _class_name(node.child_by_field_name("type")) or "", items)

    def flatten(self, node, items: list[Expr]) -> None:
        node = _unwrap(node)
        if node.type == "binary_expression" and node.child_by_field_name("operator").type == "+":
            self.flatten(node.child_by_field_name("left"), items)
            self.flatten(node.child_by_field_name("right"), items)
        else:
            items.append(self.expr(node))

    # bodies

    def walk(self, node, owner: TypeDecl, method: Method | None) -> None:
        kind = node.type
        if kind in _ANNOTATIONS or kind in _COMMENTS:
            return
        if kind in _LOCAL_TYPES:
            self.type(node, owner)
        elif kind == "local_variable_declaration":
            final = _has(node, "final")
            annotations = self.annotations(_modifiers(node))
            type_node = node.child_by_field_name("type")
            for declarator in node.children_by_field_name("declarator"):
                self.local(declarator.child_by_field_name("name"), type_node,
                           declarator.child_by_field_name("value"), annotations, final, owner, method)
        elif kind == "enhanced_for_statement":
            self.local(node.child_by_field_name("name"), node.child_by_field_name("type"), None,
                       self.annotations(_modifiers(node)), _has(node, "final"), owner, method)
            for child in node.children:
                if child.type not in ("modifiers",) and child != node.child_by_field_name("type") \
                        and child != node.child_by_field_name("name"):
                    self.walk(child, owner, method)
        elif kind == "resource" and node.child_by_field_name("type") is not None:
            self.local(node.child_by_field_name("name"), node.child_by_field_name("type"),
                       node.child_by_field_name("value"), self.annotations(_modifiers(node)),
                       _has(node, "final"), owner, method)
        elif kind in ("method_invocation", "object_creation_expression"):
            self.chain(node, owner, method)
        else:
            for child in node.children:
                self.walk(child, owner, method)

    def local(self, name, type_node, value, annotations, final, owner, method) -> None:
        init = None
        if value is not None:
            init = self.expr(value)
            self.walk(value, owner, method)
        if method is not None:
            method.locals.append(Var(_text(name), _type_ref(type_node), 0, annotations, final, init))

    def chain(self, start, owner: TypeDecl, method: Method | None) -> None:
        calls = []
        base = start
        while True:
            if base.type == "method_invocation":
                calls.append(base)
                base = base.child_by_field_name("object")
                if base is None:
                    break
            elif base.type == "field_access" and not _is_this(base) and not _is_super(base) \
                    and _dotted(base) is None:
                base = base.child_by_field_name("object")
            elif base.type == "array_access":
                self.walk(base.child_by_field_name("index"), owner, method)
                base = base.child_by_field_name("array")
            elif base.type == "parenthesized_expression" and calls:
                base = base.named_children[0]
            else:
                break
        calls.reverse()
        root, created, new_line, drop_first = "", None, 0, False
        dotted = None if base is None else _dotted(base)
        if dotted is not None:
            root = dotted
        elif base is not None and base.type == "object_creation_expression":
            arguments = base.child_by_field_name("arguments")
            for arg in arguments.named_children:
                self.walk(arg, owner, method)
            for scope in base.children:  # `outer.new Inner()`: what comes before `new`
                if scope.type == "new":
                    break
                self.walk(scope, owner, method)
            created = self.created(base)
            new_line = _line(base)
            body = _anonymous_body(base)
            for member in body.named_children if body else ():
                self.member(member, owner)
        elif base is not None and _is_super(base):
            drop_first = True
        elif base is not None and not _is_this(base):
            self.walk(base, owner, method)
        rendered = []
        for index, call in enumerate(calls):
            arguments = call.child_by_field_name("arguments")
            args = [a for a in arguments.named_children if a.type not in _COMMENTS]
            for arg in args:
                self.walk(arg, owner, method)
            if not (drop_first and index == 0):
                name = call.child_by_field_name("name")
                rendered.append(Call(_text(name), tuple(self.expr(a) for a in args), _line(name)))
        if rendered or created is not None:
            owner.chains.append(Chain(root, rendered, created, new_line, method))
