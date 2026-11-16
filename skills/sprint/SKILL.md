---
name: sprint
description: Run /build for every Ready story in docs/status.md, one at a time. Use as /sprint.
disable-model-invocation: true
---
Run the build chain for every story currently in State Ready.

Read docs/status.md, list stories with `baton stories` (it includes those on their `story/<F>-<S>` branch) and run `baton deps` for the order, dependencies first. List the Ready stories (stories in Draft / Needs Clarification / Ready for PO are listed separately as 'not yet ready - run /ready'; stories that `baton deps` shows waiting are listed separately as 'waiting on S-xxx', and are not built in this run). Gate 0 applies to each story through /build: a story whose areas are no longer understood is learnt first (`/build-context-map focus <feature-id>`); one still refused after that is listed as 'waiting on the context map' with its questions and is not built in this run. For each remaining story, in that order, run the /build chain (architect -> HUMAN design review -> developer -> qa -> security, with up to two fix loops) one story at a time, never in parallel. The design review question is asked for every story; do not batch or skip it. Do not set Approved. At the end print a table: story, final State, QA verdict, security verdict, loops, open questions count. Then say: "Ready for sprint review - run /sprint-review."
