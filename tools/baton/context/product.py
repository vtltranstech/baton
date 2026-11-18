"""What `baton context` reads: settings, repos, modules, edges and the stored branch points, from files only.

Every input is optional. A generated file that is missing is itself a gap (the map says which command fills
it);it never stops the map from being drawn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from baton import miniyaml
from baton.context import branch_points as bp
from baton.extract import yamlio
from baton.extract.repos import UNKNOWN, MissingInput, declared_modules, git_commit, read_repo_table
from baton.wiki.facts import Layout, package_of, read_dependencies, read_layout

SETTINGS_FILE = "profile/context.yaml"
POINTS_FILE = "profile/branch-points.yaml"
DRAFTS_FILE = "profile/domain-drafts.md"
MAP_JSON = "docs/context/context-map.json"
MAP_MD = "docs/context/context-map.md"
BLOCKING_DEFAULTS = {
    "light": ["undefined-word", "unresolved-edge-out"],
    "full": [
        "undefined-word",
        "unresolved-edge-out",
        "undocumented-branch-in-changed-module",
        "unprofiled-write",
    ],
}
_TS = (".ts", ".tsx")
_TS_TEST = re.compile(r"\.(?:test|spec)\.tsx?$")
_NEVER = {"node_modules", "dist", "build", "target", "out", "coverage"}


@dataclass
class Settings:
    patterns: tuple[str, ...] = bp.DEFAULT_PATTERNS
    doc_sources: list[str] = field(default_factory=list)
    max_age_days: int = 30
    blocking: dict[str, list[str]] = field(default_factory=lambda: dict(BLOCKING_DEFAULTS))
    interview_cap_minutes: int = 60
    light_open_questions: int = 2
    question_ttl_days: int = 3
    ocr_languages: tuple[str, ...] = ("eng",)
    ocr_tessdata: str | None = None
    ocr_min_chars: int = 20
    ocr_embedded_images: bool = True


def load_settings(central: Path) -> Settings:
    settings = Settings()
    path = central / SETTINGS_FILE
    if not path.is_file():
        return settings
    data = miniyaml.loads(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise MissingInput(f"{path}: the top level is not a mapping")
    if data.get("domain-field-patterns"):
        settings.patterns = tuple(str(p).lower() for p in data["domain-field-patterns"])
    settings.doc_sources = [str(p) for p in data.get("doc-sources") or []]
    settings.max_age_days = int(data.get("profile-max-age-days", settings.max_age_days))
    for track, kinds in (data.get("blocking") or {}).items():
        settings.blocking[str(track)] = [str(k) for k in kinds or []]
    settings.interview_cap_minutes = int(data.get("interview-cap-minutes", settings.interview_cap_minutes))
    settings.light_open_questions = int(data.get("light-open-questions", settings.light_open_questions))
    settings.question_ttl_days = int(data.get("question-ttl-days", settings.question_ttl_days))
    if data.get("ocr-languages"):
        settings.ocr_languages = tuple(str(lang) for lang in data["ocr-languages"])
    if data.get("ocr-tessdata"):
        tessdata = Path(str(data["ocr-tessdata"])).expanduser()
        settings.ocr_tessdata = str(tessdata if tessdata.is_absolute() else central / tessdata)
    settings.ocr_min_chars = int(data.get("ocr-min-chars", settings.ocr_min_chars))
    if "ocr-embedded-images" in data:
        settings.ocr_embedded_images = data["ocr-embedded-images"] is True
    return settings


@dataclass
class Module:
    repo: str
    name: str
    sources: list[Path] = field(default_factory=list)
    tests: list[Path] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.repo}/{self.name}"


@dataclass
class Repo:
    name: str
    path: Path
    commit: str = UNKNOWN
    owner: str = ""
    stack: dict = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    modules: dict[str, Module] = field(default_factory=dict)
    extracted: bool = False  # dependencies.yaml has an entry for it


def _stack_rows(central: Path) -> dict[str, dict]:
    path = central / "profile" / "stack-detected.md"
    rows: dict[str, dict] = {}
    if not path.is_file():
        return rows
    columns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not columns:
            columns = cells
        elif not all(set(c) <= set("-: ") for c in cells):
            row = dict(zip(columns, cells, strict=False))
            rows[row.get("repo", "")] = row
    return rows


def _owners(central: Path) -> dict[str, str]:
    """The `Owner` column of project.md's repo table, by repo name."""
    path = central / "profile" / "project.md"
    owners: dict[str, str] = {}
    if not path.is_file():
        return owners
    columns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            columns = []
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if not columns:
            low = [c.lower() for c in cells]
            columns = low if ("path" in low or "repo" in low) else ["-"]
            continue
        if columns == ["-"] or all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(columns, cells, strict=False))
        if row.get("owner") and not row["owner"].startswith(("<", "(")):
            name = row.get("repo") or Path(row.get("path", "")).name
            owners[name] = row["owner"]
    return owners


def _codeowners(repo: Path) -> bool:
    return any((repo / p).is_file() for p in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"))


def _ts_module(rel: str) -> str:
    parts = rel.split("/")
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    return "/".join(parts[:-1]) or "_root"


def module_of(rel: str, layout: Layout) -> str | None:
    if rel.endswith(_TS):
        return _ts_module(rel)
    for kind in ("main", "test"):
        package = package_of(rel, kind)
        if package is not None:
            return layout.module_of(package)
    return None


def _walk_java(root: Path, kind: str, modules: list[str]) -> list[Path]:
    found: list[Path] = []
    for module in [".", *modules]:
        base = root / module / "src" / kind / "java"
        if base.is_dir():
            found += [
                p
                for p in sorted(base.rglob("*.java"))
                if p.name not in ("package-info.java", "module-info.java")
            ]
    return found


def _walk_ts(root: Path) -> list[Path]:
    base = root / "src"
    if not base.is_dir():
        return []
    return [
        p
        for p in sorted(base.rglob("*"))
        if p.suffix in _TS
        and p.is_file()
        and not _NEVER.intersection(p.relative_to(root).parts)
        and not p.name.endswith(".d.ts")
    ]


def load_repos(central: Path, progress=None) -> list[Repo]:
    from baton.progress import silent

    progress = progress or silent()
    stack, owners = _stack_rows(central), _owners(central)
    repos = []
    for ref in read_repo_table(central):
        progress.note(f"{ref.name}: listing files under {ref.path}")
        repo = Repo(ref.name, ref.path, stack=stack.get(ref.name, {}))
        repo.owner = owners.get(ref.name) or ("CODEOWNERS" if _codeowners(ref.path) else "")
        try:
            entry = read_dependencies(central, ref.name)
            repo.extracted = True
            repo.commit = str(entry.get("commit", UNKNOWN))
            repo.edges = list(entry.get("edges") or [])
            repo.unresolved = [str(u) for u in entry.get("unresolved") or []]
        except MissingInput:
            repo.commit = git_commit(ref.path)[0] if ref.path.is_dir() else UNKNOWN
        try:
            layout = read_layout(central, ref.name)
        except MissingInput:
            layout = Layout(UNKNOWN, {})
        if ref.path.is_dir():
            build = declared_modules(ref.path)
            for kind in ("main", "test"):
                for path in _walk_java(ref.path, kind, build):
                    _add(repo, path, layout, kind == "test")
            for path in _walk_ts(ref.path):
                _add(repo, path, layout, bool(_TS_TEST.search(path.name)))
        files = sum(len(m.sources) + len(m.tests) for m in repo.modules.values())
        progress.note(f"{ref.name}: {files} files in {len(repo.modules)} modules")
        for edge in repo.edges:
            rel = str((edge.get("provenance") or {}).get("file", ""))
            name = module_of(rel, layout)
            if name is not None:
                repo.modules.setdefault(name, Module(repo.name, name)).edges.append(edge)
        repos.append(repo)
    return repos


def _add(repo: Repo, path: Path, layout: Layout, test: bool) -> None:
    name = module_of(path.relative_to(repo.path).as_posix(), layout)
    if name is None:
        return
    if test and name not in repo.modules:
        return
    module = repo.modules.setdefault(name, Module(repo.name, name))
    (module.tests if test else module.sources).append(path)


def vocabulary(repos: list[Repo], words: list[str], settings: Settings) -> bp.Vocabulary:
    fields: set[str] = set()
    for repo in repos:
        for module in repo.modules.values():
            for path in module.sources:
                if path.suffix == ".java":
                    fields |= bp.document_fields(path.read_text(encoding="utf-8", errors="replace"))
    return bp.Vocabulary({bp.normalize(w) for w in words}, fields, settings.patterns)


# --- the stored branch points ----------------------------------------------------------------------------


def stored_predicate(text: str) -> str:
    """The predicate as profile/branch-points.yaml can hold it (the YAML subset has no escapes)."""
    try:
        yamlio._scalar(text)
        return text
    except ValueError:
        rare, common = sorted(("'", '"'), key=text.count)
        return text.replace(rare, common)


def load_points(central: Path) -> list[dict] | None:
    path = central / POINTS_FILE
    if not path.is_file():
        return None
    data = miniyaml.loads(path.read_text(encoding="utf-8")) or {}
    return list(data.get("branchPoints") or []) if isinstance(data, dict) else []


def point_key(entry: dict) -> tuple[str, str, str]:
    return str(entry.get("repo")), str(entry.get("file")), " ".join(str(entry.get("predicate", "")).split())


def write_points(central: Path, points: list[dict], generated: str) -> None:
    header = (
        "Generated by baton context build (contracts/context-map.md section 2). Only `rule:` and "
        "`status: contested` are\nhuman edits, and the next build keeps them; everything else is rewritten."
    )
    text = yamlio.dumps({"generated": generated, "branchPoints": points}, header=header)
    path = central / POINTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
