# Gate-3 confidence

`baton confidence <story-id>` writes `docs/qa/<F>/<S>-confidence.json` (schema `schemas/confidence.json`). `baton evidence <story-id>` writes `-evidence.md` from what exists. `/build` runs both at step 6a.

## Exit codes
- **0** for any score, including a story with no artefacts: everything scores 0 and appears in `missing`.
- **2, no file written**: `profile/confidence-weights.yaml` is absent, unparsable, lacks a required key, or its signals are not exactly the nine and do not sum to 100; or the story does not exist or its id is ambiguous. The contract says both "exit 0 always" and "the tool refuses otherwise"; a score computed from bad weights would be misleading, so refusal wins. The message never prints a weight.

## Signals
Point tables are in plan §4.8. They are applied as fractions of the weight, so a recalibrated weight keeps the shape.

| Signal | Reads |
| --- | --- |
| `definition_of_ready` | story `## Readiness`, a `Score:` of 9/9, 1.0 or 100% |
| `design_review` | story `## Design review` |
| `change_size` | `-diff-shape.json`, story `Estimate:`, `estimate.lines.<E>` in `profile/project.md`. Lines = added + deleted, all repos |
| `sensors` | `-sensors/*`, `sensorLoops` in `-diff-shape.json`. Unknown loops score 0 |
| `mutation` | `-mutation.json`, or `-mutation-<repo>.json` per repo; the lowest score decides |
| `acceptance_coverage` | AC table in `-test-report.md` against the story's ACs. Every AC needs a named test with result PASS or FAIL |
| `independent_review` | `## Counts` block in `-triage.md`. No block scores 0 |
| `conformance_fidelity` | `Conformance:` and `Domain fidelity:` in the test report. An unfilled template line scores 0 |
| `blast_radius` | `-impact.json`, or `-impact-<repo>.json` per repo; impacted repos add up |

## `-diff-shape.json`
Written by `/build`; no schema file exists because `schemas/` is frozen and the contract only names the file. Fields: `story`, `sensorLoops`, `newDependencies`, `breakingContract`, `writesCollections`, `yagniCount`, and `repos[]` of `repo`, `branch`, `commits`, `linesAdded`, `linesDeleted`, `files`. The example is in `skills/build/SKILL.md`.

## Caps
| Cap | Fires when | Value from |
| --- | --- | --- |
| `archunit` | `archunit.txt` absent or red | 0 (the overall score is 0; the raw sum is kept) |
| `risk_zone` | a diff file matches a zone | the zone's `cap` in `risk-zones.yaml`, lowest wins |
| `breaking_contract` | `breakingContract` in the diff shape, or `breaking: true` in impact | weights |
| `unprofiled_write` | a written collection is `unprofiled: true`, or has no profile file | weights |
| `unknown_edges` | `unknownEdges` is non-empty | weights |
| `new_dependency` | `newDependencies` is non-empty | weights |

**Which collections a story writes** is the union of `writesCollections` in the diff shape and every `WRITES_COLLECTION` edge in `profile/dependencies.yaml` whose `provenance.file` is in the diff, same repo. A collection with no `docs/data-profile/<c>.json` counts as unprofiled.

## Lane
| Condition | Lane |
| --- | --- |
| any cap | tech-lead |
| `-diff-shape.json`, `risk-zones.yaml` or impact absent or not run, so caps could not be checked | tech-lead |
| below `senior_min` | tech-lead |
| at or above `fast_lane_min`, track light | fast |
| otherwise | senior |

The second row is an addition: without it a story with no diff could reach the fast lane, since the absent caps would look like none. `laneReason` in the JSON states which row applied; it is an additive field, which the schema permits.

## evidence.md
Sections exactly: Story, Design, Build, Verification, Security, Blast radius, Confidence, What was NOT done, Links. Every value line names its source file, by `(source: …)` or a Source column. It does not read the weights.

Who may see what: agents never read the yaml. `confidence.json` carries `points` and `max` per signal, as the contract requires; see [known-limitations.md](known-limitations.md).
