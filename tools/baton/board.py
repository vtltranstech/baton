"""Where every story is: State, gate 0, its branches in every repo (pushed, merged), its tag, what is next.

baton board                  one line per story, grouped by feature
baton board --story S        that story, one line per repo branch
baton board --feature F      only that feature
baton board --fetch          `git fetch` every repo first (else origin/ is as of the last fetch)
baton board --json           the same as JSON

Read-only: it reads git and the story files, and writes nothing. A story's central branch is
`story/<F>-<S>` and its code branch in each service repo `feature/<F>-<S>` (contracts/versioning.md
section 1). A branch is merged when the default branch holds its tip and a `<S>:` commit (nothing is
squashed), shipped when the tag `<S>` exists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from baton import state_check, stories
from baton.state_check import _git

EXIT_OK, EXIT_REFUSED = 0, 2


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--feature", help="only this feature id")
    parser.add_argument("--story", help="only this story, with one line per repo branch")
    parser.add_argument("--fetch", action="store_true", help="git fetch every repo first")


def _out(repo: Path, *args: str) -> str | None:
    done = _git(repo, *args)
    return done.stdout.strip() if done is not None and done.returncode == 0 else None


def _has(repo: Path, ref: str) -> bool:
    return _out(repo, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}") is not None


def default_base(repo: Path) -> str | None:
    """The ref merges land on: origin's default branch, else the local main or master."""
    head = _out(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if head and _has(repo, head):
        return head
    for name in ("origin/main", "origin/master", "main", "master"):
        if _has(repo, name):
            return name
    return None


def _counts(repo: Path, left: str, right: str) -> tuple[int, int]:
    """(commits only in `left`, commits only in `right`), from one `rev-list --left-right` call."""
    value = (_out(repo, "rev-list", "--left-right", "--count", f"{left}...{right}") or "").split()
    return (int(value[0]), int(value[1])) if len(value) == 2 and all(v.isdigit() for v in value) else (0, 0)


class Repo:
    """One repo's refs and its merged story ids, each read with a single git call (not one per story)."""

    def __init__(self, path: Path, base: str | None = None):
        self.path, self.base = path, base
        fields = "%(refname)%09%(objectname:short)%09%(committerdate:iso-strict)%09%(subject)"
        listing = _out(path, "for-each-ref", f"--format={fields}")
        self.refs: dict[str, dict] = {}
        for line in (listing or "").splitlines():
            ref, sha, when, subject = (line.split("\t", 3) + ["", "", ""])[:4]
            self.refs[ref] = {"commit": sha, "at": when, "subject": subject}
        self._landed: set[str] | None = None

    def has(self, ref: str) -> bool:
        return ref in self.refs

    def landed(self, story_id: str) -> bool:
        """The base holds a commit whose message has a line starting `<story-id>:`."""
        if self._landed is None:
            log = None
            if self.base:
                log = _out(self.path, "log", "--format=%B", "-E", "--grep=^[A-Za-z]+-[0-9]+:", self.base)
            self._landed = set(_LANDED.findall(log or ""))
        return story_id in self._landed


_LANDED = re.compile(r"^([A-Za-z]+-\d+):", re.M)


def branch_state(repo: Path | Repo, branch: str, base: str | None, story_id: str) -> dict:
    """One branch in one repo: here and on origin or not, what is unpushed, and whether it merged."""
    refs = repo if isinstance(repo, Repo) else Repo(repo, base)
    repo = refs.path
    local, remote = refs.has(f"refs/heads/{branch}"), refs.has(f"refs/remotes/origin/{branch}")
    row: dict = {"branch": branch, "local": local, "remote": remote}
    if not local and not remote:
        row["status"] = "none"
        return row
    tip = branch if local else f"origin/{branch}"
    row["behind"], row["ahead"] = _counts(repo, base, tip) if base else (None, None)
    both = local and remote
    row["unpushed"], row["unpulled"] = _counts(repo, branch, f"origin/{branch}") if both else (None, 0)
    last = refs.refs.get(f"refs/heads/{branch}" if local else f"refs/remotes/origin/{branch}")
    if last and last["commit"]:
        row["last"] = dict(last)
    landed = bool(base) and refs.landed(story_id)
    if row["ahead"] == 0 and landed:
        row["status"] = "merged"
    elif row["ahead"] == 0:
        row["status"] = "empty"
    elif not remote:
        row["status"] = "not pushed"
    elif row["unpushed"]:
        row["status"] = f"{row['unpushed']} unpushed"
    else:
        row["status"] = "pushed"
    return row


def _repos(central: Path) -> list:
    from baton.extract.repos import read_repo_table

    try:
        return [r for r in read_repo_table(central) if r.path != central and (r.path / ".git").exists()]
    except Exception:  # no project.md or no repo table yet: the board shows the central repo only
        return []


def _gate(story: state_check.Story, text: str) -> str:
    if state_check.gate_off(story.central):
        return "off"
    if not (story.central / "profile" / "branch-points.yaml").is_file():
        return "-"
    refused = state_check._context_gate(story, state_check.track_of(text))
    if refused is None:
        return "ok"
    if state_check.gate_override(text):
        return "override"
    if "does not exist" in refused:
        return "not checked"
    if "blocking" in refused:
        return "blocked"
    return "stale" if " is now " in refused else "refused"


def _next(row: dict) -> str:
    """The next move the facts show; the skills and the states contract own the rest."""
    s, central, code = row["story"], row["central"], row["code"]
    if row["tagged"]:
        return "shipped"
    if central["status"] == "merged":
        return f"baton tag {s} on the default branch"
    for repo in [{"name": "central", **central}] + code:
        if repo["status"] == "not pushed" or repo.get("unpushed"):
            return f"push {repo['branch']} ({repo['name']})"
        if repo.get("unpulled"):
            return f"pull {repo['branch']} ({repo['name']})"
    if row["gate"] in ("blocked", "stale", "refused"):
        return f"/build-context-map focus {row['feature']}"
    if row["gate"] == "not checked" and row["state"] in ("Draft", "Needs Clarification", "Ready for PO"):
        return f"baton context check {s}"
    if central["status"] == "none":
        return ""
    if row["state"] == "In Review" and code and all(c["status"] == "merged" for c in code):
        return "merge the docs PR"
    if row["state"] == "In Review":
        return "Tech Lead: review and merge the PRs"
    return ""


def collect(central: Path, feature: str | None = None, story_id: str | None = None,
            fetch: bool = False) -> dict:
    central = Path(central)
    repos = _repos(central)
    if fetch:
        for repo in [central] + [r.path for r in repos]:
            _git(repo, "fetch", "--quiet", "--prune", "origin")
    base = default_base(central)
    here = Repo(central, base)
    code = [(r.name, Repo(r.path, default_base(r.path))) for r in repos]
    on_branch = state_check.branch_stories(central)
    found = {s.story_id: s for s in _stories(central, on_branch)}
    rows = []
    for item in stories.collect(central, feature, on_branch):
        if story_id and item["story"] != story_id:
            continue
        story = found.get(item["story"])
        text = story.text() if story else ""
        branch = f"{item['feature']}-{item['story']}"
        row = {**item, "gate": _gate(story, text) if story else "-",
               "tagged": here.has(f"refs/tags/{item['story']}"),
               "central": branch_state(here, f"story/{branch}", base, item["story"])}
        row["code"] = [
            {"name": name, **branch_state(refs, f"feature/{branch}", refs.base, item["story"])}
            for name, refs in code
        ]
        row["code"] = [c for c in row["code"] if c["status"] != "none"]
        row["next"] = _next(row)
        rows.append(row)
    return {"base": base, "repos": [r.name for r in repos], "stories": rows}


def _stories(central: Path, on_branch: list[state_check.Story] | None = None) -> list[state_check.Story]:
    found = []
    for path in sorted((central / "docs" / "stories").glob("*/*.md")):
        if state_check._ID.match(path.stem):
            found.append(state_check.story_from_path(path, central))
    seen = {s.story_id for s in found}
    if on_branch is None:
        on_branch = state_check.branch_stories(central)
    return found + [s for s in on_branch if s.story_id not in seen]


def _ago(when: str | None) -> str:
    try:
        then = datetime.fromisoformat(when)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    minutes = int((datetime.now(UTC) - then).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 0)}m ago"
    return f"{minutes // 60}h ago" if minutes < 48 * 60 else f"{minutes // 1440}d ago"


def _code(code: list[dict]) -> str:
    if not code:
        return "-"
    merged = sum(c["status"] == "merged" for c in code)
    loose = sum(c["status"] == "not pushed" or bool(c.get("unpushed")) for c in code)
    text = f"{len(code)} repo(s)"
    if merged:
        text += f", {merged} merged"
    if loose:
        text += f", {loose} not pushed"
    return text


def _central(c: dict) -> str:
    if c["status"] == "none":
        return "no branch"
    ahead = f" +{c['ahead']}" if c.get("ahead") else ""
    return f"{c['status']}{ahead}"


def render(board: dict) -> list[str]:
    lines = [f"{'STORY':<8} {'STATE':<24} {'GATE 0':<12} {'CENTRAL':<16} {'CODE':<28} {'LAST':<8} NEXT"]
    feature = None
    for row in board["stories"]:
        if row["feature"] != feature:
            feature = row["feature"]
            lines.append(f"{feature}")
        last = max((b.get("last", {}).get("at", "") for b in [row["central"], *row["code"]]), default="")
        state = "shipped" if row["tagged"] else str(row["state"])
        lines.append(f"{row['story']:<8} {state:<24} {row['gate']:<12} {_central(row['central']):<16} "
                     f"{_code(row['code']):<28} {_ago(last):<8} {row['next']}")
    return lines


def render_story(row: dict) -> list[str]:
    lines = [f"{row['story']} {row['title'] or ''}".rstrip(),
             f"  feature {row['feature']}, State {row['state']}, gate 0 {row['gate']}"
             f"{', tagged' if row['tagged'] else ''}"]
    for name, b in [("central", row["central"]), *[(c["name"], c) for c in row["code"]]]:
        if b["status"] == "none":
            lines.append(f"  {name:<20} {b['branch']}: no branch")
            continue
        last = b.get("last") or {}
        where = "origin only" if b["remote"] else "local only"
        if b["local"] and b["remote"]:
            where = "local+origin"
        lines.append(f"  {name:<20} {b['branch']}: {b['status']}, {where}, +{b.get('ahead') or 0} "
                     f"-{b.get('behind') or 0}; {last.get('commit', '')} {_ago(last.get('at'))} "
                     f"{last.get('subject', '')}".rstrip())
    if row["next"]:
        lines.append(f"  next: {row['next']}")
    return lines


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    board = collect(central, args.feature, args.story, args.fetch)
    if args.story and not board["stories"]:
        print(f"baton board: no story {args.story}", file=sys.stderr)
        return EXIT_REFUSED
    if args.json:
        print(json.dumps(board, indent=1))
        return EXIT_OK
    if not board["stories"]:
        print("no stories", file=sys.stderr)
        return EXIT_OK
    lines = render_story(board["stories"][0]) if args.story else render(board)
    if board["base"] is None:
        lines.append("note: no main, master or origin/HEAD here, so nothing shows as merged")
    print("\n".join(lines))
    return EXIT_OK
