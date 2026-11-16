"""GraphStore interface. Blast radius is written over the primitives, so any backend inherits it."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from baton.graph.model import (
    DOCUMENT_EXTRACTOR,
    PAIRS,
    PRODUCER_KIND_OF_RESOURCE,
    REVERSE_PAIRS,
    Edge,
    node_name,
    node_prefix,
    unknown_edge_message,
)

MAX_DEPTH = 2


class GraphStore(ABC):
    @abstractmethod
    def upsert_nodes(self, node_ids: Iterable[str]) -> None: ...

    @abstractmethod
    def upsert_edges(self, edges: Iterable[Edge]) -> None: ...

    @abstractmethod
    def prune_repo(self, repo: str, keep: Iterable[Edge]) -> None:
        """Drop the repo's edges that are not in `keep`, so a re-extraction removes what the code removed."""

    @abstractmethod
    def edges(self, repo: str | None = None) -> list[Edge]: ...

    @abstractmethod
    def neighbours(
        self, node_id: str, kinds: Iterable[str] | None = None, direction: str = "out"
    ) -> list[Edge]:
        """Edges leaving ("out") or entering ("in") a node, optionally limited to some kinds, sorted."""

    def repos(self) -> list[str]:
        return sorted({edge.repo for edge in self.edges()})

    def callers(self, node_id: str) -> list[dict]:
        return [edge.to_dict() for edge in self.neighbours(node_id, None, "in")]

    def collections(self, repo: str) -> list[dict]:
        rows: dict[str, dict] = {}
        for edge in self.edges(repo):
            if node_prefix(edge.dst) != "collection":
                continue
            row = rows.setdefault(node_name(edge.dst), {"collection": node_name(edge.dst), "edges": []})
            row["edges"].append({"kind": edge.kind, "class": edge.src, "file": edge.file, "line": edge.line})
        return [rows[name] for name in sorted(rows)]

    def team_of(self, repo: str) -> str | None:
        owners = self.neighbours(f"repo:{repo}", ["OWNED_BY"], "out")
        return node_name(owners[0].dst) if owners else None

    def impact(
        self,
        changed_ids: Iterable[str],
        *,
        source_repo: str,
        breaking: Iterable[str] = (),
        symbols: Iterable[str] | None = None,
    ) -> dict:
        """Blast radius per contracts/graph.md; returns the impact.json document.

        Depth 1 follows what the changed symbols produce to other repos' consumers. Depth 2 follows everything
        those repos produce: dependencies.yaml carries no CALLS edges, so class-level tracing would dead-end
        inside the consuming repo and silently under-report. `breaking` is a property of the changed
        symbol and travels with its whole walk.
        """
        changed = sorted(set(changed_ids))
        breaking_ids = set(breaking)
        unknown: set[str] = set()
        found: dict[tuple[str, str, str], dict] = {}
        frontier = self._seed_frontier(changed, breaking_ids, source_repo, unknown)
        visited = {source_repo}
        for depth in range(1, MAX_DEPTH + 1):
            reached: dict[str, bool] = {}
            for kind, resource, is_breaking in sorted(frontier):
                consumers = self.neighbours(resource, [PAIRS[kind]], "in")
                if not consumers:
                    unknown.add(unknown_edge_message(resource, kind))
                for edge in consumers:
                    if edge.repo == source_repo:
                        continue
                    row = found.setdefault(
                        (edge.repo, resource, edge.file), {"lines": set(), "breaking": False}
                    )
                    row["lines"].add(edge.line)
                    row["breaking"] = row["breaking"] or is_breaking
                    reached[edge.repo] = reached.get(edge.repo, False) or is_breaking
            frontier = set()
            if depth < MAX_DEPTH:
                for repo, is_breaking in reached.items():
                    if repo not in visited:
                        visited.add(repo)
                        frontier |= {
                            (edge.kind, edge.dst, is_breaking)
                            for edge in self.edges(repo)
                            if edge.kind in PAIRS
                        }
        return {
            "sourceRepo": source_repo,
            "changedSymbols": sorted(set(symbols)) if symbols is not None else changed,
            "impacted": [self._impact_row(key, found[key]) for key in sorted(found)],
            "unknownEdges": sorted(unknown),
        }

    def _seed_frontier(self, changed, breaking_ids, source_repo, unknown) -> set[tuple[str, str, bool]]:
        frontier: set[tuple[str, str, bool]] = set()
        for node_id in changed:
            is_breaking = node_id in breaking_ids
            producer = PRODUCER_KIND_OF_RESOURCE.get(node_prefix(node_id))
            if producer:
                frontier.add((producer, node_id, is_breaking))
                continue
            for edge in self.neighbours(node_id, None, "out"):
                if edge.repo != source_repo:
                    continue
                if edge.kind in PAIRS:
                    frontier.add((edge.kind, edge.dst, is_breaking))
                elif edge.extractor == DOCUMENT_EXTRACTOR:
                    # The class IS the collection's shape: readers see the change whatever kind was recorded.
                    frontier.add(("WRITES_COLLECTION", edge.dst, is_breaking))
                elif edge.kind in REVERSE_PAIRS and not self.neighbours(
                    edge.dst, [REVERSE_PAIRS[edge.kind]], "in"
                ):
                    unknown.add(unknown_edge_message(edge.dst, edge.kind))
        return frontier

    def _impact_row(self, key: tuple[str, str, str], row: dict) -> dict:
        repo, via, file = key
        low, high = min(row["lines"]), max(row["lines"])
        result = {
            "repo": repo,
            "via": via,
            "file": file,
            "lines": str(low) if low == high else f"{low}-{high}",
            "breaking": row["breaking"],
        }
        team = self.team_of(repo)
        if team:
            result["team"] = team
        return result

    def export_c4(self, profile=None, dynamic_views: Iterable[str] = ()) -> str:
        from baton.graph.c4 import render
        from baton.graph.profile_files import Profile

        return render(self.edges(), profile or Profile(), list(dynamic_views))
