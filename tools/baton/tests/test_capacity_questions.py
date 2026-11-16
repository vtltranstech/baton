"""A design's technology choice starts from numbers: question, guidance and checks are all wired."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


def test_story_and_feature_templates_ask_for_the_numbers():
    assert "## Capacity" in _read("templates/story.md")
    assert "## Capacity" in _read("agents/story-drafter.md")
    assert "## Volumes and load" in _read("templates/feature.md")


def test_ready_treats_missing_numbers_as_a_gap_and_never_fills_them():
    assert "Capacity" in _read("skills/story-writing/SKILL.md")
    ready = _read("skills/ready/SKILL.md")
    assert "`## Capacity`" in ready and "never fill one in" in ready


def test_the_architect_writes_the_choice_and_the_lens_checks_it():
    architect = _read("agents/architect.md")
    assert "## 4b. Capacity and technology choice" in architect and "## 3a. Capacity" in architect
    assert architect.index("## 4a. Pattern ledger") < architect.index("## 4b. Capacity")
    assert "capacity:" in _read("skills/design-review-lenses/SKILL.md")


def test_guidance_covers_the_decisions_and_refuses_an_unmeasured_claim():
    guide = _read("skills/standards/capacity.md")
    for term in ("Spring Batch", "virtual threads", "WebFlux", "Concurrent requests", "Partitions"):
        assert term in guide
    assert "Performance not measured" in guide
    assert "Performance not measured" in _read("skills/data-check/SKILL.md")
