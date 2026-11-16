# baton: installation and walkthrough guide

The complete guide: what the framework is, how to install it, how a story flows from a feature note to a merged PR, and what every agent, skill, hook and command does. Shorter references: [quickstart.md](quickstart.md), [gates.md](gates.md), [confidence.md](confidence.md), [roles.md](roles.md), [../contracts/cli.md](../contracts/cli.md).

- **Presenting:** open [walkthrough.html](walkthrough.html) in a browser; click any box for its detail.

## 1. What it is
- **Agents:** story-drafter, architect, developer, qa, security, documentation, release; one story at a time.
- **Stack:** Java / Spring / React / Mongo code in sibling service repos.
- **Hooks:** enforce branch, environment and state rules mechanically.
- **`baton`:** a Python command that reads the code deterministically (AST, graph, IR).

```text
feature note -> /stories -> /ready -> Gate 1 (PO: Ready)
             -> /build:  architect -> Gate 2 (design review) -> developer -> qa + security
             -> /sprint-review -> Gate 3 (human: Approved)
             -> /ship:   documentation -> release (PR) -> a human merges
```

`/deliver F-003` runs that whole line for a feature and stops only at the gates (section 11).

- **Deterministic first:** stack, dependencies, diagrams, impact, confidence and the code IR come from `baton`, never from the model.
- **Evidence or it did not happen:** every state change needs its artefact; the `state_gate` hook refuses it otherwise.
- **Humans decide:** the PO sets Ready, the Tech Lead approves designs and stories, a human merges every PR.

## 2. The three kinds of folders
| Folder | What it holds | Who changes it |
| --- | --- | --- |
| Framework clone (`baton/`) | `agents/`, `skills/`, `hooks/`, `sensors/`, `templates/`, `tools/baton/`, `contracts/`, `docs/` | the framework owner, by PR |
| Central repo (one per product) | `.claude/` (the installed copy), `CLAUDE.md`, `profile/`, `docs/` | the agents and the team; start Claude Code here |
| Service repos (siblings of central) | the product code | the developer agent, on feature branches only |

```text
work/
  baton/                 the framework clone (or not present: install from another central repo)
  my-central/              start Claude Code here
    .claude/               agents, skills, hooks, sensors, templates, tools/baton, settings.json
    CLAUDE.md  profile/  docs/  .baton/ (local caches, git-ignored)
  order-service/         service repos, listed in profile/project.md
  web-ui/
```

## 3. Installation

### A. Each person's machine (once)
Install these first. `/build` checks the first four and stops when one is missing.

| Need | Version | Used for | Windows |
| --- | --- | --- | --- |
| Claude Code | 2.1.295 or later | gate hooks use `onFailure: "block"`; older versions ignore it | same |
| Python | 3.11 or later | hooks, `baton`, the graph tool | `py -3` works; `python3` is often a Store stub |
| Git | any recent | branches, diffs, clones | Git for Windows: hooks run under its Git Bash |
| JDK (`javac`) | the repos' Java version | reading Java with the AST; building | same |
| Maven or Gradle | the repos' build tool | the developer agent runs `mvn -q verify` with the sensors | same |
| Node and npm | LTS | reading React and TypeScript; `npm run lint` | same |
| pipx | any | installs the `baton` command | `py -3 -m pip install --user pipx` |
| `gh` (or your Git host's CLI), logged in | any | the release agent opens PRs; `/build` checks dependency PRs are merged | same |
| Access | - | read access to the framework repo; write access to the central and service repos | same |

```bash
git clone https://github.com/vtltranstech/harness.git ~/tools/baton
pipx install ~/tools/baton/tools/baton
pipx ensurepath                # then open a new terminal
baton --help                 # lists ir, reads, install, extract, diagram, ...
gh auth status                 # logged in to your Git host
```

Upgrading a machine or project from the `pod` (or `harness`) name: `pipx uninstall pod` (or `harness`), `pipx install --force ~/tools/baton/tools/baton`, then `baton install` in each central repo. The install moves `.claude/tools/pod` (or `.claude/tools/harness`) to `.claude/tools/baton`, repoints the graph server in `.mcp.json` and replaces the old install record with `.claude/baton-install.json`; commit the result. Old footers, stamps, `POD_*` and `HARNESS_*` variables and the `pod` and `harness` commands keep working for one release.

Clone the service repos next to the central repo (`work/my-central`, `work/order-service`, ...): agents reach them as `../<repo>`, as listed in `profile/project.md`.

### B. The first central repo (once per product)
```bash
mkdir -p ~/work/my-central && cd ~/work/my-central && git init
python3 ~/tools/baton/tools/baton/cli.py install --check      # what it would write
python3 ~/tools/baton/tools/baton/cli.py install --no-mcp     # --no-mcp if your org allows only listed MCP servers
```
`--central` defaults to the current folder; it is always the folder that holds `.claude/`, never `.claude` itself.

What install writes:
| Path | Rule |
| --- | --- |
| `.claude/agents, skills, hooks, sensors, templates, tools/baton` | the framework copy; replaced on upgrade |
| `.claude/baton-install.json` | the hash of every installed file and the framework version |
| `.claude/settings.json` | the baton hooks; your other settings and hooks are kept |
| `.mcp.json` | the `graph` server, unless `--no-mcp` or one is already there |
| `CLAUDE.md`, `profile/*` | from the templates, only when missing |
| `.gitignore`, `.gitattributes` | adds `.baton/` and LF line endings for hooks and scripts |

Then commit `.claude/`, `CLAUDE.md`, `profile/`, `.gitignore`, `.gitattributes` (and `.mcp.json` if written). Teammates who clone the central repo need only step A.

**Allow the `baton` command (a person does this once).** Without MCP, agents run `baton ...` through Bash, and Claude Code asks for each call unless it is allowed. Add the rule to `.claude/settings.json` yourself; install never changes permissions:
```json
"permissions": { "allow": ["Bash(baton:*)"] }
```

**Verify the install** before the first `/onboard`:
| Check | Expect |
| --- | --- |
| `baton --help` | lists `ir`, `reads`, `install` |
| `python3 --version` (Windows `py -3 --version`) | 3.11 or later |
| `cat .claude/baton-install.json` | a `framework` version and the file list |
| `grep -c run-hook .claude/settings.json` | 6 hooks or more |
| Start Claude Code, ask it to run `git push origin main` | refused by `protect_main`: the hooks work |
| After `/onboard`: `baton ir show` | one line per service |

### C. Other projects, from an installed central repo
No framework clone needed: the central repo's own copy installs the next one.
```bash
cd ~/work/my-central
python3 .claude/tools/baton/cli.py install --central ../other-central --no-mcp
# or, from pipx:
baton install --from ~/work/my-central --central ../other-central --no-mcp
```
A `.claude/` copied by hand before `baton install` existed has no `templates/`; run one install into it from the framework clone first.

### D. Upgrading
```bash
cd ~/tools/baton && git pull
pipx install --force ~/tools/baton/tools/baton
cd ~/work/my-central
python3 ~/tools/baton/tools/baton/cli.py install --check
python3 ~/tools/baton/tools/baton/cli.py install --no-mcp
```
- **Replaced:** only files install put there; files the framework dropped are removed.
- **Kept:** your own agents and skills.
- **Conflict:** an installed file you edited is kept and reported, exit 1; `--force` replaces it.
- **After:** commit `.claude/`, restart Claude Code. `/onboard` is not needed for an upgrade.

### E. Windows
- **Hooks:** every hook runs as `bash "<project>/.claude/hooks/run-hook" <hook>.py`; without Git Bash, Claude Code falls back to PowerShell and every gate refuses.
- **Line endings:** `.gitattributes` keeps hooks LF. A clone made before it existed: `git add --renormalize . && git checkout -- .` once.
- **Python:** found as `python3`, `python`, `py -3`, or the path in `BATON_PYTHON`.

### F. Organisation limits
- **No plugins:** the copied install above needs none.
- **Only listed MCP servers:** use `--no-mcp`. Every MCP tool has the same `baton` command, which the agents use first.
- **No zip attachments:** install copies plain files; nothing is packed.

## 4. First run in a central repo
| Step | Do | Result |
| --- | --- | --- |
| 1 | Fill `profile/project.md`: repos table (`../<repo>`, purpose, build command), team, test environment variable | the agents know the repos and the only database they may touch |
| 2 | Fill `profile/domain.md`: business rules, glossary, invariants, open decisions | the rules QA and the domain lens check against |
| 3 | Start Claude Code in the central repo, run `/onboard` | see below |
| 4 | Answer the onboard interview | questions only humans can answer, saved with provenance |
| 5 | Optional: `/onboard` offers the wiki (`baton wiki <repo>`, `baton verify <repo>`) | per-module pages, cited only when verified |
| 6 | Run `/build-context-map`, then answer what it asks | the system understood area by area, its end-to-end flows and the systems around it; a feature is accepted for stories only when the areas it changes are understood |

`/onboard` runs the deterministic extractors and writes:
| File | What |
| --- | --- |
| `profile/stack-detected.md` | Java, Spring Boot, Batch, Mongo, Kafka, React versions per repo, from the build files |
| `profile/dependencies.yaml` | every edge: endpoints exposed and called, collections read and written, topics, jobs, files; each with file:line |
| `docs/architecture/workspace.dsl`, `docs/architecture/diagrams/` | C4 context, containers and components generated from the code |
| `docs/context/codebase-map.md` | index of wiki pages with their verification status |
| `CLAUDE.md` agent-instructions block | verified project facts for every session |

`/build-context-map` then learns the system the way a new engineer would, and stops to ask what it cannot find (contracts/context-map.md section 10):
| Step | What happens |
| --- | --- |
| Documents | Confluence pages (through its MCP server), Word, PowerPoint, Excel, PDF and scans are ingested into `docs/context/sources/`; rules and words found in them become drafts |
| Explore | one `context-explorer` per area, in parallel: what the area is for, everything it touches, what each business rule in its code decides, contradictions with documents and diagrams, questions |
| Join | the `context-integrator` writes the end-to-end flows and the landscape of upstream and downstream systems |
| Grade | `baton context understand` checks every claim against the code and every citation; an area is understood only when nothing fails and no blocking question is open |
| Ask | the Product Owner and the Tech Lead answer the open questions; answers go into the notes and, on their yes, into the domain and branch-point files; the explorers fold them in |
| Accept (gate 0) | `/stories`, `/ready` and `/build` start with `baton context check`; when an area they change is not understood they run `/build-context-map focus F-x` themselves, then check again, and go on only when it passes; the state hook refuses Ready and Designed otherwise |

### When to run what
The context map is the first gate (gate 0): no story is drafted, readied or designed on an area it does not understand. You rarely run it by hand for that: `/stories`, `/ready` and `/build` run `/build-context-map focus F-x` themselves when the map is not confident, ask you its questions, and carry on when it is. The context map is not built once either. Each row is a moment in the product's life and the command for it, in the order you meet them.

| When | Run | What happens |
| --- | --- | --- |
| Day one, new central repo | `/onboard` | stack, edges, workspace DSL, C4 diagrams, wiki, CLAUDE.md block; questions only humans can answer |
| Right after onboard | `/build-context-map` | documents ingested, every area explored, flows and landscape joined, graded; stops with questions for the PO and the Tech Lead |
| The PO or Tech Lead has time to answer | `/build-context-map` again, or without a session `baton context answer <area> Q3 "<answer>" --by PO` | asks the open questions (or records one answer verbatim), explorers fold them in on the next run; areas move from blocked to understood |
| Every morning | `/standup` | prints `docs/context/questions.md`: who must answer what, oldest first; one open longer than `question-ttl-days` is OVERDUE for the Tech Lead |
| Where things stand | `/build-context-map status` | areas by status, the open questions by person; no agent runs |
| Building one story | `/build S-x`; by hand `baton build S-x` prints the next step, `--status` the steps so far | `baton build` owns the order: gate 0, deps, architect, gate 2, developer, checks, qa, security, confidence; the skill runs each agent and reports back with `--done`; a commit after the security report runs security again |
| Gate 0 refuses a story the Tech Lead accepts anyway | the Tech Lead adds `Gate-0-Override: <reason> (TL, YYYY-MM-DD)` to the story header, by hand | the refusal is recorded with the reason in the build ledger and shown as `override` on the board; agents cannot write the line |
| An agent or skill file changed | `baton agents check` | blueprints, handoffs, outcomes, hooks and skill activation linted; exit 1 lists each problem |
| A new service repo | copy a kit from `templates/kits/`, add its row to `profile/project.md`, then `/onboard` | sensors, CI and the Claude Code files from day one; on an existing repo `/onboard` writes the alignment list for the Tech Lead |
| Which story is where: branch, pushed, merged | `baton board` (any terminal, no session), `baton board --story S-x` for one story, `--fetch` to refresh origin first | one line per story: State, gate 0, its `story/<F>-<S>` branch (pushed, unpushed commits, merged), its `feature/<F>-<S>` branch in every service repo, the tag, and the next move (push, tag, focus, review); reads git only and writes nothing |
| A new feature note in `docs/features/` | `/build-context-map focus F-x` | explores only the areas the feature changes and their neighbours; cheaper than a full run |
| Before drafting stories | `/stories F-x` (or `/deliver F-x`) | gate 0: `baton context check F-x`; if refused, it runs `/build-context-map focus F-x` and asks you, then checks again; drafts only when the changed areas are understood, their boundary systems named and the feature's words defined |
| A small fix (light track) | `/ready S-x`, `/build S-x` | the same gate for the story's track: light work may start in an area with up to `light-open-questions` (default 2) open questions, never with an open contradiction |
| A story is shipped | nothing extra: `/ship` | the documentation agent re-extracts, refreshes wiki and diagrams, and lists in the change note the areas whose code changed (now stale) |
| Code merged outside baton, or many merges since the last run | `/onboard refresh`, then `/build-context-map refresh` | onboard shows the edges added and removed; the context map re-reads only the areas whose own code changed and the incomplete ones |
| New or updated documents, Confluence pages | add them to `doc-sources` in `profile/context.yaml`, then `/build-context-map refresh` | re-ingests and rebuilds the drafts; every note is graded again, so a citation to a removed section shows up |
| An agent got the business wrong | `/onboard record` for a fact; a PO answer through `/build-context-map` for a rule | the fix is kept with its source, so the next run does not repeat it |

What keeps work out, and what to do (the commands above do the first three for you):
| `baton context check F-x` or `S-x` says | Do |
| --- | --- |
| `<area> is unexplored` | `/build-context-map focus F-x` |
| `<area> is stale` | `/build-context-map refresh` |
| `<area> is incomplete` | `/build-context-map focus F-x`; after `explore-rounds` rounds the problems are listed for a human to look at |
| `<area> is blocked: n questions for a human` | the named person answers through `/build-context-map`, or `baton context answer <area> Q<n> "..." --by PO` |
| `<area> is blocked: n contradictions for the Tech Lead` | the Tech Lead says which is right, the document or the code: `baton context answer <area> C<n> "..." --by TL`; when the code is wrong, raise a story |
| `<resource>: which system is on the other side?` | the Tech Lead answers the landscape question |
| `no area` or an undefined word | name the module or define the word in the feature note, or ask the PO to add it to `profile/domain.md` |

A merge makes stale only the areas whose own source or test files changed; areas in other modules of the same repo stay understood, so one story does not hold up every feature.

## 5. A story end to end

### States and gates
```text
Draft / Needs Clarification -> Ready for PO -> [Gate 1] Ready
  -> Designed -> [Gate 2] Design Approved | Design Changes Requested | Blocked
  -> In Review -> QA Pass | QA Fail (back to developer)
  -> [Gate 3] Approved -> Documented -> Done (PR merged by a human)
```
`baton state-check` holds the table; the `state_gate` hook refuses a state without its artefacts (for example `In Review` needs a green `archunit.txt`; `QA Pass` needs a test report with `Verdict: PASS`).

### Tracks (Jira type and labels; `triage` skill)
| Track | For | Design | Gate 2 |
| --- | --- | --- | --- |
| light | bug, task, `quick-fix` | 5-section note, no diagrams | auto-pass at confidence >= 80, else asked |
| full | story, `new-api`, `data-model`, `batch-job`, `multi-repo` | 11-section note, generated diagrams, review lenses | always asked |
| spike | investigation | findings note; no developer | accept the findings |

The architect escalates light to full on a new collection, field, index or endpoint, more than one repo, or an open decision.

### What each step does and writes
| Step | Command | Agent | Writes |
| --- | --- | --- | --- |
| Feature to stories | `/stories F-003` | story-drafter | `docs/stories/F-003/S-*.md` with acceptance criteria, estimate, risks |
| Definition of Ready | `/ready F-003` or `/ready S-301` | story-drafter | gaps, then questions to the human; the PO sets `Ready` (Gate 1) |
| Dependencies | inside `/build` | - | `baton deps S-301`: stops if a story it depends on is not merged |
| Design | inside `/build` | architect | `docs/design/F-003/S-301-design.md`, `S-301-change.yaml`, diagrams from `baton diagram story`, blast radius, `.baton/context/S-301.md` |
| Design review | inside `/build` | human (Gate 2) | `## Design review` in the story; `docs/metrics.md` calibration row |
| Build | inside `/build` | developer | branch `feature/F-003-S-301` in each repo, code and tests, sensor reports (PMD, Checkstyle, ArchUnit, ESLint), `## Dev summary` |
| Risk tier | inside `/build` | - | `baton risk S-301`: low, medium or high from the design and the diff; low runs 2 review lenses (3 if a business rule is named), the rest all 5 |
| Verify | inside `/build` | qa + security | test report (each AC with its test and data check), review lenses, mutation on changed lines, security report (every tier) |
| Score | inside `/build` | - | `baton confidence S-301` (score and lane), `baton evidence S-301` |
| Review pack | `/sprint-review` | - | stories at Gate 3, ordered by lane: fast, senior, tech-lead |
| Approve | a human | Gate 3 | sets `Approved` in the story |
| Ship | `/ship S-301` | documentation, release | change note, wiki and map refreshed, PR(s) linking every artefact, metrics |
| Merge | a human | - | `Done` |

`/sprint` runs `/build` for every Ready story in `docs/status.md`, one at a time. `/deliver F-x` runs every row above for one feature.

## 6. Agents
| Agent | Runs at | Reads | Writes | Never |
| --- | --- | --- | --- | --- |
| context-explorer | `/build-context-map`, one per area, in parallel | its brief (`baton context brief`), domain, documents, diagrams, IR, tests | `docs/context/understanding/areas/<area>.md` | writes a claim without a citation, answers its own questions |
| context-integrator | `/build-context-map`, after the explorers | area notes, `baton context brief system`, diagrams | flows and landscape under `docs/context/understanding/` | names a system without evidence |
| story-drafter | `/stories`, `/ready` | feature note, domain, the feature's understanding manifest | stories, readiness gaps and questions | sets Ready |
| architect | `/build`, state Ready | story, domain, stack, IR, architecture views | design note, change spec, diagrams, pattern ledger, design confidence, context pack | writes code or hand-drawn diagrams |
| developer | `/build`, Design Approved or QA Fail | design, context pack, IR | feature branches, tests, sensor reports, dev summary | commits to main, touches files the design does not list without a Deviations entry |
| qa | `/build`, In Review | story ACs first (independence rule), then design, diff, context pack | test report, data checks, review-lens findings | trusts the developer's account |
| security | `/build`, In Review | diff, security checklist | security report with severities | approves its own findings away |
| documentation | `/ship`, Approved | story, diff | change note, ADRs, regenerated wiki and codebase map, architecture views | hand-edits generated pages |
| release | `/ship`, Documented | every artefact | PR(s) with links, metrics | merges |

## 7. Skills

### Commands you type
| Command | Does |
| --- | --- |
| `/onboard` | extractors + interview; stack, dependencies, architecture, codebase map |
| `/build-context-map [setup / focus F-x / refresh / status]` | documents, context explorers and integrator, grading, questions for humans; the understanding a feature needs before stories |
| `/stories F-x` | feature check, then story drafts, then `/ready` on the drafts |
| `/ready S-x / F-x / all` | Definition of Ready with a clarification loop |
| `/build S-x` | architect, gate 2, developer, qa, security, with fix loops; stops before gate 3 |
| `/deliver F-x` | the whole feature: `/stories`, gate 1, `/build` per story in dependency order, gate 3, `/ship`; asks only at the gates; run again to continue |
| `/sprint` | `/build` for every Ready story |
| `/sprint-review` | gate-3 pack by confidence lane |
| `/ship S-x` | documentation, then release |
| `/standup` | summary from `docs/status.md` and open questions |
| `/retro` | evidence-based retrospective with actions |
| `/agent-regression` | re-run agents on golden stories and diff against approved output |
| `/elicitation` | critique menu (pre-mortem, red team, socratic, ...) on the latest artefact |
| `/design-review-lenses S-x`, `/review-lenses S-x` | the independent review lenses on a design or a diff |
| `/standards`, `/triage`, `/workflow`, `/jira` | print the rules |

### Read by the agents
| Skill | Used by | Covers |
| --- | --- | --- |
| `workflow` | every agent | principles, roles, gates, states, hooks, how to read code |
| `triage` | story-drafter, architect, `/build` | track from Jira type and labels |
| `story-writing` | story-drafter | splitting features, writing ACs |
| `design-diagram` | architect | change spec format; `baton diagram` |
| `design-review-lenses` | architect | lenses before a human sees the design |
| `standards` | architect, developer, craft lens | stack rules, pattern ledger, sensors |
| `review-lenses` | qa | edge cases, verification gaps, craft, conformance, domain fidelity |
| `data-check` | qa | data checks against the test environment |
| `security-checklist` | security | secrets, exposure, injection, entitlement, dependencies |
| `impact` | architect, qa | blast radius with `baton impact` |
| `wiki` | onboard, documentation | generating and verifying wiki pages |
| `change-note` | documentation | change notes, map, ADRs |
| `doc-style` | every agent writing under `docs/` | ASCII, tables, short bullets; enforced by the doc-lint hook |

## 8. Hooks (in `.claude/settings.json`)
| Hook | When | Does |
| --- | --- | --- |
| `protect_main.py` | before Bash | refuses commits on main, pushes to main, force pushes, merges, branch deletion |
| `protect_env.py` | before Bash | refuses database URIs and clients other than the test environment named in the profile |
| `commit_scope.py` | before Bash | on a central-repo `story/<F>-<S>` branch, refuses a commit holding another story's files |
| `state_gate.py` | before Write, Edit, Bash on a story | refuses a State the artefacts do not justify |
| `protect_weights.py` | before any read or write | refuses `profile/confidence-weights.yaml` |
| `doc_lint.py` | after Write, Edit under `docs/` | hands doc-style problems back to the agent |
| `read_log.py` | after Read, Grep, Glob, Bash | logs which agent read what (never content) to `.baton/reads.jsonl` |

A gate hook that cannot start blocks the call (`onFailure: block`); the doc lint and the read log never block.

## 9. The `baton` command
| Command | Does |
| --- | --- |
| `extract-stack`, `extract`, `onboard` | stack table, dependency edges, onboarding questions |
| `c4`, `diagram architecture` | the architecture of record from the code |
| `diagram story S [--check] [--diff REF]` | design diagrams from the change spec; as-built diagrams and drift from the diff |
| `diagram context <name>` | a ~20-line card of a class, method or resource |
| `ir show [unit / Class / Class#method / collection:x]` | the code as operations and effects (section 10) |
| `ir find <words>` | where a story lands |
| `ir slice S [--write]` | the story's context pack in `.baton/context/S.md` |
| `impact --repo R --diff REF`, `graph` | blast radius across repos |
| `wiki`, `verify` | per-module pages and their verification |
| `context ingest / build / score / brief / understand / questions / answer / check S-x or F-x / gaps / trend` | documents into sources, branch points and drafts, the context map, the explorers' briefs and grades, the questions by person, a human's answer, gate 0 for stories and features |
| `mutation`, `confidence`, `evidence`, `state-check`, `deps` | gate-3 inputs and story checks |
| `doclint [--fix]` | the doc-style check |
| `reads [--story S]` | what each agent read, re-read, searched; rough tokens |
| `risk S` | the story's risk tier and the review lenses QA runs (`-risk.json`) |
| `eval S` / `eval --all` | per story: minutes, tokens and re-reads per agent, waiting between agents, and per lens how many findings only that lens found; from this machine's Claude Code transcripts |
| `stories [--feature F]` | every story wherever it lives: here, the archive, or its own `story/` branch |
| `models S` | the model each role runs on for that story, and who reviews whom |
| `tag S` / `tag F` | on the default branch after the docs PR merged: an annotated tag, the version of a shipped story or feature |
| `c4 --story S` | promote the architecture for a story: stamps, CHANGELOG line |
| `trace F [--story S] [--open]` | one HTML page per feature: who produced and who decided each step, from feature note to merged PR, and what the feature added to the domain rules, sensors and architecture |
| `install [--from X] [--check] [--force] [--no-mcp]` | install or upgrade a project's `.claude/` |

### Measuring where time goes
Run stories as usual, then `baton eval --all` in the central repo. Everything it reads is already on the machine that ran them: Claude Code's subagent transcripts, `.baton/reads.jsonl`, and each story's `-risk.json` and `-triage.md`. Nothing is sent anywhere, and only counts and file names are printed.

| Line | What it tells you |
| --- | --- |
| `span = agents + waiting` | how much of a story's elapsed time was agents working, and how much was waiting (gates, answers) |
| per agent `runs`, `min`, `tok in`, `tok out` | which phase costs most; `runs` above 1 for architect or developer is a design round or a fix loop |
| `re-read N files` | an agent reading the same file again: a sign its context pack or the IR did not answer it |
| lens `unique high/med` | high or medium findings only that lens found; one that stays 0 over 10+ stories is a candidate to drop |

Claude Code deletes transcripts after `cleanupPeriodDays` (30 by default); set `"cleanupPeriodDays": 90` in your own `~/.claude/settings.json` to keep a quarter's data.

### Versions of the central repo
Every PR, in the central repo and the service repos, targets the repo's default branch (whatever it is called; agents never commit to it). Every story gets a branch `story/<F>-<S>` in the central repo; each step commits there with a fixed message (`S-010: design (architect, 82%)`, `S-010: QA PASS`, ...), so the branch history says who decided what and when. `/ship` opens the docs PR beside the code PRs. After the Tech Lead merges them, `baton tag S-010` on the default branch marks the version; `git diff S-008..S-010 -- docs/architecture/workspace.dsl` is the architecture change between two shipped stories. Every element a story added or changed carries its story and feature in the model, and `docs/architecture/CHANGELOG.md` has one line per promotion. When a feature's last story has merged, `/ship F-003` moves its story files to `docs/archive/F-003/`.

### Which model runs what
`profile/models.yaml` (the Tech Lead's; the install adds the defaults) names a model per role and track: by default the strong model designs full-track stories and runs every reviewer (design lenses, review lenses, security), the fast model drafts, builds and orchestrates QA, the cheap one writes light-track docs and releases. A reviewer is never weaker than what it reviews; `baton models S-301` shows the pairing and refuses a file that breaks the rule. A failed QA loop moves the developer to the strong model. Metrics record both models per story, so `/retro` can tell whether the strong reviewer pays for itself.

### The feature trace page
`baton trace F-003` writes `docs/trace/F-003.html`: one page that replaces a demo and a status meeting. `/ship` refreshes it after each story; `/sprint-review` and `/standup` link it.

| Part | Shows |
| --- | --- |
| Lineage strip | feature note -> stories -> gate 1 -> design -> design lenses -> gate 2 -> build -> sensors -> QA + security -> confidence -> gate 3 -> docs + PR -> merged; red = a human decided, blue = an agent produced, orange = a tool computed, dashed = not produced yet; a QA fail draws the loop back to build |
| Panel per step | the artefact's own content, and first who made it and from what: agent, skills, profile sections and wiki pages read, time taken |
| Knowledge | domain lines added through clarifications, sensor rules recorded, architecture elements and relationships added |
| Timeline | agent time against time waiting for a human |

The "who made it and from what" row comes from the provenance footer every agent now appends to its Markdown files (an HTML comment, `workflow` skill). Files written before this release have none and show "no provenance footer"; the rest of the page still works. The page needs no network and opens from the file system or a VS Code preview.

## 10. How agents read code (the IR)
The IR lifts the AST into operations and effects, so an agent reads a few lines instead of files.

```text
service OrderService  order-service/src/main/java/.../OrderService.java:42-548
  cancelOrder(command, actor): CancelOrderResult  :206-284
    calls OrderRepository.findById,findLines,save; PaymentRepository.save; ...
    reads orders
    writes order_audit_log, orders, outbox_events, payments
    throws NotFoundException, OrderValidationException
    called by OrderController#cancel
    from POST /orders/{orderId}/cancel (OrderController#cancel)
```

| Need | Command |
| --- | --- |
| Where am I | `baton ir show` (one line per unit) |
| Where does this story land | `baton ir find cancel order refund` |
| One class or method | `baton ir show OrderService#cancelOrder` |
| Who reads or writes this data | `baton ir show collection:payments` |
| Everything for one story | `.baton/context/S-301.md` (`baton ir slice S-301 --write`) |

- **Effects through calls:** reads and writes include those done by the methods an operation calls, also across interfaces and recursion.
- **Overloads apart:** callers are matched by signature, also through interfaces.
- **Overview cost:** ~800 tokens on a 12-service product, against ~49,000 for the map plus `dependencies.yaml`.
- **Story pack cost:** 1,000-2,000 tokens.
- **Caches:** `.baton/code/<repo>.json` and `.baton/graph.sqlite`, rebuilt automatically when the code or `dependencies.yaml` changes.
- **Measure it:** `baton reads --story S-301` after a story shows reads, re-reads and searches per agent; `baton eval S-301` adds time, tokens and waiting per agent.

## 11. Walkthrough: one feature to a merged PR
| # | You | What happens |
| --- | --- | --- |
| 1 | Write `docs/features/F-003-<slug>.md` (problem, outcome, rules, acceptance, open questions) | the input for drafting |
| 2 | `/stories F-003` | the drafter checks the feature, asks what is missing, writes `S-301`, `S-302`, ... and runs `/ready` |
| 3 | Answer the questions; as PO choose "Set Ready" | Gate 1: `State: Ready` |
| 4 | `/build S-301` | architect: design note, change spec, diagrams, blast radius, context pack |
| 5 | Read the design (path and confidence shown); choose Approve or Request changes | Gate 2 |
| 6 | Wait | developer builds on `feature/F-003-S-301`; qa and security verify; fix loops on QA Fail |
| 7 | `/sprint-review` | the gate-3 pack: evidence, confidence lane, reports |
| 8 | Set `State: Approved` in the story | Gate 3 |
| 9 | `/ship S-301` | change note, wiki refresh, PR(s) with every artefact linked |
| 10 | Review and merge the PR | `Done` |
| 11 | `/standup` daily, `/retro` per sprint | status, open questions, actions |

### The same with one command
`/deliver F-003` runs rows 2 to 9 and stops only where a person decides:

| Stop | Who | Question |
| --- | --- | --- |
| Feature and story gaps | anyone who knows | the `/stories` and `/ready` questions |
| Gate 1 | Product Owner | Set Ready, or leave for refinement (up to 4 stories per prompt) |
| Gate 2 | Tech Lead | Approve, Request changes or Block, when the track asks (light stories at 80+ auto-pass) |
| Gate 3 | Senior Engineer writes `## Human findings`, Tech Lead answers | Approve, Send back (Blocked, with the reason) or Not now |
| Merge | a person, outside Claude | a story that depends on an unmerged PR waits |

- **Resumable:** it reads every story's State each time; after a merge, a review or an answer, run `/deliver F-003` again and it continues.
- **Nothing skipped:** it chains `/stories`, `/ready`, `/build`, `/sprint-review` and `/ship` unchanged; the hooks check every state as before.
- **One story at a time,** in `Depends-On:` order; a blocked story stops only itself.

## 12. Files in a central repo
| Path | Written by |
| --- | --- |
| `profile/project.md`, `profile/domain.md` | humans (templates from install) |
| `profile/stack-detected.md`, `profile/dependencies.yaml`, `profile/aggregates.yaml` | `baton extract-stack`, `baton extract` |
| `profile/confidence-weights.yaml` | humans only; agents are refused |
| `docs/features/`, `docs/stories/<F>/` | PO, story-drafter |
| `docs/design/<F>/` | architect, `baton diagram` |
| `docs/qa/<F>/` | developer (sensors), qa, security, `baton confidence`, `baton evidence` |
| `docs/changes/<F>/`, `docs/decisions/` | documentation |
| `docs/architecture/` | `baton c4`, `baton diagram architecture` |
| `docs/wiki/`, `docs/context/codebase-map.md` | `baton wiki`, `baton verify` |
| `docs/status.md`, `docs/metrics.md` | every agent that changes a state |
| `.baton/` | local caches, context packs, read log (git-ignored) |

## 13. Troubleshooting
| Symptom | Cause | Fix |
| --- | --- | --- |
| `baton: invalid choice: 'install'` | an old `baton` | `git pull`, then `pipx install --force <clone>/tools/baton` |
| install: "nothing to install from" | run from pipx or a hand-copied `.claude/` | `--from <clone or installed project>`, or the clone's `cli.py` |
| Every tool call refused on Windows | no Git Bash, or CRLF hooks | install Git for Windows; renormalize line endings (3E) |
| "hooks need Python 3.11" | no usable Python | install it, or set `BATON_PYTHON` |
| `baton ir`: "run baton extract first" | no `profile/dependencies.yaml` | run `/onboard` |
| install exit 1, "conflict" | an installed file edited in the project | move the change to the framework, or `--force` |
| "Prompt blocked" by an organisation hook right after a subagent finishes | the subagent ran in the background; its report came back as an injected `<agent-message>` prompt, which the organisation's `UserPromptSubmit` hook refused | keep `"env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}` in `.claude/settings.json` (install adds it), restart Claude Code; if it still happens, ask the enablement team to allow `<agent-message>` hand-backs |
| MCP approval prompt at start | `.mcp.json` written | decline, or remove the entry; reinstall with `--no-mcp` |
| A wiki page is not cited | its map row is not `verified @<commit>` | `baton wiki <repo>` and `baton verify <repo>` |
