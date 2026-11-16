"""A two-repo product (the Java and React fixtures) with a central repo, extracted once per session."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "fixtures"
SPEC = """story: S-201
title: Waive the fee for dormant accounts
changed:
  - FeeService#accrue
new:
  - class: com.example.sample.application.service.FeeWaiverPolicy
    stereotype: service
    uses: [FeeAccrualPort]
  - method: FeeWaiverPolicy#isWaived
    signature: "isWaived(String accountRef, String periodKey): boolean"
    calledFrom: FeeService#accrue
    before: FeeCalculator#calculateFee
    calls: [FeeAccrualPort#findForPeriod]
    reads: [collection:fee_waivers]
  - field: FeeAccrualDoc.waived
    type: boolean
"""


def git(repo: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def cli(*argv: str):
    from baton.cli import main

    return main(list(argv))


@pytest.fixture(scope="session")
def product_template(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("product")
    ignore = shutil.ignore_patterns("target", "violations", "variants", "node_modules", ".DS_Store")
    shutil.copytree(FIXTURES / "sample-java-repo", base / "fee-service", ignore=ignore)
    shutil.copytree(FIXTURES / "sample-react-repo", base / "fee-ui", ignore=ignore)
    shutil.copytree(FIXTURES / "sample-central-repo", base / "central", ignore=ignore)
    for repo in ("fee-service", "fee-ui"):
        git(base / repo, "init", "-q", "-b", "main")
        git(base / repo, "add", "-A")
        git(base / repo, "commit", "-qm", "base")
    project = base / "central" / "profile" / "project.md"
    project.write_text(
        project.read_text().replace(
            "| `../invoice-service` | Invoice APIs | mvn -q clean verify |",
            "| `../fee-service` | Fee APIs | mvn -q clean verify |\n| `../fee-ui` | Fee screens | npm test |",
        )
    )
    (base / "central" / "profile" / "risk-zones.yaml").unlink()
    central = str(base / "central")
    assert cli("extract-stack", "--central", central) == 0
    assert cli("extract", "--central", central) == 0
    stories = base / "central" / "docs" / "stories" / "F-200"
    stories.mkdir(parents=True)
    (stories / "S-201.md").write_text(
        "# S-201: Waive the fee for dormant accounts\nState: Ready\nDepends-On: none\n"
    )
    (stories / "S-202.md").write_text("# S-202: Change the summary\nState: Ready\nDepends-On: none\n")
    design = base / "central" / "docs" / "design" / "F-200"
    design.mkdir(parents=True)
    (design / "S-201-change.yaml").write_text(SPEC)
    return base


@pytest.fixture
def product(product_template, tmp_path) -> Path:
    """A private copy per test: tests write diagrams and edit code."""
    target = tmp_path / "p"
    shutil.copytree(product_template, target, symlinks=True)
    return target
