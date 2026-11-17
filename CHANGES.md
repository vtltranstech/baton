# UI stories: wireframes, the organisation's component library, gate 2a, screens of record

| Path | Change |
| --- | --- |
| `contracts/ui-stories.md` (new) | the UI stories guide adapted to baton: the architect's UI mode, `screen-spec.md`, the component library keys and inventory, the UX lens, gate 2a, screens of record, `ux verify`, the kit's sensors, and where it differs from the guide |
| `tools/baton/ux/` (new), `tools/baton/extract/extract_cmd.py`, `tools/baton/cli.py` | `baton ux inventory` (= `extract --ui`), `ux check`, `ux show`, `ux verify`, `ux diff`, `ux promote` |
| `tools/baton/orchestrate.py`, `skills/build`, `skills/workflow` | a `ui` story gets the wireframe, `baton ux check`, the UX lens and gate 2a (the PO, `--answer option-N --by PO`) before the design; on the light track one delta and one question for the PO and the Tech Lead (`--by PO+TL`), no auto-pass |
| `tools/baton/state_check.py`, `contracts/states.md` | Designed needs the approved wireframe and `## Wireframe approval` (full) or the delta (light) for a `ui` story |
| `tools/baton/confidence.py` | a serious or critical `axe.json` violation turns the sensors red; `ui-verify.json` HIGH zeroes the conformance signal, MEDIUM halves it |
| `agents/architect.md`, `developer.md`, `documentation.md`, `story-drafter.md` | UI mode; build from the spec with the library and the data attributes, then `ux verify`; `ux promote` and the UI metrics; the `ui` label |
| `skills/ux-checklist` (new), `skills/design-review-lenses`, `skills/review-lenses`, `skills/triage`, `skills/retro`, `skills/stories` | the UX lens; the screen check in the conformance lens; the `ui` label; gate 2a wait and UX-lens precision |
| `templates/ui/` (new), `templates/profile/project.md`, `templates/story.md`, `schemas/screen-spec.json` (new) | the lo-fi stylesheet, wireframe and spec templates; the `ui.*` keys; the spec's JSON schema |
| `templates/kits/react-ts-ui` | jsx-a11y, no direct import of what the library wraps, `npm run ui:sensors` (axe and Web Vitals through Playwright) |
| `fixtures/sample-ui/` (new) | a component library, a UI repo, the built screen, and two stories: a new screen with three options and a light delta |

# Agent blueprints, baton build, security last, starter kits; build-phase files removed

| Path | Change |
| --- | --- |
| `contracts/agent-enhancements.md` (new) | the guide adapted to baton and to Claude Code only: blueprints, outcomes, orchestration, security last, one consolidated fix, same bar, ticket input, systems of record, kits, enablement, baseline, `agents check`, and where it differs from the guide |
| `agents/*.md`, `docs/roles.md` | a `## Blueprint` block on all nine agents; the outcome table each one names |
| `tools/baton/agents_check.py` | `baton agents check`: blueprint fields, Input paths, Handoff gates and skills, Outcome rows, hooks, provenance rule, skill activation, the developer's triage-only rule |
| `tools/baton/orchestrate.py`, `skills/build` | `baton build <S>`: the order of one story's steps with a ledger (`-build.json`, heads per step); runs gate 0, deps, the gate 2 auto-pass, confidence, evidence and trace itself; prints the agent, skill or gate for the rest; `--done`, `--answer`, `--from`, `--status`, `--security-check`; the skill loops on it |
| `tools/baton/state_check.py`, `hooks/state_gate.py`, `contracts/states.md` | Approved needs a security report whose `Heads:` match every `feature/<F>-<S>` head; `Gate-0-Override:` (TL, by hand) accepts a refused gate 0; the hook refuses an agent edit that touches it |
| `agents/developer.md`, `security.md`, `qa.md`, `architect.md`, `story-drafter.md`, `documentation.md`, `release.md` | triage-only fix loop and `Heads:` in the Dev summary; security `Heads:`, re-run, risk-zone severity; manifest rules as QA expectations, `SE: agree / disagree`, unprofiled is a FAIL; architect reads rules by id, ledger names a test; EARS, rule ids, clarification drafts, Jira key; Confluence publish when a connector exists; release refuses a stale security report |
| `skills/stories`, `skills/jira`, `skills/onboard`, `skills/retro`, `skills/doc-style`, `skills/standards/stack.md` | `/stories <Jira key>`; the one-way Git to Jira mirror; the kit comparison; lens precision; the Baseline table; the same quality bar |
| `templates/kits/` (new), `templates/ci/central-ci.yml` (new), `tools/baton/install.py` | three starter kits (Spring Boot + Mongo, Spring Batch, React + TS) with sensors, hooks, same-bar CI, runbook; the central repo's CI; raw report folders ignored |
| `docs/enablement/` (new) | first story, demo script, FAQ, baseline |
| `tools/baton/trace/collect.py` | a Confidence section without `Why:` no longer crashes the trace |
| removed: `Archive.zip`, `IMPLEMENTATION-PLAN.md`, `worktrees/`, `tools/dev/` | build-phase files; the formats the contracts cited from the plan now live in `contracts/artefacts.md` and `contracts/confidence.md`; the project-word list moved out of the repo, to a git-ignored `tools/baton/tests/project-words.local.txt` read by `project_words.py` (the word tests skip without it) |

# baton board: where every story's work is, without asking

| Path | Change |
| --- | --- |
| `tools/baton/board.py`, `tools/baton/cli.py` | `baton board`: per story its State, gate 0, the `story/<F>-<S>` branch and the `feature/<F>-<S>` branch in every service repo (pushed, unpushed commits, merged), the tag, the last commit and the next move; `--story` for one story, `--fetch`, `--json`; read-only, no session needed |
| `tools/baton/state_check.py` | `Story.read`: a story file from disk or its story branch; gate 0 reads the context manifest of a story that lives only on its branch |
| `contracts/cli.md`, `docs/guide.md`, `skills/standup` | the command, when to run it; /standup lists what is not pushed or waits for a tag |

# Gate 0: nothing runs on a system the context map does not understand

| Path | Change |
| --- | --- |
| `tools/baton/context/check.py`, `skills/stories`, `skills/ready`, `skills/build`, `skills/sprint`, `skills/deliver` | gate 0 for features and stories, per track (full: understood; light: at most `light-open-questions` open questions, no contradiction; spike: listed only); when it refuses, the skill runs `/build-context-map focus F-x` itself, asks the human present, checks again, and goes on only when it passes |
| `tools/baton/state_check.py`, `contracts/states.md` | once `profile/branch-points.yaml` exists, Ready for PO, Ready and Designed need the story's context manifest, no blocking gap, and every changed area still passing in `docs/context/understanding/status.json` (an area gone stale after a merge refuses the move); no override |
| `tools/baton/context/understanding.py` | `## Contradictions` as `- C<n>:`; an unresolved one blocks its area for every track |
| `baton context answer`, `baton context questions`, `skills/standup` | a human answers a question or resolves a contradiction without a session, verbatim; `docs/context/questions.md` by person with age, OVERDUE after `question-ttl-days`; /standup prints it |
| `skills/build-context-map` | model-invocable so the gated skills can run it; prints `GATE 0: accepted` or `refused` when run by one |
| `contracts/context-map.md` 10.2, 10.4, 10.5, `contracts/cli.md`, `contracts/models-and-activation.md`, `schemas/context.json`, `templates/profile/context.yaml`, `docs/guide.md` | formats, the gate per track, `light-open-questions`, `question-ttl-days`, when to run what |

# Learn the system before building: /build-context-map

| Path | Change |
| --- | --- |
| **new** `skills/build-context-map/SKILL.md` | `/build-context-map [setup \| focus F-x \| refresh \| status]`: documents and drafts (moved from /onboard), context explorers in parallel, the integrator, grading, rounds of fixes, then it stops and asks the Product Owner and the Tech Lead what nobody could find, and folds the answers in |
| **new** `agents/context-explorer.md`, `agents/context-integrator.md` | a new engineer per area (purpose, every edge, every business branch point, contradictions, questions), and one who joins the areas into end-to-end flows and the landscape of upstream and downstream systems |
| **new** `tools/baton/context/understanding.py` | `baton context brief <area \| system>` and `baton context understand`: the notes graded against the extracted code (no claim without an edge and a resolving citation, every flow step joined, every entry point in a flow, no open blocking question) into `docs/context/understanding/status.*`; the context map gets a System understanding line |
| `tools/baton/context/check.py` | `baton context check F-001`: a feature is accepted for story drafting only when the areas it changes are understood and the systems at their edges named; exit 2 otherwise; `docs/design/<F>/<F>-context.md`; story manifests list the notes and flows of their scope |
| `skills/stories`, `agents/story-drafter.md`, `agents/architect.md` | `/stories` step 0 runs the feature check and drafts nothing while it fails; the drafter and the architect read the notes and flows |
| `skills/onboard` | stays with extraction, the workspace DSL, the diagrams, the wiki and its own interview; documents, the domain interview and refresh of drafts moved to /build-context-map |
| `contracts/context-map.md` section 10, `contracts/cli.md`, `schemas/context.json`, `templates/profile/context.yaml` | formats, checks and states; `explore-parallel`, `explore-rounds` |
| `fixtures/sample-context/understanding-example/` | notes, flows and landscape as an explorer would write them: billing understood, pricing blocked on six questions for the Product Owner |
| staleness per area | the note header carries `code=<hash>` of the area's own source and test files; a merge makes stale only the areas it changed; `/ship` (documentation agent step 5b) lists them in the change note |
| `docs/guide.md` "When to run what", `docs/quickstart.md` | which command to run on day one, for a new feature, after a merge, for new documents, and what to do for each reason `baton context check` gives |

# POD is now BATON; context map and document ingest

| Path | Change |
| --- | --- |
| `tools/pod/` -> `tools/baton/` | the CLI is `baton`, the Python package `baton`; `pod` and `harness` stay as aliases for one release and print a note |
| everywhere in agents, skills, hooks, tools, contracts, docs, templates, fixtures | `baton` commands, `baton:provenance` footers, `baton.*` architecture stamps, `BATON_*` variables, the `.baton/` cache, plugin name `baton` (MCP tools `mcp__plugin_baton_graph__*`) |
| `tools/baton/install.py` | an upgrade reads `.claude/pod-install.json` or `.claude/harness-install.json`, removes `.claude/tools/pod/` or `.claude/tools/harness/`, moves the graph server in `.mcp.json` |
| compatibility | `pod:`/`harness:` footers, `pod.*`/`harness.*` stamps, `POD_*`/`HARNESS_*` variables and `podTarget*`/`harnessTarget*` PIT properties keep working; `tests/W1/test_rename_compat.py` |
| **new** `contracts/context-map.md`, `tools/baton/context/`, `schemas/context.json`, `schemas/branch-points.json`, `templates/profile/context.yaml` | `baton context ingest \| build \| score \| check S \| gaps \| trend`: business branch points, domain.md as an index, drafts from code, tests, clarifications and documents, coverage per layer, a context map per module, the per-story sufficiency check |
| `tools/baton/context/ingest.py`, `tools/baton/context/ocr.py` | Confluence pages (HTML export, or fetched by the Confluence MCP server in /onboard and cited by URL), XML, Markdown, text, CSV, JSON, Word, PowerPoint and Excel into `docs/context/sources/`; PDF with the `baton[pdf]` extra (pypdfium2); OCR of images, scanned PDF pages and images inside Word and PowerPoint with Tesseract, using only the binary and language files installed from the organisation's mirror; nothing is downloaded |
| `skills/ready`, `skills/build`, `skills/onboard`, `skills/standup`, `agents/architect.md`, `tools/baton/state_check.py` | `/ready` runs the context check and a blocking gap keeps a story out of Ready; `/build` re-checks; the architect starts from the manifest; `/onboard` ingests, builds and scores; `/standup` prints readiness |

Upgrade: `pipx uninstall pod`, `pipx install --force <checkout>/tools/baton` (add `pipx inject baton tree-sitter tree-sitter-java` for the tree-sitter parser), `baton install` in each central repo, commit `.claude/`.

# harness is now POD

| Path | Change |
| --- | --- |
| `tools/harness/` -> `tools/pod/` | the CLI is `pod`, the Python package `pod`; `harness` stays as an alias for one release and prints a note |
| everywhere in agents, skills, hooks, tools, contracts, docs, templates, fixtures | `pod` commands, `pod:provenance` footers, `pod.*` architecture stamps, `POD_*` variables, the `.pod/` cache, plugin name `pod` (MCP tools `mcp__plugin_pod_graph__*`) |
| `tools/pod/install.py` | an upgrade reads `.claude/harness-install.json`, removes `.claude/tools/harness/`, moves the graph server in `.mcp.json` |
| compatibility | old footers, `harness.*` stamps, `HARNESS_*` variables and `harnessTarget*` PIT properties keep working; `tests/W1/test_rename_compat.py` |
| `README.md` | POD runs on a coding harness (Claude Code today); it is the SDLC layer above the runtime the harness-engineering literature describes |

Upgrade: `pipx uninstall harness`, `pipx install --force <checkout>/tools/pod`, `pod install` in each central repo, commit `.claude/`.

# Model per role, conditional skill activation, stories across branches

| Path | Change |
| --- | --- |
| **new** `contracts/models-and-activation.md` | extractor decision (tree-sitter; planned for W2, not built), conditional skill activation, model per role with the reviewer rule, the POD rename |
| **new** `templates/profile/models.yaml`, `schemas/models.json`, `tools/harness/models.py` | `harness models S`: the model per role for the story's track, escalations after a failed QA loop or diff-shape flags, the implementer / reviewer pairing; refuses a file where a reviewer is weaker than what it reviews |
| `skills/build`, `review-lenses`, `design-review-lenses`, `stories`, `ship`, `agent-regression`, `workflow` | every agent and lens subagent is launched with its model from `harness models`; gate prompts name the pairing; the footer gains `model:`; metrics gain impl and review model columns |
| agents, `skills/design-diagram`, `story-writing`, `change-note`, entry-point skills, `skills/build` | `paths:` activation for the doc skills, agent `skills:` preloads, `model: inherit`, `disable-model-invocation` on `/sprint /deliver /onboard /retro /agent-regression /standup /sprint-review`, `/build` registers its gate hooks |
| **new** `tools/harness/stories.py`, `tools/harness/state_check.py`, `tools/harness/deps.py`, `tools/harness/trace/collect.py` | stories that live only on their `story/<F>-<S>` branch are found: `harness stories`, `Depends-On` checks, `harness deps` and the trace page read them through git |
| `skills/standup`, `sprint-review`, `sprint`, `deliver` | list stories with `harness stories` |
| `tools/dev/precommit_check.py` | W1 may commit the trace, stamps, stories, models, contracts and the two schemas |
| `worktrees/W2-extract/BRIEF.md` | the tree-sitter delta |

# Versioning of the central repo, and the feature trace page

| Path | Change |
| --- | --- |
| `skills/workflow`, `agents/developer.md`, `agents/release.md`, `hooks/protect_main.py` | every PR targets the repo's default branch (`origin/HEAD`, else `main`), and branches start from it; `protect_main` guards the default branch whatever its name |
| `skills/workflow` | central-repo story branch `story/<F>-<S>` and the commit-points table with fixed messages (contracts/versioning.md section 1); agents never read `docs/archive/` |
| `skills/stories`, `skills/ready`, `skills/build`, `skills/sprint-review`, `skills/ship` | the first skill that writes for a story creates its branch from main; a commit with the fixed message after every agent and every gate |
| **new** `hooks/commit_scope.py`, `hooks/hooks.json`, `templates/settings.json` | on `story/*` in the central repo, a commit holding another story's or feature's files is refused; shared files pass |
| **new** `tools/harness/graph/stamps.py`, `tools/harness/graph/c4_cmd.py` | `harness c4 --story S` stamps new and changed elements and relationships with the feature tag and `harness.story` / `feature` / `since` / `changed-by`, appends to `docs/architecture/CHANGELOG.md` (removals as `removed-by S`); every run keeps earlier stamps and `--check` ignores them |
| `agents/documentation.md` | promotes with `harness c4 --story`; never stamps by hand |
| `agents/release.md` | opens the central-repo PR for `story/<F>-<S>` and links it with every code PR both ways |
| `tools/harness/cli.py` | `harness tag <S or F>`: annotated tag on the default branch; refused elsewhere or when the tag exists |
| `skills/ship`, `skills/retro`, `tools/harness/state_check.py` | `/ship <F>` archives a finished feature to `docs/archive/<F>/` after its last story merged; archived stories still resolve for `Depends-On` |
| **new** `tools/harness/trace/` | `harness trace F [--story S] [--open]`: one self-contained page per feature (contracts/trace.md); reads live and archived features; architecture from the CHANGELOG and stamps |
| `skills/workflow`, every agent, `skills/change-note`, `skills/story-writing`, `skills/design-diagram` | every Markdown artefact ends with a provenance footer (contracts/trace.md section 2) |
| `skills/ready` | a clarification is `- <date> Q: ... A: ...`; an answer that becomes a domain rule ends `-> domain.md: <rule>` after the human agrees |
| `contracts/versioning.md`, `contracts/trace.md`, `contracts/cli.md`, `contracts/README.md`, **new** `schemas/trace.json` | the default branch, `harness c4 --story` stamping, archive after merge, ASCII messages and the missing commit points; trace inputs matched to the framework; rows for `tag`, `trace`, `c4 --story` |
| `fixtures/sample-central-repo` | feature F-FIX: S-151 Done with every artefact, S-152 Designed after a failed QA loop, no mutation.json; stamped workspace and CHANGELOG |

# Risk-tiered review, measurement, faster mutation

| Path | Change |
| --- | --- |
| **new** `tools/harness/risk.py` | `harness risk S`: low / medium / high from the design's touch points, the diff, risk zones, labels, track and estimate; the higher of design and diff wins; writes `-risk.json` |
| `skills/build`, `skills/review-lenses`, `agents/qa.md`, `skills/workflow` | `/build` runs `harness risk` before QA; QA runs the lenses `-risk.json` lists: low = conformance + verification-gap (+ domain when the design names a rule), else all five; security and every gate run whatever the tier; triage adds a `## Findings by lens` table; the QA agent's out-of-date "two lenses" line is gone |
| `tools/harness/confidence.py` | a domain lens left out by a low tier is not scored as a missing fidelity line; only when `-risk.json` says so |
| **new** `tools/harness/evaluate.py` | `harness eval S` / `--all`: minutes, tokens, re-reads per agent, waiting between agents, unique findings per lens; from local Claude Code transcripts, read-only |
| `tools/harness/reads.py` | `--story` finds the story's agents from the transcripts; nothing set the `HARNESS_STORY` tag it relied on |
| `tools/harness/mutation/pit.py`, `schemas/mutation.json` | the score counts mutants on changed lines only and skips logging lines (Google's diff-based mutation testing); PIT runs on several threads with history; `scope` and `classScore` added |

# Readable diagrams

| Path | Change |
| --- | --- |
| `tools/harness/diagram/output.py` | `index.html` shows each diagram at its own size with sideways scroll, a Fit to width / Actual size button and an Open full size link; nav anchors no longer hide the heading; `diagrams.md` links each SVG at full size under its image |
| `tools/harness/diagram/svg.py`, `draw_sequence.py`, `draw_flow.py` | small text one point larger (message and link labels, sub-text, legend, subtitle); sequence labels may wrap onto two lines instead of widening the gap between lifelines; flow gaps tighter; a wrapped label at the start of a fragment stays clear of its tag |

# Subagents in the foreground

| Path | Change |
| --- | --- |
| `templates/settings.json`, `tools/harness/install.py` | `env.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, added by install when the project has not set it: a background subagent's report returns as an injected prompt, which an organisation `UserPromptSubmit` hook can refuse; a foreground report is a tool result |
| `skills/workflow`, `build`, `ship`, `stories`, `agent-regression`, `review-lenses`, `design-review-lenses` | launch subagents in the foreground and wait for each report |
| `docs/guide.md` | troubleshooting row for "prompt blocked" after a subagent |

# Generic core: no product vocabulary

| Path | Change |
| --- | --- |
| `contracts/artefacts.md`, `contracts/confidence.md`, `skills/design-diagram`, `skills/doc-style`, `skills/story-writing`, `tools/harness/diagram/spec.py`, `ir/cmd.py`, `graph/mcp_server.py` | examples use a neutral orders domain instead of one product's terms |
| `tools/harness/install.py`, `templates/profile/` | install no longer seeds `dependencies.yaml`, `aggregates.yaml`, `stack-detected.md`: the templates held the sample repo's data, so a new project started with another product's stack and edges; /onboard writes them |
| `tools/harness/tests/W1/test_plugin.py` | fails when agents, skills, hooks, sensors, templates or contracts name a product |
| `docs/guide.md`, `docs/walkthrough.html` | the IR example uses the orders domain |

# One command per feature

| Path | Change |
| --- | --- |
| **new** `skills/deliver` | `/deliver F-x`: `/stories`, gate 1, `/build` per story in dependency order, gate 3, `/ship`; asks only at the gates; resumable from the story States |
| `docs/guide.md`, `docs/quickstart.md`, `docs/walkthrough.html`, `README.md`, `skills/workflow` | list `/deliver` and its stops |

# Windows hooks and `harness install`

| Path | Change |
| --- | --- |
| `hooks/hooks.json`, `templates/settings.json` | every hook in shell form under bash (`bash "<root>/hooks/run-hook" x.py`, `"shell": "bash"`), no `args`: exec form cannot start an extensionless script on Windows, so every gate failed there |
| **new** `.gitattributes` | LF for hooks, scripts, Python, JSON, Markdown: a CRLF checkout breaks run-hook under Git Bash |
| `tools/harness/env.sh`, `hooks/run-hook` | Python also found through the Windows `py -3` launcher |
| **new** `tools/harness/install.py` | `harness install [--check] [--force]`: the copied install, upgrades in place with a manifest, keeps project edits (conflicts) and project settings |
| `docs/quickstart.md`, `templates/CLAUDE.md`, `contracts/cli.md` | install with `harness install`; Windows needs Git Bash; read code through the IR |

# Code as operations and effects (the IR)

Agents read the code through a compact IR instead of the codebase map, the wiki index and `profile/dependencies.yaml`. On a 12-service product: 778 tokens for the one-line-per-unit view against 48,700 for the map plus dependencies.yaml; a story's context pack is 1,000-2,000 tokens.

| Path | Change |
| --- | --- |
| **new** `tools/harness/ir/` | `harness ir show` (unit, class, operation, resource), `harness ir find <words>`, `harness ir slice <S> [--write]` (`.harness/context/<S>.md`). Effects lifted through calls with exact recursion (strongly connected components); interface calls follow their implementation; overloads keyed by signature, also through interfaces; calls on data classes and trivial accessors hidden |
| `tools/harness/diagram/codemap.py` | each call records its argument count (code map version 2: caches rebuild once) |
| `tools/harness/diagram/context.py` | the card hides calls on data classes and lists callers of the right overload only |
| `tools/harness/graph/mcp_server.py` | new tools `graph.ir` and `graph.find` |
| **new** `hooks/read_log.py`, `tools/harness/reads.py` | a PostToolUse hook logs every Read, Grep, Glob and Bash (path, size, first two words of a command, never content) to `.harness/reads.jsonl`; `harness reads` reports per agent reads, re-reads, scans, shared files and ~tokens |
| `agents/architect.md`, `agents/developer.md`, `agents/qa.md`, `skills/workflow` | read the IR before Grep or files; the architect writes the context pack after a clean `harness diagram story`; the developer and QA start from it; a wiki page's freshness comes from its map row, never from dependencies.yaml |
| `hooks/hooks.json`, `templates/settings.json` | register `read_log.py` |

# Diagrams from the code (this release)

Diagrams are no longer drawn by the agent. The architect writes a short change spec and `harness diagram` draws everything from the code's AST, checked against the code.

| Path | Change |
| --- | --- |
| **new** `tools/harness/diagram/` | `harness diagram story <S>` (flow with impacts, a sequence per entry point, low-level design, data model, use cases, touch-points and blast-radius tables; `--check`; `--diff REF` for as-built + design conformance), `harness diagram architecture` (context, containers and data, components per repo), `harness diagram context <name>` (a ~20-line code card for agents). SVG + Markdown + HTML + Mermaid; stdlib only, no model, no network |
| `tools/harness/extract/helpers/AstDump.java`, `extract/model.py`, both parsers | methods carry end line, return type, visibility; types carry end line |
| `tools/harness/graph/mcp_server.py` | new tool `graph.context` |
| `tools/harness/evidence.py` | design section reports the generated diagrams and design conformance |
| `skills/design-diagram/SKILL.md` | rewritten: change spec -> `harness diagram`; no hand-written Mermaid or DSL |
| `agents/architect.md` | writes the change spec, embeds the generated SVGs; reads code through context cards; tools add Bash and `graph_context`, `graph_impact` under both the plugin and the copied-install MCP names |
| `skills/design-review-lenses`, `review-lenses/references/conformance-lens.md`, `skills/build`, `agents/documentation.md`, `skills/onboard`, `skills/workflow`, `templates/CLAUDE.md`, `docs/roles.md` | no candidate workspace or DSL delta any more; as-built diagrams after /build; workspace.dsl and the architecture diagrams regenerated from merged code |
| `contracts/cli.md`, `contracts/artefacts.md` section 10-11, `contracts/graph.md` | the new command, spec and outputs |
| **new** `skills/doc-style/SKILL.md` | the writing standard for docs/: ASCII only, tables for facts, `- **Term:** fact` bullets under 20 words, one-line `> [!NOTE]` caveats, no filler; exact formats of status.md, metrics.md, change note, ADR |
| **new** `tools/harness/doclint.py`, `hooks/doc_lint.py` | `harness doclint [--fix]`; a PostToolUse hook runs it after every Write/Edit under docs/ and hands problems back to the agent (`hooks/hooks.json`, `templates/settings.json`) |
| `agents/documentation.md`, `agents/release.md`, `agents/story-drafter.md`, `skills/change-note`, `skills/build`, `skills/workflow` | load doc-style; status.md and metrics.md in its fixed tables; doclint before setting State |
| `tools/harness/wiki/index.py` | codebase map: one table per repo (page, status, data, APIs) |
| `agents/`, `skills/`, `templates/`, `contracts/`, `hooks/`, all generated output | ASCII only (a test keeps it that way) |

# Changes since pod-core 0.1.0 (the last zip you installed)

Keep your `profile/`, `docs/`, `CLAUDE.md` (apply the two line changes below by hand or take the first project's copy). Replace `agents/` and `skills/` wholesale — upgrade = replace core, never touch profile/docs.

| Path | Change |
| --- | --- |
| `skills/codebase-onboarding/` → `skills/onboard/` | renamed (`/onboard`); every reference updated |
| `skills/workflow/SKILL.md` | rewritten: principles, roles (PO intent / TL feed-forward / SE feedback), SE first reader + TL decider at gates 2 and 3, attachments convention, hooks, confidence step 6a, monthly calibration |
| `agents/architect.md` | reads `docs/architecture/workspace.dsl` or stops; full note gets **3a. C4 delta (Structurizr DSL)** + candidate `docs/design/<F>/<S>.dsl`; light note gets `C4 delta:` line; ArchUnit install as task 1 when missing |
| `skills/design-diagram/SKILL.md` + `references/workspace-template.dsl` | new C4 / Structurizr section: project workspace, per-story delta + dynamic view, validation rules |
| `skills/design-review-lenses/SKILL.md` | rubric walker checks the DSL; seam lens reads the candidate workspace |
| `skills/review-lenses/references/conformance-lens.md` | check 8: architecture changed without a delta = HIGH |
| `agents/documentation.md` | step 5: promotes the candidate workspace into `docs/architecture/` |
| `skills/standards/stack.md` | new section **Architecture tests (mandatory — ArchUnit)** |
| `agents/developer.md`, `agents/qa.md`, `skills/review-lenses/references/craft-lens.md`, `skills/standards/sensors/README.md` | ArchUnit mandatory: `archunit.txt` required, QA FAIL / craft HIGH without it; `## Human findings` section in the test report |
| `PROFILE.md`, `README.md`, `.claude-plugin/plugin.json` | harness 0.2.0; new profile files listed |
| **new** `IMPLEMENTATION-PLAN.md`, `contracts/`, `schemas/`, `worktrees/` | the build plan for the six parallel worktrees |
| **new** `tools/harness/miniyaml.py` | seed for W1 (stdlib YAML-subset reader) |

First project's profile: `profile/sensors/ArchitectureTestExtra.java` removed (guessed rules; replaced by `profile/sensors/README.md` as the record); new `profile/risk-zones.yaml`, `profile/confidence-weights.yaml`, `docs/architecture/README.md`; `CLAUDE.md` and `project.md` updated.
