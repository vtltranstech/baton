"""harness -> pod -> baton (models-and-activation.md section 4): what came before each rename still works."""

import json
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
from baton import install
from baton.graph.stamps import apply, extract, strip
from baton.mutation import pit
from baton.trace.collect import provenance

ROOT = Path(__file__).resolve().parents[4]
OLD = ("pod", "harness")


def test_the_old_command_names_are_deprecated_aliases():
    scripts = tomllib.loads((ROOT / "tools" / "baton" / "pyproject.toml").read_text())["project"]["scripts"]
    assert scripts == {"baton": "baton.cli:main", "pod": "baton.cli:main", "harness": "baton.cli:main"}


@pytest.mark.parametrize("old", OLD)
def test_old_provenance_footers_are_read(old):
    block = provenance(f"x\n<!-- {old}:provenance\nagent: qa\nmodel: fast (sonnet)\n-->\n", "qa")
    assert block["agent"] == "qa" and block["model"] == "fast (sonnet)"


@pytest.mark.parametrize("old", OLD)
def test_old_stamps_are_read_and_rewritten_as_baton(old):
    dsl = (
        'workspace "P" "p" {\n    model {\n'
        '        job = container "job" "d" "t" {\n'
        '            tags "F-002"\n'
        "            properties {\n"
        f'                "{old}.story" "S-010"\n'
        f'                "{old}.feature" "F-002"\n'
        "            }\n"
        "        }\n    }\n}\n"
    )
    stamps = extract(dsl)
    assert stamps["job"].props == {"baton.story": "S-010", "baton.feature": "F-002"}
    plain = strip(dsl)
    assert f'"{old}.' not in plain and "{" not in plain.split("job =")[1].split("\n")[0]
    assert '"baton.story" "S-010"' in apply(plain, stamps)


@pytest.mark.parametrize("old", OLD)
def test_an_install_from_before_a_rename_is_upgraded(tmp_path, old):
    central = tmp_path / "central"
    cli = central / ".claude" / "tools" / old / "cli.py"
    cli.parent.mkdir(parents=True)
    cli.write_text("old\n")
    legacy = central / f".claude/{old}-install.json"
    legacy.write_text(json.dumps({"files": {f".claude/tools/{old}/cli.py": install.sha(cli)}}))
    result = install.plan(central, force=False)
    assert f".claude/tools/{old}/cli.py" in result.removed and not result.conflicts
    install.apply(central, result)
    assert not cli.exists() and not legacy.exists() and (central / install.MANIFEST).is_file()
    assert (central / ".claude" / "tools" / "baton" / "cli.py").is_file()


@pytest.mark.parametrize("old", OLD)
def test_the_graph_server_entry_follows_the_move(tmp_path, old):
    central = tmp_path / "central"
    central.mkdir()
    (central / ".mcp.json").write_text(json.dumps({"mcpServers": {"graph": {
        "type": "stdio", "command": "/opt/py3", "args": [f".claude/tools/{old}/graph/mcp_server.py"]}}}))
    done = install.project_files(central, None, write=True)
    graph = json.loads((central / ".mcp.json").read_text())["mcpServers"]["graph"]
    assert graph["command"] == "/opt/py3" and graph["args"] == [".claude/tools/baton/graph/mcp_server.py"]
    assert any("graph server moved" in line for line in done)


def test_pit_passes_the_old_property_names_too(tmp_path):
    (tmp_path / "build.gradle.kts").write_text('plugins { id("info.solidsoft.pitest") }\n')
    gradlew = tmp_path / "gradlew"
    gradlew.write_text("#!/bin/sh\n")
    gradlew.chmod(0o755)
    command, _, why = pit.plan(tmp_path, ["com.x.A"])
    assert why is None
    for prefix in ("baton", *OLD):
        assert any(c.startswith(f"-P{prefix}TargetClasses=") for c in command)


def _stray(word: re.Pattern, allowed: tuple[str, ...]) -> list[str]:
    found = []
    for top in ("agents", "skills", "hooks", "tools", "contracts", "docs", "templates"):
        listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", top], capture_output=True, text=True)
        for name in listing.stdout.split():
            if "/vendor/" in name or name.endswith((".png", ".jar", ".zip", "test_rename_compat.py",
                                                     "models-and-activation.md")):  # documents the renames
                continue
            path = ROOT / name
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                low = line.lower()
                if word.search(low) and not any(a.lower() in low for a in allowed):
                    found.append(f"{name}:{number}: {line.strip()[:90]}")
    return found


def test_harness_appears_only_where_the_contract_allows():
    """Only the README sentence, the paper's name (harness-engineering, harnesses) and the compatibility
    shims named in section 4 may still say harness in agents, skills, hooks, tools, contracts and docs."""
    allowed = (
        "harness-engineering", "harnesses", "harness-framework", "vtltranstech/harness",
        "harness:provenance", "harness-install.json", "HARNESS_", "harness =", "harness.*",
        "harnessTarget", "`harness`", "tools/harness/", "harness\\.", "harness-W", "\"harness\"",
        "\"harness.", "|harness)", "\"harness.\")",
    )
    found = _stray(re.compile("harness"), allowed)
    assert not found, "\n".join(found)


def test_pod_appears_only_where_the_contract_allows():
    """After the second rename, `pod` is only a compatibility shim (section 4)."""
    allowed = (
        "pod:provenance", "pod-install.json", "POD_", "pod =", "pod.*", "podTarget", "`pod`",
        "tools/pod/", "\"pod\"", "\"pod.\"", "(?:baton|pod|harness)", "(?:pod|harness)", "podman",
    )
    found = _stray(re.compile(r"\bpod\b|\bpod_|podtarget"), allowed)
    assert not found, "\n".join(found)
