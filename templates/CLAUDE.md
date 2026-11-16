# <project name>: central repo for BATON agentic delivery

This repo holds the project profile and all product artefacts. The agents and skills are the common `baton` core. Service code lives in sibling repos listed in `profile/project.md`. Start Claude Code from THIS folder.

Before doing anything:
1. Load the `workflow` skill and the `triage` skill.
2. Read `profile/project.md`, `profile/domain.md`, `profile/stack-detected.md`, `docs/architecture/diagrams/diagrams.md` (generated architecture views). If stack-detected still says pending or `docs/architecture/workspace.dsl` is missing, run `/onboard` first.
3. Read code through the IR before opening source files: `baton ir show` (one line per unit), `baton ir show <Class | Class#method | collection:x>`, `baton ir find <words>`, and a story's pack `.baton/context/<story-id>.md` (`baton ir slice <story-id> --write`).
4. Never read `profile/confidence-weights.yaml`. Hooks refuse it.

<!-- agent-instructions -->
(Filled by /onboard)
<!-- /agent-instructions -->

Core version: see `profile/project.md` -> core.version.
