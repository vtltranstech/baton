# Test report: S-151 Flag overdue invoices every morning
Branch: feature/F-FIX-S-151
Commit: 5d6e7f8
Conformance: CONFORMS
Craft: 0 high / 0 medium findings
Domain fidelity: 1 rules touched, 1 faithful, 0 reinterpreted

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC1 | OverdueJobTest#flagsAfter30Days | PASS | check_overdue.js p=2026-10, flagged=12 |
| AC2 | OverdueJobTest#paidIsNotFlagged | PASS | flagged=0 of 5 paid |
| AC3 | OverdueJobTest#rerunSendsOneNotice | PASS | notices=12 after 2 runs |

## Data checks run
- mongosh "$TEST_URI" scripts/qa/check_overdue.js - flagged=12, duplicates=0

## Defects
- (none)

## Verdict: PASS

## Human findings
2026-11-05 09:30 Senior Engineer: none; the upsert key is right. Recommend approve.

<!-- baton:provenance
agent: qa
skills: review-lenses, data-check
profile: domain.md#severity-hints, project.md#test-env
model: fast (sonnet)
commit: 5d6e7f8
started: 2026-11-04T12:00:00Z  finished: 2026-11-04T12:45:00Z
tokens: 52300
-->
