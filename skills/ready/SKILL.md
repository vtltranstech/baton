---
name: ready
description: Definition-of-Ready check with a clarification loop for ANY story - agent-drafted or human-written, in a feature or ad hoc. Says exactly what is missing, asks the human until there is enough to build, then hands to the PO for Ready. Use as /ready S-010 | /ready F-002 | /ready all.
---
Readiness check for: $ARGUMENTS (a story id; a feature id = every story of that feature in Draft or Needs Clarification; `all` = every such story under docs/stories/, including docs/stories/backlog/).

Read the workflow skill, the triage skill, profile/domain.md and the `story-writing` skill (its Definition of Ready section is the checklist). Run the story-drafter agent in READINESS mode for each story (it checks; it never rewrites a human's words).

## 0. Story branch
Switch to `story/<feature-id>-<story-id>`; if it does not exist (a story a human wrote), create it from the default branch (`workflow` skill) and commit the story file as it stands with `<story-id>: stories drafted (story-drafter)` only when the drafter wrote it, else `<story-id>: story added (human)`. Commit points follow the `workflow` skill's commit-points section.

## 1. Normalise a human-written story
If the story lacks the standard header, add it without changing the body: `Feature:` (the folder it sits in, or `none` for backlog/), `Depends-On:` (proposed from the content and marked in your question to the human, never `none` by default), `Jira-Key:` blank, `Jira-Type:` / `Labels:` / `Track:` proposed from the content per triage.md and marked `(proposed)`, `Estimate:` proposed, `Created:` today, `Author: human`. Sections missing from the template are added empty (Dependencies, Risks, Out of scope, Open questions). Agent-drafted stories already have all this.

## 2. Check against the Definition of Ready
For each item, PASS or a one-line gap:
- Story paragraph says who, what, why in business terms
- 3-6 ACs, each Given/When/Then, each with a number or an observable, each naming the collection, API or screen it is checked against
- At least one negative AC; an empty-state AC if a screen is involved
- No AC assumes an answer to an item under Open decisions in the domain context
- Jira-Type, Labels and Track present and consistent with the content (a "Bug" with a new endpoint is not light)
- Estimate S or M (L must be split - propose the split)
- `Depends-On:` lists story ids or says `none`, and the human has confirmed it; any fixture or data a human must supply is named under `## Dependencies`
- Nothing technology-specific in the Story paragraph (fine inside ACs as verification targets)
- Open questions empty, or each one answerable by a named person
- Capacity: if the story has an API, file, batch, messaging or a new collection, `## Capacity` gives the numbers per the `standards` skill's `capacity.md`, or `unknown` with who will find out. Ask for them as options with ranges; never fill one in

Write the result into the story under `## Readiness` as a dated checklist, score = passes / items. Commit the story (and `docs/status.md` if you changed it): `<story-id>: readiness <n>/9`. After each clarification round, commit again with the new score.

## 2a. Context check
When `profile/branch-points.yaml` exists (`baton context build` wrote it, which /onboard does), run `baton context check <story-id>` (contracts/context-map.md); without it, skip this step and say the product has no context map yet. The check includes gate 0: an area the story changes that is not understood for its track gives `not-understood`, `question`, `contradiction` or `boundary-unknown` gaps. For those, run the `build-context-map` skill with `focus <feature-id>` first (it explores and asks), then run the check again; the gaps it leaves join the clarification loop below. The state-gate hook refuses Ready for PO and Ready without the check's manifest once the product has a context map. It looks up what the title and ACs name (collections, endpoints, topics, domain words), widens that to the modules within two hops, writes the manifest `docs/design/<F>/<S>-context.md` and adds each gap to `## Open questions` as a `[context]` line, phrased for the PO or the Tech Lead. Exit 2 = a gap blocks this track (light: an undefined domain word or an unresolved edge leaving the scope; full: also an undocumented branch point in a module the story changes, or an unprofiled collection it writes; a spike never blocks): the story cannot go to Ready for PO, and `baton state-check` refuses it. The blocking gaps join the clarification loop below. An answer that defines a word or states a rule goes into `profile/domain.md` only on the PO's yes (a word as a row of the Domain words table with `confirmed: true`; a rule as `### R<n>` with `fields:`, `source:` and `confirmed: true`); then run the check again. A draft the PO set `confirmed: true` in `profile/domain-drafts.md` moves the same way, and is deleted there. Never edit `profile/branch-points.yaml` except a `rule:` the PO or Tech Lead named.

## 3. Clarification loop (max 3 rounds per story)
If any gap remains, ask the human with the AskUserQuestion tool - ONE call per story, up to 4 questions, each the smallest question that closes a gap, with 2-4 concrete options where the answer is a choice (e.g. "Is X in scope for this release?" -> Yes / No / Defer to the next feature). Free text via Other.
- Human present and answers: write the answers under `## Clarifications` as `- <date> Q: <question> A: <answer>` (verbatim), apply them (fill the gap, never reword the human's story text beyond what the answer requires), re-check, and ask again only for what is still open.
- An answer that states a business rule: propose the line for `profile/domain.md` in the same AskUserQuestion call; on the human's yes, add it under the right section and end the clarification with `-> domain.md: <the rule line>`. `baton trace` lists these as what the feature taught the system.
- Human not present or answers "not now": leave the story `State: Needs Clarification`, list the open gaps in `## Open questions`, and add it to the standup blockers.
- After 3 rounds with gaps still open: `State: Blocked - needs refinement session`, reason recorded, stop.

## 4. Hand-off
All items pass and `baton context check` (when run) exits 0 -> set `State: Ready for PO`, update docs/status.md (add the row if the story was human-written and absent), and print: story id, track, estimate, one line per clarification made.
Then, if a human is present, ask ONE question: "S-010 is ready. Set State: Ready and start /build now?" with options **Set Ready and build (Recommended)** / **Set Ready only** / **Leave for refinement**. Only a human answer moves the state to Ready - this IS gate 1 for ad-hoc stories. On Ready, commit the story and `docs/status.md`: `<story-id>: Ready (PO)`.

Never write code or design. Never set Ready without a human answer. Never delete or rewrite a human-authored sentence; add beneath it.
