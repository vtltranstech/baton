"""Idempotent loader from profile/dependencies.yaml; refuses the whole file if any edge lacks provenance."""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from pathlib import Path

from baton import miniyaml
from baton.graph.model import EDGE_KINDS, Edge, node_kind
from baton.graph.profile_files import read_profile
from baton.graph.sqlite_store import SqliteStore

DEPENDENCIES = "profile/dependencies.yaml"
GRAPH_FILE = ".baton/graph.sqlite"
_FINGERPRINT = "dependencies_sha256"
_ENDPOINT = re.compile(r"^endpoint:([A-Z]+) (?:[a-z][a-z0-9+.-]*://[^/]+)?(/[^?#]*)?(?:[?#].*)?$")


class LoadError(Exception):
    """The input is invalid; `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


class MissingInput(Exception):
    pass


def _parse_edge(repo: str, repo_commit, index: int, raw, problems: list[str]) -> Edge | None:
    where = f"{repo} edge {index}"
    if not isinstance(raw, dict):
        problems.append(f"{where}: not a mapping")
        return None
    start = len(problems)
    kind, src, dst, prov = raw.get("kind"), raw.get("from"), raw.get("to"), raw.get("provenance")
    if kind not in EDGE_KINDS:
        problems.append(f"{where}: unknown kind {kind!r}")
    for label, node in (("from", src), ("to", dst)):
        if not isinstance(node, str) or node_kind(node) is None:
            problems.append(f"{where}: {label} {node!r} is not a contract node id")
    if not isinstance(prov, dict):
        problems.append(f"{where}: provenance is mandatory")
        return None
    file, line, extractor = prov.get("file"), prov.get("line"), prov.get("extractor")
    commit = prov.get("commit", repo_commit)
    if not file or not isinstance(file, str):
        problems.append(f"{where}: provenance.file is mandatory")
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        problems.append(f"{where}: provenance.line must be a positive integer")
    if not extractor or not isinstance(extractor, str):
        problems.append(f"{where}: provenance.extractor is mandatory")
    if commit in (None, ""):
        problems.append(f"{where}: provenance.commit is mandatory (from the edge or its repo)")
    if len(problems) > start:
        return None
    return Edge(kind, src, dst, repo, file, line, extractor, str(commit))


def parse_dependencies(document) -> dict[str, list[Edge]]:
    problems: list[str] = []
    result: dict[str, list[Edge]] = {}
    repos = document.get("repos") if isinstance(document, dict) else None
    if not isinstance(repos, list):
        raise LoadError([f"{DEPENDENCIES}: `repos` must be a list"])
    for entry in repos:
        name = entry.get("repo") if isinstance(entry, dict) else None
        if not name or not isinstance(name, str):
            problems.append(f"repo entry without a name: {entry!r}")
            continue
        if entry.get("commit") in (None, ""):
            problems.append(f"{name}: commit is mandatory")
        raw_edges = entry.get("edges") or []
        if not isinstance(raw_edges, list):
            problems.append(f"{name}: edges must be a list")
            continue
        parsed = [_parse_edge(name, entry.get("commit"), i, raw, problems) for i, raw in enumerate(raw_edges)]
        result[name] = [edge for edge in parsed if edge is not None]
    if problems:
        raise LoadError(problems)
    return result


def _endpoint_key(node: str) -> tuple[str, str] | None:
    """(METHOD, path) ignoring the base URL and path-variable names; None for an unresolved literal."""
    match = _ENDPOINT.match(node)
    if not match:
        return None
    path = re.sub(r"\{[^}]*\}", "{}", match.group(2) or "/").rstrip("/") or "/"
    return match.group(1), path


def _unit(repo: str, file: str) -> tuple[str, str]:
    """(repo, top folder): `src` for a single-module repo, the module folder in a monorepo."""
    return repo, file.split("/", 1)[0]


def join_called_endpoints(by_repo: dict[str, list[Edge]]) -> dict[str, list[Edge]]:
    """Point each call at the endpoint another repo exposes, so the walk can cross repos over REST.

    A call carries its base URL and an exposed endpoint does not, and no extractor knows which repo
    serves a base URL. The call joins only when exactly one other deployable unit exposes that method and
    path; otherwise it stays literal and surfaces as an unknown edge, because a guess would hide a repo. A
    unit is a repo, or a top-level module folder of a monorepo: a service calling a sibling module joins too.
    """
    exposed: dict[tuple[str, str], set[tuple[tuple[str, str], str]]] = {}
    for repo, edges in by_repo.items():
        for edge in edges:
            key = _endpoint_key(edge.dst) if edge.kind == "EXPOSES" else None
            if key:
                exposed.setdefault(key, set()).add((_unit(repo, edge.file), edge.dst))

    def resolve(repo: str, edge: Edge) -> Edge:
        if edge.kind != "CALLS_ENDPOINT":
            return edge
        caller = _unit(repo, edge.file)
        others = {(unit, dst) for unit, dst in exposed.get(_endpoint_key(edge.dst), ()) if unit != caller}
        return replace(edge, dst=next(iter(others))[1]) if len(others) == 1 else edge

    return {repo: [resolve(repo, edge) for edge in edges] for repo, edges in by_repo.items()}


def dependencies_path(central: str | Path) -> Path:
    return Path(central) / DEPENDENCIES


def _fingerprint(central: str | Path) -> str:
    digest = hashlib.sha256(dependencies_path(central).read_bytes())
    for name in ("project.md",):  # team ownership comes from here
        path = Path(central) / "profile" / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def load_into(store, central: str | Path) -> dict:
    """Upsert every repo in dependencies.yaml into the store, atomically."""
    path = dependencies_path(central)
    if not path.is_file():
        raise MissingInput(f"{path} not found: run `baton extract` first")
    try:
        document = miniyaml.load_file(str(path))
    except ValueError as exc:
        raise LoadError([f"{path}: {exc}"]) from exc
    by_repo = join_called_endpoints(parse_dependencies(document))
    profile = read_profile(central)
    with store.transaction():
        for repo, edges in by_repo.items():
            info = profile.repos.get(repo)
            if info and info.team:
                edges = [
                    *edges,
                    Edge(
                        "OWNED_BY",
                        f"repo:{repo}",
                        f"team:{info.team}",
                        repo,
                        "profile/project.md",
                        info.team_line,
                        "project-md",
                        "working-tree",
                    ),
                ]
            store.upsert_nodes(sorted({f"repo:{repo}"} | {n for e in edges for n in (e.src, e.dst)}))
            store.upsert_edges(edges)
            store.prune_repo(repo, edges)
        store.prune_orphan_nodes()
        store.set_meta(_FINGERPRINT, _fingerprint(central))
    return {"repos": sorted(by_repo), "edges": len(store.edges()), "nodes": len(store.dump()["nodes"])}


def open_for_reading(central: str | Path, writable: bool = True) -> SqliteStore:
    """A store that reflects dependencies.yaml as it is now.

    A missing or stale file is refreshed when writable. Read-only callers (the MCP server) get an
    in-memory copy instead, so they never write to disk. With no dependencies.yaml an existing graph
    file is served as it is.
    """
    graph = Path(central) / GRAPH_FILE
    has_input = dependencies_path(central).is_file()
    if not has_input and not graph.is_file():
        raise MissingInput(
            f"neither {DEPENDENCIES} nor {GRAPH_FILE} found under {central}: run `baton extract`"
        )
    if graph.is_file():
        current = SqliteStore(graph, read_only=True)
        fresh = not has_input or current.get_meta(_FINGERPRINT) == _fingerprint(central)
        if fresh:
            return current
        current.close()
    store = SqliteStore(graph if writable else ":memory:")
    load_into(store, central)
    return store
