---
name: stories
description: Check a feature note has enough information (asking for what is missing), then draft stories from it; respects stories humans added; ends by running /ready on everything in Draft. Use as /stories F-002 or /stories PROJ-123 (a Jira key).
---
Draft stories for the feature: $ARGUMENTS.

Resolve the argument: a feature id such as F-002 means the single file under docs/features/ whose name starts with that id; a path is used as given. If nothing matches, list docs/features/ and stop.

A Jira key instead (letters, a dash, digits, e.g. PROJ-123, matching `jira.key` in `profile/project.md` when set): look for a note whose header says `jira: <KEY>` and use it. If there is none, take the next free F-xxx and write `docs/features/F-xxx-<slug>.md` with `jira: <KEY>` as its first header line: when a Jira tool from an allowed connector is available, fill it from the issue (summary, description, acceptance criteria, as written); otherwise ask the Product Owner with AskUserQuestion to paste the issue text, and write it verbatim. Never invent the text. Then go on with that feature id. The `jira` skill says how state changes mirror back (one way, Git to Jira).

Read the workflow skill and the triage skill. If the feature is an Epic, the drafter splits it; never accept a single story for an epic.

## 0. Is the system understood? (before anything else)
Gate 0: nothing below runs on a system the context map does not understand. Run `baton context check <feature-id>`. Exit 0: the areas the feature changes are understood, and `docs/design/<feature-id>/<feature-id>-context.md` lists the explorers' notes, flows and landscape to load; pass that file to the story-drafter. Exit 2: print its blocking gaps, say "learning the areas first", and run the `build-context-map` skill with `focus <feature-id>`: it explores the areas, asks the human present what it cannot find, and ends with `GATE 0: accepted` or `GATE 0: refused`. Then run the check again. Go on only on exit 0. Still exit 2 (a question nobody could answer now, a contradiction): stop, list what is waiting and for whom, and say `baton context answer` records an answer without a session and `/stories <feature-id>` continues afterwards. Never draft around it. When `profile/branch-points.yaml` does not exist (no context map yet), stop and say to run `/onboard` and then `/build-context-map`.

## 1. Feature readiness (before drafting anything)
Run the story-drafter in FEATURE-CHECK mode: does the note give enough to write testable stories? It needs: the problem, the outcome, who the users are, the behaviours in business terms, scope and out-of-scope, feature-level acceptance, dependencies. Business rules the drafter would otherwise have to invent are gaps.

If gaps exist: write them into the feature under `## Clarification needed` as numbered questions, each saying which behaviour it unblocks, and set the feature `State: Needs Clarification`. Then ask the human with AskUserQuestion - up to 4 questions per round, options where the answer is a choice, max 3 rounds. Answers go under `## Clarifications` (dated, verbatim) in the feature file.
- Partial answers are fine: draft the stories whose questions are answered; create a placeholder story (`State: Blocked - awaiting Q<n>`, title and one-line intent only) for each behaviour still blocked, so the backlog shows what is waiting and why.
- Human absent or "not now": leave the feature in Needs Clarification with the questions, draft what is already clear, stop, and report. The questions surface in /standup.
- After 3 rounds with unanswered blocking questions: flag the feature `Blocked - refinement session needed`.

## 2. Draft (or refine)
Run the story-drafter agent on the feature file as a subagent in the foreground, with the `story-drafter` model for the full track from `baton models` (`baton models --check` first), and wait for its report before the next step.
If docs/stories/<feature-id>/ already has stories, this is a REFINEMENT: keep existing ids; never change a story whose State is Ready or later; never touch a story whose header says `Author: human` beyond adding missing header lines; add only the stories that are missing. Before drafting new ones, read the Done stories of this feature and the latest file under docs/retros/ so new stories reflect what was learned, not only the original note.

## 2a. Story branches and the first commit
For each story the drafter wrote, in id order: `git switch -c story/<feature-id>-<story-id> <default>`, `git add docs/stories/<feature-id>/<story-id>.md` (with the first story only, also the feature note and its attachments), `git commit -m "<story-id>: stories drafted (story-drafter)"`, then `git switch <default>` (the `workflow` skill says how to find the default branch). The `workflow` skill's commit-points section has the rules. A story that already has its branch (a refinement) gets the commit on that branch.

## 3. Readiness
Run the `ready` skill on every story of this feature that is in Draft or Needs Clarification - the agent's and the humans' alike. Same checklist, same clarification loop, same hand-off.

## 4. Report
If a human is present, offer the `elicitation` menu once against the drafted set (Proceed is fine). Then print, for the Product Owner: a table (story id, title, author agent|human, Jira-Type, Labels, Track, estimate, readiness score, state), every open question grouped by story, and the feature's own open clarifications. End with: "Set State: Ready on the stories you accept (or answer the /ready prompt), then /build <id> or /sprint."
Do NOT set any story to Ready yourself.
