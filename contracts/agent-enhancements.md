# Agent enhancements, orchestration and systems of record

Scope: Claude Code only (the VS Code extension; no headless `claude -p`). The context map (`contracts/context-map.md`) stays as specified, gate 0 included; this contract names where the agents call it. Everything here extends the existing agents and skills.

## 1. Agent blueprint - every `agents/*.md`
A fixed block right after the frontmatter, linted by `baton agents check` (section 13):

```
## Blueprint
- Trigger: /build, story State Ready or Design Changes Requested, gate 0 passed for the story's track
- Input: docs/stories/<F>/<S>.md; docs/design/<F>/<S>-context.md (the manifest); profile/stack-detected.md
- Action: the design note as a delta on the architecture of record; challenge round first; pattern ledger
- Output: docs/design/<F>/<S>-design.md; docs/design/<F>/<S>.dsl; provenance footer
- Handoff: gate 2 - the Senior Engineer reads, the Tech Lead decides
- Outcome: A design inside the architecture
- Never: edit docs/architecture/workspace.dsl; change an AC (hooks: protect_weights, state_gate)
```

- **Fields:** each once. Input items are separated by `;`, each a path or `manifest: <how it is produced>`; never "the codebase".
- **Handoff:** a gate (`gate 0` to `gate 3`) or a skill that exists (`/build qa`).
- **Outcome:** a row of the outcome table in `docs/roles.md` (section 2).
- **Never:** ends with `(hooks: a, b)`, each a file in `hooks/`.

| Agent | Trigger | Handoff |
| --- | --- | --- |
| story-drafter | `/stories <F or Jira key>` after the feature check | `/ready` on every Draft |
| architect | `/build`, Ready, gate 0 passed | gate 2 |
| developer | gate 2 approved or auto-passed; a QA Fail loop (at most 2); a security BLOCKED | `/build qa` |
| qa | developer done, sensors green | `/build security` |
| security | QA Pass, and again after any code change that follows its report (section 4) | `/build confidence`, then gate 3 |
| documentation | gate 3 Approved | `/ship release` |
| release | Documented, trace regenerated | `/ship`: the Tech Lead merges, then `baton tag` |
| context-explorer | `/build-context-map`, one per area | `/build-context-map integrator` |
| context-integrator | `/build-context-map`, after each round | `/build-context-map grader` (gate 0) |

## 2. Outcome table - `docs/roles.md`
One row per outcome: what the AI does, what a human does, what a human decides. Rows: Understood system (gate 0), Clear aligned stories (gate 1), A design inside the architecture (gate 2), Working conforming code, Verified change, Accepted change (gate 3), Shipped and recorded, Rules that improve.

## 3. Orchestration in the CLI: `baton build <S>`
Claude Code runs the agents (only it can); `baton build` owns the order. The `/build` skill loops: `baton build S --json`, do the printed action, report back.

| Action kind | Who does it | Reported back with |
| --- | --- | --- |
| `agent` | the skill runs the named agent with exactly the listed inputs | `baton build S --done <step>` |
| `skill` | the skill runs `/ready` or `/build-context-map focus <F>` | `baton build S` again |
| `gate` | the skill asks the gate 2 question with AskUserQuestion | `baton build S --answer approve\|changes\|block --by TL --note "..."` |
| `do` | the skill does the named step of the `/build` skill (the checks after the developer) | `--done checks` |
| `done` | nothing: QA Pass, security current, evidence written; gate 3 is `/sprint-review`'s | - |
| `stop` (exit 2) | a human: blocked, waiting on a dependency, a third failed loop, a refused `--done` | - |

Steps, by State:

| State | Steps |
| --- | --- |
| Draft, Needs Clarification, Ready for PO | `skill`: /ready (gate 1) |
| Ready, Design Changes Requested | gate 0 (`baton context check S --track T`; refused: `skill` /build-context-map focus F, or the recorded override), `baton deps S`; a `ui` story: `agent` architect step wireframe, `baton ux check`, `do` ux-lens, `gate` gate2a (contracts/ui-stories.md); then `agent` architect |
| Designed | full track: a pattern-ledger Verification cell naming no test or ArchUnit rule sends the design back (State Design Changes Requested, by `baton`); light track at or above `track.auto-pass.confidence` with no mandatory label, or `hotfix`: auto-pass, never for a `ui` story (one question for the PO and the Tech Lead); else `gate` |
| Design Approved | `agent` developer |
| In Review | `do` checks (diff shape, impact, mutation, as-built, risk) once per set of branch heads, then `agent` qa |
| QA Fail | `agent` developer with the triage file as the only review input (section 5); after 2 loops, `stop` for the Senior Engineer |
| QA Pass | `agent` security unless its report is current (section 4), then `baton confidence`, `baton evidence`, `baton trace` once per set of heads, then `done` |
| Blocked | after a security BLOCKED within 2 loops: `agent` developer with the security report; else `stop` |

- **Ledger:** `docs/qa/<F>/<S>-build.json`, one entry per step: step, time, who (`baton`, `agent`, the deciding human), the code branch heads it saw, and the gate answer, note or override. A step is current while it is recorded with the same heads; `--from <step>` forgets it and every later step.
- **`--done` checks the step's outputs:** architect - the design note exists and the State is Designed; developer - In Review, and on a fix loop no lens file in its provenance footer; checks - `-diff-shape.json` and `-risk.json`; qa - the test report and QA Pass or QA Fail; security - the report exists and is current.
- **Gate 0 off for the product:** a row `| gate0 | off: <reason> (TL, YYYY-MM-DD) |` in `profile/project.md`, written by the Tech Lead in their own editor (the hook refuses an agent edit that adds, changes or removes it), for when the context map cannot be built or trusted. `baton context check` then accepts every story and feature with that reason and checks nothing; the state check, `baton build` (recorded once in the ledger, `scope: product`) and `/stories` go on; `baton board` shows `off`. Remove the row to switch gate 0 back on.
- **Gate 0 override:** a story header line `Gate-0-Override: <reason> (TL, YYYY-MM-DD)`, written by the Tech Lead in their own editor; the state-gate hook refuses an agent edit that adds, changes or removes it. `baton build` and the state check accept a refused gate 0 with it and record the reason; `baton board` shows `override`.
- **Not yet in the CLI:** `/stories`, `/ready`, `/ship`, `/sprint-review`, `/standup` and `/retro` still order their own steps in the skill text; each moves to a subcommand the same way.

## 4. Security runs last
Any code change after the security report invalidates it.
- The report carries `Heads: <repo>@<sha>, ...`, read at review time from every repo it reviewed.
- `baton build` runs security again when a `feature/<F>-<S>` head differs from the report.
- The state-gate hook refuses Approved while it differs, or while the report has no `Heads:` line and a code branch exists (`contracts/states.md`).
- The release agent runs `baton build S --security-check` (exit 2 when the report is missing, BLOCKED or stale, or `confidence.json` is missing) and opens no PR until it passes.

## 5. One consolidated fix
A fix loop's only review input is `docs/qa/<F>/<S>-triage.md`, never the lens files or the raw sensor reports. `baton build` passes only that path; the developer agent says so; `--done developer` refuses a loop whose provenance footer lists a `-lens-*.md` file.

## 6. Same quality bar
Agent branches run exactly the human pipeline (`skills/standards/stack.md`): no agent lane, no skipped stage. The central repo's CI (`templates/ci/central-ci.yml`) runs `baton state-check` on every changed story, `baton confidence` and `baton evidence` on story branches, and posts evidence.md as the PR description. Branch protection on the default branch of every repo, the central one included.

## 7. Ticket as input
`/stories` takes `F-002` or a Jira key. With a Jira tool from an allowed connector, the issue text goes into `docs/features/F-xxx.md` with a `jira: <KEY>` header; without one, the PO pastes it and the key is still recorded. State mirrors one way, Git to Jira, gate decisions as comments naming the deciding human (`skills/jira`). The webhook stays deferred.

## 8. Systems of record

| Kind | Source of record | Published copy | Never |
| --- | --- | --- | --- |
| Intent and state (features, stories, decisions, who decided) | Jira for intent; Git for State | the story header carries the key; Git to Jira mirror | ACs or rules authored in Jira as final |
| Evidence and machine-read context (profile, architecture of record, context map, stories, designs, reports, confidence, evidence, change notes, metrics) | Git, the central repo | evidence.md on the PR and as a Jira comment | raw tool output, real data |
| Knowledge for people (architecture page, readiness, what we know, wiki, trace, change notes) | generated from Git | Confluence, one page per artefact type, overwritten by the documentation agent when a connector is present | hand edits that agents would read |
| Raw reports (PMD and Checkstyle XML, surefire, PIT HTML) | the CI artifact store | JSON or text summaries in Git | committed whole |

- **Repo hygiene:** `baton install` adds `.baton/`, `target/`, `node_modules/`, `pit-reports/`, `surefire-reports/` to `.gitignore`.
- **Commit scope:** the `commit-scope` hook refuses files outside the allowed folders.
- **Archive:** `/ship` of a feature's last story archives it (`contracts/versioning.md` section 5).
- **Agents read Git only:** a Confluence export is a `doc-source` for the context map, cited as a document, never as a confirmed rule.
- **Trace page:** `docs/trace/<F>.html` is still committed; it moves out once a publisher exists.

## 9. Per-agent changes
- **story-drafter:** ACs cite the rule id that governs them; EARS for non-behavioural ACs; every answered clarification is one line in `profile/domain-drafts.md`; a Jira key input.
- **architect:** reads the manifest first and only the rules it names, by id; the pattern ledger's Verification cell names a test or an ArchUnit rule.
- **developer:** the triage file is a fix loop's only review input; `Heads:` in the Dev summary.
- **qa:** expectations from the manifest's confirmed rules; an `SE: agree | disagree` cell per carried lens finding (`/retro` computes lens precision); an unprofiled collection in an AC is a FAIL, reason `unprofiled`.
- **security:** the `Heads:` line; runs again after any later commit; one severity level higher inside a risk zone.
- **documentation:** publishes the people pages to Confluence when a connector is present (step 5c); lists the areas gone stale (step 5b).
- **release:** refuses on a stale security report or a missing confidence.json; posts evidence.md to Jira.

## 10. Starter kits - `templates/kits/`
`spring-boot-mongo-service`, `spring-batch-job`, `react-ts-ui`: skeletons with the sensors in the build, the Claude Code files (`.claude/settings.json` hooks, `CLAUDE.md` importing `AGENTS.md`), the same-bar CI, a runbook stub and a README that says what `/onboard` will ask. Dependencies resolve through the org's mirrors only. `/onboard` compares an existing repo with the nearest kit and writes `docs/onboarding/<repo>-alignment.md` for the Tech Lead (step 5a).

## 11. Enablement pack - `docs/enablement/`
`first-story.md` (a walkthrough on the fixture product, every command and file), `demo-script.md` (file by file, feature to trace), `faq.md` (seeded from the questions the context map asks), `baseline.md` (the current-state map, done once before the product's next story).

## 12. Baseline before claims
One working day with the team: every step from feature idea to production, who touches it, how long it works and waits, into the `## Baseline` table of `docs/metrics.md` (`skills/doc-style`). Every later figure is reported beside it as waiting removed.

## 13. `baton agents check`
Exit 1 with one line per problem:
- a blueprint field missing, repeated or unknown;
- an Input that is not a path or a manifest;
- a Handoff that is not a gate or an existing skill;
- an Outcome that is not a row of `docs/roles.md`;
- a `Never` without its hooks, or naming a hook that does not exist;
- an agent without the provenance footer rule (the context agents carry their note header instead);
- a chained skill marked `disable-model-invocation`, or a skill that declares no activation (the flag, `paths`, an agent's `skills:` list, or a stay-invocable row in `contracts/models-and-activation.md`);
- the developer without the triage-only fix-loop rule.

Project words stay out of the repo: one regex per line in a git-ignored `tools/baton/tests/project-words.local.txt` (or the file named by `BATON_PROJECT_WORDS`), read by `tools/baton/tests/project_words.py`; the word tests skip without it.

## 14. Differences from the source guide
- **No headless runs:** `baton build` cannot start an agent itself, so the skill does and reports back.
- **Gate 0 stays gate 0:** `baton context check` is the guide's `learn status`; a refused gate leaves the State as it is, with no new `Blocked - context` state. The manifest comes from the check, not from a separate `propose`.
- **The checks stay a skill step:** the guide's `sensors` and `diff-shape` commands are the `/build` skill's checks after the developer.
- **Mechanical checks:** the pattern-ledger and lens-input checks run in `baton build`, where the artefacts are, not in `baton agents check`.
