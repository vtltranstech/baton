# Domain Fidelity Lens

**Goal:** Is the code faithful to the business rules as written, and does it speak the domain's language? Not "does it pass the ACs" (QA), not "does it match the design" (conformance) - a design can misread a rule and the code can faithfully implement the misreading. You check the code against the rules themselves.

**Inputs:** `rules` (`profile/domain.md`), `story` (the story file - its ACs and Clarifications), `design` (read ONLY the "Rules touched" list and the pattern ledger), `content` (the diff or a path).

Read the rules file first, whole. Then the story. Then the diff. Then the design's "Rules touched".

## Sequence
1. **Which rules does this code touch?** From the diff alone, list every domain rule the changed code implements, depends on, or could violate - precedence rules, resolution walks, compound keys, period keys, exactly-one relationships, mastering/integration boundaries, scope limits - as named in `profile/domain.md` (its Rules sections and section  Invariants).
2. **Compare with the design's list.** A rule the code touches that the design did not list = finding (the design was incomplete; MEDIUM). A rule the design listed that the code does not honour = HIGH.
3. **Fidelity, rule by rule.** For each touched rule, quote the code (file:line) that implements it and state in one line whether it matches the rule AS WRITTEN. Reinterpretations are HIGH: an "ignore" implemented as "deprioritise", an "always together" key used alone, a cascade that stops early, a default applied where the rule says error, a period filter missing. Partial implementations (happy path only) are HIGH if the rule has a stated exception, else MEDIUM.
4. **Open decisions.** Any code that embodies an answer to an item under "Open decisions" in the rules file = HIGH, whatever the design said.
5. **Domain language.** New types, methods, fields and variable names: do they use the domain's words? A domain concept named `data`, `item`, `node2`, `processX`, or a persisted field named differently from the canonical shape in the profile, is LOW each; a domain word used for the wrong concept is HIGH.
6. **Tests speak the domain.** Test names and fixtures should describe the rule in domain words, not the method. Tests that never exercise the rule's exception clause are MEDIUM.

## Evidence rules
- Every finding: the rule's name as it appears in the rules file, file:line, the quoted code, and the sentence that would make it faithful.
- Never invent a rule. If the rules file is silent, say "rules file silent on X - Open question for the PO", severity none; do not decide it yourself.

## Output
```markdown
## Domain fidelity: <story-id>
Rules touched by code: n   Listed by design: n   Faithful: n   Reinterpreted: n   Open decisions assumed: n

| Rule (as named in domain file) | Code (file:line) | Faithful? | Note |
| --- | --- | --- | --- |

### Findings
- F1 - <rule> - file:line - what differs from the rule as written - fix - severity
### Rules file silent on
- ...
### Domain language
- ...
```
Nothing to report: the table with every row Faithful, and `No domain findings.`

## Content source
Paths come from the launch message. This instruction file is never the content under review.
