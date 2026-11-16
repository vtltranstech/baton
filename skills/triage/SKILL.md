---
name: triage
description: How a story's Jira type and labels derive its track (light | full | spike) and which gates apply. Read by story-drafter, architect and /build. Use as /triage to print the rules.
---
# Triage - how a story's Jira type and labels pick its track

Every story carries `Jira-Type:` and `Labels:` (mirrored from Jira once connected; until then set by the story-drafter from the feature note and corrected by the Product Owner at gate 1). The track is DERIVED from them by these rules; nobody sets the track by hand.

## 1. Default track by Jira issue type
| Jira-Type | Track | Notes |
| --- | --- | --- |
| Bug | light | A defect in existing behaviour. |
| Task | light | Config, data fix, small internal change. |
| Sub-task | light | Always belongs to a parent story; inherits its labels. |
| Story | full | New or changed user-visible behaviour. |
| Spike | spike | Investigation only: architect writes findings, no developer run. |
| Epic | - | Never built directly. `/stories` splits it into Stories/Tasks first. |

## 2. Label overrides (applied after the type; later rows win)
| Label | Effect |
| --- | --- |
| `quick-fix` | force light |
| `design-required` | force full |
| `new-api`, `data-model`, `batch-job`, plus any label in `profile/project.md` -> `jira.labels.extra` | force full AND design review is mandatory regardless of confidence |
| `multi-repo` | force full |
| `hotfix` | light; gate 2 skipped; QA + security still run; PR is labelled `hotfix` and flagged for same-day human merge |
| `spike` | spike track |

## 3. Automatic escalation (the architect applies these even on the light track)
A light story becomes full if the architect finds any of: a new collection, field or index; a new or changed endpoint; more than one repo touched; any item under Open decisions in the domain context. The architect sets `Track: full (escalated: <reason>)` in the story and writes the full design note.

## 4. What each track runs
| Step | light | full | spike |
| --- | --- | --- | --- |
| story-drafter | yes | yes | yes |
| Gate 1 (PO) | yes | yes | yes |
| architect | light note (5 sections, no diagrams) | full note (11 sections, diagrams) | findings note |
| Gate 2 (design review) | auto-pass if confidence >= 80, else ask | always ask (`new-api`/`data-model`/... : ask even at 100) | ask (accept findings) |
| developer | yes | yes | no |
| qa + security | yes | yes | no |
| Gate 3 (sprint review) | yes | yes | no |
| documentation + release | yes | yes | documentation only (findings -> ADR or domain context) |

## 5. Drafter rule
When in doubt, full. A light story that should have been full costs a bad design; the reverse costs twenty minutes. The drafter writes one line under `Track:` saying why, e.g. `Track: light - Bug, single module, no data change`.
