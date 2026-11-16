# Test report: S-152 Show the overdue list for a billing period
Branch: feature/F-FIX-S-152
Commit: 9c8b7a6
Conformance: CONFORMS
Craft: not run (low risk)
Domain fidelity: not run (low risk)

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC1 | InvoiceControllerTest#overdueForPeriod | FAIL | returned invoices of 2026-09 too |
| AC2 | InvoiceControllerTest#noneOverdue | PASS | empty list message |

## Data checks run
- mongosh "$TEST_URI" scripts/qa/check_overdue.js p=2026-10 - 3 rows from another period

## Defects
- D1: query has no billingPeriod key, InvoiceController.java:58, open the list for 2026-10, breaks AC1

## Verdict: FAIL

## Human findings

<!-- baton:provenance
agent: qa
skills: review-lenses, data-check
profile: project.md#test-env
commit: 9c8b7a6
started: 2026-11-05T10:30:00Z  finished: 2026-11-05T11:00:00Z
-->
