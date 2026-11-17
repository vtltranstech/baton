"""baton ir: operations and effects lifted from the code map, the text views, the story slice, the MCP
tools, and the read log."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from baton.cli import main

ROOT = Path(__file__).resolve().parents[4]
SERVICE = "fee-service/src/main/java/com/example/sample/application/service"


def run(central: Path, *argv: str, capsys):
    code = main(["ir", *argv, "--central", str(central)])
    return code, capsys.readouterr()


def test_orientation_has_one_line_per_unit(product, capsys):
    code, out = run(product / "central", "show", capsys=capsys)
    assert code == 0, out.err
    assert (
        "fee-service | fee-service | 21 | 4 | fee_accruals | FEE.ADJUSTMENT.ACK, fee.accrual.posted | 2"
        in out.out
    )
    assert "fee-ui | fee-ui |" in out.out


def test_an_operation_shows_lifted_effects_callers_and_entry_points(product, capsys):
    code, out = run(product / "central", "show", "FeeService#accrue", capsys=capsys)
    assert code == 0, out.err
    lines = out.out.splitlines()
    assert lines[0].startswith(
        "service FeeService  src/main/java/com/example/sample/application/service/FeeService.java:13-40"
    )
    assert "  accrue(accountRef, periodKey, scheduleId, balance): FeeSummary  :32-39" in lines
    assert "    calls FeeSchedulePort.findSchedule; FeeCalculator.calculateFee; FeeAccrualPort.save" in lines
    assert "    reads fee_schedules" in lines and "    writes fee_accruals" in lines  # through the ports
    assert "    called by FeeController#accrue, FeeEventListener#onFeeEvent" in lines
    assert "POST /api/v1/fees/{accountRef}/accruals (FeeController#accrue)" in out.out
    assert "topic:fee.events (FeeEventListener#onFeeEvent)" in out.out
    assert "summarise" not in out.out  # only the operation asked for


def test_a_resource_lists_direct_users_and_reaching_entry_points(product, capsys):
    code, out = run(product / "central", "show", "collection:fee_accruals", capsys=capsys)
    assert code == 0, out.err
    assert "  writes FeeAccrualStore#save  fee-service" in out.out
    assert "  reads FeeAccrualStore#findForPeriod  fee-service" in out.out
    assert "also through calls: FeeController#accrue" in out.out
    assert "shape FeeAccrualDoc; indexes account_period" in out.out


def test_the_ui_lifts_http_calls_through_hooks(product, capsys):
    code, out = run(product / "central", "show", "fee-ui", capsys=capsys)
    assert code == 0, out.err
    block = out.out.split("screen FeeSummaryCard", 1)[1].split("hook ", 1)[0]
    assert "calls useFeeSummary.useFeeSummary" in block and "http /api/v1/fees/{accountRef}" in block
    assert "ui fee " not in out.out  # a types-only file says nothing


def test_unknown_names_get_a_suggestion(product, capsys):
    code, out = run(product / "central", "show", "FeeServce", capsys=capsys)
    assert code == 1 and "did you mean FeeService" in out.err
    code, out = run(product / "central", "show", "FeeSummary", capsys=capsys)
    assert code == 1 and "data, not behaviour" in out.err


def test_find_ranks_the_story_words(product, capsys):
    code, out = run(product / "central", "find", "accrue", "fee", "schedule", capsys=capsys)
    assert code == 0, out.err
    assert "op FeeService#accrue" in out.out and "collection:fee_schedules" in out.out
    code, out = run(product / "central", "find", "zzz", capsys=capsys)
    assert code == 1


def _add_java(product: Path, name: str, body: str) -> None:
    (product / SERVICE / f"{name}.java").write_text(
        "package com.example.sample.application.service;\n\n"
        "import com.example.sample.application.port.FeeAccrualPort;\n"
        "import com.example.sample.domain.document.FeeAccrualDoc;\n"
        "import java.math.BigDecimal;\n"
        "import org.springframework.stereotype.Service;\n\n" + body
    )


OVERLOADS = {
    "Rounding": """@Service
public class Rounding {
    public BigDecimal round(BigDecimal a) {
        return a.setScale(2);
    }

    public BigDecimal round(BigDecimal a, int scale) {
        BigDecimal b = a.setScale(scale);
        return b.stripTrailingZeros();
    }
}
""",
    "WaiveByRef": "public interface WaiveByRef {\n    boolean waive(String ref);\n}\n",
    "WaiveByAmount": "public interface WaiveByAmount {\n    boolean waive(BigDecimal amount);\n}\n",
    "Waiver": """@Service
public class Waiver implements WaiveByRef, WaiveByAmount {
    private final FeeAccrualPort accruals;

    public Waiver(FeeAccrualPort accruals) {
        this.accruals = accruals;
    }

    public boolean waive(String ref) {
        accruals.save(null);
        return true;
    }

    public boolean waive(BigDecimal amount) {
        return amount.signum() == 0;
    }
}
""",
    "RoundingUser": """@Service
public class RoundingUser {
    private final Rounding rounding;
    private final WaiveByRef byRef;
    private final WaiveByAmount byAmount;

    public RoundingUser(Rounding rounding, WaiveByRef byRef, WaiveByAmount byAmount) {
        this.rounding = rounding;
        this.byRef = byRef;
        this.byAmount = byAmount;
    }

    public BigDecimal one(BigDecimal x) {
        byRef.waive("r");
        return rounding.round(x);
    }

    public BigDecimal two(BigDecimal x) {
        byAmount.waive(x);
        return rounding.round(x, 3);
    }
}
""",
}


def test_overloads_stay_apart_also_through_interfaces(product, capsys):
    for name, body in OVERLOADS.items():
        _add_java(product, name, body)
    code, out = run(product / "central", "show", "Rounding", capsys=capsys)
    assert code == 0, out.err
    first, second = out.out.split("  round(BigDecimal a, int scale)", 1)
    assert "called by RoundingUser#one" in first and "RoundingUser#two" not in first
    assert "called by RoundingUser#two" in second and "RoundingUser#one" not in second
    code, out = run(product / "central", "show", "Waiver", capsys=capsys)
    by_ref, by_amount = out.out.split("  waive(BigDecimal amount)", 1)
    assert "called by RoundingUser#one" in by_ref and "writes fee_accruals" in by_ref
    assert "called by RoundingUser#two" in by_amount and "fee_accruals" not in by_amount
    code, out = run(product / "central", "show", "RoundingUser", capsys=capsys)
    one, two = out.out.split("  two(", 1)
    assert "writes fee_accruals" in one and "fee_accruals" not in two


def test_mutual_recursion_gets_every_effect(product, capsys):
    _add_java(
        product,
        "PingPong",
        "@Service\npublic class PingPong {\n"
        "    private final FeeAccrualPort accruals;\n\n"
        "    public PingPong(FeeAccrualPort accruals) {\n        this.accruals = accruals;\n    }\n\n"
        "    public void ping(int n) {\n        if (n > 0) {\n            pong(n - 1);\n        }\n    }\n\n"
        "    public void pong(int n) {\n        accruals.save(null);\n        ping(n);\n"
        '        accruals.findForPeriod("a", "b");\n    }\n}\n',
    )
    code, out = run(product / "central", "show", "PingPong", capsys=capsys)
    assert code == 0, out.err
    ping, pong = out.out.split("  pong(", 1)
    for block in (ping, pong):
        assert "reads fee_accruals" in block and "writes fee_accruals" in block


def test_slice_from_the_change_spec(product, capsys):
    central = product / "central"
    code, out = run(central, "slice", "S-201", "--write", capsys=capsys)
    assert code == 0, out.err
    text = (central / ".baton/context/S-201.md").read_text()
    assert text == out.out and text.isascii()
    assert "from spec S-201-change.yaml" in text
    assert f"- {SERVICE}/FeeService.java:32-39 - changed: FeeService#accrue" in text
    assert "FeeAccrualStore.java:20-24 - implements FeeAccrualPort#findForPeriod" in text
    assert "FeeServiceTest.java - test of a touched class" in text
    assert "ProjectArchitectureTest" not in text
    assert "- collection:fee_waivers - used by the new FeeWaiverPolicy#isWaived" in text
    assert "- collection:fee_accruals - touched by these operations; also writes FeeAccrualStore#save" in text


def test_slice_from_story_words_and_the_budget(product, capsys):
    central = product / "central"
    code, out = run(central, "slice", "S-202", capsys=capsys)
    assert code == 0, out.err
    assert "from story words (no change spec yet)" in out.out and "FeeController" in out.out
    code, small = run(central, "slice", "S-201", "--budget", "250", capsys=capsys)
    assert code == 0 and "trimmed to the budget" in small.out and len(small.out) < 1100
    code, out = run(central, "slice", "S-999", capsys=capsys)
    assert code == 2 and "no story S-999" in out.err


def test_mcp_ir_and_find(product):
    from baton.graph.mcp_server import _call

    central = str(product / "central")
    shown = _call("graph.ir", {"name": "FeeService#accrue"}, central)
    assert "writes fee_accruals" in shown["text"]
    assert "fee-service |" in _call("graph.ir", {"name": ""}, central)["text"]
    found = _call("graph.find", {"words": "fee schedule"}, central)
    assert "collection:fee_schedules" in found["hits"]


def _hook(central: Path, payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full = {"cwd": str(central), "session_id": "s1", **payload}
    return subprocess.run(
        [sys.executable, str(ROOT / "hooks" / "read_log.py")],
        input=json.dumps(full),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(central), **(env or {})},
    )


def test_read_log_and_report(product, capsys):
    central = product / "central"
    source = str(product / SERVICE / "FeeService.java")
    read = {"tool_name": "Read", "tool_input": {"file_path": source}, "tool_response": {"content": "x" * 400}}
    for agent in ("architect", "developer", "developer"):
        assert _hook(central, {**read, "agent_type": agent}, {"BATON_STORY": "S-201"}).returncode == 0
    secret = {
        "tool_name": "Bash",
        "tool_input": {"command": "curl -H 'Authorization: Bearer abc' x"},
        "agent_type": "qa",
    }
    assert _hook(central, secret).returncode == 0
    assert (
        _hook(central, {"tool_name": "Grep", "tool_input": {"pattern": "Fee"}, "agent_type": "qa"}).returncode
        == 0
    )
    assert _hook(central, {"tool_name": "Write", "tool_input": {"file_path": source}}).returncode == 0
    assert (
        subprocess.run(
            [sys.executable, str(ROOT / "hooks" / "read_log.py")], input="not json", text=True
        ).returncode
        == 0
    )
    log = (central / ".baton/reads.jsonl").read_text()
    assert "Bearer" not in log and '"cmd": "curl -H"' in log
    assert len(log.splitlines()) == 5  # the Write is not logged
    assert '"file": "fee-service/src/main/java/' in log
    assert main(["reads", "--central", str(central), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    developer = next(a for a in data["agents"] if a["agent"] == "developer")
    assert developer["reads"] == 2 and developer["rereads"] == 1
    assert data["sharedFiles"][0]["agents"] == ["architect", "developer"]
    assert next(a for a in data["agents"] if a["agent"] == "qa")["scans"] == 1
    assert main(["reads", "--central", str(central), "--story", "S-201"]) == 0
    assert "files read by more than one agent: 1" in capsys.readouterr().out
    (central / ".baton/reads.jsonl").unlink()
    assert main(["reads", "--central", str(central)]) == 1


def test_read_log_story_from_branch(product):
    central = product / "central"
    git = central / ".git"
    if not git.is_dir():
        git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/story/F-002-S-010\n")
    read = {"tool_name": "Read", "tool_input": {"file_path": str(central / "x.md")}, "agent_type": "qa"}
    env = {"BATON_STORY": "", "POD_STORY": "", "HARNESS_STORY": ""}
    assert _hook(central, read, env).returncode == 0
    assert json.loads((central / ".baton/reads.jsonl").read_text().splitlines()[-1])["story"] == "S-010"
    assert _hook(central, read, {**env, "BATON_STORY": "S-099"}).returncode == 0
    assert json.loads((central / ".baton/reads.jsonl").read_text().splitlines()[-1])["story"] == "S-099"
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    assert _hook(central, read, env).returncode == 0
    assert json.loads((central / ".baton/reads.jsonl").read_text().splitlines()[-1])["story"] == ""
