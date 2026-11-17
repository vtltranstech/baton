"""templates/kits: required files, sensors in the build, hooks, CI, ASCII, no project words."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
KITS = ROOT / "templates" / "kits"
JAVA_KITS = ["spring-boot-mongo-service", "spring-batch-job"]
REACT_KITS = ["react-ts-ui"]
COMMON = [
    ".claude/settings.json", "CLAUDE.md", "AGENTS.md", ".github/workflows/ci.yml", "RUNBOOK.md", "README.md",
    ".gitignore",
]
JAVA_FILES = [
    "pom.xml", ".mvn/settings.xml", "config/sensors/pmd-ruleset.xml", "config/sensors/checkstyle.xml",
]
REACT_FILES = [
    "package.json", ".npmrc", "tsconfig.json", "eslint.config.js", "config/sensors/eslint-sensors.json",
]
HOOKS = ("protect_main.py", "commit_scope.py", "state_gate.py")
RUNBOOK_HEADINGS = ("Start", "Stop", "Health", "Logs", "Config", "Alerts")


def _project_words():
    """The shared list (tools/baton/tests/project_words.py); the repo never spells a project word."""
    words = ROOT / "tools/baton/tests/project_words.py"
    spec = importlib.util.spec_from_file_location("project_words", words)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.CORE_WORDS is None:
        pytest.skip("no project word list (tools/baton/tests/project-words.local.txt or BATON_PROJECT_WORDS)")
    return module.CORE_WORDS


def kit_files():
    skip = ("__pycache__", ".DS_Store")
    return sorted(p for p in KITS.rglob("*") if p.is_file() and not any(s in p.parts for s in skip))


def test_kits_readme_names_every_kit_and_the_onboard_path():
    text = (KITS / "README.md").read_text()
    for kit in JAVA_KITS + REACT_KITS:
        assert f"`{kit}/`" in text, kit
    for phrase in ("profile/project.md", "/onboard", "nearest kit", "Tech Lead"):
        assert phrase in text, phrase


@pytest.mark.parametrize("kit", JAVA_KITS + REACT_KITS)
def test_kit_has_the_common_files(kit):
    missing = [name for name in COMMON if not (KITS / kit / name).is_file()]
    assert not missing, missing


@pytest.mark.parametrize("kit", JAVA_KITS)
def test_java_kit_wires_the_sensors(kit):
    base = KITS / kit
    assert not [name for name in JAVA_FILES if not (base / name).is_file()]
    pom = (base / "pom.xml").read_text()
    for marker in ("archunit", "maven-pmd-plugin", "maven-checkstyle-plugin", "pitest-maven", "cpd-check"):
        assert marker in pom, marker
    assert "<mutationThreshold>" not in pom, "PIT is a confidence signal, not a gate"
    tests = list((base / "src" / "test").rglob("ArchitectureTest.java"))
    assert tests, "no ArchitectureTest.java under src/test"
    assert list((base / "src" / "test").rglob("ProjectArchitectureTest.java"))
    assert "${env.ORG_MAVEN_MIRROR}" in (base / ".mvn" / "settings.xml").read_text()


@pytest.mark.parametrize("kit", JAVA_KITS)
def test_java_kit_sensor_files_are_copies_of_the_core(kit):
    for name in ("pmd-ruleset.xml", "checkstyle.xml"):
        copy = KITS / kit / "config" / "sensors" / name
        assert copy.read_bytes() == (ROOT / "sensors" / name).read_bytes(), name
    arch = next((KITS / kit / "src" / "test").rglob("ArchitectureTest.java")).read_text()
    core = (ROOT / "sensors" / "ArchitectureTest.java").read_text()
    rule_lines = [line for line in core.splitlines() if ".because(" in line]
    assert rule_lines and all(line in arch for line in rule_lines)


@pytest.mark.parametrize("kit", REACT_KITS)
def test_react_kit_wires_the_sensors(kit):
    base = KITS / kit
    assert not [name for name in REACT_FILES if not (base / name).is_file()]
    package = json.loads((base / "package.json").read_text())
    dev = package.get("devDependencies", {})
    assert "eslint" in dev and "typescript" in dev
    for script in ("lint", "typecheck", "test"):
        assert package["scripts"].get(script), script
    assert json.loads((base / "tsconfig.json").read_text())["compilerOptions"]["strict"] is True
    assert "eslint-sensors.json" in (base / "eslint.config.js").read_text()
    copied = json.loads((base / "config" / "sensors" / "eslint-sensors.json").read_text())
    assert copied == json.loads((ROOT / "sensors" / "eslint-sensors.json").read_text())
    assert "registry=${ORG_NPM_REGISTRY}" in (base / ".npmrc").read_text()


@pytest.mark.parametrize("kit", JAVA_KITS + REACT_KITS)
def test_settings_wire_the_baton_hooks(kit):
    text = (KITS / kit / ".claude" / "settings.json").read_text()
    settings = json.loads(text)
    assert "PreToolUse" in settings["hooks"]
    for hook in HOOKS:
        assert hook in text, hook


@pytest.mark.parametrize("kit", JAVA_KITS + REACT_KITS)
def test_claude_md_imports_agents_md(kit):
    assert "@AGENTS.md" in (KITS / kit / "CLAUDE.md").read_text()


@pytest.mark.parametrize("kit", JAVA_KITS + REACT_KITS)
def test_runbook_has_the_operational_headings(kit):
    headings = re.findall(r"^## (\w+)", (KITS / kit / "RUNBOOK.md").read_text(), re.M)
    assert all(h in headings for h in RUNBOOK_HEADINGS), headings


@pytest.mark.parametrize("kit", JAVA_KITS + REACT_KITS)
def test_ci_runs_the_same_bar_on_every_change(kit):
    ci = (KITS / kit / ".github" / "workflows" / "ci.yml").read_text()
    assert re.search(r"^on:\n(\s+\w+:\n)*\s+push:", ci, re.M) and "pull_request:" in ci
    assert "branch protection" in ci.lower()
    uses = re.findall(r"uses: (\S+)", ci)
    assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@v\d+", u) for u in uses), uses
    steps = "\n".join(line for line in ci.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"skip|continue-on-error", steps, re.I), "a stage is skipped or allowed to fail"
    assert re.findall(r"^\s+if: (.+)$", steps, re.M) in ([], ["always()"]), "only the upload is conditional"
    if kit in JAVA_KITS:
        for sensor in ("mvn -B -ntp verify", "ArchitectureTest", "PMD", "Checkstyle", "pitest-maven"):
            assert sensor in ci, sensor
    else:
        for sensor in ("ESLint", "npm run lint", "npm run typecheck", "npm test"):
            assert sensor in ci, sensor


def test_every_kit_file_is_ascii_and_free_of_project_words():
    words = _project_words()
    bad = []
    for path in kit_files():
        data = path.read_bytes()
        if not data.isascii():
            bad.append(f"non-ASCII: {path.relative_to(ROOT)}")
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if words.search(line):
                bad.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:80]}")
    assert not bad, "\n".join(bad)


def test_the_ui_kit_lints_accessibility_and_the_library_boundary():
    base = KITS / "react-ts-ui"
    config = (base / "eslint.config.js").read_text()
    assert "jsx-a11y" in config and "no-restricted-imports" in config and "ui-library.json" in config
    library = json.loads((base / "config" / "ui-library.json").read_text())
    assert library["import"] and library["forbid"]
    package = json.loads((base / "package.json").read_text())
    assert package["scripts"]["ui:sensors"] == "node scripts/ui-sensors.mjs"
    wanted = {"eslint-plugin-jsx-a11y", "@playwright/test", "@axe-core/playwright"}
    assert wanted <= set(package["devDependencies"])
    runner = (base / "scripts" / "ui-sensors.mjs").read_text()
    assert "axe.json" in runner and "web-vitals.json" in runner and "wcag22aa" in runner
