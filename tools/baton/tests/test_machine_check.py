"""hooks/run-hook finds a working Python or refuses; skills expect the machine to be set up."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "hooks/run-hook"
ALLOWED = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX sh")


@pytest.fixture
def env(tmp_path):
    """Only basic tools on the PATH: a machine with no usable Python."""
    bare = tmp_path / "bare"
    bare.mkdir()
    for tool in ("sh", "env", "dirname", "tr"):
        for base in ("/bin", "/usr/bin"):
            if (Path(base) / tool).exists():
                (bare / tool).symlink_to(Path(base) / tool)
                break
    fake = bare / "python3"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    return {"PATH": str(bare), "HOME": str(tmp_path), "BATON_COMMON_PYTHONS": ""}


def run(env, stdin):
    return subprocess.run(
        [str(HOOK), "protect_main.py"], env=env, input=stdin, capture_output=True, text=True
    )


def test_a_hook_refuses_when_there_is_no_python(env):
    done = run(env, "{}")
    assert done.returncode == 2 and "docs/quickstart.md" in done.stderr


def test_a_hook_runs_with_the_named_python(env):
    assert run({**env, "BATON_PYTHON": sys.executable}, ALLOWED).returncode == 0


def test_a_named_python_that_does_not_work_is_refused_not_replaced(env):
    path = f"{Path(sys.executable).parent}:{env['PATH']}"
    assert run({**env, "PATH": path, "BATON_PYTHON": "/no/such/python"}, ALLOWED).returncode == 2


def test_the_windows_py_launcher_is_used_when_python3_is_a_stub(env, tmp_path):
    """On Windows `python3` is often the Store stub; `py -3` names the real interpreter (with a CR)."""
    launcher = Path(env["PATH"]) / "py"
    launcher.write_text(f'#!/bin/sh\n[ "$1" = "-3" ] || exit 1\nprintf "%s\\r\\n" "{sys.executable}"\n')
    launcher.chmod(0o755)
    assert run(env, ALLOWED).returncode == 0


def test_a_stale_pythonhome_is_ignored(env):
    named = {**env, "BATON_PYTHON": sys.executable, "PYTHONHOME": "/no/such/home"}
    assert run(named, ALLOWED).returncode == 0


def test_there_is_no_bin_folder_and_nothing_points_to_it():
    assert not (ROOT / "bin").exists()
    assert json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["graph"]["command"] == "python3"
    for folder in ("agents", "skills", "docs", "templates", "hooks"):
        for path in (ROOT / folder).rglob("*.md"):
            text = path.read_text()
            assert "baton-check" not in text and "bin/baton" not in text, path


def test_skills_check_the_machine_and_no_file_hard_codes_the_cli_path():
    for skill in ("onboard", "build"):
        assert "baton --help" in (ROOT / f"skills/{skill}/SKILL.md").read_text()
    for folder in ("agents", "skills"):
        for path in (ROOT / folder).rglob("*.md"):
            assert "tools/baton/cli.py" not in path.read_text(), path
