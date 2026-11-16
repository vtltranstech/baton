# Known limitations

## What a text-matching hook cannot stop
The hooks read the command line. They cannot see what a program does once it runs, so these get through:
- A script file: `./deploy.sh`, `sh x.sh`, `python x.py`, `mvn exec:java`, a Makefile target. A script may run `git push` or read the weights. (mongosh script files are the one exception: they are read and checked.)
- A language's own git or file API inside such a script, or inline code that builds strings without naming the profile: `python3 -c` with base64-decoded text.
- Commands assembled at run time from sources other than shell variables, unless the program word or a target is visibly dynamic; those are refused.
- `git push` through a remote-side refspec in config (`remote.<name>.push`), or plumbing not listed in [gates.md](gates.md) such as `git commit-tree` with `git fetch . x:main`, `git reset --hard` on main.
- `curl` to a forge's merge API; only `gh` and `glab` are recognised.
- `git show`, `git log -p` or `git diff` without a path can print the weights if they are tracked and changed. The file's name is refused, not its content.
- `state_gate` refuses Bash writes it can recognise, by an allowlist of read-only commands on paths under `docs/stories`. A script writing to a story is invisible.
- A URI literal written by the Write or Edit tool is not checked: `protect_env` matches Bash only. Sensors and the security review cover config files.
- `@file` references in a prompt insert content with no tool call, so no PreToolUse hook fires. A human can include the weights this way; add a `Read` deny rule for it if needed. MCP tools that read files are not matched.
- The Bash parser is a reader for common shell, not bash itself. Exotic syntax it misreads may be refused, or in rare cases misjudged. `GIT_DIR` exported inside a subshell is treated as still set afterwards.
- PowerShell is not matched, so Windows without Git Bash has no shell protection.

Treat the hooks as guard rails against an agent's mistakes. Against a determined adversary use OS-level controls: branch protection on the server, and a test-only database credential.

## Artefacts are trusted as files
- `state-check` confirms artefacts exist and read as green. An agent can write a false `archunit.txt` or test report. Independent QA, lenses and human review are the defence.
- `state-check` applies the contract's table, not the order of states. `Draft` to `Done` passes if the story has a `PR:` line with a URL. The contract defines no transition rule, and a spike legitimately skips states.
- `Ready` is human-only by contract, but a hook cannot tell a human from an agent: only the `/ready` skill's rule protects it.
- `-diff-shape.json` is written by `/build`, an LLM step. Its numbers are checked by no tool; the risk-zone and dependency caps are as good as its file list.
- The Documented check compares mtimes as the contract says, and mtimes are not preserved by a clone.

## Confidence
- `confidence.json` holds `points` and `max` per signal, and the score implies the caps. The contract requires them. Anyone reading that file, an agent included, can derive the weights, the caps that fired and, over several stories, the policy. The hook protects the yaml and the thresholds, not these outputs. Agents are told not to reason from them; nothing enforces it.
- Weights are initial guesses until calibration data exists.
- The score reads what the artefacts claim; it does not rerun anything.
- `sensors` depends on `sensorLoops`, self-reported in the developer's Dev summary.
- `## Counts` in the triage file is written by the qa agent and is not recomputed.
- `evidence.md` reports data checks and verdicts as written in the reports.

## Multi-repo stories
`-impact.json` and `-mutation.json` each hold one repo. A multi-repo story writes `-impact-<repo>.json` and `-mutation-<repo>.json`. These names are an addition to the contract. `baton confidence` adds impacted repos across files (a repo counts once) and takes the lowest mutation score; a repo in `-diff-shape.json` with no file scores the signal 0 and forces the tech-lead lane. It relies on `sourceRepo` and `repo` matching the diff shape's repo names.

## Versioning, trace and models
- Model choice is passed by the launching skill and recorded in each footer; no hook can enforce it, since the tool call carries it. The footer is the audit.
- Only files written from now on carry a provenance footer; older artefacts show "no provenance footer" on the trace page.
- A story still on its `story/` branch is read through git; its trace links point to the path the file will have once its docs PR merges.
- `commit_scope` allows any change to `profile/domain.md`; it cannot tell whether the PO approved the line.
- Commit messages are written by skills; no hook checks their text.
- The `harness` command, `harness:` footers, `harness.*` stamps and `HARNESS_*` variables work for one release after the rename to `baton`.
- Tree-sitter reads Java only when the `baton[treesitter]` extra is installed; without it JavaParser (needs a JDK), then the regex scanner, read the code. A file with a syntax error is refused by tree-sitter rather than read around.

## Not run
- `/build` with a person answering every WAIT has not been run by a human; `test_fixture_walk.py` proves the deterministic parts, without a model and without gates being asked.
- Hooks were tested by feeding their PreToolUse JSON to the scripts by subprocess, and the plugin was installed in a temporary config dir. They have not been observed firing inside a live Claude Code session.
- End-to-end test of a product deploy is out of scope; `evidence.md` says it was not executed.

## Parsers
- JavaParser 3.28.2 names language levels up to Java 26. Java syntax neither tree-sitter-java nor JavaParser knows falls back to the scanner, per file, and the file is listed under `parser.fallback`.
- No JDK means every Java file goes through the scanner. No Node means TypeScript is not read, and onboarding asks about it.
- The TypeScript extractors see `fetch` and `axios` only. A wrapper or client imported from another file, GraphQL and generated clients are not seen.
