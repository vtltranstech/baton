"""Drives the real builds: every planted violation is caught with REMEDIATION:, clean passes, PIT scores.

Run with BATON_SLOW=1. Needs JDK 17 and 21, gradle and node; Maven comes from the fixture's wrapper.
"""
import json
import os
import subprocess
import xml.etree.ElementTree as ET

import jsonschema
import pytest
from baton import cli
from w6support import JAVA_FIXTURE, REACT_FIXTURE, ROOT, copy_fixture, git, java_home

pytestmark = pytest.mark.slow
JAVA_MANIFEST = json.loads((JAVA_FIXTURE / "violations/MANIFEST.json").read_text())
REACT_MANIFEST = json.loads((REACT_FIXTURE / "violations/MANIFEST.json").read_text())
BUILD_CHECKS = [(v["patch"], c) for v in JAVA_MANIFEST["violations"] for c in v["checks"]
                if c["sensor"] != "new-dependency"]
MUTATION_SCHEMA = json.loads((ROOT / "schemas/mutation.json").read_text())
FEE_CALCULATOR = "com.example.sample.application.service.FeeCalculator"
FEE_CALCULATOR_PATH = "src/main/java/com/example/sample/application/service/FeeCalculator.java"
NOTE_SERVICE_PATH = "src/main/java/com/example/samplegradle/application/service/NoteService.java"


def build_env(java):
    return {**os.environ, "JAVA_HOME": java_home(java)}


def mvn(repo, *args, java=21):
    return subprocess.run(["./mvnw", "-B", "verify", *args], cwd=repo, env=build_env(java),
                          capture_output=True, text=True)


def _remediations(check, reports):
    """The report entries for this very rule that say REMEDIATION:, not merely both words somewhere."""
    if check["sensor"] == "archunit":
        lines = [line for report in reports for line in report.read_text().splitlines()]
        return [line for line in lines if "REMEDIATION:" in line and check["rule"] in line]
    found = []
    for report in reports:
        for element in ET.parse(report).getroot().iter():
            rule = element.get("rule", "") if check["sensor"] == "pmd" else element.get("source", "")
            text = (element.text or "") if check["sensor"] == "pmd" else element.get("message", "")
            if check["rule"] in rule and "REMEDIATION:" in text:
                found.append(text.strip())
    return found


@pytest.mark.parametrize("java", [21, 17])
def test_clean_maven_fixture_is_green_with_all_sensors(tmp_path, java):
    repo = copy_fixture(JAVA_FIXTURE, tmp_path / "repo")
    done = mvn(repo, f"-Djava.version={java}", java=java)
    assert done.returncode == 0, done.stdout[-3000:]
    surefire = repo / "target/surefire-reports"
    reports = "".join(p.read_text() for p in surefire.glob("*ArchitectureTest*.txt"))
    assert "Failures: 0, Errors: 0" in reports
    assert "ProjectArchitectureTest" in reports and "com.example.sample.ArchitectureTest" in reports
    assert (repo / "target/pmd.xml").is_file() and (repo / "target/checkstyle-result.xml").is_file()
    assert "<violation" not in (repo / "target/pmd.xml").read_text()


@pytest.mark.parametrize("patch,check", BUILD_CHECKS, ids=[f"{p}-{c['sensor']}" for p, c in BUILD_CHECKS])
def test_violation_fails_the_build_with_remediation_in_the_report(tmp_path, patch, check):
    repo = copy_fixture(JAVA_FIXTURE, tmp_path / "repo")
    git(repo, "apply", f"violations/{patch}")
    done = mvn(repo, *check["args"])
    assert done.returncode != 0, f"{patch} did not fail the build"
    reports = list(repo.glob(check["report"]))
    assert reports, f"no report at {check['report']}"
    caught = _remediations(check, reports)
    assert caught, f"{patch}: {check['rule']} has no REMEDIATION in {reports}"


def _pit_repo(tmp_path):
    central = tmp_path / "central"
    central.mkdir()
    repo = copy_fixture(JAVA_FIXTURE, tmp_path / "svc")
    git(repo, "checkout", "-q", "-b", "feature")
    path = repo / FEE_CALCULATOR_PATH
    path.write_text(path.read_text() + "// changed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change the calculator")
    return central, repo


@pytest.mark.parametrize("java", [21, 17])
def test_mutation_returns_a_real_score_on_changed_classes_only(tmp_path, capsys, monkeypatch, java):
    central, repo = _pit_repo(tmp_path)
    monkeypatch.setenv("JAVA_HOME", java_home(java))
    if java == 17:
        pom = repo / "pom.xml"
        pom.write_text(pom.read_text().replace("<java.version>21<", "<java.version>17<"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "java 17")
    out_file = tmp_path / "S-1-mutation.json"
    code = cli.main(["mutation", "--central", str(central), "--json", "--repo", "svc",
                     "--diff", "main...HEAD", "--out", str(out_file)])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0
    jsonschema.validate(doc, MUTATION_SCHEMA)
    assert doc == json.loads(out_file.read_text())
    assert doc["notRun"] is False, doc["reason"]
    assert doc["changedClasses"] == [FEE_CALCULATOR]
    assert doc["killed"] + doc["survived"] + doc["noCoverage"] > 0 and 0 < doc["score"] <= 1
    report = (repo / "target/pit-reports/mutations.xml").read_text()
    assert FEE_CALCULATOR in report and "FeeService</mutatedClass>" not in report


def test_mutation_not_run_when_pit_is_absent_from_the_fixture(tmp_path, capsys):
    central, repo = _pit_repo(tmp_path)
    pom = repo / "pom.xml"
    text = pom.read_text()
    start = text.index("      <plugin>\n        <groupId>org.pitest</groupId>")
    end = text.index("</plugin>", start) + len("</plugin>\n")
    pom.write_text(text[:start] + text[end:])
    code = cli.main(["mutation", "--central", str(central), "--json", "--repo", "svc",
                     "--diff", "main...HEAD"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0 and doc["notRun"] is True and "PIT is not installed" in doc["reason"]
    jsonschema.validate(doc, MUTATION_SCHEMA)


def test_mutation_not_run_when_the_build_fails(tmp_path, capsys, monkeypatch):
    central, repo = _pit_repo(tmp_path)
    monkeypatch.setenv("JAVA_HOME", java_home(21))
    path = repo / FEE_CALCULATOR_PATH
    path.write_text(path.read_text() + "this does not compile\n")
    code = cli.main(["mutation", "--central", str(central), "--json", "--repo", "svc", "--diff", "main"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0 and doc["notRun"] is True and "build failed" in doc["reason"]


def _gradle_repo(tmp_path):
    return copy_fixture(JAVA_FIXTURE / "variants/gradle-kts", tmp_path / "sample-gradle-repo")


def test_gradle_kts_variant_builds_green_with_sensors(tmp_path):
    repo = _gradle_repo(tmp_path)
    done = subprocess.run(["gradle", "--no-daemon", "build"], cwd=repo, env=build_env(17),
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    assert (repo / "build/test-results/test/TEST-com.example.samplegradle.ArchitectureTest.xml").is_file()


def test_gradle_variant_catches_field_injection_with_remediation(tmp_path):
    repo = _gradle_repo(tmp_path)
    path = repo / NOTE_SERVICE_PATH
    path.write_text(path.read_text().replace(
        "    private final NotePort notes;\n",
        "    @org.springframework.beans.factory.annotation.Autowired\n    private NotePort other;\n\n"
        "    private final NotePort notes;\n"))
    done = subprocess.run(["gradle", "--no-daemon", "build", "--continue"], cwd=repo, env=build_env(17),
                          capture_output=True, text=True)
    assert done.returncode != 0
    text = (repo / "build/test-results/test/TEST-com.example.samplegradle.ArchitectureTest.xml").read_text()
    assert "REMEDIATION:" in text and "Autowired" in text


def test_mutation_scores_the_gradle_variant(tmp_path, capsys, monkeypatch):
    central = tmp_path / "central"
    central.mkdir()
    repo = _gradle_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "feature")
    path = repo / NOTE_SERVICE_PATH
    path.write_text(path.read_text() + "// changed\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    monkeypatch.setenv("JAVA_HOME", java_home(17))
    code = cli.main(["mutation", "--central", str(central), "--json", "--repo", "sample-gradle-repo",
                     "--diff", "main...HEAD"])
    doc = json.loads(capsys.readouterr().out)
    assert code == 0 and doc["notRun"] is False, doc
    jsonschema.validate(doc, MUTATION_SCHEMA)
    assert doc["changedClasses"] == ["com.example.samplegradle.application.service.NoteService"]
    assert doc["killed"] > 0, "the service's tests must cover it"


@pytest.fixture(scope="module")
def react_repo(tmp_path_factory):
    repo = copy_fixture(REACT_FIXTURE, tmp_path_factory.mktemp("react") / "repo")
    done = subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=repo, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return repo


def eslint(repo):
    return subprocess.run(["npx", "eslint", "src", "--format", "json"], cwd=repo,
                          capture_output=True, text=True)


def test_clean_react_fixture_passes_lint_and_types(react_repo):
    done = eslint(react_repo)
    assert done.returncode == 0, done.stdout
    assert all(not f["messages"] for f in json.loads(done.stdout))
    typed = subprocess.run(["npx", "tsc", "--noEmit"], cwd=react_repo, capture_output=True, text=True)
    assert typed.returncode == 0, typed.stdout


@pytest.mark.parametrize("item", REACT_MANIFEST["violations"], ids=lambda v: v["patch"])
def test_react_violation_is_caught_with_remediation(react_repo, item):
    check = item["checks"][0]
    git(react_repo, "apply", f"violations/{item['patch']}")
    try:
        done = eslint(react_repo)
        assert done.returncode == 1
        report = next(f for f in json.loads(done.stdout) if f["filePath"].endswith(check["file"]))
        messages = [m["message"] for m in report["messages"]]
        assert any(check["rule"] in m and "REMEDIATION:" in m for m in messages), messages
    finally:
        git(react_repo, "apply", "-R", f"violations/{item['patch']}")
