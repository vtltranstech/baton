"""Run extract-stack, extract and c4, then print the open questions as JSON for the /onboard skill."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import importlib
import json
import sys
from pathlib import Path

from baton import miniyaml
from baton.extract import questions as q
from baton.extract.pipeline import DEPENDENCIES_FILE, GENERATED_FILES, RefusedOverwrite, run_extract
from baton.extract.repos import MissingInput, read_repo_table

WORKSPACE = "docs/architecture/workspace.dsl"
C4_MODULE = "baton.graph.c4_cmd"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--interview", action="store_true", help="also group the questions into batches of at most 8"
    )
    parser.add_argument(
        "--allow-sample",
        action="store_true",
        help="allow the framework's own fixtures/sample-* (framework tests only, never a product)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="also report what changed against the files as they were before this run",
    )


def _is_sample(path: Path) -> bool:
    parts = path.resolve().parts
    return any(a == "fixtures" and b.startswith("sample-") for a, b in zip(parts, parts[1:], strict=False))


def _sample_refusal(central: Path) -> str | None:
    """The framework's samples look like a product, so reading one by mistake must not look like success."""
    if _is_sample(central):
        return f"{central.resolve()} is the framework's sample, not a product. Start in your central repo."
    for repo in read_repo_table(central):
        if _is_sample(repo.path):
            return f"profile/project.md lists {repo.path}, the framework's sample. List your own repos."
    return None


def _run_c4(central: Path) -> dict:
    """c4 is another worktree's subcommand. Absent, the skill falls back. Its stdout never joins the JSON."""
    try:
        module = importlib.import_module(C4_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name and (C4_MODULE == exc.name or C4_MODULE.startswith(exc.name + ".")):
            return {"status": "not built yet", "exit": None}
        raise
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--central")
    module.add_arguments(parser)
    args = parser.parse_args(["--central", str(central)])
    with contextlib.redirect_stdout(sys.stderr):
        code = module.run(args)
    return {"status": "ok" if code == 0 else "failed", "exit": code}


def _snapshot(central: Path) -> dict[str, str | None]:
    out = {}
    for name in (*GENERATED_FILES, WORKSPACE):
        path = central / name
        out[name] = path.read_text(encoding="utf-8") if path.is_file() else None
    return out


def _drop_generated(text: str | None) -> list[str]:
    return [ln for ln in (text or "").splitlines() if not ln.startswith("generated:")]


def _edge_keys(text: str | None) -> dict[str, set[tuple]]:
    if not text:
        return {}
    document = miniyaml.loads(text) or {}
    return {
        r["repo"]: {(e["kind"], e["from"], e["to"]) for e in r.get("edges") or []}
        for r in document.get("repos") or []
    }


def _commits(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    return {r["repo"]: r["commit"] for r in (miniyaml.loads(text) or {}).get("repos") or []}


def _refresh_report(before: dict, after: dict) -> dict:
    files = {}
    for name in before:
        old, new = _drop_generated(before[name]), _drop_generated(after[name])
        if old != new or (before[name] is None) != (after[name] is None):
            lines = difflib.unified_diff(old, new, f"before/{name}", f"after/{name}", lineterm="")
            files[name] = "\n".join(lines)
    old_edges, new_edges = _edge_keys(before[DEPENDENCIES_FILE]), _edge_keys(after[DEPENDENCIES_FILE])

    def edge_list(left, right):
        return sorted(
            f"{repo}: {k} {a} -> {b}" for repo in right for k, a, b in right[repo] - left.get(repo, set())
        )

    old_commits, new_commits = _commits(before[DEPENDENCIES_FILE]), _commits(after[DEPENDENCIES_FILE])
    return {
        "changed": bool(files),
        "files": files,
        "edgesAdded": edge_list(old_edges, new_edges),
        "edgesRemoved": edge_list(new_edges, old_edges),
        "commits": {
            repo: {"from": old_commits.get(repo), "to": sha}
            for repo, sha in new_commits.items()
            if old_commits.get(repo) != sha
        },
    }


def run(args: argparse.Namespace) -> int:
    central = Path(args.central)
    try:
        refusal = None if args.allow_sample else _sample_refusal(central)
    except MissingInput as exc:
        print(f"baton onboard: {exc}. Start in your product's central repo.", file=sys.stderr)
        return 2
    if refusal:
        print(f"baton onboard: refused: {refusal}", file=sys.stderr)
        return 2
    before = _snapshot(central)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            outcome = run_extract(central, None)  # also writes stack-detected.md
    except MissingInput as exc:
        print(f"baton onboard: {exc}", file=sys.stderr)
        return 2
    except RefusedOverwrite as exc:
        print(f"baton onboard: {exc}", file=sys.stderr)
        return 1
    c4 = _run_c4(central)
    questions, answered, warnings = q.build_questions(central, outcome)
    report = {
        "central": str(central.resolve()),
        "repos": [{"name": r.name, "path": str(r.path)} for r in read_repo_table(central)],
        "ran": {"extract-stack": "ok", "extract": "ok", "c4": c4},
        "questions": questions,
        "answered": answered,
        "warnings": warnings,
    }
    if args.interview:
        report["batches"] = q.batches(questions)
    if args.refresh:
        report["refresh"] = _refresh_report(before, _snapshot(central))
    print(json.dumps(report, indent=2))
    return 1 if c4["status"] == "failed" else 0
