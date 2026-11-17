"""Read a lo-fi wireframe option: regions, fields, actions, states, components; what it may not hold."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

_COLOUR = re.compile(
    r"(?:^|[;{\s])(?:color|background(?:-color)?|border-color|fill|stroke)\s*:\s*(?!inherit|transparent|none)"
    r"|font-family\s*:|#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(",
    re.I,
)
TECHNICAL = ("id", "null", "undefined", "nan", "true", "false", "uuid", "objectid")


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.regions: list[str] = []
        self.fields: list[str] = []
        self.actions: list[str] = []
        self.states: list[str] = []
        self.components: dict[str, str] = {}
        self.changed: list[str] = []
        self.problems: list[str] = []
        self.text: list[str] = []
        self._region: list[str] = []
        self._skip = 0
        self._style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in ("img", "picture", "svg", "video", "canvas"):
            self.problems.append(f"<{tag}>: no images in a lo-fi wireframe")
        if tag == "script":
            self.problems.append("<script>: a wireframe has no behaviour")
            self._skip += 1
        if tag == "style":
            self._style = True
        if (
            tag == "link"
            and "stylesheet" in a.get("rel", "")
            and not a.get("href", "").endswith("wireframe.css")
        ):
            self.problems.append(f"stylesheet {a.get('href')}: only wireframe.css")
        if tag == "font":
            self.problems.append("<font>: no fonts")
        if "style" in a and _COLOUR.search(a["style"]):
            self.problems.append(f"inline style `{a['style'][:40]}`: no colour or font")
        for attr in ("color", "bgcolor", "face"):
            if attr in a:
                self.problems.append(f"{attr}= attribute: no colour or font")
        if a.get("data-region"):
            self.regions.append(a["data-region"])
            if a.get("data-component"):
                self.components[a["data-region"]] = a["data-component"]
            if "data-changed" in a:
                self.changed.append(a["data-region"])
        for key, bucket in (
            ("data-field", self.fields),
            ("data-action", self.actions),
            ("data-state", self.states),
        ):
            if a.get(key):
                bucket.append(a[key])

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._skip:
            self._skip -= 1
        if tag == "style":
            self._style = False

    def handle_data(self, data: str) -> None:
        if self._style:
            if _COLOUR.search(data.replace("font-family: system-ui", "")):
                self.problems.append("<style>: no colour or font; use wireframe.css")
            return
        if not self._skip and data.strip():
            self.text.append(data.strip())


def read(path: Path) -> dict:
    reader = _Reader()
    try:
        reader.feed(path.read_text(encoding="utf-8", errors="replace"))
    except OSError as exc:
        return {"path": str(path), "problems": [f"unreadable: {exc}"]}
    words = re.findall(r"[A-Za-z]+", " ".join(reader.text))
    technical = sorted({w.lower() for w in words if w.lower() in TECHNICAL})
    return {
        "path": str(path),
        "regions": reader.regions,
        "fields": reader.fields,
        "actions": reader.actions,
        "states": reader.states,
        "components": reader.components,
        "changed": reader.changed,
        "technical": technical,
        "words": words,
        "problems": sorted(set(reader.problems)),
    }


def options(folder: Path) -> list[Path]:
    return sorted(folder.glob("option-*.html"), key=lambda p: (len(p.name), p.name))
