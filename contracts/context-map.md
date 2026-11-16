# Context map - `baton context`

`baton context` checks deterministically whether the product's context is good enough for the work at hand. It reports what is missing and stops a story from starting without enough context. It runs before the delivery agents do: `/build-context-map` builds the map after `/onboard`, `/stories` accepts a feature only when the areas it changes are understood (section 10), `/ready` checks each story against it, and `/build` hands the result to the architect. It writes no knowledge of its own. It measures what is known, mines drafts with their provenance, and sends confirmations to a human. No model call and no network anywhere.

Subcommands: `baton context ingest [--from PATH] | build | score | brief <area|system> | understand | check <story-id|feature-id> [--no-write] | gaps [--layer L] | trend`.

## 1. The five layers

| Layer | Unit | Covered when | Read from |
| --- | --- | --- | --- |
| structural | module, edge | the module's wiki page is `verified: true` with `generatedFrom` = the repo's extracted commit; the edge's target is not in `unresolved:` | `docs/wiki/`, `profile/dependencies.yaml` |
| behavioural | collection, module | the collection's data profile is no older than `profile-max-age-days` and not `unprofiled`; the module has a test whose name contains `ac<n>`, `rule` or `r<n>_`, or uses `@DisplayName` | `docs/data-profile/`, the repos' tests |
| domain | branch point | `status: mapped`: a human set `rule:` to a rule that is confirmed in `domain.md` | `profile/branch-points.yaml`, `profile/domain.md` |
| operational | repo | build and test commands detected; owner known (an `Owner` column in the project.md repo table, or a CODEOWNERS file); ArchUnit or ESLint installed. Plus one product-wide check: `test.env` is named | `profile/stack-detected.md`, `profile/project.md` |
| intent | feature, open decision | the feature note has an `## Outcome` (or `## Problem`) and a `## Scope` section; the decision line has `owner:` and a story id or an ADR | `docs/features/`, `profile/domain.md` |

A layer's score is the number of covered units divided by the number of units, unweighted. Layers are reported side by side and never averaged. The domain score is mapped branch points / all branch points. The map also reports words defined and rules tested, but they do not change that score. "Confirmed" always means a human set it. Mined drafts stay `confirmed: false` and count as gaps, never as coverage.

## 2. Branch points (`profile/branch-points.yaml`, schema `branch-points.json`)

A branch point is a conditional whose predicate names a domain field:
- `if` (an `else if` counts as its own point), `switch`, the ternary operator, `.filter(...)` (stream or Optional), `@ConditionalOn*`, `@Query`;
- in TS/TSX, `{x && <...>}` as well.

A domain field is any of these:
- a word from the Domain words table or the project.md list (compared case-insensitively, ignoring separators);
- a field of a `@Document` class;
- an identifier containing one of the words in `domain-field-patterns`.

Other rules:
- `getX`, `isX` and `hasX` count as `x`.
- A bare null check names no field.
- Identifiers that start with a capital letter (types and constants) are skipped.
- String contents are read only inside `@Query` and `@ConditionalOn*`.

Back-ends:
- Java is read with tree-sitter when the `baton[treesitter]` extra is installed (extractor `branch-points-java`). Otherwise a comment- and string-aware scanner reads it (`branch-points-java-scan`).
- TS and TSX always go through the scanner (`branch-points-ts-scan`).
- The two Java back-ends find the same points on the fixture.

Each entry has these fields: `id, repo, module, file, line, kind, predicate, fields, rule, status (mapped | undocumented | contested), provenance {extractor, commit}`. An unmapped point may also carry `proposed: R<n>` and `confidence: field-overlap n/m`, taken from the confirmed rule whose `fields:` overlap it most. Only a human sets `rule:` and `status: contested`. A rebuild keeps both, along with the id, for every point whose repo, file and predicate are unchanged; the line number may move.

## 3. `profile/domain.md` as an index (additive)

A rule is a `### R<n> - title` heading, followed by `fields:`, `source:` and `confirmed:` lines, then prose. Rules can sit in any section.
- A rule with no `fields:` is a gap: "rule not indexable".
- A rule with no `source:`, or not `confirmed: true`, is a draft.

Domain words live in a `| word | definition | confirmed |` table under `## Domain words`. A word listed only in project.md's `## Domain words` still counts, as a word with no definition. Open decisions are the bullets under `## Open decisions`.

## 4. Unstructured documents (`baton context ingest`)

`ingest` reads each file, folder or glob given with `--from`, or else those listed in `doc-sources`. It turns every supported document into plain Markdown at `docs/context/sources/<slug>.md`. The output keeps the document's headings, paragraphs and tables in order, under a `baton:source` header giving the original path, its kind and its sha256.

Supported formats:
- Confluence exports and other HTML. Script, style, head, nav and footer content is dropped.
- XML, such as Confluence storage format.
- Markdown, text, CSV/TSV and JSON (string values with at least three words).
- Word `.docx` (headings from the Heading styles, plus tables).
- PowerPoint `.pptx` (one heading per slide, plus speaker notes).
- Excel `.xlsx` (one table per sheet).
- PDF, with the optional `baton[pdf]` extra (pypdfium2). A page whose text layer has fewer than `ocr-min-chars` characters is a scan, and is read by OCR.
- Images (`.png .jpg .jpeg .tif .tiff .bmp .gif .webp .pnm .ppm`), read by OCR only.
- Images inside Word and PowerPoint files (2 KB or larger, so icons and bullets are left out), read by OCR when `ocr-embedded-images` is true (the default). A slide's images land under that slide; a Word file's at its end.

All of these except PDF and OCR are read with the standard library only.

### OCR, with nothing downloaded

- **Engine.** OCR is Tesseract (Apache-2.0), run as the `tesseract` command; `BATON_TESSERACT` names another binary.
- **Language files.** It reads the languages in `ocr-languages` (default `eng`) from `ocr-tessdata` (or `TESSDATA_PREFIX`, or Tesseract's own default folder).
- **Nothing is downloaded, ever.** The binary, the `.traineddata` files and pypdfium2 come from the organisation's package mirror. Before a run, `ingest` asks the binary which languages it has (`--list-langs`), so a missing language is named, never fetched. No code in `ingest` or `ocr` opens a network connection; a test holds them to that.
- **When OCR is missing.** If OCR cannot run, an image file is skipped with the reason, the images inside an Office file and the scanned pages of a PDF are recorded as `warnings` on the document, and the rest of the text is kept. `score` reports both as gaps.
- **OCR text is marked.** Text from OCR is under a heading or line marked `(OCR)`, and the source header's `ocr:` line names the engine version and the pages or images read. A draft from it therefore cites `...#Page 2 (OCR)`, and the PO can see it came from pixels.

### Confluence through its MCP server

`baton` never calls Confluence: that is a network call. When the organisation's Confluence MCP server is connected, the `/onboard` skill fetches the pages the humans name, through that server. It saves each page body as returned to `docs/legacy/confluence/<space>/<page-id>-<slug>.html`, with the first line `<!-- confluence: <page url> version <n> -->`, and then runs `ingest` on the folder. `ingest` records the URL as the document's `origin`, and drafts cite the URL instead of the file. A page whose version is unchanged is not fetched again; a changed page gets a new sha256 and is re-read.

Rules for the run:
- A file that cannot be read is listed under `skipped` in `docs/context/sources/index.json` with its reason, and is never half-written. Reasons include: unsupported format, larger than 50 MB, a broken archive, or an Office part declaring a DTD or entities.
- An unchanged file (same sha256) is not rewritten.
- `score` reports each skipped file as a gap.

Nothing is summarised or interpreted at this step. The doc miner in `build` does the reading, and the score turns its findings into the document map (section 5.1).

## 4a. Miners (drafts into `profile/domain-drafts.md`)

| Miner | Reads | Proposes |
| --- | --- | --- |
| branch-point | undocumented points with no proposed rule | one draft per module and field set, with the file:line of each point |
| test-name | Java `@Test` methods (name or `@DisplayName`, domain fields from the body), TS `it(...)`/`test(...)` names; skips tests a confirmed rule's `source:` already cites | a draft from the name |
| doc | the ingested sources | word drafts (`W-draft-<n>`, with `definition:`): rows of a table whose header has a term/word/name column and a definition/meaning/description column; `Term: definition` lines under a Glossary, Definitions or Terms heading; sentences of the form `A <Term> is/means/refers to ...` where the Term is a domain word or in Title Case. A word already defined and confirmed is skipped. Rule drafts: sentences with a normative word (must, shall, never, always, only if, cannot, at least, ...) that name a domain field. Each draft cites `<original file>#<heading>` and carries the sentence as `quote:`. At most 200 of each per document |
| clarification | `- <date> Q: ... A: ...` lines under `## Clarifications` of every story (here, archived or on its branch), except those already ending `-> domain.md` | a draft tagged with the story id |

Every draft starts as `confirmed: false` and carries `drafted-by:`. A rebuild keeps, word for word, any block a human set to `confirmed: true`; a draft is identified by its `source:` and `quote:`, so a corrected title is still the same draft. `/ready` and `/onboard refresh` move such a block into `domain.md`, and only on a human's yes. An R-draft becomes the next `R<n>`; a W-draft becomes a row of the Domain words table.

## 5. Scores and checks

### 5.1 `baton context score` -> `docs/context/context-map.json` and `.md`

The JSON holds:
- `computedAt`, `commit`, `repos` (the extracted commit of each repo);
- `layers` (counts per section 1);
- `byModule` (structural, behavioural and domain per module);
- `readiness` and `interviewOrder`;
- `gaps` (`layer, module, kind, text, ask: PO | TL`, plus `file` and `line` where there is one);
- `drafts` and `trend`;
- `documents`: for each ingested source, the modules (by module name or a class name of 6 or more characters), the collections, topics and endpoints, and the domain words its text names. `byModule.<key>.documents` lists the same, per module.

`score` also writes one context map per module, `docs/context/modules/<repo>--<module>.md`. Each lists the module's layer scores, its readiness, its wiki page, every branch point with its rule or status, the documents that mention it, and its gaps. A module that no longer exists has its file removed.

Readiness, for each module:
- **Light stories:** ready when no edge in the module is unresolved.
- **Full stories:** ready when, on top of that, every branch point in it is mapped.

The interview order puts the module with the most work first, by (undocumented points) x (edges + 1). The `.md` file is rendered from the JSON in this order: Readiness (plain sentences), Scorecard (five rows), Trend, Interview order, Gaps by module, Documents, Drafts awaiting confirmation, How to raise a score. A rerun keeps `trend`. Apart from `computedAt`, the same inputs give the same output.

### 5.2 `baton context check <S>` -> exit 0 / 2, `docs/design/<F>/<S>-context.md` and `.json`

1. **Seeds.** The checker looks up what the story's title and ACs name: collections, topics and endpoints from `dependencies.yaml`, and words from the word table. Endpoint paths are matched literally. It infers nothing.
2. **Scope.**
   - Changed modules: those with an edge to a seed.
   - In scope: the changed modules plus every module within two hops, where a hop is a resource two modules share.
3. **Checks on each module in scope.**
   - The wiki page is verified at the extracted commit.
   - Each collection it touches is profiled. An unprofiled collection written by a changed module is `unprofiled-write`.
   - No edge is unresolved (`unresolved-edge-out`).
   - Each branch point is mapped, or the ACs name all its fields. An unmapped point in a changed module is `undocumented-branch-in-changed-module`.
   - Every domain word the story uses has a confirmed definition (`undefined-word`).
   - The repo has an owner.
4. **Outputs.**
   - The manifest lists what will be loaded: pages, rules by id, data profiles, edges, and the ingested documents that mention a module in scope or a domain word the story uses.
   - Each gap is added to the story's `## Open questions` as a `- [context] <PO or TL>: ...` line. Lines from an earlier check are replaced; a human's lines are never touched.
   - The story's row in the map's `trend` is updated with the domain score and the clarification count.
   - Exit 2 if any gap is blocking. `--no-write` prints the same result and writes nothing.
5. **Blocking, per track (`profile/context.yaml` `blocking`).**
   - Light: `undefined-word`, `unresolved-edge-out`.
   - Full: also `undocumented-branch-in-changed-module` and `unprofiled-write`.
   - Spike: never blocks.
   - A story with no `Track:` is checked as full.

The manifest lives under `docs/design/`, not next to the story. A file named `S-010-context.md` in `docs/stories/<F>/` would be read as a second S-010.

## 6. Wiring

- **`/ready`, step 2a:** runs the check. On exit 2 the story stays out of Ready for PO, and the blocking gaps join the clarification loop. `baton state-check` refuses Ready for PO and Ready while the story's `-context.json` lists a blocking gap. A story never checked is not refused, so stories from before this contract keep working.
- **`/build`:** re-runs the check with `--no-write` before the architect, and stops on a new blocking gap. The architect starts from the manifest's Load list.
- **`/onboard`:** extraction, the workspace DSL, the architecture diagrams and the wiki; it ends by pointing at `/build-context-map`.
- **`/build-context-map`:** ingests the documents, runs `build` and `score`, runs the context explorers and the integrator, grades them with `understand`, and interviews in `interviewOrder`, capped at `interview-cap-minutes`; `refresh` re-ingests, rebuilds, re-explores stale areas and moves confirmed drafts into `domain.md` (section 10).
- **`/stories`:** step 0 runs `check <feature-id>` and drafts nothing while it exits 2 (section 10.5).
- **`/standup`:** prints the readiness lines and the trend.

Every step above is skipped when `profile/branch-points.yaml` does not exist yet.

## 7. `profile/context.yaml` (schema `context.json`)

`domain-field-patterns`, `doc-sources` (the files, folders or globs `ingest` reads when given no `--from`; relative to the central repo), `profile-max-age-days` (default 30), `blocking` (per track), `interview-cap-minutes` (default 60), the OCR keys of section 4, `explore-parallel` (default 4) and `explore-rounds` (default 3) for `/build-context-map`. Every key is optional. The defaults are in `templates/profile/context.yaml`.

## 8. Left out, on purpose

- **`.scm` query files.** The branch-point kinds are a handful of node types, matched in `context/branch_points.py`, as for the extractors (models-and-activation.md section 1).
- **The history miner (git log).** Turning commit messages into rules needs judgment and would mostly add noise.
- **Reading Confluence from `baton` itself.** That would be a network call; the MCP step in `/onboard` fetches pages instead (section 4).
- **Handwriting, and the layout of complex scans.** Tesseract reads printed text line by line, so tables in a scan come out as lines of text.
- **The batch `ItemProcessor` skip rule.** Its `return null` sits inside an `if` that is already a point.
- **`case` labels.** A `switch` is one point, keyed by its selector.
- **The `/retro` table and the trace page's Context column.** The manifest and the trend in `context-map.json` hold the data for both.
- **Seeding from C4 identifiers.**
- **A reachability test for the test environment.** It would be a network call. Operational checks only that `test.env` is named.

## 9. What this does not claim

It measures known-knowns (code, tests, data) and surfaces known-unknowns (branch points, edges and words with no answer). Unknown-unknowns are rules that never reached code or tests. They show up only as outcomes: lens findings, defects and clarifications. The clarification miner is how they enter the map. Readiness therefore means "ready as far as the code can tell", and every readiness block ends by saying so.

Fixture: `fixtures/sample-context/`, tested by `tools/baton/tests/context/`.

## 10. System understanding (`baton context understand`, `brief`, `check <feature>`)

The layers above say what is known. This section says whether the system has been *understood*: whether someone new could explain each area, follow the business end to end and name the systems around it. Agents do the learning, as a new engineer would; `baton` grades what they wrote against the code, and humans answer what nobody can find. No model call happens in `baton`; the agents are run by the `/build-context-map` skill.

### 10.1 Who writes what (`docs/context/understanding/`)

| File | Written by | Says |
| --- | --- | --- |
| `areas/<repo>--<module>.md` | `context-explorer`, one per area (a module, as in section 5), several in parallel | what the area is for; every edge it has, each with what it is for; what each business branch point decides; contradictions between documents, diagrams and code; questions |
| `flows/<name>.md` | `context-integrator` | one business journey, as steps across areas and outside systems |
| `landscape.md` | `context-integrator` | one row per boundary resource: the system on the other side, the direction and how it is integrated |
| `status.json`, `status.md` | `baton context understand` | the grade of everything above; do not edit |

`baton context brief <repo>/<module>` prints what an explorer must explain (its file and header line, its edges, its branch points with their rules, its tests, documents, architecture files and neighbours, and the grader's last problems). `baton context brief system` prints the same for the integrator: areas, entry points, shared and boundary resources, flows and landscape problems.

### 10.2 Formats

An area note starts `<!-- baton:understanding area=<repo>/<module> commit=<repo commit> code=<hash> -->` (the brief gives the line; `code` fingerprints the area's own source and test files), then:
- `## Purpose`: business words and at least one citation.
- `## What it touches`: `- <verb> <resource> - <what it is for> [<file>:<line>]`, verbs `exposes consumes reads writes publishes calls` (one per edge kind of section 5).
- `## Rules`: `- bp-NNNN - <what it decides> (R<n> | Q<n>) [<file>:<line>]`.
- `## Questions`: `- Q<n> (blocking|open, PO|TL): <question>`, and the human's answer on the next line as `  answer: <words> (<role>, <date>)`.
- Optional: `## Lifecycle`; `## Contradictions` as `- C<n>: <document or diagram> says ..., the code ... [cite] [cite]`, settled by the Tech Lead's `  resolved: <words> (TL, <date>)` on the next line (a line saying none were found is allowed).

A flow has `## Steps`: `<n>. <area | external:<System>> <verb> <resource> - <what happens> [<file>:<line>]`, where the verb may also be `uses <area>`. The landscape has `## Systems`, a table `| system | direction | how | resource | evidence |` (direction `upstream downstream both none`, evidence a citation starting with the repo or the id of an answered question), and `## Questions`.

Citations are `[path:line]` (relative to the area's repo, or `<repo>/path` or a central-repo path), `[path#Section]` or `[R<n>]`.

### 10.3 What the grader checks

An area is:
- **unexplored** when it has no note;
- **stale** when the area's own source or test files changed since the note was written (its `code` fingerprint differs); a merge that touches other modules of the same repo leaves it as it was. A note without `code` is stale when its commit is not the repo's extracted commit. Refresh re-explores stale areas;
- **incomplete** when any of these fails:
  - every edge of the module is under What it touches, and nothing else is: a claim with no edge is reported as `not in the code`;
  - every claim, rule line and the Purpose has at least three words of meaning and a citation that resolves (the file exists, the line is within it, the rule exists);
  - every branch point of the module is under Rules; a mapped one names its rule; an unmapped or contested one names a question, and that question counts as blocking whatever its label, because only a human confirms a rule;
  - every entry point (`exposes`, `consumes`) is a step of a valid flow, and an area with edges but no entry point is in at least one;
- **blocked** when nothing fails but a blocking question has no answer, or a contradiction is not resolved;
- **understood** otherwise.

A flow is valid when every step names a known area and an edge it has (or an `external:` system in the landscape), a `uses` step's area imports code from the other area (Java `import`, relative TypeScript import), consecutive steps share an area or a resource, and it has at least two steps. Only valid flows count.

The boundary is computed, never written by hand: an unresolved edge; an endpoint called and not exposed, or exposed and not called; a topic published and not consumed, or the reverse; a collection read and not written, or the reverse; any file. The landscape is understood when every boundary resource has a row with a named system, a direction and evidence (a citation, or an answered question), and no blocking question is open. A row for a resource the extractors never found is reported.

### 10.4 Stopping to ask

The skill stops and asks the humans the open questions, blocking first, Product Owner then Tech Lead, highest-impact area first, capped at `interview-cap-minutes`. The answer is written under the question verbatim, and into `profile/branch-points.yaml`, `profile/domain.md` or `profile/project.md` when it settles a rule, a word or a system, on the human's yes. The explorer then folds it into the note. Nobody else answers a question.

A human may also answer without a session: `baton context answer <area | landscape | flow:<name>> Q<n> "<words>" --by PO|TL` writes `  answer: <words> (<role>, <date>)` under the question, verbatim, and grades again; `... C<n> "<words>" --by TL` resolves a contradiction the same way. It refuses an item that already has an answer. `baton context questions` writes `docs/context/questions.md`: the open questions and contradictions by person, blocking first, oldest first, each with the day a run first saw it (kept in `docs/context/understanding/asked.json`); one open longer than `question-ttl-days` (default 3) is marked OVERDUE for the Tech Lead. /standup prints it.

### 10.5 Gate 0: accepting a feature or a story (`baton context check F-001 | S-010`)

Gate 0 is the first gate: once the product has a context map (`profile/branch-points.yaml`), no story is drafted, readied or designed on an area it does not understand. A changed area passes when it is good enough for the track:

| Track | A changed area passes when |
| --- | --- |
| full (default for a feature) | understood |
| light | understood, or blocked only by at most `light-open-questions` (default 2) open questions and no contradiction |
| spike | always (it investigates); the gaps are listed, open |

When it does not pass, the work is not refused and left: `/stories`, `/ready` and `/build` run `/build-context-map focus <F>` themselves, which explores the areas and asks the human present, then check again, and go on only when it passes. What nobody can answer now stays as questions (section 10.4).

`baton context check F-001 [--track light|full|spike]`: 
the feature's whole note seeds the scope as for a story (section 5.2). Blocking: no seed (nobody can say what it changes); an undefined word it uses; a changed area that does not pass for the track, with each of its open blocking questions and unresolved contradictions; a boundary resource of a changed area that the landscape does not name. The areas within two hops are listed, and their gaps are open, not blocking. Exit 0 accepts the feature for story drafting; exit 2 does not. It writes `docs/design/<F>/<F>-context.md` and `.json`, whose Load list (notes, flows, landscape) the story-drafter reads. A story's check (section 5.2) applies the same gate for the story's track, lists the notes and flows of its scope, and records in its `.json` the status each changed area had (`gate`); every check also writes `docs/context/understanding/status.json`.

The state gate (contracts/states.md) enforces it: once `profile/branch-points.yaml` exists, Ready for PO, Ready and Designed need the story's context manifest with no blocking gap, and every area in its `gate` must still pass for the track in the current `status.json`. An area that went stale after a merge refuses the move until `/build-context-map` re-reads it and the check runs again. There is no override: a gap is answered, not waived.

### 10.6 What this does not claim

The grader proves that a note agrees with the extracted code and that every claim points at something real. It cannot prove that the business words in it are right: that is why the rules come from humans, every claim is cited for a reviewer, and an area is never understood while a human question is open. A flow through code the extractors cannot see (reflection, a call through configuration) cannot be joined and becomes a question.

