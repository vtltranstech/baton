---
name: doc-style
description: The writing standard for every Markdown file an agent writes under docs/ - change notes, ADRs, codebase map, status.md, metrics.md, release notes. Dense, ASCII-only, tables for facts, one idea per line, readable by a human in a glance and parsable by an agent. Includes the exact formats of status.md and metrics.md. Enforced by `baton doclint` and the doc-lint hook.
---
# Doc style: facts, not prose

Readers are a Tech Lead with two minutes and an agent with a token budget. Both want the fact, its source, and nothing else.

## Rules

| Rule | Do | Not |
| --- | --- | --- |
| **Output** | Write only the Markdown. | Preambles, "Here is the change note", sign-offs. |
| **Characters** | ASCII only: `-`, `->`, `...`, `"`, `'`, `<<x>>`, `>=`. | Em dash, arrows, bullets, smart quotes, ellipsis, emoji. |
| **Facts** | Key facts and parameters in a table. | The same facts in a sentence. |
| **Steps** | Numbered list, one action per item. | A paragraph that narrates the steps. |
| **Lists** | `- **Term:** fact.` Under 20 words per item. | Items that wrap to a second line. |
| **Paragraphs** | At most 2 sentences, 40 words; usually none. | Narrative transitions, "In this section". |
| **Caveats** | One line: `> [!WARNING] Restart the loader after the index change.` | A multi-line quote; a caveat buried in a list. |
| **Flows** | Link the generated SVG (`baton diagram`) or a 5-line ASCII sketch. | Hand-written Mermaid or DSL. |
| **Headings** | Say what the section holds, under 60 characters. | "Overview", "Introduction", "Miscellaneous". |
| **Sources** | Every number names its file: `(source: docs/qa/F-1/S-2-test-report.md)`. | Numbers with no source; behaviour not seen in the code. |
| **Terms** | The domain words in `profile/project.md`; define an acronym once in a table. | Synonyms for the same thing; undefined acronyms. |
| **Empty** | `none`, or `-` in a table cell. | Leaving a section out; "N/A - not applicable". |

Banned words (the lint rejects them): it is important to note, note that, in order to, let's, we will, simply, basically, obviously, of course, furthermore, moreover, additionally, comprehensive, robust, seamless, leverage, delve, very, really, in conclusion, in summary.

One document type per file: a change note states what changed; an ADR records one decision; the map indexes code. Do not mix explanation into reference.

## Check before you finish

```
baton doclint docs/changes/F-1/S-2-change-note.md     # exit 1 lists file:line: rule: fix
baton doclint --fix <file>                            # replaces non-ASCII characters
```
The doc-lint hook runs the same check after every Write or Edit under `docs/` and hands problems back to you. Fix them; never work around the rule with code fences or HTML.

## docs/status.md
One row per story. The agent that changes State updates the row in the same edit.

```markdown
# Status

| Story | Title | Track | State | Owner | Loops | Created | Updated | Done | Waiting on |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S-010 | Loyalty discount on orders | full | In Review | developer | 1 | 2026-11-01 | 2026-11-03 | - | - |
```
- **Title:** under 6 words.
- **Owner:** the agent or role that acts next.
- **Dates:** ISO `YYYY-MM-DD`.
- **Waiting on:** a story id, a question id, or `-`.

## docs/metrics.md
Append rows; never edit a past row.

```markdown
# Metrics

## Baseline
| Step | Who | Works (h) | Waits (h) | Handoffs |
| --- | --- | --- | --- | --- |

## Calibration
| Story | Track | Confidence | Review | Rounds |
| --- | --- | --- | --- | --- |

## Build
| Story | Track | Minutes | Tokens | Loops | Design rounds | Impl model | Review model | Lines added | YAGNI | Forbidden hits | Complexity | Generic names | Principles invalid | Conformance | Sensors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Delivery
| Story | Lead time (d) | Cycle time (d) | Loops | Rounds | Confidence | Review | Gate-3 score | Lane | Tokens | Minutes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
```
- **Baseline:** written once by the team before the product's next story, from `docs/enablement/baseline.md` (one row per step from feature idea to production); never edited after. Every later figure is reported beside it as waiting removed.
- **Calibration:** `/build` after gate 2. Review is `auto-pass`, `approved`, `changes` or `blocked`.
- **Build:** `/build` at the end. Sensors is `green` or the red tool names.
- **Delivery:** release agent, with the PR.
- **Unknown value:** `-`, never a guess.

## Change note (docs/changes/<F>/<S>-change-note.md)

```markdown
# S-010 Loyalty discount on orders

| Field | Value |
| --- | --- |
| Date | 2026-11-03 |
| Repos | order-service |
| PR | pending |
| Track | full |

## What changed
- **OrderService#place:** applies the loyalty discount before the total.
- **loyalty_tiers:** new collection, read only.

## Why
- **Story S-010:** loyal customers paid full price (link).

## How to verify
1. `mvn -q -pl order-service test -Dtest=LoyaltyDiscountPolicyTest`
2. Expect `Tests run: 6, Failures: 0`.

## Operational impact
| Item | Change |
| --- | --- |
| Collections | `loyalty_tiers` (new), index `customerRef` |
| Jobs | none |
| Config | none |

> [!WARNING] Create the index before deploy: the loader scans without it.

## Design conformance
(the table from docs/qa/<F>/<S>-as-built/diagrams.md)

## Decisions
- **ADR-007:** discount rules live in the domain service (link).

## Links
| Story | Design | Diagrams | Test report | Security report |
| --- | --- | --- | --- | --- |
```

## ADR (docs/decisions/ADR-nnn-<slug>.md)

```markdown
# ADR-007 Discount rules live in the domain service

| Field | Value |
| --- | --- |
| Date | 2026-11-03 |
| Status | Accepted |
| Decided by | Tech Lead |
| Story | S-010 |

## Context
- **Open decision:** <verbatim from profile/domain.md>

## Decision
- **Chosen:** <one line>
- **Rejected:** <option> - <why, one line>

## Consequences
| Area | Effect |
| --- | --- |
```

## Codebase map (docs/context/codebase-map.md)
- **Generated block:** `baton wiki` and `baton verify` write one table per repo, one row per page.
- **Hand edits:** never inside the markers; outside them, one row or one bullet per fact.

## Sources
- **Google developer style guide:** short sentences, one idea each, tables for comparable data.
- **Diataxis:** reference states facts; explanation lives in its own document.
- **Docs for agents:** self-contained sections, descriptive headings, defined terms, Markdown tables.
