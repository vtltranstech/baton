# Design Conformance Lens

**Goal:** Answer one question with evidence: is what was built what was approved? Compare the APPROVED design note against the diff. Deviation is not automatically wrong - but an UNDOCUMENTED deviation is, because gate 2 approved a different thing.

**Inputs:** `design` (path to the approved design note), `content` (the diff or a path), `story` (path to the story, for the ACs and the `## Design review` record).

Read the design note first and extract: Repos touched; Files to change / create; the classes, methods and fields in the low-level design; the Tasks list; Data model impact; the Security considerations; any `## Deviations` section the developer appended. Then read the diff.

## Checks
1. **Files.** Every file in the diff is listed in the design (or covered by a documented deviation). Every file the design lists was touched or has a stated reason why not.
2. **Structure.** Every class/record/interface named in the low-level design exists with the named responsibilities; public methods match in name and intent. New public types not in the design are findings.
3. **Tasks.** Each task in the design maps to commits/changes in the diff. Skipped tasks are findings. Work beyond the tasks is a finding.
4. **Data model.** Collections, fields and indexes changed in the diff equal the design's Data model impact section exactly. Any extra field, index or collection is HIGH.
5. **Behaviour scope.** The diff implements the story's ACs and nothing more: no extra endpoints, flags, config, feature toggles, or "while I was here" changes.
6. **Security considerations.** Each item the design listed under Security considerations is visibly addressed in the diff, or a deviation says why not.
7. **Deviations section.** Every deviation the developer documented is real (matches the diff) and justified in one sentence; every actual deviation you found is documented. Undocumented = HIGH.
8. **Architecture (design conformance).** Read `docs/qa/<F>/<S>-as-built/diagrams.json` -> `conformance` (written by `baton diagram story <S> --diff main` in /build). Every method or class in `undeclared` / `newClassesUndeclared` is a change the design never showed = HIGH ("built without a design") unless `## Deviations` in the design note explains it; every item in `notBuilt` / `newClassesNotBuilt` = MEDIUM. Compare the as-built `flow.svg` with the design's: a new collection, topic, endpoint or cross-repo call that only the as-built flow has is HIGH. If the as-built folder is missing, say so as a finding; do not reconstruct it by reading the diff.

## Output
```markdown
## Conformance: <story-id>
Verdict: CONFORMS | CONFORMS WITH DOCUMENTED DEVIATIONS | DEVIATES

| # | Check | Result | Evidence (file:line / task / section) |
| --- | --- | --- | --- |

### Findings
- D1 - <undocumented deviation or scope creep>, file:line, which design section it contradicts, severity (HIGH undocumented / data model / scope; MEDIUM documented but weakly justified; LOW cosmetic)

### For the architect
- one line per pattern worth feeding back into the design template or the standards (e.g. "design never lists test fixtures; developer added three")
```
No deviations: Verdict CONFORMS and the table only.

## Content source
Paths come from the launch message. This instruction file is never the content under review.
