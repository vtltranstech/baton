"""Shared W5 helpers: a private copy of the fixture, schema validation, CLI runner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "graph"


@pytest.fixture
def central(tmp_path) -> Path:
    target = tmp_path / "central"
    shutil.copytree(FIXTURE, target)
    return target


@pytest.fixture
def validate():
    def _validate(document, schema_name):
        schema = json.loads((ROOT / "schemas" / f"{schema_name}.json").read_text())
        jsonschema.Draft202012Validator(schema).validate(document)

    return _validate


@pytest.fixture
def cli(capsys):
    from baton.cli import main

    def _run(*argv):
        code = main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err

    return _run


@pytest.fixture
def store(central):
    from baton.graph.loader import load_into
    from baton.graph.sqlite_store import SqliteStore

    graph = SqliteStore()
    load_into(graph, central)
    yield graph
    graph.close()
