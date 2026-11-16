# Starter kits: a new service repo with the sensors already in the build

| Kit | Pick it for | Build |
| --- | --- | --- |
| `spring-boot-mongo-service/` | a REST service that owns a MongoDB collection | `mvn -B verify` |
| `spring-batch-job/` | a scheduled or rerunnable job: read, decide per item, write | `mvn -B verify` |
| `react-ts-ui/` | a browser UI over one or more services | `npm ci && npm run lint && npm run typecheck && npm test` |

A service that both serves REST and runs a job starts from `spring-boot-mongo-service` and takes `adapters/batch` from `spring-batch-job`.

Every kit has: the sensors wired in the build (Java: ArchUnit `ArchitectureTest`, PMD + CPD, Checkstyle, PIT; React: ESLint with `sensors/eslint-sensors.json`, TypeScript strict, `npm test`), `.claude/settings.json` with the baton hooks, `CLAUDE.md` importing `AGENTS.md`, `.github/workflows/ci.yml` running the same pipeline for every change, `RUNBOOK.md`, `README.md`, `.gitignore`, and an org-mirror placeholder (`.mvn/settings.xml` with `${env.ORG_MAVEN_MIRROR}`, `.npmrc` with `${ORG_NPM_REGISTRY}`). Nothing is fetched from outside the org.

## How a repo is born from a kit
1. Copy the kit folder to the new repo.
2. Rename the package (`com.example.mongoservice`, `com.example.batchjob`) or the app name, and fill every `<angle bracket>` placeholder.
3. Add the repo's row to the central repo's `profile/project.md` (path, purpose, build command).
4. Run `/onboard` in the central repo: it reads the new repo, asks for the domain words and the test environment, and writes the agent-instructions block.

The sensor files in each kit are copies of `sensors/`; when a threshold changes there, change the kits in the same commit.

## Existing repos
`/onboard` on an existing repo compares it with the nearest kit and drafts the alignment for the Tech Lead: the missing sensors (ArchUnit, PMD, Checkstyle, PIT, ESLint rules), the CI stages that differ from the kit's `ci.yml`, and the agent instructions (`AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`). Nothing is applied without the Tech Lead's approval; old violations are frozen, not fixed at once (`sensors/README.md`).

## Limitations
The kits have not been compiled, installed or run here: no download from outside the org is allowed. Versions and sensor wiring match `fixtures/sample-java-repo` and `fixtures/sample-react-repo`.
