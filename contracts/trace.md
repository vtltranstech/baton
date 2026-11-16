# `baton trace`  -  implementation guide (story trace page)

**Purpose.** One generated HTML page per feature, `docs/trace/<F-xxx>.html`, that shows how the feature became stories, designs, code, reviews and a PR: which agent produced each artefact, which skills and profile sections it read, which humans decided what, and what the feature added to the knowledge base (domain lines, rules, architecture). Every node is a real file. The page replaces a recorded demo and a status meeting. It is a **view**: no new agent behaviour, no new data, except the provenance footer in section 2.

Owner: W1. Subcommand: `baton trace <feature-id> [--story S-yyy] [--open]`. Exit 0 on success, 2 if the feature folder is missing. Reruns overwrite; the page is committed with the docs.

---

## 1. Inputs (all existing, fixed names, relative to the product root)

| Source | What trace reads from it |
| --- | --- |
| `docs/features/<F>.md` | title, author line, date, business summary (first paragraph), scope bullets |
| `docs/stories/<F>/S-*.md` | header fields (Jira-Type, Labels, Track, Estimate, State, Owner, PR), `## Acceptance criteria` (count + first line each), `## Readiness` (score n/9), `## Clarifications` (Q/A pairs + "-> domain line" marker), `## Design review` (decision, date, rounds), `## Dev summary`, `## Rule ledger`, `## Open questions` |
| `docs/design/<F>/S-*-design.md` (or `-findings.md`) | sections found by heading name, not number (the light and full notes number them differently): Challenge round (strawman, where it fails, chosen design), Rules touched, Change or Approach, Pattern ledger rows, Repos and files, Confidence (score, Why, Reviewer should check), Revision |
| `docs/design/<F>/S-*-diagrams/diagrams.json` + `flow.svg`, `docs/design/<F>/S-*.dsl` | the design's touch points new / changed / removed with their names; flow.svg embedded as an image; a link to the candidate .dsl |
| `docs/design/<F>/S-*-reviews/*.md` | design lens names + verdict line each |
| `docs/qa/<F>/S-*-sensors/*` | per-tool green/red + counts (archunit.txt `Tests run/Failures`, pmd.xml violations, checkstyle.xml errors, eslint.json errorCount) |
| `docs/qa/<F>/S-*-diff-shape.md/.json` | lines vs estimate, files, new types vs ledger, flags |
| `docs/qa/<F>/S-*-lens-*.md`, `S-*-triage.md` | five lens verdicts, triage counts HIGH/MEDIUM/LOW, dismissed |
| `docs/qa/<F>/S-*-test-report.md` | AC table (AC, test, result, evidence), data checks (command -> result), Conformance, Domain fidelity, Verdict, Human findings |
| `docs/qa/<F>/S-*-security-report.md` | verdict + findings count by severity |
| `docs/qa/<F>/S-*-impact.json`, `S-*-mutation.json`, `S-*-confidence.json`, `S-*-evidence.md` | when present (else "not run") |
| `docs/changes/<F>/S-*-change-note.md` | summary, "Architecture: +n elements..." line, ADR links |
| `docs/metrics.md` | the feature's rows (lead time, loops, confidence vs outcome, cost) |
| story `## Clarifications` lines ending `-> domain.md: <rule>` (written by `/ready`), `profile/domain.md`, `profile/sensors/README.md`, `docs/architecture/CHANGELOG.md` and the stamps in `docs/architecture/workspace.dsl` (versioning.md section 3) | domain lines the feature added (checked present in domain.md); sensor-record rows whose Added date is on or after the feature start, or whose incident names one of its stories; architecture +elements / +relationships / ~changed / removed from the feature's CHANGELOG rows and the names of the elements stamped with the feature, falling back to the change notes' `Architecture:` line; before = current workspace counts minus the additions. No git history is needed |
| `git log` of the service repos' `feature/<F>-S-*` branches | commits per task, PR link |
| provenance footer (section 2) in every artefact | agent, skills, profile sections, wiki pages, commit, timestamp, tokens |

Parsing is by section heading and fixed field names; anything missing becomes `null` and renders as "not produced", never as an error. A missing artefact must never break the page.

## 2. Provenance footer (the one addition to agent behaviour)

Every agent appends this to every artefact it writes (W1 adds the rule to each agent prompt and the `change-note`/`story-writing`/`design-diagram` skills):

```
<!-- baton:provenance
agent: architect
skills: design-diagram, standards, design-review-lenses
profile: domain.md#rules-touched(R3,R7), project.md#repos, stack-detected.md
context: docs/wiki/order-service/pricing.md@3f9c2e1, docs/wiki/batch-loaders/orders.md@3f9c2e1
graph: impact.json (2 repos, 0 unknown edges)
commit: 3f9c2e1
started: 2026-11-04T09:12:00Z  finished: 2026-11-04T09:31:00Z
tokens: 41200
-->
```
HTML comment so it never renders in the markdown. Keys are fixed; unknown keys are kept and shown under "more". One footer per agent per file (an agent editing a file replaces its own). `started`/`finished` come from `date -u` (an agent without Bash omits them); `tokens` only when the session reports it, never estimated - `baton eval` has measured numbers. This footer is also the "context manifest": the lenses read the same `context:` list.

## 3. Output: `docs/trace/<F>.html`  -  one self-contained file

Generated from a template `tools/baton/trace/template.html` by injecting one JSON object (`window.TRACE`, schema in section 4). No network, no CDN (the page must open from the file system and inside a locked-down VS Code preview): inline CSS and JS, system font stack with optional Google Fonts link that degrades silently. Dark and light theme via `prefers-color-scheme`. Works at 1280 px and at phone width; the lineage strip scrolls horizontally when narrow.

### 3.1 Layout, top to bottom

1. **Header band.** Feature id + title; status pill (In progress / Done); five figures as tiles: stories (done/total), gates passed (n/3 per story, aggregated), lead time (feature start -> last PR), fix loops, confidence (median, with lane). Under it one line: "PO <name> - Tech Lead <name> - Senior Engineer <name>" from the optional `people.po`, `people.tech-lead`, `people.senior-engineer` rows of `project.md` (PO falls back to the feature's `Owner:`; a missing name shows the role only). A story selector (chips) when the feature has more than one story; the lineage below follows the selected story; "All" shows the feature level.

2. **Lineage strip** (the centrepiece). A horizontal flow of nodes with gate markers between them:
   `Feature note` -> `Stories` -> **GATE 1** -> `Design` -> `Design lenses` -> **GATE 2** -> `Build` -> `Sensors` -> `QA + Security` -> `Confidence` -> **GATE 3** -> `Docs + PR` -> `Merged`.
   Node = card with: icon, title, who (agent name in blue, human role in red, tool in orange), one metric (e.g. "3 stories", "confidence 86%", "ArchUnit green", "2 HIGH -> fixed"), time (duration), state dot (done / in progress / failed / not produced). A node not yet produced is drawn grey and dashed. Gate markers are red diamonds with the decision and date ("Approved - TL - 4 Nov"). Clicking a node opens its panel (section 3.2) below the strip; the selected node is highlighted; keyboard: arrow keys move, Enter opens. The strip is an SVG or flex row; connectors are straight; the fail loop (QA Fail -> Build) is drawn as a return arrow with the loop count when > 0.

3. **Detail panel** (one at a time, under the strip, animated height change, respects reduced motion). Content per node in section 3.2. Every panel starts with a **provenance row** rendered from section 2: agent - skills (chips) - profile sections (chips) - wiki pages (chips with commit) - duration - tokens, and a "Open file" link to the artefact (`vscode://file/<abs path>` plus the relative path as text).

4. **"What this feature added to the knowledge base"**  -  three columns, always visible under the panel: **Domain lines added** (each line, its source story, approved by whom), **Rules added** (`/standards record` entries: rule, kind, repo, incident), **Architecture changes** (elements and relationships added/changed, with before -> after counts and a link to the workspace diff). Empty column says "none  -  nothing new was learned in this feature", which is itself information.

5. **Timeline footer.** A thin horizontal time axis with every artefact as a dot (hover = name + timestamp), gates as red ticks, humans' wait time shaded. This is the "where did the time go" view; lead time splits into agent time / waiting for a human / fix loops.

### 3.2 Panels

| Node | Panel content |
| --- | --- |
| Feature note | business summary, scope bullets, author, date; "no technology words" badge when the lint finds none |
| Stories | table: story - Jira type - labels - track - estimate - state - readiness n/9; below it, for the selected story: AC list, **Clarifications as Q -> A -> "added to domain.md as R12"** |
| Design | challenge round (strawman, where it failed, chosen design) as three short blocks; flow-with-impacts rendered (Mermaid source -> embedded SVG via the same pipeline as the design note preview, or the diagram image if pre-rendered; else the text); **C4 delta**: before/after counts and added element names, link to the candidate .dsl; pattern ledger table (class - pattern - force - simpler alternative - verification); design confidence with the rubric rows |
| Design lenses | four/five cards: lens name - verdict - blocking findings count - one-line summary; "fresh context" badge |
| Gate 2 | decision - who - date - rounds - the human's findings text |
| Build | branches per repo with commit list (task -> commit sha -> files); diff shape: lines vs estimate bar, files, new types vs ledger, flags |
| Sensors | table: tool - result (green/red pill) - count - report link; ArchUnit first and labelled mandatory; mutation score when present |
| QA + Security | five lens verdict cards; triage counts (HIGH/MEDIUM/LOW/dismissed); AC table with evidence; data checks (command -> numbers); conformance and domain-fidelity lines; security verdict + findings; **Human findings** text |
| Confidence | score as a gauge, lane, caps listed with evidence, the nine signals as a bar list (points/max + evidence), "missing" list; link to evidence.md |
| Gate 3 | decision - who - date - what they read (evidence only / diff) |
| Docs + PR | change note summary, "Architecture: ..." line, ADRs, PR link, metrics row |
| Merged | merge commit, date, outcome fields when later known (reverted? defect linked?) |

### 3.3 Visual rules (so anyone understands it without a legend)

- Colour carries one meaning only: **red = human decided**, **blue = agent produced**, **orange = tool/sensor computed**, **green = merged / in Git**, grey dashed = not produced yet. Semantic status (pass/fail) is a pill with the word, never colour alone.
- One type scale (28 / 20 / 15 / 13 px), one accent per meaning, generous whitespace, cards only where a thing is clickable. Numbers use tabular figures.
- Every panel opens with the provenance row, so "who did this and from what" is the first thing seen, everywhere.
- Every file path is a link (`vscode://file/...` and a copy button) and shows the relative path in monospace.
- No prose the artefacts do not contain; the generator quotes, it does not summarise. Empty = "not produced".
- First paint shows the whole strip and the Stories panel open; nothing hidden behind scroll-triggered animation.

## 4. `trace.json` (the contract between generator and template; schema `schemas/trace.json`)

```json
{ "feature": {"id":"F-002","title":"...","state":"In progress","author":"PO","date":"2026-11-02","summary":"...","scope":["..."]},
  "people": {"po":"...","techLead":"...","seniorEngineer":"..."},
  "figures": {"storiesDone":1,"storiesTotal":3,"gatesPassed":5,"gatesTotal":9,"leadTimeHours":31.5,"fixLoops":1,"confidenceMedian":86,"lane":"fast"},
  "stories": [ { "id":"S-010","title":"...","jiraType":"Story","labels":["new-api"],"track":"full","estimate":"M","state":"Done","readiness":"9/9",
      "acs":[{"id":"AC1","text":"...","test":"ac1_...","result":"PASS","evidence":"..."}],
      "clarifications":[{"q":"...","a":"...","domainLine":"R12"}],
      "nodes": { "feature":{...},"stories":{...},"gate1":{"decision":"Ready","by":"PO","at":"..."},"design":{...},"designLenses":{...},"gate2":{...},"build":{...},"sensors":{...},"qa":{...},"confidence":{...},"gate3":{...},"docs":{...},"merged":{...} },
      "timeline":[{"artefact":"design","at":"...","kind":"agent"},{"artefact":"gate2","at":"...","kind":"human"}] } ],
  "knowledge": { "domainLines":[{"id":"R12","text":"...","story":"S-010","approvedBy":"PO"}], "rules":[{"name":"...","kind":"ArchUnit","repo":"...","incident":"..."}], "architecture":{"before":{"elements":14,"relationships":22},"after":{"elements":16,"relationships":25},"added":["pricingComponent","orderService -> db (orders)"],"diff":"docs/design/F-002/S-010.dsl"} } }
```
Every node object has `{state: done|in_progress|failed|not_produced, path, who:{kind: agent|human|tool, name}, metric, provenance:{agent,skills,profile,context,graph,commit,started,finished,tokens,more} | null, at, minutes, data:{...panel fields}}`. `path` is relative to the top-level `root` (the central repo's absolute path), which the page uses for `vscode://file/` links. The top level also has `version`, `generated` and `selected`. A finished feature is read from `docs/archive/<F>/<kind>/` (versioning.md section 5) the same way.

## 5. Build steps for the Claude Code session

1. Read this file, `contracts/states.md`, `contracts/confidence.md`, and the agent prompts for artefact section names. Do not change any artefact format; add only the provenance footer rule (section 2) to each agent and the three skills named.
2. `tools/baton/trace/collect.py`: one function per source in section 1 returning the `trace.json` fragments; every parser tolerant (missing -> `null`); unit tests against `fixtures/sample-central-repo/` which must contain one feature, `F-FIX`, with two stories: one `Done` with every artefact, one `Designed` again after a failed QA loop (gate 2 sent back) with a missing mutation.json.
3. `tools/baton/trace/template.html`: static HTML+CSS+JS reading `window.TRACE`; build it first with the fixture JSON hard-coded, make it look right in light and dark at 1280 px and 400 px, then switch to injection. No framework, no CDN.
4. `baton trace <F>`: collect -> validate against `schemas/trace.json` -> inject -> write `docs/trace/<F>.html`; `--open` launches the default browser; `--story` preselects.
5. Wire: `/ship` runs `baton trace <F> --story <S>` after the release agent, so the PR links are on the page; `/sprint-review` prints the trace path first; `/standup` lists features with a trace link.
6. Tests: parser tests per source; a golden `trace.json` for the fixture; an HTML smoke test (file opens, contains every node id, no `undefined`).

## 6. Done when

`baton trace F-FIX` on the fixture produces a page where: every node is clickable and opens the right panel; the failed-QA story shows the return arrow with "1 loop" and a red FAIL pill; the missing mutation shows "not run" without breaking the confidence panel; the knowledge section lists the fixture's one domain line, one rule and the architecture +2/+3; every file path opens in VS Code; the page reads correctly in dark mode and at phone width; a person who has never seen baton can say, from the page alone, who decided what and what the feature taught the system.
