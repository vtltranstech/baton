---
name: wiki
description: Generate and verify the per-module wiki with `baton wiki` and `baton verify`, and how to read a page. Use after /onboard, after a story changed modules, or when asked whether a wiki page can be trusted.
---
Wiki work: $ARGUMENTS

Run from the central repo. `baton <cmd>` is as the `workflow` skill says.

```text
baton extract --repo <repo>                 # first: claims are read from this output
baton wiki <repo> [--changed-since SHA] [--module M]
baton verify <repo>
```

`wiki` writes every page from the code and `dependencies.yaml` alone: no model, no quota, seconds per repo. Purpose lists each type with the first line of its Javadoc; Invariants lists the test methods. This is the default; use it.

`--prose` also sends each module's sources and tests to headless `claude -p`, one call per module, for written Purpose and Invariants. Only on a human's request, and say first that it makes one call per module and can hit the model's quota (for example Vertex AI). On a quota error it stops calling the model and writes the remaining pages from the code; the run's `withoutProse` lists them. Add prose to a few modules later with `--prose --module <name>`. `--changed-since` calls the model only for touched modules; the others move to the new commit with `verified: false`, so `verify` has to follow.

Who decides what on a page:
- Claims, Entry points, Reads / Writes, Calls, and Known pitfalls come from `profile/dependencies.yaml`, imports and `docs/context/pitfalls-log.md`.
- Purpose and Invariants observed in tests are read from the code (default) or are the model's prose (`--prose`). They are not checked by `verify`: treat them as a lead and confirm in the source before relying on one.
- `verified: true` comes only from `verify`. Never set it, and never edit a page or its claims to make it pass: the fix is in the code, in `baton extract`, or in regenerating the page.

Reading a page `docs/wiki/<repo>/<module>.md`: rely on it only with `verified: true` and a `generatedFrom` equal to the repo's `commit` in `profile/dependencies.yaml`. Anything else is never cited; read the source.

Reading `docs/wiki/<repo>/verify-report.json`: `pages[].reasons` says why a page failed. `commit: unknown` means the repo has no git history of its own and nothing can pass. `stale` means run `wiki` again. A claim that is `not in dependencies.yaml` is false or invisible to the extractors, and either way it fails. `modulesWithoutPage` lists gaps; they do not fail the run.

Exit codes: 0 ok; 1 a page failed or a model call failed (the old page stays); 2 missing input or `claude` not found, nothing written.
