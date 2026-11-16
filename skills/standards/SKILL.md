---
name: standards
description: Guardrails, not textbooks - the common Java/React house rules (stack.md), the pattern-validity ledger (patterns.md), and the mechanical sensors (PMD, Checkstyle, ArchUnit, ESLint); project invariants and versions come from profile/. Read by architect, developer and the craft lens. Use as /standards to see the index, or /standards record to turn an observed failure into a rule.
---
# Engineering standards = guardrails

The model already knows SOLID, Spring idioms and Java features. What it does not know is OUR constraints, and what it does not do unprompted is apply principles consistently under "make it green" pressure. So this skill holds four things only:

1. **`stack.md`** - constraints common to all our Java/React projects: layering, data rules by datastore, batch, API, React, testing, logging, forbidden patterns. Versions are NOT here - they are detected into `profile/stack-detected.md`. Project invariants are NOT here - they are in `profile/domain.md` section  Invariants.
2. **`capacity.md`** - the numbers to ask for, and which framework and configuration they lead to (Spring Batch or not, MVC or virtual threads, pool sizes). A choice cites a number from the story.
3. **`patterns.md`** - the pattern ledger and validity tests: a principle is valid only when a force in the story calls for it. This is how "which principle was applied, and was it the right one" becomes checkable.
4. **`sensors/`** - mechanical checks (complexity, size, duplication, layering, forbidden patterns, domain-language names) that run in the build and cost no tokens.

The sensors live at the plugin root, in `sensors/` (`../../sensors/` from this skill); every mention of `sensors/` in this skill and in `stack.md` means that folder.

No reference library is loaded. If an agent needs depth on a principle it already knows it; if it needs OUR position, it is in stack.md or patterns.md or it does not exist yet.

## Who reads what (always; nothing else from this skill)
| Agent / lens | Reads | Must produce |
| --- | --- | --- |
| architect | stack.md, capacity.md, patterns.md, profile/stack-detected.md (re-verified), profile/domain.md section  Invariants | the capacity table, the pattern ledger (one row per class) + the three simplicity questions in the Approach |
| developer | stack.md, patterns.md (ledger rows of its story), profile/stack-detected.md | a `## Rule ledger` in the Dev summary: per task, which stack.md rule or ledger row shaped the choice, or "none applied"; sensors green before In Review |
| craft lens | stack.md, patterns.md, profile/stack-detected.md, profile/domain.md section  Invariants, the sensor reports | findings with evidence; pattern-validity verdicts; the three questions re-asked |
| design-review lens (rubric walker) | patterns.md, capacity.md | invalid / incomplete ledger rows; a technology choice with no number behind it |

## `/standards record`
Capture one observed failure - a lens finding a human agreed with, a design sent back, a sensor that should have fired and did not. Take: what happened, where, which rule or threshold would have caught it. Propose ONE of: a line in stack.md's forbidden list, a threshold change in sensors/ (mirrored in stack.md), a row in patterns.md's validity table, or a checkpoint question for an agent. Show the diff; a human approves. Never add a rule speculatively; every line here is earned by an incident.

## `/standards` (no argument)
Print this index, the current thresholds from stack.md and sensors/, and the count of forbidden-pattern hits per sprint from docs/metrics.md.
