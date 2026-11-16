---
name: onboard
description: Brownfield onboarding - run the deterministic extractors over the sibling service repos (stack, edges, workspace DSL, architecture diagrams, wiki), interview the humans for what extraction could not find, and write docs/context/codebase-map.md plus a verified agent-instructions block in CLAUDE.md. Run once before the first sprint, then refresh after significant change; /build-context-map follows it. Use as /onboard [setup|refresh|record|audit].
disable-model-invocation: true
---
Onboard the codebase: $ARGUMENTS (setup | refresh | record | audit; default setup).

Load `references/best-practices.md` and `references/template.md` first; every decision below is made against them. The admission test is theirs: not "could an agent derive this" but "what does it cost when it doesn't".

Conversational; the human approves every write. No writes until step 5, with one named exception, approved by the human before the command runs: the generated files of step 2a. Documents, the domain and how the system works end to end are not this skill's job: `/build-context-map` reads them after it (step 6).

`baton <cmd>` is as the `workflow` skill says, run from this repo. The model never decides structure: stack facts, edges, collections, aggregates and risk zones come from the extractors or from a human. A value the extractors report as `unknown` or under `unresolved:` is asked about, never filled in.

## 0. Check this machine
Run `baton --help`, `python3 --version`, `javac -version` and `node --version`. If `baton` is missing, or `python3` is older than 3.11, stop and say this machine has not been set up: install Python 3.11 or later as `python3`, then install the `baton` command with `pipx` as the framework quickstart says. If `javac` is missing, say Java files will be read by the simpler scanner; if `node` is missing, say React and TypeScript files will not be read; then continue. Do not install anything, and do not guess a path.

## 0a. Confirm this is the product
The central repo is the folder Claude Code started in. Never use `--central`, and never read or run anything under a `fixtures/` folder: those are the framework's samples, not this product. If `profile/project.md` is missing here, stop: say the folder you are in, and that onboarding must start in the product's central repo with that file filled in. Do not look for one elsewhere. Print the current folder and each repo in the table with its full path, and ask the human to confirm them with AskUserQuestion before going on. A row that still says `<repo>` or points at a missing folder is a stop, not a guess.

## 1. Assess
Read `CLAUDE.md`, `profile/project.md`, `profile/domain.md`, `docs/context/codebase-map.md`, and each repo in the profile's repo table (`../<repo>`): its README, build files, CI config, any AGENTS.md or CLAUDE.md of its own. Report what exists and how it measures up. Existing instructions are the baseline being improved, never raw material to discard: open a ledger - one entry per existing instruction line, `retain | rewrite | relocate | automate | delete`, each with its reason. Deletion needs one of the grounds in best-practices.md.

## 2. Ask what the humans bring
Rules that hold regardless of what the repos do: bank policy (branch rules, frozen paths, secrets handling, the test environment-only, no deploy), coding standards, review requirements, external docs (Confluence pages, the target design doc, the field-lineage doc). Note paths; do not read yet.

## Progress and failure rules (apply to every step)
- Print a one-line progress marker before each step ("Step 2a - detecting stack: 4 repos") and a one-line result after it. A run must never go silent.
- Do stack detection INLINE, in this session, never via a subagent: it is a handful of file reads per repo and a subagent adds nothing but a failure point.
- The steps below use no subagents now. Where one is used anyway, launch them in the FOREGROUND in one message, wait for every one to return, then print a checklist: repo -> done | failed | empty. A failed or empty result is retried inline by you, in this session, before continuing. Never carry on with a repo missing and never assume a subagent wrote a file - read the file back.
- If a previous run left partial output (a `profile/stack-detected.md` with some rows, a half-written codebase map), say so first and resume from the gap rather than starting over.

## 2a. Run the extractors (mechanical, INLINE; writes the generated files)
Say exactly what `baton onboard` will write and get a yes: `profile/stack-detected.md`, `profile/dependencies.yaml`, `profile/aggregates.yaml`, `profile/risk-zones.yaml`, and `docs/architecture/workspace.dsl` plus the git-ignored `.baton/graph.sqlite` if `c4` is built. It touches nothing else and never commits. Entries a human has confirmed are never overwritten: only entries still at `confirmed: false` are regenerated, and an unreadable reviewed file makes the command refuse (exit 1) without writing.

Run `baton onboard --interview`; stdout is one JSON report. Check its `central` and `repos` match what the human confirmed in step 0a. Exit 2 means a repo path or `profile/project.md` is missing: name it and stop. Exit 1 means a reviewed file is unreadable or `c4` failed: report the reason from stderr and do not hand-write what the command would have produced.

Print the stack table and, per repo, the edge and unresolved counts, then read the files back and confirm the row count matches the repo table. Never edit a generated file to change a value; the fix belongs in the build file, the config, or the answer table below. A value could not be detected if it says `unknown`, and it stays that way. The architect re-verifies `stack-detected.md` against the build files on every run and stops on drift. A human who rejects the output after seeing it can discard these files: nothing was committed.

Report `ran.c4.status`. `ok`: the workspace was generated; then run `baton diagram architecture` and show `docs/architecture/diagrams/diagrams.md` in step 5 (system context, containers with every collection / topic / file, components per repo, drawn from the code). That is what people read; the DSL is for tools and needs no preview. `not built yet`: say so plainly and, in step 5, propose `docs/architecture/workspace.dsl` from `templates/workspace.dsl` (or `skills/design-diagram/references/workspace-template.dsl` while that file does not exist), with the repos as containers and nothing else, marked as hand-seeded until `baton c4` can project it.

## 3. Review what extraction found (no scanning, no subagents)
The extractors replace the per-repo discovery of earlier versions. Show `profile/dependencies.yaml` grouped by repo, each edge with its `file:line` so a human can audit it; `warnings` from the report (nested projects not walked, uncommitted changes); which files parsed under which back-end (`parser` in `dependencies.yaml`). Show the seeded `aggregates.yaml` and `risk-zones.yaml`: both stay `confirmed: false` until the Tech Lead says otherwise.

Output of this step, shown in step 5 and written there = `docs/context/codebase-map.md`, one line per module/job/endpoint: path - purpose - reads - writes, grouped by repo. Reads, writes and paths are copied from `dependencies.yaml`; only the purpose words are yours, and a purpose you cannot support from the code is left blank. Path-check every claim. For every command the map will state, read the script or config that runs it. These lines are the seed: the wiki replaces them as what agents read, per step 5.

## 4. Interview the gaps
Note the documents and Confluence pages the humans named in step 2 for `/build-context-map`; do not read them here. Then ask the report's `questions`, in its `batches`: each has an `id`, the gap-table row (`gap`), the text (`ask`), where the answer belongs (`writesTo`), and any `seeds` or `values` from the code to show with it. They are exactly what extraction could not answer; do not add questions a report already answered, and do not answer one yourself. Then only what no scan reaches, in batches of at most eight questions, recall not review: what agents keep getting wrong here; what is off limits; why a constraint exists; runtime behaviour invisible from the repo (the nightly job's real runtime, which collections are refreshed when, what the test-environment data is missing). Never ask what a scan could answer. When the repo contradicts the human, show the evidence and ask.

## 5. Show, then write
Compose the agent-instructions block per `references/template.md` (Orientation, Policy, Where things are, Running and verifying, Conventions that differ from defaults, Known pitfalls) - terse imperative lines, a prohibition names the alternative, pitfalls only with observed evidence. For each candidate line ask whether a hook, lint rule or CI check enforces it better; propose that and keep the line as fallback.

Show the complete block AND the settled ledger before writing, with every other proposed write: each answer as a row under `## Onboard answers` in `profile/project.md` (`| question id | answer |`; a question with an answer there is not asked again, and the generated edge stays literal, because an answer names the system, it does not change what the code says), answers whose `writesTo` is `profile/domain.md`, and each aggregate or risk zone the Tech Lead confirmed, set to `confirmed: true` in place. Only the Tech Lead confirms those two files. On approval: write those, splice the block into `CLAUDE.md` between `<!-- agent-instructions -->` markers (replacing only what is between them), write `docs/context/codebase-map.md`, and add a provenance line with today's date and each repo's HEAD SHA. Never commit.

Then offer the wiki per the `wiki` skill: say that `baton wiki <repo>` (no `--prose`) writes the pages from the code alone, with no model call, and writes `docs/wiki/<repo>/<module>.md` and the index block in `docs/context/codebase-map.md`. On a yes, run it and `baton verify <repo>` for each repo, and show the result per repo. Agents rely only on a page with `verified: true`; report any failed page with its reasons rather than editing it. A repo whose `commit` is `unknown` cannot pass verify: say so.

## 5a. Compare with the nearest starter kit
For each repo, pick the nearest kit under the framework's `templates/kits/` (`spring-boot-mongo-service`, `spring-batch-job`, `react-ts-ui`) from `profile/stack-detected.md`. List what the repo lacks that the kit has: the sensors in the build (ArchUnit, PMD, Checkstyle, PIT, or ESLint and typecheck), the same-bar CI workflow, `CLAUDE.md` importing `AGENTS.md`, the hooks in `.claude/settings.json`, a runbook. Write the list as `docs/onboarding/<repo>-alignment.md`, each item with the kit file to copy and the build-file lines to add, for the Tech Lead to raise as one alignment PR in that repo. Never edit a service repo here.

## 6. Close
Say what went in, what was left out and why, and that `/onboard refresh` re-verifies against the recorded SHAs. Then say the next step is `/build-context-map`: it reads the documents, the domain, the code and the diagrams this skill generated, stops to ask what it cannot find, and a feature is accepted for story drafting only once the areas it changes are understood. Suggest `/onboard record` the moment an agent gets something wrong.

## record
Capture one observed agent mistake: task, mistake, correction, evidence. One occurrence is noted in docs/context/pitfalls-log.md; a recurring or costly one earns a line under Known pitfalls now, shown as a diff before writing. If mechanically preventable, propose the check instead.

## refresh / audit
Refresh starts with `baton onboard --refresh --interview`, after saying what it writes as in step 2a. Show its `refresh` section: `commits` that moved, `edgesAdded`, `edgesRemoved`, and the unified diff per generated file (the `generated:` line is ignored, so an empty section means nothing changed; say so). Confirmed aggregates and risk zones are kept; a new path outside a confirmed zone and a confirmed aggregate whose root is gone come back as questions. Ask only the questions that are new. Then:

Then say that `/build-context-map refresh` brings the documents, the drafts and the explorers' notes up to the new commits.

Re-verify every path and command against the repos since the recorded SHAs (`git log --diff-filter=DR --name-only <sha>..HEAD`); update or remove lines whose evidence is gone, each as a ledger entry shown before writing. A policy or pitfall goes only when the thing it guards is gone or a human retires it. Audit ends smaller or equal.
