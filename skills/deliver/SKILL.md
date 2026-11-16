---
name: deliver
description: Take one feature from its note to open PRs in one command - /stories, gate 1, /build (gate 2 inside), gate 3, /ship - asking the human only at the gates. Resumable - it reads every story's State, so running it again continues where it stopped. Use as /deliver F-003.
disable-model-invocation: true
---
Deliver the feature: $ARGUMENTS (a feature id such as F-003, or a path under docs/features/).

Resolve the argument as the `stories` skill does. Read the `workflow` and `triage` skills. Refuse to run if `profile/project.md`, `profile/domain.md`, `profile/stack-detected.md` or `docs/architecture/workspace.dsl` is missing or still says pending - say which and point to `/onboard`.

This skill chains the existing skills; it adds no step of its own and skips none. It never remembers progress: before each step it re-reads the State of every story of the feature with `baton stories --feature <feature-id>` (which also finds stories that live only on their `story/<F>-<S>` branch), so a second run, a new session, or a run after someone edited a story continues from the files. Only a human answer moves a story through gate 1 or gate 3, exactly as in `/ready` and `/sprint-review`; the state-gate hook refuses any state its evidence does not justify.

Print a one-line progress marker before each step ("F-003 step 3 - building S-302 (2 of 4)") and the story table after it.

## 1. Stories
Gate 0 comes first, through the skills it chains: `/stories` and `/build` run `/build-context-map focus <feature-id>` when the areas the feature changes are not understood, and stop the feature while the map still refuses it; say so and list what is waiting and for whom. If `docs/stories/<feature-id>/` has no story, or the feature or any of its stories is in Draft or Needs Clarification, run the `stories` skill on the feature. It asks the feature questions, drafts, and runs `/ready`. Then go on with the stories that came out Ready for PO or Ready; stories still in Needs Clarification or Blocked are listed as waiting and not built.

## 2. HUMAN GATE 1 - Product Owner sets Ready
For the stories in Ready for PO, ask with AskUserQuestion, up to 4 stories per call, one question each: "Product Owner: <story-id> <title> (<track>, <estimate>, readiness N/N). Set Ready?" Options: **Set Ready** / **Leave for refinement**. Set `State: Ready` only on a Set Ready answer and update docs/status.md. A human who is not the Product Owner answers "Leave for refinement"; the story waits for the next run.

## 3. Build, in dependency order
Run `baton deps` on each Ready story and order them dependencies first. For each, one at a time, never in parallel:
- Exit 2, or a dependency's PR not merged (checked as the `build` skill says): skip it, list it as "waiting on <story-id>", and go on with the next story.
- Otherwise run the `build` skill on it, every step, including its design-review question at gate 2. Its stop rules are this skill's: a Blocked story, or a third QA or security failure, stops that story only; go on with the next.

## 4. HUMAN GATE 3 - approval, per lane
For each story the build left in QA Pass, show the `/sprint-review` section for it (lane, score, caps, lowest three signals, AC table, verdicts, recommendation) and ask ONE question per story: "Gate 3 for <story-id>, <lane> lane, score NN. <the lane's prompt from the sprint-review skill>. Human findings go under `## Human findings` in <test report path>." Options:
1. **Approve** - "The findings are written; sets State: Approved." Re-read the test report first: if `## Human findings` has no line written by a person, say so and ask again; never write findings for the human.
2. **Send back** - "Your reason goes under `## Human findings` verbatim, dated, and the story is set Blocked for the Tech Lead to route."
3. **Not now** - "Stops here; run /deliver again after the review."
Set `State: Approved` only on Approve.

## 5. Ship
Run the `ship` skill on each Approved story. A person merges every PR; this skill never merges. A later story that depends on one just shipped stays "waiting on" until its PR is merged; say so.

## 6. Repeat or stop
Go back to step 3 while a Ready story became buildable during this run (its dependency's PR was merged and the human confirmed it). Otherwise stop and print:
- a table per story: id, title, State, gate 2 outcome, QA, security, confidence and lane, PR
- what each waiting story waits for: an answer (who), a merge (which PR), or a review (which lane)
- "Run /deliver <feature-id> again once those are done."
