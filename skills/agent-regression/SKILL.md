---
name: agent-regression
description: Re-run the agents on the golden set of stories and diff against the human-approved outputs, after any change to an agent prompt or skill. Use as /agent-regression [story-drafter|architect|qa|all].
disable-model-invocation: true
---
Run the agent regression for: $ARGUMENTS (an agent name, or all).

The golden set lives in docs/golden/<story-id>/: the story file, the human-approved design note, test report and security report, plus README.md listing which agents each story exercises. If docs/golden/ is empty, say so and stop - a human seeds it by copying 4-5 completed stories' artefacts there.

For each golden story and each requested agent:
1. Copy the story into a scratch folder docs/golden/_run/<date>/<story-id>/ so nothing under docs/stories or docs/design changes.
2. Run the agent as a subagent on the scratch copy, in the foreground, with the model `baton models <story-id>` gives that role (the same `profile/models.yaml` as production, so outputs compare like with like), and wait for its report before the next step.
3. Compare the new output with the approved one. Not a text diff: report (a) sections missing or added, (b) acceptance criteria or tasks that changed meaning, (c) confidence score delta, (d) any new open question, (e) diagrams present/absent.
4. Verdict per story: SAME | ACCEPTABLE DRIFT (explain) | REGRESSION (explain).

Finish with a table: story x agent x verdict, and one line: safe to keep the prompt change, or not. Never overwrite anything under docs/golden/<story-id>/ itself.
