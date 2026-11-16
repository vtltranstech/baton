"""baton models: model per role from profile/models.yaml (contracts/models-and-activation.md section 3)."""

import copy
import json
import shutil
from pathlib import Path

import pytest
from baton import miniyaml
from baton.cli import main
from baton.models import DEFAULTS, problems

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-central-repo"


@pytest.fixture
def central(tmp_path):
    target = tmp_path / "central"
    shutil.copytree(FIXTURE, target)
    return target


def test_the_template_is_the_defaults_and_matches_the_schema():
    template = miniyaml.load_file(str(ROOT / "templates" / "profile" / "models.yaml"))
    assert template == DEFAULTS
    assert problems(template) == []
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(template, json.loads((ROOT / "schemas" / "models.json").read_text()))


@pytest.mark.parametrize(
    ("role", "track", "value", "why"),
    [
        ("review-lenses", "light", "fast", "review-lenses (fast) reviews developer (strong)"),  # escalation
        ("design-lenses", "full", "fast", "design-lenses (fast) reviews architect (strong)"),
        ("security", "spike", "cheap", "security (cheap) reviews developer (strong)"),
    ],
)
def test_rule_1_a_reviewer_is_never_weaker(role, track, value, why):
    doc = copy.deepcopy(DEFAULTS)
    doc["roles"][role][track] = value
    assert any(why in p for p in problems(doc))


def test_opus_implements_sonnet_reviews_is_refused():
    doc = copy.deepcopy(DEFAULTS)
    doc["escalation"] = {}
    doc["roles"]["developer"]["full"] = "strong"
    doc["roles"]["review-lenses"]["full"] = "fast"
    assert any("rule 1" in p for p in problems(doc))


def test_a_full_story_and_a_light_story_after_a_failed_qa_loop(central, capsys):
    assert main(["models", "S-151", "--json", "--central", str(central)]) == 0
    full = json.loads(capsys.readouterr().out)
    assert full["track"] == "full" and full["source"].startswith("framework defaults")
    assert full["roles"]["architect"]["model"] == "opus" and full["roles"]["developer"]["model"] == "sonnet"
    assert "developer by sonnet, reviewed by opus (review-lenses; different models)" in full["pairing"]
    assert main(["models", "S-152", "--json", "--central", str(central)]) == 0
    light = json.loads(capsys.readouterr().out)
    assert light["track"] == "light" and "developer_after_qa_fail" in light["escalations"]
    escalated = {"alias": "strong", "model": "opus", "escalated": "developer_after_qa_fail"}
    assert light["roles"]["developer"] == escalated
    same = "developer by opus, reviewed by opus (review-lenses; independent by context only)"
    assert same in light["pairing"]


def test_the_project_file_is_used_and_a_bad_one_refused(central, capsys):
    text = (ROOT / "templates" / "profile" / "models.yaml").read_text()
    (central / "profile" / "models.yaml").write_text(text.replace("strong: opus", "strong: my-gateway-opus"))
    assert main(["models", "S-151", "--json", "--central", str(central)]) == 0
    assert json.loads(capsys.readouterr().out)["roles"]["architect"]["model"] == "my-gateway-opus"
    bad = text.replace("review-lenses:   { light: strong", "review-lenses:   { light: fast")
    (central / "profile" / "models.yaml").write_text(bad)
    assert main(["models", "--check", "--central", str(central)]) == 2
    assert "rule 1" in capsys.readouterr().err
