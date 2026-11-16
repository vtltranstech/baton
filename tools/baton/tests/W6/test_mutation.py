"""`baton mutation`: changed classes, report parsing, notRun, CLI wiring and schema."""
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from baton import cli
from baton.mutation import pit
from w6support import ROOT, git

SCHEMA = json.loads((ROOT / "schemas" / "mutation.json").read_text())
REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<mutations>
<mutation detected='true' status='KILLED'><mutatedClass>a.b.Fee</mutatedClass></mutation>
<mutation detected='true' status='KILLED'><mutatedClass>a.b.Fee$Inner</mutatedClass></mutation>
<mutation detected='true' status='TIMED_OUT'><mutatedClass>a.b.Fee</mutatedClass></mutation>
<mutation detected='false' status='SURVIVED'><mutatedClass>a.b.Fee</mutatedClass></mutation>
<mutation detected='false' status='NO_COVERAGE'><mutatedClass>a.b.Fee</mutatedClass></mutation>
<mutation detected='false' status='NON_VIABLE'><mutatedClass>a.b.Fee</mutatedClass></mutation>
<mutation detected='true' status='KILLED'><mutatedClass>a.b.Other</mutatedClass></mutation>
</mutations>
"""
JAVA_CLASS = "package a.b;\npublic class {name} {{}}\n"


def test_git_ignores_a_hook_environment(tmp_path, monkeypatch):
    central, repo = make_repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "wrong"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "wrong-index"))
    assert pit.changed_classes(repo, "main...HEAD") == ["a.b.Added", "a.b.Fee"]


def test_counts_report_for_the_changed_classes_only(tmp_path):
    report = tmp_path / "mutations.xml"
    report.write_text(REPORT)
    counts = pit.count_mutations([report], ["a.b.Fee"])
    assert counts == {"killed": 3, "survived": 1, "noCoverage": 1}


def test_score_counts_no_coverage_in_the_denominator():
    assert pit.score({"killed": 3, "survived": 1, "noCoverage": 1}) == 0.6


def test_maps_paths_to_classes():
    paths = ["src/main/java/a/b/Fee.java", "mod/src/main/java/a/C.java", "src/test/java/a/FeeTest.java",
             "README.md", "src/main/java/a/package-info.java", "src/main/java/module-info.java"]
    assert pit.classes_from_paths(paths) == ["a.C", "a.b.Fee"]


def make_repo(tmp_path, build_file="pom.xml", build_text="<project><!-- pitest-maven --></project>"):
    central = tmp_path / "central"
    central.mkdir()
    repo = tmp_path / "svc"
    (repo / "src/main/java/a/b").mkdir(parents=True)
    (repo / "src/test/java/a/b").mkdir(parents=True)
    (repo / build_file).write_text(build_text)
    (repo / "src/main/java/a/b/Fee.java").write_text(JAVA_CLASS.format(name="Fee"))
    (repo / "src/test/java/a/b/FeeTest.java").write_text(JAVA_CLASS.format(name="FeeTest"))
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "src/main/java/a/b/Fee.java").write_text(JAVA_CLASS.format(name="Fee") + "// changed\n")
    (repo / "src/main/java/a/b/Added.java").write_text(JAVA_CLASS.format(name="Added"))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return central, repo


def stub_wrapper(repo, name="mvnw", exit_code=0, report="target/pit-reports/mutations.xml"):
    """A fake build tool: records its arguments and drops a canned PIT report, so tests stay fast."""
    (repo / "report.xml").write_text(REPORT.replace("a.b.Other", "a.b.Added"))
    script = repo / name
    script.write_text(
        "#!/bin/sh\n"
        'echo "$@" > args.txt\n'
        f"mkdir -p $(dirname {report}) && cp report.xml {report}\n"
        "echo 'build log line'\n"
        f"exit {exit_code}\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def run_cli(capsys, central, *args):
    code = cli.main(["mutation", "--central", str(central), "--json", *args])
    out = capsys.readouterr()
    return code, out


def test_runs_pit_on_changed_classes_only_and_validates(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    stub_wrapper(repo)
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    assert code == 0, out.err
    doc = json.loads(out.out)
    jsonschema.validate(doc, SCHEMA)
    assert doc["changedClasses"] == ["a.b.Added", "a.b.Fee"]
    assert doc["notRun"] is False and doc["reason"] is None
    assert doc["diffRef"] == "main...HEAD" and doc["repo"] == "svc"
    assert (doc["killed"], doc["survived"], doc["noCoverage"]) == (4, 1, 1)
    assert doc["score"] == pytest.approx(4 / 6, abs=0.0001)
    args = (repo / "args.txt").read_text()
    assert "-DtargetClasses=a.b.Added,a.b.Added$*,a.b.Fee,a.b.Fee$*" in args
    assert "-DtargetTests=a.b.*" in args
    assert "org.pitest:pitest-maven:mutationCoverage" in args


def test_stale_report_is_not_reused_when_the_build_fails(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    (repo / "target/pit-reports").mkdir(parents=True)
    (repo / "target/pit-reports/mutations.xml").write_text(REPORT)
    stub_wrapper(repo, exit_code=1)
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    doc = json.loads(out.out)
    assert code == 0
    jsonschema.validate(doc, SCHEMA)
    assert doc["notRun"] is True and "build failed" in doc["reason"] and "score" not in doc


def test_not_run_when_pit_is_not_in_the_build(tmp_path, capsys):
    central, repo = make_repo(tmp_path, build_text="<project></project>")
    stub_wrapper(repo)
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    doc = json.loads(out.out)
    assert code == 0
    jsonschema.validate(doc, SCHEMA)
    assert doc["notRun"] is True and "PIT is not installed" in doc["reason"]
    assert doc["changedClasses"] == ["a.b.Added", "a.b.Fee"]
    assert not (repo / "args.txt").exists()


def test_not_run_when_no_build_tool_can_be_found(tmp_path, capsys, monkeypatch):
    central, repo = make_repo(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(pit, "GIT", "/usr/bin/git")
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    doc = json.loads(out.out)
    assert code == 0 and doc["notRun"] is True and "mvn" in doc["reason"]


def test_not_run_when_no_class_changed(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    stub_wrapper(repo)
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "HEAD...HEAD")
    doc = json.loads(out.out)
    assert code == 0 and doc["notRun"] is True and doc["changedClasses"] == []
    assert "no changed" in doc["reason"]


def test_not_run_when_pit_generates_no_mutations(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    stub_wrapper(repo)
    (repo / "mvnw").write_text("#!/bin/sh\nexit 0\n")
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    doc = json.loads(out.out)
    assert code == 0 and doc["notRun"] is True and "no mutations" in doc["reason"]


def test_gradle_build_uses_the_gradle_task(tmp_path, capsys):
    build_text = 'plugins { id("info.solidsoft.pitest") version "1" }'
    central, repo = make_repo(tmp_path, "build.gradle.kts", build_text)
    stub_wrapper(repo, "gradlew", report="build/reports/pitest/mutations.xml")
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    doc = json.loads(out.out)
    assert code == 0 and doc["notRun"] is False
    args = (repo / "args.txt").read_text()
    assert "pitest" in args and "-PbatonTargetClasses=a.b.Added,a.b.Added$*,a.b.Fee,a.b.Fee$*" in args
    assert "-PbatonTargetTests=a.b.*" in args


def test_out_writes_the_file_and_makes_parents(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    stub_wrapper(repo)
    out_file = tmp_path / "docs/qa/F-1/S-1-mutation.json"
    code = cli.main(["mutation", "--central", str(central), "--repo", "svc", "--diff", "main...HEAD",
                     "--out", str(out_file)])
    assert code == 0
    jsonschema.validate(json.loads(out_file.read_text()), SCHEMA)
    assert "mutation score" in capsys.readouterr().out


def test_repo_path_comes_from_the_profile_table(tmp_path, capsys):
    central, repo = make_repo(tmp_path)
    stub_wrapper(repo)
    moved = tmp_path / "elsewhere"
    repo.rename(moved)
    (central / "profile").mkdir()
    (central / "profile/project.md").write_text(
        "# P\n\n| repo | path | purpose | build |\n| --- | --- | --- | --- |\n"
        "| svc | ../elsewhere | x | maven |\n")
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "main...HEAD")
    assert code == 0 and json.loads(out.out)["notRun"] is False


def test_missing_repo_exits_2(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    code, out = run_cli(capsys, central, "--repo", "nope", "--diff", "main...HEAD")
    assert code == 2 and "nope" in out.err


def test_unknown_ref_exits_2(tmp_path, capsys):
    central, _repo = make_repo(tmp_path)
    code, out = run_cli(capsys, central, "--repo", "svc", "--diff", "no-such-ref")
    assert code == 2 and "no-such-ref" in out.err


def test_help_works_from_the_entry_point():
    done = subprocess.run([sys.executable, str(ROOT / "tools/baton/cli.py"), "mutation", "--help"],
                          capture_output=True, text=True, env={**os.environ})
    assert done.returncode == 0
    for option in ("--repo", "--diff", "--out", "--timeout"):
        assert option in done.stdout


def test_module_exposes_the_cli_interface():
    from baton.mutation import cmd
    assert callable(cmd.add_arguments) and callable(cmd.run)
    assert Path(cmd.__file__).parent.joinpath("README.md").is_file()
