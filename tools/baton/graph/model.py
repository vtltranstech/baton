"""Store-agnostic graph vocabulary: node ids, edge kinds and the Edge record (contracts/graph.md)."""

from __future__ import annotations

from dataclasses import dataclass

NODE_KINDS = {
    "repo": "Repo",
    "class": "Class",
    "collection": "Collection",
    "endpoint": "Endpoint",
    "topic": "Topic",
    "queue": "Queue",
    "file": "FileInterface",
    "job": "BatchJob",
    "team": "Team",
}
EDGE_KINDS = frozenset(
    "CONTAINS CALLS READS_COLLECTION WRITES_COLLECTION EXPOSES CALLS_ENDPOINT PUBLISHES CONSUMES "
    "WRITES_FILE READS_FILE RUNS_JOB OWNED_BY".split()
)
# Producer-side kind -> consumer-side kind: the walks blast radius follows.
PAIRS = {
    "WRITES_COLLECTION": "READS_COLLECTION",
    "EXPOSES": "CALLS_ENDPOINT",
    "PUBLISHES": "CONSUMES",
    "WRITES_FILE": "READS_FILE",
}
REVERSE_PAIRS = {consumer: producer for producer, consumer in PAIRS.items()}
MISSING_SIDE = {
    "WRITES_COLLECTION": "reader",
    "EXPOSES": "caller",
    "PUBLISHES": "consumer",
    "WRITES_FILE": "reader",
    "READS_COLLECTION": "writer",
    "CALLS_ENDPOINT": "provider",
    "CONSUMES": "publisher",
    "READS_FILE": "writer",
}
PRODUCER_KIND_OF_RESOURCE = {
    "collection": "WRITES_COLLECTION",
    "endpoint": "EXPOSES",
    "topic": "PUBLISHES",
    "queue": "PUBLISHES",
    "file": "WRITES_FILE",
}
DOCUMENT_EXTRACTOR = "document-annotation"


def node_prefix(node_id: str) -> str:
    return node_id.split(":", 1)[0] if ":" in node_id else ""


def node_name(node_id: str) -> str:
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def node_kind(node_id: str) -> str | None:
    return NODE_KINDS.get(node_prefix(node_id))


def unknown_edge_message(resource: str, kind: str) -> str:
    return f"{resource} has no known {MISSING_SIDE[kind]} in graph"


@dataclass(frozen=True, order=True)
class Edge:
    kind: str
    src: str
    dst: str
    repo: str
    file: str
    line: int
    extractor: str
    commit: str

    def provenance(self) -> dict:
        return {
            "repo": self.repo,
            "file": self.file,
            "line": self.line,
            "extractor": self.extractor,
            "commit": self.commit,
        }

    def to_dict(self) -> dict:
        return {"kind": self.kind, "from": self.src, "to": self.dst, "provenance": self.provenance()}
