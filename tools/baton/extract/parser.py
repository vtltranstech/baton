"""The parser interface: tree-sitter if the `baton[treesitter]` extra is installed, else JavaParser if a JDK
is there, else the regex back-end (contracts/models-and-activation.md section 1).

Fallback is per file and recorded on the file (`backend`, `fallback_reason`). BATON_JAVA_PARSER names the
first back-end to try: `javaparser` skips tree-sitter, `regex` forces the regex back-end. A file no back-end
reads raises ParseFailure and is reported, never half-extracted.
"""

from __future__ import annotations

import os
from pathlib import Path

from baton.extract import javaparser_backend, regex_backend, treesitter_backend
from baton.extract.model import JavaFile, ParseFailure

ORDER = ("treesitter", "javaparser", "regex")
AST = ORDER[:-1]
_AVAILABLE = {"treesitter": treesitter_backend.available, "javaparser": javaparser_backend.available}


def backends(use_ast: bool | None = None) -> list[str]:
    """The back-ends to try, in order. use_ast False is regex only; True or None follows the environment."""
    if use_ast is False:
        return ["regex"]
    names = ("BATON_JAVA_PARSER", "POD_JAVA_PARSER", "HARNESS_JAVA_PARSER")  # the last two: older names
    choice = next((os.environ[n] for n in names if os.environ.get(n)), ORDER[0])
    start = ORDER.index(choice) if choice in ORDER else 0
    return [name for name in ORDER[start:] if name == "regex" or _AVAILABLE[name]()]


def ast_usable() -> bool:
    return backends()[0] != "regex"


def _regex(source: str, path: str, reason: str) -> JavaFile:
    parsed = regex_backend.parse(source, path)
    if not parsed.types and not path.endswith(("package-info.java", "module-info.java")):
        raise ParseFailure(reason or "no type declaration found")
    parsed.fallback_reason = reason
    return parsed


def _reason(reasons: list[str]) -> str:
    return "; ".join(reasons)


def parse_java(source: str, path: str, use_ast: bool | None = None) -> JavaFile:
    reasons: list[str] = []
    for name in backends(use_ast):
        if name == "regex":
            return _regex(source, path, _reason(reasons))
        try:
            backend = treesitter_backend if name == "treesitter" else javaparser_backend
            parsed = backend.parse(source, path)
        except ParseFailure as exc:
            reasons.append(f"{name}: {exc}")
            continue
        parsed.fallback_reason = _reason(reasons)
        return parsed
    raise ParseFailure(_reason(reasons))


def parse_java_many(
    items: list[tuple[Path, str, str]], use_ast: bool | None = None
) -> list[JavaFile | ParseFailure]:
    """(file on disk, repo-relative path, text) to one result each; JavaParser runs one JVM for its share."""
    out: list[JavaFile | ParseFailure | None] = [None] * len(items)
    reasons: list[list[str]] = [[] for _ in items]
    for name in backends(use_ast):
        todo = [i for i, result in enumerate(out) if result is None]
        if not todo:
            break
        if name == "treesitter":
            results = []
            for i in todo:
                try:
                    results.append(treesitter_backend.parse(items[i][2], items[i][1]))
                except ParseFailure as exc:
                    results.append(exc)
        elif name == "javaparser":
            results = javaparser_backend.parse_many([(items[i][0], items[i][1]) for i in todo])
        else:
            results = []
            for i in todo:
                try:
                    results.append(_regex(items[i][2], items[i][1], _reason(reasons[i])))
                except ParseFailure as exc:
                    results.append(exc)
        for i, result in zip(todo, results, strict=True):
            if isinstance(result, JavaFile):
                if name != "regex":
                    result.fallback_reason = _reason(reasons[i])
                out[i] = result
            elif name == "regex":
                out[i] = result
            else:
                reasons[i].append(f"{name}: {result}")
    return [r if r is not None else ParseFailure(_reason(reasons[i])) for i, r in enumerate(out)]


__all__ = [
    "AST", "ORDER", "JavaFile", "ParseFailure", "ast_usable", "backends", "parse_java", "parse_java_many",
]
