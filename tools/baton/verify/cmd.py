"""Check each wiki page's claims against dependencies.yaml at the same commit; sets `verified: true`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from baton.extract.repos import MissingInput, git_commit, git_dirty, select_repos
from baton.verify.check import page_reasons, repo_reasons
from baton.wiki import index
from baton.wiki.facts import load_facts
from baton.wiki.page import with_state, write_atomic

REPORT_NAME = "verify-report.json"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="repo name from profile/project.md")


def _check_one(path: Path, facts, shared: list[str]) -> list[str]:
    """Writes the page's state and returns why it failed. A page with no frontmatter is left as it is."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"frontmatter: the page cannot be read: {exc}"]
    reasons, page = page_reasons(text, path.stem, facts, shared)
    if page is not None:
        updated = with_state(text, not reasons, commit=facts.commit)
        if updated != text:
            write_atomic(path, updated)
    return reasons


def run(args: argparse.Namespace) -> int:
    central = Path(args.central)
    try:
        repo = select_repos(central, args.repo)[0]
        facts = load_facts(central, repo)
        pages_dir = central / index.WIKI_DIR / repo.name
        paths = sorted(pages_dir.glob("*.md")) if pages_dir.is_dir() else []
        if not paths:
            raise MissingInput(f"no pages under {pages_dir}: run baton wiki {repo.name}")
    except MissingInput as exc:
        print(f"baton verify: {exc}", file=sys.stderr)
        return 2
    head, head_reason = git_commit(repo.path)
    shared = repo_reasons(facts, head, head_reason, git_dirty(repo.path) if head != "unknown" else False)
    entries = []
    for path in paths:
        reasons = _check_one(path, facts, shared)
        entries.append(
            {
                "page": path.relative_to(central).as_posix(),
                "module": path.stem,
                "status": "failed" if reasons else "passed",
                "reasons": reasons,
            }
        )
        for reason in reasons:
            print(f"baton verify: {path.stem}: {reason}", file=sys.stderr)
    failed = sum(1 for entry in entries if entry["reasons"])
    report = {
        "repo": repo.name,
        "commit": facts.commit,
        "checkedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": len(entries) - failed,
        "failed": failed,
        "modulesWithoutPage": sorted(set(facts.modules) - {path.stem for path in paths}),
        "pages": entries,
    }
    write_atomic(pages_dir / REPORT_NAME, json.dumps(report, indent=2) + "\n")
    index.regenerate(central)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{repo.name} @ {facts.commit}: {report['passed']} passed, {failed} failed")
    return 1 if failed else 0
