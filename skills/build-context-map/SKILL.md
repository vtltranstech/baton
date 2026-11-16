---
name: build-context-map
description: Build the context map the way a new engineer learns a system - read the documents, the domain, the code and the architecture diagrams, area by area with context explorers in parallel, join the areas into end-to-end flows and the landscape of upstream and downstream systems, and stop to ask a human whatever cannot be found. This is gate 0: /stories, /ready and /build run nothing on an area it does not understand, and run it themselves (focus) when it refuses. Run after /onboard. Use as /build-context-map [setup|focus <F-id|area>|refresh|status].
---
Build the context map: $ARGUMENTS (setup | focus <F-id or area> | refresh | status; default setup).

Read the `workflow` skill and `contracts/context-map.md` sections 4 and 10 first. `baton <cmd>` is as the `workflow` skill says, run from the central repo.

The agents here are new engineers, and they are held to it: nothing is understood because an agent says so. `baton context understand` grades every note against the code (each claim must be an edge the extractors found, with a citation that resolves; each flow step joined to the next; each entry point inside a flow), and an area with a blocking question no human has answered is not understood. Never edit a note to make it pass, never answer an agent's question yourself, and never mark a draft or a rule confirmed: only the Product Owner (domain) and the Tech Lead (systems) do that.

## Run by another skill (gate 0)
`/stories`, `/ready` and `/build` run this skill as `focus <F-id>` when `baton context check` refuses their work because of an area (`not-understood`, `question`, `contradiction` or `boundary-unknown` gaps). Do steps 2 to 7 for that feature only, ask the human present (step 6), and end by printing the check's verdict on one line, `GATE 0: accepted` or `GATE 0: refused - <the areas and who must answer>`, so the calling skill knows whether to go on. Skip step 1 unless the human names a new document.

## Progress and failure rules
- Print a one-line marker before each step ("Step 3 - exploring 4 areas, wave 1 of 2") and a one-line result after it. A run never goes silent.
- Subagents run in the FOREGROUND, at most `explore-parallel` of them (in `profile/context.yaml`, default 4) in one message. Wait for every one, then read each note back; print a checklist: area -> written | failed. A failed or missing note is retried once as a new subagent; if it fails again, report it and go on with the others. Never assume an agent wrote a file.
- Ask before writing anything outside `docs/context/`. Never commit.

## 0. Preconditions
`profile/stack-detected.md` and `profile/dependencies.yaml` must exist: if either is missing, stop and say "run /onboard first". Say whether `docs/architecture/diagrams/diagrams.md` exists; without it the explorers cannot compare the code with the architecture, so suggest `baton diagram architecture` and go on.

## 1. Documents and drafts (setup and refresh)
If the humans named documents in /onboard or now (Word, PowerPoint, Excel, PDF, scans and images, Markdown or text files), add their paths to `doc-sources` in `profile/context.yaml`. If they named Confluence pages or spaces and a Confluence MCP server is connected, fetch each page with it (search a space for its pages first; at most the pages they named, or a space they named), and write each page body exactly as returned to `docs/legacy/confluence/<space>/<page-id>-<slug>.html` with the first line `<!-- confluence: <page url> version <n> -->`. Never rewrite or summarise a page body; skip a page whose saved file already has that version. Then add `docs/legacy/confluence/**` to `doc-sources`. No MCP server: ask for an HTML export of the space instead.

Run `baton context ingest` and report its `OCR:` line: when OCR is not available, say which images and scanned pages were not read, and that the tesseract binary and language files must come from the organisation's mirror. Never download them, and never suggest a download. Show the files the index lists as not read; never guess their content. Then `baton context build` and `baton context score` (they write `profile/branch-points.yaml`, `profile/domain-drafts.md`, `docs/context/context-map.*` and `docs/context/modules/`; say so before running).

## 2. Plan
Run `baton context understand`. It lists every area (a module) as unexplored, stale, incomplete, blocked or understood, and writes `docs/context/understanding/status.md`. The areas to explore are those not understood and not blocked:
- **setup:** all of them, highest-impact first (`interviewOrder` in `docs/context/context-map.json`).
- **focus F-001:** run `baton context check F-001 --no-write`; the areas it lists as changed, then those within two hops. **focus <area>:** that area.
- **refresh:** the stale ones (their own code changed since the note was written) and the incomplete ones.
- **status:** print the `understand` summary and the open questions, and stop.

## 3. Explore (parallel)
For each area, run the `context-explorer` agent with the area key and the round number. In a later round, pass it the area's problems from `status.md`: it fixes exactly those. Waves of at most `explore-parallel`.

## 4. Join the areas
Run the `context-integrator` agent once, after every wave of the round. It writes the flows under `docs/context/understanding/flows/` and `docs/context/understanding/landscape.md`.

## 5. Grade, then go round again
Run `baton context understand`. An area that is incomplete only because of the grader's problems goes back to step 3 with them, at most `explore-rounds` rounds in all (in `profile/context.yaml`, default 3). After the last round, an area still incomplete is reported with its problems; never fix a note yourself.

## 6. Stop and ask
Collect the open questions from `status.md`: blocking first, Product Owner questions on rules and words, then Tech Lead questions on systems, highest-impact area first, and stop at `interview-cap-minutes` (default 60). Ask with AskUserQuestion, up to 4 per round, the agent's question verbatim with the evidence it cites and, for a branch point, the proposed rule when there is one. For each answer:
- Write it under the question in the note, flow or landscape it came from, as `  answer: <the human's words> (<role>, <date>)`. Verbatim; never shortened.
- When it settles a rule, and the Product Owner says yes to writing it: a named rule goes into `rule:` of that branch point in `profile/branch-points.yaml`; a new rule into `profile/domain.md` as `### R<n>` with `fields:`, `source:` and `confirmed: true`. A word goes into the `## Domain words` table with its definition and `confirmed: true`. A system goes in `profile/project.md` under `## Onboard answers`. Show each of these writes as a diff first.
- A draft in `profile/domain-drafts.md` that the PO confirms gets `confirmed: true` in place, and moves into `profile/domain.md` as the next `R<n>`.

Contradictions (`- C<n>:` under `## Contradictions` of a note) block their area whatever the track. Ask the Tech Lead which is right, the document or the code; write the answer as `  resolved: <words> (TL, <date>)` under it (`baton context answer <area> C<n> "<words>" --by TL` does exactly that). When the code is wrong, say a story must be raised; never change the code or the document here.

Human absent or "not now": stop here and report what is waiting, by area and by person, and run `baton context questions` (it writes `docs/context/questions.md`, which /standup prints; each person can answer later with `baton context answer`, without a session). The questions stay in the notes, and the next run starts from them. Never answer one yourself, and never guess.

## 7. Fold the answers in
Run the `context-explorer` again for each area that got an answer (it folds the answer into the note and drops what it settled), then the integrator if a system was named, then `baton context build` if a rule was written, then `baton context understand`. Go back to step 6 while there are answers to fold in and questions to ask.

## 8. Close
Run `baton context score` and print its readiness lines and the `## System understanding` line. Then say, per feature under `docs/features/` that has no stories yet, what `baton context check <F-id> --no-write` says: accepted for story drafting, or which areas and questions keep it out. Say what was left unexplored and why.
