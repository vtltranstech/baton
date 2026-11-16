# Kit: spring-boot-mongo-service
A Spring Boot 3 REST service over MongoDB (Java 21), with every baton sensor already in the build. Example resource: `items` (`GET /api/v1/items/{itemKey}`, `PUT /api/v1/items`), to replace with the real aggregate.

## What it gives
- Layout the extractors read: `adapters/controller`, `application/service`, `application/port`, `adapters/repository` (Spring Data Mongo), `application/dto`, `domain/document`.
- Sensors in `pom.xml`: ArchUnit (`src/test/java/.../ArchitectureTest.java`, `ProjectArchitectureTest.java`), PMD + CPD and Checkstyle (`config/sensors/`, fail `mvn verify`), PIT (`pitest-maven`, run on changed classes).
- Tests: a service unit test, a `@WebMvcTest` controller slice.
- Claude Code: `.claude/settings.json` (baton hooks, as `templates/settings.json`), `CLAUDE.md` importing `AGENTS.md`.
- CI: `.github/workflows/ci.yml`, the same pipeline for every change.
- `RUNBOOK.md` stub, `.gitignore`, `.mvn/settings.xml` (org mirror via `ORG_MAVEN_MIRROR`).

## Start a repo from it
1. Copy this folder to the new repo and `git init`.
2. Rename the package `com.example.mongoservice` (folders, `package` lines, `BASE` in `ArchitectureTest.java`, `ROOT_PACKAGE` in `ci.yml`), the `artifactId`, and every `<angle bracket>` placeholder.
3. Replace `items` with the real aggregate; keep the layer folders.
4. Copy `.claude/hooks/` from the central repo; until it is there, every hook refuses.
5. Set `ORG_MAVEN_MIRROR`, run `mvn -B verify`, push, and turn on branch protection for the default branch.
6. In the central repo, add the row to `profile/project.md` and run `/onboard`.

## What /onboard still asks
- The repo table row in the central repo's `profile/project.md`: path, purpose, build command.
- The domain words this service uses, for the naming checks.
- The test environment: its name and the variable that holds its URI.
- Anything the extractors report as `unknown`.

Not verified here: the kit was not compiled or run, because nothing may be downloaded outside the org mirror. Versions match `fixtures/sample-java-repo`, which is built by the baton slow tests.
