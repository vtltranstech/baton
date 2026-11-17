# States and prerequisites (enforced by `baton state-check` and the state-gate hook)

Order: Draft -> Needs Clarification | Ready for PO -> Ready -> Designed -> Design Approved | Design Changes Requested | Blocked -> In Review -> QA Pass | QA Fail -> Approved -> Documented -> Done

Story file: `docs/stories/<F>/<S>.md` or `docs/stories/backlog/<S>.md` (then `<F>` = `backlog` in every artefact path below).

Every story carries one header line, `Depends-On: S-101, S-102` or `Depends-On: none` (story ids only; fixtures and outside teams stay in `## Dependencies`). Every state below except the always-allowed row needs that line, every listed story must exist, and the list must not make a loop. **Designed and every later state also need every listed story to be `Done`.** Once a story has reached Ready, the hook refuses an agent edit that removes an id from the line; a human changes it in their own editor.

| New state | Prerequisite artefacts (all must hold) |
| --- | --- |
| Ready for PO | story has `## Readiness`; gate 0 (context-map.md section 10.5; a header line `Gate-0-Override: <reason> (TL, YYYY-MM-DD)` accepts a refused gate 0, and only a human writes it): once `profile/branch-points.yaml` exists, `docs/design/<F>/<S>-context.json` exists, lists no blocking gap, and every changed area it recorded still passes for the track in `docs/context/understanding/status.json` |
| Ready | human-only (gate 1): `## Readiness` present, no blocking context gap (as Ready for PO); the hook cannot tell human from agent - the `/ready` skill is the only path that sets it, after an AskUserQuestion answer |
| Designed | gate 0 as for Ready for PO (none while `profile/project.md` has `| gate0 | off: <reason> (TL, date) |`); `docs/design/<F>/<S>-design.md` (or `-findings.md` for spike) exists; full track: `docs/design/<F>/<S>.dsl` exists; a `ui` story: `<S>-wireframe/screen-spec.md`, and `approved.html` with a `## Wireframe approval` line saying approved (full) or the delta `option-1.html` (light) (`contracts/ui-stories.md`) |
| Design Approved | story `## Design review` contains `Approved` or `auto-passed` |
| In Review | `docs/qa/<F>/<S>-sensors/archunit.txt` exists, contains `Tests run:` and `Failures: 0, Errors: 0`; at least one of `pmd.xml` / `checkstyle.xml` / `eslint.json` exists; story has `## Dev summary` and `## Rule ledger` |
| QA Pass | `docs/qa/<F>/<S>-test-report.md` contains `## Verdict: PASS` |
| QA Fail | the test report exists |
| Approved | QA Pass holds; `docs/qa/<F>/<S>-security-report.md` exists and does not contain `Verdict: BLOCKED`; security is current (agent-enhancements.md section 4): once a `feature/<F>-<S>` branch exists in a repo of the repo table, the report's `Heads: <repo>@<sha>, ...` line names each branch head; `docs/qa/<F>/<S>-confidence.json` exists; test report's `## Human findings` has a non-placeholder line |
| Documented | `docs/changes/<F>/<S>-change-note.md` exists; full track: `docs/architecture/workspace.dsl` mtime >= the design note's |
| Done | story contains a `PR:` line with a URL |
| Blocked / Needs Clarification / Design Changes Requested | always allowed (they only move backwards) |

**Order.** A story moves only to its next state: Draft or Needs Clarification -> Ready for PO -> Ready -> Designed -> Design Approved -> In Review -> QA Pass or QA Fail; QA Pass -> Approved -> Documented -> Done; QA Fail -> In Review; Design Changes Requested -> Designed. A spike may go from Design Approved to Documented. A Blocked story resumes at Ready for PO, Ready, Designed, Design Approved or In Review, and In Review also needs an approved `## Design review`. Blocked, Needs Clarification, Design Changes Requested and Draft can be entered from any state. A new story file counts as coming from Draft. The prerequisites still apply to every move.

`state-check` prints the first missing prerequisite on stderr and exits 2; the hook relays that message to the agent, which must produce the artefact, not retry the state.
