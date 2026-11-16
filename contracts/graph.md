# Graph contract (store-agnostic)

Nodes: `Repo, Module, Class, Method, Collection, Field, Endpoint, Topic, Queue, FileInterface, BatchJob, Team, Container, ExternalSystem`.
Edges: `CONTAINS, CALLS, READS_COLLECTION, WRITES_COLLECTION, EXPOSES, CALLS_ENDPOINT, PUBLISHES, CONSUMES, WRITES_FILE, READS_FILE, RUNS_JOB, OWNED_BY`.
Every edge carries provenance `{repo, file, line, extractor, commit}` - mandatory; an edge without it is rejected by the loader.

Node ids: `repo:<name>`, `class:<fqcn>`, `collection:<name>`, `endpoint:<METHOD> <path>`, `topic:<name>`, `queue:<name>`, `file:<pattern>`, `job:<name>`, `team:<name>`.

`GraphStore` interface: `upsert_nodes`, `upsert_edges`, `neighbours(id, kinds, direction)`, `impact(changed_ids) -> impact.json`, `callers(id)`, `export_c4()`. Implementations: `sqlite` (stdlib) now; `age` later.

Blast radius: from changed symbols (classes/fields/collections/endpoints/topics in the diff) walk `WRITES_COLLECTION->READS_COLLECTION`, `EXPOSES->CALLS_ENDPOINT`, `PUBLISHES->CONSUMES`, `WRITES_FILE->READS_FILE` across repos, depth <= 2; an edge whose other side is not in the graph is an `unknownEdge`. `breaking` = the changed symbol is a removed/renamed field, endpoint signature or topic schema.

C4 projection (`baton c4`): Container <- each Repo (type from stack-detected: service/batch/ui) + each Collection's datastore + each broker; ExternalSystem <- `profile/domain.md` section  External systems and any unknown edge endpoint; Component <- Class with a Spring stereotype or a BatchJob; Relationship <- edges collapsed to component level, label = the data (collection/topic/endpoint name), technology from the edge kind. Identifiers = lowerCamel of the names; stable across runs (sorted, no counters). Output must pass `structurizr-cli validate`.

MCP server (`.mcp.json`, stdio, python): tools `graph.impact(repo, diff_ref)`, `graph.callers(id)`, `graph.collections(repo)`, `graph.context(name)` (the `baton diagram context` card); read-only.
