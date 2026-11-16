---
name: story-writing
description: How the story-drafter splits a feature into stories and writes acceptance criteria, estimates and risks for this project. Use whenever drafting or refining stories.
paths: ["docs/stories/**", "docs/features/**"]
user-invocable: false
---
# Story writing for this project

## Splitting a feature
Split by business outcome, then by the thinnest slice that proves it. In this order of preference:
1. **By rule** - one story per business rule from `profile/domain.md`.
2. **By journey step** - find, then view, then the first detail, then the rest.
3. **By data path** - one story per source -> canonical path.
Never split by layer (UI story, API story, DB story) - those are tasks inside a story, the architect's job.

Every story must pass INVEST: Independent, Negotiable, Valuable to a named user, Estimable, Small (one developer run), Testable.

## Walking skeleton first
The first story of any UI feature is the end-to-end skeleton with one real value on screen (e.g. one search -> one result -> one detail value on screen). Everything after it adds width.

## Acceptance criteria
Given / When / Then, one observable result each, one verification target each:
- `Given <data state in a named collection or fixture>, when <user or system action>, then <result the QA agent can assert>.`
- Name the collection, API or screen element it is checked against.
- Numbers, not adjectives: "0 rows with >1 parent", not "no duplicates"; "renders in <= 3 s for the 2,000-row fixture", not "fast".
- Include at least one negative AC (what must NOT happen) and one empty-state AC where a screen is involved.
- 3-6 ACs. More than 6 means the story is too big.

## Bug shape (Jira-Type: Bug)
Replace the Story paragraph with:
- **Description** - what the user sees go wrong and what should happen instead, 2-4 sentences.
- **Reproduction** - exact steps, environment (the test environment, period), actual vs expected, logs or errors verbatim.
- **Cause hypothesis** - where the defect likely lives and why. Never a prescribed fix.
ACs for a bug are always these three:
1. The expected behaviour holds - Given the reproduction state, when the steps are followed, then <expected>.
2. Tests cover the condition found and fixed - a test that fails on the defect and passes on the fix covers the reproduction, plus one per related case the fix touched.
3. Or: no change is needed, with proof - the reproduction on current code already behaves correctly, or the report was mistaken, evidence recorded under Notes; this supersedes 1 and 2.

## Spike shape (Jira-Type: Spike)
Title is the question. Description: the question, why it is open, which stories wait on the answer. **Approach**: numbered steps (what to research, prototype, who signs off), the time box, what good enough looks like. ACs:
1. The candidates are compared on the criteria that decide - verify: where recorded.
2. The prototype shows the chosen answer works for the cases that matter - verify: where it lives.
3. The answer is recorded with its consequences where the waiting stories can find it (an ADR or the domain context) - verify: where.
4. The people who must accept it have - verify: who, recorded where.

## Estimate rubric
- **S** - one repo, no new collection or endpoint, <= 4 ACs.
- **M** - two repos or one new endpoint/collection, <= 6 ACs.
- **L** - anything larger: split it and write the two stories instead.

## Risks
One line each, pattern: `<what could be wrong> - signal: <how we'd notice>`. Draw from the domain context's Open decisions first; a story that depends on an unresolved decision gets that as a risk AND an open question.

## Open questions
Business questions only, phrased for the Product Owner. If the answer would come from reading code, it is not an open question - leave it to the architect.

## Dependencies
Every story has a `Depends-On:` header line: the story ids that must be Done before this one can start, or `none`. List a story only when this one truly needs its result: it uses that story's API, data or screen, or it would break without it. Do not list stories only to set a preferred order. The tools enforce this line, so a story cannot be designed or built until those stories are Done.

The `## Dependencies` section holds what the tools cannot check: why each story comes first, feature ids, outside teams, and fixtures a human must supply (e.g. "20 hand-picked records from the analyst"). Never "the API must exist" - the architect decides that.

## Definition of Ready (every story, whoever wrote it, before gate 1)
1. Story paragraph: who, what, why - business terms only.
2. 3-6 ACs, Given/When/Then, each with a number or an observable, each naming where it is verified.
3. At least one negative AC; an empty-state AC if a screen is involved.
4. No AC assumes an answer to an open decision in the domain context.
5. Jira-Type, Labels, Track present and consistent with the content.
6. Estimate S or M; L is split first.
7. `Depends-On:` lists story ids or says `none`; fixtures or data a human must supply are named under `## Dependencies`.
8. Open questions empty, or each answerable by a named person.
9. Risks: at least one, with its signal.
10. Capacity: a story with an API, file, batch, messaging or new collection states its numbers in `## Capacity` (`standards` skill, `capacity.md`), or `unknown` with who will find out. Not applicable otherwise, and it passes.
A story passes when all ten hold. /ready runs this and loops with the human on the gaps.

## Human-written stories
Humans may add a story anywhere: under a feature folder or under docs/stories/backlog/ for ad hoc work. Minimum they must write: a title, the Story paragraph, and whatever ACs they can. Everything else /ready fills or asks for. Mark `Author: human` in the header (ready adds it if missing). Agents never rewrite a human's sentences; they add beneath them.

## Before saving each story
- Title is a result, not an activity ("Every account maps to exactly one entity", not "Validate account mapping").
- A business analyst from the domain could read it and say whether it is right.
- No technology words: no datastore, framework, endpoint or table/collection names in the Story paragraph (they are fine inside ACs as verification targets).

End every Markdown artefact you write with your provenance footer, per the `workflow` skill's Provenance footer section.
