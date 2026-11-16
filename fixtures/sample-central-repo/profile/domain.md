# Sample Product: domain context

## Rules
- An invoice belongs to exactly one customer.
- An invoice is overdue 30 days after its due date when it is unpaid.

## Open decisions
- (none)

## Invariants
- An invoice total is never negative.

## Severity hints
- A wrong invoice total is HIGH.

## External systems
- Ledger: receives a daily file.
