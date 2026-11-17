# S-nnn <title: a result, not an activity>
Feature: <F-xxx or none>
Author: human
Jira-Type: <Bug | Task | Story | Spike>   (leave blank and /ready will propose)
Labels:
Depends-On: <story ids that must be Done first, separated by commas, or none>
State: Draft

## Story
As a <role>, I want <capability> so that <outcome>.

## Acceptance criteria
- AC1: Given <state>, when <action>, then <observable result>.

## Capacity   (API, file, batch, messaging or a new collection; delete rows that do not apply; `unknown` is allowed, with who will find out)
- API: peak requests/second: ... - p95 target: ... - largest payload: ...
- File or batch: largest size and records: ... - how often: ... - must finish within: ... - resume after failure: yes/no
- Messaging: peak messages/second: ... - order matters: yes/no
- Data: documents now and growth per year: ...

## Open questions
- (anything you already know is unclear)

<!-- A story that adds or changes a screen carries the label `ui`: /build writes `## Wireframe approval` here at gate 2a (contracts/ui-stories.md). -->

<!-- Save under docs/stories/<F-xxx>/ to attach to a feature, or docs/stories/backlog/ for ad hoc. Then run: /ready S-nnn -->
