# Kit: spring-batch-job
A Spring Batch 5 job on Spring Boot 3 (Java 21), with every baton sensor already in the build. Example job: `itemImportJob` reads a CSV of items, normalises each line, drops the invalid ones, and writes a CSV; to replace with the real job.

## What it gives
- Layout the extractors read: `adapters/batch` (job config, processor, step listener), `application/service` (the rules), `application/dto`.
- Sensors in `pom.xml`: ArchUnit (`src/test/java/.../ArchitectureTest.java`, `ProjectArchitectureTest.java`), PMD + CPD and Checkstyle (`config/sensors/`, fail `mvn verify`), PIT (`pitest-maven`, run on changed classes).
- Tests: a rules unit test, a `JobLauncherTestUtils` job test on a fixture file, including a rerun.
- Claude Code: `.claude/settings.json` (baton hooks, as `templates/settings.json`), `CLAUDE.md` importing `AGENTS.md`.
- CI: `.github/workflows/ci.yml`, the same pipeline for every change.
- `RUNBOOK.md` stub, `.gitignore`, `.mvn/settings.xml` (org mirror via `ORG_MAVEN_MIRROR`).
- Job repository on in-memory H2 so the kit runs alone; point `JOB_REPOSITORY_URL` and the driver at the org database before the first real run.

## Start a repo from it
1. Copy this folder to the new repo and `git init`.
2. Rename the package `com.example.batchjob` (folders, `package` lines, `BASE` in `ArchitectureTest.java`, `ROOT_PACKAGE` in `ci.yml`), the `artifactId`, and every `<angle bracket>` placeholder.
3. Replace the item reader, rules and writer with the real ones; keep the layer folders.
4. Copy `.claude/hooks/` from the central repo; until it is there, every hook refuses.
5. Set `ORG_MAVEN_MIRROR`, run `mvn -B verify`, push, and turn on branch protection for the default branch.
6. In the central repo, add the row to `profile/project.md` and run `/onboard`.

## What /onboard still asks
- The repo table row in the central repo's `profile/project.md`: path, purpose, build command.
- The domain words this job uses, for the naming checks.
- The test environment: its name and the variable that holds its URI; the period key if the job has one.
- Anything the extractors report as `unknown`, and the job's real runtime and schedule.

Not verified here: the kit was not compiled or run, because nothing may be downloaded outside the org mirror. Versions match `fixtures/sample-java-repo`, which is built by the baton slow tests.
