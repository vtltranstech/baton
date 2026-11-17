# Contracts - the interfaces between agents, skills, hooks and the CLI

Agents read them and never edit them. A contract that turns out wrong is raised with the framework's maintainers and changed in its own commit, with a `CHANGES.md` row.

| File | Holds |
| --- | --- |
| `cli.md` | the one CLI, every subcommand, exit codes, output files |
| `artefacts.md` | file formats agents and tools exchange: stack-detected, dependencies.yaml, aggregates.yaml, risk-zones.yaml, data-profile, wiki frontmatter, impact.json, mutation.json |
| `confidence.md` | signals, weights file, caps, policy, evidence.md layout |
| `states.md` | story states and the prerequisite artefacts `state-check` enforces |
| `graph.md` | node/edge schema, provenance, C4 projection rules |
| `ui-stories.md` | `ui` stories: the architect's UI mode, wireframe options, `screen-spec.md`, the organisation's component library and the inventory, the UX lens, gate 2a, screens of record, `baton ux` |
| `agent-enhancements.md` | agent blueprints, the outcome table, `baton build` orchestration, security last, the triage-only fix loop, systems of record, starter kits, `baton agents check` |
| `versioning.md` | central-repo story branches, commit points, the docs PR and tags, architecture stamps and changelog, the archive |
| `trace.md` | the feature trace page: inputs, provenance footer, layout, trace.json |
| `models-and-activation.md` | extractor decision (tree-sitter), conditional skill activation, model per role and the reviewer rule, the BATON rename |
| `context-map.md` | `baton context`: the five context layers, business branch points, domain.md as an index, miner drafts, coverage and per-story sufficiency, the `/ready` gate |
| `../schemas/*.json` | JSON Schemas for every `--json` output and every yaml profile file |

Paths in every contract are relative to the product's central repo (where Claude Code starts). Service repos are `../<repo>` per `profile/project.md`.
