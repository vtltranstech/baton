# S-151 Flag overdue invoices every morning

| Field | Value |
| --- | --- |
| Date | 2026-11-05 |
| Repos | invoice-service |
| PR | https://example.invalid/pr/201 |
| Track | full |

## What changed
- **OverdueJob:** flags invoices 30 days past due every morning.
- **notices:** new collection, one row per overdue invoice.

## Why
- **Story S-151:** clerks found overdue invoices by hand.

## Decisions
- **Overdue rule:** recorded in domain.md from the S-151 clarification.

- **Architecture:** +2 elements (overdueJob, notices), +3 relationships (overdueJob -> db, overdueJob -> notices, clerk -> notices).

<!-- baton:provenance
agent: documentation
skills: change-note, doc-style
commit: 5d6e7f8
started: 2026-11-05T10:00:00Z  finished: 2026-11-05T10:20:00Z
-->
