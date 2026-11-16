"""The page sections the extractors decide. Each fact here is an edge or an import, with its file and line."""

from __future__ import annotations

import re
from pathlib import Path

from baton.wiki.facts import Layout, Module, RepoFacts, imports_of, package_of

_ENTRY_KINDS = ("EXPOSES", "CONSUMES", "RUNS_JOB")
_DATA_KINDS = (
    "READS_COLLECTION",
    "WRITES_COLLECTION",
    "READS_FILE",
    "WRITES_FILE",
    "PUBLISHES",
    "CONSUMES",
)
PITFALLS_FILE = "docs/context/pitfalls-log.md"
_TYPE = re.compile(
    r"(?:/\*\*(?P<doc>(?:(?!\*/).)*)\*/\s*)?(?:@\w+(?:\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private|abstract|final|sealed|non-sealed|static)\s+)*"
    r"(?:class|interface|enum|record|@interface)\s+(?P<name>\w+)",
    re.S,
)
_TEST = re.compile(
    r"(?P<notes>(?:@\w+(?:\([^)]*\))?\s*)*@(?:Test|ParameterizedTest|RepeatedTest)\b(?:\([^)]*\))?\s*"
    r"(?:@\w+(?:\([^)]*\))?\s*)*)(?:(?:public|protected|private|static|final)\s+)*void\s+(?P<name>\w+)",
)
_DISPLAY = re.compile(r'@DisplayName\(\s*"((?:[^"\\]|\\.)*)"')


def _first_sentence(doc: str) -> str:
    lines = [ln.strip().lstrip("*").strip() for ln in doc.splitlines()]
    text = " ".join(ln for ln in lines if ln and not ln.startswith("@"))
    text = re.sub(r"<[^>]+>|\{@\w+\s+([^}]*)\}", r"\1", text).strip()
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0] if text else ""


def purpose_from_code(module: Module) -> str:
    """Each type with the first sentence of its Javadoc: read from the code, no model."""
    lines = []
    for path in module.sources:
        source = path.read_text(encoding="utf-8", errors="replace")
        match = _TYPE.search(source)
        if match is None:
            continue
        sentence = _first_sentence(match.group("doc") or "")
        lines.append(f"- `{match.group('name')}`" + (f": {sentence}" if sentence else ""))
    if not lines:
        return "No types found in this module's sources."
    heading = "Types in this module, with the first line of each one's Javadoc (read from the code):"
    return heading + "\n" + "\n".join(sorted(lines))


def invariants_from_tests(module: Module) -> str:
    """One bullet per test method, with its @DisplayName when it has one: the names, not a judgement."""
    lines = []
    for path in module.tests:
        source = path.read_text(encoding="utf-8", errors="replace")
        for match in _TEST.finditer(source):
            display = _DISPLAY.search(match.group("notes"))
            name = f"- `{path.stem}.{match.group('name')}`"
            lines.append(name + (f": {display.group(1)}" if display else ""))
    if not module.tests:
        return "None observed: no tests for this module."
    if not lines:
        return "No test methods found in this module's test files."
    return "Test methods for this module (names read from the code):\n" + "\n".join(lines)


def prose_from_code(module: Module) -> dict:
    return {
        "Purpose": purpose_from_code(module),
        "Invariants observed in tests": invariants_from_tests(module),
    }


def edge_line(edge: dict) -> str:
    provenance = edge.get("provenance") or {}
    return f"- {edge['kind']} `{edge['to']}` ({provenance.get('file')}:{provenance.get('line')})"


def edges_text(edges: list[dict]) -> str:
    return "\n".join(f"{e['kind']} {e['from']} -> {e['to']}" for e in edges)


def _listing(edges: list[dict], kinds: tuple[str, ...]) -> str:
    lines = sorted(edge_line(e) for e in edges if e["kind"] in kinds)
    return "\n".join(lines) if lines else "None found by the extractors."


def _class_modules(facts: RepoFacts, layout: Layout) -> dict[str, str]:
    """FQCN of each source file to its module, from its path."""
    found = {}
    for module in facts.modules.values():
        for path in module.sources:
            package = package_of(path.relative_to(facts.repo.path).as_posix())
            found[f"{package}.{path.stem}"] = module.name
    return found


def _uses(module: Module, classes: dict[str, str]) -> list[str]:
    used = set()
    for path in module.sources:
        for name in imports_of(path):
            target = classes.get(name)
            if target and target != module.name:
                used.add(target)
    return sorted(used)


def _calls_section(module: Module, facts: RepoFacts, layout: Layout) -> str:
    classes = _class_modules(facts, layout)
    called_by = sorted(other.name for other in facts.modules.values() if module.name in _uses(other, classes))
    uses = _uses(module, classes)
    return "\n".join(
        [
            _listing(module.edges, ("CALLS_ENDPOINT",)),
            "",
            f"Imports from modules in this repo (not a claim): {', '.join(uses) or 'none'}.",
            f"Imported by modules in this repo (not a claim): {', '.join(called_by) or 'none'}.",
            "Callers in other repos: ask `baton impact`.",
        ]
    )


def _pitfalls(central: Path, module: Module) -> str:
    log = central / PITFALLS_FILE
    if not log.is_file():
        return "None recorded."
    words = [module.name, *module.class_names()]
    pattern = re.compile(r"(?<![\w.])(?:" + "|".join(re.escape(w) for w in words) + r")(?![\w])")
    lines = [
        ln for ln in log.read_text(encoding="utf-8", errors="replace").splitlines() if pattern.search(ln)
    ]
    return "\n".join(lines) if lines else "None recorded."


def compose(repo: str, module: Module, facts: RepoFacts, layout: Layout, central: Path, prose: dict) -> str:
    """Everything before Last verified. Only Purpose and Invariants come from the model."""
    return "\n".join(
        [
            "",
            f"# {repo} / {module.name}",
            "",
            "## Purpose",
            prose["Purpose"],
            "",
            "## Entry points",
            _listing(module.edges, _ENTRY_KINDS),
            "",
            "## Reads / Writes",
            _listing(module.edges, _DATA_KINDS),
            "",
            "## Calls / Called by",
            _calls_section(module, facts, layout),
            "",
            "## Invariants observed in tests",
            prose["Invariants observed in tests"],
            "",
            "## Known pitfalls",
            _pitfalls(central, module),
            "",
        ]
    )
