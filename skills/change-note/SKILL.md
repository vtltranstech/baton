---
name: change-note
description: How the documentation agent writes change notes, keeps the codebase map current, and records decisions (ADR style) for this project. Use for every Approved story and whenever a domain decision is settled.
paths: ["docs/changes/**", "docs/decisions/**"]
user-invocable: false
---
# Documentation for this project

Formats and writing rules: the `doc-style` skill. This skill says what each artefact is for and when to write it.

| Artefact | Path | Purpose | When |
| --- | --- | --- | --- |
| Change note | `docs/changes/<F>/<S>-change-note.md` | What changed, how to verify, operational impact | Every Approved story |
| Codebase map | `docs/context/codebase-map.md` | Index of wiki pages, generated | After `baton wiki` / `verify` |
| ADR | `docs/decisions/ADR-nnn-<slug>.md` | One settled open decision | A human settled an Open decision |

## Change note
- **Reader:** the Tech Lead at gate 2, and whoever reads the PR in six months.
- **What changed:** effects first, one bullet per class or resource, at most 5 bullets.
- **How to verify:** the exact commands and expected output, copied from the test report.
- **Operational impact:** a table of jobs, schedules, collections, indexes, config; `none` when empty.
- **Facts only:** from the story, design, reports and diff; nothing you did not see in the code.

## Codebase map
- **Generated:** `baton wiki` and `baton verify` rewrite it. Never hand-edit the generated block.
- **This story:** regenerate and verify the pages of the modules the diff touched.

## ADR
- **Only:** when a human settled an item under Open decisions; the decision is written in the story.
- **Then:** move the item out of Open decisions in `profile/domain.md`, suffixed `(ADR-nnn)`.
- **Never:** record a decision an agent made.

## Before setting State: Documented
1. `baton doclint` exits 0 on every file you wrote.
2. The change note's How to verify runs as written.
3. Every file in the diff appears in the touch points or the codebase map.
4. No open decision was silently closed.

End every Markdown artefact you write with your provenance footer, per the `workflow` skill's Provenance footer section.
