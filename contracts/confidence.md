# Confidence contract (gate 3)

## Inputs (all under the central repo; a missing input scores its signal 0 and is listed under `missing`)
story `docs/stories/<F>/<S>.md` (Readiness score, Design review, Track, Estimate) - `docs/qa/<F>/<S>-diff-shape.json` - `docs/qa/<F>/<S>-sensors/*` - `-mutation.json` - `-test-report.md` (AC table, Conformance, Domain fidelity) - `-triage.md` - `-security-report.md` - `-impact.json` - `profile/risk-zones.yaml` - `profile/confidence-weights.yaml` - `docs/data-profile/*.json` (for the unprofiled cap).

## `profile/confidence-weights.yaml` (schema `confidence-weights.json`; owned by the Senior Engineer; the protect-weights hook refuses agent reads)
```yaml
version: 1
signals:
  definition_of_ready: 10
  design_review: 10
  change_size: 10
  sensors: 10
  mutation: 10
  acceptance_coverage: 10
  independent_review: 15
  conformance_fidelity: 10
  blast_radius: 15
caps:
  risk_zone: 50
  breaking_contract: 40
  unprofiled_write: 60
  unknown_edges: 70
  new_dependency: 70
policy:
  fast_lane_min: 85
  senior_min: 60
thresholds:
  change_size_files: 5
  mutation_full: 0.80
  mutation_half: 0.60
  sensors_loops_half: 2
```
Signals must sum to 100 (the tool refuses otherwise). Scoring rules per signal (initial points; the Senior Engineer owns the weights):

| Signal | How measured (artefact) | Points |
| --- | --- | --- |
| Definition of Ready | story `## Readiness` score = 1.0 | 10 |
| Design review | `## Design review`: Approved first round 10; approved after changes 5; auto-pass 8 | 10 |
| Change size | `-diff-shape.md`: <= estimate and <= 5 files 10; <= estimate 5; over 0 | 10 |
| Sensors | `-sensors/`: all green first try 10; green after <= 2 loops 6; else 0; `archunit.txt` absent or red: 0 | 10 |
| Mutation score (changed classes) | `mutation.json`: >= 80% 10; >= 60% 5; else 0; not run 0 | 10 |
| Acceptance coverage | test report AC table: every AC has an executing test | 10 |
| Independent review | `-triage.md`: no HIGH/MEDIUM 15; MEDIUM only 10; any HIGH 0 | 15 |
| Conformance + domain fidelity | CONFORMS and 0 reinterpreted 10; documented deviations 5; DEVIATES or reinterpreted 0 | 10 |
| Blast radius | `impact.json`: 0 impacted repos 15; 1-2 8; more 0; not run 0 | 15 |

Hard caps after summing: touches a `risk-zones.yaml` path 50; breaking contract change (endpoint signature or DTO field removed) 40; writes an `unprofiled` collection 60; `impact.json.unknownEdges` non-empty 70; new dependency in a build file 70.

Policy (initial; promoted only through calibration):

| Score | Track light | Track full |
| --- | --- | --- |
| >= 85, no caps | fast lane: the Senior Engineer reads `evidence.md`, the Tech Lead approves on it | the Senior Engineer reviews diff and reports; the TL approves |
| 60-84 | the Senior Engineer reviews and recommends; the TL approves | same |
| < 60 or any cap | the Tech Lead reads the diff; the agent explains the lowest signals; the design may go back | same, plus a design revisit |

The author is always the agent identity, the approver a human. A merge approved by one developer alone is a later promotion earned per repo (20 consecutive >= 85 PRs with no negative outcome; demoted on any incident). Calibration: `confidence.json` is stored with every PR; outcomes are joined monthly (revert within 30 days, linked defect, hotfix on the same files) and the Senior Engineer adjusts the weights.

## Output `docs/qa/<F>/<S>-confidence.json` (schema `confidence.json`)
```json
{ "story": "S-010", "track": "full", "computedAt": "...", "weightsVersion": 1,
  "signals": { "definition_of_ready": {"points": 10, "max": 10, "evidence": "Readiness 9/9"},
               "mutation": {"points": 0, "max": 10, "evidence": "mutation.json not present"} },
  "raw": 72, "caps": [ {"name": "risk_zone", "cap": 50, "evidence": "src/main/java/.../ExportFileWriter.java matches outbound-core-file"} ],
  "score": 50, "lane": "tech-lead", "missing": ["mutation.json", "impact.json"] }
```
`lane` in `fast | senior | tech-lead` from the policy and the track. `exit 0` always; the score is information for humans, never a gate by itself.

## `docs/qa/<F>/<S>-evidence.md` (`baton evidence`)
Sections in this order: Story (title, track, estimate, PO) - Design (confidence, review outcome, rounds, C4 delta summary) - Build (branches, commits, lines, files, sensors table with green/red per tool, loops) - Verification (AC table from the test report, data checks, mutation score, lenses verdicts, triage counts HIGH/MEDIUM/LOW) - Security (verdict, findings) - Blast radius (impacted repos table, unknown edges) - Confidence (score, lane, caps, lowest three signals with their evidence) - What was NOT done (every `missing` input, "end-to-end test not executed") - Links to every artefact. Every number cites the file it came from. No prose the artefacts do not support.
