# Quickstart

Requirements: Claude Code 2.1.295 or later (the hooks use `onFailure: "block"`), `git`, Maven or Gradle and npm for the service repos, and `gh` logged in for PRs. The full list and an install check: [guide.md](guide.md) section 3.

## Set up your machine (each person, once)
Claude Code doesn't do this for you. Install these yourself and make sure they're on your PATH:

| Tool | Needed for | If it's missing |
| --- | --- | --- |
| Python 3.11 or later, as `python3` (Windows: `py -3` works) | hooks, the `baton` command, the graph tool | Hooks refuse every action they check, and `/build` stops |
| JDK (`javac`), or `JAVA_HOME` set | reading Java with the AST | A simpler scanner reads Java instead |
| Node (`node`) | reading React and TypeScript | Those files aren't read |

Then install the `baton` command and check it:
```bash
pipx install "git+https://your-git-server/your-org/baton.git#subdirectory=tools/baton"
# from a local checkout: pipx install /path/to/baton/tools/baton
baton --help
```
Run the install again with `--force` after each framework update, so the command matches the plugin.

## Install into a project (no plugin; the usual way)
From a framework checkout, once per central repo and again after each framework update:
```bash
baton install --from /path/to/baton --central /path/to/central --check   # what would change
baton install --from /path/to/baton --central /path/to/central
```
`--from` is the framework folder you cloned (it has `agents/`, `skills/`, `templates/` at the top); the pipx `baton` does not contain them. Set `BATON_FRAMEWORK=/path/to/baton` once to leave `--from` out. `--from` may also be a central repo that already has the install (its `.claude/` is the source). Add `--no-mcp` when your organisation allows only listed MCP servers. The full guide: [guide.md](guide.md). `--central` is the folder that holds (or will hold) `.claude/`, never `.claude` itself.
It copies `agents/`, `skills/`, `hooks/`, `sensors/` and `tools/baton/` under `.claude/` and records them in `.claude/baton-install.json`. An upgrade replaces only what it installed and removes what the framework dropped. A file you edited in the project is reported as a conflict and kept (`--force` replaces it). It adds, never overwrites: `CLAUDE.md` and `profile/*` when missing, the baton hooks in `.claude/settings.json`, the `graph` server in `.mcp.json`, and lines in `.gitignore` and `.gitattributes`. Commit `.claude/` with the central repo.

Windows: install Git for Windows (Git Bash). Hooks run under bash; without it Claude Code falls back to PowerShell and every gate refuses. Python is found as `python3`, `python`, the `py -3` launcher, or `BATON_PYTHON`.

## Install as a plugin (only where plugins and the Claude Code CLI are allowed)
From a shell, with this repository checked out locally:
```bash
claude plugin marketplace add /path/to/baton
claude plugin install baton@lob
claude plugin details baton      # 27 skills, 9 agents, PreToolUse hooks
```
Plugin skills are namespaced: `/build` runs as `/baton:build`. The docs use the short form. With only the VS Code extension and no plugins, use the install below; it needs neither.

## Set up the central repo
1. Create the central repo as a sibling of the service repos, open it in VS Code and start Claude Code there.
2. `baton install` has added `CLAUDE.md` and `profile/*` from `templates/` where they were missing (`sensors-README.md` becomes `profile/sensors/README.md`). `profile/models.yaml` holds the default model per role; the Tech Lead maps its aliases to what your gateway exposes. Fill in `profile/project.md`; `test.env.uri.var` is required before any database client is allowed.
3. Run `/onboard`. It needs the W2 extractors and `baton c4` (W5) to generate the stack table, dependency edges and workspace.
4. Run `/build-context-map` and answer its questions. A feature is accepted for stories only once the areas it changes are understood. Which command to run as code, documents and features change: `docs/guide.md`, "When to run what".

## A story end to end
`/build-context-map focus F-003` -> `/stories F-003` (stops if `baton context check F-003` does not accept the feature) -> `/ready S-010` -> the PO sets Ready -> `/build S-010` -> `/sprint-review` -> a human sets Approved -> `/ship S-010` -> a human merges the code PRs and the docs PR -> `baton tag S-010`. Each step commits on `story/<F>-<S>`; `baton trace <F> --open` shows the whole path on one page; `baton board` shows where every story is. After a feature's last story merges, `/ship F-003` archives it.

Or for a whole feature: `/deliver F-003` runs the same chain and stops only at the gates; run it again to continue after a merge or a review.

## Day to day: where to type what
Agents run only in the Claude Code panel. The `baton` command runs in any terminal, needs no Claude session and no network, and never starts an agent: it tells you where things are and what is next, and you type that in the panel.

| You want to | Type | Where |
| --- | --- | --- |
| Turn a feature note or a Jira key into stories | `/stories F-003` or `/stories PROJ-123` | Claude Code |
| Get a story to the PO | `/ready S-010`; the PO sets `State: Ready` | Claude Code |
| Build one story | `/build S-010` | Claude Code |
| Build a whole feature, stopping only at gates | `/deliver F-003` | Claude Code |
| Review, approve, ship | `/sprint-review`, a human sets Approved, `/ship S-010` | Claude Code |
| See every story, its branches, pushed or merged | `baton board` (`--fetch` first to refresh `origin/`) | terminal |
| See one story across every repo | `baton board --story S-010` | terminal |
| See what one story's build has done, and what is next | `baton build S-010 --status`, then `baton build S-010` | terminal |
| See why a story cannot start | `baton deps S-010`, `baton context check S-010` | terminal |
| Show a feature to people | `baton trace F-003 --open` | terminal, then the browser |
| Tag what shipped | `baton tag S-010`, on the default branch after the merges | terminal |

### The board
```text
$ baton board --fetch
STORY    STATE                    GATE 0       CENTRAL          CODE                         LAST     NEXT
F-003
S-010    In Review                ok           pushed +6        1 repo(s)                    2h ago   Tech Lead: review and merge the PRs
S-011    Design Approved          ok           2 unpushed +3    -                            10m ago  push story/F-003-S-011 (central)
S-012    Ready                    blocked      no branch        -                                     /build-context-map focus F-003
```
- **CENTRAL:** the story's `story/<F>-<S>` branch in the central repo: none, not pushed, n unpushed, pushed, merged.
- **CODE:** its `feature/<F>-<S>` branches in the service repos of `profile/project.md`: how many, merged, not pushed; `baton board --story S-010` shows each.
- **NEXT:** the next move: a push, a merge, a tag, a `/build-context-map focus`; blank when the agents are on it.
- It reads git and the story files only and writes nothing. `--json` gives the same rows to a script or a future UI.

### One story's build
`/build S-010` loops on `baton build S-010`: it prints the next action (an agent with its inputs, a skill, the gate 2 question, a check, or done), the skill does it and reports back with `--done`. You can run the same command by hand to see where a story is:
```text
$ baton build S-010
AGENT architect: design S-010 (light track)
  input: docs/stories/F-003/S-010.md
  then: baton build S-010 --done architect
$ baton build S-010 --status
2026-11-15T11:08:42Z deps        baton
```
- **Gate 2 by hand:** `baton build S-010 --answer approve --by TL` (or `changes --note "..."`, `block`).
- **Redo from a step:** `baton build S-010 --from qa`.
- **Before a PR:** `baton build S-010 --security-check` exits 2 when the security report is missing, blocked or older than the last commit.
- The steps, with who did each and the code heads seen, are in `docs/qa/<F>/<S>-build.json`.

### The trace page
`baton trace F-003` writes `docs/trace/F-003.html`; `--open` opens it in your browser, and `--story S-010` opens it on that story. One self-contained page, no network:
- **Lineage:** feature note, stories, gate 1, design, gate 2, build, sensors, QA and security, confidence, gate 3, docs and PR, merged; red where a human decided, blue where an agent produced, orange where a tool computed, dashed where nothing is produced yet.
- **Each step:** the artefact itself, and who made it from what (the provenance footer).
- **Timeline:** agent time against time spent waiting for a human.

`/build` refreshes it at the end of a story and `/ship` after each merge, so it is current without asking. It is the page to send instead of a status meeting.

### A UI
There is none yet. The planned one is a React and MUI page, from the org's npm registry, over `baton board --json` and each story's `docs/qa/<F>/<S>-build.json`; agents still run in the Claude Code panel.

## Check the install
```bash
baton --help
baton confidence --central fixtures/sample-central-repo S-114 --json
```
The last command rewrites `S-114-confidence.json` in the fixture; run it on a copy to keep your tree clean.
