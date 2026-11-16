# `baton mutation`

```
baton mutation --central <central> --repo <name> --diff <ref> [--out <path>] [--timeout <seconds>] [--json]
```

Runs PIT on the classes the diff changed under `src/main/java`, and only those, and reports `mutation.json` (`contracts/artefacts.md` §8, `schemas/mutation.json`). Without `--out` it prints only; `/build` passes `--out docs/qa/<F>/<S>-mutation.json`. The score is a confidence signal, not a gate.

- **Repo path:** the `path` cell of the repo's row in `profile/project.md`, else `../<name>`.
- **Build tool:** `./mvnw`, then `mvn`; `./gradlew`, then `gradle`. Maven passes `-DtargetClasses` and `-DtargetTests`; Gradle passes `-PbatonTargetClasses` and `-PbatonTargetTests`, which `sensors/build.gradle.kts` reads. The JDK comes from the environment (`JAVA_HOME`).
- **Score:** `killed / (killed + survived + noCoverage)`, PIT's definition. `killed` includes `TIMED_OUT` and `MEMORY_ERROR`. `NON_VIABLE` and `RUN_ERROR` give no verdict and are left out. Only changed classes and their nested classes count.
- **Exit codes:** `0` with a score or with `notRun: true`; `2` when the repo is missing or the ref cannot be diffed. `notRun` reasons: PIT not in the build file, no build tool, no changed classes, build failed or timed out, no mutations generated. A `notRun` document has no `score`, `killed`, `survived` or `noCoverage`.

Limitations: `pitest: installed` is read from the build file, not `profile/stack-detected.md`. The build tool may fetch dependencies from its configured repository; the subcommand itself makes no network call. Multi-module builds are coded for (every `mutations.xml` under the repo is read, and the wrapper must be at the root) but no fixture proves them.
