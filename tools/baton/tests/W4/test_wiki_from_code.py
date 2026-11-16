"""`baton wiki` without --prose: no model call, pages from the code; --prose stops at a quota error."""

import pytest
from baton.wiki import body
from baton.wiki.facts import Module
from w4_helpers import ALL_MODULES, REPO, page_path, run_cli


def wiki(central, *more):
    return run_cli("wiki", REPO, "--central", str(central), "--no-prose-default", *more)


def test_the_default_calls_no_model_and_writes_every_page(central, stub, monkeypatch, tmp_path):
    monkeypatch.setenv("BATON_CLAUDE_BIN", str(tmp_path / "no-claude-here"))
    assert wiki(central) == 0
    assert stub() == []
    for module in ALL_MODULES:
        text = page_path(central, module).read_text()
        assert "## Purpose" in text and "## Invariants observed in tests" in text, module


def test_a_default_page_verifies(central, stub):
    assert wiki(central) == 0
    assert run_cli("verify", REPO, "--central", str(central)) == 0


def test_purpose_and_tests_are_read_from_the_code(tmp_path):
    source = tmp_path / "FeeService.java"
    source.write_text(
        "package x;\n/**\n * Works out the monthly fee. Uses the tier table.\n * @since 1\n */\n"
        "@Service\npublic final class FeeService {}\n"
    )
    test = tmp_path / "FeeServiceTest.java"
    test.write_text(
        'class FeeServiceTest {\n  @Test\n  @DisplayName("zero balance pays nothing")\n  void zero() {}\n'
        "  @ParameterizedTest\n  @ValueSource(ints = {1, 2})\n  public void tiers(int t) {}\n"
        "  void helper() {}\n}\n"
    )
    module = Module("application.service", sources=[source], tests=[test])
    assert "- `FeeService`: Works out the monthly fee." in body.purpose_from_code(module)
    invariants = body.invariants_from_tests(module)
    assert "- `FeeServiceTest.zero`: zero balance pays nothing" in invariants
    assert "- `FeeServiceTest.tiers`" in invariants and "helper" not in invariants
    assert body.invariants_from_tests(Module("m", sources=[source])).startswith("None observed")


QUOTA_STUB = """#!{python}
import os, sys
log = os.environ["STUB_LOG"]
open(log, "a").write("{{}}\\n")
sys.stderr.write("Vertex AI: 429 RESOURCE_EXHAUSTED: Quota exceeded for aiplatform")
sys.exit(1)
"""


def test_a_quota_error_stops_model_calls_and_still_writes_pages(central, stub, tmp_path, monkeypatch, capsys):
    import sys

    script = tmp_path / "quota-claude"
    script.write_text(QUOTA_STUB.format(python=sys.executable))
    script.chmod(0o755)
    monkeypatch.setenv("BATON_CLAUDE_BIN", str(script))
    assert wiki(central, "--prose") == 0
    assert len(stub()) == 1
    assert "quota" in capsys.readouterr().err
    for module in ALL_MODULES:
        assert page_path(central, module).is_file(), module


@pytest.mark.parametrize(
    "answer",
    [
        "### purpose\nHolds it.\n\n### Invariants Observed In Tests:\nNone.\n",
        "**Purpose**\nHolds it.\n\n**Invariants observed in tests**\nNone.\n",
    ],
)
def test_heading_variations_are_accepted(answer):
    from baton.wiki import model

    assert model.parse_answer(answer)["Purpose"] == "Holds it."
