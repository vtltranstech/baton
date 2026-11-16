---
name: data-check
description: How the qa agent verifies stories against the shared test environment's data - generic check shapes (exactly-one-parent, orphans, reconciliation, duplication, spot-check vs fixture, performance) for Mongo or SQL, with the project's concrete patterns taken from profile/domain.md section  Data-check patterns. Use for any AC that names a collection or table.
---
# Data checks against the test environment

Every AC that names a collection/table gets a data check, run read-only against the environment named in `profile/project.md` (URI from the variable it names), recorded with the exact command and the numbers. Scripts live in `scripts/qa/`; reuse before writing new ones. The project's concrete patterns (collection names, keys) are in `profile/domain.md` section  Data-check patterns - read them first; the shapes below are the generic forms.

## Check shapes
- **Exactly-one-parent** - group children by id, collect distinct parents, report any with count != 1. (Mongo: `$group` + `$addToSet` + `$match $size`; SQL: `GROUP BY child HAVING COUNT(DISTINCT parent) <> 1`.)
- **Orphans** - children whose parent id has no row/document (Mongo `$lookup` -> size 0; SQL `LEFT JOIN ... WHERE parent.id IS NULL`).
- **Reconciliation** - source rows vs target rows per entity type for the period; print both counts; every difference explained (filters, dedupe, scope) or it is a defect.
- **Duplication** - the same logical record under more than one key/level (hash or natural-key group with count > 1); expected 0 when the domain says "referenced, not copied".
- **Spot-check vs fixture** - a human-supplied CSV of expected outcomes (ids, inputs, expected result); run the resolver/API per row; report mismatches as a table.
- **Performance AC** - run 5 times after one warm-up; report p50 and max; state fixture size. For a rate or concurrency target, drive that load and report p95, errors and the environment. If the test environment cannot show it, write `Performance not measured: <why>`; never report the target as met.
- **Period/partition key** - if `profile/project.md` names a period key, every check filters on it, and a check for rows missing it is included.

## Recording evidence
Evidence column: script name, period/partition, the number - e.g. `check_parent.js p=2026-08 -> bad=0, src=517,204 tgt=517,204`. Never "passed" without a number.

## Rules
- Read-only: no insert/update/delete/drop in any QA script.
- URI variable not set -> the check is FAIL with reason "test environment not reachable", never skipped.
- New scripts go to `scripts/qa/` with a header: story id, AC, usage.
