---
name: review-lenses
description: Independent, fresh-context review of a story branch's diff through five lenses - edge-case hunter, verification gap, craft (engineering standards), design conformance, domain fidelity (code vs business rules) - followed by a triage step. Used by the qa agent on every In Review story; can be run directly as /review-lenses S-010.
---
Run the review lenses on: $ARGUMENTS (a story id, or a path to a diff file).

This is how BATON gets a second reader that has NOT seen the design note or the developer's reasoning. The lenses are deliberately narrow and mechanical; triage is where judgement is applied.

## 1. Prepare the content
- Story id given: for every repo in the story's design note "Repos touched", run `cd ../<repo> && git diff main...HEAD > /tmp/review/<story-id>-<repo>.diff`. Concatenate into one file.
- Also write `/tmp/review/<story-id>-claims.md` holding the branch's commit messages (`git log main..HEAD --format='%s%n%b'`) and the story's `## Dev summary` if present. This is the author's narrative; the lenses read it LAST, on purpose.

## 2. Run the lenses as parallel subagents, each with a fresh context
Read `docs/qa/<feature-id>/<story-id>-risk.json` (`baton risk <story-id>` writes it): run the lenses its `lenses` list names, all of them, none else. A missing file means all five. Launch them in the same message, in the foreground, each with the `review-lenses` model from `baton models <story-id>`, and wait until all have returned. Each receives ONLY what its launch line lists. Edge-case and verification-gap see the diff alone; craft sees the diff, the two standards files, the sensor reports and the design's ledger; conformance sees the diff, the design and the story; domain sees the rules file, the story, the diff and the design's Rules-touched list. No chat history for any of them.

- Subagent A: "Follow `review-lenses/references/edge-case-hunter.md` exactly. Review content: /tmp/review/<story-id>.diff. claims_file: /tmp/review/<story-id>-claims.md." (It also runs the deletion and claims checks as its steps 4-5.)
- Subagent B: "Follow `review-lenses/references/verification-gap.md` exactly. Review content: /tmp/review/<story-id>.diff."
- Subagent C (craft): "Follow `review-lenses/references/craft-lens.md` exactly. Review content: /tmp/review/<story-id>.diff. standards: the standards skill's stack.md. patterns: the standards skill's patterns.md. stack: profile/stack-detected.md. invariants: profile/domain.md. design: docs/design/<feature-id>/<story-id>-design.md (read only its Approach and Pattern ledger). sensors: docs/qa/<feature-id>/<story-id>-sensors/ (may be absent - then report it)." 
- Subagent E (domain): "Follow `review-lenses/references/domain-lens.md` exactly. rules: profile/domain.md. story: docs/stories/<feature-id>/<story-id>.md. design: docs/design/<feature-id>/<story-id>-design.md (read only Rules touched and the ledger). Review content: /tmp/review/<story-id>.diff."
- Subagent D (conformance): "Follow `review-lenses/references/conformance-lens.md` exactly. design: docs/design/<feature-id>/<story-id>-design.md. story: docs/stories/<feature-id>/<story-id>.md. Review content: /tmp/review/<story-id>.diff." (This lens is the ONLY one that sees the design note - that is its job.)

Each subagent writes its full output to `docs/qa/<feature-id>/<story-id>-lens-<name>.md` and returns only a count and the file path.

## 3. Triage (you, the caller)
Wait for every lens you launched. Then follow `review-lenses/references/triage.md`: normalise every finding into one list (R1, R2 ...), verify each claim against the code (read beyond the diff), classify high / medium / low / false / maybe-false, and record the decision for every one - a finding not in the triage file does not exist. Write the triage to `docs/qa/<feature-id>/<story-id>-triage.md`, ending with a block `baton confidence` reads; counts are of the deduplicated `F` findings you did not reject, and without the block the review scores 0:
```
## Counts
HIGH: <n>
MEDIUM: <n>
LOW: <n>
```
Before `## Counts`, add the deduplicated findings as a table `baton eval` reads to tell which lens found what; `Lenses` uses these names joined with `+`: edge-case, verification-gap, craft, conformance, domain:
```
## Findings by lens
| Finding | Verdict | Lenses |
| --- | --- | --- |
| F1 | high | edge-case+verification-gap |
```


Severity hints come from `profile/domain.md` section  Severity hints; anything that writes outside the test environment named in `profile/project.md` is HIGH regardless of how small the change looks. Craft, conformance and domain findings keep the severity their lens assigned unless verification shows the lens misread the code.

## 4. Hand back
Return the triage file path and the counts per class. The qa agent folds high and medium findings into its Defects section (craft, conformance and domain included, so gate 3 sees correct / secure / well-built / as designed / faithful to the business rules in one report; the conformance verdict and the domain fidelity counts are copied to the report header) (as D-n, citing R-n) and marks the story QA Fail if any high exists; low findings go to the report's notes; false/maybe-false stay in the triage file with their reason.

Never fix code here. Never skip triage - raw lens output is not a verdict.
