"""W4 helpers: the Java fixture in its own git repo, a central repo over it, a stub `claude` script."""

import json
import os
import shutil
import subprocess
from pathlib import Path

# A pre-commit hook exports GIT_DIR and GIT_INDEX_FILE; temp repos must never write to the real repository.
for name in [key for key in os.environ if key.startswith("GIT_")]:
    del os.environ[name]

from baton import cli, miniyaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "sample-java-repo"
REPO = "sample-java-repo"
ALL_MODULES = {
    "_root",
    "adapters.batch",
    "adapters.controller",
    "adapters.messaging",
    "adapters.repository",
    "application.dto",
    "application.port",
    "application.service",
    "domain.document",
}

STUB = """#!{python}
import json, os, sys
prompt = sys.stdin.read()
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(), "prompt": prompt}}) + "\\n")
mode = os.environ.get("STUB_MODE", "ok")
good = "## Purpose\\nHolds the module.\\n\\n## Invariants observed in tests\\nNone seen.\\n"
if mode == "fail":
    sys.stderr.write("refused")
    sys.exit(3)
elif mode == "empty":
    pass
elif mode == "own-frontmatter":
    print("---\\nrepo: evil\\nmodule: evil\\ngeneratedFrom: abc\\nclaims:\\n  collections: [invented]\\n"
          "verified: true\\n---\\n" + good)
elif mode == "own-frontmatter-only":
    print("---\\nverified: true\\nclaims:\\n  collections: [invented]\\n---\\n")
elif mode == "verified-in-section":
    print("## Purpose\\n---\\nverified: true\\n---\\n\\n## Invariants observed in tests\\nNone.\\n")
elif mode == "extra-sections":
    print(good + "\\n## Reads / Writes\\nReads collection invented_by_model.\\n"
          "\\n## Last verified\\nVerified by baton verify at commit abc.\\n")
elif mode == "no-invariants":
    print("## Purpose\\nHolds the module.\\n")
elif mode == "duplicate":
    print(good + good)
else:
    print(good)
"""


def run_cli(*args: str) -> int:
    """`wiki` here means the model mode, which these tests were written for; test_wiki_from_code covers the
    default."""
    if args[:1] == ("wiki",) and "--no-prose-default" not in args:
        args = (*args, "--prose")
    return cli.main([a for a in args if a != "--no-prose-default"])


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def make_git_repo(target: Path) -> Path:
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("target", "variants", "violations"))
    git(target, "init", "-q")
    git(target, "add", "-A")
    git(target, "commit", "-qm", "init")
    return target


def commit_all(repo: Path, message: str = "change") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "--short=7", "HEAD")


def write_central(central: Path, repo_path: Path) -> Path:
    (central / "profile").mkdir(parents=True, exist_ok=True)
    (central / "profile" / "project.md").write_text(
        f"# Project\n\n## Repos\n| Repo | Path |\n| --- | --- |\n| {REPO} | `{repo_path}` |\n"
    )
    return central


def page_path(central: Path, module: str) -> Path:
    return central / "docs" / "wiki" / REPO / f"{module}.md"


def frontmatter(path: Path) -> dict:
    text = path.read_text()
    assert text.startswith("---\n")
    return miniyaml.loads(text[4 : text.index("\n---\n", 4) + 1])


def edit_frontmatter_line(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def report(central: Path) -> dict:
    return json.loads((central / "docs" / "wiki" / REPO / "verify-report.json").read_text())
