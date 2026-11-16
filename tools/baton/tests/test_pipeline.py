"""Phase 2: the real tools feeding each other, on a git copy of the Java fixture. No model runs here.

Artefacts only a live agent can write (design, test report, triage, security) come from the central fixture's
FIX-1 walk. Mutation needs a Maven build, so it runs only with BATON_SLOW=1 and is otherwise recorded as not
run, which is what /build does when the tool cannot run.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools" / "baton" / "cli.py"
FIXTURES = ROOT / "fixtures"
CHANGED = "src/main/java/com/example/sample/application/service/FeeCalculator.java"
STUB = (
    "#!/bin/sh\ncat > /dev/null\n"
    "printf '## Purpose\\nStub prose.\\n\\n## Invariants observed in tests\\nNone.\\n'\n"
)
WALK = {
    "design.md": "docs/design/F-100/FIX-1-design.md",
    "archunit.txt": "docs/qa/F-100/FIX-1-sensors/archunit.txt",
    "pmd.xml": "docs/qa/F-100/FIX-1-sensors/pmd.xml",
    "test-report.md": "docs/qa/F-100/FIX-1-test-report.md",
    "triage.md": "docs/qa/F-100/FIX-1-triage.md",
    "security-report.md": "docs/qa/F-100/FIX-1-security-report.md",
}


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=clean_env(),
    )


def baton(central, command, *args, env=None):
    verb = command.split()
    return subprocess.run(
        [sys.executable, str(CLI), *verb, "--central", str(central), *args],
        capture_output=True,
        text=True,
        cwd=central,
        env={**clean_env(), **(env or {})},
    )


def schema(name):
    return json.loads((ROOT / "schemas" / f"{name}.json").read_text())


@pytest.fixture
def product(tmp_path):
    repo = tmp_path / "fee-service"
    shutil.copytree(
        FIXTURES / "sample-java-repo", repo, ignore=shutil.ignore_patterns("target", "violations", "variants")
    )
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    central = tmp_path / "central"
    shutil.copytree(FIXTURES / "sample-central-repo", central)
    project = central / "profile" / "project.md"
    project.write_text(
        project.read_text().replace("`../invoice-service` | Invoice APIs", "`../fee-service` | Fee APIs")
    )
    (central / "profile" / "risk-zones.yaml").unlink()  # let extract seed it from the code
    git(repo, "checkout", "-qb", "feature/F-100-FIX-1")
    source = repo / CHANGED
    source.write_text(source.read_text().rstrip()[:-1] + "\n    // changed by FIX-1\n}\n")
    git(repo, "commit", "-qam", "change the fee calculation")
    return central, repo


def run_pipeline(central, tmp_path):
    assert (done := baton(central, "onboard")).returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert report["ran"]["c4"]["status"] == "ok"
    qa = central / "docs/qa/F-100"
    qa.mkdir(parents=True, exist_ok=True)
    impact = baton(
        central,
        "impact",
        "--repo",
        "fee-service",
        "--diff",
        "main...HEAD",
        "--json",
        "--out",
        "docs/qa/F-100/FIX-1-impact.json",
    )
    assert impact.returncode == 0, impact.stderr
    jsonschema.validate(json.loads((qa / "FIX-1-impact.json").read_text()), schema("impact"))
    if os.environ.get("BATON_SLOW") == "1":
        mutation = baton(
            central,
            "mutation",
            "--repo",
            "fee-service",
            "--diff",
            "main...HEAD",
            "--json",
            "--out",
            "docs/qa/F-100/FIX-1-mutation.json",
        )
        assert mutation.returncode == 0, mutation.stderr
    else:
        (qa / "FIX-1-mutation.json").write_text('{"notRun": true, "reason": "needs BATON_SLOW=1"}')
    for name, target in WALK.items():
        path = central / target
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(central / "walk/FIX-1" / name, path)
    shape = {
        "story": "FIX-1",
        "sensorLoops": 0,
        "newDependencies": [],
        "breakingContract": [],
        "writesCollections": [],
        "yagniCount": 0,
        "repos": [
            {
                "repo": "fee-service",
                "branch": "feature/F-100-FIX-1",
                "commits": 1,
                "linesAdded": 1,
                "linesDeleted": 0,
                "files": [CHANGED],
            }
        ],
    }
    (qa / "FIX-1-diff-shape.json").write_text(json.dumps(shape))
    assert (done := baton(central, "confidence", "FIX-1", "--json")).returncode == 0, done.stderr
    assert (done := baton(central, "evidence", "FIX-1")).returncode == 0, done.stderr
    return json.loads((qa / "FIX-1-confidence.json").read_text()), (qa / "FIX-1-evidence.md").read_text()


def test_the_seeded_risk_zone_caps_a_real_diff(product, tmp_path):
    central, _ = product
    confidence, evidence = run_pipeline(central, tmp_path)
    jsonschema.validate(confidence, schema("confidence"))
    assert any(cap["name"] == "risk_zone" and CHANGED in cap["evidence"] for cap in confidence["caps"]), (
        confidence["caps"]
    )
    assert confidence["score"] <= 50 and confidence["lane"] == "tech-lead"
    assert confidence["signals"]["blast_radius"]["points"] > 0, confidence["signals"]["blast_radius"]
    assert "FIX-1-impact.json" in evidence and "FIX-1-confidence.json" in evidence
    assert "end-to-end test not executed" in evidence.lower()


def test_generated_workspace_passes_its_own_drift_check(product, tmp_path):
    central, _ = product
    run_pipeline(central, tmp_path)
    assert (done := baton(central, "c4", "--check")).returncode == 0, done.stdout + done.stderr


def test_wiki_pages_verify_against_real_extraction(product, tmp_path):
    central, repo = product
    run_pipeline(central, tmp_path)
    git(repo, "checkout", "-q", "main")
    assert baton(central, "extract").returncode == 0
    stub = tmp_path / "claude-stub"
    stub.write_text(STUB)
    stub.chmod(0o755)
    env = {"BATON_CLAUDE_BIN": str(stub)}
    assert (done := baton(central, "wiki", "fee-service", "--prose", env=env)).returncode == 0, done.stderr
    assert (done := baton(central, "verify", "fee-service")).returncode == 0, done.stdout + done.stderr
    assert (central / "docs/context/codebase-map.md").read_text().count("fee-service") > 0
