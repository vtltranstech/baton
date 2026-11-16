---
name: sprint-review
description: Sprint review pack from evidence.md, confidence.json, QA and security reports for stories awaiting gate 3, ordered by confidence lane. Use as /sprint-review.
disable-model-invocation: true
---
Produce the sprint review pack for the project team.

First, for every feature with a story in the states below, run `baton trace <feature-id>` and print the page paths (`docs/trace/<feature-id>.html`) at the top of the pack: the page shows who decided what and what each feature taught the system.

List stories with `baton stories` (a story's files stay on its `story/<F>-<S>` branch until its docs PR merges; read them with `git show <where>:<path>`, or switch to that branch before a gate-3 commit). For every story in State In Review, QA Pass, Approved or Documented: read the story, its design note, test report, security report, change note, `-evidence.md` and `-confidence.json` (whichever exist). Never read `profile/confidence-weights.yaml`; never recompute a score. If a QA Pass story has no `-confidence.json`, run `baton confidence` and `baton evidence` first.

Order the stories by lane: `fast`, then `senior`, then `tech-lead`, then stories with no score; highest score first inside a lane. Output one section per story:
- Confidence score, lane, every cap, and the lowest three signals with their evidence (from `-evidence.md` section  Confidence)
- Title, Jira-Type, Track, estimate, created -> now (days), design confidence and review outcome
- AC table with QA result per AC
- Security verdict and any findings needing a decision
- Conformance verdict (design vs code), craft findings count, domain fidelity (rules touched / reinterpreted) - gate 3 is 'what we agreed, built the way we build, true to the business rules'
- Repos / branches touched
- One-line recommendation: Approve | Send back | Needs decision (and which open question)
Then a totals line: stories reviewed, pass, fail, blocked.

## Gate-3 prompt per lane (the human decides; the lane never approves anything)
End each QA Pass story's section with the prompt for its lane:
- **fast** (track light, score at or above the fast-lane minimum, no caps): "Senior Engineer: read `<evidence.md>`, write `## Human findings` in the test report. Tech Lead: approve on it, or send back."
- **senior**: "Senior Engineer: read the diff and reports, write `## Human findings` and a recommendation. Tech Lead: approve, or send back."
- **tech-lead** (low score, any cap, or caps that could not be evaluated): "Tech Lead: read the diff. Lowest signals: <the three, explained from their evidence>. Approve, send back, or send the design back." A track-full story adds the design revisit.

`State: Approved` is set only after a human answers; the state-gate hook needs `## Human findings` and confidence.json for it. Then, on `story/<feature-id>-<story-id>`, commit the story, the test report (Human findings) and `docs/status.md`: `<story-id>: Approved (TL)` (`workflow` skill, commit points).
