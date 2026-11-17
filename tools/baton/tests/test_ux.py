"""UI stories (contracts/ui-stories.md): inventory, ux check, gate 2a, verify, promote, diff."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from baton import state_check
from baton.cli import main
from baton.confidence import sensor_status

ROOT = Path(__file__).resolve().parents[3]
CENTRAL = ROOT / "fixtures" / "sample-central-repo"
UI = ROOT / "fixtures" / "sample-ui"
WIRE = "docs/design/F-300/{}-wireframe"


@pytest.fixture
def central(tmp_path):
    target = tmp_path / "central"
    shutil.copytree(CENTRAL, target)
    for name in ("library", "invoice-ui"):
        shutil.copytree(UI / name, tmp_path / name)
    shutil.copytree(UI / "central", target, dirs_exist_ok=True)
    project = target / "profile" / "project.md"
    text = project.read_text()
    text = text.replace(
        "| estimate.lines.M | 800 |",
        "| estimate.lines.M | 800 |\n| ui.library | Atlas |\n| ui.library.path | ../library |\n"
        "| ui.library.import | @org/atlas |\n| ui.library.forbid | @mui/* |\n| ui.designer | none |",
    )
    text = text.replace(
        "| `../invoice-service` | Invoice APIs | mvn -q clean verify |",
        "| `../invoice-service` | Invoice APIs | mvn -q clean verify |\n"
        "| `../invoice-ui` | Invoice screens | npm run build |",
    )
    project.write_text(text)
    domain = target / "profile" / "domain.md"
    domain.write_text(
        domain.read_text() + "\n### R2 - An invoice total shows only when every line is resolved\n"
        "fields: total, lines\nsource: fixture\nconfirmed: true\n"
    )
    return target


def built(central: Path) -> None:
    shutil.copytree(UI / "built", central.parent / "invoice-ui", dirs_exist_ok=True)


def ux(central, capsys, *args):
    code = main(["ux", *args, "--central", str(central), "--json"])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip().startswith("{") else out


def build(central, capsys, sid, *args):
    code = main(["build", sid, "--central", str(central), "--json", *args])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


def story(central, sid):
    return central / "docs" / "stories" / "F-300" / f"{sid}.md"


def wire(central, sid, name=""):
    return central / WIRE.format(sid) / name


def set_state(central, sid, state):
    path = story(central, sid)
    path.write_text(re.sub(r"^State:.*$", f"State: {state}", path.read_text(), count=1, flags=re.M))


# --- inventory --------------------------------------------------------------------------------------------
def test_the_inventory_reads_the_library_from_source_typings_and_pages(central, capsys):
    code, data = ux(central, capsys, "inventory")
    assert code == 0
    lib = data["library"]
    assert lib["name"] == "Atlas" and lib["forbid"] == ["@mui/*"]
    assert set(lib["components"]) == {"PageHeader", "DataTable", "Card", "Stat", "ActionBar", "StatePanel"}
    assert lib["components"]["DataTable"]["props"] == ["caption", "columns", "rows"]
    assert lib["components"]["Stat"] == {"file": "types/index.d.ts", "props": ["label", "unit", "value"]}
    assert lib["components"]["StatePanel"]["props"] == ["message", "onRetry", "state"]
    repo = data["repos"]["invoice-ui"]
    assert repo["routes"] == [{"path": "/invoices", "component": "InvoiceList", "file": "src/App.tsx"}]
    assert repo["imports"] == {"@org/atlas": ["DataTable", "PageHeader"]}
    assert (central / "profile" / "ui-inventory.yaml").is_file()


def test_extract_ui_is_the_same_inventory(central, capsys):
    assert main(["extract", "--ui", "--central", str(central)]) == 0
    assert "Atlas: 6 components" in capsys.readouterr().out


def test_a_missing_library_folder_is_reported(central, capsys):
    shutil.rmtree(central.parent / "library")
    assert main(["ux", "inventory", "--central", str(central)]) == 2
    assert "ui.library.path ../library does not exist" in capsys.readouterr().err


# --- ux check ---------------------------------------------------------------------------------------------
def test_three_clean_options_pass_and_name_what_is_new(central, capsys):
    code, result = ux(central, capsys, "check", "S-120")
    assert (code, result["ok"], result["problems"]) == (0, True, [])
    assert result["newComponents"] == ["InvoiceTotals"] and result["options"] == [
        "option-1.html",
        "option-2.html",
        "option-3.html",
    ]
    twin = json.loads(wire(central, "S-120", "screen-spec.json").read_text())
    assert twin["screen"] == "invoice-summary" and twin["rules"] == ["R2"]


def test_the_planted_unmapped_field_missing_state_and_colour_fail(central, capsys):
    built(central)
    spec = wire(central, "S-121", "screen-spec.md")
    text = spec.read_text().replace("GET /invoices/{id} -> dueDate", "GET /invoices/{id}/schedule -> dueDate")
    spec.write_text(re.sub(r"^\| empty \|.*\n", "", text, flags=re.M))
    option = wire(central, "S-121", "option-1.html")
    option.write_text(option.read_text().replace('<p class="title">', '<p class="title" style="color: red">'))
    code, result = ux(central, capsys, "check", "S-121")
    assert code == 1
    problems = "\n".join(result["problems"])
    assert "field dueDate: `GET /invoices/{id}/schedule` is not an endpoint" in problems
    assert "state `empty` is missing" in problems
    assert "option-1.html: inline style `color: red`: no colour or font" in problems
    assert result["questions"] and "dueDate" in result["questions"][0]


def test_components_must_come_from_the_library(central, capsys):
    spec = wire(central, "S-120", "screen-spec.md")
    text = (
        spec.read_text()
        .replace("| PageHeader |", "| Header |")
        .replace("New: InvoiceTotals (library: Card, Stat)", "New: InvoiceTotals")
    )
    spec.write_text(text.replace("| DataTable |", "| New: LinesGrid (library: Grid) |"))
    for n in (1, 2, 3):
        option = wire(central, "S-120", f"option-{n}.html")
        text = option.read_text()
        option.write_text(text.replace('data-component="PageHeader"', 'data-component="Header"'))
    problems = "\n".join(ux(central, capsys, "check", "S-120")[1]["problems"])
    assert "region header: Header is not in the inventory (Atlas or the app)" in problems
    assert "region totals: New: InvoiceTotals names no Atlas component it is built from" in problems
    assert "region lines: Grid is not a Atlas component" in problems


def test_labels_rules_and_technical_words(central, capsys):
    spec = wire(central, "S-120", "screen-spec.md")
    spec.write_text(spec.read_text().replace("| Status |", "| Remittance flag |").replace("(R2)", "(R9)"))
    option = wire(central, "S-120", "option-1.html")
    option.write_text(option.read_text().replace("Retry</div>", "Retry, null</div>"))
    problems = "\n".join(ux(central, capsys, "check", "S-120")[1]["problems"])
    assert "label `Remittance flag` uses Remittance, flag" in problems
    assert "rule R9 is not a `### R9` in profile/domain.md" in problems
    assert "option-1.html: technical words on screen: null" in problems


def test_a_new_screen_on_the_light_track_is_refused(central, capsys):
    built(central)
    spec = wire(central, "S-121", "screen-spec.md")
    spec.write_text(re.sub(r"^screen-of-record:.*$", "screen-of-record: new", spec.read_text(), flags=re.M))
    problems = ux(central, capsys, "check", "S-121")[1]["problems"]
    assert any("a new screen is always full track" in p for p in problems)


# --- gate 2a in baton build -------------------------------------------------------------------------------
def test_a_full_ui_story_gets_its_wireframe_approved_before_the_design(central, capsys):
    lens = central / "docs" / "design" / "F-300" / "S-120-reviews" / "ux.md"
    lens.unlink()
    code, act = build(central, capsys, "S-120")
    assert (act["kind"], act["step"], act["agent"]) == ("agent", "wireframe", "architect")
    assert "up to three options" in act["text"] and "profile/ui-inventory.yaml" not in act["inputs"]
    code, act = build(central, capsys, "S-120", "--done", "wireframe")
    assert "baton ux check: ok" in act["log"] and (act["kind"], act["step"]) == ("do", "ux-lens")
    assert build(central, capsys, "S-120", "--done", "ux-lens")[1]["step"] == "ux-lens"  # refused: no ux.md
    shutil.copyfile(UI / "central" / "docs" / "design" / "F-300" / "S-120-reviews" / "ux.md", lens)
    code, act = build(central, capsys, "S-120", "--done", "ux-lens")
    assert (act["kind"], act["step"]) == ("gate", "gate2a")
    assert act["options"] == ["option-1", "option-2 (Recommended)", "option-3", "changes", "block"]
    assert wire(central, "S-120", "index.html").is_file()
    code, act = build(central, capsys, "S-120", "--answer", "option-2", "--by", "TL")
    assert code == 2 and "gate 2a is the PO's" in act["text"]
    code, act = build(central, capsys, "S-120", "--answer", "changes", "--by", "PO", "--note", "lines first")
    assert act["step"] == "wireframe" and "lines first" in act["text"]
    build(central, capsys, "S-120", "--done", "wireframe")
    code, act = build(central, capsys, "S-120", "--done", "ux-lens")
    assert act["step"] == "gate2a"
    code, act = build(central, capsys, "S-120", "--answer", "option-2", "--by", "PO", "--note", "send first")
    assert (act["kind"], act["agent"]) == ("agent", "architect")
    assert f"{WIRE.format('S-120')}/approved.html" in act["inputs"]
    assert f"{WIRE.format('S-120')}/screen-spec.md" in act["inputs"]
    approved = wire(central, "S-120", "approved.html").read_text()
    assert approved == wire(central, "S-120", "option-2.html").read_text()
    text = story(central, "S-120").read_text()
    assert "PO: Changes requested (round 1): lines first" in text
    assert "PO: Option 2 approved - send first" in text
    steps = [s["step"] for s in json.loads((central / "docs/qa/F-300/S-120-build.json").read_text())["steps"]]
    once = ["wireframe", "ux-check", "ux-lens", "gate2a"]
    assert steps == ["deps", *once, *once]


def test_a_failed_ux_check_goes_back_to_the_architect_with_the_problems(central, capsys):
    build(central, capsys, "S-120")
    spec = wire(central, "S-120", "screen-spec.md")
    spec.write_text(re.sub(r"^\| loading \|.*\n", "", spec.read_text(), flags=re.M))
    code, act = build(central, capsys, "S-120", "--done", "wireframe")
    assert act["step"] == "wireframe" and "state `loading` is missing" in act["text"]
    assert any("back to the architect" in line for line in act["log"])


def test_a_light_ui_story_is_one_question_for_the_po_and_the_tech_lead(central, capsys):
    built(central)
    code, act = build(central, capsys, "S-121")
    assert act["step"] == "wireframe" and "delta on the screen of record" in act["text"]
    code, act = build(central, capsys, "S-121", "--done", "wireframe")
    assert (act["kind"], act["agent"]) == ("agent", "architect")
    assert f"{WIRE.format('S-121')}/option-1.html" in act["inputs"]
    design = central / "docs" / "design" / "F-300" / "S-121-design.md"
    design.write_text("# Design (light): S-121\n\n## 5. Confidence\nScore: 95%\n")
    set_state(central, "S-121", "Designed")
    code, act = build(central, capsys, "S-121", "--done", "architect")
    assert (act["kind"], act["step"]) == ("gate", "gate2")  # no auto-pass for a ui story
    assert act["options"][0] == "approve (wireframe + design)" and "--by PO+TL" in act["then"]
    code, act = build(central, capsys, "S-121", "--answer", "approve", "--by", "TL")
    assert code == 2 and "--by PO+TL" in act["text"]
    code, act = build(central, capsys, "S-121", "--answer", "approve", "--by", "PO+TL")
    assert act["agent"] == "developer"
    text = story(central, "S-121").read_text()
    assert "PO+TL: delta approved with the design" in text and "State: Design Approved" in text
    assert wire(central, "S-121", "approved.html").is_file()


def test_designed_needs_the_approved_wireframe(central):
    path = story(central, "S-120")
    (central / "docs" / "design" / "F-300" / "S-120-design.md").write_text("# Design: S-120\n")
    (central / "docs" / "design" / "F-300" / "S-120.dsl").write_text("workspace {}\n")
    result = state_check.check(path, "Designed", story_text=path.read_text(), central=central)
    assert not result.ok and "approved.html (gate 2a" in result.missing
    shutil.copyfile(wire(central, "S-120", "option-2.html"), wire(central, "S-120", "approved.html"))
    result = state_check.check(path, "Designed", story_text=path.read_text(), central=central)
    assert not result.ok and "Wireframe approval" in result.missing
    text = path.read_text() + "\n## Wireframe approval\n- 2026-11-17 PO: Option 2 approved\n"
    assert state_check.check(path, "Designed", story_text=text, central=central).ok


# --- the built screen, promotion, compare -----------------------------------------------------------------
def test_the_built_screen_conforms_and_drift_is_caught(central, capsys):
    built(central)
    code, result = ux(central, capsys, "verify", "S-120")
    assert (code, result["ok"], result["mismatches"]) == (0, True, [])
    assert result["files"][0] == "invoice-ui:src/pages/InvoiceSummary.tsx"
    totals = central.parent / "invoice-ui" / "src" / "components" / "InvoiceTotals.tsx"
    totals.write_text(totals.read_text().replace('label="Total"', 'label="Sum"'))
    page = central.parent / "invoice-ui" / "src" / "pages" / "InvoiceSummary.tsx"
    text = page.read_text().replace('data-state="empty"', 'data-state="blank"')
    page.write_text('import Button from "@mui/material/Button";\n' + text)
    code, result = ux(central, capsys, "verify", "S-120")
    kinds = {(m["severity"], m["kind"]) for m in result["mismatches"]}
    assert code == 1 and not result["ok"]
    assert {("MEDIUM", "label-drift"), ("HIGH", "missing-state"), ("HIGH", "forbidden-import")} <= kinds
    assert (central / "docs" / "qa" / "F-300" / "S-120-ui-verify.json").is_file()


def test_promotion_writes_the_screen_of_record_and_its_history(central, capsys):
    built(central)
    shutil.copyfile(wire(central, "S-120", "option-2.html"), wire(central, "S-120", "approved.html"))
    assert main(["ux", "promote", "S-120", "--date", "2026-11-17", "--central", str(central)]) == 0
    assert main(["ux", "promote", "S-121", "--date", "2026-11-18", "--central", str(central)]) == 0
    screen = central / "docs" / "architecture" / "screens" / "invoice-summary"
    assert (screen / "approved.html").is_file() and (screen / "wireframe.css").is_file()
    history = (screen / "history.md").read_text()
    assert "- 2026-11-17 S-120 (F-300): new screen" in history
    assert "- 2026-11-18 S-121 (F-300): header: +dueDate" in history
    spec = (screen / "screen-spec.md").read_text()
    assert "baton.story: S-121" in spec and "baton.since: 2026-11-17" in spec
    index = (central / "docs" / "architecture" / "screens" / "index.md").read_text()
    assert "| /invoices/{invoiceId} | Billing Clerk | invoice-ui | S-121 |" in index
    capsys.readouterr()


def test_promotion_needs_an_approved_wireframe(central, capsys):
    assert main(["ux", "promote", "S-120", "--central", str(central)]) == 2
    assert "no approved wireframe" in capsys.readouterr().err


def test_diff_outlines_the_changed_region(central, capsys):
    a, b = wire(central, "S-120", "screen-spec.md"), wire(central, "S-121", "screen-spec.md")
    assert main(["ux", "diff", "invoice-summary", str(a), str(b), "--central", str(central)]) == 0
    page = capsys.readouterr().out
    assert "<div class='region changed' data-region='header'>" in page
    assert "<div class='region' data-region='lines'>" in page and "header: +dueDate" in page


def test_axe_serious_violations_turn_the_sensors_red(tmp_path):
    (tmp_path / "axe.json").write_text(
        json.dumps([{"violations": [{"id": "label", "impact": "critical"}, {"id": "x", "impact": "minor"}]}])
    )
    assert sensor_status(tmp_path)["axe"] == ("red", "axe.json: 1 serious or critical")


def test_the_spec_twin_follows_its_schema(central, capsys):
    jsonschema = pytest.importorskip("jsonschema")
    ux(central, capsys, "check", "S-120")
    schema = json.loads((ROOT / "schemas" / "screen-spec.json").read_text())
    jsonschema.validate(json.loads(wire(central, "S-120", "screen-spec.json").read_text()), schema)
