---
name: retro
description: Evidence-based sprint retrospective for the team - inventories what the sprint actually produced (stories, diffs, reports, metrics), aggregates it, judges acceptance per story, runs a short team discussion, and writes the retro document with action items that become prompt/skill/threshold changes. Use as /retro [feature-id or sprint label].
disable-model-invocation: true
---
Run the retrospective for: $ARGUMENTS (a feature id such as F-002, or a sprint label; default = every story set to Done since the last retro document).

The references under `references/` are the method; follow them in order, substituting our artefacts for theirs: our "epic" is a feature (`docs/features/F-xxx.md`), our "tickets" are stories under `docs/stories/F-xxx/`, our "plans" are the design notes, and our build sessions are the `/build` rows in `docs/metrics.md`. Where a reference names a script that does not exist here, do the equivalent with git directly (`git log`, `git diff --stat` per branch range).

## Phase 1 - Evidence (`references/evidence-gathering.md`)
Inventory, with paths (a finished feature's story artefacts are under `docs/archive/<feature-id>/` once `/ship <feature-id>` archived it; read them there): the feature note, every story and its State history (from `## Design review`, `## Dev summary`, status.md dates), design notes and their Revision counts, test and security reports, lens triage files, change notes, PR links, the `docs/metrics.md` rows (per-story, calibration, build runs), and the commit ranges per story branch in each repo. Never hide a gap: a reader must be able to tell "checked and clean" from "never checked".

## Phase 2 - Aggregate views (`references/aggregate-views.md`)
Across the sprint: loops per story, design rounds, confidence vs outcome (the calibration question: were >= 85 designs sent back?), human review minutes, wall-clock and tokens per track, open questions raised and how long they waited, escalations light -> full, security verdicts, defects after merge. Which files changed most; which stories touched the same modules. The sensor table in metrics.md: lines-vs-estimate, YAGNI, forbidden hits, complexity violations, generic names, invalid or unapplied principles - per story and as a trend; any rising line is an action item, and any lens finding a human agreed with becomes a `/standards record`. Lens precision: per lens, the share of its findings the Senior Engineer marked `agree` in the test reports' `SE: agree | disagree` cells (unmarked ones are counted apart, never as agree); a lens under 50% over the sprint is an action item for the Senior Engineer.

## Phase 3 - Acceptance verdict per story (`references/acceptance-verdict.md`)
For each Done story: does the delivered diff plus the test report satisfy the story's ACs and the feature's success statement? Profile from the diff when ACs are thin. Verdict: Accepted / Accepted with gaps / Not accepted, with the evidence line.

## Phase 4 - Team discussion (`references/team-discussion.md`)
Short, structured, with the three humans (PO, Tech Lead, Senior Engineer) - if they are not present, write the questions for them and stop before Phase 5. What the agents got wrong and where it was caught; what the gates caught that would have shipped; which guardrail fired; what the humans spent time on that an agent should have.

## Phase 5 - Retro document (`references/retro-document.md`)
Write `docs/retros/<feature-or-sprint>-retrospective.md`. Action items are concrete and owned, and each one is one of: a prompt change to an agent, a skill change, a threshold change in the `triage` skill, a domain-context correction, a golden-set addition, or a process change for the humans. Close with: run `/agent-regression all` before the next sprint if any prompt or skill changed.
