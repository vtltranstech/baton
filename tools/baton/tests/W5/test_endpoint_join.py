"""A resolved call carries its base URL; only an unambiguous match may join it to an exposed endpoint."""

from baton.graph.loader import join_called_endpoints
from baton.graph.model import Edge


def _edge(kind, dst, repo):
    return Edge(kind, f"class:com.{repo}.A", dst, repo, "A.java", 1, "x", "abc")


def _call(by_repo):
    return join_called_endpoints(by_repo)["caller"][0].dst


def test_joins_ignoring_base_url_and_path_variable_names():
    by_repo = {
        "caller": [_edge("CALLS_ENDPOINT", "endpoint:GET https://x.test/v1/r/{c}", "caller")],
        "provider": [_edge("EXPOSES", "endpoint:GET /v1/r/{currency}", "provider")],
    }
    assert _call(by_repo) == "endpoint:GET /v1/r/{currency}"


def test_two_providers_stay_literal():
    literal = "endpoint:GET https://x.test/v1/r"
    by_repo = {
        "caller": [_edge("CALLS_ENDPOINT", literal, "caller")],
        "a": [_edge("EXPOSES", "endpoint:GET /v1/r", "a")],
        "b": [_edge("EXPOSES", "endpoint:GET /v1/r", "b")],
    }
    assert _call(by_repo) == literal


def test_method_must_match_and_own_repo_does_not_count():
    literal = "endpoint:GET https://x.test/v1/r"
    wrong_method = {
        "caller": [_edge("CALLS_ENDPOINT", literal, "caller")],
        "a": [_edge("EXPOSES", "endpoint:POST /v1/r", "a")],
    }
    own_repo = {
        "caller": [
            _edge("CALLS_ENDPOINT", literal, "caller"),
            _edge("EXPOSES", "endpoint:GET /v1/r", "caller"),
        ]
    }
    assert _call(wrong_method) == literal
    assert _call(own_repo) == literal


def test_unresolved_placeholder_stays_literal():
    literal = "endpoint:${ledger.base-url}/v1/r"
    by_repo = {
        "caller": [_edge("CALLS_ENDPOINT", literal, "caller")],
        "a": [_edge("EXPOSES", "endpoint:GET /v1/r", "a")],
    }
    assert _call(by_repo) == literal


def test_a_monorepo_module_calling_a_sibling_module_joins():
    from baton.graph.loader import join_called_endpoints
    from baton.graph.model import Edge

    call = Edge(
        "CALLS_ENDPOINT",
        "class:a.C",
        "endpoint:POST http://localhost:8081/internal/x/{id}",
        "mono",
        "svc-a/src/main/java/a/C.java",
        3,
        "rest-client-base-url",
        "c1",
    )
    exposed = Edge(
        "EXPOSES",
        "class:b.Ctl",
        "endpoint:POST /internal/x/{xid}",
        "mono",
        "svc-b/src/main/java/b/Ctl.java",
        9,
        "request-mapping",
        "c1",
    )
    own = Edge(
        "EXPOSES",
        "class:a.Own",
        "endpoint:GET /internal/x/{id}",
        "mono",
        "svc-a/src/main/java/a/Own.java",
        5,
        "request-mapping",
        "c1",
    )
    joined = join_called_endpoints({"mono": [call, exposed, own]})["mono"][0]
    assert joined.dst == "endpoint:POST /internal/x/{xid}"
