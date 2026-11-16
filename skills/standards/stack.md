# House rules - Java / Spring / React (core; binding for every project on this framework)
Versions come from `profile/stack-detected.md` (detected from the build files, re-verified by the architect). Project invariants (business rules enforced in code) come from `profile/domain.md` section  Invariants. This file holds only what is common to all our Java/React projects.

## Versions
- Java: the version in `profile/stack-detected.md`. Use language features UP TO that version and no further. (17: records, sealed types, switch pattern matching, text blocks. 21 adds virtual threads, record patterns, sequenced collections, unnamed variables - not before 21.) A feature above the pinned version is a HIGH craft finding.
- Spring Boot 3.x (Jakarta namespace). Spring Batch 5 where detected. Build and test with the command in `profile/stack-detected.md`; tests must pass on the build, not only in the IDE.

## Layering (Spring services)
- Controller -> Service -> Repository. Controllers hold no business logic; they validate, call one service method, map to a response DTO.
- Services own business rules and transactions. One service per aggregate. No "Util" / "Helper" / "Manager" service that grows without bound.
- Repositories per aggregate/collection/table. Custom queries in a `*RepositoryCustom` + Impl, never string-built filters or string-built JPQL/SQL.
- Persistence types (Mongo documents, JPA entities) never cross the API boundary: map to DTOs (records). The persistence shape is the data model; the API shape is the view model.
- Constructor injection only (no field `@Autowired`). Beans immutable after construction.
- A business rule the domain file names lives in ONE place; every reader calls it. No second implementation of a named rule (the profile lists which, e.g. a resolver).

## Spring Batch (when detected)
- Reader / Processor / Writer strictly separated; processors pure functions of one item; writers batch.
- Each step idempotent per its natural key / period key (named in `profile/project.md`): re-running a step must not duplicate rows or documents (upsert on the natural key).
- Step listeners record counts in -> out -> written; reconciliation reads them.
- No business decision in a writer. No cross-step state except through the JobExecutionContext or the store itself.

## Data (datastore-specific rules apply by what `profile/stack-detected.md` says)
- Natural keys are explicit, indexed fields; a surrogate `_id`/`id` is never a business key.
- The project's period / partition key (if `profile/project.md` names one) is on every row/document and in every query.
- Mongo: no `$where`, no string-built filters, no raw `org.bson.Document` in service code; new query shapes come with an index.
- JPA: no native SQL by string concatenation; `@Transactional` at the service boundary only; no lazy-loading across the API boundary; N+1 is a finding.
- Writes to any store another system still masters are forbidden outside the designated integration job (the profile names it).

## API
- REST, versioned path (`/api/v1/...`), problem-detail errors (RFC 9457), pagination on any list.
- Every endpoint checks entitlement for the resource requested before any data access.
- Contract first: the design's sequence diagram names request and response DTOs; a changed contract is a design change.

## React
- Functional components + hooks; components render, hooks hold state and effects, an API client module calls the backend. No fetch inside a component body.
- Server state via the project's query client (TanStack Query unless the profile says otherwise); UI state local; no global store unless two distant screens share it.
- Typed props and API types in `types/`; no `any`.
- Lists/trees and detail panes are separate components with their own data hooks; selection changes a query key, not a prop chain.

## Architecture tests (mandatory - ArchUnit)
- Every Java repo carries the core `ArchitectureTest` (from the `standards` skill's `sensors/`) and the `archunit-junit5` dependency; it runs in `mvn verify` / `gradle build` with the unit tests. `/onboard` records `archunit: installed | missing` per repo in `profile/stack-detected.md`; a story that touches a `missing` repo has "install the core sensors" as its first task.
- No story reaches `In Review` without a green ArchUnit run saved to `docs/qa/<feature-id>/<story-id>-sensors/archunit.txt` (the state-gate hook refuses the state; the craft lens and QA FAIL on a missing or red report).
- Project-specific rules (a single-implementation rule, a thin-writer rule, a period-key rule) live in the repo as `ProjectArchitectureTest`, added only through `/standards record` from an observed failure; `profile/sensors/README.md` records each rule, its repo, and the incident that earned it. The profile holds the record, the repo holds the code.
- An ArchUnit failure is fixed in the code, never by narrowing the rule or freezing the violation; a rule believed wrong goes to `/standards record`.

## Testing
- Unit tests per service and per named rule, with fixtures, named after the AC (`ac1_...`). Slice tests (`@DataMongoTest` / `@DataJpaTest`, `@WebMvcTest`) over full context where possible; one full-context smoke test per service.
- Batch steps tested with `JobLauncherTestUtils` on a fixture period.
- No test hits the shared test environment; environment data checks are QA scripts, not tests.
- Test names say the behaviour, not the method.

## Logging & errors
- No client or account identifiers and no money amounts at INFO or above (the profile lists the field names); correlation id on every log line.
- Domain exceptions mapped to problem details at the edge; never swallow; never log-and-rethrow.

## Forbidden patterns (the craft lens flags these HIGH)
- Business logic in a controller, batch writer, or static util.
- A second implementation of a rule the profile says lives in one place.
- String-built queries (`$where`, concatenated filters, concatenated JPQL/SQL); raw `Document` / raw SQL in service code.
- Field injection; mutable singletons; `static` mutable state.
- Language features above the pinned Java version.
- Catch-all `catch (Exception e)` that continues.
- A class over ~300 lines or a method over ~40 without a reason recorded in the design note.
- Any write outside the test environment named in `profile/project.md`.

## Same quality bar for agents and humans
- **One pipeline:** an agent branch runs exactly the human CI pipeline: build, unit tests, ArchUnit, PMD, Checkstyle, mutation on changed classes, ESLint and typecheck for UI. No agent lane, no skipped stage.
- **Central repo CI:** on every PR, `baton state-check`, `baton agents check` (core repo), and `baton confidence` with `evidence.md` posted as the PR description (`templates/ci/central-ci.yml`).
- **Branch protection:** on the default branch of every repo, the central repo included. It is the floor under the hooks.
- **Security last:** any code change after the security report invalidates it. `baton build` runs security again; the state-gate hook refuses Approved while the report's `Heads:` differ from a branch head.
