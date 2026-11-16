---
name: impact
description: Blast radius of a story across repos with `baton impact`, and how to read impact.json. Use when a design or a diff needs its cross-repo impact, or asked "what does this change break".
---
Compute the blast radius of a change: $ARGUMENTS

Run from the central repo. The graph reloads itself when `profile/dependencies.yaml` changed.

```text
baton impact --repo <repo> --diff <file|ref> --json [--out docs/qa/<F>/<S>-impact.json]
```

| You have | `--diff` | Who |
| --- | --- | --- |
| a design note's file list, one file per repo | a text file: one path per line (`../<repo>/path` accepted), plus `topic:x`-style ids and `breaking: <Class.field or id>` for what the design removes | architect, before the challenge round |
| a branch | `main...HEAD`, diffed in `../<repo>` | /build, after the developer, with `--out` |
| a saved unified diff | its path | anyone |

Run once per repo the story touches. `docs/qa/<F>/<S>-impact.json` is one file and holds one source repo, so a multi-repo story needs a distinct `--out` for each extra repo; report every result.

Reading it:
- `impacted[]`: `repo`, `via` (the shared collection, endpoint, topic or file), exact `file` and `lines`, `team` if the profile names one. Quote these as they are; never add or drop a row by judgement.
- `breaking: true`: the changed symbol is a removed or renamed field, an endpoint signature, or a topic schema or name.
- `unknownEdges`: the other side is not in the graph. Each caps the gate-3 confidence; ask who owns it rather than assuming nobody.
- Depth 2 entries are conservative: everything a depth-1 repo produces is followed, so some may be unrelated. Say so instead of removing them.

Exit 2 means missing input (no graph, unknown repo, bad ref): report it, do not write an empty impact file. The confidence signal treats a missing file as `not run`, which is the truth.

Inside Claude Code the same answers come from the read-only MCP tools `graph.impact`, `graph.callers`, `graph.collections`.
