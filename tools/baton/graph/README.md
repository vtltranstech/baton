# `baton graph`, `baton impact`, `baton c4`, MCP server

Stdlib only. Everything reads `profile/dependencies.yaml` (`schemas/dependencies.json`) under `--central`.

```text
baton graph load [--store sqlite|age] [--central C] [--json]
baton impact --repo R --diff FILE|REF [--out PATH] [--central C] [--json]
baton c4 [--check] [--central C] [--json]
```
Exit codes: 0 ok; 1 validation failure or drift; 2 missing input or refused (`--store age`, unknown repo, bad ref).

## graph load
Writes `.baton/graph.sqlite` (git-ignored). Atomic: any edge without full provenance, an off-contract kind or
node id refuses the whole file and changes nothing. Idempotent, and it mirrors each repo present in the file: an
edge the code no longer has leaves the graph. A repo absent from the file (a partial extract) is kept. `impact`
and `c4` reload automatically when `dependencies.yaml` or `project.md` changed. A `Team` column in the repo table
of `project.md` becomes `OWNED_BY` and fills `impacted[].team`; without it `team` is omitted.

## impact: how changed symbols are derived
`--diff` is tried as a file (cwd, then central); otherwise it is a git ref or range diffed in `../<repo>`.

- **Unified diff** (any line starting `diff --git`, `--- `, `+++ ` or `@@ `): for each file, the classes are those
  whose edge provenance names that file, else the FQCN from `src/main/{java,kotlin}/`. Tests and other files with
  no provenance derive nothing. Lines both removed and added are moves and are ignored.
  - private/protected/public non-static field or record component changed: symbol `Class.field`; else the symbol
    is `class:<fqcn>`.
  - field gone (removed or renamed): every path from that class is `breaking`. A changed type alone is not.
  - `@*Mapping("...")` literal removed, or a removed line with `@PathVariable/@RequestParam/@RequestBody/
    @RequestHeader` (attributed to the nearest preceding `EXPOSES` line): the endpoint is `breaking`.
  - a published topic or queue's quoted name removed: that resource is `breaking`.
- **Design file list** (anything else): one entry per line, optional `- ` bullet, trailing words ignored.
  `path`, `../<repo>/path` (entries of other repos are ignored with a note on stderr: run once per repo), a node id
  such as `topic:x`, or `breaking: <node id or Class.field>`, since a design has no code to diff.

## impact: the walk
Per `contracts/graph.md`. Seeds: a changed class's `WRITES_COLLECTION`, `EXPOSES`, `PUBLISHES`, `WRITES_FILE` in the
source repo, or a changed resource itself. A class with a `document-annotation` edge is the collection's shape, so
its collection is a seed whichever kind W2 records. Depth 1 reports the other repos' consumers. Depth 2 continues
from **everything** those repos produce, because `dependencies.yaml` has no `CALLS` edges and class-level tracing
would stop inside the consumer. This over-reports rather than under-reports. The source repo is never reported.
`lines` is `N`, or `min-max` for several edges of one (repo, via, file). `unknownEdges`: a producer with no consumer
anywhere in the walk, or a changed class's consumer edge with no producer. `breaking` travels with the symbol.

## c4
`docs/architecture/workspace.dsl` per `contracts/graph.md`, byte-identical across runs. Additions the contract
leaves open: the first persona in `project.md` is `user` (the design-diagram template and dynamic views use it);
one-sided topics, queues, files and called endpoints become an `External,Unknown` system, while a one-sided collection
or exposed endpoint stays with its owning container; component stereotypes come from the extractor name.
`dynamic` views in the existing workspace are always kept verbatim. `--check` compares with comments and whitespace
ignored, so a hand edit elsewhere in the model is drift (exit 1). Both refuse a kept view that would no longer
validate: an unknown identifier or a step with no relationship in the projected model.

Validate with the official CLI by setting `BATON_STRUCTURIZR_JAR` to its `lib/structurizr-cli.jar`; the tests skip
that check with a message when it is unset:
`java -cp "$(dirname "$BATON_STRUCTURIZR_JAR")/*" com.structurizr.cli.StructurizrCliApplication validate -workspace docs/architecture/workspace.dsl`

## MCP server
`graph/mcp_server.py`, newline-delimited JSON-RPC on stdio, read-only: a stale graph is rebuilt in memory, never on
disk. Tools `graph.impact(repo, diff_ref)`, `graph.callers(id)`, `graph.collections(repo)`. Central repo:
`BATON_CENTRAL`, else `CLAUDE_PROJECT_DIR`, else cwd. Dots are legal in MCP names (SEP-986); Claude Code exposes
them with `_`, for example `mcp__graph__graph_impact`, or `mcp__plugin_baton_graph__graph_impact` from the plugin.
`.mcp.json` uses the plain `${CLAUDE_PLUGIN_ROOT}`: the form `${CLAUDE_PLUGIN_ROOT:-.}` made the plugin server fail
to connect when tried under `--plugin-dir`. So it works as a plugin (`claude --plugin-dir <this repo>` or installed);
as a project-scope config in a checkout the variable is unset, and the server will not start.

## REST join
A call carries its base URL and an exposed endpoint does not, so `load` rewrites a `CALLS_ENDPOINT` target to the exposed endpoint when exactly one other repo exposes that method and path (path-variable names ignored). With two providers it stays literal and surfaces as an unknown edge. An external system that happens to share a path with a repo over-reports; this errs toward a wider blast radius.
