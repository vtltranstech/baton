---
name: workflow
description: The BATON workflow - principles, roles, three human gates, agent sequence, states, hooks, confidence, ceremonies. Every agent reads this first. Use as /workflow to print it.
---
# The BATON workflow

Read this file before running any agent. This is the COMMON core; everything project-specific is read from the project's `profile/` folder: `project.md` (non-derivable values, repos, domain words, personas), `domain.md` (business rules, open decisions, invariants, severity hints, security specifics, data-check patterns), `stack-detected.md` (extracted from the build files by `baton extract-stack` during /onboard and re-verified by the architect every run), `risk-zones.yaml` (paths where confidence is capped), `confidence-weights.yaml` (owned by the Senior Engineer; agents never read it). The project's C4 model is `docs/architecture/workspace.dsl`. No agent may run `/build` if `project.md`, `domain.md`, `stack-detected.md` or `workspace.dsl` is missing.

## Principles (what every agent and skill is built on)
1. **One install, one profile.** A team installs baton, runs `/onboard`, answers only what extraction could not, and is live.
2. **The LLM never decides structure.** Stack facts, collections, endpoints, edges, risk zones and confidence weights come from code, config or a human. The model names, explains, proposes and implements.
3. **Gates are enforcement, not instructions.** What an agent must not do is a hook or a permission rule (`hooks/`). CLAUDE.md and skills are guidance; hooks are law.
4. **Every artefact is a file in Git.** Stories, designs, change specs and their generated diagrams, reports, sensor output, triage, confidence.json, evidence.md. Nothing lives only in chat.
5. **Evidence, not trust.** The gate-3 confidence score is computed from artefacts by `baton confidence`; no agent self-reports it; a human owns the weights and recalibrates from outcomes.
6. **Common framework, per-project profile.** Agents, skills, hooks, sensors, templates and tools are common. A project contributes `profile/` and its `docs/`.
7. **Grow only from observed failures.** No rule, lens, sensor or threshold is added speculatively; `/standards record` turns an incident into a rule.

## The team
Humans (3) and what each owns:
| Role | Owns | At the gates |
| --- | --- | --- |
| Product Owner | **Intent**: feature notes, story quality, glossary (domain words), invariants in business terms, clarification answers | Gate 1 - sets `Ready`; approves additions to `profile/domain.md` rules |
| Tech Lead | **Feed-forward**: `profile/domain.md`, risk zones, the C4 model's intent, ArchUnit rules as architecture, design option choices, which skills the project uses | Gate 2 - decides Approve / Changes / Block; Gate 3 - decides `Approved` for scores < 60 and for every track-full story; merges |
| Senior Engineer | **Feedback**: sensors, verifier rules, fixtures, golden set, `confidence-weights.yaml`, escalations; turns every escaped defect into a rule via `/standards record` | Gate 2 - first reader, writes findings before the TL decides; Gate 3 - first reader of the diff + reports, reviews scores 60-84 and recommends; runs `/agent-regression` and the monthly calibration |

Agents (7): story-drafter (supports the PO), architect, developer, qa, security, documentation, release. Agents draft, design, build, test and report. No agent approves its own work and no agent passes a gate; the state-gate hook refuses a state an artefact does not justify.

## Triage
Every story's Jira-Type and Labels derive its Track (light | full | spike) per the triage skill. The track decides how heavy the design note is, whether gate 2 asks or auto-passes, and which human lane gate 3 uses.

## Skills
Workflow skills (/onboard, /deliver, /stories, /ready, /build, /sprint, /ship, /standup, /sprint-review, /retro, /agent-regression) chain the agents. Role skills (story-writing, design-diagram, data-check, security-checklist, change-note) tell each agent how to do its job well. Review skills (design-review-lenses, review-lenses, elicitation) give every artefact a fresh-context second reader before a human sees it. The `standards` skill is guardrails only: `stack.md`, `patterns.md`, `sensors/`. Tools (`tools/baton`, stdlib Python, one CLI) do the deterministic work: `extract-stack`, `state-check`, `impact`, `mutation`, `confidence`, `evidence`. Several skills are adapted from BMAD-METHOD under MIT - see NOTICE.md.

## Where stories come from
Two sources, one gate. (a) /stories drafts them from a feature note - after a FEATURE-CHECK that asks the human for anything the note lacks (max 3 rounds). (b) Humans write stories themselves - under a feature folder or ad hoc under docs/stories/backlog/ - from the template. Every story passes /ready (Definition of Ready, clarification loop, max 3 rounds), then the PO sets Ready.

Attachments (a spreadsheet, a mapping, expected results): `docs/stories/<F-xxx>/<S-yyy>/attachments/` for one story, `docs/features/<F-xxx>/attachments/` when shared. The story names each under `Inputs:` with the sheet / rows that matter. Agents read only the text copy (`.csv` / `.md`) that /ready places beside the original; a human-supplied expected-results sheet becomes the QA fixture for the data-check "spot-check vs fixture".

## Sequence
1. story-drafter   : docs/features/F-xxx.md        -> docs/stories/F-xxx/S-yyy.md with estimate + risks; State = Draft   (or a human writes the story)
1a. /ready         : any Draft story                -> Definition of Ready, clarification questions, State = Ready for PO | Needs Clarification | Blocked
2. HUMAN GATE 1    : Product Owner sets State = Ready
3. architect       : one Ready story                -> docs/design/F-xxx/S-yyy-design.md - light or full note per Track; full = challenge round, flow-with-impacts, **change spec -> `baton diagram story` draws flow-with-impacts, sequences, LLD, data model, use cases from the AST**, low-level class diagram, pattern ledger, sequence, data model, tasks, design confidence grounded by design-review-lenses. State = Designed
3a. HUMAN GATE 2   : Senior Engineer reads first (findings under `## Design review`); Tech Lead decides. Light + confidence >= threshold or hotfix: auto-pass (recorded). Otherwise /build asks Approve | Request changes | Block (max 2 rounds). Mandatory-ask labels: new-api, data-model, batch-job + the profile's extras. State = Design Approved | Design Changes Requested | Blocked
4. developer       : one Design Approved story      -> branch feature/F-xxx-S-yyy in each repo the design lists; code + unit tests; **sensors green including ArchUnit** (reports saved under docs/qa/F-xxx/S-yyy-sensors/). State = In Review (the hook refuses it without the reports)
4a. /build         : diff-shape sensors, impact, mutation, risk tier (`baton risk`: how many review lenses QA runs) -> docs/qa/F-xxx/S-yyy-diff-shape.md + -diff-shape.json + -impact.json + -mutation.json (`not run` recorded when a tool is absent)
5. qa              : the branch                     -> docs/qa/F-xxx/S-yyy-test-report.md (ACs + data checks + 5 lenses + triage). ArchUnit missing or red = FAIL. State = QA Pass | QA Fail
6. security        : the branch                     -> docs/qa/F-xxx/S-yyy-security-report.md
   - QA Fail or Security Blocked -> developer with the reports (max 2 loops, then the Senior Engineer)
6a. /build         : `baton confidence` + `baton evidence` -> docs/qa/F-xxx/S-yyy-confidence.json + S-yyy-evidence.md (computed; the model never sees the weights)
7. HUMAN GATE 3    : per the confidence policy - >= 85 no caps: Senior Engineer reviews evidence.md, Tech Lead approves on it; 60-84: Senior Engineer reads diff + reports, recommends, Tech Lead approves; < 60 or any cap: Tech Lead reads the diff, may send the design back. `## Human findings` goes into the test report. State = Approved (TL)
8. documentation   : Approved story                 -> change note; codebase map; **regenerates workspace.dsl (`baton c4`) and the architecture diagrams (`baton diagram architecture`) from the merged code**; ADR if a decision settled. State = Documented
9. release         : Documented story               -> opens PR linking every artefact incl. evidence.md and confidence.json. State = Done; a human merges.

## Hooks (law, not guidance - `hooks/hooks.json`)
- `protect_main.py` (PreToolUse Bash): no commit on main, master or the repo's default branch (`origin/HEAD`), no push to them, no merge, no force-push, no branch or tag deletion.
- `protect_env.py` (PreToolUse Bash): any datastore URI literal, or an env var other than the one `profile/project.md` names, is refused. Only the named test environment is reachable from an agent, read-only.
- `commit_scope.py` (PreToolUse Bash): in the central repo, on a `story/<F>-<S>` branch, a commit that would hold another story's or another feature's files is refused. Shared files always pass: `docs/status.md`, `docs/metrics.md`, `docs/architecture/*`, `profile/domain.md`, `profile/sensors/README.md`.
- `state_gate.py` (PreToolUse Write|Edit|MultiEdit|Bash on a story file): a State transition is refused unless its prerequisite artefacts exist - see `baton state-check` for the table (Design Approved needs `## Design review`; In Review needs sensors incl. ArchUnit; QA Pass needs a test report with Verdict: PASS; Approved needs QA Pass + security report + confidence.json + `## Human findings`). Change a story with Write or Edit; a Bash write to a story is refused. When refused, produce the artefact; do not retry the state.
- `protect_weights.py` (PreToolUse Read|Grep|Glob|Bash|Write|Edit|MultiEdit|NotebookEdit): `profile/confidence-weights.yaml` is refused, directly or through a glob or a recursive search. Search a narrower path (`docs/`, `../<repo>`) or filter by file type instead of searching the whole central repo.

## Calling the CLI
`baton <cmd>` in any skill means the `baton` command, run from the central repo, without `--central`. Never work on anything under a `fixtures/` folder: those are the framework's samples. Each person installs it once with `pipx`, as the framework quickstart says.

## Rules for every agent
- Read profile/domain.md before anything else. For code, start from `baton ir show` (one line per unit) and the story's context pack `.baton/context/<story-id>.md` (`baton ir slice <story-id> --write`), not from the whole `docs/context/codebase-map.md`; grep the map only for one module's row.
- Read the repo table in profile/project.md to know which sibling repos exist and what they are.
- Work on exactly one story at a time. Never touch files outside the story's scope.
- Run every subagent in the foreground and wait for its report; never with run_in_background. A background report comes back as an injected message, and organisation prompt hooks may refuse it. The project's settings set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` for the same reason.
- If a requirement is ambiguous, STOP and write questions into the story under "## Open questions". Do not guess.
- Never change a story's acceptance criteria; only the story-drafter agent or a human may.
- Every output is a markdown file under docs/; nothing lives only in chat.
- Never read `docs/archive/`: finished features moved there by `/ship <feature-id>`. Only `/retro` and `baton trace` read it.
- Keep docs/status.md current whenever you change a story's State, including the date columns, in the `doc-style` format.
- Every Markdown file you write under docs/ follows the `doc-style` skill: ASCII only, tables for facts, bullets under 20 words, no narrative. The doc-lint hook checks it after each write.
- Never read `profile/confidence-weights.yaml`. Never run anything against a non-test-environment database. Never merge. Never deploy.
- End every Markdown artefact you write under docs/ with your provenance footer (below). `baton trace` reads it.
- **Models:** a skill that launches an agent or a lens subagent passes it the model `baton models <story-id>` prints for that role (the `model` parameter of the Agent call); agents keep `model: inherit`. A reviewer is never a weaker model than what it reviews, and differs from it whenever that allows (`profile/models.yaml`, owned by the Tech Lead; contracts/models-and-activation.md section 3).

## Provenance footer
An HTML comment at the end of the file, so it never renders. One footer per agent per file: when you edit a file that already has your footer, replace it; leave other agents' footers alone.
```
<!-- baton:provenance
agent: architect
skills: design-diagram, standards, design-review-lenses
profile: domain.md#rules-touched(R3,R7), project.md#repos, stack-detected.md
context: <each wiki page you cited>@<its commit>
graph: impact.json (2 repos, 0 unknown edges)
model: strong (opus)
commit: <service repo HEAD you read or wrote>
started: 2026-11-04T09:12:00Z  finished: 2026-11-04T09:31:00Z
tokens: 41200
-->
```
- **Keys:** fixed; omit a key you have no value for. Lists are comma-separated.
- **profile / context:** only the sections and wiki pages you actually read, so a reviewer sees what the work rested on.
- **started / finished:** UTC, from `date -u +%Y-%m-%dT%H:%M:%SZ` at the start and end of your work; never guessed. An agent without Bash omits both.
- **tokens:** only when the session reports it; never estimate.
- **model:** the alias and the model you were launched with, from `baton models <story-id>`.

## Central repo: story branch and commit points (contracts/versioning.md)
- **Default branch:** each repo's own, never assumed to be `main`: `git symbolic-ref --short refs/remotes/origin/HEAD` without the `origin/` prefix (if it is not set, `git remote set-head origin --auto` once; a repo with no remote uses `main`). `<default>` below and in every skill means that branch. Every PR, central or code, targets it.
- **Story branch:** `story/<feature-id>-<story-id>` (`story/backlog-<story-id>` for a backlog story). The first skill that writes for a story (`/stories`, else `/ready`) creates it from the default branch: `git switch -c story/<F>-<S> <default>`; if it exists, `git switch story/<F>-<S>`. Every later step for that story runs with its branch checked out. Agents never commit to the default branch (`protect_main`).
- **A commit:** `git add` the files the step wrote plus the shared files it changed, never `git add -A`; then `git commit -m "<message>"`. The `commit_scope` hook refuses another story's files. Never amend, squash or rebase: the branch history is the audit trail.
- **Messages are fixed,** so the trace and the changelog can parse them:

| Point | By | Message |
| --- | --- | --- |
| stories drafted | `/stories` | `<S>: stories drafted (story-drafter)` |
| story written by a human | `/ready`, first time it sees the story | `<S>: story added (human)` |
| readiness result | `/ready` | `<S>: readiness n/9` |
| gate 1 | `/ready` after the PO's answer | `<S>: Ready (PO)` |
| design written | `/build` | `<S>: design (architect, <confidence>%)` or `<S>: findings (spike)` |
| design lenses | `/build` | `<S>: design lenses (<n> blocking)` |
| gate 2 | `/build` after the decision | `<S>: design approved (TL)` / `<S>: design changes requested (TL, round n)` / `<S>: auto-passed (light, <confidence>%)` / `<S>: blocked (TL)` |
| build done | `/build` | `<S>: build (developer) - sensors <green or red>` |
| diff shape + impact + mutation | `/build` | `<S>: diff shape, impact, mutation` |
| QA | `/build` | `<S>: QA PASS` / `<S>: QA FAIL loop n` |
| security | `/build` | `<S>: security <verdict>` |
| confidence + evidence | `/build` | `<S>: confidence <score> <lane>` |
| gate 3 | `/sprint-review` after the decision | `<S>: Approved (TL)` |
| documentation | `/ship` | `<S>: change note; promote architecture (+a elements, +r relationships, ~c changed)` |
| release | `/ship` | `<S>: trace regenerated; PR <url>` |
| archive | `/ship <F>` on `archive/<F>` | `<F>: archived (<n> stories)` |

- **Service repos:** unchanged; branch `feature/<F>-<S>` per repo, one commit per task (`<S>: <task>`).

## States
Draft | Needs Clarification -> Ready for PO -> Ready -> Designed -> Design Approved | Design Changes Requested | Blocked -> In Review -> QA Pass | QA Fail -> Approved -> Documented -> Done

## Ceremonies (what each one reads)
- Sprint Planning     : docs/stories/*/ (estimates, risks) + docs/status.md
- Daily Standup       : /standup - docs/status.md + every story's "## Open questions"
- Backlog Refinement  : stories in Draft / Needs Clarification
- Sprint Review       : /sprint-review - evidence.md + confidence.json per story, ordered by lane
- Retrospective       : /retro (evidence -> aggregate -> acceptance -> discussion -> retro doc with owned action items) -> /agent-regression before the next sprint
- Monthly calibration : Senior Engineer joins confidence.json with outcomes (revert <= 30 days, linked defect, hotfix on the same files) and adjusts `confidence-weights.yaml`
