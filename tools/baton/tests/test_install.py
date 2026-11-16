"""baton install: a copied install that upgrades in place, keeps project edits and project settings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from baton.cli import main
from baton.install import FRAMEWORK, MANIFEST, merge_settings


def install(central: Path, *extra: str, capsys=None) -> tuple[int, str]:
    code = main(["install", "--central", str(central), *extra])
    out = capsys.readouterr().out if capsys else ""
    return code, out


def test_a_fresh_install_copies_the_core_and_adds_project_files(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    code, out = install(central, capsys=capsys)
    assert code == 0, out
    claude = central / ".claude"
    assert (claude / "agents/architect.md").read_text() == (FRAMEWORK / "agents/architect.md").read_text()
    assert (claude / "skills/workflow/SKILL.md").is_file() and (claude / "sensors/pmd-ruleset.xml").is_file()
    assert (claude / "tools/baton/ir/model.py").is_file()
    assert not (claude / "tools/baton/tests").exists()
    assert not list(claude.rglob("__pycache__"))
    assert os.access(claude / "hooks/run-hook", os.X_OK)
    manifest = json.loads((central / MANIFEST).read_text())
    assert ".claude/agents/qa.md" in manifest["files"] and manifest["framework"]
    settings = json.loads((claude / "settings.json").read_text())
    assert any("read_log.py" in json.dumps(e) for e in settings["hooks"]["PostToolUse"])
    # subagent reports come back as tool results, not as prompts an organisation hook can refuse
    assert settings["env"]["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    graph = json.loads((central / ".mcp.json").read_text())["mcpServers"]["graph"]
    assert graph["args"][-1] == ".claude/tools/baton/graph/mcp_server.py"
    assert (central / "CLAUDE.md").is_file() and (central / "profile/project.md").is_file()
    for generated in ("dependencies.yaml", "aggregates.yaml", "stack-detected.md"):
        assert not (central / "profile" / generated).exists()  # /onboard writes them from this project's code
    assert ".baton/" in (central / ".gitignore").read_text()
    assert ".claude/hooks/run-hook text eol=lf" in (central / ".gitattributes").read_text()
    assert "add .claude/agents/architect.md" in out


def test_a_second_run_changes_nothing(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    install(central, capsys=capsys)
    code, out = install(central, "--check", capsys=capsys)
    assert code == 0 and out.startswith("0 new, 0 updated, 0 removed,")
    code, out = install(central, capsys=capsys)
    assert code == 0 and "0 conflicts" in out


def test_project_settings_and_files_are_kept(tmp_path, capsys):
    central = tmp_path / "central"
    (central / ".claude").mkdir(parents=True)
    mine = {"type": "command", "command": "echo mine"}
    (central / ".claude/settings.json").write_text(
        json.dumps(
            {
                "claudeMdExcludes": ["/home/me/CLAUDE.md"],
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]},
            }
        )
    )
    (central / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"graph": {"command": "/opt/py/bin/python"}}})
    )
    (central / "CLAUDE.md").write_text("# ours\n")
    install(central, capsys=capsys)
    install(central, capsys=capsys)  # twice: the baton hooks are replaced, not duplicated
    settings = json.loads((central / ".claude/settings.json").read_text())
    assert settings["claudeMdExcludes"] == ["/home/me/CLAUDE.md"]
    pre = json.dumps(settings["hooks"]["PreToolUse"])
    assert pre.count("echo mine") == 1 and pre.count("protect_main.py") == 1
    assert (
        json.loads((central / ".mcp.json").read_text())["mcpServers"]["graph"]["command"]
        == "/opt/py/bin/python"
    )
    assert (central / "CLAUDE.md").read_text() == "# ours\n"


def test_an_edited_file_is_a_conflict_until_forced(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    install(central, capsys=capsys)
    edited = central / ".claude/agents/qa.md"
    edited.write_text("local change\n")
    code, out = install(central, capsys=capsys)
    assert code == 1 and "conflict .claude/agents/qa.md" in out
    assert edited.read_text() == "local change\n"
    code, out = install(central, "--force", capsys=capsys)
    assert code == 0 and edited.read_text() == (FRAMEWORK / "agents/qa.md").read_text()


def test_upgrade_removes_dropped_files_but_never_the_projects_own(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    install(central, capsys=capsys)
    dropped = central / ".claude/skills/old-skill/SKILL.md"
    dropped.parent.mkdir(parents=True)
    dropped.write_text("from an older framework\n")
    own = central / ".claude/agents/our-agent.md"
    own.write_text("ours\n")
    manifest = json.loads((central / MANIFEST).read_text())
    from baton.install import sha

    manifest["files"][".claude/skills/old-skill/SKILL.md"] = sha(dropped)
    (central / MANIFEST).write_text(json.dumps(manifest))
    code, out = install(central, capsys=capsys)
    assert code == 0 and "remove .claude/skills/old-skill/SKILL.md" in out
    assert not dropped.exists() and own.read_text() == "ours\n"


def test_install_refuses_the_framework_itself(capsys):
    code, _ = install(FRAMEWORK, capsys=capsys)
    assert code == 2


def test_the_installed_hooks_run(tmp_path, capsys):
    central = tmp_path / "my central"
    central.mkdir()
    install(central, capsys=capsys)
    settings = json.loads((central / ".claude/settings.json").read_text())
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    command = command.replace("${CLAUDE_PROJECT_DIR}", str(central))
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(central)}
    done = subprocess.run(
        ["bash", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "BATON_PYTHON": sys.executable, "CLAUDE_PROJECT_DIR": str(central)},
    )
    assert done.returncode == 2, done.stderr


def test_merge_settings_only_replaces_pod_hooks():
    existing = {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": 'bash ".claude/hooks/run-hook" x.py'}],
                }
            ]
        }
    }
    merged = merge_settings(existing, {"hooks": {}})
    assert merged["hooks"] == {}


def test_an_installed_copy_needs_the_checkout_named(tmp_path, capsys, monkeypatch):
    import baton.install as install_mod

    monkeypatch.setattr(install_mod, "FRAMEWORK", tmp_path / "site-packages")  # as pipx would have it
    monkeypatch.delenv("BATON_FRAMEWORK", raising=False)
    central = tmp_path / "central"
    central.mkdir()
    code = main(["install", "--central", str(central)])
    err = capsys.readouterr().err
    assert code == 2 and "--from <clone or project>" in err and not (central / ".claude").exists()
    assert main(["install", "--central", str(central), "--from", str(tmp_path)]) == 2  # not a checkout
    capsys.readouterr()
    assert main(["install", "--central", str(central), "--from", str(FRAMEWORK)]) == 0
    assert (central / ".claude/agents/architect.md").is_file()
    monkeypatch.setenv("BATON_FRAMEWORK", str(FRAMEWORK))
    assert main(["install", "--central", str(central), "--check"]) == 0


def test_an_installed_project_installs_the_next_one(tmp_path, capsys):
    """The usual flow: the central repo's own copy installs another project, with no framework clone."""
    first, second = tmp_path / "central", tmp_path / "other"
    first.mkdir()
    second.mkdir()
    install(first, capsys=capsys)
    assert (first / ".claude/templates/settings.json").is_file()
    copy_cli = first / ".claude/tools/baton/cli.py"
    done = subprocess.run(
        [sys.executable, str(copy_cli), "install", "--central", str(second)], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stderr
    for rel in (".claude/agents/architect.md", ".claude/hooks/run-hook", ".claude/tools/baton/ir/model.py"):
        assert (second / rel).read_bytes() == (first / rel).read_bytes()
    assert (
        json.loads((second / MANIFEST).read_text())["framework"]
        == json.loads((first / MANIFEST).read_text())["framework"]
    )
    assert (second / "CLAUDE.md").is_file() and (second / ".claude/settings.json").is_file()
    by_folder = main(["install", "--from", str(first), "--central", str(tmp_path / "third")])
    assert by_folder == 2  # the target folder does not exist
    (tmp_path / "third").mkdir()
    assert main(["install", "--from", str(first), "--central", str(tmp_path / "third")]) == 0
    capsys.readouterr()
    itself = subprocess.run(
        [sys.executable, str(copy_cli), "install", "--central", str(first)], capture_output=True, text=True
    )
    assert itself.returncode == 2 and "the framework itself" in itself.stderr


def test_no_mcp_leaves_mcp_json_alone(tmp_path, capsys):
    central = tmp_path / "central"
    central.mkdir()
    code, out = install(central, "--no-mcp", capsys=capsys)
    assert code == 0 and not (central / ".mcp.json").exists() and ".mcp.json" not in out
    assert (central / ".claude/settings.json").is_file()  # hooks still installed
    assert install(central, "--no-mcp", "--check", capsys=capsys)[0] == 0


def test_env_is_added_but_a_project_value_is_kept():
    template = {"env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}, "hooks": {}}
    assert merge_settings({}, template)["env"] == {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
    mine = {"env": {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "0", "OTHER": "x"}}
    kept = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "0", "OTHER": "x"}
    assert merge_settings(mine, template)["env"] == kept
