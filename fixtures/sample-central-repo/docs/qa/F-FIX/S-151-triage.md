# Triage: S-151

R1 edge-case: job runs at midnight across billing periods. Verdict: low.
R2 craft: NoticeDoc not in the ledger. Verdict: low.
R3 domain: notice wording. Verdict: false - wording is out of scope.

## Findings by lens
| Finding | Verdict | Lenses |
| --- | --- | --- |
| F1 | low | edge-case |
| F2 | low | craft+conformance |

## Counts
HIGH: 0
MEDIUM: 0
LOW: 2

<!-- baton:provenance
agent: qa
skills: review-lenses, data-check
profile: domain.md#severity-hints
model: strong (opus)
started: 2026-11-04T12:00:00Z  finished: 2026-11-04T12:30:00Z
-->
