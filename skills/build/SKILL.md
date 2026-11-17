---
name: build
description: Run architect -> design review (per track) -> developer -> qa -> security for one Ready story, with fix loops; stops before gate 3. Use as /build S-010.
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: 'bash "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR}/.claude}/hooks/run-hook" commit_scope.py'
    - matcher: Bash|Write|Edit|MultiEdit
      hooks:
        - type: command
          command: 'bash "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR}/.claude}/hooks/run-hook" state_gate.py'
---
Run the build chain for one story: $ARGUMENTS (a story id such as S-010).

Read the `workflow` and `triage` skills first. Refuse to run if `profile/project.md`, `profile/domain.md`, `profile/stack-detected.md` or `docs/architecture/workspace.dsl` is missing or still says pending - say which and point to `/onboard`. `baton <cmd>` below means the CLI as the workflow skill says to call it. Read the story's `Track:` and `Labels:`. Record the start time. `baton build <story-id>` owns the order (contracts/agent-enhancements.md section 3); this skill runs the agents and asks the human. Do not skip a step. Do not ask the human anything except at the gates `baton build` prints.

## The loop
After step 0a, repeat until `baton build` prints `DONE` or stops (exit 2):
1. Run `baton build <story-id> --json`. It runs the deterministic steps itself (gate 0, `baton deps`, the gate 2 auto-pass, `baton confidence`, `baton evidence`, `baton trace`) and prints the next action.
2. Do exactly that action:
   - `agent`: run that agent as a subagent in the foreground with the model from step 0d, passing the story id and the `inputs` it lists, and nothing else as review input (a fix loop gets the triage file only). Wait for its report, make that step's commits as the sections below say, then run its `then` line (`--done <step>`).
   - `skill`: run that skill as printed (the ready skill, or build-context-map with `focus <feature-id>`), then run `baton build` again. If gate 0 still refuses after a focus run, stop and report the questions and who must answer them.
   - `gate`: ask the gate 2 question below with AskUserQuestion, the options in the order printed, then pass the answer: `baton build <story-id> --answer approve|changes|block --by TL --note "<their words>"`. Commit as section 2 says.
   - `do`: do what the text names, as the section below describes (the checks after the developer, or the UX lens of a `ui` story, section 1a), commit, then run its `then` line.
   - A `ui` story's wireframe steps (`agent` step `wireframe`, `do` step `ux-lens`, `gate` step `gate2a`, and the light track's combined gate 2): section 1a.
3. A `--done` that exits 2 names what the step did not produce: give the agent that reason and run it again once; a second refusal stops the build.
`DONE` means QA Pass with a security report current for every branch head, and the evidence written: print the summary at the end of this skill and stop before gate 3. `baton build <story-id> --status` shows the steps recorded in `docs/qa/<feature-id>/<story-id>-build.json`; `--from <step>` redoes from a step.

The sections below say how each step is done and committed.

## 0a. Check this machine
Run `baton --help`, `python3 --version`, `javac -version` and `node --version`. If `baton` is missing, or `python3` is older than 3.11, stop and say this machine has not been set up: install Python 3.11 or later as `python3`, then install the `baton` command with `pipx` as the framework quickstart says. If `javac` is missing, say Java files will be read by the simpler scanner; if `node` is missing, say React and TypeScript files will not be read; then continue. Do not install anything, and do not guess a path.

## 0. Not Ready yet?
If the story's State is Draft, Needs Clarification or Ready for PO, run the `ready` skill on it first. It loops with the human on the gaps and asks whether to set Ready. If the human does not set Ready, stop here and report - nothing is built from an unapproved story.

## 0c. Story branch
Switch to `story/<feature-id>-<story-id>` before any agent runs (create it from the default branch if `/stories` and `/ready` never did; the `workflow` skill says how to find it). After every agent and every gate below, commit what that step wrote with the fixed message from the `workflow` skill's commit-points section; the step says which. Never batch two steps into one commit.

## 0d. Models
Run `baton models <story-id>`. Launch every agent below with the model it prints for that role (the Agent call's `model` parameter), and pass the `review-lenses` and `design-review-lenses` models on to those skills for their lens subagents. Exit 2 means `profile/models.yaml` breaks the reviewer rule: say so and stop. Run it again before a fix-loop developer run: a failed QA loop or diff-shape flags escalate the developer, and the reviewers stay at least as strong. Every gate prompt below adds its pairing line ("design by <model>, reviewed by <model>; built by <model>, reviewed by <model>").

## 0b. Are the stories it depends on finished?
Run `baton deps <story-id>`. If it exits 2, stop before any agent runs. Say which stories must finish first and their State, and do not ask to work around it. Only a human can change `Depends-On:`.

If it exits 0, it prints the PR of each story this one depends on. Done only means the PR is open, so check each is merged with `gh pr view <url> --json state`. If `gh` cannot answer, ask the human with AskUserQuestion, options "Merged" and "Not merged yet". If a PR is not merged, stop and say the code is not on the default branch yet.

## 1. Architect (only if State is Ready or Design Changes Requested)
When `profile/branch-points.yaml` exists, run `baton context check <story-id>` first (gate 0 again: code merged since /ready can leave an area stale). Exit 2 with only gate-0 gaps (`not-understood`, `question`, `contradiction`, `boundary-unknown`): run the `build-context-map` skill with `focus <feature-id>`, then the check again, and go on only on exit 0. Exit 2 with any other gap (a new undefined word, a new branch point): say which and stop, pointing to /ready. The state-gate hook refuses Designed while an area the story changes is not understood for its track. Then run the architect agent; it starts from the manifest `docs/design/<feature-id>/<story-id>-context.md`, and the design lenses load the same list. It ends with `DESIGN READY FOR REVIEW: <path> - confidence NN%`. Re-read the story's `Track:` afterwards - the architect may have escalated it.
Commit twice: first the design note, change spec, `<story-id>.dsl`, `<story-id>-diagrams/`, the story and `docs/status.md` as `<story-id>: design (architect, NN%)` (a spike: `<story-id>-findings.md` as `<story-id>: findings (spike)`); then `<story-id>-reviews/` as `<story-id>: design lenses (<n> blocking)`, n = lenses whose verdict was blocking before fold-in. No reviews folder (a light note with the rubric walker only): skip the second commit.

## 1a. A `ui` story: wireframe, UX lens, gate 2a (contracts/ui-stories.md)
`baton build` runs these before the technical design; the State stays Ready.
- **`agent` step `wireframe`:** run the architect with the inputs printed and tell it: "UI mode for <story-id>", plus the text (it carries the PO's or the check's reasons on a redo). It writes `docs/design/<feature-id>/<story-id>-wireframe/`. Commit it as `<story-id>: wireframe (architect, <n> options)`, then `--done wireframe`. `baton build` runs `baton ux check` itself; a failure comes back as the same step with the problems.
- **`do` step `ux-lens`:** run the UX lens of the `design-review-lenses` skill (lens 6) with the `design-lenses` model. Commit `<story-id>-reviews/ux.md` as `<story-id>: UX lens (<verdict>, <n> high)`, then `--done ux-lens`.
- **`gate` step `gate2a`:** run `baton ux show <story-id> --open` so the PO sees the options side by side (the page also shows each option's rationale, the UX lens and the check). Then ask ONE question with AskUserQuestion:

  "Wireframes for <story-id> are ready: <page path>. Recommended: Option <n> (<one line from options.md>). UX lens: <verdict>, <n> HIGH. Which option do you approve?"

  Options in the printed order: each option (the recommended one first, carrying "(Recommended)"), "Changes" (the PO says what to change; at most 2 rounds), "Block". Ask the PO to mark each UX-lens finding `agree` or `disagree` in their answer, and write those into the `PO` cells of `ux.md`. Pass the answer: `baton build <story-id> --answer option-<n>|changes|block --by PO --note "<their words>"`; when `ui.designer` names someone, the note says whether they agreed. Commit the story, `approved.html` and `ux.md` as `<story-id>: gate 2a option <n> (PO)`, `<story-id>: wireframe changes requested (PO, round <n>)` or `<story-id>: blocked (PO)`.
- **Light track:** one delta wireframe and no UX lens. The architect then writes the design as usual, and gate 2 is one question for the PO and the Tech Lead together, printed by `baton build` with options "approve (wireframe + design)", "changes", "block": show the delta `option-1.html` and the design note, and pass `--by PO+TL`. There is no auto-pass for a `ui` story.

## 2. HUMAN GATE 2 - Design review, per track
Read the design note's Confidence section. `baton build` applies the two auto-pass rules itself (it writes `## Design review` and the State) and sends a full-track design back when a pattern-ledger Verification cell names no test or ArchUnit rule; you ask only when it prints a `gate` action.

- **Track light, label `hotfix`:** no question. Write `## Design review` into the story: "auto-passed (hotfix), confidence NN%". Set `State: Design Approved`. Continue.
- **Track light, confidence >= `track.auto-pass.confidence` (profile/project.md, default 80):** no question. Write `## Design review`: "auto-passed (light track, confidence NN%) - reviewer may still open <path>". Set `State: Design Approved`. Continue.
- **Track light, confidence < 80**, **track full**, **track spike**, or any label in `new-api`, `data-model`, `batch-job` or `profile/project.md` -> `jira.labels.extra`: ASK, using the AskUserQuestion tool, ONE question:

  "Design for <story-id> (<track>) is ready at <path>, confidence NN%. <one-line approach>. Design by <model>, reviewed by <model>. Reviewer should check: <bullets from the Confidence section>. How do you want to proceed?"

  Options, in this order:
  1. "Approve design" - "(Recommended)" ONLY if confidence >= 80 and no mandatory-review label is present. Description: "Sets State: Design Approved and continues to developer."
  2. "Request changes" - Description: "Tell me what to change; the architect revises and I ask again (max 2 rounds)."
  3. "Block this story" - Description: "Sets State: Blocked with your reason; nothing is built."
  If confidence < 80, option 2 is first and carries "(Recommended)".

  On Approve: write `## Design review` (date, reviewer human, Approved, confidence NN%), set `State: Design Approved`, continue.
  On Request changes: offer the `elicitation` menu against the design note (the human may pick a method or type free text); append the outcome under `## Design review` as "Changes requested: ...", set `State: Design Changes Requested`, re-run the architect with the comments, bump Revision, ask again. After the second round, if still not approved, set `State: Blocked` and stop.
  On Block: set `State: Blocked`, record the reason, stop and report.

Always append one row to the `## Calibration` table in docs/metrics.md (columns per the `doc-style` skill): story, track, confidence, review outcome (auto-pass | approved | changes | blocked), rounds.
Then commit the story, `docs/status.md` and `docs/metrics.md`: `<story-id>: design approved (TL)`, `<story-id>: design changes requested (TL, round <n>)` or `<story-id>: auto-passed (light, NN%)`. A revised design after changes gets its own design and lenses commits again. A Block is committed as `<story-id>: blocked (TL)`.

- **Spike:** after the human accepts the findings, run the documentation agent in spike mode so `docs/changes/<feature-id>/<story-id>-change-note.md` exists (the state-gate hook requires it), set `State: Documented` and stop - no developer, qa or security. Say that the findings need the documentation agent (`/ship`) if an ADR or domain-context change is still open.

## 3. Developer (only if State is Design Approved)
When the developer returns, commit the story (Dev summary, Rule ledger, State), `docs/status.md` and `docs/qa/<feature-id>/<story-id>-sensors/`: `<story-id>: build (developer) - sensors green` (or `red`).
After the developer returns, compute the diff-shape sensors on the branch(es) and write `docs/qa/<feature-id>/<story-id>-diff-shape.md`:
- lines added / deleted vs Estimate (thresholds `estimate.lines.S` / `.M` in `profile/project.md`; over = flag)
- new public types in the diff vs classes in the design's pattern ledger (extra = flag)
- single-implementation abstractions introduced (interface with one impl, abstract class with one subclass, generic with one type use) = YAGNI count
- new dependencies in any pom.xml / package.json (any = flag)
- queries without the period/partition key named in `profile/project.md`, if any (grep `Query(`, `find(`, `aggregate(`, `createQuery(`, `@Query` in the diff) (any = flag)
- sensor reports present (PMD / Checkstyle / ArchUnit / ESLint) and green? (absent or red = flag)
Flags do not stop the chain; they are handed to the qa agent (which hands them to the craft lens) and recorded in metrics.

Write the same facts as `docs/qa/<feature-id>/<story-id>-diff-shape.json` beside the `.md`; `baton confidence` reads it. Only facts from `git diff` and the build files; a field you cannot establish is left out, and the tool then scores it 0 and lists it as missing:
```json
{ "story": "S-010", "sensorLoops": 1, "newDependencies": ["group:artifact:1.2"], "breakingContract": ["GET /x removed"],
  "writesCollections": ["orders"], "yagniCount": 0,
  "repos": [ { "repo": "<repo>", "branch": "feature/<feature-id>-<story-id>", "commits": 3, "linesAdded": 120, "linesDeleted": 10,
               "files": ["<repo-relative path>"] } ] }
```
`sensorLoops` = the `Sensor loops:` value in the story's `## Dev summary`. `breakingContract` = endpoint signatures or DTO fields removed or changed in the diff; `writesCollections` = collections the changed code writes.

Then, when the subcommands exist, run the blast-radius and mutation tools from this central repo. A subcommand that says `not built yet`, or fails, is recorded as not run; never invent the file:
- One repo touched: `baton impact --repo <repo> --diff <default>...HEAD --out docs/qa/<feature-id>/<story-id>-impact.json` and `baton mutation --repo <repo> --diff <default>...HEAD --out docs/qa/<feature-id>/<story-id>-mutation.json`.
- Several repos touched: the same per repo, with `--out docs/qa/<feature-id>/<story-id>-impact-<repo>.json` and `...-mutation-<repo>.json`. `baton confidence` adds the impacted repos across the files, takes the lowest mutation score, and scores 0 when a repo in `-diff-shape.json` has no file.
- Not run: write `{"notRun": true, "reason": "<why>"}` to the same path, so evidence.md states it.

Then draw what was built: `baton diagram story <story-id> --diff <default>` (each repo's working tree on the story branch against its default branch). It writes `docs/qa/<feature-id>/<story-id>-as-built/` with the same diagrams as the design, from the code that now exists, plus a **Design conformance** table: methods built but not in the change spec, and spec items not built. Hand both lists to the qa agent and the conformance lens; an undeclared change is the developer's to explain under `## Deviations` in the design note, never something to hide by editing the spec after the fact.
Then run `baton risk <story-id>`. It writes `docs/qa/<feature-id>/<story-id>-risk.json` from the design's touch points and the diff: tier low, medium or high, with the reasons, and the review lenses QA runs (low: conformance and verification-gap, plus domain fidelity when the design names a rule under Rules touched; medium and high: all five). It is computed, never chosen: do not edit it, and a story whose diff grew past its design comes out higher. The security review and every gate run whatever the tier.
Commit `-diff-shape.md`, `-diff-shape.json`, `-impact*.json`, `-mutation*.json`, `-as-built/` and `-risk.json` when it exists: `<story-id>: diff shape, impact, mutation`.

## 4. QA (only if State is In Review)
When qa returns, commit the test report, `-lens-*.md`, `-triage.md`, the story and `docs/status.md`: `<story-id>: QA PASS`, or `<story-id>: QA FAIL loop <n>` (n = 1 for the first failure).
## 5. Security (only if State is In Review or QA Pass)
When security returns, commit the security report and the story: `<story-id>: security <verdict>` (CLEAR, FINDINGS or BLOCKED).
## 6. Fix loop
If qa wrote QA Fail, `baton build` runs the developer again with `docs/qa/<feature-id>/<story-id>-triage.md` as its only review input (never the lens files or the raw sensor reports); after a security BLOCKED, with the security report. Then the checks, qa and security again, each with its commit as above. At most twice; on the third failure it stops for the Senior Engineer. Security always runs last: any commit after its report makes `baton build` run it again, and the state-gate hook refuses Approved until it has.

Stop when the story is QA Pass with a security verdict of CLEAR or FINDINGS, or when any agent sets State to Blocked.

## 6a. Confidence and evidence (when the story is QA Pass)
Run `baton confidence <story-id>`, then `baton evidence <story-id>`. They write `docs/qa/<feature-id>/<story-id>-confidence.json` and `-evidence.md`; commit both: `<story-id>: confidence <score> <lane>`. Never compute, edit or estimate the score yourself and never read `profile/confidence-weights.yaml`. Exit 2 means the Senior Engineer's weights file is unusable: say so and stop; the story waits. The score is information for humans, never a gate by itself.
Do NOT set Approved (gate 3) - that is a human gate at /sprint-review.

Finish by appending to the `## Build` table in docs/metrics.md (columns per the `doc-style` skill): story, track, wall-clock minutes (start to now), tokens if the session reports them, loops, design rounds, impl model (the developer's, from `baton models`), review model (the review lenses'), and the sensor columns (lines added, YAGNI count, forbidden-pattern hits, complexity violations, generic names, principles invalid/not-applied, conformance verdict). Commit it on the story branch with the last step's message (amending is not allowed, so it is a separate commit with the same message). Then print: story id, track, final State, design confidence, review outcome, QA verdict, security verdict, confidence score and lane, loops used, every open question raised.
