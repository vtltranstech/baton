"""Everything the diagrams read: each repo's code map, the graph edges, the profile. Loaded once per run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from baton import miniyaml
from baton.diagram import codemap
from baton.diagram.codemap import ClassInfo, CodeMap, MethodInfo
from baton.extract.repos import MissingInput, declared_modules, read_repo_table
from baton.graph.loader import dependencies_path, open_for_reading
from baton.graph.model import Edge, node_name, node_prefix
from baton.graph.profile_files import Profile, known, read_profile


@dataclass
class World:
    central: Path
    maps: dict[str, CodeMap]
    edges: list[Edge]
    profile: Profile
    store: object  # the graph store, for impact walks
    missing: list[str] = field(default_factory=list)  # repos named in project.md but not checked out
    collections: dict[str, dict] = field(default_factory=dict)  # name -> dependencies.yaml collection entry
    modules: dict[str, list[str]] = field(default_factory=dict)  # repo -> declared build modules (monorepo)

    # -- deployable units: a declared build module of a monorepo, else the repo itself --

    def unit_of(self, repo: str, file: str) -> str:
        for module in sorted(self.modules.get(repo, []), key=len, reverse=True):
            if file == module or file.startswith(module.rstrip("/") + "/"):
                return module.rsplit("/", 1)[-1]
        return repo

    def unit(self, info: ClassInfo) -> str:
        return self.unit_of(info.repo, info.file)

    def units(self) -> list[str]:
        """Every unit, repo order first, modules sorted inside a repo; a repo with modules and no code of its
        own outside them is not a unit."""
        out = []
        for repo in self.maps:
            mods = [m.rsplit("/", 1)[-1] for m in sorted(self.modules.get(repo, []))]
            out += mods
            if not mods or any(self.unit(c) == repo for c in self.maps[repo].classes.values()):
                out.append(repo)
        return out

    def repo_of_unit(self, unit: str) -> str:
        for repo, mods in self.modules.items():
            if unit in {m.rsplit("/", 1)[-1] for m in mods}:
                return repo
        return unit

    # -- lookups --

    def cls(self, fqcn: str) -> ClassInfo | None:
        for cmap in self.maps.values():
            if fqcn in cmap.classes:
                return cmap.classes[fqcn]
        return None

    def map_of(self, fqcn: str) -> CodeMap | None:
        for cmap in self.maps.values():
            if fqcn in cmap.classes:
                return cmap
        return None

    def classes(self):
        for repo in sorted(self.maps):
            for fqcn in sorted(self.maps[repo].classes):
                yield self.maps[repo].classes[fqcn]

    def implementation(self, fqcn: str) -> str:
        cmap = self.map_of(fqcn)
        return cmap.implementation(fqcn) if cmap else fqcn

    def method(self, fqcn: str, name: str) -> MethodInfo | None:
        info = self.cls(fqcn)
        if info is None:
            return None
        found = info.method(name)
        if not found:
            return None
        return max(found, key=lambda m: (len(m.calls) + len(m.uses), -m.start))

    def nodes(self) -> set[str]:
        return {n for e in self.edges for n in (e.src, e.dst)}

    def edges_to(self, resource: str, *kinds: str) -> list[Edge]:
        return sorted(e for e in self.edges if e.dst == resource and (not kinds or e.kind in kinds))

    def owner(self, edge: Edge) -> tuple[ClassInfo | None, MethodInfo | None]:
        """The class and method an edge was found in."""
        cmap = self.maps.get(edge.repo)
        if cmap is None:
            return None, None
        info = cmap.classes.get(node_name(edge.src))
        if info is None:
            return None, None
        method = next((m for m in info.methods if m.start <= edge.line <= m.end), None)
        return info, method

    def callers(self, fqcn: str, method: str | None = None):
        out = []
        for cmap in self.maps.values():
            out += cmap.callers(fqcn, method)
        return out

    def repo_tech(self, repo: str) -> str:
        row = self.profile.stack.get(repo, {})
        if known(row.get("ui")):
            return "React UI"
        if row.get("build") == "npm":
            return "TypeScript package"
        parts = []
        if known(row.get("spring-boot")):
            parts.append(f"Spring Boot {row['spring-boot']}")
        elif known(row.get("java")):
            parts.append(f"Java {row['java']}")
        if row.get("batch") == "true":
            parts.append("Batch")
        return " / ".join(parts) or "service"

    def datastore(self) -> str:
        for repo in sorted(self.profile.stack):
            value = self.profile.stack[repo].get("datastore")
            if known(value):
                return value.split(",")[0].strip()
        return "datastore"

    def broker(self, resource: str) -> str:
        tokens = []
        for repo in sorted(self.profile.stack):
            value = self.profile.stack[repo].get("messaging")
            if known(value):
                tokens += [t.strip() for t in value.replace(";", ",").split(",") if t.strip()]
        if node_prefix(resource) == "queue":
            for token in tokens:
                if token.lower().startswith(("jms", "mq", "ibm", "activemq", "artemis", "rabbit")):
                    return token
        for token in tokens:
            if token.lower().startswith("kafka"):
                return token
        return tokens[0] if tokens else "broker"

    def commits(self) -> str:
        return ", ".join(f"{repo} @ {self.maps[repo].commit}" for repo in sorted(self.maps))


def load_world(central: Path) -> World:
    central = Path(central)
    store = open_for_reading(central)
    edges = store.edges()
    maps: dict[str, CodeMap] = {}
    modules: dict[str, list[str]] = {}
    missing = []
    try:
        repos = read_repo_table(central)
    except MissingInput:
        repos = []
    for repo in repos:
        if not repo.path.is_dir():
            missing.append(repo.name)
            continue
        maps[repo.name] = codemap.load(central, repo, edges)
        modules[repo.name] = declared_modules(repo.path)
    collections = {}
    path = dependencies_path(central)
    if path.is_file():
        try:
            document = miniyaml.load_file(str(path)) or {}
        except ValueError:
            document = {}
        for entry in document.get("repos") or []:
            for item in entry.get("collections") or []:
                if isinstance(item, dict) and item.get("name"):
                    collections.setdefault(str(item["name"]), item)
    return World(central, maps, edges, read_profile(central), store, missing, collections, modules)
