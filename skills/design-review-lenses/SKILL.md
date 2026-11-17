---
name: design-review-lenses
description: The architect's pre-handoff gate - independent reviewer lenses run in parallel against a finished design note before a human sees it, so the confidence score is grounded in findings, not self-assessment. Used by the architect on every full-track design; can be run directly as /design-review-lenses S-010.
---
Review the design note for: $ARGUMENTS (a story id).

Runs after the architect has written the design note and BEFORE it sets `State: Designed`. Light-track notes get the rubric walker and the domain-fidelity lens; full-track notes get all lenses. Spikes get the rubric walker and the data-integrity lens.

## Lenses (each a parallel subagent with a fresh context and the `design-lenses` model from `baton models <story-id>`, launched together in the foreground and waited for: it receives the design note path, the story path, the domain context path, and its lens text - nothing else)
1. **Rubric walker** - judges the note against this checklist and reports every miss:
   - every section present and non-empty, or an explicit "Not applicable - why"
   - **diagrams are generated, not drawn**: `baton diagram story <story-id> --check` exits 0 (run it); `docs/design/<F>/<S>-diagrams/diagrams.json` exists and its `source` is the story's change spec; the note embeds the generated SVGs and contains no hand-written Mermaid or DSL block (one is a finding: it will drift)
   - the change spec agrees with the note: every row of the touch-points table is covered by a task and a file under "Repos and files", and every file there maps to a touch point (a file with no touch point = the spec is missing it); a light note whose files add a class, collection, topic or endpoint that the spec does not list is a BLOCKING finding
   - every repo in the blast-radius table appears under Risks; an unknown edge is named there too
   - every class in the low-level design appears in a task; every task maps to a file
   - each AC in the story is addressed by a task AND by a line in "How QA should verify"
   - no open decision from the domain context is silently assumed (check the Open decisions list by name)
   - no new collection, endpoint or repo appears without the story's labels/track justifying it (escalation missed)
   - the challenge round exists, is written before the approach, names a concrete failure per step up from the strawman, and lists the rules touched
   - the confidence "Why" bullets are concrete and the "Reviewer should check" bullets point at real sections
   - capacity: a story with `## Capacity` has the Capacity section; every framework, pool, chunk or index choice cites a number from the story or is marked `assumed`; a choice contradicting `capacity.md` says why; a `stated` value matches the story
   - pattern ledger: every new/changed class has a row; every row's Force cites a real AC, rule or open decision (check `patterns.md`'s validity table - an abstraction with one implementation, a strategy with one variant, a generic with one use, or a force of "future flexibility" is INVALID); every row has a simpler alternative and a verification; the three simplicity questions in Approach are answered with evidence, and the simplest design is not obviously sufficient on its own
2. **Security & compliance lens** - entitlement on every endpoint; client identifiers in logs or responses; data written outside the test environment; mastering rule or outbound-file impact; new dependencies. Reports findings with the section they apply to.
3. **Data-integrity lens** - reads `profile/domain.md` section  Invariants: can this design break any of them (wrong parent, duplicated records across levels, a missing period key, a second implementation of a single-place rule, a count reconciliation depends on)?
4. **Domain-fidelity lens** - reads `profile/domain.md`, the story and the design. For every rule the design's "Rules touched" lists, and for every rule the diagrams or ledger imply even if unlisted: is it honoured exactly as written? Flags any reinterpretation (an "ignore" implemented as "deprioritise"; a compound key used in part; a query without the period key; a precedence rule inverted), any rule the design depends on but did not list, and any Open decision silently assumed. Also checks the challenge round: does the strawman really fail where the architect says it does (re-derive each failure from the ACs/rules); is there a simpler design that satisfies the ACs - if yes, that is a BLOCKING finding with the simpler design written out in <= 5 lines.
5. **Seam lens** (only when more than one repo is touched, or the blast-radius table is not empty) - reads `diagrams.md` (flow, sequences, blast radius): the contract between the repos touched - who owns the schema, versioning, what breaks if one side deploys first; every cross-repo step in a sequence that is new or changed is listed as a seam with its owner, and every IMPACTED repo with how it learns of the change.

6. **UX lens** (a `ui` story on the full track only, run on its own when `baton build` prints step `ux-lens`, before gate 2a and before any design note exists) - loads the `ux-checklist` skill and reads only: the wireframe options, `options.md` and `screen-spec.md` in `<story-id>-wireframe/`, the story, `profile/project.md` Personas, the screens of record of the same area, the UI wiki page, and `<story-id>-sensors/axe.json` when present. Writes `docs/design/<feature-id>/<story-id>-reviews/ux.md` in the checklist's format; it never edits the wireframes.

Each lens writes `docs/design/<feature-id>/<story-id>-reviews/review-<lens>.md` and returns only: verdict (clear / findings / blocking), top findings (<= 5), file path.

## Fold-in (the architect)
Apply the clear fixes to the design note yourself; do not hand the human a list you could have resolved. Then rewrite section 12 Confidence so that: the score reflects what the lenses found (a blocking finding caps the score at 60 until fixed); "Why" cites the lenses; "Reviewer should check" names what you could NOT resolve. Append `## Lens summary` to the note: one line per lens with verdict and link. Only then set `State: Designed` and emit `DESIGN READY FOR REVIEW`.

Never skip the lenses on a full-track or mandatory-review-label story.
