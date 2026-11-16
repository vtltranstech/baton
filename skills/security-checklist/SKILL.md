---
name: security-checklist
description: The security agent's checklist and severity rubric for Java/Spring/React diffs in a regulated bank - secrets, data exposure, injection, entitlement, dependencies, environment boundaries - plus the project's specifics from profile/domain.md section  Security specifics. Use on every In Review story.
---
# Security review checklist

Start with the built-in `/security-review` on the branch diff, then apply this list, then the project items in `profile/domain.md` section  Security specifics.

## Checklist (grep targets in brackets)
1. **Secrets** - connection strings, passwords, tokens in code, YAML, tests, fixtures. [`://`, `password`, `secret`, `token`, `Bearer`]
2. **Client data in logs** - the identifier and amount fields the profile names, logged at INFO or above or in exception messages. [`log.info(`, `log.warn(`, `getMessage()` with ids]
3. **Injection** - string-built queries: Mongo `$where`, `$function`, string-concatenated filters, `Document.parse(` on input; SQL/JPQL by concatenation; unparameterised native queries.
4. **Entitlement** - every endpoint checks the caller may access the resource requested, before data access. [`@GetMapping`, `@PostMapping` without an entitlement check in the call path]
5. **Input validation** - path/query/body params validated for type and length; batch readers reject malformed rows rather than skipping silently.
6. **Environment boundary** - any URI, profile or config that is not the test environment in `profile/project.md`; any write to a store another system masters outside the designated job. [`prod`, `uat`, `.properties`/`.yml` changes]
7. **Dependencies** - new or bumped artifacts in pom/gradle/package.json: name, version, licence, known CVEs (`mvn org.owasp:dependency-check-maven:check` / `npm audit` if available, else say "not scanned").
8. **Integration contracts** - any change to an outbound file format, event schema or mastering rule the profile names is flagged for business review even if technically fine.
9. **Tests** - fixtures must not contain real client names, account numbers or real identifiers.
10. **Frontend** - no secrets in the bundle; no `dangerouslySetInnerHTML` with untrusted input; auth tokens not in localStorage unless the profile says so.

## Severity
| Severity | Meaning | Verdict |
| --- | --- | --- |
| Critical | Secret committed, data written outside the test environment, entitlement bypass | BLOCKED |
| High | Injection path, client identifiers in logs, unvetted dependency with known CVE | BLOCKED |
| Medium | Missing validation, test data with real-looking ids, integration-contract change without sign-off | FINDINGS |
| Low | Over-broad logging without ids, missing header comment | FINDINGS |

CLEAR = nothing found. Every finding: file:line, the exact change required, one line. No generic advice.
