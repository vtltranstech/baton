"""baton diagram: code map from the AST, spec checks, story / as-built / architecture diagrams, context
cards."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from baton.cli import main

SERVICE = "com.example.sample.application.service.FeeService"


def run(central: Path, *argv: str, capsys=None):
    code = main(["diagram", *argv, "--central", str(central)])
    out = capsys.readouterr() if capsys else None
    return code, out


def world(central: Path):
    from baton.diagram.world import load_world

    return load_world(central)


# -- code map ----------------------------------------------------------------------------------------------


def test_code_map_resolves_calls_through_fields_and_interfaces(product):
    w = world(product / "central")
    controller = w.cls("com.example.sample.adapters.controller.FeeController")
    summary = controller.method("summary")[0]
    assert [(c.target.rsplit(".", 1)[-1], c.method, c.via) for c in summary.calls] == [
        ("FeeService", "summarise", "field")
    ]
    assert [u.resource for u in summary.uses] == ["endpoint:GET /api/v1/fees/{accountRef}"]
    accrue = w.method(SERVICE, "accrue")
    assert (accrue.start, accrue.end) == (32, 39)
    assert accrue.throws == ["IllegalArgumentException"]
    port = "com.example.sample.application.port.FeeAccrualPort"
    assert w.implementation(port) == "com.example.sample.adapters.repository.FeeAccrualStore"
    store = w.cls("com.example.sample.adapters.repository.FeeAccrualStore")
    assert {u.kind for m in store.methods for u in m.uses} == {"READS_COLLECTION", "WRITES_COLLECTION"}
    assert any(t.endswith("FeeServiceTest.java") for t in w.cls(SERVICE).tests)


def test_code_map_follows_ui_imports_to_the_endpoint(product):
    w = world(product / "central")
    hook = w.cls("src.hooks.useFeeSummary")
    assert hook.stereotype == "hook"
    assert [(c.target, c.method) for c in hook.methods[0].calls] == [("src.api.feeClient", "fetchFeeSummary")]
    client = w.cls("src.api.feeClient")
    assert [u.kind for u in client.methods[0].uses] == ["CALLS_ENDPOINT"]


def test_code_map_cache_is_reused_and_refreshed_on_edit(product):
    central = product / "central"
    world(central)
    cache = central / ".baton" / "code" / "fee-service.json"
    first = cache.stat().st_mtime_ns
    world(central)
    assert cache.stat().st_mtime_ns == first
    source = product / "fee-service/src/main/java/com/example/sample/application/service/FeeService.java"
    source.write_text(
        source.read_text().replace("public FeeSummary summarise", "public FeeSummary summarise ")
    )
    w = world(central)
    assert cache.stat().st_mtime_ns != first
    assert w.method(SERVICE, "summarise") is not None


# -- spec checks -------------------------------------------------------------------------------------------


def write_spec(product: Path, text: str) -> None:
    (product / "central/docs/design/F-200/S-201-change.yaml").write_text(text)


def test_check_accepts_the_spec_and_writes_nothing(product, capsys):
    code, out = run(product / "central", "story", "S-201", "--check", capsys=capsys)
    assert code == 0, out.err
    assert "FeeController#accrue" in out.out and "FeeEventListener#onFeeEvent" in out.out
    assert not (product / "central/docs/design/F-200/S-201-diagrams").exists()


def test_spec_names_are_checked_against_the_code(product, capsys):
    write_spec(
        product,
        "story: S-201\nchanged:\n  - FeeServce#accrue\n  - FeeService#acrue\nnew:\n"
        "  - class: com.example.sample.application.service.FeeService\n"
        "  - method: FeeService#summarise\n"
        "  - method: FeeService#extra\n    calledFrom: FeeController#summary\n"
        "    before: FeeCalculator#calculateFee\n",
    )
    code, out = run(product / "central", "story", "S-201", "--check", capsys=capsys)
    assert code == 1
    assert "no class FeeServce in the code; did you mean FeeService" in out.err
    assert "FeeService has no method acrue; did you mean accrue" in out.err
    assert "new class com.example.sample.application.service.FeeService already exists" in out.err
    assert "new method FeeService#summarise already exists" in out.err
    assert "before FeeCalculator#calculateFee is not a call in FeeController#summary" in out.err


def test_spec_shape_errors(product, capsys):
    write_spec(product, "story: S-201\nnew:\n  - method: FeeService#x\n    colour: red\nwrong: 1\n")
    code, out = run(product / "central", "story", "S-201", "--check", capsys=capsys)
    assert code == 1
    assert "unknown key 'wrong'" in out.err and "unknown key 'colour'" in out.err
    write_spec(product, "story: S-999\n")
    code, out = run(product / "central", "story", "S-201", "--check", capsys=capsys)
    assert code == 1 and "the spec is for S-999" in out.err


def test_missing_spec_is_refused(product, capsys):
    code, out = run(product / "central", "story", "S-202", capsys=capsys)
    assert code == 2 and "S-202-change.yaml not found" in out.err


# -- story diagrams ----------------------------------------------------------------------------------------


def test_story_diagrams_are_written_and_well_formed(product, capsys):
    central = product / "central"
    code, out = run(central, "story", "S-201", "--json", capsys=capsys)
    assert code == 0, out.err
    summary = json.loads(out.out)
    assert summary["entries"] == ["POST /api/v1/fees/{accountRef}/accruals", "topic fee.events"]
    folder = central / "docs/design/F-200/S-201-diagrams"
    svgs = sorted(p.name for p in folder.glob("*.svg"))
    assert svgs == [
        "data-model.svg",
        "flow.svg",
        "lld.svg",
        "sequence-1.svg",
        "sequence-2.svg",
        "use-cases.svg",
    ]
    for svg in folder.glob("*.svg"):
        root = ET.fromstring(svg.read_text())
        assert root.tag.endswith("svg") and root.get("data-generator") == "baton-diagram"
    page = (folder / "diagrams.md").read_text()
    for image in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", page):
        assert (folder / image).is_file()
    for block in re.findall(r"```mermaid\n(.*?)```", page, re.S):
        first = block.splitlines()[0]
        assert first in ("flowchart LR", "sequenceDiagram", "classDiagram", "erDiagram")
        for label in re.findall(r'"([^"\n]*)"', block):
            assert "<" not in label.replace("<br/>", "").replace("<small>", "").replace("</small>", "")
    html = (folder / "index.html").read_text()
    assert html.count("<svg") == 6 and "http" not in html.split("<style>")[0].replace("http://www.w3.org", "")


def test_sequence_puts_the_new_call_where_the_spec_says(product):
    from baton.diagram import story as story_mod
    from baton.diagram.change import apply_spec
    from baton.diagram.spec import load

    central = product / "central"
    w = world(central)
    change, problems = apply_spec(w, load(central / "docs/design/F-200/S-201-change.yaml"))
    assert problems == []
    d = story_mod.build(w, change, "S-201", "t", "spec", None)
    labels = [m.label for m in d.sequences[0].messages if m.kind != "return"]
    assert labels.index("isWaived(accountRef, periodKey)") < labels.index("calculateFee(balance, rate)")
    statuses = {m.label: m.status for m in d.sequences[0].messages}
    assert statuses["isWaived(accountRef, periodKey)"] == "new"
    assert statuses["findSchedule(scheduleId)"] == "touched"
    assert any(m.kind == "error" and "IllegalArgumentException" in m.label for m in d.sequences[0].messages)
    first = d.sequences[0].participants[0]
    assert first.kind == "person"
    touch = {r["element"]: r for r in d.touch}
    assert touch["FeeService#accrue"]["status"] == "changed"
    assert touch["FeeService#accrue"]["lines"] == "32-39"
    assert touch["FeeWaiverPolicy#isWaived"]["status"] == "new"
    assert touch["collection:fee_waivers"]["status"] == "new"
    lld = {b.name: b for b in d.lld.boxes}
    assert lld["FeeWaiverPolicy"].status == "new" and not lld["FeeAccrualPort"].methods
    data = {b.name: b for b in d.data.boxes}
    assert any(f.text == "waived: boolean" and f.status == "new" for f in data["fee_accruals"].fields)


def test_diagrams_are_byte_identical_across_runs(product, capsys):
    central = product / "central"
    run(central, "story", "S-201", capsys=capsys)
    folder = central / "docs/design/F-200/S-201-diagrams"
    first = {p.name: p.read_bytes() for p in folder.iterdir()}
    run(central, "story", "S-201", capsys=capsys)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == first


def test_other_repos_in_the_blast_radius_are_drawn(product, capsys):
    central = product / "central"
    (central / "docs/design/F-200/S-202-change.yaml").write_text(
        "story: S-202\nchanged:\n  - FeeController#summary\n"
        "removed:\n  - endpoint:GET /api/v1/fees/{accountRef}\n"
    )
    code, out = run(central, "story", "S-202", "--json", capsys=capsys)
    assert code == 0, out.err
    assert json.loads(out.out)["impactedRepos"] == ["fee-ui"]
    page = (central / "docs/design/F-200/S-202-diagrams/diagrams.md").read_text()
    assert (
        "| fee-ui | `endpoint:GET /api/v1/fees/{accountRef}` | `src/api/feeClient.ts:4` | **yes** |" in page
    )
    flow = (central / "docs/design/F-200/S-202-diagrams/flow.svg").read_text()
    assert "IMPACTED" in flow and "useFeeSummary" in flow


def test_as_built_reports_changed_lines_and_drift(product, capsys):
    central = product / "central"
    source = product / "fee-service/src/main/java/com/example/sample/application/service/FeeService.java"
    text = source.read_text().replace(
        "calculator.calculateFee(balance, schedule.rate());",
        "calculator.calculateFee(balance, schedule.rate()).abs();",
    )
    text = text.rstrip()[:-1] + "\n    public int count() {\n        return 0;\n    }\n}\n"
    source.write_text(text)
    code, out = run(central, "story", "S-201", "--diff", "HEAD", "--json", capsys=capsys)
    assert code == 0, out.err
    report = json.loads(out.out)
    assert report["conformance"]["undeclared"] == ["FeeService#count"]
    assert "FeeWaiverPolicy#isWaived" in report["conformance"]["notBuilt"]
    rows = json.loads((central / "docs/qa/F-200/S-201-as-built/diagrams.json").read_text())["touchPoints"]
    by = {r["element"]: r for r in rows}
    assert by["FeeService#accrue"]["status"] == "changed" and by["FeeService#accrue"]["lines"] == "35-35"
    assert by["FeeService#count"]["status"] == "new" and by["FeeService#count"]["reachedFrom"] == []


# -- architecture and context ------------------------------------------------------------------------------


def test_architecture_views(product, capsys):
    central = product / "central"
    code, out = run(central, "architecture", capsys=capsys)
    assert code == 0, out.err
    folder = central / "docs/architecture/diagrams"
    assert {p.name for p in folder.glob("*.svg")} == {
        "context.svg",
        "containers.svg",
        "components-fee-service.svg",
        "components-fee-ui.svg",
    }
    containers = (folder / "containers.svg").read_text()
    for name in (
        "fee-service data",
        "2 collections",
        "fee.accrual.posted",
        "fee.events",
        "fee-ui",
        "fee-service",
    ):
        assert name in containers
    components = (folder / "components-fee-service.svg").read_text()
    assert "FeeService" in components and "FeeAccrualPort" not in components  # drawn as its implementation


def test_context_card(product, capsys):
    central = product / "central"
    code, out = run(central, "context", "FeeService#accrue", capsys=capsys)
    assert code == 0, out.err
    assert (
        "accrue(String accountRef, String periodKey, String scheduleId, BigDecimal balance): "
        "FeeSummary  lines 32-39" in out.out
    )
    assert "called by FeeController#accrue, FeeEventListener#onFeeEvent" in out.out
    assert "FeeAccrualPort#save -> FeeAccrualStore" in out.out
    code, out = run(central, "context", "collection:fee_accruals", capsys=capsys)
    assert code == 0 and "writes by FeeAccrualStore#save" in out.out
    code, out = run(central, "context", "FeeServce", capsys=capsys)
    assert code == 1 and "did you mean FeeService" in out.err


def test_evidence_reports_the_diagrams_and_conformance(product, capsys):
    central = product / "central"
    run(central, "story", "S-201", capsys=capsys)
    source = product / "fee-service/src/main/java/com/example/sample/application/service/FeeService.java"
    source.write_text(source.read_text().replace("schedule.rate());", "schedule.rate()).abs();"))
    run(central, "story", "S-201", "--diff", "HEAD", capsys=capsys)
    assert main(["evidence", "S-201", "--central", str(central)]) == 0
    capsys.readouterr()
    text = (central / "docs/qa/F-200/S-201-evidence.md").read_text()
    assert "- Design diagrams: 4 new, 2 changed, 0 removed; blast radius none" in text
    assert "designed but not built FeeWaiverPolicy#isWaived, FeeWaiverPolicy" in text


def test_generated_docs_are_ascii_and_pass_doclint(product, capsys):
    from baton.doclint import check

    central = product / "central"
    run(central, "story", "S-201", capsys=capsys)
    run(central, "architecture", capsys=capsys)
    assert main(["wiki", "fee-service", "--central", str(central)]) == 0
    assert main(["verify", "fee-service", "--central", str(central)]) == 0
    capsys.readouterr()
    folders = [
        central / "docs/design/F-200/S-201-diagrams",
        central / "docs/architecture/diagrams",
        central / "docs/wiki",
    ]
    for folder in folders:
        for path in folder.rglob("*"):
            if path.suffix in (".md", ".svg", ".html", ".json"):
                assert path.read_text().isascii(), path
    codebase_map = (central / "docs/context/codebase-map.md").read_text()
    assert "| Page | Status | Data (collections, topics, files) | APIs (exposed, called) |" in codebase_map
    block = codebase_map.split("<!-- /wiki-index -->")[0]
    assert check(block, "docs/context/codebase-map.md", style=True) == []


def test_long_unbreakable_labels_are_cut_and_stay_ascii():
    from baton.diagram import svg

    lines = svg.wrap("X" * 400, 120, 13, bold=True, max_lines=1)
    assert len(lines) == 1 and lines[0].endswith("...") and lines[0].isascii()
    assert svg.text_width(lines[0], 13, True) <= 120
