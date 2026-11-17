"""`baton ux verify S`: the built screen against its approved spec, from the source."""

from __future__ import annotations

import json
import re
from pathlib import Path

from baton import state_check
from baton.ux import check as checks
from baton.ux import inventory as inv
from baton.ux import spec as specs

_ATTR = r"""{name}\s*=\s*(?:["']([^"']+)["']|\{{\s*["'`]([^"'`]+)["'`]\s*\}})"""
_REL_IMPORT = re.compile(r"""(?:import|from)\s*(?:[^'"]*?\sfrom\s*)?['"](\.[^'"]+)['"]""")


def attrs(text: str, name: str) -> set[str]:
    return {a or b for a, b in re.findall(_ATTR.format(name=re.escape(name)), text)}


def _resolve(base: Path, spec: str) -> Path | None:
    target = (base.parent / spec).resolve()
    for candidate in [target, *[target.with_name(target.name + s) for s in inv.SOURCE_SUFFIXES]] + [
        target / f"index{s}" for s in inv.SOURCE_SUFFIXES
    ]:
        if candidate.is_file():
            return candidate
    return None


def screen_files(central: Path, spec: dict, inventory: dict) -> tuple[list[tuple[str, Path]], str | None]:
    """[(repo, file)] for the screen and the local files it imports (3 levels), or why none was found."""
    repos = {r.name: r.path for r in inv.ui_repos(central)}
    start: list[tuple[str, Path]] = []
    for item in [f.strip() for f in (spec.get("files") or "").split(",") if f.strip()]:
        repo, _, rel = item.rpartition(":")
        for name, root in repos.items():
            if repo in ("", name) and (root / rel).is_file():
                start.append((name, root / rel))
    route = spec.get("route")
    if not start and route:
        wanted = checks.norm_path(route)
        for name, data in (inventory.get("repos") or {}).items():
            for r in (data or {}).get("routes") or []:
                if checks.norm_path(r.get("path", "")) == wanted and name in repos:
                    comp = ((data.get("components") or {}).get(r.get("component")) or {}).get("file")
                    if comp and (repos[name] / comp).is_file():
                        start.append((name, repos[name] / comp))
    if not start:
        return (
            [],
            f"no source for the screen: no `files:` in the spec and route {route} "
            "has no component in a UI repo",
        )
    seen: dict[Path, str] = {}
    frontier = start
    for _ in range(4):
        following = []
        for repo, path in frontier:
            if path in seen:
                continue
            seen[path] = repo
            text = path.read_text(encoding="utf-8", errors="replace")
            for rel in _REL_IMPORT.findall(text):
                target = _resolve(path, rel)
                if target and target not in seen:
                    following.append((repo, target))
        frontier = following
    return [(repo, path) for path, repo in seen.items()], None


def verify(central: Path, story: state_check.Story) -> tuple[int, dict]:
    folder = story.design("wireframe")
    spec_path = folder / "screen-spec.md"
    if not spec_path.is_file():
        return 2, {
            "story": story.story_id,
            "ok": False,
            "mismatches": [],
            "problem": f"{story.rel(spec_path)} does not exist",
        }
    spec = specs.parse(spec_path.read_text(encoding="utf-8"))
    inventory = inv.collect(central)
    files, why = screen_files(central, spec, inventory)
    out = story.qa("ui-verify.json")
    if why:
        result = {
            "story": story.story_id,
            "screen": spec.get("screen"),
            "files": [],
            "ok": False,
            "mismatches": [{"severity": "HIGH", "kind": "no-source", "what": why}],
        }
        _write(out, result)
        return 1, result
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for _, p in files)
    rendered = {
        "field": attrs(text, "data-field"),
        "action": attrs(text, "data-action"),
        "state": attrs(text, "data-state"),
    }
    mismatches = []

    def add(severity: str, kind: str, what: str) -> None:
        mismatches.append({"severity": severity, "kind": kind, "what": what})

    for field in spec["fields"]:
        if field["field"] not in rendered["field"]:
            add("HIGH", "missing-field", f"field {field['field']} has no data-field in the screen")
        elif field["label"] and not _shows(field["label"], text):
            add(
                "MEDIUM",
                "label-drift",
                f"field {field['field']}: label `{field['label']}` is not in the screen",
            )
    for action in spec["actions"]:
        if action["action"] not in rendered["action"]:
            add("HIGH", "missing-action", f"action {action['action']} has no data-action in the screen")
        elif action["label"] and not _shows(action["label"], text):
            add(
                "MEDIUM",
                "label-drift",
                f"action {action['action']}: label `{action['label']}` is not in the screen",
            )
    for state in specs.STATES:
        if state not in rendered["state"]:
            add("HIGH", "missing-state", f"state {state} has no data-state in the screen")
    known = {f["field"] for f in spec["fields"]}
    for extra in sorted(rendered["field"] - known):
        add("MEDIUM", "extra-field", f"data-field {extra} is not in the approved spec")
    library = inventory.get("library") or {}
    imports = {
        m for _, p in files for m in re.findall(r"""from\s*['"]([^'"]+)['"]""", p.read_text(errors="replace"))
    }
    for module in sorted(imports):
        if inv.forbidden(module, library.get("forbid") or []):
            use = library.get("name") or "the library"
            add(
                "HIGH",
                "forbidden-import",
                f"imports {module} directly; build it from {use} ({', '.join(library.get('import') or [])})",
            )
    lib = set((library.get("components") or {}).keys())
    for region in spec["regions"]:
        comp = region.get("component") or {}
        for name in [comp.get("name")] if comp and not comp.get("new") else comp.get("uses") or []:
            if name in lib and not re.search(rf"\b{re.escape(name)}\b", text):
                add("MEDIUM", "component", f"region {region['region']}: {name} is not used by the screen")
    roots = {r.name: r.path for r in inv.ui_repos(central)}
    result = {
        "story": story.story_id,
        "screen": spec.get("screen"),
        "files": [f"{repo}:{_rel(p, roots.get(repo))}" for repo, p in files],
        "ok": not any(m["severity"] == "HIGH" for m in mismatches),
        "mismatches": mismatches,
    }
    _write(out, result)
    return (0 if result["ok"] else 1), result


def _shows(label: str, text: str) -> bool:
    """The label as a whole phrase: `Total` is not shown by `Totals`."""
    return re.search(rf"(?<![\w]){re.escape(label)}(?![\w])", text) is not None


def _rel(path: Path, root: Path | None) -> str:
    try:
        return path.relative_to(root).as_posix() if root else path.as_posix()
    except ValueError:
        return path.as_posix()


def _write(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
