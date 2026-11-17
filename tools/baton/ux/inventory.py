"""The component inventory (contracts/ui-stories.md section 4): the organisation's library and every UI repo.

Regular expressions over the source, typings or Markdown pages; no Node, no network. Written to
`profile/ui-inventory.yaml` by `baton extract --ui` or `baton ux inventory`.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from baton.confidence import project_value

SOURCE_SUFFIXES = (".tsx", ".ts", ".jsx", ".js", ".mjs")
DOC_SUFFIXES = (".md", ".mdx")
_NEVER = {"node_modules", "dist", "build", "coverage", "__tests__", "__mocks__", ".git", "target"}
_NOT_SOURCE = re.compile(r"\.(test|spec|stories)\.[cm]?[jt]sx?$")
_EXPORT_FN = re.compile(
    r"export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?function\s+([A-Z]\w*)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
)
_EXPORT_CONST = re.compile(r"export\s+(?:declare\s+)?const\s+([A-Z]\w*)\s*(?::\s*([^=;]+?))?\s*(?:=|;)")
_EXPORT_CLASS = re.compile(r"export\s+(?:default\s+)?(?:declare\s+)?class\s+([A-Z]\w*)")
_EXPORT_LIST = re.compile(r"export\s*(?:type\s*)?\{([^}]*)\}")
_PROPS_DECL = re.compile(r"(?:interface|type)\s+(\w+)\s*(?:<[^>]*>)?\s*(?:extends[^{]*)?=?\s*\{")
_MEMBER = re.compile(r"^\s*(?:readonly\s+)?['\"]?([A-Za-z_]\w*)['\"]?\??\s*:", re.M)
_IMPORT = re.compile(r"import\s+(?:type\s+)?(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from\s*['\"]([^'\"]+)['\"]")
_ROUTE_JSX = re.compile(
    r"<Route\b[^>]*?\bpath=\{?['\"]([^'\"]+)['\"]\}?[^>]*?(?:element=\{\s*<\s*(\w+)|component=\{\s*(\w+))"
)
_ROUTE_OBJ = re.compile(
    r"\bpath\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*(?:element\s*:\s*<\s*(\w+)|component\s*:\s*(\w+))"
)
_NOT_UI = re.compile(
    r"^(react|react-dom|react-router(?:-dom)?|vite|vitest|typescript|@types/.*|eslint.*|@testing-library/.*)$"
)


def walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    if root.is_file():
        return [root] if root.name.endswith(suffixes) else []
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _NEVER and not d.startswith("."))
        found += [
            Path(current) / f for f in sorted(files) if f.endswith(suffixes) and not _NOT_SOURCE.search(f)
        ]
    return found


def _block(text: str, start: int) -> str:
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def props_types(text: str) -> dict[str, list[str]]:
    """`interface XProps { a: T; b?: U }` -> {XProps: [a, b]}: only the members at the first level."""
    found = {}
    for match in _PROPS_DECL.finditer(text):
        body = _block(text, match.end() - 1)
        flat = re.sub(r"\{[^{}]*\}", "", re.sub(r"\{[^{}]*\}", "", body))
        found[match.group(1)] = sorted(set(_MEMBER.findall(flat)))
    return found


def components(path: Path, root: Path) -> dict[str, dict]:
    """Exported components (capitalised names) of one source or typings file, with their props."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    types = props_types(text)
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    found: dict[str, dict] = {}

    def add(name: str, props_type: str | None) -> None:
        props = types.get(props_type or "", types.get(f"{name}Props", []))
        found.setdefault(name, {"file": rel, "props": props})

    for match in _EXPORT_FN.finditer(text):
        typed = re.search(r":\s*(\w+)", match.group(2))
        add(match.group(1), typed.group(1) if typed else None)
    for match in _EXPORT_CONST.finditer(text):
        typed = re.search(r"<\s*(\w+Props)\s*>", match.group(2) or "") or re.search(
            r"\(\s*(?:\{[^}]*\}|\w+)\s*:\s*(\w+)", text[match.end() : match.end() + 200]
        )
        add(match.group(1), typed.group(1) if typed else None)
    for match in _EXPORT_CLASS.finditer(text):
        add(match.group(1), None)
    for match in _EXPORT_LIST.finditer(text):
        for part in match.group(1).split(","):
            name = part.split(" as ")[-1].strip()
            if re.match(r"^[A-Z]\w*$", name) and not name.endswith("Props"):
                add(name, None)
    return found


def doc_components(path: Path, root: Path) -> dict[str, dict]:
    """One Markdown page per component: `# Name`, props from a table whose header has `prop`."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    title = re.search(r"^#\s+`?([A-Z]\w*)`?\s*$", text, re.M)
    if not title:
        return {}
    props, in_table = [], False
    for line in text.splitlines():
        if line.strip().startswith("|"):
            cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
            if not in_table:
                in_table = "prop" in cells[0].lower()
                continue
            if cells and not set(cells[0]) <= set("-: ") and re.match(r"^\w+\??$", cells[0]):
                props.append(cells[0].rstrip("?"))
        else:
            in_table = False
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    return {title.group(1): {"file": rel, "props": sorted(set(props))}}


def library(central: Path) -> dict:
    name = (project_value(central, "ui.library") or "").strip()
    paths = [p.strip().strip("`") for p in (project_value(central, "ui.library.path") or "").split(",")]
    result = {
        "name": name if name.lower() not in ("", "none") else None,
        "paths": [p for p in paths if p],
        "import": [
            p.strip().strip("`")
            for p in (project_value(central, "ui.library.import") or "").split(",")
            if p.strip()
        ],
        "forbid": [
            p.strip().strip("`")
            for p in (project_value(central, "ui.library.forbid") or "").split(",")
            if p.strip() and p.strip() != "none"
        ],
        "components": {},
        "missing": [],
    }
    for rel in result["paths"]:
        root = (central / rel).resolve()
        if not root.exists():
            result["missing"].append(rel)
            continue
        for path in walk(root, SOURCE_SUFFIXES + (".d.ts",)):
            for comp, info in components(path, root).items():
                result["components"].setdefault(comp, info)
        for path in walk(root, DOC_SUFFIXES):
            for comp, info in doc_components(path, root).items():
                result["components"].setdefault(comp, info)
    return result


def repo_inventory(repo: Path) -> dict:
    package = repo / "package.json"
    try:
        meta = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    deps = sorted({**(meta.get("dependencies") or {}), **(meta.get("peerDependencies") or {})}.keys())
    files = [p for d in ("src", "app", "pages", "lib") for p in walk(repo / d, SOURCE_SUFFIXES)]
    comps: dict[str, dict] = {}
    imported: dict[str, set[str]] = {}
    routes = []
    for path in files:
        if path.suffix in (".tsx", ".jsx"):
            for comp, info in components(path, repo).items():
                comps.setdefault(comp, info)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _IMPORT.finditer(text):
            module = match.group(3)
            if module.startswith(".") or _NOT_UI.match(module):
                continue
            names = [match.group(1)] if match.group(1) else []
            names += [n.split(" as ")[0].strip() for n in (match.group(2) or "").split(",")]
            imported.setdefault(module, set()).update(n for n in names if re.match(r"^[A-Z]\w*$", n or ""))
        for regex in (_ROUTE_JSX, _ROUTE_OBJ):
            for match in regex.finditer(text):
                routes.append(
                    {
                        "path": match.group(1),
                        "component": match.group(2) or match.group(3),
                        "file": path.relative_to(repo).as_posix(),
                    }
                )
    return {
        "packages": [d for d in deps if not _NOT_UI.match(d)],
        "imports": {m: sorted(n) for m, n in sorted(imported.items()) if n},
        "routes": sorted(routes, key=lambda r: r["path"]),
        "components": dict(sorted(comps.items())),
    }


def ui_repos(central: Path) -> list:
    from baton.extract.repos import read_repo_table

    try:
        return [r for r in read_repo_table(central) if (r.path / "package.json").is_file()]
    except Exception:  # no project.md or no repo table: the library alone
        return []


def collect(central: Path) -> dict:
    return {
        "library": library(central),
        "repos": {r.name: repo_inventory(r.path) for r in ui_repos(central)},
    }


def write(central: Path, inventory: dict) -> Path:
    from baton.extract.yamlio import dumps

    path = central / "profile" / "ui-inventory.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = json.loads(json.dumps(inventory))
    document["library"].pop("missing", None)
    path.write_text(
        dumps(
            document, header="Written by baton extract --ui (contracts/ui-stories.md section 4). Do not edit."
        ),
        encoding="utf-8",
    )
    return path


def load(central: Path) -> dict:
    """The inventory file when present, else collected now (nothing written)."""
    path = central / "profile" / "ui-inventory.yaml"
    if path.is_file():
        from baton import miniyaml

        try:
            data = miniyaml.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # an unreadable file: collect from the source instead
            pass
    return collect(central)


def known_components(inventory: dict) -> tuple[set[str], set[str]]:
    """(library components, app components)."""
    lib = set(((inventory.get("library") or {}).get("components") or {}).keys())
    forbid = (inventory.get("library") or {}).get("forbid") or []
    app: set[str] = set()
    for repo in (inventory.get("repos") or {}).values():
        app |= set(((repo or {}).get("components") or {}).keys())
        for module, names in ((repo or {}).get("imports") or {}).items():
            if not forbidden(module, forbid):
                app |= set(names or [])
    return lib, app - lib


def forbidden(module: str, forbid: list[str]) -> bool:
    """`@mui/*` forbids `@mui/material`; a plain name forbids itself and its subpaths."""
    for pattern in forbid:
        stem = pattern.rstrip("*").rstrip("/")
        if (
            module == stem
            or module.startswith(stem + "/")
            or (pattern.endswith("*") and module.startswith(stem))
        ):
            return True
    return False


def known_routes(inventory: dict) -> set[str]:
    return {
        r.get("path", "")
        for repo in (inventory.get("repos") or {}).values()
        for r in ((repo or {}).get("routes") or [])
    }
