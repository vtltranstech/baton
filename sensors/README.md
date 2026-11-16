# Sensors: mechanical checks that cost no tokens

| File | Enforces | Runs | How `REMEDIATION:` reaches the report |
| --- | --- | --- | --- |
| `pmd-ruleset.xml` | complexity (cyclomatic 10 / cognitive 15 / NPath 200), god class, coupling, catch-all, mutable static, field injection, logic in a controller, duplication (CPD ≥ 30 tokens). Project invariants (e.g. a period-key rule) go in `profile/sensors/pmd-extra.xml` | `mvn verify` via maven-pmd-plugin; `gradle build` via the pmd plugin | `message` on each rule; in `target/pmd.xml` (`build/reports/pmd/main.xml`) and the console. CPD output has no such line, see Limitations |
| `checkstyle.xml` | method ≤ 40 lines, file ≤ 300, params ≤ 5, nesting ≤ 2, boolean complexity ≤ 3, fan-out ≤ 20, illegal catch, generic type-name warning (Manager/Helper/Util…) | `mvn verify` via maven-checkstyle-plugin; `gradle build` via the checkstyle plugin | custom `message` per module; in `target/checkstyle-result.xml` and the console |
| `ArchitectureTest.java` | **MANDATORY in every Java repo.** Layering, no persistence types in controllers, no field injection, no slice cycles. One file for Java 17 and 21 (the same rules, run on both by the fixture's slow tests) | surefire / gradle test; report saved as `archunit.txt` | `because("REMEDIATION: …")`; in `target/surefire-reports/*ArchitectureTest*.txt` |
| (same file, best-practice rules) | stereotypes in their layer, services free of HTTP, controllers free of datastore types, no `@Transactional` in controllers, domain at the bottom, no floating-point money, private static final loggers, no `System.out`, generic exceptions, java.util.logging or Joda-Time | as above | as above |
| `ProjectArchitectureTest.java` | template with three commented examples: single implementation of a named rule, thin batch writers, no raw datastore type in services. Project rules live in the repo, added via `/standards record`; `profile/sensors/README.md` is the record of which rule exists where and why | as above | as above |
| `eslint-sensors.json` | React/TS complexity, size, depth, no `any`, no fetch in components | `npm run lint` | `no-restricted-syntax` messages; in `eslint --format json` (and on the console) |
| `new_dependency_check.py` | a dependency declared in `pom.xml`, `build.gradle(.kts)` or `package.json` that the base ref does not declare | `python3 sensors/new_dependency_check.py --repo <repo> --base <ref>`; exit 1 on a finding | printed per finding on stdout |
| `semgrep/banking.yaml` | secrets, identifiers in logs, `$where`, string-built queries | `semgrep --config sensors/semgrep/banking.yaml --error <repo>` | `message` on each rule |
| `pom-snippet.xml`, `build.gradle.kts` | how to wire PMD, Checkstyle, ArchUnit (Gradle file includes PIT) | | |
| `pitest-snippet.xml` | PIT for Maven. No `mutationThreshold`: the score is a confidence signal, not a gate | `baton mutation` | n/a |

Install once per service repo: `/onboard` detects `archunit: installed | missing` per repo and offers the install branch; otherwise the first story touching the repo lists it as task 1. Thresholds are mirrored in `../skills/standards/stack.md`; change both together, and only from an observed failure (`/standards record`).

Diff-shape sensors (lines vs estimate, new public types vs design, single-impl abstractions, new dependencies, queries without the profile's period key) are computed by `/build` after the developer runs; see the build skill. `new_dependency_check.py` is available for that step.

## Adopting ArchUnit on an existing repo
The rules in `ArchitectureTest.java` will find old violations. Do not weaken a rule or fix everything at once: wrap the failing rule in `FreezingArchRule.freeze(rule)` (`com.tngtech.archunit.library.freeze`). Existing violations are stored and only new ones fail the build. Commit the store, and let it shrink. A package layout other than `controller`, `service`, `repository` needs the layer names changed in this one file, and that change is recorded in `profile/sensors/README.md`.

## Planted-violation proof
`fixtures/sample-java-repo/violations/` and `fixtures/sample-react-repo/violations/` hold one patch per violation and a `MANIFEST.json` naming the sensor and report that must catch it. `tools/baton/tests/W6/` applies each to a temp copy and asserts the `REMEDIATION:` line (`BATON_SLOW=1` for the build-driven ones).

## Limitations
- `semgrep/banking.yaml` has been checked with Python `re` against positive and negative samples, not by the semgrep engine, which is not installed here. Regex rules also match comments.
- CPD (`cpd-check`) fails the build but its report has no `REMEDIATION:` line: the tool has no message setting.
- ESLint built-ins other than the two `no-restricted-syntax` rules (`complexity`, `max-depth`, …) keep their own messages.
- `NoLogicInController` flags every `if` in a controller, including input validation; use Bean Validation there.
