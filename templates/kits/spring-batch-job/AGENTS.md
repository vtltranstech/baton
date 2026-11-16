# <job name>: agent instructions
<one line: what this job reads, decides and writes, and when it runs>. Spring Boot 3, Spring Batch 5, Java 21. Started from the baton `spring-batch-job` kit. Work is driven from the central repo `<central repo>`; its `profile/` is the source of truth for domain words, the test environment and the period key.

## Build and verify
| What | Command | Report |
| --- | --- | --- |
| Build | `mvn -B compile` | console |
| Unit tests + job test + ArchUnit + PMD + Checkstyle | `mvn -B verify` | `target/surefire-reports/`, `target/pmd.xml`, `target/cpd.xml`, `target/checkstyle-result.xml` |
| ArchUnit only | `mvn -B test -Dtest='*ArchitectureTest'` | `target/surefire-reports/*ArchitectureTest.txt` |
| PIT on changed classes | `baton mutation --repo <repo> --diff <base ref>` from the central repo | `target/pit-reports/mutations.xml` |
| Run once locally | `ITEMS_INBOUND_FILE=<file> ITEMS_OUTBOUND_FILE=<file> mvn spring-boot:run` | console, exit code |

Maven resolves through the org mirror only (`.mvn/settings.xml`, `ORG_MAVEN_MIRROR`). Do not add a repository, a plugin repository or a wrapper that downloads from outside the org.

## Layout
- `adapters/batch`: the job config (reader, step, writer, job), the processor, the step listener.
- `application/service`: the job's business rules, once; the processor calls them.
- `application/dto`: the item records.
- `config/sensors/`: PMD and Checkstyle rules, copies of the baton `sensors/` files. `src/test/.../ArchitectureTest.java`: the core ArchUnit rules; `ProjectArchitectureTest.java`: this repo's own rules (the thin-writer example is there, commented).

## Rules
- A red sensor is fixed in the code. Never edit `config/sensors/`, `ArchitectureTest.java` or a threshold to get green; a rule believed wrong goes to `/standards record` in the central repo.
- Reader, processor and writer stay separate. A processor is a pure function of one item; a writer only writes its chunk and takes no business decision.
- Every step is idempotent on its natural key or the period key: a rerun must not duplicate a row, a document or a line.
- No state across steps except through the JobExecutionContext or the store itself.
- The step listener records counts; it never logs an identifier or an amount.
- Test a step with `JobLauncherTestUtils` on a fixture file; no test reaches a shared environment.
- Money is `BigDecimal`, never `double` or `float`.
- A new dependency is a design change: name it in the design note before adding it to `pom.xml`.
- CI runs the same pipeline for every change (`.github/workflows/ci.yml`). Do not add a skip flag, a condition or a separate lane.
- Do not commit to the default branch; the hooks in `.claude/settings.json` refuse it.

## Known pitfalls
(Filled by /onboard and /onboard record, with evidence.)
