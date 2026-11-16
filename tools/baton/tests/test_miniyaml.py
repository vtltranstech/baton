"""The contracts' own YAML examples must parse: this is the subset every worktree depends on."""
from baton.cli import main
from baton.miniyaml import loads


def test_flow_list_and_map_from_the_contracts():
    data = loads(
        '''
generated: 2026-11-01T10:00:00Z
repos:
  - repo: deal
    commit: 3f9c2e1
    edges:
      - kind: EXPOSES
        from: class:com.x.api.ClientController
        to: "endpoint:GET /api/v1/clients/{id}/pricing"
        provenance: {file: src/A.java, line: 31, extractor: request-mapping}
zones:
  - name: outbound
    paths: ["**/outbound/**", "**/*FileWriter*"]   # comment
    cap: 50
'''
    )
    edge = data["repos"][0]["edges"][0]
    assert edge["to"] == "endpoint:GET /api/v1/clients/{id}/pricing"
    assert edge["from"] == "class:com.x.api.ClientController"
    assert edge["provenance"] == {"file": "src/A.java", "line": 31, "extractor": "request-mapping"}
    assert data["generated"] == "2026-11-01T10:00:00Z"
    assert data["zones"][0]["paths"] == ["**/outbound/**", "**/*FileWriter*"]
    assert data["zones"][0]["cap"] == 50


def test_colon_without_space_is_a_scalar():
    data = loads("members: [class:com.x.A, class:com.x.B]\nitems:\n  - class:com.x.C\n  - topic:a.b\n")
    assert data == {"members": ["class:com.x.A", "class:com.x.B"], "items": ["class:com.x.C", "topic:a.b"]}


def test_empty_collections_and_scalars():
    assert loads("a: []\nb: {}\nc: true\nd: 0.8\ne: 3\nf: null\ng: 'x y'\n") == {
        "a": [], "b": {}, "c": True, "d": 0.8, "e": 3, "f": None, "g": "x y",
    }


def test_unbuilt_subcommand_refuses():
    # argparse --help must never need an optional dependency; unbuilt commands exit 2.
    import baton.cli as cli

    cli.SUBCOMMANDS["__unbuilt"] = "baton.no_such_module"
    try:
        assert main(["__unbuilt"]) == 2
    finally:
        del cli.SUBCOMMANDS["__unbuilt"]
