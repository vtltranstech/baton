# FAQ

Seed it from the first month's questions: `docs/context/questions.md` and the stories' `## Open questions`. One question per row, the answer in one line, the file that settles it.

| Question | Answer | Where |
| --- | --- | --- |
| Why did /stories stop before drafting? | Gate 0: an area the feature changes is not understood yet. | `baton context check <F>`; `docs/guide.md` "When to run what" |
| Who answers a context question? | The person named on it, PO or TL, with `baton context answer`. | `docs/context/questions.md` |
| Can the Tech Lead let one story past gate 0? | Yes, with a `Gate-0-Override: <reason> (TL, date)` line in the story, written by hand. | `contracts/agent-enhancements.md` section 3 |
| Why did security run twice? | A commit landed after its report; security runs last. | the report's `Heads:` line; `baton build <S> --status` |
| Which branch is my story on, and is it pushed? | `baton board`, or `baton board --story <S>`. | `contracts/cli.md` |
| Where do agents' instructions live? | `agents/*.md`; each opens with its Blueprint. | `baton agents check` |
