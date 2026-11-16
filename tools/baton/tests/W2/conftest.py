"""W2 test setup: temp central repos over the fixtures, and both parser back-ends."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from baton.extract import javaparser_backend, treesitter_backend

# A pre-commit hook exports GIT_DIR and GIT_INDEX_FILE; temp repos must never write to the real repository.
for name in [key for key in os.environ if key.startswith("GIT_")]:
    del os.environ[name]

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(params=["treesitter", "javaparser", "no-javaparser"])
def backend(request, monkeypatch):
    """Run the test with tree-sitter, then with JavaParser, then with the regex back-end forced."""
    if request.param == "treesitter":
        if not treesitter_backend.available():
            pytest.skip("the baton[treesitter] extra is not installed")
        monkeypatch.setenv("BATON_JAVA_PARSER", "treesitter")
    elif request.param == "javaparser":
        if not javaparser_backend.available():
            pytest.skip("no JDK on the PATH")
        monkeypatch.setenv("BATON_JAVA_PARSER", "javaparser")
    else:
        monkeypatch.setenv("BATON_JAVA_PARSER", "regex")
    return request.param


@pytest.fixture
def root():
    return ROOT


def write_project(central: Path, rows: list[tuple[str, str]], extra: str = "") -> None:
    (central / "profile").mkdir(parents=True, exist_ok=True)
    table = "\n".join(f"| {name} | `{path}` | service |" for name, path in rows)
    (central / "profile" / "project.md").write_text(
        "# Project profile: Sample\n\n## Repos\n| Repo | Path | What it is |\n| --- | --- | --- |\n"
        f"{table}\n{extra}"
    )


@pytest.fixture
def fixture_central(tmp_path):
    """A central repo whose repo table points at the java and react fixtures, in place."""
    central = tmp_path / "central"
    write_project(
        central,
        [
            ("sample-java-repo", str(ROOT / "fixtures/sample-java-repo")),
            ("sample-react-repo", str(ROOT / "fixtures/sample-react-repo")),
        ],
    )
    return central


def make_java_repo(base: Path, name: str, files: dict[str, str], pom: str | None = None) -> Path:
    """A small repo: `files` maps paths under the repo to content; a minimal pom unless one is given."""
    repo = base / name
    repo.mkdir(parents=True)
    (repo / "pom.xml").write_text(pom or MINIMAL_POM)
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return repo


MINIMAL_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <properties><java.version>21</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.kafka</groupId><artifactId>spring-kafka</artifactId></dependency>
  </dependencies>
</project>
"""


def git(repo: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.test",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.test",
    )
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def copy_fixture(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / f"{name}.json").read_text())
