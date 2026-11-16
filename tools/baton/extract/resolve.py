"""Turns a parsed expression into a target value, or says plainly that it cannot be read."""

from __future__ import annotations

from dataclasses import dataclass, field

from baton.extract.config import Config
from baton.extract.model import Expr, JavaFile, Method, TypeDecl, Var


@dataclass
class TypeIndex:
    """Every type in a repo, for resolving constants and document classes across files."""

    by_fqcn: dict[str, TypeDecl] = field(default_factory=dict)
    file_of: dict[str, JavaFile] = field(default_factory=dict)  # fqcn -> file

    def add(self, parsed: JavaFile) -> None:
        for decl in parsed.types:
            self.by_fqcn[decl.fqcn] = decl
            self.file_of[decl.fqcn] = parsed

    def find(self, name: str, context: TypeDecl) -> TypeDecl | None:
        """A simple or dotted type name from `context`: nesting, imports, same package, or fully qualified."""
        head, _, rest = name.partition(".")
        parsed = self.file_of.get(context.fqcn)
        candidates = []
        scope: TypeDecl | None = context
        while scope is not None:
            candidates.append(f"{scope.fqcn}.{head}")
            scope = scope.outer
        if parsed is not None:
            candidates += [imp for imp in parsed.imports if imp.rsplit(".", 1)[-1] == head]
            if parsed.package:
                candidates.append(f"{parsed.package}.{head}")
            candidates += [imp[:-1] + head for imp in parsed.imports if imp.endswith(".*")]
        candidates.append(head)
        for candidate in candidates:
            found = self.by_fqcn.get(candidate if not rest else f"{candidate}.{rest}")
            if found is not None:
                return found
        return self.by_fqcn.get(name)


def field_of(decl: TypeDecl, name: str) -> tuple[Var, TypeDecl] | None:
    scope: TypeDecl | None = decl
    while scope is not None:
        for var in scope.fields:
            if var.name == name:
                return var, scope
        scope = scope.outer
    return None


def variable(name: str, decl: TypeDecl, method: Method | None) -> tuple[Var, TypeDecl] | None:
    if method is not None:
        for var in [*method.locals, *method.params]:
            if var.name == name:
                return var, decl
    return field_of(decl, name)


@dataclass
class Resolver:
    index: TypeIndex
    config: Config

    def value(self, expr: Expr, decl: TypeDecl, method: Method | None, line: int) -> tuple[str, bool]:
        """(text, resolved). Unresolved text stays recognisable: `${...}` as written, or `<Class.name>` naming
        the source expression, so two unrelated unknowns never become one graph node."""
        text, ok = self._value(expr, decl, method, line, frozenset())
        if ok and (not text or "\n" in text or "#{" in text):
            return (text if text and "\n" not in text else f"<{decl.name}:{line}>"), False
        return text, ok

    def _opaque(self, decl: TypeDecl, line: int) -> tuple[str, bool]:
        return f"<{decl.name}:{line}>", False

    def _value(self, expr, decl, method, line, seen) -> tuple[str, bool]:
        if expr.kind == "str":
            return self.config.expand(expr.value)
        if expr.kind == "concat":
            parts = [self._value(item, decl, method, line, seen) for item in expr.items]
            return "".join(p[0] for p in parts), all(p[1] for p in parts)
        if expr.kind == "name":
            return self._name(expr.value, decl, method, line, seen)
        return self._opaque(decl, line)

    def _var_value(self, var: Var, owner, method, line, seen) -> tuple[str, bool] | None:
        for annotation in var.annotations:
            if annotation.name == "Value" and "value" in annotation.args:
                return self._value(annotation.args["value"], owner, method, line, seen)
        if var.final and var.init is not None:
            return self._value(var.init, owner, method, line, seen)
        return None

    def _name(self, name, decl, method, line, seen) -> tuple[str, bool]:
        literal = f"<{decl.name}.{name}>", False
        key = (decl.fqcn, name)
        if key in seen:
            return literal
        seen = seen | {key}
        if "." not in name:
            found = variable(name, decl, method)
            if found is not None:
                # A constant's initializer lives in its own scope, not the method that reads it.
                var, owner = found
                in_method = owner is decl and method is not None and var not in decl.fields
                return self._var_value(var, owner, method if in_method else None, line, seen) or literal
            return self._static_import(name, decl, line, seen) or literal
        owner_name, _, member = name.rpartition(".")
        owner = self.index.find(owner_name, decl)
        if owner is not None:
            found = field_of(owner, member)
            if found is not None:
                return self._var_value(found[0], found[1], None, line, seen) or literal
        return literal

    def _static_import(self, name, decl, line, seen) -> tuple[str, bool] | None:
        parsed = self.index.file_of.get(decl.fqcn)
        for imported in parsed.static_imports if parsed else []:
            owner_name, _, member = imported.rpartition(".")
            if member in (name, "*") and owner_name in self.index.by_fqcn:
                found = field_of(self.index.by_fqcn[owner_name], name)
                if found is not None:
                    return self._var_value(found[0], found[1], None, line, seen)
        return None
