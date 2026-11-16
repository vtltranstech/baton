"""Conditional skill activation (contracts/models-and-activation.md section 2): frontmatter per the table."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
HUMAN_ONLY = ("onboard", "retro", "agent-regression", "standup", "sprint-review", "sprint", "deliver")
CHAINED = ("stories", "ready", "build", "ship", "build-context-map")  # chained by other skills
BY_PATH = {
    "design-diagram": ["docs/design/**", "docs/architecture/**"],
    "story-writing": ["docs/stories/**", "docs/features/**"],
    "change-note": ["docs/changes/**", "docs/decisions/**"],
}
PRELOAD = {
    "qa": ["data-check", "review-lenses"],
    "security": ["security-checklist"],
    "architect": ["standards"],
    "developer": ["standards"],
}
STAY_INVOCABLE = ("review-lenses", "design-review-lenses", "elicitation")


def front(path: Path) -> dict[str, str]:
    text = path.read_text()
    assert text.startswith("---\n"), path
    body = text[4: text.index("\n---\n", 4)]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^([\w-]+):\s*(.*)$", body, re.M)}


def as_list(value: str) -> list[str]:
    return [v.strip().strip('"') for v in value.strip("[]").split(",") if v.strip()]


@pytest.mark.parametrize("skill", HUMAN_ONLY)
def test_human_only_workflow_skills(skill):
    assert front(ROOT / "skills" / skill / "SKILL.md").get("disable-model-invocation") == "true"


@pytest.mark.parametrize("skill", CHAINED + STAY_INVOCABLE)
def test_chained_and_review_skills_stay_invocable(skill):
    assert "disable-model-invocation" not in front(ROOT / "skills" / skill / "SKILL.md")


@pytest.mark.parametrize(("skill", "paths"), BY_PATH.items())
def test_path_activated_role_skills(skill, paths):
    meta = front(ROOT / "skills" / skill / "SKILL.md")
    assert as_list(meta["paths"]) == paths and meta["user-invocable"] == "false"


@pytest.mark.parametrize(("agent", "skills"), PRELOAD.items())
def test_agents_preload_their_role_skills(agent, skills):
    meta = front(ROOT / "agents" / f"{agent}.md")
    assert as_list(meta["skills"]) == skills
    for skill in skills:
        assert (ROOT / "skills" / skill / "SKILL.md").is_file()


def test_every_agent_inherits_the_model_the_skill_passes():
    for path in sorted((ROOT / "agents").glob("*.md")):
        assert front(path).get("model") == "inherit", path


def test_build_registers_its_gate_hooks_for_the_session():
    text = (ROOT / "skills" / "build" / "SKILL.md").read_text()
    head = text[: text.index("\n---\n", 4)]
    for hook in ("commit_scope.py", "state_gate.py"):
        assert f'/hooks/run-hook" {hook}' in head and (ROOT / "hooks" / hook).is_file()


def test_every_workflow_skill_is_classified():
    """A new workflow skill must be added to HUMAN_ONLY or CHAINED (with its reason) before it ships."""
    workflow = re.findall(r"/(\w[\w-]*)", (ROOT / "skills" / "workflow" / "SKILL.md").read_text())
    for skill in {"build", "stories", "ready", "sprint", "ship", "onboard", "retro", "agent-regression",
                  "standup", "sprint-review", "deliver"}:
        assert skill in HUMAN_ONLY + CHAINED
    assert workflow
