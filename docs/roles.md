# Roles

## Outcomes
One row per outcome the team delivers. Every agent's `## Blueprint` names its row under `Outcome:`, and `baton agents check` fails a name that is not in this table.

| Outcome | AI does | Human does | Human decides |
| --- | --- | --- | --- |
| Understood system | context explorers read each area, the integrator joins flows and the landscape, the grader checks every citation (gate 0) | the PO and the Tech Lead answer the day's questions (`baton context questions`), the Tech Lead resolves contradictions | the Tech Lead accepts an area by answering its questions, or overrides gate 0 for one story with a recorded `Gate-0-Override:` line |
| Clear, aligned stories | drafts stories, asks for what the note lacks, checks the Definition of Ready | the PO gives intent, answers clarifications, confirms domain lines | the PO sets Ready (gate 1) |
| A design inside the architecture | challenge round, C4 delta, pattern ledger, diagrams; the design lenses | the Senior Engineer reads first and writes findings | the Tech Lead approves, asks for changes or blocks (gate 2) |
| Working, conforming code | builds to the design; sensors; fixes from the triage file | the Senior Engineer answers blocked questions, runs the loader on the test environment | - |
| Verified change | AC tests, data checks, the review lenses, triage, security last | the Senior Engineer marks each lens finding agree or disagree | - |
| Accepted change | confidence.json, evidence.md, the trace page | the Senior Engineer reads by lane; the PO confirms the feature outcome (full track) | the Tech Lead sets Approved (gate 3) |
| Shipped and recorded | change note, promoted workspace, trace, code PRs and the docs PR linked both ways | - | the Tech Lead merges the PRs together and tags |
| Rules that improve | drafts rules from incidents, clarifications and answered questions | the Senior Engineer and the PO approve | the Tech Lead owns `profile/domain.md` |

## People and agents

| Human | Owns | Gates |
| --- | --- | --- |
| Product Owner | intent: feature notes, story quality, glossary, invariants in business terms | gate 1 |
| Tech Lead | feed-forward: `profile/domain.md`, risk zones, C4 intent, ArchUnit rules, `profile/models.yaml` (which model each role runs on) | decides gates 2 and 3; merges a story's code PRs and docs PR together, then runs `baton tag <S>` |
| Senior Engineer | feedback: sensors, golden set, `confidence-weights.yaml` (edited outside Claude), `/standards record`, `/agent-regression` | first reader at gates 2 and 3 |

| Agent | Produces | Refuses a story not in |
| --- | --- | --- |
| story-drafter | stories from a feature | n/a |
| architect | design note, change spec, generated diagrams | Ready, Design Changes Requested |
| developer | branch, code, tests, sensor reports | Design Approved, QA Fail |
| qa | test report, lens reports, triage | In Review |
| security | security report | In Review, QA Pass |
| documentation | change note, codebase map, promoted workspace | Approved (or an accepted spike) |
| release | code PRs and the docs PR (`story/<F>-<S>`), linked both ways, to each repo's default branch; `PR:` lines, metrics | Documented |

Each agent runs on the model `baton models <S>` gives its role; a reviewer is never a weaker model than what it reviews. No agent approves its own work. The author is the agent identity; the approver is a human.
