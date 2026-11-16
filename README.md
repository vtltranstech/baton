# BATON - agentic delivery for Java / Spring / React / Mongo teams

BATON runs on a coding harness (Claude Code today); it is the SDLC layer above the runtime the harness-engineering literature describes. Its command is `baton` (formerly `pod`, and before that `harness`; both still work for one release).

One core, many projects. Everything here is project-agnostic; a project supplies a `profile/` folder (see `PROFILE.md`) and its own `docs/`.

**Status:** built and tested on fixtures (`fixtures/sample-central-repo`); not yet run on a real product. The data profiler (W3) is not built, so every written collection counts as unprofiled. What has not been proven: `docs/known-limitations.md`.

## How you use it
Three places, one rule: agents run only inside Claude Code; everything else is plain files and the `baton` command.

| Where | Who | What you do there |
| --- | --- | --- |
| The Claude Code panel in VS Code, opened on the central repo | everyone who starts work | type a slash command: `/stories F-003`, `/ready S-010`, `/build S-010`, `/sprint-review`, `/ship S-010`; answer the questions it asks at the gates |
| A terminal (VS Code's, or any other), no Claude session needed | anyone tracking work | `baton board` - every story, its State, gate 0, its branches in every repo, pushed or merged, and the next move; `baton build S-010 --status` - the steps one story has done; `baton deps`, `baton context check` |
| A browser | the PO, the Tech Lead, a demo audience | `baton trace F-003 --open` - one page per feature: every step from feature note to merged PR, who produced it, who decided |

The CLI never starts an agent and never needs the network. When the board says what is next, you type it in the Claude Code panel. There is no web UI yet; `baton board --json` is the data it will read.

Start here: [docs/quickstart.md](docs/quickstart.md) (install, then daily use). The full guide: [docs/guide.md](docs/guide.md). Try it without a model on the fixture: [docs/enablement/first-story.md](docs/enablement/first-story.md).

## Mandatory in every design and review
- The architect writes every design as a delta on the project's C4 model (`docs/architecture/workspace.dsl`, Structurizr DSL) with a per-story dynamic view; the documentation agent promotes it after gate 3.
- ArchUnit runs in every Java repo; no story reaches `In Review` without a green `archunit.txt`; QA and the craft lens fail on its absence.
- Gates: the context map accepts the area (0); PO sets Ready (1); Senior Engineer reads first and the Tech Lead decides (2 and 3). Hooks enforce states, branch and environment protection.
- Security reviews last: a commit after its report makes it stale, and Approved is refused until it is run again.

## What is in the core
- `agents/` - story-drafter, architect, developer, qa, security, documentation, release, and the two that learn the system before any of them: context-explorer and context-integrator. Each opens with a blueprint (trigger, input, output, handoff, outcome); `baton agents check` lints them
- `skills/` - workflow skills (`/onboard /build-context-map /deliver /stories /ready /build /sprint /sprint-review /ship /standup /retro /agent-regression`), role skills (story-writing, design-diagram, data-check, security-checklist, change-note), review skills (design-review-lenses, review-lenses with 5 lenses, elicitation), the `standards` guardrails (common Java/React rules, pattern ledger, sensors), and the `workflow`, `triage`, `jira` references
- `hooks/`, `sensors/` - the mechanical gates and the build checks
- `tools/baton/` - the `baton` command (stdlib Python): extractors, code IR, diagrams, context map, confidence, evidence, board, build order, trace
- `templates/` - `CLAUDE.md`, `profile/`, the central repo CI, and starter kits for new service repos (`templates/kits/`)
- `contracts/` - the formats and rules every file and command follows; `docs/` - the guides and the enablement pack
- `NOTICE.md` - MIT attributions

## How a project uses it
Option A (today): `baton install --from <this checkout> --central <central repo>` copies `agents/`, `skills/`, `hooks/`, `sensors/` and `tools/baton/` under `.claude/` (quickstart). Needs no plugin; add `--no-mcp` when only listed MCP servers are allowed.
Option B (where plugins are allowed): add this repo as a marketplace and install `baton`; the project repo then needs only `CLAUDE.md`, `profile/`, `docs/`.
Either way, open the project's central repo in VS Code and start Claude Code there: every path the core uses (`profile/...`, `docs/...`, `../<repo>`) is relative to that folder.

## Versioning and ownership (the part that keeps "common" common)
- One owner. Changes to the core go through a PR here, never by editing a project's copy.
- Semantic version in `.claude-plugin/plugin.json`; projects record the version they run in `profile/project.md` (`core.version`).
- Before a core release: `/agent-regression all` against every project's `docs/golden/`, and `baton agents check`. A regression in any project blocks the release.
- A project that needs a core change proposes it via `/standards record` output or a PR; project-only needs go in the profile (invariants, sensor extras, severity hints), never in the core.
- Upgrade = `baton install` again; nothing under `profile/` or `docs/` is touched.

## Java version policy
The core is written for "the pinned version" and reads it from `profile/stack-detected.md`. Moving a project to Java 21 is a build-file change plus a re-run of `/onboard`; no core change.
