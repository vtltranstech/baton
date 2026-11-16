---
name: elicitation
description: Pressure-test the most recent artefact (stories, a design note, a decision) with a short menu of structured critique methods - socratic, pre-mortem, red team, first principles and others - chosen from references/methods.csv. Used at gate 1 and gate 2 pauses, or directly as /elicitation.
---
Refine the target: $ARGUMENTS (a story id, a design note path, or nothing = the most recent artefact in this conversation).

The catalogue is `references/methods.csv` (num, category, method_name, description, output_pattern). Never paste the whole file into the conversation; read it, pick, and show only the picks.

## When this runs automatically
- `/stories`, after drafting, when a human is present: offer the menu once against the drafted stories before the PO reviews them.
- `/build`, on "Request changes" at the design review: offer the menu against the design note so the human can pick a method instead of writing free-text comments.
- Any agent may invoke it on its own output when confidence is below 80.

## The menu
Pick 2-4 categories that fit the target (risk before a build, technical for a design, collaboration when stakeholders compete, core for anything), then hand-pick FIVE methods that attack the target from different angles. For designs, always consider: Pre-mortem / Inversion Analysis (what guarantees the worst outcome named in `profile/domain.md` section  Severity hints), Red Team vs Blue Team (entitlement, data exposure), Second-Order Thinking (integration and mastering boundaries), Stakeholder Round Table (the personas in `profile/project.md`).

HALT and offer:
- the five methods by name, one line each
- **Reshuffle** - five new methods, excluding those already offered
- **List all** - the catalogue as a compact table
- **Proceed** - no further elicitation

## Running a method
Use the method's description as intent and its output_pattern as the flow. Scale depth to the target: a story gets a light pass, a full design gets the full treatment. Show what the method revealed and the concrete changes it proposes to the artefact, then HALT: **Apply** / **Reject** / other direction. Never change the artefact unless the human accepts. Refinements compound: each method runs on the current version.

When a method casts personas (round table, expert panel, debate), use the personas listed in `profile/project.md` plus the Tech Lead.

## Proceed
Hand the refined artefact back to the calling skill as the replacement for what it had, and say in one line which methods were applied and what changed. Record applied methods in the artefact under `## Elicitation` (method, date, one-line outcome).
