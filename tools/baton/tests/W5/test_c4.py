import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from baton.graph.c4 import extract_dynamic_views, lower_camel, render
from baton.graph.model import Edge
from baton.graph.profile_files import Profile, read_profile

WORKSPACE = "docs/architecture/workspace.dsl"
JAR_VAR = "BATON_STRUCTURIZR_JAR"
DYNAMIC = """
        // the architect's view, kept
        dynamic accountService "S-010" "Account lookup" {
            statementBatch -> accountController "GET /api/v1/accounts/{id}"
            accountRepository -> mongodb "accounts"
            autoLayout lr
        }
"""


def _generate(cli, central):
    code, _, err = cli("c4", "--central", str(central))
    assert code == 0, err
    return (central / WORKSPACE).read_text()


def _with_view(text):
    return text.replace("        styles {", DYNAMIC.lstrip("\n") + "        styles {")


def _validate_with_cli(path: Path):
    jar = os.environ.get(JAR_VAR)
    if not jar:
        pytest.skip(
            f"{JAR_VAR} not set: point it at structurizr-cli's lib/structurizr-cli.jar to run validate"
        )
    assert Path(jar).is_file(), f"{JAR_VAR}={jar} does not exist"
    done = subprocess.run(
        [
            "java",
            "-cp",
            f"{Path(jar).parent}/*",
            "com.structurizr.cli.StructurizrCliApplication",
            "validate",
            "-workspace",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_generation_is_deterministic(cli, central):
    first = _generate(cli, central)
    shutil.rmtree(central / ".baton")
    (central / WORKSPACE).unlink()
    assert _generate(cli, central) == first


def test_projection_contents(cli, central):
    text = _generate(cli, central)
    assert 'workspace "Sample Ledger" "Loads account data and issues statements"' in text
    assert 'user = person "Billing Analyst"' in text
    assert 'ledgerLoader = container "ledger-loader" "Nightly account loader" "Spring Batch"' in text
    assert 'accountService = container "account-service" "Account APIs" "Spring Boot"' in text
    assert 'mongodb = container "mongodb" "collections: accounts" "MongoDB"' in text
    assert 'kafka = container "kafka"' in text
    assert 'coreLedger = softwareSystem "Core Ledger" "system of record for balances"' in text
    assert (
        'unknownConsumerOfQueueSettlementIn = softwareSystem "Unknown consumer of queue:SETTLEMENT.IN"'
        in text
    )
    assert 'accountController = component "AccountController" "" "Spring @RestController"' in text
    assert 'nightlyAccountLoad = component "nightlyAccountLoad" "" "Spring Batch Job"' in text
    assert "accountDoc" not in text  # a document class is not a stereotype
    assert 'accountRepository -> mongodb "accounts" "MongoDB read"' in text
    assert 'accountClient -> accountController "GET /api/v1/accounts/{id}" "REST/JSON"' in text
    assert 'accountExtractWriter -> accountExtractReader "outbound/accounts-*.csv" "file"' in text
    assert 'kafka -> accountEventListener "account.events" "Kafka consume"' in text
    assert 'component accountService "accountServiceComponents"' in text


def test_all_identifiers_are_lower_camel(cli, central):
    text = _generate(cli, central)
    for name in re.findall(r"(?m)^\s*(\w+) = (?:person|softwareSystem|container|component)\b", text):
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", name), name


def test_check_clean_then_detects_drift(cli, central):
    _generate(cli, central)
    assert cli("c4", "--central", str(central), "--check")[0] == 0
    deps = central / "profile/dependencies.yaml"
    deps.write_text(
        deps.read_text()
        + (
            "      - kind: PUBLISHES\n        from: class:com.sample.statement.NewPublisher\n"
            "        to: topic:new.topic\n"
            "        provenance: {file: N.java, line: 3, extractor: kafka-template}\n"
        )
    )
    code, _, err = cli("c4", "--central", str(central), "--check")
    assert code == 1 and "newPublisher" in err
    code, out, _ = cli("c4", "--central", str(central), "--check", "--json")
    assert code == 1 and json.loads(out)["drift"] is True


def test_check_keeps_dynamic_views_and_ignores_comments_and_whitespace(cli, central):
    path = central / WORKSPACE
    text = _generate(cli, central)
    path.write_text("// a human comment\n" + _with_view(text).replace("    model {", "      model {"))
    assert cli("c4", "--central", str(central), "--check")[0] == 0


def test_check_reports_manual_model_edit(cli, central):
    path = central / WORKSPACE
    path.write_text(_generate(cli, central).replace('"Account APIs"', '"Edited by hand"'))
    code, _, err = cli("c4", "--central", str(central), "--check")
    assert code == 1 and "Edited by hand" in err


def test_regenerating_keeps_dynamic_views_verbatim(cli, central):
    path = central / WORKSPACE
    path.write_text(_with_view(_generate(cli, central)))
    second = _generate(cli, central)
    assert 'dynamic accountService "S-010" "Account lookup" {' in second
    assert second == _generate(cli, central)
    assert cli("c4", "--central", str(central), "--check")[0] == 0


def test_dynamic_view_on_a_removed_element_is_refused(cli, central):
    path = central / WORKSPACE
    broken = _generate(cli, central).replace(
        "        styles {",
        'dynamic accountService "S-1" {\n  ghost -> accountService "x"\n}\n        styles {',
    )
    path.write_text(broken)
    code, _, err = cli("c4", "--central", str(central))
    assert code == 1 and "ghost" in err
    assert path.read_text() == broken
    assert cli("c4", "--central", str(central), "--check")[0] == 1


def test_dynamic_step_with_no_model_relationship_is_refused(cli, central):
    path = central / WORKSPACE
    path.write_text(
        _generate(cli, central).replace(
            "        styles {",
            'dynamic accountService "S-1" {\n  accountController -> accountRepository "x"\n}\n'
            "        styles {",
        )
    )
    code, _, err = cli("c4", "--central", str(central))
    assert code == 1 and "accountController -> accountRepository has no relationship" in err


def test_check_without_workspace_or_graph_exits_2(cli, central, tmp_path):
    assert cli("c4", "--central", str(central), "--check")[0] == 2
    assert cli("c4", "--central", str(tmp_path))[0] == 2


def test_extract_dynamic_ignores_braces_in_strings_and_comments():
    text = """views {
        dynamic a "S-2" "has } brace" {
            // comment }
            a -> b "{x}"
        }
        styles { }
    }"""
    views = extract_dynamic_views(text)
    assert len(views) == 1 and views[0].startswith('dynamic a "S-2"') and views[0].endswith("}")
    assert "styles" not in views[0]


@pytest.mark.parametrize(
    "name, camel",
    [
        ("account-service", "accountService"),
        ("AccountController", "accountController"),
        ("Core Ledger", "coreLedger"),
        ("nightly_load", "nightlyLoad"),
        ("MQSender", "mqSender"),
        ("2nd-repo", "n2Nd" if False else "n2NdRepo"),
        ("---", "unnamed"),
    ],
)
def test_lower_camel(name, camel):
    assert lower_camel(name) == camel


def test_same_class_name_in_two_repos_gets_qualified_ids_regardless_of_input_order():
    a = Edge(
        "WRITES_COLLECTION",
        "class:x.UserRepository",
        "collection:u",
        "one",
        "a",
        1,
        "spring-data-generic",
        "c",
    )
    b = Edge(
        "READS_COLLECTION",
        "class:y.UserRepository",
        "collection:u",
        "two",
        "b",
        1,
        "spring-data-generic",
        "c",
    )
    text = render([a, b], Profile())
    assert render([b, a], Profile()) == text
    assert "oneUserRepository = component" in text and "twoUserRepository = component" in text


def test_reserved_word_is_not_an_identifier():
    edge = Edge("EXPOSES", "class:x.Model", "endpoint:GET /m", "views", "a", 1, "request-mapping", "c")
    text = render([edge], Profile())
    assert "viewsService = container" in text
    assert "viewsModel = component" in text


def test_profile_reader_tolerates_missing_files_and_tables(tmp_path, central):
    assert read_profile(tmp_path).name == "Product"
    (central / "profile/domain.md").write_text(
        "## External systems\n| Name | What |\n| --- | --- |\n| Mainframe | Masters things |\n"
    )
    assert read_profile(central).externals == [("Mainframe", "Masters things")]
    assert read_profile(central).repos["ledger-loader"].team == "ledger-team"


def test_generated_workspace_validates_with_structurizr(cli, central):
    path = central / WORKSPACE
    path.write_text(_with_view(_generate(cli, central)))
    _generate(cli, central)
    _validate_with_cli(path)


def test_unresolved_literal_validates_with_structurizr(cli, central):
    deps = central / "profile/dependencies.yaml"
    deps.write_text(
        deps.read_text()
        + (
            "      - kind: CALLS_ENDPOINT\n        from: class:com.sample.statement.PricingClient\n"
            '        to: "endpoint:${pricing.base-url}/fees"\n'
            "        provenance: {file: P.java, line: 3, extractor: rest-client-base-url}\n"
        )
    )
    _generate(cli, central)
    _validate_with_cli(central / WORKSPACE)
