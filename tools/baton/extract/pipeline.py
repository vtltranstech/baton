"""The work behind the three commands: detect, merge with what a human already reviewed, write atomically."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from baton import miniyaml
from baton.extract import VERSION, extractors, seeds, ts_backend, yamlio
from baton.extract.config import Config, load_config
from baton.extract.model import JavaFile
from baton.extract.parser import ast_usable
from baton.extract.repos import (
    UNKNOWN,
    Sources,
    git_commit,
    git_dirty,
    load_sources,
    read_repo_table,
    select_repos,
)
from baton.extract.resolve import TypeIndex
from baton.extract.stack import detect_stack

STACK_FILE = "profile/stack-detected.md"
DEPENDENCIES_FILE = "profile/dependencies.yaml"
AGGREGATES_FILE = "profile/aggregates.yaml"
RISK_ZONES_FILE = "profile/risk-zones.yaml"
GENERATED_FILES = (STACK_FILE, DEPENDENCIES_FILE, AGGREGATES_FILE, RISK_ZONES_FILE)
_REVIEW_HEADER = (
    "Seeded by baton extract. {who} reviews: set confirmed: true to keep an entry as it is.\n"
    "Entries still at confirmed: false are regenerated on every run; confirmed ones never are."
)
_COLUMNS = (
    ("repo", "repo"),
    ("build", "build"),
    ("build cmd", "buildCmd"),
    ("test cmd", "testCmd"),
    ("java", "java"),
    ("spring-boot", "springBoot"),
    ("batch", "batch"),
    ("datastore", "datastore"),
    ("messaging", "messaging"),
    ("web", "web"),
    ("ui", "ui"),
    ("package root", "packageRoot"),
    ("layout", "layout"),
    ("archunit", "archunit"),
    ("pitest", "pitest"),
    ("build-file sha256", "buildFileSha256"),
)


class RefusedOverwrite(Exception):
    """Exit 1: a file a human may have edited cannot be read, so it is not replaced."""


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(text)
    os.replace(temp, path)


# -- stack-detected.md --------------------------------------------------------------------------------------


def _cell(row: dict, key: str) -> str:
    value = row.get(key, UNKNOWN)
    if key == "batch":
        # `none`, not `false`: readers of this table treat any value other than unknown or none as present.
        return "true" if value is True else "none" if value is False else UNKNOWN
    if key == "layout":
        if not value or value == UNKNOWN:
            return UNKNOWN
        return ";".join(
            f"{layer}={value.get(layer, UNKNOWN)}" for layer in ("adapters", "application", "domain")
        )
    return str(value)


def render_stack(rows: list[dict], generated: str) -> str:
    lines = [
        "| " + " | ".join(title for title, _ in _COLUMNS) + " |",
        "| " + " | ".join("---" for _ in _COLUMNS) + " |",
    ]
    lines += ["| " + " | ".join(_cell(row, key) for _, key in _COLUMNS) + " |" for row in rows]
    return "\n".join(lines) + f"\n\ngenerated: {generated} by baton extract-stack {VERSION}\n"


def parse_stack(text: str) -> list[dict]:
    """Rows back from stack-detected.md, in `--json` form. Used to keep other repos on a --repo run."""
    rows = []
    for line in text.splitlines()[2:]:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        row = {key: cell for (_, key), cell in zip(_COLUMNS, cells, strict=False)}
        batch = row.pop("batch", UNKNOWN)
        if batch != UNKNOWN:
            row["batch"] = batch == "true"
        layout = row.pop("layout", UNKNOWN)
        if layout != UNKNOWN:
            row["layout"] = dict(part.split("=", 1) for part in layout.split(";"))
        rows.append(row)
    return rows


def _write_stack(central: Path, rows: list[dict], only: str | None, generated: str) -> list[dict]:
    path = central / STACK_FILE
    by_name = {}
    if only and path.is_file():
        by_name = {r["repo"]: r for r in parse_stack(path.read_text(encoding="utf-8"))}
    by_name.update({r["repo"]: r for r in rows})
    ordered = [by_name[r.name] for r in read_repo_table(central) if r.name in by_name]
    _write(path, render_stack(ordered, generated))
    return ordered


def stack_rows(all_sources: list[Sources]) -> list[dict]:
    return [detect_stack(sources) for sources in all_sources]


def public_rows(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if k not in ("problems", "testcontainers")} for row in rows]


def run_stack(central: Path, only: str | None) -> dict:
    all_sources = [load_sources(repo) for repo in select_repos(central, only)]
    rows = stack_rows(all_sources)
    generated = now()
    written = _write_stack(central, public_rows(rows), only, generated)
    return {"generated": generated, "repos": written, "_rows": rows}


# -- extract ------------------------------------------------------------------------------------------------


@dataclass
class RepoResult:
    """A repo's dependencies.yaml entry and what goes only into questions."""

    entry: dict
    sources: Sources
    configs: dict[str, Config]
    documents: list = field(default_factory=list)
    risk: dict = field(default_factory=dict)
    commit_reason: str = ""
    dirty: bool = False
    notes: list[str] = field(default_factory=list)


def _config_lookup(sources: Sources, configs: dict[str, Config]):
    modules = sorted(sources.modules, key=len, reverse=True)

    def config_of(parsed: JavaFile) -> Config:
        for module in modules:
            if parsed.path.startswith(module + "/"):
                return configs[module]
        return configs["."]

    return config_of


def _resources(sources: Sources) -> list[str]:
    out = []
    root = sources.repo.path
    for module in sources.module_roots:
        base = root / module / "src" / "main" / "resources"
        if base.is_dir():
            out += [
                p.resolve().relative_to(root.resolve()).as_posix()
                for p in sorted(base.rglob("*"))
                if p.is_file()
            ]
    return out


def extract_repo(sources: Sources) -> RepoResult:
    root = sources.repo.path
    configs = {m: load_config(root, m) for m in sources.module_roots}
    index = TypeIndex()
    for parsed in sources.main:
        index.add(parsed)
    found = extractors.extract(sources.main, index, _config_lookup(sources, configs))
    frontend = ts_backend.extract(root)
    sources.failures += frontend["failures"]
    commit, reason = git_commit(root)
    entry = {
        "repo": sources.repo.name,
        "commit": commit,
        "edges": found.edges + frontend["edges"],
        "unresolved": found.unresolved + frontend["unresolved"],
        "collections": found.collections,
        "parser": sources.parser_record(ast_usable()),
    }
    if frontend["parser"]:
        entry["parser"]["typescript"] = frontend["parser"]
    documents = extractors.document_classes(sources.main, index, _config_lookup(sources, configs))
    return RepoResult(
        entry,
        sources,
        configs,
        documents,
        seeds.risk_files(sources.main, found.edges, _resources(sources)),
        reason,
        commit != UNKNOWN and git_dirty(root),
        found.notes,
    )


def _read_reviewed(path: Path, top: str) -> list[dict]:
    if not path.is_file():
        return []
    try:
        document = miniyaml.load_file(str(path))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RefusedOverwrite(f"{path}: cannot be read ({exc}); fix it, nothing was written") from exc
    entries = document.get(top) if isinstance(document, dict) else None
    if entries is None and document is not None and not (isinstance(document, dict) and top in document):
        raise RefusedOverwrite(f"{path}: no `{top}` list; fix it, nothing was written")
    return entries or []


def _read_previous(central: Path) -> dict:
    path = central / DEPENDENCIES_FILE
    if not path.is_file():
        return {}
    try:
        document = miniyaml.load_file(str(path))
    except (ValueError, UnicodeDecodeError):
        return {}
    repos = document.get("repos") if isinstance(document, dict) else None
    return {r["repo"]: r for r in repos or [] if isinstance(r, dict) and "repo" in r}


def _write_if_changed(path: Path, top: str, existing: list[dict], merged: list[dict], who: str) -> None:
    """Rewriting drops a human's comments, so an unchanged list leaves the file's bytes alone."""
    if path.is_file() and merged == existing:
        return
    _write(path, yamlio.dumps({top: merged}, _REVIEW_HEADER.format(who=who)))


def run_extract(central: Path, only: str | None) -> dict:
    repos = select_repos(central, only)
    aggregates_path, zones_path = central / AGGREGATES_FILE, central / RISK_ZONES_FILE
    existing_aggregates = _read_reviewed(aggregates_path, "aggregates")
    existing_zones = _read_reviewed(zones_path, "zones")

    results = [extract_repo(load_sources(repo)) for repo in repos]
    previous = _read_previous(central)
    generated = now()

    entries = {name: entry for name, entry in previous.items()} if only else {}
    entries.update({r.entry["repo"]: r.entry for r in results})
    ordered = [entries[name] for name in _table_order(central, entries)]
    document = {"generated": generated, "repos": ordered}

    index = TypeIndex()
    for result in results:
        for parsed in result.sources.main:
            index.add(parsed)
    documents = [item for result in results for item in result.documents]
    aggregate_seeds = seeds.seed_aggregates(documents, index)
    refreshed = {s["root"] for s in aggregate_seeds}
    if only:
        old = previous.get(only, {}).get("edges") or []
        refreshed |= {
            e["from"] for e in old if e.get("provenance", {}).get("extractor") == "document-annotation"
        }
    else:
        refreshed |= {e.get("root") for e in existing_aggregates}
    aggregates = seeds.merge_reviewed(existing_aggregates, aggregate_seeds, "root", refreshed)

    risk: dict[str, set[str]] = {}
    for result in results:
        for name, paths in result.risk.items():
            risk.setdefault(name, set()).update(paths)
    if only:  # other repos' paths are not known on a partial run: a full run clears stale ones
        for zone in existing_zones:
            if zone.get("confirmed") is False and zone.get("name") in seeds.ZONE_REASONS:
                risk.setdefault(zone["name"], set()).update(zone.get("paths") or [])
    zone_seeds = seeds.zone_entries({k: sorted(v) for k, v in risk.items()})
    replaced = {z.get("name") for z in existing_zones} | {z["name"] for z in zone_seeds}
    zones = seeds.merge_reviewed(existing_zones, zone_seeds, "name", replaced)

    text = yamlio.dumps(document)  # refuses before anything is written if it cannot round-trip
    _write(central / DEPENDENCIES_FILE, text)
    _write_if_changed(aggregates_path, "aggregates", existing_aggregates, aggregates, "The Tech Lead")
    _write_if_changed(zones_path, "zones", existing_zones, zones, "The Tech Lead")
    rows = stack_rows([r.sources for r in results])
    _write_stack(central, public_rows(rows), only, generated)
    return {
        "document": document,
        "results": results,
        "aggregates": aggregates,
        "zones": zones,
        "zone_seeds": zone_seeds,
        "rows": rows,
    }


def _table_order(central: Path, entries: dict) -> list[str]:
    return [r.name for r in read_repo_table(central) if r.name in entries]
