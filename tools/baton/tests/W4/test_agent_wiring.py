"""An unverified page is never cited: checked over the prompts themselves, with negative controls."""

import re

import pytest
from w4_helpers import ROOT

CONSUMERS = ["architect", "developer", "qa", "documentation"]
PAGE_REFERENCE = "docs/wiki/<repo>/<module>.md"
_ANY_WIKI_PATH = re.compile(r"docs/wiki/[^\s`'\",)]*")
_ALLOWED_PATHS = {PAGE_REFERENCE, "docs/wiki/<repo>/verify-report.json", "docs/wiki/"}


def violations(text: str) -> list[str]:
    """A named page, or a paragraph that points at pages without the rule that only verified ones count."""
    found = [
        m.group(0) for m in _ANY_WIKI_PATH.finditer(text) if m.group(0).rstrip(".:;") not in _ALLOWED_PATHS
    ]
    for paragraph in re.split(r"\n\s*\n", text):
        if PAGE_REFERENCE in paragraph and "verified: true" not in paragraph:
            found.append(paragraph[:80])
    return found


def prompts():
    return sorted([*(ROOT / "agents").glob("*.md"), *(ROOT / "skills").rglob("*.md")])


def test_the_scan_sees_files():
    assert len(prompts()) > 20


@pytest.mark.parametrize("path", prompts(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_prompt_cites_a_page_that_may_be_unverified(path):
    assert violations(path.read_text()) == []


@pytest.mark.parametrize(
    "bad",
    [
        "See docs/wiki/billing/adapters.batch.md for details.",
        f"Read `{PAGE_REFERENCE}` for the modules touched.",
        "Citation: `docs/wiki/<repo>/adapters.batch.md`",
    ],
)
def test_the_check_catches_a_bad_prompt(bad):
    assert violations(bad)


def test_the_check_accepts_the_rule():
    assert violations(f"Read `{PAGE_REFERENCE}`; rely on it only with `verified: true`.") == []


@pytest.mark.parametrize("agent", CONSUMERS)
def test_each_consumer_is_wired(agent):
    text = (ROOT / "agents" / f"{agent}.md").read_text()
    assert PAGE_REFERENCE in text
    if agent != "documentation":  # it regenerates pages; the other three read them
        assert "generatedFrom" in text


def test_consumers_keep_their_base_rules():
    """The wiring is additive: spot checks of rules a careless edit would lose."""
    expect = {
        "architect": ["Stack verification", "Challenge round", "profile/stack-detected.md"],
        "developer": ["ArchUnit is mandatory", "Never run anything against a non-test-environment database"],
        "qa": ["Independence rule", "Any HIGH triaged lens finding"],
        "documentation": ["c4 --check", "Never touch service repos"],
    }
    for agent, lines in expect.items():
        text = (ROOT / "agents" / f"{agent}.md").read_text()
        for line in lines:
            assert line in text, (agent, line)


def test_documentation_regenerates_and_verifies_instead_of_hand_editing():
    text = (ROOT / "agents/documentation.md").read_text()
    assert "--changed-since" in text and "baton verify" in text
    assert "add or correct one line" not in text


def test_onboard_points_at_the_wiki():
    text = (ROOT / "skills/onboard/SKILL.md").read_text()
    assert "baton wiki" in text and "baton verify" in text


def test_skill_exists_with_frontmatter():
    text = (ROOT / "skills/wiki/SKILL.md").read_text()
    assert text.startswith("---\nname: wiki\n")
