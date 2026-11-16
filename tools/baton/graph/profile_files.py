"""Reads the few values the graph needs from profile/project.md, domain.md and stack-detected.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_VALUES = {"", "unknown", "none", "-", "—", "n/a", "pending"}


@dataclass
class RepoInfo:
    name: str
    purpose: str = ""
    team: str | None = None
    team_line: int = 0


@dataclass
class Profile:
    name: str = "Product"
    one_liner: str = ""
    repos: dict[str, RepoInfo] = field(default_factory=dict)
    personas: list[str] = field(default_factory=list)
    externals: list[tuple[str, str]] = field(default_factory=list)
    stack: dict[str, dict[str, str]] = field(default_factory=dict)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_row(line: str) -> bool:
    return line.lstrip().startswith("|") and not re.match(r"^\s*\|[\s:|-]+\|?\s*$", line)


def _section(lines: list[str], title: str) -> list[tuple[int, str]]:
    """(1-based line number, text) of the `## <title>...` section, or empty."""
    out: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(lines, 1):
        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            if inside:
                break
            inside = line.startswith("##") and heading.startswith(title.lower())
            continue
        if inside:
            out.append((number, line))
    return out


def _parse_project(text: str, profile: Profile) -> None:
    lines = text.splitlines()
    for line in lines:
        if _is_row(line):
            cells = _cells(line)
            if len(cells) >= 2 and cells[0] == "project.name":
                profile.name = cells[1]
            elif len(cells) >= 2 and cells[0] == "project.one-liner":
                profile.one_liner = cells[1]
    header: list[str] = []
    for number, line in _section(lines, "Repos"):
        if not _is_row(line):
            continue
        cells = _cells(line)
        if not header:
            header = [cell.lower() for cell in cells]
            continue
        row = dict(zip(header, cells, strict=False))
        name = Path(row.get("path", cells[0]).strip("`")).name
        team = row.get("team", "").strip("`")
        info = RepoInfo(name, row.get("what it is", row.get("purpose", "")))
        if team.lower() not in _SKIP_VALUES:
            info.team, info.team_line = team, number
        profile.repos[name] = info
    for _, line in _section(lines, "Personas"):
        if line.strip():
            profile.personas = [part.strip() for part in line.split(",") if part.strip()]
            break


def _parse_externals(text: str, profile: Profile) -> None:
    rows: list[tuple[str, str]] = []
    header_seen = False
    for _, line in _section(text.splitlines(), "External systems"):
        if _is_row(line):
            if not header_seen:
                header_seen = True
                continue
            cells = _cells(line)
            rows.append((cells[0], cells[1] if len(cells) > 1 else ""))
        elif line.lstrip().startswith(("- ", "* ")):
            parts = re.split(r"\s*(?::|—|–| - )\s+", line.strip()[2:], maxsplit=1)
            rows.append((parts[0].strip("*` "), parts[1].strip() if len(parts) > 1 else ""))
    profile.externals = sorted(set(rows))


def _parse_stack(text: str, profile: Profile) -> None:
    header: list[str] = []
    for line in text.splitlines():
        if not _is_row(line):
            continue
        cells = _cells(line)
        if not header:
            header = [cell.lower() for cell in cells]
            continue
        row = dict(zip(header, cells, strict=False))
        if row.get("repo"):
            profile.stack[row["repo"]] = row


def known(value: str | None) -> bool:
    return bool(value) and value.strip().lower() not in _SKIP_VALUES


def read_profile(central: str | Path) -> Profile:
    base = Path(central) / "profile"
    profile = Profile()
    for name, parser in (
        ("project.md", _parse_project),
        ("domain.md", _parse_externals),
        ("stack-detected.md", _parse_stack),
    ):
        path = base / name
        if path.is_file():
            parser(path.read_text(encoding="utf-8"), profile)
    return profile
