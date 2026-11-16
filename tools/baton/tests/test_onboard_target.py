"""`baton onboard` works on the product it was started in, never on the framework's samples."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "tools" / "baton" / "cli.py"
TABLE = "# Project\n\n| Path | What | Build |\n| --- | --- | --- |\n| `{}` | x | x |\n"


def onboard(cwd):
    return subprocess.run(
        [sys.executable, str(CLI), "onboard", "--interview"], cwd=cwd, capture_output=True, text=True
    )


def product(tmp_path, repo_path="../my-api"):
    shutil.copytree(ROOT / "fixtures" / "sample-java-repo", tmp_path / "my-api")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path / "my-api", check=True)
    central = tmp_path / "central"
    (central / "profile").mkdir(parents=True)
    (central / "profile" / "project.md").write_text(TABLE.format(repo_path))
    return central


def test_it_reads_the_repos_of_the_folder_it_started_in(tmp_path):
    central = product(tmp_path)
    done = onboard(central)
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert report["central"] == str(central.resolve())
    assert report["repos"] == [{"name": "my-api", "path": str((tmp_path / "my-api").resolve())}]
    assert "my-api" in (central / "profile" / "stack-detected.md").read_text()


def test_no_project_file_stops_even_when_a_sample_is_nearby(tmp_path):
    shutil.copytree(ROOT / "fixtures" / "sample-central-repo", tmp_path / "fixtures" / "sample-central-repo")
    done = onboard(tmp_path)
    assert done.returncode == 2 and "central repo" in done.stderr
    assert not (tmp_path / "profile").exists()


def test_starting_inside_the_sample_is_refused():
    done = onboard(ROOT / "fixtures" / "sample-central-repo")
    assert done.returncode == 2 and "framework's sample" in done.stderr


def test_a_repo_table_pointing_at_the_sample_is_refused(tmp_path):
    central = product(tmp_path, str(ROOT / "fixtures" / "sample-java-repo"))
    done = onboard(central)
    assert done.returncode == 2 and "framework's sample" in done.stderr
    assert not (central / "profile" / "stack-detected.md").exists()


def test_a_copy_of_the_sample_outside_fixtures_still_works_for_a_trial(tmp_path):
    shutil.copytree(ROOT / "fixtures", tmp_path / "trial")
    done = onboard(tmp_path / "trial" / "sample-central-repo")
    assert "framework's sample" not in done.stderr
