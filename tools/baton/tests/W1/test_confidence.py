"""Scoring: every signal bracket, every threshold boundary, every cap, the lane table, refusals."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from baton import confidence

CLI = Path(__file__).resolve().parents[4] / "tools" / "baton" / "cli.py"
WEIGHTS = """version: 3
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
"""
STORY = """# S-1 Title
Track: {track}
Estimate: S
State: QA Pass

## Acceptance criteria
- AC1: Given a, when b, then c.
- AC2: Given a, when b, then d.

## Readiness
Score: 9/9

## Design review
2026-01-01 human Approved, confidence 90%
"""
REPORT = """# Test report
Conformance: CONFORMS
Craft: 0 high / 0 medium findings
Domain fidelity: 2 rules touched, 2 faithful, 0 reinterpreted

| AC | Test | Result | Evidence |
| --- | --- | --- | --- |
| AC1 | ac1_x | PASS | n=1 |
| AC2 | ac2_y | PASS | n=2 |

## Verdict: PASS
"""
TRIAGE = "# Triage\n\n## Counts\nHIGH: {h}\nMEDIUM: {m}\nLOW: 0\n"
GREEN = "Tests run: 5, Failures: 0, Errors: 0\n"


class Bench:
    def __init__(self, root):
        self.root = root
        self.qa_dir = root / "docs" / "qa" / "F-1"
        (root / "docs" / "stories" / "F-1").mkdir(parents=True)
        (root / "profile").mkdir()
        self.qa_dir.mkdir(parents=True)
        self.diff = {
            "story": "S-1",
            "sensorLoops": 0,
            "newDependencies": [],
            "breakingContract": [],
            "writesCollections": [],
            "repos": [
                {
                    "repo": "svc",
                    "branch": "feature/F-1-S-1",
                    "commits": 2,
                    "linesAdded": 100,
                    "linesDeleted": 50,
                    "files": ["src/main/A.java"],
                }
            ],
        }
        self.impact = {"sourceRepo": "svc", "changedSymbols": [], "impacted": [], "unknownEdges": []}
        self.set_story()
        (root / "profile" / "confidence-weights.yaml").write_text(WEIGHTS)
        (root / "profile" / "risk-zones.yaml").write_text(
            'zones:\n  - name: money\n    paths: ["**/pricing/**"]\n    cap: 50\n'
        )
        (root / "profile" / "project.md").write_text(
            "| estimate.lines.S | 300 |\n| estimate.lines.M | 800 |\n"
        )
        (self.qa_dir / "S-1-test-report.md").write_text(REPORT)
        (self.qa_dir / "S-1-triage.md").write_text(TRIAGE.format(h=0, m=0))
        (self.qa_dir / "S-1-security-report.md").write_text("## Verdict: CLEAR\n")
        (self.qa_dir / "S-1-mutation.json").write_text(
            json.dumps({"repo": "svc", "diffRef": "x", "changedClasses": [], "score": 0.9, "notRun": False})
        )
        sensors = self.qa_dir / "S-1-sensors"
        sensors.mkdir()
        (sensors / "archunit.txt").write_text(GREEN)
        (sensors / "pmd.xml").write_text("<pmd/>")

    def set_story(self, track="light", replace=None):
        text = STORY.format(track=track)
        for old, new in (replace or {}).items():
            text = text.replace(old, new)
        (self.root / "docs" / "stories" / "F-1" / "S-1.md").write_text(text)

    def result(self):
        (self.qa_dir / "S-1-diff-shape.json").write_text(json.dumps(self.diff))
        (self.qa_dir / "S-1-impact.json").write_text(json.dumps(self.impact))
        return confidence.compute(self.root, "S-1")[1]

    def signal(self, name):
        return self.result()["signals"][name]["points"]

    def qa(self, name):
        return self.qa_dir / f"S-1-{name}"


@pytest.fixture
def bench(tmp_path):
    return Bench(tmp_path)


def test_clean_story_scores_100_fast_lane_and_validates(bench, validate):
    document = bench.result()
    validate(document, "confidence.json")
    assert document["score"] == document["raw"] == 100
    assert document["caps"] == [] and document["missing"] == []
    assert document["lane"] == "fast" and document["weightsVersion"] == 3
    for name, signal in document["signals"].items():
        assert signal["points"] == signal["max"], name


def test_every_signal_names_its_source_file(bench):
    for name, signal in bench.result()["signals"].items():
        assert "docs/" in signal["evidence"], f"{name}: {signal['evidence']}"
    bench.qa("mutation.json").unlink()
    assert "docs/qa/F-1/S-1-mutation.json" in bench.result()["signals"]["mutation"]["evidence"]


@pytest.mark.parametrize(
    "body,points",
    [
        ("Score: 9/9", 10),
        ("Score: 8/9", 0),
        ("score = 1.0", 10),
        ("score: 0.89", 0),
        ("Score: 100%", 10),
        ("no number", 0),
    ],
)
def test_definition_of_ready(bench, body, points):
    bench.set_story(replace={"Score: 9/9": body})
    assert bench.signal("definition_of_ready") == points


def test_definition_of_ready_absent(bench):
    bench.set_story(replace={"## Readiness\nScore: 9/9\n": ""})
    document = bench.result()
    assert document["signals"]["definition_of_ready"]["points"] == 0
    assert "story ## Readiness" in document["missing"]


@pytest.mark.parametrize(
    "body,points",
    [
        ("2026-01-01 human Approved", 10),
        ("Changes requested: x\n2026-01-02 human Approved", 5),
        ("auto-passed (light track, confidence 90%)", 8),
        ("auto-passed (hotfix), confidence 90%", 8),
        ("Changes requested: x", 0),
        ("Not Approved", 0),
    ],
)
def test_design_review(bench, body, points):
    bench.set_story(replace={"2026-01-01 human Approved, confidence 90%": body})
    assert bench.signal("design_review") == points


def test_design_review_absent_is_missing(bench):
    bench.set_story(replace={"## Design review\n2026-01-01 human Approved, confidence 90%\n": ""})
    document = bench.result()
    assert (
        document["signals"]["design_review"]["points"] == 0
        and "story ## Design review" in document["missing"]
    )


@pytest.mark.parametrize(
    "added,files,points",
    [
        (300, 5, 10),  # exactly at the estimate, exactly at the file limit
        (300, 6, 5),  # one file over
        (301, 1, 0),  # one line over
        (300, 1, 10),
    ],
)
def test_change_size_boundaries(bench, added, files, points):
    bench.diff["repos"][0].update(
        linesAdded=added, linesDeleted=0, files=[f"f{i}.java" for i in range(files)]
    )
    assert bench.signal("change_size") == points


def test_change_size_counts_deleted_lines_and_all_repos(bench):
    bench.diff["repos"][0].update(linesAdded=200, linesDeleted=101)
    assert bench.signal("change_size") == 0
    bench.diff["repos"] = [
        {"repo": "a", "linesAdded": 100, "files": ["a"]},
        {"repo": "b", "linesAdded": 201, "files": ["b"]},
    ]
    assert bench.signal("change_size") == 0


def test_change_size_no_limit_in_profile(bench):
    bench.set_story(replace={"Estimate: S": "Estimate: L"})
    document = bench.result()
    assert document["signals"]["change_size"]["points"] == 0
    assert "estimate.lines.L in profile/project.md" in document["missing"]


def test_change_size_diff_absent(bench):
    bench.result()
    bench.qa("diff-shape.json").unlink()
    bench.qa("impact.json").write_text(json.dumps(bench.impact))
    document = confidence.compute(bench.root, "S-1")[1]
    assert document["signals"]["change_size"]["points"] == 0 and "diff-shape.json" in document["missing"]
    assert document["lane"] == "tech-lead", "caps cannot be checked without the diff"
    assert "diff-shape.json" in document["laneReason"]


@pytest.mark.parametrize("loops,points", [(0, 10), (1, 6), (2, 6), (3, 0)])
def test_sensor_loops(bench, loops, points):
    bench.diff["sensorLoops"] = loops
    assert bench.signal("sensors") == points


def test_sensor_loops_unknown_scores_zero(bench):
    del bench.diff["sensorLoops"]
    document = bench.result()
    assert (
        document["signals"]["sensors"]["points"] == 0
        and "sensorLoops in diff-shape.json" in document["missing"]
    )


def test_red_sensor_scores_zero(bench):
    bench.qa("sensors/pmd.xml").write_text("<pmd><violation/></pmd>")
    assert bench.signal("sensors") == 0
    bench.qa("sensors/pmd.xml").write_text("<pmd/>")
    (bench.qa("sensors") / "checkstyle.xml").write_text("<error line='1'/>")
    assert bench.signal("sensors") == 0
    (bench.qa("sensors") / "checkstyle.xml").write_text("<checkstyle/>")
    (bench.qa("sensors") / "eslint.json").write_text('[{"errorCount": 1}]')
    assert bench.signal("sensors") == 0
    (bench.qa("sensors") / "eslint.json").write_text("not json")
    assert bench.signal("sensors") == 0
    (bench.qa("sensors") / "eslint.json").write_text('[{"errorCount": 0}]')
    assert bench.signal("sensors") == 10


def test_only_archunit_scores_zero(bench):
    bench.qa("sensors/pmd.xml").unlink()
    assert bench.signal("sensors") == 0


@pytest.mark.parametrize(
    "archunit",
    [None, "Tests run: 5, Failures: 1, Errors: 0\n", "Tests run: 0, Failures: 0, Errors: 0\n", "garbage\n"],
)
def test_archunit_absent_or_red_makes_the_overall_score_zero(bench, archunit, validate):
    if archunit is None:
        bench.qa("sensors/archunit.txt").unlink()
    else:
        bench.qa("sensors/archunit.txt").write_text(archunit)
    document = bench.result()
    validate(document, "confidence.json")
    assert document["score"] == 0 and document["raw"] == 90
    assert [c["name"] for c in document["caps"]] == ["archunit"] and document["caps"][0]["cap"] == 0
    assert "archunit.txt" in document["caps"][0]["evidence"]
    assert document["lane"] == "tech-lead"
    assert ("sensors/archunit.txt" in document["missing"]) is (archunit is None)


@pytest.mark.parametrize("score,points", [(1.0, 10), (0.80, 10), (0.7999, 5), (0.60, 5), (0.5999, 0), (0, 0)])
def test_mutation_boundaries(bench, score, points):
    bench.qa("mutation.json").write_text(json.dumps({"score": score, "notRun": False}))
    assert bench.signal("mutation") == points


def test_mutation_not_run_and_absent(bench):
    bench.qa("mutation.json").write_text(json.dumps({"notRun": True, "reason": "pitest: missing"}))
    assert "pitest: missing" in bench.result()["signals"]["mutation"]["evidence"]
    assert bench.signal("mutation") == 0
    bench.qa("mutation.json").write_text("not json")
    document = bench.result()
    assert document["signals"]["mutation"]["points"] == 0 and "mutation.json" in document["missing"]
    bench.qa("mutation.json").unlink()
    document = bench.result()
    assert document["signals"]["mutation"]["points"] == 0 and "mutation.json" in document["missing"]


@pytest.mark.parametrize(
    "old,new,points",
    [
        ("| AC2 | ac2_y | PASS | n=2 |\n", "", 0),  # an AC of the story has no row
        ("| AC2 | ac2_y | PASS | n=2 |", "| AC2 |  | PASS | n=2 |", 0),  # no test named
        ("| AC2 | ac2_y | PASS | n=2 |", "| AC2 | none | PASS | - |", 0),
        ("| AC2 | ac2_y | PASS | n=2 |", "| AC2 | ac2_y | not run | - |", 0),
        ("| AC2 | ac2_y | PASS | n=2 |", "| AC2 | ac2_y | FAIL | n=3 |", 10),  # executed, and failed
    ],
)
def test_acceptance_coverage(bench, old, new, points):
    bench.qa("test-report.md").write_text(REPORT.replace(old, new))
    assert bench.signal("acceptance_coverage") == points


def test_report_absent(bench):
    bench.qa("test-report.md").unlink()
    document = bench.result()
    assert document["signals"]["acceptance_coverage"]["points"] == 0
    assert document["signals"]["conformance_fidelity"]["points"] == 0
    assert "test-report.md" in document["missing"]


@pytest.mark.parametrize("high,medium,points", [(0, 0, 15), (0, 3, 10), (1, 0, 0), (2, 5, 0)])
def test_independent_review(bench, high, medium, points):
    bench.qa("triage.md").write_text(TRIAGE.format(h=high, m=medium))
    assert bench.signal("independent_review") == points


def test_triage_without_counts_is_not_assumed_clean(bench):
    bench.qa("triage.md").write_text("# Triage\nlooks fine\n")
    document = bench.result()
    assert (
        document["signals"]["independent_review"]["points"] == 0
        and "## Counts in triage.md" in document["missing"]
    )
    bench.qa("triage.md").unlink()
    assert "triage.md" in bench.result()["missing"]


@pytest.mark.parametrize(
    "conformance,reinterpreted,points",
    [
        ("CONFORMS", 0, 10),
        ("CONFORMS WITH DOCUMENTED DEVIATIONS", 0, 5),
        ("DEVIATES", 0, 0),
        ("CONFORMS", 1, 0),
        ("CONFORMS WITH DOCUMENTED DEVIATIONS", 2, 0),
        ("CONFORMS | CONFORMS WITH DOCUMENTED DEVIATIONS | DEVIATES", 0, 0),  # the unfilled template
    ],
)
def test_conformance(bench, conformance, reinterpreted, points):
    text = REPORT.replace("Conformance: CONFORMS", f"Conformance: {conformance}").replace(
        "0 reinterpreted", f"{reinterpreted} reinterpreted"
    )
    bench.qa("test-report.md").write_text(text)
    assert bench.signal("conformance_fidelity") == points


def impacted(*repos, breaking=False):
    return [
        {"repo": r, "via": "collection:x", "file": "A.java", "lines": "1-2", "breaking": breaking}
        for r in repos
    ]


@pytest.mark.parametrize(
    "repos,points", [((), 15), (("a",), 8), (("a", "b"), 8), (("a", "a", "b"), 8), (("a", "b", "c"), 0)]
)
def test_blast_radius(bench, repos, points):
    bench.impact["impacted"] = impacted(*repos)
    assert bench.signal("blast_radius") == points


def test_blast_radius_absent_or_not_run(bench):
    bench.impact = {"notRun": True}
    assert bench.signal("blast_radius") == 0
    bench.result()
    bench.qa("impact.json").unlink()
    (bench.qa_dir / "S-1-diff-shape.json").write_text(json.dumps(bench.diff))
    document = confidence.compute(bench.root, "S-1")[1]
    assert document["signals"]["blast_radius"]["points"] == 0 and "impact.json" in document["missing"]
    assert document["lane"] == "tech-lead"


def caps(document):
    return {c["name"]: c["cap"] for c in document["caps"]}


def test_cap_risk_zone(bench):
    bench.diff["repos"][0]["files"] = ["src/pricing/Fee.java"]
    document = bench.result()
    assert caps(document) == {"risk_zone": 50} and document["score"] == 50 and document["raw"] == 100
    assert "src/pricing/Fee.java matches money" in document["caps"][0]["evidence"]
    assert document["lane"] == "tech-lead"


def test_cap_risk_zone_lowest_wins(bench):
    (bench.root / "profile" / "risk-zones.yaml").write_text(
        'zones:\n  - name: a\n    paths: ["**/x/**"]\n    cap: 55\n  - name: b\n    paths: ["**/*.java"]\n    cap: 30\n'  # noqa: E501
    )
    bench.diff["repos"][0]["files"] = ["src/x/A.java"]
    assert caps(bench.result()) == {"risk_zone": 30}


@pytest.mark.parametrize(
    "pattern,path,hit",
    [
        ("**/outbound/**", "src/outbound/A.java", True),
        ("**/outbound/**", "outbound/A.java", True),
        ("**/outbound/**", "src/outboundx/A.java", False),
        ("**/*Writer*", "a/b/FileWriter.java", True),
        ("*.yml", "deep/x.yml", True),
        ("src/*.yml", "src/x.yml", True),
        ("src/*.yml", "src/a/x.yml", False),
        ("**/*Fee*", "Fee.java", True),
        ("security/", "security/A.java", True),
        ("security/", "a/security/A.java", True),
    ],
)
def test_gitignore_style_globs(pattern, path, hit):
    assert bool(confidence.glob_regex(pattern).match(path)) is hit


def test_cap_breaking_from_diff_and_impact(bench):
    bench.diff["breakingContract"] = ["GET /x removed"]
    assert caps(bench.result()) == {"breaking_contract": 40}
    bench.diff["breakingContract"] = []
    bench.impact["impacted"] = impacted("a", breaking=True)
    document = bench.result()
    assert caps(document) == {"breaking_contract": 40} and document["score"] == 40


def test_cap_unknown_edges(bench):
    bench.impact["unknownEdges"] = ["queue:Q has no known consumer in graph"]
    document = bench.result()
    assert caps(document) == {"unknown_edges": 70} and "queue:Q" in document["caps"][0]["evidence"]


def test_cap_new_dependency(bench):
    bench.diff["newDependencies"] = ["org.x:y:1"]
    assert caps(bench.result()) == {"new_dependency": 70}


def test_new_dependency_field_absent_is_missing(bench):
    del bench.diff["newDependencies"]
    assert "newDependencies in diff-shape.json" in bench.result()["missing"]


def profile_doc(root, name, unprofiled):
    folder = root / "docs" / "data-profile"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps({"collection": name, "unprofiled": unprofiled}))


def test_cap_unprofiled_from_diff_shape(bench):
    bench.diff["writesCollections"] = ["orders"]
    profile_doc(bench.root, "orders", True)
    document = bench.result()
    assert caps(document) == {"unprofiled_write": 60} and "orders" in document["caps"][0]["evidence"]
    profile_doc(bench.root, "orders", False)
    assert caps(bench.result()) == {}


def test_cap_unprofiled_when_no_profile_exists(bench):
    bench.diff["writesCollections"] = ["collection:orders"]
    document = bench.result()
    assert (
        caps(document) == {"unprofiled_write": 60}
        and "no docs/data-profile/orders.json" in document["caps"][0]["evidence"]
    )


def test_cap_unprofiled_from_dependency_edges(bench):
    (bench.root / "profile" / "dependencies.yaml").write_text(
        "repos:\n  - repo: svc\n    commit: a\n    edges:\n      - kind: WRITES_COLLECTION\n        from: class:A\n"  # noqa: E501
        "        to: collection:orders\n        provenance: {file: src/main/A.java, line: 1, extractor: x}\n"
    )
    assert caps(bench.result()) == {"unprofiled_write": 60}
    bench.diff["repos"][0]["files"] = ["src/main/Other.java"]
    assert caps(bench.result()) == {}


def test_reading_a_collection_does_not_cap(bench):
    (bench.root / "profile" / "dependencies.yaml").write_text(
        "repos:\n  - repo: svc\n    commit: a\n    edges:\n      - kind: READS_COLLECTION\n        from: class:A\n"  # noqa: E501
        "        to: collection:orders\n        provenance: {file: src/main/A.java, line: 1, extractor: x}\n"
    )
    assert caps(bench.result()) == {}


def test_lowest_cap_wins_and_all_are_listed(bench):
    bench.diff["newDependencies"] = ["x"]
    bench.diff["breakingContract"] = ["y"]
    bench.impact["unknownEdges"] = ["z"]
    document = bench.result()
    assert caps(document) == {"breaking_contract": 40, "unknown_edges": 70, "new_dependency": 70}
    assert document["score"] == 40


def test_risk_zones_absent_is_missing_and_blocks_fast(bench):
    (bench.root / "profile" / "risk-zones.yaml").unlink()
    document = bench.result()
    assert "risk-zones.yaml" in document["missing"] and document["lane"] == "tech-lead"


@pytest.mark.parametrize(
    "score,capped,blind,track,lane",
    [
        (85, False, [], "light", "fast"),
        (84.99, False, [], "light", "senior"),
        (85, False, [], "full", "senior"),
        (100, False, [], "full", "senior"),
        (60, False, [], "light", "senior"),
        (60, False, [], "full", "senior"),
        (59.99, False, [], "light", "tech-lead"),
        (59.99, False, [], "full", "tech-lead"),
        (100, True, [], "light", "tech-lead"),
        (100, False, ["impact.json"], "light", "tech-lead"),
        (100, False, [], "spike", "senior"),
    ],
)
def test_lane_table(score, capped, blind, track, lane):
    assert (
        confidence.lane_for(score, capped, blind, track, {"fast_lane_min": 85, "senior_min": 60})[0] == lane
    )


def test_full_track_story_at_100_goes_to_senior(bench):
    bench.set_story(track="full (escalated: new field)")
    document = bench.result()
    assert document["track"] == "full" and document["lane"] == "senior"


def test_track_missing_counts_as_full_and_missing(bench):
    bench.set_story(replace={"Track: light\n": ""})
    document = bench.result()
    assert document["track"] == "full" and "story Track" in document["missing"]


def test_weights_are_read_from_the_file(bench):
    text = WEIGHTS.replace("mutation: 10", "mutation: 20").replace("sensors: 10", "sensors: 0")
    (bench.root / "profile" / "confidence-weights.yaml").write_text(text)
    document = bench.result()
    assert document["signals"]["mutation"]["max"] == 20 and document["signals"]["sensors"]["max"] == 0


def cli(root, *args):
    return subprocess.run(
        [sys.executable, str(CLI), "confidence", "--central", str(root), *args],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "text",
    [
        WEIGHTS.replace("mutation: 10", "mutation: 11"),
        WEIGHTS.replace("mutation: 10", "mutation: 9"),
        WEIGHTS.replace("  mutation: 10\n", ""),
        WEIGHTS.replace("mutation: 10", "mutation: ten"),
        WEIGHTS.replace("  risk_zone: 50\n", ""),
        WEIGHTS.replace("  fast_lane_min: 85\n", ""),
        "just: words\n",
        "bad yaml without colon\n  more\n",
        "",
    ],
)
def test_unusable_weights_are_refused_and_no_file_is_written(bench, text):
    (bench.root / "profile" / "confidence-weights.yaml").write_text(text)
    done = cli(bench.root, "S-1")
    assert done.returncode == 2
    assert "refused" in done.stderr
    assert not bench.qa("confidence.json").exists()
    for number in ("11", "85", "50"):
        assert number not in done.stderr, "the refusal must not reveal weights"


def test_weights_file_absent_is_refused(bench):
    (bench.root / "profile" / "confidence-weights.yaml").unlink()
    assert cli(bench.root, "S-1").returncode == 2


def test_unknown_story_is_refused(bench):
    assert cli(bench.root, "S-404").returncode == 2


def test_nothing_at_all_still_exits_zero(tmp_path, validate):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "confidence-weights.yaml").write_text(WEIGHTS)
    (tmp_path / "docs" / "stories" / "F-1").mkdir(parents=True)
    (tmp_path / "docs" / "stories" / "F-1" / "S-1.md").write_text("# S-1\nState: Draft\n")
    done = cli(tmp_path, "S-1", "--json")
    assert done.returncode == 0, done.stderr
    document = json.loads(done.stdout)
    validate(document, "confidence.json")
    assert document["score"] == 0 and document["lane"] == "tech-lead"
    assert len(document["missing"]) >= 6
    written = json.loads((tmp_path / "docs" / "qa" / "F-1" / "S-1-confidence.json").read_text())
    validate(written, "confidence.json")


def test_story_with_a_slug_and_ambiguous_prefix(tmp_path):
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "confidence-weights.yaml").write_text(WEIGHTS)
    folder = tmp_path / "docs" / "stories" / "backlog"
    folder.mkdir(parents=True)
    (folder / "S-1-a-slug.md").write_text("State: Draft\n")
    (folder / "S-10.md").write_text("State: Draft\n")
    assert cli(tmp_path, "S-1").returncode == 0
    assert (tmp_path / "docs" / "qa" / "backlog" / "S-1-confidence.json").is_file()
    (folder / "S-1-other.md").write_text("State: Draft\n")
    assert cli(tmp_path, "S-1").returncode == 2


def test_weights_file_shipped_in_the_contract_is_accepted(bench, validate):
    from baton import miniyaml

    validate(miniyaml.loads(WEIGHTS), "confidence-weights.json")


def test_multi_repo_story_needs_impact_and_mutation_for_every_repo(bench):
    bench.diff["repos"].append({"repo": "other", "linesAdded": 1, "files": ["B.java"]})
    document = bench.result()
    assert document["signals"]["blast_radius"]["points"] == 0
    assert document["signals"]["mutation"]["points"] == 0
    assert "impact.json for other" in document["missing"] and "mutation.json for other" in document["missing"]
    assert document["lane"] == "tech-lead"
    (bench.qa_dir / "S-1-impact-other.json").write_text(
        json.dumps(
            {
                "sourceRepo": "other",
                "changedSymbols": [],
                "impacted": impacted("x", "y", "z"),
                "unknownEdges": ["queue:Q"],
            }
        )
    )
    (bench.qa_dir / "S-1-mutation-other.json").write_text(
        json.dumps({"repo": "other", "score": 0.61, "notRun": False})
    )
    bench.qa("mutation.json").write_text(json.dumps({"repo": "svc", "score": 0.9, "notRun": False}))
    document = bench.result()
    assert document["signals"]["blast_radius"]["points"] == 0, "repos add up across files"
    assert document["signals"]["mutation"]["points"] == 5, "the lowest repo decides"
    assert caps(document) == {"unknown_edges": 70}


@pytest.mark.parametrize(
    "risk,points",
    [
        ({"tier": "low", "lenses": ["conformance", "verification-gap"]}, 10),  # domain lens skipped by tier
        ({"tier": "low", "lenses": ["conformance", "verification-gap", "domain"]}, 0),  # it should have run
        ({"tier": "medium", "lenses": ["edge-case", "verification-gap", "craft", "conformance", "domain"]},
         0),
        (None, 0),  # no risk.json: a missing fidelity line is not excused
    ],
)
def test_domain_lens_skipped_only_when_the_risk_tier_says_so(bench, risk, points):
    text = REPORT.replace(
        "Domain fidelity: 2 rules touched, 2 faithful, 0 reinterpreted", "Domain fidelity: not run (low risk)"
    )
    bench.qa("test-report.md").write_text(text)
    if risk:
        bench.qa("risk.json").write_text(json.dumps({"story": "S-1", **risk}))
    assert bench.signal("conformance_fidelity") == points
