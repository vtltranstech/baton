"""TypeScript and JavaScript through the TypeScript compiler API: helpers/tsdump.cjs, one Node per repo.

The extractor names `ts-fetch` and `ts-axios` are additions to contracts/artefacts.md section 2.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

_HERE = Path(__file__).parent
HELPER = _HERE / "helpers" / "tsdump.cjs"
VENDORED = _HERE / "vendor" / "typescript-5.9.3.js"
_ROOTS = ("src", "app", "pages", "lib")
_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs"}
_NEVER = {"node_modules", "dist", "build", "coverage", "__tests__", "__mocks__"}
_NOT_SOURCE = re.compile(r"\.(test|spec|stories|d)\.[cm]?[jt]sx?$")
_TIMEOUT = 900


def source_files(repo: Path) -> list[Path]:
    if not (repo / "package.json").is_file():
        return []
    found: list[Path] = []
    for name in _ROOTS:
        for current, dirs, files in os.walk(repo / name):
            dirs[:] = sorted(d for d in dirs if d not in _NEVER and not d.startswith("."))
            found += [
                Path(current) / f
                for f in sorted(files)
                if Path(f).suffix in _SUFFIXES and not _NOT_SOURCE.search(f)
            ]
    return found


def endpoint(method: str, url: str | None, rel: str, line: int) -> tuple[str, bool]:
    """(graph node, resolved). A value the file cannot tell stays literal and has no method, as for Java."""
    if url is None:
        return f"endpoint:<{rel}:{line}>", False
    path = re.split(r"[?#]", url, maxsplit=1)[0]
    if "${" in path or not path:
        return f"endpoint:{path or url}", False
    return f"endpoint:{method} {path}", True


def node_of(rel: str) -> str:
    return "class:" + str(Path(rel).with_suffix("")).replace(os.sep, ".")


def extract(repo: Path) -> dict:
    """{parser, edges, unresolved, failures}; parser is None for a repo with no such sources."""
    files = source_files(repo)
    if not files:
        return {"parser": None, "edges": [], "unresolved": [], "failures": []}
    node = shutil.which("node")
    if not node:
        reason = "Node is not on the PATH: TypeScript sources were not read"
        return {
            "parser": {"files": 0, "unavailable": True},
            "edges": [],
            "unresolved": [],
            "failures": [{"file": "package.json", "reason": reason}],
        }
    root = repo.resolve()
    done = subprocess.run(
        [node, str(HELPER), str(root), str(VENDORED)],
        input="\n".join(str(p.resolve()) for p in files) + "\n",
        capture_output=True,
        encoding="utf-8",
        timeout=_TIMEOUT,
    )
    lines = done.stdout.splitlines()
    if done.returncode != 0 or len(lines) != len(files) + 1:
        reason = f"tsdump exited {done.returncode}: {done.stderr.strip()[:300]}"
        return {
            "parser": {"files": 0, "unavailable": True},
            "edges": [],
            "unresolved": [],
            "failures": [{"file": "package.json", "reason": reason}],
        }
    edges: dict[tuple, dict] = {}
    unresolved: set[str] = set()
    failures = []
    parsed = 0
    for path, line in zip(files, lines[1:], strict=True):
        rel = path.resolve().relative_to(root).as_posix()
        data = json.loads(line)
        if not data["ok"]:
            failures.append({"file": rel, "reason": data["reason"]})
            continue
        parsed += 1
        for call in data["calls"]:
            target, resolved = endpoint(call["method"], call["url"], rel, call["line"])
            if not resolved:
                unresolved.add(target)
            edges.setdefault(
                (rel, call["line"], target),
                {
                    "kind": "CALLS_ENDPOINT",
                    "from": node_of(rel),
                    "to": target,
                    "provenance": {"file": rel, "line": call["line"], "extractor": call["extractor"]},
                },
            )
    version = json.loads(lines[0])["typescript"]
    return {
        "parser": {"files": parsed, "typescript": version, "unavailable": False},
        "edges": [edges[k] for k in sorted(edges)],
        "unresolved": sorted(unresolved),
        "failures": failures,
    }
