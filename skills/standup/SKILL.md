---
name: standup
description: Daily standup summary from docs/status.md and every story's open questions. Use as /standup.
disable-model-invocation: true
---
Produce the daily standup summary for the project team.

Read docs/status.md and list every story with `baton stories` (it also finds the stories that live only on their `story/<F>-<S>` branch until their docs PR merges; read one with `git show <where>:<path>`). Output, in this order, nothing else:
1. Stories by State (one line each: id, title, agent, days in state).
2. Blockers: every non-empty "## Open questions" across stories, every feature in Needs Clarification with its numbered questions, every story waiting on an unfinished `Depends-On:` story (from `baton deps`), and every story in Ready for PO awaiting gate 1 - as a checklist a human can answer.
3. Loops: any story with Loops >= 2.
4. What the agents will do next if no human input arrives.
5. Features: one line each, with done/total stories and the trace page `docs/trace/<feature-id>.html` when it exists (else "no trace yet: baton trace <feature-id>").
6. Context: the readiness lines of `baton context score` as printed, the domain score per story from `baton context trend`, and the questions from `baton context questions` (gate 0: who must answer what, oldest first; an OVERDUE one is the Tech Lead's to chase), each answerable with `baton context answer` (skip when `profile/branch-points.yaml` is absent; say "no context map yet: /onboard").
7. Branches: from `baton board`, every story whose next move is a push, a pull or a tag, with that move.
Keep it under 30 lines.
