"""Plugin manifests, hook wiring and templates. `claude plugin validate` runs when the CLI is on the PATH."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from baton import miniyaml

ROOT = Path(__file__).resolve().parents[4]
HOOKS = ("protect_main.py", "protect_env.py", "state_gate.py", "protect_weights.py", "commit_scope.py")


def commands(config):
    return [(entry["matcher"], hook) for entry in config["hooks"]["PreToolUse"] for hook in entry["hooks"]]


_SHELL_FORM = re.compile(r'^bash "\$\{CLAUDE_PLUGIN_ROOT\}/hooks/run-hook" (\w+\.py)$')


def test_hooks_json_uses_plugin_root_and_blocks_on_failure():
    wired = commands(json.loads((ROOT / "hooks" / "hooks.json").read_text()))
    names = set()
    for _, hook in wired:
        assert hook["type"] == "command" and hook["onFailure"] == "block"
        match = _SHELL_FORM.match(hook["command"])
        assert match and (ROOT / "hooks" / match.group(1)).is_file()
        names.add(match.group(1))
    assert names == set(HOOKS)


def test_every_hook_runs_under_bash_never_exec_form():
    """Exec form (`args`) spawns run-hook directly: on Windows an extensionless sh script cannot start, so
    every gate would fail. Shell form under bash (Git Bash on Windows) runs it on every OS."""
    config = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    for entries in config["hooks"].values():
        for entry in entries:
            for hook in entry["hooks"]:
                assert "args" not in hook and hook["shell"] == "bash"
                assert hook["command"].startswith('bash "${CLAUDE_PLUGIN_ROOT}/hooks/run-hook" ')


def test_the_shell_form_command_runs_from_a_path_with_spaces(tmp_path):
    root = tmp_path / "my plugin"
    shutil.copytree(ROOT / "hooks", root / "hooks", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        ROOT / "tools" / "baton",
        root / "tools" / "baton",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    config = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    hook = config["hooks"]["PreToolUse"][0]["hooks"][0]  # protect_main
    command = hook["command"].replace(
        "${CLAUDE_PLUGIN_ROOT}", str(root)
    )  # Claude Code substitutes it as text
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": str(tmp_path)}
    done = subprocess.run(
        ["bash", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "BATON_PYTHON": sys.executable},
    )
    assert done.returncode == 0, done.stderr
    payload["tool_input"]["command"] = "git push origin main"
    refused = subprocess.run(
        ["bash", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "BATON_PYTHON": sys.executable},
    )
    assert refused.returncode == 2 and "protect" in refused.stderr.lower()


def test_settings_template_mirrors_hooks_json():
    plugin = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    copied = json.loads((ROOT / "templates" / "settings.json").read_text())
    text = json.dumps(plugin["hooks"]).replace(
        "${CLAUDE_PLUGIN_ROOT}/hooks", "${CLAUDE_PROJECT_DIR}/.claude/hooks"
    )
    assert json.loads(text) == copied["hooks"]


def test_manifest_names_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "baton" == market["plugins"][0]["name"]
    assert market["plugins"][0]["source"] == "./"
    assert "mcpServers" not in plugin and "hooks" not in plugin, "defaults load both; W5 adds .mcp.json"


@pytest.mark.skipif(not shutil.which("claude"), reason="claude CLI not on the PATH")
def test_claude_plugin_validate_also_with_the_w5_mcp_file(tmp_path):
    copy = tmp_path / "baton"
    for name in (".claude-plugin", "agents", "skills", "hooks"):
        shutil.copytree(ROOT / name, copy / name, ignore=shutil.ignore_patterns("__pycache__"))
    assert (
        subprocess.run(
            ["claude", "plugin", "validate", str(copy), "--strict"], capture_output=True
        ).returncode
        == 0
    )
    (copy / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"graph": {"command": "python3", "args": ["x.py"]}}})
    )
    done = subprocess.run(
        ["claude", "plugin", "validate", str(copy), "--strict"], capture_output=True, text=True
    )
    assert done.returncode == 0, done.stdout


def test_copied_install_finds_its_tools(tmp_path):
    """templates/settings.json layout: .claude/hooks beside .claude/tools."""
    claude = tmp_path / "central" / ".claude"
    shutil.copytree(ROOT / "hooks", claude / "hooks", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        ROOT / "tools" / "baton",
        claude / "tools" / "baton",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    story = tmp_path / "central" / "docs" / "stories" / "F-1" / "S-1.md"
    story.parent.mkdir(parents=True)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(story), "content": "Depends-On: none\nState: Done\n"},
        "cwd": str(story.parents[3]),
    }
    done = subprocess.run(
        [sys.executable, str(claude / "hooks" / "state_gate.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2 and "cannot move" in done.stderr


def test_templates_parse_against_their_schemas(validate):
    validate(
        miniyaml.load_file(str(ROOT / "templates" / "profile" / "confidence-weights.yaml")),
        "confidence-weights.json",
    )
    validate(miniyaml.load_file(str(ROOT / "templates" / "profile" / "risk-zones.yaml")), "risk-zones.json")
    text = (ROOT / "templates" / "profile" / "project.md").read_text()
    assert re.search(r"^\| test\.env\.uri\.var \|", text, re.M)


def test_templates_workspace_is_the_design_diagram_reference():
    assert (ROOT / "templates" / "workspace.dsl").read_text() == (
        ROOT / "skills" / "design-diagram" / "references" / "workspace-template.dsl"
    ).read_text()


def test_template_has_no_single_line_style_blocks():
    text = (ROOT / "templates" / "workspace.dsl").read_text()
    assert not re.search(r'element "\w+" \{ \S', text)


@pytest.mark.parametrize(
    "path,needle",
    [
        ("skills/build/SKILL.md", "-diff-shape.json"),
        ("skills/build/SKILL.md", "baton impact --repo"),
        ("skills/build/SKILL.md", "baton mutation --repo"),
        ("skills/build/SKILL.md", "baton confidence <story-id>"),
        ("skills/build/SKILL.md", "baton evidence <story-id>"),
        ("skills/build/SKILL.md", "HUMAN GATE 2"),
        ("skills/sprint-review/SKILL.md", "Order the stories by lane"),
        ("skills/sprint-review/SKILL.md", "lowest three signals"),
        ("agents/release.md", "-evidence.md"),
        ("agents/release.md", "-confidence.json"),
        ("agents/release.md", "PR: <url>"),
        ("skills/review-lenses/SKILL.md", "## Counts"),
        ("agents/developer.md", "Sensor loops:"),
    ],
)
def test_wiring_is_in_the_skills(path, needle):
    assert needle in (ROOT / path).read_text()


@pytest.mark.parametrize(
    "path,needle",
    [
        ("skills/build/SKILL.md", "Do NOT set Approved (gate 3)"),
        ("skills/deliver/SKILL.md", "Set `State: Approved` only on Approve"),
        ("skills/deliver/SKILL.md", "never write findings for the human"),
        ("skills/deliver/SKILL.md", "this skill never merges"),
        ("skills/build/SKILL.md", "After the second round, if still not approved, set `State: Blocked`"),
        ("agents/release.md", "Never merge. Never deploy."),
        ("agents/developer.md", "ArchUnit is mandatory"),
        ("agents/qa.md", "Any HIGH triaged lens finding"),
        ("skills/workflow/SKILL.md", "Never read `profile/confidence-weights.yaml`"),
    ],
)
def test_base_rules_survive(path, needle):
    assert needle in (ROOT / path).read_text()


def test_no_agent_is_pointed_at_the_weights():
    pattern = re.compile(r"confidence-weights")
    for path in list((ROOT / "agents").glob("*.md")) + list((ROOT / "skills").rglob("*.md")):
        for line in path.read_text().splitlines():
            if pattern.search(line):
                assert re.search(r"(?i)never|owned|hook|refuse|Senior Engineer|agents never", line), (
                    f"{path}: {line[:100]}"
                )


# The installed core must stay generic: a project's own vocabulary belongs in its profile/, never in
# agents, skills, hooks or templates.
def _project_words():
    """The shared list (tools/baton/tests/project_words.py); the repo never spells a project word."""
    words = ROOT / "tools/baton/tests/project_words.py"
    spec = importlib.util.spec_from_file_location("project_words", words)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.CORE_WORDS is None:
        pytest.skip("no project word list (tools/baton/tests/project-words.local.txt or BATON_PROJECT_WORDS)")
    return module.CORE_WORDS


TEXT_SUFFIXES = (".md", ".yaml", ".json", ".py", ".java", ".xml", ".dsl", ".csv")


def test_installed_core_has_no_project_words():
    words = _project_words()
    found = []
    for top in ("agents", "skills", "hooks", "sensors", "templates", "contracts"):
        for path in sorted((ROOT / top).rglob("*")):
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if words.search(line):
                        found.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
    assert not found, "\n".join(found)
