"""Screens of record (ui-stories.md section 6): promote, compare, and the options page for gate 2a."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from baton import state_check
from baton.ux import spec as specs
from baton.ux import wireframe

STYLE = """body{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#222}
h1{font-size:18px}h2{font-size:15px;margin:0 0 6px}p,li,td{font-size:13px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.col{border:1px solid #999;padding:8px;min-width:0}iframe{width:100%;height:520px;border:1px solid #bbb}
.region{border:1px solid #888;margin:6px 0;padding:6px}.region.changed{border:3px dashed #000}
.region.gone{opacity:.45;text-decoration:line-through}.tag{font-size:11px;border:1px solid #888;padding:0 4px}
pre{white-space:pre-wrap;font-size:12px;background:#f4f4f4;padding:8px}"""


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def approved(story: state_check.Story) -> Path | None:
    """The approved wireframe: approved.html (full track), else the light delta option-1.html."""
    folder = story.design("wireframe")
    for name in ("approved.html", "option-1.html"):
        if (folder / name).is_file() and (
            name == "approved.html" or state_check.track_of(story.text()) == "light"
        ):
            return folder / name
    return None


def region_changes(old: dict | None, new: dict) -> list[str]:
    if not old:
        return ["new screen"]
    before = {r["region"]: r for r in old.get("regions", [])}
    after = {r["region"]: r for r in new.get("regions", [])}
    out = [f"+region {r}" for r in after if r not in before] + [
        f"-region {r}" for r in before if r not in after
    ]
    for name in after.keys() & before.keys():
        added = sorted(set(after[name]["items"]) - set(before[name]["items"]))
        gone = sorted(set(before[name]["items"]) - set(after[name]["items"]))
        out += [f"{name}: +{i}" for i in added] + [f"{name}: -{i}" for i in gone]
        if (after[name].get("component") or {}).get("name") != (before[name].get("component") or {}).get(
            "name"
        ):
            out.append(f"{name}: component {(after[name].get('component') or {}).get('name')}")
    return sorted(out) or ["no region or field changed"]


def promote(central: Path, story: state_check.Story, today: str | None = None) -> tuple[int, str]:
    folder = story.design("wireframe")
    spec_path, wire = folder / "screen-spec.md", approved(story)
    if not spec_path.is_file() or wire is None:
        return 2, f"no approved wireframe and spec under {story.rel(folder)}"
    text = spec_path.read_text(encoding="utf-8")
    spec = specs.parse(text)
    screen = spec.get("screen")
    if not screen:
        return 2, f"{story.rel(spec_path)} has no `# Screen: <id>` title"
    today = today or _today()
    target = central / "docs" / "architecture" / "screens" / screen
    old = specs.load(target / "screen-spec.md")
    changes = region_changes(old, spec)
    since = (old or {}).get("baton_since") or today
    stamped = re.sub(r"^baton\.(story|feature|since):.*\n", "", text, flags=re.M)
    head, _, rest = stamped.partition("\n")
    stamped = (
        f"{head}\nbaton.story: {story.story_id}\nbaton.feature: {story.feature}\nbaton.since: {since}\n{rest}"
    )
    stamped = re.sub(
        r"^screen-of-record:.*$", f"screen-of-record: docs/architecture/screens/{screen}", stamped, flags=re.M
    )
    target.mkdir(parents=True, exist_ok=True)
    (target / "screen-spec.md").write_text(stamped, encoding="utf-8")
    shutil.copyfile(wire, target / "approved.html")
    if (folder / "wireframe.css").is_file():
        shutil.copyfile(folder / "wireframe.css", target / "wireframe.css")
    history = target / "history.md"
    lines = (
        history.read_text(encoding="utf-8").splitlines()
        if history.is_file()
        else [f"# History: {screen}", ""]
    )
    if not any(f" {story.story_id} " in line for line in lines):
        lines.append(f"- {today} {story.story_id} ({story.feature}): {'; '.join(changes)}")
    history.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_index(central)
    return 0, f"promoted {screen}: {'; '.join(changes)}"


def write_index(central: Path) -> Path:
    root = central / "docs" / "architecture" / "screens"
    rows = []
    for path in sorted(root.glob("*/screen-spec.md")):
        spec = specs.load(path) or {}
        rows.append(
            f"| [{spec.get('screen') or path.parent.name}]({path.parent.name}/screen-spec.md) | "
            f"{spec.get('route') or '-'} | {spec.get('persona') or '-'} | {spec.get('area') or '-'} | "
            f"{spec.get('baton_story') or '-'} |"
        )
    index = root / "index.md"
    index.write_text(
        "# Screens of record\n\nWritten by `baton ux promote`; one row per screen.\n\n"
        "| Screen | Route | Persona | Area | Last story |\n| --- | --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    return index


def _at(central: Path, ref: str, rel: str) -> str | None:
    path = Path(ref)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    done = subprocess.run(["git", "-C", str(central), "show", f"{ref}:{rel}"], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else None


def _short(central: Path, ref: str) -> str:
    path = Path(ref)
    if not path.is_file():
        return ref
    try:
        return path.resolve().relative_to(central.resolve()).as_posix()
    except ValueError:
        return path.name


def _column(title: str, spec: dict, other: dict) -> str:
    theirs = {r["region"]: r for r in other.get("regions", [])}
    out = [f"<div class='col'><h2>{html.escape(title)}</h2>"]
    for region in spec.get("regions", []):
        peer = theirs.get(region["region"])
        changed = (
            peer is None
            or set(peer["items"]) != set(region["items"])
            or ((peer.get("component") or {}).get("name") != (region.get("component") or {}).get("name"))
        )
        comp = (region.get("component") or {}).get("name") or "-"
        out.append(
            f"<div class='region{' changed' if changed else ''}' "
            f"data-region='{html.escape(region['region'])}'>"
            f"<b>{html.escape(region['region'])}</b> <span class='tag'>{html.escape(comp)}</span>"
            f"<p>{html.escape(', '.join(region['items']))}</p></div>"
        )
    for name in theirs.keys() - {r["region"] for r in spec.get("regions", [])}:
        out.append(f"<div class='region gone'><b>{html.escape(name)}</b> (not here)</div>")
    return "\n".join(out) + "</div>"


def diff(central: Path, screen: str, ref_a: str, ref_b: str) -> tuple[int, str]:
    rel = f"docs/architecture/screens/{screen}/screen-spec.md"
    texts = [_at(central, ref, rel) for ref in (ref_a, ref_b)]
    missing = [ref for ref, t in zip((ref_a, ref_b), texts, strict=True) if t is None]
    if missing:
        return 2, f"{rel} is not at {', '.join(missing)}"
    a, b = (specs.parse(t or "") for t in texts)
    ref_a, ref_b = (_short(central, ref) for ref in (ref_a, ref_b))
    changes = region_changes(a, b)
    page = (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(screen)}: {html.escape(ref_a)} vs "
        f"{html.escape(ref_b)}</title><style>{STYLE}</style></head><body><h1>{html.escape(screen)}</h1>"
        f"<p>Changed regions are outlined. {html.escape('; '.join(changes))}</p><div class='cols'>"
        f"{_column(ref_a, a, b)}{_column(ref_b, b, a)}</div></body></html>\n"
    )
    return 0, page


def show(story: state_check.Story) -> tuple[int, Path | str]:
    """`<S>-wireframe/index.html`: every option side by side with its rationale, the check and the UX lens."""
    folder = story.design("wireframe")
    options = wireframe.options(folder)
    if not options:
        return 2, f"{story.rel(folder)} has no option-<n>.html"
    notes = folder / "options.md"
    lens = story.design("reviews") / "ux.md"
    check = folder / "check.json"
    parts = [
        f"<!doctype html><html><head><meta charset='utf-8'><title>{story.story_id} wireframes</title>"
        f"<style>{STYLE}</style></head><body><h1>{story.story_id}: choose a wireframe</h1>",
        "<p>Answer in Claude Code: Option 1, 2 or 3, Changes (say what), or Block.</p><div class='cols'>",
    ]
    for path in options:
        parts.append(
            f"<div class='col'><h2>{html.escape(path.stem.replace('-', ' ').title())}</h2>"
            f"<iframe src='{html.escape(path.name)}' title='{html.escape(path.stem)}'></iframe></div>"
        )
    parts.append("</div>")
    for title, path in (("Why each option", notes), ("UX lens", lens), ("Check", check)):
        if path.is_file():
            parts.append(f"<h2>{title}</h2><pre>{html.escape(path.read_text(encoding='utf-8'))}</pre>")
    parts.append("</body></html>\n")
    page = folder / "index.html"
    page.write_text("\n".join(parts), encoding="utf-8")
    return 0, page
