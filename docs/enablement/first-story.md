# Your first story in 30 minutes

On the fixture product `fixtures/sample-central-repo` (invoices, one service). Work on a copy so the repo stays clean. No model call is needed until step 4.

| Step | Run | Open | What you learn |
| --- | --- | --- | --- |
| 1. Copy | `cp -R fixtures/sample-central-repo /tmp/central` | `/tmp/central/profile/project.md` | the profile: repo table, test environment, thresholds |
| 2. Where things are | `baton board --central /tmp/central` | `docs/stories/F-100/FIX-1.md` | every story: State, gate 0, branches, next move |
| 3. The order | `baton build FIX-1 --central /tmp/central` | the printed action | `baton build` owns the order; the first action is the architect |
| 4. The real thing | in Claude Code, from `/tmp/central`: `/build FIX-1` | `docs/design/F-100/FIX-1-design.md` | the skill loops on `baton build`: agent, `--done`, next |
| 5. Gate 2 | answer the design question, or see the light-track auto-pass line | the story's `## Design review` | who decided is recorded, with the confidence |
| 6. Sensors | after the developer: `docs/qa/F-100/FIX-1-sensors/archunit.txt` | the story's `## Dev summary` and `Heads:` | ArchUnit is mandatory; In Review is refused without it |
| 7. Review | `docs/qa/F-100/FIX-1-triage.md` | the lens files beside it | a fix loop reads the triage file only |
| 8. Security last | `baton build FIX-1 --security-check` | `docs/qa/F-100/FIX-1-security-report.md` | a commit after the report makes it stale |
| 9. Evidence | `baton confidence FIX-1`, `baton evidence FIX-1` | `FIX-1-evidence.md` | the score is information; gate 3 is the Tech Lead's |
| 10. The record | `baton build FIX-1 --status`; `baton trace F-100 --open` | `docs/qa/F-100/FIX-1-build.json` | every step, who did it, and the code heads it saw |

Every command takes `--central <path>` (default: the current folder) and `--json`.
