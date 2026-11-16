# BATON - model routing, conditional skill activation, tree-sitter extractors

Three decisions from the harness-engineering paper review, plus the rename. Status: sections 1 to 4 are implemented; section 1 lists what was left out and why.

---

## 1. Extractors: tree-sitter, not javalang, not regex (decision D1, settled)

**Before:** the bundled JavaParser helper (`extract/helpers/`, run with `javac`/`java`) with a regex fallback when Java is absent. TypeScript is read by the TypeScript compiler API under Node (`ts_backend.py`), not by regex. javalang is not used.

**Why it is more effective than the baseline (and than the javalang the briefs once named):**

| | regex | javalang | tree-sitter |
| --- | --- | --- | --- |
| Java 17/21 syntax (records, sealed, switch patterns, text blocks, `var`) | blind | **fails** - grammar stops around Java 8; records and sealed classes raise parse errors | full, maintained grammar |
| Multi-line annotations, nested generics, lambdas in `@Query` values | brittle | ok | exact |
| Broken or half-edited file (a branch mid-story) | partial | throws, whole file lost | error-tolerant: returns a tree with ERROR nodes, the rest still extracts |
| TypeScript / TSX (React repo) | brittle | none | `tree-sitter-typescript` |
| Speed on 8 repos | fast | slow (pure Python) | native, ms per file |
| Provenance (file:line:col for every edge) | approximate | yes | yes, byte-exact |

The paper's finding (Obs. 9, Rec. 8/16): every production coding agent that extracts structure uses tree-sitter plus ripgrep; none uses embeddings. We are building the same kind of extractor, so the same tool applies.

**Implementation (built):**
- `extract/treesitter_backend.py` reads the tree in process and builds the same model (`extract/model.py`) as `helpers/AstDump.java`, node for node, so no extractor changed. `tests/W2/test_parsers.py` holds the two back-ends equal on every fixture file and on a file of hard syntax (records, sealed types, switch patterns, record patterns, text blocks, anonymous classes, local types, varargs, qualified `this`/`super`), including lines, method ends, return types, visibility and the comment-free source.
- Optional extra `baton[treesitter]` = `tree-sitter`, `tree-sitter-java` (prebuilt wheels). The stdlib-only install keeps working without it.
- Order, per file: tree-sitter, else JavaParser (one JVM per batch for the files left), else regex. `BATON_JAVA_PARSER` names the first to try: `javaparser` skips tree-sitter, `regex` forces the scanner. A file a back-end refuses goes to the next, and `fallback_reason` names each refusal (`treesitter: syntax error at line 2; ...`).
- `dependencies.yaml` `parser` per repo: `treesitter`, `javaparser`, `regex` file counts, `fallback` files, `unavailable` (no AST back-end).
- A syntax error is refused, not read around: the "never half-extracted" rule wins over tree-sitter's error tolerance, so a broken file still becomes a question.

**Left out, on purpose:**
- **`.scm` query files per extractor.** The extractors already read a parser-independent model; a new stereotype is a Python extractor in `extract/extractors.py` over that model, whichever back-end ran. Queries would duplicate the extractors per back-end. A declarative stereotype file over the model is the route if non-framework teams must add stereotypes; not needed while the twelve extractors cover the contract.
- **`tree-sitter-typescript`.** The TypeScript compiler API is the reference parser for TS/TSX and is already used; swapping it would lose nothing but Node, and Node is needed for the React build anyway.
- **`-regex` extractor names and the confidence cap of 80 for regex-sourced edges.** Edge `extractor` names are fixed by `fixtures/*/EXPECTED.json`, and a cap needs a new key in `profile/confidence-weights.yaml`. The `parser` record already shows per repo which files the scanner read. Open: decide whether to add the cap.
- **A Java 21 file in `fixtures/sample-java-repo`.** Adding it would change that fixture's 20-file count and expected edges; Java 21 syntax is covered by the parser tests instead.

---

## 2. Conditional skill activation

**What Claude Code offers** (`code.claude.com/docs/en/skills`): frontmatter `paths:` (glob list; the skill auto-loads only when Claude works with matching files; globs are relative to the session's working directory and files outside it never match), `user-invocable: false` (only Claude may load it; hidden from `/`), `disable-model-invocation: true` (only a human may run it), `context: fork` + `agent:` + `model:` (run the skill as a subagent on a chosen model), `hooks:` (register hooks for the session when the skill is invoked), and subagent `skills:` preload (an agent gets the full skill text at startup).

**The catch for us:** `paths` is relative to the working directory. In the multi-repo layout the service code is `../api-service/...` - outside the product root - so `paths` would never fire for code-driven skills. Therefore two mechanisms, by layout:

| Skill | Mechanism | Frontmatter / agent change |
| --- | --- | --- |
| `design-diagram` | `paths` (design folder is always under the root) | `paths: ["docs/design/**", "docs/architecture/**"]`, `user-invocable: false` |
| `story-writing` | `paths` | `paths: ["docs/stories/**", "docs/features/**"]`, `user-invocable: false` |
| `change-note` | `paths` | `paths: ["docs/changes/**", "docs/decisions/**"]`, `user-invocable: false` |
| `data-check` | preload into the agent (code may be outside cwd) | `agents/qa.md`: `skills: [data-check, review-lenses]`; single-repo layouts may add `paths: ["**/repository/**", "**/*Repository*.java", "**/*Document*.java"]` |
| `security-checklist` | preload | `agents/security.md`: `skills: [security-checklist]` |
| `standards` | preload where it is read | `agents/architect.md`, `agents/developer.md`: `skills: [standards]`; the craft lens loads it explicitly |
| `review-lenses`, `design-review-lenses`, `elicitation` | stay invocable (`/review-lenses S-010` is a legitimate human command) | no change |
| Workflow entry points (`/sprint /deliver /onboard /retro /agent-regression`) | human-only - a gate must never be started by the model on its own | `disable-model-invocation: true` on each |
| Chained workflow skills (`/stories /ready /build /ship /build-context-map`) | stay model-invocable: `/deliver`, `/sprint`, `/stories` and `/build` run them (and `/stories`, `/ready`, `/build` run `/build-context-map focus` when gate 0 refuses), and `disable-model-invocation` would block that chain. Their gates are still human: the state-gate hook and the AskUserQuestion answers decide | no flag; the W1 test checks they have none |
| Reference skills (`workflow`, `triage`, `doc-style`, `jira`, `impact`, `wiki`) | stay model-invocable: agents and skills load them by name ("read the `workflow` skill") | no flag; `baton agents check` fails a skill that declares no activation |
| `/standup`, `/sprint-review` | human-only too (they read state; harmless, but the rule is simpler as "all workflow skills") | `disable-model-invocation: true` |
| `build` | registers the commit-scope and state-gate hooks for the session as a belt-and-braces (they are also in `hooks.json`) | `hooks:` block per the hooks docs; the command is `bash "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR}/.claude}/hooks/run-hook" <hook>.py`, so it runs as a plugin and as a copied install |

Effect: the main session's skill listing shrinks to the commands a human types; role skills cost nothing until the agent that needs them starts; no agent has to "remember" to load its know-how. Record the preload list in each agent's provenance footer (`skills:`) so the trace shows what was actually in context.

Verification: `tests/W1/test_activation.py` opens each `SKILL.md` and agent, checks the frontmatter keys above against this table, fails on an entry-point skill without `disable-model-invocation: true`, and on a chained skill with it. Every agent has `model: inherit`.

---

## 3. Cross-model review: implementer on one model, reviewer on another

**Principle:** independence by context (fresh subagent) *and* by model. Two rules, in this order:
1. **The reviewer is never a weaker model than the implementer.** A cheaper reviewer rubber-stamps a stronger author.
2. **The reviewer differs from the implementer whenever rule 1 allows.**

So "Sonnet implements, Opus reviews" is the default pairing; "Opus implements, Sonnet reviews" is never allowed (it breaks rule 1). When the implementer must be Opus (full track, complex design), the reviewers are Opus too - still independent by context, not by model - and the trace says so.

**`profile/models.yaml`** (owned by the Tech Lead; schema `schemas/models.json`; the core ships `templates/profile/models.yaml` with these defaults):
```yaml
version: 1
aliases:            # map to what your gateway exposes; values are passed verbatim to Claude Code's model field
  fast: sonnet
  strong: opus
  cheap: haiku
roles:
  story-drafter:   { light: fast,   full: fast,   spike: fast }
  architect:       { light: fast,   full: strong, spike: strong }
  developer:       { light: fast,   full: fast,   spike: fast }
  design-lenses:   { light: strong, full: strong, spike: strong }   # gate 2 readers
  review-lenses:   { light: strong, full: strong, spike: strong }   # gate 3 readers (edge, verification, craft, conformance, domain)
  qa:              { light: fast,   full: fast,   spike: fast }     # orchestrates; the lenses above carry the judgement
  security:        { light: strong, full: strong, spike: strong }
  documentation:   { light: cheap,  full: fast,   spike: fast }
  release:         { light: cheap,  full: cheap,  spike: cheap }
escalation:
  developer_after_qa_fail: strong        # loop 2 runs the developer on the strong model
  developer_when_diff_shape_flags: strong # lines over estimate or new dependency -> re-run on strong
rules:
  reviewer_never_weaker_than_implementer: true
  reviewer_differs_from_implementer_when_possible: true
```
Ordering for rule 1 is `cheap < fast < strong` (declared in the schema). The tool refuses a file that violates rule 1 for any track.

**Implementation (W1):**
- Agent files keep `model: inherit`; the **skill that launches an agent chooses the model** by reading `profile/models.yaml` for the story's track and passing it on the Agent/Task call (`model:` parameter), and the same for every lens subagent spawned by `review-lenses` / `design-review-lenses`. A skill run as a fork (`context: fork`) uses its `model:` frontmatter only as the fallback.
- `baton models <story-id>` (and `--check` for the file alone) prints the resolved model per role for that story, applying the escalations it finds (a failed QA loop in the test report or `docs/status.md`; diff-shape flags: a new dependency or lines over the estimate) (used by `/build` at start and shown in the gate prompts: "design by opus, reviewed by opus, built by sonnet, reviewed by opus").
- Provenance footer gains `model: <alias> (<resolved>)`; the trace page shows implementer/reviewer models on the Build and QA nodes; `docs/metrics.md` gains two columns (`impl_model`, `review_model`) so `/retro` can compare fix loops and escaped defects by pairing. That is the only way to learn whether the strong reviewer is worth its cost per track - the weights stay honest.
- Hooks cannot enforce model choice (the tool call carries it); the provenance line is the audit. `/agent-regression` runs with the same `models.yaml` as production so golden outputs compare like with like.

**Cost note for the Tech Lead:** on the light track this pairing spends the strong model only on the five lenses and security, not on drafting, building or docs; on the full track it adds the architect. If the gateway meters by model, the per-story cost row in metrics will show the split.

---

## 4. Renames: harness -> POD -> BATON - done

harness -> POD because the harness-engineering paper owns the word "harness"; POD -> BATON by the owner's choice (a baton is what each agent hands to the next, gate by gate).

- `.claude-plugin/plugin.json` `name: baton`; the CLI is `baton` (`tools/baton/`, Python package `baton`); provenance key `baton:provenance`; DSL properties `baton.story`, `baton.feature`, `baton.since`, `baton.changed-by`; environment variables `BATON_*`; the project cache `.baton/`; hook file names unchanged.
- One sentence in README: "BATON runs on a coding harness (Claude Code today); it is the SDLC layer above the runtime the harness-engineering literature describes."
- Kept for one release, for both earlier names, so nothing installed before a rename breaks: the `pod` and `harness` commands (aliases that print a note), `pod:provenance` and `harness:provenance` footers, `pod.*` and `harness.*` stamps (read, and rewritten as `baton.*`), `POD_*` and `HARNESS_*` variables (read when the `BATON_*` one is unset, in that order), `.claude/pod-install.json`, `.claude/harness-install.json`, `.claude/tools/pod/` and `.claude/tools/harness/` (an install upgrades them, and moves the graph server in `.mcp.json`), and the `podTarget*` and `harnessTarget*` PIT properties of build files installed earlier. The `.pod/` cache of a project is simply no longer used; `.baton/` is rebuilt.
- `tests/W1/test_rename_compat.py` fails on any other "harness" or "pod" in agents, skills, hooks, tools, contracts, docs or templates.
