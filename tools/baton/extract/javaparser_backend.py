"""The AST back-end for Java: JavaParser (vendor/) through helpers/AstDump.java, one JVM per batch."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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
)

NAME = "javaparser"
_HERE = Path(__file__).parent
JAR = _HERE / "vendor" / "javaparser-core-3.28.2.jar"
HELPER = _HERE / "helpers" / "AstDump.java"
_TIMEOUT = 900


def _tool(name: str) -> str | None:
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / name).is_file():
        return str(Path(home) / "bin" / name)
    return shutil.which(name)


def available() -> bool:
    return bool(_tool("java") and _tool("javac") and JAR.is_file())


def _compiled() -> Path:
    """Compile the helper once per helper version, into a per-user cache."""
    digest = hashlib.sha256(HELPER.read_bytes() + JAR.name.encode()).hexdigest()[:16]
    target = Path(tempfile.gettempdir()) / f"baton-astdump-{getattr(os, 'getuid', int)()}-{digest}"
    if (target / "AstDump.class").is_file():
        return target
    temp = Path(tempfile.mkdtemp(prefix="baton-astdump-"))
    done = subprocess.run(
        [_tool("javac"), "-nowarn", "-cp", str(JAR), "-d", str(temp), str(HELPER)],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if done.returncode != 0:
        shutil.rmtree(temp, ignore_errors=True)
        raise ParseFailure(f"AstDump did not compile: {done.stderr.strip()[:300]}")
    try:
        os.replace(temp, target)
    except OSError:  # another run got there first
        shutil.rmtree(temp, ignore_errors=True)
    return target


def parse_many(items: list[tuple[Path, str]]) -> list[JavaFile | ParseFailure]:
    """(file on disk, repo-relative path) to one result per item, in order. A bad file fails alone."""
    if not items:
        return []
    try:
        classes = _compiled()
        done = subprocess.run(
            [_tool("java"), "-cp", os.pathsep.join((str(classes), str(JAR))), "AstDump"],
            input="\n".join(str(path.resolve()) for path, _ in items) + "\n",
            capture_output=True,
            encoding="utf-8",
            timeout=_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError, ParseFailure) as exc:
        return [ParseFailure(f"JavaParser did not run: {exc}") for _ in items]
    lines = done.stdout.splitlines()
    if done.returncode != 0 or len(lines) != len(items):
        reason = f"JavaParser exited {done.returncode}: {done.stderr.strip()[:300]}"
        return [ParseFailure(reason) for _ in items]
    return [_read(json.loads(line), rel) for line, (_, rel) in zip(lines, items, strict=True)]


def parse(source: str, path: str) -> JavaFile:
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / "Source.java"
        file.write_text(source, encoding="utf-8")
        result = parse_many([(file, path)])[0]
    if isinstance(result, ParseFailure):
        raise result
    return result


# -- JSON to model ------------------------------------------------------------------------------------------


def _expr(node: dict | None) -> Expr:
    if not node or node["k"] == "other":
        return OTHER
    return Expr(node["k"], node.get("v", ""), tuple(_expr(i) for i in node.get("i", ())))


def _annotations(nodes: list[dict]) -> list[Annotation]:
    return [Annotation(n["name"], n["line"], {k: _expr(v) for k, v in n["args"].items()}) for n in nodes]


def _ref(node: dict) -> TypeRef:
    return TypeRef(node["name"], tuple(node["args"]))


def _var(node: dict) -> Var:
    return Var(
        node["name"],
        _ref(node["type"]),
        node["line"],
        _annotations(node["annotations"]),
        node["final"],
        _expr(node["init"]) if node["init"] else None,
    )


def _read(data: dict, path: str) -> JavaFile | ParseFailure:
    if not data["ok"]:
        return ParseFailure(data["reason"])
    file = JavaFile(
        path=path,
        package=data["package"],
        imports=data["imports"],
        static_imports=data["static_imports"],
        source=data["source"],
        backend=NAME,
    )
    for node in data["types"]:
        decl = TypeDecl(
            node["name"],
            node["fqcn"],
            node["kind"],
            node["line"],
            _annotations(node["annotations"]),
            [_ref(r) for r in node["extends"]],
            [_ref(r) for r in node["implements"]],
            [_var(f) for f in node["fields"]],
            outer=file.types[node["outer"]] if node["outer"] >= 0 else None,
            end=node.get("end", 0),
        )
        for m in node["methods"]:
            decl.methods.append(
                Method(
                    m["name"],
                    m["line"],
                    _annotations(m["annotations"]),
                    [_var(p) for p in m["params"]],
                    [_var(v) for v in m["locals"]],
                    m.get("end", 0),
                    m.get("ret", ""),
                    m.get("vis", ""),
                )
            )
        for c in node["chains"]:
            decl.chains.append(
                Chain(
                    c["root"],
                    [Call(k["name"], tuple(_expr(a) for a in k["args"]), k["line"]) for k in c["calls"]],
                    _expr(c["new"]) if c["new"] else None,
                    c["new_line"],
                    decl.methods[c["method"]] if c["method"] >= 0 else None,
                )
            )
        file.types.append(decl)
    return file
