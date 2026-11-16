"""Generate wiki pages from the code and dependencies.yaml; `--prose` adds the model's words."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from baton.doclint import to_ascii
from baton.extract.repos import UNKNOWN, MissingInput, git_commit, select_repos
from baton.wiki import body, index, model
from baton.wiki.facts import RepoFacts, load_facts, module_of_file, read_layout
from baton.wiki.page import PageError, parse, render, with_state, write_atomic

DEFAULT_TIMEOUT = 300
_REVISION = re.compile(r"^[0-9A-Za-z][\w./~^-]*$")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="repo name from profile/project.md")
    parser.add_argument(
        "--changed-since",
        metavar="SHA",
        help="regenerate only modules touched since SHA; others are re-stamped",
    )
    parser.add_argument(
        "--module",
        action="append",
        metavar="M",
        help="only this module (repeatable); other pages stay as they are",
    )
    parser.add_argument(
        "--prose",
        action="store_true",
        help="also have the model write Purpose and Invariants (one claude -p call per module)",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per model call (default %(default)s)"
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env)


def _changed_files(repo: Path, since: str) -> set[str]:
    if not _REVISION.match(since):  # comes from an argument or a page; must never reach git as an option
        raise MissingInput(f"not a revision: {since!r}")
    done = _git(repo, "diff", "--no-renames", "--name-only", since, "HEAD", "--")
    if done.returncode != 0:
        raise MissingInput(f"cannot diff {since}..HEAD: {done.stderr.strip()}")
    return {line for line in done.stdout.splitlines() if line}


def _read_page(path: Path) -> dict | None:
    try:
        return parse(path.read_text(encoding="utf-8")).front
    except (PageError, OSError, UnicodeDecodeError):
        return None


def _touched(facts: RepoFacts, central: Path, pages: Path, since: str) -> set[str]:
    """Modules with a changed main or test file since SHA or since their own page, a page that is absent or
    unreadable, or claims that differ from the page's."""
    layout = read_layout(central, facts.repo.name)
    touched = {module_of_file(f, layout) for f in _changed_files(facts.repo.path, since)}
    for name in facts.modules:
        front = _read_page(pages / f"{name}.md")
        if front is None or front.get("claims") != facts.claims(name):
            touched.add(name)
            continue
        generated = front.get("generatedFrom")
        if generated == facts.commit:
            continue
        try:
            changed = _changed_files(facts.repo.path, str(generated))
        except MissingInput:
            touched.add(name)
            continue
        if name in {module_of_file(f, layout) for f in changed}:
            touched.add(name)
    return {name for name in touched if name in facts.modules}


def _generate(name: str, facts: RepoFacts, central: Path, pages: Path, timeout: int | None) -> None:
    """`timeout` None writes the page from the code alone, with no model call."""
    module = facts.modules[name]
    if timeout is None:
        prose = body.prose_from_code(module)
    else:
        prompt = model.build_prompt(
            facts.repo.name,
            name,
            body.edges_text(module.edges),
            module.sources,
            module.tests,
            facts.repo.path,
        )
        prose = model.parse_answer(model.ask(prompt, timeout))
    layout = read_layout(central, facts.repo.name)
    content = to_ascii(body.compose(facts.repo.name, module, facts, layout, central, prose))
    try:
        text = render(facts.repo.name, name, facts.commit, facts.claims(name), content)
    except ValueError as exc:
        raise model.ModelError(f"a claim cannot be written as YAML: {exc}") from exc
    write_atomic(pages / f"{name}.md", text)


def _remove_orphans(facts: RepoFacts, pages: Path) -> list[str]:
    """Only a generated page of this repo goes: a hand-written file stays, and `verify` will fail it."""
    removed = []
    for path in sorted(pages.glob("*.md")) if pages.is_dir() else []:
        front = _read_page(path)
        generated = front and front.get("repo") == facts.repo.name and front.get("module") == path.stem
        if generated and "bodySha256" in front and path.stem not in facts.modules:
            path.unlink()
            removed.append(path.stem)
    return removed


def _restamp(name: str, facts: RepoFacts, pages: Path) -> bool:
    """An untouched page describes this commit too: move it there, and it needs `verify` again."""
    path = pages / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    if parse(text).front.get("generatedFrom") == facts.commit:
        return False
    write_atomic(path, with_state(text, False, new_commit=facts.commit))
    return True


def _select(args, facts: RepoFacts, central: Path, pages: Path) -> set[str]:
    if args.module:
        unknown = sorted(set(args.module) - set(facts.modules))
        if unknown:
            raise MissingInput(
                f"no such module: {', '.join(unknown)}; have {', '.join(sorted(facts.modules))}"
            )
    chosen = set(args.module or facts.modules)
    if args.changed_since:
        if facts.commit == UNKNOWN:
            raise MissingInput(
                "--changed-since needs a repo with a known commit; dependencies.yaml says unknown"
            )
        chosen &= _touched(facts, central, pages, args.changed_since)
    return chosen


def run(args: argparse.Namespace) -> int:
    central = Path(args.central)
    try:
        repo = select_repos(central, args.repo)[0]
        facts = load_facts(central, repo)
        if not facts.modules:
            raise MissingInput(
                f"{repo.name} has no Java modules under src/main/java: the wiki is Java only for now"
            )
        head, reason = git_commit(repo.path)
        if head != facts.commit:
            raise MissingInput(
                f"dependencies.yaml has {repo.name} at {facts.commit}, the repo is at {head}: "
                "run baton extract"
            )
        pages = central / index.WIKI_DIR / repo.name
        chosen = _select(args, facts, central, pages)
    except MissingInput as exc:
        print(f"baton wiki: {exc}", file=sys.stderr)
        return 2
    if chosen and args.prose and model.claude_bin() is None:
        print(f"baton wiki: claude executable not found (see ${model.CLAUDE_BIN_VAR})", file=sys.stderr)
        return 2
    if facts.commit == UNKNOWN:
        print(
            f"baton wiki: {repo.name}: commit is unknown ({reason}); these pages cannot pass verify",
            file=sys.stderr,
        )
    for edge in facts.unassigned:
        print(f"baton wiki: edge outside any module, not claimed: {edge.get('to')}", file=sys.stderr)

    outcome: dict = {
        "repo": repo.name,
        "commit": facts.commit,
        "generated": [],
        "restamped": [],
        "failed": [],
        "withoutProse": [],
    }
    quota_hit = False
    for name in sorted(chosen):
        timeout = args.timeout if args.prose and not quota_hit else None
        try:
            _generate(name, facts, central, pages, timeout)
            outcome["generated"].append(name)
        except model.QuotaError as exc:
            quota_hit = True
            print(f"baton wiki: {name}: {exc}. No more model calls in this run.", file=sys.stderr)
            _generate(name, facts, central, pages, None)
            outcome["generated"].append(name)
        except model.ModelError as exc:
            print(f"baton wiki: {name}: {exc}", file=sys.stderr)
            outcome["failed"].append({"module": name, "reason": str(exc)})
            continue
        if args.prose and timeout is None:
            outcome["withoutProse"].append(name)
    if quota_hit:
        print(
            f"baton wiki: the model quota was reached; {len(outcome['withoutProse'])} pages were "
            "written from the code only. Add prose later with --prose --module <name>.",
            file=sys.stderr,
        )
    if args.changed_since:
        for name in sorted(set(args.module or facts.modules) - chosen):
            if (pages / f"{name}.md").is_file() and _restamp(name, facts, pages):
                outcome["restamped"].append(name)
    outcome["removed"] = [] if args.module else _remove_orphans(facts, pages)
    outcome["index"] = index.regenerate(central).relative_to(central).as_posix()
    if args.json:
        print(json.dumps(outcome, indent=2))
    else:
        print(
            f"{repo.name} @ {facts.commit}: {len(outcome['generated'])} generated, "
            f"{len(outcome['restamped'])} re-stamped, {len(outcome['removed'])} removed, "
            f"{len(outcome['failed'])} failed. Unverified until: baton verify {repo.name}"
        )
    return 1 if outcome["failed"] else 0
