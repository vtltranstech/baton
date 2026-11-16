"""Apache AGE adapter: interface only (plan §8, platform track). Nothing here talks to a database."""

from __future__ import annotations

from baton.graph.store import GraphStore

MESSAGE = "the age store is not implemented; use --store sqlite"


class AgeStore(GraphStore):
    def __init__(self, *_args, **_kwargs):
        raise NotImplementedError(MESSAGE)

    def upsert_nodes(self, node_ids):
        raise NotImplementedError(MESSAGE)

    def upsert_edges(self, edges):
        raise NotImplementedError(MESSAGE)

    def prune_repo(self, repo, keep):
        raise NotImplementedError(MESSAGE)

    def edges(self, repo=None):
        raise NotImplementedError(MESSAGE)

    def neighbours(self, node_id, kinds=None, direction="out"):
        raise NotImplementedError(MESSAGE)
