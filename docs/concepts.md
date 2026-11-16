# Concepts

**Central repo.** One per product. It holds `profile/` and `docs/`. Service repos are siblings (`../<repo>`) and receive only sensors and ArchUnit tests.

**Profile.** `profile/` holds everything project-specific; see `PROFILE.md`. Agents, skills, hooks, tools and templates are common and carry no project words.

**Story file.** `docs/stories/<F>/<S>.md`, or `docs/stories/backlog/<S>.md` (then `<F>` is `backlog`). A slug is allowed (`S-010-some-title.md`); the id is the leading `S-010`. Its `State:` line is the state of record.

**Story branch.** `story/<F>-<S>` in the central repo, from its default branch. Every step commits there with a fixed message, so the branch history says who decided what and when; it merges with the story's docs PR. Until then the story is read from its branch: `baton stories` lists every story wherever it lives.

**Track.** `light`, `full` or `spike`, derived from Jira type and labels by the `triage` skill. It sets the weight of the design note and which gates ask.

**Artefact.** Every output is a file in Git. A skill that needs a fact reads a file. Nothing is carried in chat.

**Hook.** A check Claude Code runs before a tool call. Skills and CLAUDE.md are guidance; hooks refuse. See [gates.md](gates.md).

**Confidence.** A number computed by a tool from artefacts, with weights an agent cannot read. It routes the human review at gate 3; it never approves anything. See [confidence.md](confidence.md).

**C4 model of record.** `docs/architecture/workspace.dsl`, Structurizr DSL, generated from the code by `baton c4`. When a story ships, `baton c4 --story S` stamps what it added or changed with its story and feature (`baton.story`, `baton.feature`, ...) and appends a line to `docs/architecture/CHANGELOG.md`. Tags (`baton tag S`) are the versions.

**Provenance footer.** Every Markdown artefact ends with a hidden comment naming the agent, its model, the skills and profile sections it read, and when. `baton trace F` turns them into one page per feature.

**Model per role.** `profile/models.yaml` (Tech Lead) names the model each role runs on per track; the launching skill passes it. A reviewer is never weaker than what it reviews.

**Archive.** When a feature's last story has merged, `/ship F` moves its story artefacts to `docs/archive/<F>/`. Agents never read it; `/retro` and `baton trace` do.
