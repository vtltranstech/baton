"""TypeScript and React sources: REST calls through the compiler API."""

import shutil
from pathlib import Path

import pytest
from baton.extract import ts_backend

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="no Node on the PATH")


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    (tmp_path / "package.json").write_text("{}")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def _targets(result: dict) -> list[str]:
    return [e["to"] for e in result["edges"]]


def test_fetch_template_becomes_a_path_variable_and_drops_the_query(tmp_path):
    repo = _repo(tmp_path, {"src/a.ts": "export const f = (id: string) => fetch(`/api/x/${id}?y=${id}`);\n"})
    result = ts_backend.extract(repo)
    assert _targets(result) == ["endpoint:GET /api/x/{id}"]
    assert result["edges"][0]["provenance"] == {"file": "src/a.ts", "line": 1, "extractor": "ts-fetch"}
    assert result["edges"][0]["from"] == "class:src.a"
    assert result["unresolved"] == []


def test_fetch_method_from_options(tmp_path):
    repo = _repo(
        tmp_path, {"src/a.tsx": 'const V = () => <b onClick={() => fetch("/p", {method: "post"})}>x</b>;\n'}
    )
    assert _targets(ts_backend.extract(repo)) == ["endpoint:POST /p"]


def test_axios_verbs_and_client_with_base_url(tmp_path):
    source = """import axios from "axios";
const BASE = "/api/v2";
const api = axios.create({ baseURL: BASE });
axios.put(`${BASE}/a`, {});
api.delete("/b");
axios({ url: "/c", method: "patch" });
"""
    result = ts_backend.extract(_repo(tmp_path, {"src/a.js": source}))
    assert sorted(_targets(result)) == [
        "endpoint:DELETE /api/v2/b",
        "endpoint:PATCH /c",
        "endpoint:PUT /api/v2/a",
    ]
    assert {e["provenance"]["extractor"] for e in result["edges"]} == {"ts-axios"}


@pytest.mark.parametrize(
    "call, literal",
    [
        ("fetch(`${import.meta.env.VITE_API}/f`)", "endpoint:${VITE_API}/f"),
        ("fetch(process.env.API + '/f')", "endpoint:${API}/f"),
        ("fetch(`${imported}/f`)", "endpoint:${imported}/f"),
        ("fetch(u)", "endpoint:<src/a.ts:1>"),
    ],
)
def test_what_the_file_cannot_tell_stays_literal(tmp_path, call, literal):
    result = ts_backend.extract(_repo(tmp_path, {"src/a.ts": call + ";\n"}))
    assert _targets(result) == [literal] and result["unresolved"] == [literal]


def test_tests_and_declarations_and_dependencies_are_not_read(tmp_path):
    files = {f"src/{n}": "fetch('/no');\n" for n in ("a.test.ts", "b.spec.tsx", "c.d.ts", "__tests__/d.ts")}
    files["src/node_modules/x/e.js"] = "fetch('/no');\n"
    assert ts_backend.extract(_repo(tmp_path, files))["edges"] == []


def test_a_call_in_a_string_or_comment_is_not_a_call(tmp_path):
    repo = _repo(tmp_path, {"src/a.ts": "// fetch('/no')\nconst s = \"fetch('/no')\";\n"})
    assert ts_backend.extract(repo)["edges"] == []


def test_broken_source_is_reported_not_guessed(tmp_path):
    result = ts_backend.extract(_repo(tmp_path, {"src/a.ts": "const = ;\n"}))
    assert result["edges"] == [] and result["failures"][0]["file"] == "src/a.ts"


def test_newest_syntax_parses(tmp_path):
    source = """type C = { a: number };
const x = { a: 1 } satisfies C;
function f<const T extends readonly unknown[]>(t: T) { return t; }
class K { accessor n = 1; @dec m() {} }
export function V() { using r = g(); return <div onClick={() => fetch("/n")}>hi</div>; }
"""
    result = ts_backend.extract(_repo(tmp_path, {"src/a.tsx": source}))
    assert result["failures"] == [] and _targets(result) == ["endpoint:GET /n"]


def test_no_package_json_means_no_frontend(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("fetch('/no');\n")
    assert ts_backend.extract(tmp_path)["parser"] is None


def test_no_node_is_a_failure_not_silence(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.ts": "fetch('/x');\n"})
    monkeypatch.setattr(ts_backend.shutil, "which", lambda _: None)
    result = ts_backend.extract(repo)
    assert result["parser"]["unavailable"] and "Node" in result["failures"][0]["reason"]
