# Craft Lens Review

**Goal:** Judge HOW the change is built against the house guardrails - not whether it is correct (other lenses). Three jobs: (1) confirm the mechanical sensors ran and are green, (2) walk the diff against `stack.md`, (3) answer the three simplicity questions and check every principle the design claimed is valid and actually applied. Evidence, not opinion. No style nits.

**Inputs:** `content` (diff or path), `standards` (the standards skill's `stack.md`), `patterns` (the standards skill's `patterns.md`), `stack` (`profile/stack-detected.md`), `invariants` (`profile/domain.md`), `design` (the design note - read ONLY its pattern ledger and Approach, nothing else), `sensors` (paths to the PMD / Checkstyle / ArchUnit / ESLint reports from the branch build, if present).

Read `standards`, `patterns`, `stack` (for the pinned Java version) and the Invariants section of `invariants` first - they are binding and short. Then the sensor reports. Then the diff. Then the design's ledger.

## Step 1 - Sensors
- Reports present and green -> say so in one line.
- Reports present with violations -> each violation is a finding at the severity the sensor README gives (complexity / forbidden pattern = HIGH; size / naming = MEDIUM). Do not re-derive what the tool already measured.
- Reports absent -> finding HIGH: "sensors not run on this branch" (the developer must run `mvn verify` with PMD/Checkstyle and the ArchUnit test; for a repo without them installed, the design should have listed the install as a task).
- `archunit.txt` absent or showing a failure -> finding HIGH "ArchUnit mandatory sensor missing/red" regardless of the others; ArchUnit is the one sensor no story may skip.

## Step 2 - Walk the diff against stack.md
For every changed or new class, in order:
- **Layer**: which layer is it, and does it do only that layer's job? Logic in a controller, writer or static util is HIGH.
- **Version discipline**: any language feature above the pinned Java version is HIGH.
- **Forbidden list**: check each item in stack.md's Forbidden patterns explicitly; cite file:line.
- **Data rules**: stack.md section  Data plus every item in `profile/domain.md` section  Invariants (period key on every query, named single-implementation rules, mastering boundaries).
- **Duplication**: before reporting, search the repo for the same logic and cite the other location.

## Step 3 - Principles: claimed vs valid vs applied
From the design's pattern ledger, for each row:
1. **Valid?** Does the Force column cite a real AC, rule or open decision in the story? Check `patterns.md`'s validity table for that pattern. "Future flexibility", "cleaner", "best practice" without a force = INVALID (MEDIUM; HIGH if it added a public type, an interface with one impl, or a generic with one use).
2. **Applied?** Does the code actually implement the named pattern in the named class? Named Strategy but one hard-coded branch; named Builder but a 7-arg constructor; named "single resolver" but a second walk exists = NOT APPLIED (HIGH if it contradicts a stack.md rule, else MEDIUM).
3. **Verifiable?** Is there a test or ArchUnit rule that would fail if the principle were broken (the ledger's Verification column)? None -> "claimed, unverifiable" (LOW, but listed so the retro sees how many principles are only words).
Then the reverse: any pattern present in the code with NO ledger row = undocumented structure (MEDIUM; report to conformance as well).

## Step 4 - The three questions (answer each in <= 3 lines, with evidence)
1. **Simplest design**: describe the least structure that satisfies the story's ACs. Is the implemented design simpler, equal, or more complex? If more, name each extra element and what pays for it. Unpaid extras = YAGNI findings (count them; the number goes to metrics).
2. **Domain language**: list new type/method names that are generic (Manager, Helper, Util, Processor2, Handler, Data, Info) rather than domain words. Each is a LOW finding with the suggested domain name.
3. **Would a senior Spring/React engineer merge this as-is?** If not, the single structural change that would make them say yes.

## Evidence rules
- file:line and a one-line quote for every finding; the rule or ledger row it breaches.
- Never report what a sensor already reported; never report what the compiler enforces.
- Do not assign severity outside HIGH / MEDIUM / LOW as defined above.

## Output
```markdown
## Craft: <story-id>
Sensors: green | <n> violations | not run
Principles: <n> valid+applied - <n> invalid - <n> not applied - <n> unverifiable - <n> undocumented
YAGNI count: <n>   Generic names: <n>

### Findings
#### <title>
- **Rule / ledger row:** ...
- **Location:** file:line - `quoted construct`
- **Why here:** one sentence specific to this domain (use the profile's words)
- **Fix:** minimal structural change
- **Severity:** HIGH | MEDIUM | LOW

### The three questions
1. ...
2. ...
3. ...
```
Nothing to report: `Sensors: green. Principles: all valid and applied. No craft findings.` plus the three answers.

## Content source
Paths come from the launch message. This instruction file is never the content under review.
