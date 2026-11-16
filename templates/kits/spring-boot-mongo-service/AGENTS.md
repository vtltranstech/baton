# <service name>: agent instructions
<one line: what this service owns>. Spring Boot 3, Java 21, MongoDB. Started from the baton `spring-boot-mongo-service` kit. Work is driven from the central repo `<central repo>`; its `profile/` is the source of truth for domain words, the test environment and the period key.

## Build and verify
| What | Command | Report |
| --- | --- | --- |
| Build | `mvn -B compile` | console |
| Unit tests + ArchUnit + PMD + Checkstyle | `mvn -B verify` | `target/surefire-reports/`, `target/pmd.xml`, `target/cpd.xml`, `target/checkstyle-result.xml` |
| ArchUnit only | `mvn -B test -Dtest='*ArchitectureTest'` | `target/surefire-reports/*ArchitectureTest.txt` |
| PIT on changed classes | `baton mutation --repo <repo> --diff <base ref>` from the central repo | `target/pit-reports/mutations.xml` |
| Run locally | `MONGODB_URI=<test environment uri> mvn spring-boot:run` | `/actuator/health` |

Maven resolves through the org mirror only (`.mvn/settings.xml`, `ORG_MAVEN_MIRROR`). Do not add a repository, a plugin repository or a wrapper that downloads from outside the org.

## Layout
- `adapters/controller`: REST controllers and the problem-detail mapping. Validate, call one service method, return a DTO.
- `application/service`: business rules and transactions, one service per aggregate.
- `application/port`: interfaces the services call; `adapters/repository` implements them over Spring Data Mongo.
- `application/dto`: API records. `domain/document`: Mongo documents, which never leave the service layer.
- `config/sensors/`: PMD and Checkstyle rules, copies of the baton `sensors/` files. `src/test/.../ArchitectureTest.java`: the core ArchUnit rules; `ProjectArchitectureTest.java`: this repo's own rules.

## Rules
- A red sensor is fixed in the code. Never edit `config/sensors/`, `ArchitectureTest.java` or a threshold to get green; a rule believed wrong goes to `/standards record` in the central repo.
- New project rules go in `ProjectArchitectureTest.java` only through `/standards record`.
- Constructor injection only; no field `@Autowired`.
- Persistence types stay behind the port: map to a DTO record at the boundary.
- Mongo: no `$where`, no string-built filter, no raw `org.bson.Document` in services; a new query shape comes with an index. The natural key is an indexed field, never `id`.
- Money is `BigDecimal`, never `double` or `float`.
- No client or account identifier and no amount in a log line at INFO or above.
- No test reaches a shared environment; the only environment is `<test environment name>` from the central profile.
- A new dependency is a design change: name it in the design note before adding it to `pom.xml`.
- CI runs the same pipeline for every change (`.github/workflows/ci.yml`). Do not add a skip flag, a condition or a separate lane.
- Do not commit to the default branch; the hooks in `.claude/settings.json` refuse it.

## Known pitfalls
(Filled by /onboard and /onboard record, with evidence.)
