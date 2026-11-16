# The project profile — what a project must provide

Folder `profile/` in the product's central repo. The core refuses to run `/build` if `project.md`, `domain.md`, `stack-detected.md` or `docs/architecture/workspace.dsl` is missing or still says pending.

| File | Who writes it | Holds |
| --- | --- | --- |
| `project.md` | humans, once | non-derivable values: project name, test environment name and URI variable, period/partition key if any, Jira key/site/extra labels, hotfix policy, auto-pass confidence, size thresholds, core.version; the repo table (path, purpose, build); domain words; personas |
| `domain.md` | Product Owner + Tech Lead, maintained | business rules, open decisions (agents must not resolve), invariants enforced in code, severity hints for reviewers, security specifics, data-check patterns, external systems (for the C4 model) |
| `stack-detected.md` | `baton extract-stack` via `/onboard` (generated) | per repo: build tool and commands, Java, Spring Boot, Batch, datastore, messaging, web, UI, package root, layout, `archunit` / `pitest` installed or missing, build-file hash. Re-verified by the architect every run. |
| `dependencies.yaml` | `baton extract` (generated) | every collection / REST / topic / queue / file / job edge with provenance (W2) |
| `aggregates.yaml` | seeded by `baton extract`, confirmed by the Tech Lead | aggregate roots, members, references |
| `risk-zones.yaml` | seeded, confirmed by the Tech Lead | path globs where the gate-3 confidence is capped |
| `confidence-weights.yaml` | Senior Engineer | signal weights, caps, policy thresholds — agents never read it (hook) |
| `sensors/README.md` (+ `pmd-extra.xml`) | Senior Engineer via `/standards record` | the RECORD of project ArchUnit/PMD rules; the code lives in the service repos |

`docs/architecture/workspace.dsl` is the C4 model of record (Structurizr DSL): written by `/onboard`, promoted per story by the documentation agent. Everything else — stories, designs, reports, metrics, golden set, retros, wiki, data profiles — lives under the project's `docs/`.
