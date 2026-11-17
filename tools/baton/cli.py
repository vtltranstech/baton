"""The one baton CLI (contracts/cli.md). Subcommands live in their own modules.

Each module exposes `add_arguments(parser)` and `run(args) -> int`; a new subcommand is its module plus
one row in the table below. A module must import
optional dependencies (pymongo, javalang) inside functions so `--help` works without them.
"""
from __future__ import annotations

import argparse
import importlib
import re
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2

SUBCOMMANDS = {
    "extract-stack": "baton.extract.stack_cmd",
    "extract": "baton.extract.extract_cmd",
    "onboard": "baton.extract.onboard_cmd",
    "profile": "baton.profile.cmd",
    "wiki": "baton.wiki.cmd",
    "verify": "baton.verify.cmd",
    "graph": "baton.graph.graph_cmd",
    "impact": "baton.graph.impact_cmd",
    "c4": "baton.graph.c4_cmd",
    "mutation": "baton.mutation.cmd",
    "confidence": "baton.confidence",
    "evidence": "baton.evidence",
    "state-check": "baton.state_check",
    "deps": "baton.deps",
    "diagram": "baton.diagram.cmd",
    "doclint": "baton.doclint",
    "ir": "baton.ir.cmd",
    "reads": "baton.reads",
    "install": "baton.install",
    "risk": "baton.risk",
    "eval": "baton.evaluate",
    "trace": "baton.trace.cmd",
    "stories": "baton.stories",
    "board": "baton.board",
    "build": "baton.orchestrate",
    "agents": "baton.agents_check",
    "models": "baton.models",
    "context": "baton.context.cmd",
    "ux": "baton.ux.cmd",
}


def _load(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name and (module_name == exc.name or module_name.startswith(exc.name + ".")):
            return None
        raise


TAG_DOC = "Tag the default branch with a shipped story or feature id (annotated); refuses elsewhere or twice"
_TAG_ID = re.compile(r"^[A-Za-z]+-[A-Za-z0-9]+$")


def _git(central: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(central), *args], capture_output=True, text=True, timeout=30)


def _title(central: Path, ident: str) -> str | None:
    """The `# <id> <title>` line of the story or feature note with that id, if main has one."""
    patterns = (f"docs/stories/*/{ident}.md", f"docs/stories/*/{ident}-*.md", f"docs/features/{ident}.md",
                f"docs/features/{ident}-*.md", f"docs/archive/*/stories/{ident}.md")
    for pattern in patterns:
        for path in sorted(central.glob(pattern)):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(rf"^#\s+{re.escape(ident)}\s+(.+)$", line)
                if match:
                    return match.group(1).strip()
    return None


def tag(args: argparse.Namespace) -> int:
    """`baton tag <S|F>` (contracts/versioning.md section 2): the tag is the version."""
    central = Path(args.central).resolve()
    ident = args.id
    if not _TAG_ID.match(ident):
        print(f"baton tag: {ident!r} is not a story or feature id (e.g. S-010, F-002)", file=sys.stderr)
        return EXIT_REFUSED
    try:
        branch = _git(central, "symbolic-ref", "--short", "-q", "HEAD")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"baton tag: git did not run ({exc})", file=sys.stderr)
        return EXIT_REFUSED
    head = _git(central, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
    defaults = {head.stdout.strip().split("/", 1)[-1]} if head.returncode == 0 else {"main", "master"}
    if branch.returncode != 0 or branch.stdout.strip() not in defaults:
        where = branch.stdout.strip() or "a detached HEAD or no repository"
        wanted = " or ".join(sorted(defaults))
        print(f"baton tag: refused, tags go on the default branch ({wanted}) once the docs PR merged; "
              f"this is {where}", file=sys.stderr)
        return EXIT_REFUSED
    if _git(central, "rev-parse", "-q", "--verify", f"refs/tags/{ident}").returncode == 0:
        print(f"baton tag: refused, tag {ident} already exists; a version is never moved", file=sys.stderr)
        return EXIT_REFUSED
    title = _title(central, ident)
    message = f"{ident}: {title}" if title else ident
    done = _git(central, "tag", "-a", ident, "-m", message)
    if done.returncode != 0:
        print(f"baton tag: git tag failed: {done.stderr.strip()}", file=sys.stderr)
        return EXIT_FAILED
    head = _git(central, "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"tagged {ident} at {head} ({message}); push it with: git push origin {ident}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="baton", description="baton framework CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, module_name in SUBCOMMANDS.items():
        module = _load(module_name)
        doc = module.__doc__.splitlines()[0] if module and module.__doc__ else "not built yet"
        sub = subparsers.add_parser(name, help=doc, description=doc)
        sub.add_argument("--json", action="store_true", help="machine output on stdout")
        sub.add_argument("--central", default=".", help="central repo path (default: current directory)")
        if module:
            module.add_arguments(sub)
            sub.set_defaults(handler=module.run)
        else:
            sub.set_defaults(handler=None)
    sub = subparsers.add_parser("tag", help=TAG_DOC, description=TAG_DOC)
    sub.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    sub.add_argument("--central", default=".", help="central repo path (default: current directory)")
    sub.add_argument("id", help="story or feature id, e.g. S-010 or F-002")
    sub.set_defaults(handler=tag)
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None and Path(sys.argv[0]).stem in ("harness", "pod"):
        old = Path(sys.argv[0]).stem
        print(f"note: `{old}` is now `baton`; the old name works for one more release", file=sys.stderr)
    args = build_parser().parse_args(argv)
    if args.handler is None:
        print(f"baton {args.command}: not built yet", file=sys.stderr)
        return EXIT_REFUSED
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
