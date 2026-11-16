"""What the agents read: per agent, reads, re-reads, scans and rough tokens, from .baton/reads.jsonl.

baton reads                     the latest session in the log
baton reads --session <id>      one session
baton reads --story S-010       the calls of the agents whose prompt names S-010 (or tagged BATON_STORY)
baton reads --all               every session

Tokens are the size of what each tool returned divided by four: an estimate for comparing runs, not
billing. The ratios (re-reads, files read by more than one agent, scans) are exact.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

LOG = ".baton/reads.jsonl"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", help="one session id")
    parser.add_argument("--story", help="only calls of the agents that worked on this story")
    parser.add_argument("--all", action="store_true", help="every session in the log")


def load(central: Path) -> list[dict]:
    path = Path(central) / LOG
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def story_agents(central: Path, story: str) -> set[str]:
    """Agent ids whose transcript prompt names the story (see `baton eval`); empty when none are found."""
    from baton.evaluate import load_agents, project_dir, story_ids

    folder = project_dir(central)
    if not folder.is_dir():
        return set()
    return {a["id"] for a in load_agents(folder, story_ids(central) | {story}) if a["story"] == story}


def select(
    rows: list[dict], session: str | None, story: str | None, everything: bool, agents: set[str] | None = None
) -> list[dict]:
    if story:
        return [r for r in rows if r.get("story") == story or r.get("agent_id") in (agents or set())]
    if session:
        return [r for r in rows if r.get("session") == session]
    if everything or not rows:
        return rows
    latest = max(rows, key=lambda r: r.get("ts", 0)).get("session")
    return [r for r in rows if r.get("session") == latest]


def report(rows: list[dict]) -> dict:
    agents: dict[str, dict] = {}
    readers: dict[str, set[str]] = defaultdict(set)
    file_tokens: Counter = Counter()
    for row in rows:
        agent = row.get("agent") or "main"
        a = agents.setdefault(
            agent, {"calls": 0, "reads": Counter(), "scans": 0, "bash": Counter(), "tokens": 0}
        )
        a["calls"] += 1
        a["tokens"] += int(row.get("tokens") or 0)
        tool = row.get("tool")
        if tool == "Read" and row.get("file"):
            a["reads"][row["file"]] += 1
            readers[row["file"]].add(agent)
            file_tokens[row["file"]] += int(row.get("tokens") or 0)
        elif tool in ("Grep", "Glob"):
            a["scans"] += 1
        elif tool == "Bash":
            a["bash"][row.get("cmd") or "?"] += 1
    out_agents = []
    for name in sorted(agents, key=lambda n: -agents[n]["tokens"]):
        a = agents[name]
        reads = sum(a["reads"].values())
        out_agents.append(
            {
                "agent": name,
                "calls": a["calls"],
                "reads": reads,
                "files": len(a["reads"]),
                "rereads": reads - len(a["reads"]),
                "scans": a["scans"],
                "tokens": a["tokens"],
                "bash": dict(a["bash"].most_common(5)),
            }
        )
    shared = sorted(
        ((f, sorted(r)) for f, r in readers.items() if len(r) > 1), key=lambda x: (-len(x[1]), x[0])
    )
    return {
        "calls": len(rows),
        "tokens": sum(a["tokens"] for a in out_agents),
        "agents": out_agents,
        "sharedFiles": [{"file": f, "agents": r} for f, r in shared],
        "topFiles": [{"file": f, "tokens": t} for f, t in file_tokens.most_common(10)],
    }


def render(data: dict) -> str:
    lines = [
        f"{'agent':<22} {'calls':>6} {'reads':>6} {'files':>6} {'re-read':>8} {'scans':>6} {'~tokens':>9}"
    ]
    for a in data["agents"]:
        lines.append(
            f"{a['agent'][:22]:<22} {a['calls']:>6} {a['reads']:>6} {a['files']:>6} {a['rereads']:>8} "
            f"{a['scans']:>6} {a['tokens']:>9,}"
        )
    lines.append(f"total ~tokens returned by tools: {data['tokens']:,} over {data['calls']} calls")
    if data["sharedFiles"]:
        lines.append(f"files read by more than one agent: {len(data['sharedFiles'])}")
        lines += [
            f"  {len(s['agents'])} {s['file']} ({', '.join(s['agents'])})" for s in data["sharedFiles"][:10]
        ]
    if data["topFiles"]:
        lines.append("largest reads:")
        lines += [f"  {t['tokens']:>8,} {t['file']}" for t in data["topFiles"]]
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    agents = story_agents(central, args.story) if args.story else None
    rows = select(load(central), args.session, args.story, args.all, agents)
    if not rows:
        print(
            f"baton reads: nothing logged in {LOG}; the read_log hook writes it (templates/settings.json)",
            file=sys.stderr,
        )
        return EXIT_FAILED
    data = report(rows)
    print(json.dumps(data, indent=1) if args.json else render(data), end="" if not args.json else "\n")
    return EXIT_OK
