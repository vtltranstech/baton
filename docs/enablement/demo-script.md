# Demo script - feature to trace, file by file

Fifteen minutes, on the fixture product. Open each file as you say the line.

| # | Say | Open |
| --- | --- | --- |
| 1 | A feature starts as a note in business words. | `docs/features/F-100-invoice-totals.md` |
| 2 | Gate 0: nothing is drafted on code the context map does not understand. | `baton context check F-100` output; `docs/context/questions.md` |
| 3 | Every AC is checkable and names the collection or API it is checked against. | `docs/stories/F-100/S-112.md` |
| 4 | The design is a delta on the architecture of record, with a challenge round first. | `docs/design/F-100/S-112-design.md` |
| 5 | Every pattern names the test that fails if it is broken. | `docs/design/F-FIX/S-151-design.md`, section 4a |
| 6 | The sensors are deterministic: ArchUnit, PMD, Checkstyle. | `docs/qa/F-100/S-112-sensors/` |
| 7 | Five lenses review; triage consolidates; the fix loop reads triage only. | `docs/qa/F-100/S-112-triage.md` |
| 8 | Security runs last; a new report names the branch heads it reviewed (`Heads:`), and a later commit makes it stale. | `docs/qa/F-100/S-112-security-report.md` |
| 9 | Confidence is computed from evidence; a human approves. | `docs/qa/F-100/S-112-confidence.json`, `-evidence.md` |
| 10 | One page shows the whole story. | `baton trace F-100 --open` |
| 11 | Where every story is, without asking anyone. | `baton board` |
