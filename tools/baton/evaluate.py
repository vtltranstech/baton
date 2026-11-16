"""Where a story's time, tokens and findings went, per agent and per review lens. Read-only; no model.

baton eval S-010             one story
baton eval --all             every story found in this machine's transcripts
baton eval --transcripts D   read subagent transcripts from D instead of ~/.claude/projects/<this repo>

Sources, all local: Claude Code's subagent transcripts (`<config>/projects/<repo>/<session>/subagents/
agent-*.jsonl` with `.meta.json`), `.baton/reads.jsonl`, and the story's `-risk.json` and `-triage.md`.
A subagent belongs to the first story id its prompt names. Only counts, times and file names are
printed; no prompt or code text leaves the transcripts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from baton.confidence import read_json
from baton.state_check import find_story

EXIT_OK, EXIT_FAILED, EXIT_REFUSED = 0, 1, 2
LENSES = ("edge-case", "verification-gap", "craft", "conformance", "domain")
_STORY_FILE = re.compile(r"^([A-Za-z]+-\d+)")
_FINDING_ROW = re.compile(r"^\|\s*(F\d+)\s*\|\s*([\w-]+)\s*\|\s*([^|]+?)\s*\|", re.M)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("story", nargs="?", help="story id, e.g. S-010")
    parser.add_argument("--all", action="store_true", help="every story found in the transcripts")
    parser.add_argument("--transcripts", help="a projects/<repo> folder of Claude Code transcripts")
    parser.add_argument(
        "--gap", type=float, default=2.0, help="minutes of no agent activity that count as waiting"
    )


def project_dir(central: Path) -> Path:
    """Claude Code keeps a repo's sessions under projects/<path with every non-alphanumeric as '-'>."""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(central))


def story_ids(central: Path) -> set[str]:
    root = central / "docs" / "stories"
    return {m.group(1) for p in root.glob("*/*.md") if (m := _STORY_FILE.match(p.stem))}


def _time(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
    except ValueError:
        return None


def _prompt_text(record: dict) -> str:
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def read_agent(path: Path, known: set[str]) -> dict | None:
    """One subagent run: type, story, start, end, tokens and tool calls. None if unreadable or empty."""
    meta, _ = read_json(path.parent / (path.stem + ".meta.json"))
    times, tools = [], Counter()
    usage_by_message: dict[str, tuple[int, int]] = {}  # one API message spans several lines: keep its largest
    story = None
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if stamp := _time(record.get("timestamp")):
                times.append(stamp)
            if story is None and record.get("type") == "user":
                text = _prompt_text(record)
                hits = [(text.find(sid), sid) for sid in known if sid in text]
                story = min(hits)[1] if hits else ""
            message = record.get("message") or {}
            if not isinstance(message, dict):
                continue
            usage, key = message.get("usage"), message.get("id") or record.get("requestId") or line
            if usage:
                seen_in, seen_out = usage_by_message.get(key, (0, 0))
                now_in = sum(int(usage.get(k) or 0) for k in
                             ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                now_out = int(usage.get("output_tokens") or 0)
                usage_by_message[key] = (max(seen_in, now_in), max(seen_out, now_out))
            for part in message.get("content") or [] if isinstance(message.get("content"), list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    tools[part.get("name", "?")] += 1
    if not times:
        return None
    tokens_in = sum(i for i, _ in usage_by_message.values())
    tokens_out = sum(o for _, o in usage_by_message.values())
    return {
        "id": path.stem.removeprefix("agent-"),
        "type": (meta or {}).get("agentType") or "unknown",
        "description": (meta or {}).get("description") or "",
        "story": story or "",
        "start": min(times),
        "end": max(times),
        "tokensIn": tokens_in,
        "tokensOut": tokens_out,
        "toolCalls": sum(tools.values()),
    }


def load_agents(folder: Path, known: set[str]) -> list[dict]:
    agents = []
    for path in sorted(folder.glob("*/subagents/agent-*.jsonl")):
        agent = read_agent(path, known)
        if agent:
            agents.append(agent)
    return agents


def load_reads(central: Path) -> dict[str, dict]:
    """Per agent id: reads, re-reads of a file it already read, and ~tokens returned."""
    out: dict[str, dict] = defaultdict(lambda: {"reads": 0, "rereads": 0, "readTokens": 0, "_files": set()})
    log = central / ".baton" / "reads.jsonl"
    if not log.is_file():
        return {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        item = out[row.get("agent_id") or "main"]
        item["reads"] += 1
        item["readTokens"] += int(row.get("tokens") or 0)
        target = row.get("file") or ""
        if row.get("tool") == "Read" and target and not row.get("partial"):
            if target in item["_files"]:
                item["rereads"] += 1
            item["_files"].add(target)
    return {k: {x: y for x, y in v.items() if x != "_files"} for k, v in out.items()}


def lens_yield(central: Path, story_id: str) -> dict[str, dict] | None:
    """Per lens: findings it was part of, findings only it found, and how many of those were high/medium."""
    try:
        triage = find_story(central, story_id).qa("triage.md")
    except FileNotFoundError:
        return None
    if not triage.is_file():
        return None
    result = {lens: {"findings": 0, "unique": 0, "uniqueHighMedium": 0} for lens in LENSES}
    for _, verdict, sources in _FINDING_ROW.findall(triage.read_text(encoding="utf-8", errors="replace")):
        lenses = [s.strip() for s in sources.split("+") if s.strip()]
        for lens in lenses:
            item = result.setdefault(lens, {"findings": 0, "unique": 0, "uniqueHighMedium": 0})
            item["findings"] += 1
            if len(lenses) == 1:
                item["unique"] += 1
                item["uniqueHighMedium"] += verdict.lower() in ("high", "medium")
    return result


def _minutes(seconds: float) -> float:
    return round(seconds / 60, 1)


def summarize(central: Path, story_id: str, agents: list[dict], reads: dict, gap: float) -> dict:
    mine = sorted((a for a in agents if a["story"] == story_id), key=lambda a: a["start"])
    rows = []
    for a in mine:
        r = reads.get(a["id"], {})
        rows.append({
            "agent": a["type"], "description": a["description"], "start": a["start"].isoformat(),
            "minutes": _minutes((a["end"] - a["start"]).total_seconds()),
            "tokensIn": a["tokensIn"], "tokensOut": a["tokensOut"], "toolCalls": a["toolCalls"],
            "reads": r.get("reads", 0), "rereads": r.get("rereads", 0),
        })
    # busy time: overlapping runs (parallel lenses) count once; gaps between them are waiting
    busy, waits, cursor = 0.0, [], None
    for a in mine:
        if cursor is None or a["start"] > cursor:
            if cursor is not None and (a["start"] - cursor).total_seconds() >= gap * 60:
                idle = _minutes((a["start"] - cursor).total_seconds())
                waits.append({"minutes": idle, "before": a["type"]})
            busy += (a["end"] - a["start"]).total_seconds()
            cursor = a["end"]
        elif a["end"] > cursor:
            busy += (a["end"] - cursor).total_seconds()
            cursor = a["end"]
    by_type: dict[str, dict] = {}
    for row in rows:
        item = by_type.setdefault(row["agent"], {"runs": 0, "minutes": 0.0, "tokensIn": 0, "tokensOut": 0})
        item["runs"] += 1
        item["minutes"] = round(item["minutes"] + row["minutes"], 1)
        item["tokensIn"] += row["tokensIn"]
        item["tokensOut"] += row["tokensOut"]
    try:
        risk, _ = read_json(find_story(central, story_id).qa("risk.json"))
    except FileNotFoundError:
        risk = None
    span = (mine[-1]["end"] - mine[0]["start"]).total_seconds() if mine else 0
    return {
        "story": story_id,
        "risk": (risk or {}).get("tier"),
        "agents": rows,
        "byAgent": by_type,
        "spanMinutes": _minutes(span),
        "agentMinutes": _minutes(busy),
        "waitMinutes": round(sum(w["minutes"] for w in waits), 1),
        "waits": waits,
        "designRounds": by_type.get("architect", {}).get("runs", 0),
        "developerRuns": by_type.get("developer", {}).get("runs", 0),
        "lenses": lens_yield(central, story_id),
    }


def render(stories: list[dict]) -> str:
    lines = []
    for s in stories:
        lines.append(f"{s['story']}  risk {s['risk'] or '-'}  span {s['spanMinutes']} min = agents "
                     f"{s['agentMinutes']} + waiting {s['waitMinutes']}  design rounds {s['designRounds']}, "
                     f"developer runs {s['developerRuns']}")
        lines.append(f"  {'agent':<18}{'runs':>5}{'min':>8}{'tok in':>11}{'tok out':>9}")
        for name, a in sorted(s["byAgent"].items(), key=lambda kv: -kv[1]["minutes"]):
            lines.append(
                f"  {name:<18}{a['runs']:>5}{a['minutes']:>8}{a['tokensIn']:>11,}{a['tokensOut']:>9,}"
            )
        for w in s["waits"]:
            lines.append(f"  waited {w['minutes']} min before {w['before']}")
        heavy = [a for a in s["agents"] if a["rereads"]]
        for a in sorted(heavy, key=lambda a: -a["rereads"])[:3]:
            lines.append(f"  {a['agent']} re-read {a['rereads']} files ({a['reads']} reads)")
        lines.append("")
    totals: dict[str, Counter] = defaultdict(Counter)
    for s in stories:
        for lens, item in (s["lenses"] or {}).items():
            totals[lens]["stories"] += 1
            totals[lens].update(item)
    if any(totals[x]["findings"] for x in totals):
        counted = len([s for s in stories if s["lenses"]])
        lines.append(f"review lenses over {counted} stories with a triage table")
        lines.append(f"  {'lens':<18}{'findings':>9}{'unique':>8}{'unique high/med':>17}")
        for lens in LENSES + tuple(x for x in totals if x not in LENSES):
            t = totals.get(lens)
            if t:
                lines.append(f"  {lens:<18}{t['findings']:>9}{t['unique']:>8}{t['uniqueHighMedium']:>17}")
        lines.append("  a lens whose unique high/med stays 0 over 10+ stories costs time without new catches")
    return "\n".join(lines).rstrip() + "\n"


def run(args: argparse.Namespace) -> int:
    central = Path(args.central).resolve()
    if not args.story and not args.all:
        print("baton eval: name a story or pass --all", file=sys.stderr)
        return EXIT_REFUSED
    folder = Path(args.transcripts) if args.transcripts else project_dir(central)
    if not folder.is_dir():
        print(f"baton eval: no transcripts at {folder}; run the stories from this folder in Claude Code, "
              "or pass --transcripts", file=sys.stderr)
        return EXIT_FAILED
    known = story_ids(central)
    agents = load_agents(folder, known)
    reads = load_reads(central)
    wanted = sorted({a["story"] for a in agents if a["story"]}) if args.all else [args.story]
    stories = [summarize(central, sid, agents, reads, args.gap) for sid in wanted]
    stories = [s for s in stories if s["agents"]]
    if not stories:
        print(f"baton eval: no subagent transcript in {folder} names {args.story or 'a known story'}",
              file=sys.stderr)
        return EXIT_FAILED
    print(json.dumps(stories, indent=1) if args.json else render(stories), end="" if not args.json else "\n")
    return EXIT_OK
