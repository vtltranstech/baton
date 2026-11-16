"""What the extractors say about a repo: its modules, and each module's claims from dependencies.yaml.

Shared by `wiki` (which writes claims) and `verify` (which checks them), so the two can never read the same
edge differently. Claims are read from dependencies.yaml itself, never from the graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from baton import miniyaml
from baton.extract.repos import UNKNOWN, MissingInput, RepoRef, declared_modules

DEPENDENCIES_FILE = "profile/dependencies.yaml"
STACK_FILE = "profile/stack-detected.md"
ROOT_MODULE = "_root"
CATEGORIES = ("collections", "topics", "endpoints", "calls", "files")
_CLAIM_OF_KIND = {
    "READS_COLLECTION": "collections",
    "WRITES_COLLECTION": "collections",
    "PUBLISHES": "topics",
    "CONSUMES": "topics",
    "EXPOSES": "endpoints",
    "CALLS_ENDPOINT": "calls",
    "READS_FILE": "files",
    "WRITES_FILE": "files",
}
_STRIP = {
    "collections": "collection:",
    "topics": "topic:",
    "endpoints": "endpoint:",
    "calls": "endpoint:",
    "files": "file:",
}
_SOURCE_ROOTS = {"main": "src/main/java/", "test": "src/test/java/"}


@dataclass
class Layout:
    """The stack-detected row's package root and layers. Unknown values simply never match."""

    root: str
    layers: dict[str, str]

    def module_of(self, package: str) -> str:
        best, best_len = None, -1
        for layer, base in self.layers.items():
            if (
                base != UNKNOWN
                and (package == base or package.startswith(base + "."))
                and len(base) > best_len
            ):
                best, best_len = layer + package[len(base) :], len(base)
        if best is not None:
            return best
        if self.root != UNKNOWN and package == self.root:
            return ROOT_MODULE
        if self.root != UNKNOWN and package.startswith(self.root + "."):
            return package[len(self.root) + 1 :]
        return package or ROOT_MODULE


@dataclass
class Module:
    name: str
    sources: list[Path] = field(default_factory=list)
    tests: list[Path] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    def class_names(self) -> list[str]:
        return sorted(path.stem for path in self.sources)


@dataclass
class RepoFacts:
    repo: RepoRef
    commit: str
    modules: dict[str, Module]
    unassigned: list[dict]

    def claims(self, name: str) -> dict[str, list[str]]:
        module = self.modules.get(name)
        return claims_of(module.edges if module else [])


def claim_value(edge: dict) -> tuple[str, str] | None:
    """(category, claim text) for an edge, or None for a kind with no claim category (RUNS_JOB). A queue keeps
    its prefix, so it stays apart from a topic of the same name."""
    category = _CLAIM_OF_KIND.get(edge.get("kind"))
    if category is None:
        return None
    return category, str(edge["to"]).removeprefix(_STRIP[category])


def claims_of(edges: list[dict]) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {category: set() for category in CATEGORIES}
    for edge in edges:
        value = claim_value(edge)
        if value:
            found[value[0]].add(value[1])
    return {category: sorted(values) for category, values in found.items()}


def read_layout(central: Path, repo_name: str) -> Layout:
    path = central / STACK_FILE
    if not path.is_file():
        raise MissingInput(f"{path} not found: run baton extract first")
    columns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not columns:
            columns = cells
            continue
        row = dict(zip(columns, cells, strict=False))
        if row.get("repo") == repo_name:
            layers = dict(part.split("=", 1) for part in row.get("layout", "").split(";") if "=" in part)
            return Layout(row.get("package root", UNKNOWN), layers)
    raise MissingInput(f"{path} has no row for {repo_name}: run baton extract first")


def read_dependencies(central: Path, repo_name: str) -> dict:
    path = central / DEPENDENCIES_FILE
    if not path.is_file():
        raise MissingInput(f"{path} not found: run baton extract first")
    try:
        document = miniyaml.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise MissingInput(f"{path} cannot be read: {exc}") from exc
    for entry in document.get("repos") or []:
        if entry.get("repo") == repo_name:
            return entry
    raise MissingInput(f"{path} has no entry for {repo_name}: run baton extract first")


def package_of(rel_path: str, kind: str = "main") -> str | None:
    """The package a repo-relative file sits in by its path, or None when it is not under that source root."""
    marker = _SOURCE_ROOTS[kind]
    if not rel_path.startswith(marker):
        marker = "/" + marker
    head, found, tail = rel_path.partition(marker)
    if not found or not tail.endswith(".java") or (head and marker[0] != "/"):
        return None
    return ".".join(tail.split("/")[:-1])


def _walk(root: Path, kind: str, modules: list[str]) -> list[Path]:
    found: list[Path] = []
    for module in [".", *modules]:
        base = root / module / "src" / kind / "java"
        if base.is_dir():
            found += [
                p
                for p in sorted(base.rglob("*.java"))
                if p.name not in ("package-info.java", "module-info.java")
            ]
    return found


def load_facts(central: Path, repo: RepoRef) -> RepoFacts:
    """Raises MissingInput when a generated profile file is absent or has nothing on this repo."""
    entry = read_dependencies(central, repo.name)
    layout = read_layout(central, repo.name)
    build_modules = declared_modules(repo.path)
    modules: dict[str, Module] = {}
    for path in _walk(repo.path, "main", build_modules):
        package = package_of(path.relative_to(repo.path).as_posix(), "main")
        if package is not None:
            name = layout.module_of(package)
            modules.setdefault(name, Module(name)).sources.append(path)
    for path in _walk(repo.path, "test", build_modules):
        package = package_of(path.relative_to(repo.path).as_posix(), "test")
        if package is not None and layout.module_of(package) in modules:
            modules[layout.module_of(package)].tests.append(path)
    unassigned: list[dict] = []
    for edge in entry.get("edges") or []:
        package = package_of(str((edge.get("provenance") or {}).get("file", "")), "main")
        module = modules.get(layout.module_of(package)) if package is not None else None
        if module is None:
            unassigned.append(edge)
        else:
            module.edges.append(edge)
    return RepoFacts(repo, str(entry.get("commit", UNKNOWN)), modules, unassigned)


def module_of_file(rel_path: str, layout: Layout) -> str | None:
    """The module a changed repo file belongs to, main or test."""
    for kind in _SOURCE_ROOTS:
        package = package_of(rel_path, kind)
        if package is not None:
            return layout.module_of(package)
    return None


_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.M)


def imports_of(path: Path) -> list[str]:
    try:
        return _IMPORT.findall(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []
