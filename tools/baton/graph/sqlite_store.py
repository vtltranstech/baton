"""SQLite GraphStore (stdlib): file `.baton/graph.sqlite` or `:memory:`."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from baton.graph.model import Edge, node_kind
from baton.graph.store import GraphStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edges (
  kind TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, repo TEXT NOT NULL,
  file TEXT NOT NULL, line INTEGER NOT NULL, extractor TEXT NOT NULL, commit_sha TEXT NOT NULL,
  PRIMARY KEY (kind, src, dst, repo, file, line));
CREATE INDEX IF NOT EXISTS edges_dst ON edges (dst, kind);
CREATE INDEX IF NOT EXISTS edges_src ON edges (src, kind);
CREATE INDEX IF NOT EXISTS edges_repo ON edges (repo);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_COLUMNS = "kind, src, dst, repo, file, line, extractor, commit_sha"
_ORDER = "ORDER BY kind, src, dst, repo, file, line"


class SqliteStore(GraphStore):
    def __init__(self, path: str | Path = ":memory:", read_only: bool = False):
        self.read_only = read_only
        if read_only:
            self.conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        else:
            if str(path) != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path))
            self.conn.executescript(_SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def transaction(self):
        return self.conn

    def upsert_nodes(self, node_ids: Iterable[str]) -> None:
        rows = [(node_id, node_kind(node_id) or "Unknown") for node_id in node_ids]
        self.conn.executemany(
            "INSERT INTO nodes (id, kind) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET kind = excluded.kind",
            rows,
        )

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        self.conn.executemany(
            f"INSERT INTO edges ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(kind, src, dst, repo, file, line) DO UPDATE SET "
            "extractor = excluded.extractor, commit_sha = excluded.commit_sha",
            [(e.kind, e.src, e.dst, e.repo, e.file, e.line, e.extractor, e.commit) for e in edges],
        )

    def prune_repo(self, repo: str, keep: Iterable[Edge]) -> None:
        wanted = {(e.kind, e.src, e.dst, e.file, e.line) for e in keep}
        current = self.conn.execute(
            "SELECT kind, src, dst, file, line FROM edges WHERE repo = ?", (repo,)
        ).fetchall()
        self.conn.executemany(
            "DELETE FROM edges WHERE kind = ? AND src = ? AND dst = ? AND file = ? AND line = ? AND repo = ?",
            [(*row, repo) for row in current if row not in wanted],
        )

    def prune_orphan_nodes(self) -> None:
        self.conn.execute(
            "DELETE FROM nodes WHERE id NOT IN (SELECT src FROM edges) AND id NOT IN (SELECT dst FROM edges) "
            "AND kind != 'Repo'"
        )

    def edges(self, repo: str | None = None) -> list[Edge]:
        if repo is None:
            rows = self.conn.execute(f"SELECT {_COLUMNS} FROM edges {_ORDER}")
        else:
            rows = self.conn.execute(f"SELECT {_COLUMNS} FROM edges WHERE repo = ? {_ORDER}", (repo,))
        return [Edge(*row) for row in rows.fetchall()]

    def neighbours(self, node_id, kinds=None, direction="out") -> list[Edge]:
        if direction not in ("in", "out"):
            raise ValueError(f"direction must be in or out, not {direction}")
        column = "src" if direction == "out" else "dst"
        sql = f"SELECT {_COLUMNS} FROM edges WHERE {column} = ?"
        params: list[str] = [node_id]
        if kinds is not None:
            kinds = list(kinds)
            sql += f" AND kind IN ({', '.join('?' * len(kinds))})"
            params += kinds
        return [Edge(*row) for row in self.conn.execute(f"{sql} {_ORDER}", params).fetchall()]

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def dump(self) -> dict:
        """Everything in the store in a stable order; two equal dumps are the idempotence proof."""
        return {
            "nodes": self.conn.execute("SELECT id, kind FROM nodes ORDER BY id").fetchall(),
            "edges": [e.to_dict() for e in self.edges()],
        }
