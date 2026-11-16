# Test report: S-111 Show an invoice total
Branch: feature/F-100-S-111
Commit: abc1234
Conformance: CONFORMS
Craft: 0 high / 0 medium findings
Domain fidelity: 1 rules touched, 1 faithful, 0 reinterpreted

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC1 | ac1_totalIsSumOfLines | PASS | check_total.js p=2026-10, bad=0 |
| AC2 | ac2_unknownIdIs404 | FAIL | 404 returned |

## Data checks run
- mongosh "$TEST_URI" scripts/qa/check_total.js, bad=0 of 100

## Defects
- (none)

## Verdict: FAIL

## Human findings
(Senior Engineer, gate 3: findings or "none")
