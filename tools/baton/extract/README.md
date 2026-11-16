# `baton extract-stack`, `baton extract`, `baton onboard`

Stdlib Python, plus a JDK for JavaParser and Node for TypeScript; both parsers are vendored. The optional `baton[treesitter]` extra adds tree-sitter, the first choice for Java. No network. Paths are relative to `--central`.

```text
baton extract-stack [--repo R] [--central C] [--json]
baton extract       [--repo R] [--central C] [--json]
baton onboard [--interview] [--refresh] [--central C]
```
Exit codes: 0 ok; 1 a reviewed file cannot be read (nothing written), or `c4` failed; 2 `profile/project.md`, its repo table, a repo path or the named repo is missing (nothing written).

Repos come from the first table in `profile/project.md` with a `Repo` or `Path` column.

| Command | Writes | `--json` |
| --- | --- | --- |
| `extract-stack` | `profile/stack-detected.md` | `schemas/stack-detected.json` |
| `extract` | `profile/dependencies.yaml`, `aggregates.yaml`, `risk-zones.yaml`, and the rows of `stack-detected.md` | `schemas/dependencies.json`, plus `aggregates` and `zones` |
| `onboard` | what `extract` writes, plus what `c4` writes | always JSON: `ran`, `questions`, `answered`, `warnings`, optional `batches`, `refresh` |

`--repo` keeps the other repos' rows and entries. Risk-zone paths from other repos stay until a full run clears them.

## Reading Java
`parser.py` is the interface; extractors read only `model.py`. Per file the order is tree-sitter, JavaParser, regex; a file one refuses goes to the next. `treesitter_backend.py` runs in process when the `baton[treesitter]` extra (`tree-sitter`, `tree-sitter-java`) is installed, and builds the same model as JavaParser node for node; a syntax error is refused, not read around. `javaparser_backend.py` runs `vendor/javaparser-core-3.28.2.jar` through `helpers/AstDump.java`, one JVM per batch, at language level 26. It needs `java` and `javac` (`JAVA_HOME` first, then the PATH); the helper is compiled once into a temp-folder cache. `regex_backend.py` (a tokenizing scanner) takes any file both refuse, and every file when neither is there. The result is per file, in `parser` on each `dependencies.yaml` repo: `treesitter`, `javaparser` and `regex` counts, `fallback` files (a better back-end refused them; `fallback_reason` says why) and `unavailable` (no AST back-end). `BATON_JAVA_PARSER` names the first back-end to try: `javaparser` skips tree-sitter, `regex` forces the fallback. A file no back-end reads gives no edges and becomes a question.

Only `src/main/java` of the root and declared modules (`<modules>`, `settings.gradle` `include`) is walked. A nested folder with its own build file that the root does not declare is a separate project: not walked, and named in `warnings`.

## Reading TypeScript and React
`ts_backend.py` runs `helpers/tsdump.cjs` under Node on `.ts .tsx .js .jsx .mjs` in `src app pages lib` of a repo with a `package.json`, skipping tests, stories, declarations and `node_modules`. It parses with the repo's own `typescript` when that has the JS API, else `vendor/typescript-5.9.3.js`. `parser.typescript` records the version and file count. No Node on the PATH gives a failure, which becomes a question; there is no scanner fallback.

It finds `fetch` (`ts-fetch`) and `axios`, including a client from `axios.create` in the same file (`ts-axios`). `from` is `class:<path.with.dots>`. A `${x}` after the start of a path is the variable `{x}`; the query is dropped; a constant in the same file resolves. What the file cannot tell stays literal and is listed in `unresolved`: `endpoint:${VITE_API}/f`, or `endpoint:<src/a.ts:12>` for an expression. A wrapper or client imported from another file is not followed, so its calls are not seen.

## Values
- A placeholder resolves through `application.yml|yaml|properties` under `src/main/resources` (and `config/`) of the file's module, with Spring's relaxed names, nesting and `${x:default}`.
- Constants resolve through `static final` and interface fields: same class, other classes by import, static imports, concatenation. Non-final fields, parameters and method results do not. A field assigned from a `@Value` constructor parameter stays open.
- A base value wins, because that is what runs with no profile active. A profile that overrides it gives a `profile-override` question. A value found only in a profile file stays unresolved and is shown beside the question. If any config file is unreadable, placeholders stay open even with a default.
- What cannot resolve stays literal and is listed in `unresolved`: `${as.written}`, `<Class.name>` for a variable, `<Class:line>` for an expression. The class name stops two unrelated unknowns from becoming one graph node. A resolved `CALLS_ENDPOINT` is `endpoint:<METHOD> <url>`; an unresolved one has no method, per `EXPECTED.json`.
- `@RequestMapping` with no `method` gives `endpoint:ANY <path>`.

## Commit
`commit` is the short HEAD sha only if the repo path is itself a git top level. Otherwise it is `unknown`, with a `commit:<repo>` question: not a git repo, no commits yet, or a folder inside another repository (the fixtures in this tree), whose HEAD says nothing about this code. Uncommitted changes give a warning, because the edges then describe more than the sha.

## What a human reviewed
Only entries with `confirmed: false` are regenerated or dropped; any other entry in `aggregates.yaml` or `risk-zones.yaml` is kept as is. An unchanged list leaves the file's bytes alone. Seeded zones carry an additive `confirmed` field, which the schema allows. A path a seed finds outside a reviewed zone comes back as a question.

## Questions
One per open row of the plan's section 3, stable `id`, `gap` = the row. Answers go under `## Onboard answers` in `project.md` as `| id | answer |`, or close by state: a filled `## Domain words`, `## Invariants`, `## External systems`, confirmed seeds, a `Team` column, `CODEOWNERS`.

`--refresh` diffs the generated files against how they were before the run, ignoring `generated:`, and lists edges added and removed and commits moved.
