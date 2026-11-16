# `baton wiki`, `baton verify`

Stdlib only. `wiki` calls headless `claude -p`; `verify` calls nothing and needs no network.

```text
baton wiki <repo> [--changed-since SHA] [--module M]... [--timeout S] [--central C] [--json]
baton verify <repo> [--central C] [--json]
```
Run `baton extract` first. Exit codes: 0 ok; 1 a page or a model call failed; 2 missing input, or `claude` not found.

| Command | Writes |
| --- | --- |
| `wiki` | `docs/wiki/<repo>/<module>.md`, the index block in `docs/context/codebase-map.md` |
| `verify` | `docs/wiki/<repo>/verify-report.json`, `verified` and Last verified on each page, the index block |

`cli.md` does not list the map under either command; the brief and `artefacts.md` §6 require it. `verify` regenerates it too, or the index would call a just-verified page unverified.

## Modules
One module per Java package. The name comes from the `layout` cell of `stack-detected.md`: `<layer><rest of package>`, such as `adapters.repository`. A package outside the layers is named relative to `package root`; the root package itself is `_root`. A repo with no Java under `src/main/java` is refused.

## Who writes what
By default no model is called: Purpose lists each type with the first sentence of its Javadoc, and Invariants observed in tests lists the test methods (with `@DisplayName`). With `--prose`, the model's answer fills those two sections instead. Headings are matched loosely (`##`–`####`, bold, any case, a trailing colon). A quota or rate-limit error stops the model calls for the run; that module and the rest are written from the code and listed under `withoutProse`.

The model's answer fills two sections, Purpose and Invariants observed in tests. Only the text under those two headings is read from it, so frontmatter or extra sections in an answer never reach the page. A kept section holding `verified:`, `claims:`, `generatedFrom:` or `bodySha256:` rejects the answer, as does a repeated heading or an empty section. Then no page is written and an existing page stays.

Everything else is deterministic: frontmatter, Entry points, Reads / Writes, Calls / Called by (edges; imports are labelled as not a claim), Known pitfalls (lines of `docs/context/pitfalls-log.md` naming the module or one of its classes), Last verified.

The call is `claude -p --tools ""`, prompt on stdin, from an empty temp directory. `BATON_CLAUDE_BIN` names another executable; the tests use a stub. Sources sit between lines carrying a per-call nonce and the prompt calls them data. Sources per module stop at 80,000 characters, and the prompt says so where they stop.

## Claims
Read from `dependencies.yaml`, by the module of each edge's `provenance.file`.

| Claim | Edge kinds | Text |
| --- | --- | --- |
| `collections` | READS_COLLECTION, WRITES_COLLECTION | name |
| `topics` | PUBLISHES, CONSUMES | topic name; a queue keeps `queue:` |
| `endpoints` | EXPOSES | `GET /path` |
| `calls` | CALLS_ENDPOINT | target as written, `GET https://…` or `${x}/…` |
| `files` | READS_FILE, WRITES_FILE | pattern |

RUNS_JOB has no claim category. It appears under Entry points.

`calls` holds only outbound REST calls, because `dependencies.yaml` has no class-to-class edge.

## What fails a page in `verify`
- The commit: `dependencies.yaml` says `unknown` (never a match, not even with `unknown`); it is not at the repo's HEAD; the repo has uncommitted changes; the page's `generatedFrom` differs.
- A claim that is not an edge of this module, an edge of this module that is not claimed, a claim category that does not exist. A claim true of another module fails and names that module.
- Frontmatter missing, unreadable or short of a required key; `repo` or `module` not matching the file; a module that no longer exists.
- A body that no longer matches `bodySha256`, is missing a section, or has other text under Last verified. An edited page stays failed however often `verify` runs, until it is regenerated.

A failing page is reset to `verified: false`, except one whose frontmatter cannot be parsed, which is left alone and shows as unverified in the index. The index calls a page verified only if it says `verified: true` and its `generatedFrom` is the repo's current `commit`, so a page whose repo has since been re-extracted reads as unverified even before `verify` runs.

## `--changed-since`
The model is called for a module with a changed main or test file since SHA or since its own page's `generatedFrom`, with no page or an unreadable one, or whose claims differ. Other pages keep their body, move to the new commit and go to `verified: false`. A later `verify` restores them.

## The index
Between `<!-- wiki-index` markers in `docs/context/codebase-map.md`: one table per repo, one row per page: status, data claims, API claims. ASCII only. Anything outside the markers, such as a map written by `/onboard`, is kept below it.
