"""A small SVG kit: palette, text measuring, shapes, arrows. Stdlib only; the output needs no viewer plugin.

Every diagram is a standalone .svg with its own white background, so it reads the same in the VS Code
Markdown preview, a browser, GitHub and a printed review pack.
"""

from __future__ import annotations

import math
from html import escape

FONT = "'Inter','Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

INK = "#0f172a"
MUTED = "#475569"
FAINT = "#94a3b8"
RULE = "#cbd5e1"
PAPER = "#ffffff"
LANE_FILLS = ("#f8fafc", "#f1f5f9")

# status -> (stroke, fill, chip text). Colours chosen to stay apart for the common colour-vision deficiencies;
# every status also has a word on the chip, so colour is never the only signal.
STATUS = {
    "new": ("#2563eb", "#eff6ff", "NEW"),
    "changed": ("#ea580c", "#fff7ed", "CHANGED"),
    "removed": ("#6b7280", "#f3f4f6", "REMOVED"),
    "impacted": ("#dc2626", "#fef2f2", "IMPACTED"),
    "touched": ("#475569", "#ffffff", ""),
    "context": ("#94a3b8", "#ffffff", ""),
}
LEGEND = {
    "new": "new in this story",
    "changed": "changed by this story",
    "removed": "removed by this story",
    "impacted": "other repo affected (blast radius)",
    "touched": "on the path, unchanged",
}
ACCENT = {  # left stripe of a component box in the architecture views, by role
    "entry": "#7c3aed",
    "app": "#0891b2",
    "adapter": "#059669",
    "data": "#b45309",
    "messaging": "#db2777",
    "external": "#64748b",
}

_NARROW = set("ilj.,:;|!'`()[]{}/\\ ")
_WIDE = set("mwMW@%")


def text_width(text: str, size: float = 13, bold: bool = False, mono: bool = False) -> float:
    """An estimate close enough to lay out boxes: within a few percent of Inter / Segoe UI."""
    if mono:
        return len(text) * size * 0.61
    width = 0.0
    for ch in text:
        if ch in _NARROW:
            width += 0.30
        elif ch in _WIDE:
            width += 0.86
        elif ch.isupper() or ch.isdigit():
            width += 0.64
        else:
            width += 0.54
    return width * size * (1.06 if bold else 1.0)


def wrap(text: str, max_width: float, size: float = 13, bold: bool = False, max_lines: int = 3) -> list[str]:
    """Greedy wrap at spaces, slashes and dots; a single over-long word is cut with an ellipsis."""
    if text_width(text, size, bold) <= max_width:
        return [text]
    tokens: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if ch in " /.,(":
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    lines: list[str] = []
    line = ""
    for token in tokens:
        if line and text_width(line + token, size, bold) > max_width:
            lines.append(line.rstrip())
            line = token
        else:
            line += token
    if line:
        lines.append(line.rstrip())
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [" ".join(lines[max_lines - 1 :])]
    out = []
    for item in lines:
        while text_width(item, size, bold) > max_width and len(item) > 4:
            item = item.removesuffix("...")[:-1] + "..."
        out.append(item)
    return out


def esc(text: str) -> str:
    return escape(str(text), quote=True)


def color(status: str) -> str:
    return STATUS.get(status, STATUS["context"])[0]


def fill(status: str) -> str:
    return STATUS.get(status, STATUS["context"])[1]


class Canvas:
    """Collects SVG elements; `render` wraps them with the shared defs and a white page."""

    def __init__(self) -> None:
        self.items: list[str] = []
        self.width = 0.0
        self.height = 0.0

    def add(self, item: str) -> None:
        self.items.append(item)

    def grow(self, x: float, y: float) -> None:
        self.width = max(self.width, x)
        self.height = max(self.height, y)

    def text(
        self,
        x: float,
        y: float,
        text: str,
        size: float = 13,
        weight: int = 400,
        fill_color: str = INK,
        anchor: str = "start",
        mono: bool = False,
        italic: bool = False,
        extra: str = "",
    ) -> None:
        family = MONO if mono else FONT
        style = ' font-style="italic"' if italic else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill_color}" text-anchor="{anchor}"{style}{extra}>{esc(text)}</text>'
        )

    def render(self, title: str, margin: float = 24) -> str:
        width = math.ceil(self.width + margin)
        height = math.ceil(self.height + margin)
        defs = _defs()
        body = "\n".join(self.items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}" '
            'data-generator="baton-diagram">\n'
            f"<title>{esc(title)}</title>\n{defs}\n"
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="{PAPER}"/>\n{body}\n</svg>\n'
        )


def _marker(name: str, stroke: str, shape: str) -> str:
    if shape == "open":
        path = f'<path d="M1,1 L9,5 L1,9" fill="none" stroke="{stroke}" stroke-width="1.5"/>'
    elif shape == "triangle":
        path = f'<path d="M1,1 L11,6 L1,11 Z" fill="#ffffff" stroke="{stroke}" stroke-width="1.3"/>'
        return (
            f'<marker id="{name}" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" '
            f'orient="auto-start-reverse" markerUnits="userSpaceOnUse">{path}</marker>'
        )
    else:
        path = f'<path d="M0,0 L10,5 L0,10 L2.5,5 Z" fill="{stroke}"/>'
    return (
        f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
        f'orient="auto-start-reverse" markerUnits="userSpaceOnUse">{path}</marker>'
    )


def _defs() -> str:
    markers = []
    for status, (stroke, _, _) in STATUS.items():
        markers.append(_marker(f"a-{status}", stroke, "solid"))
        markers.append(_marker(f"o-{status}", stroke, "open"))
        markers.append(_marker(f"t-{status}", stroke, "triangle"))
    return (
        "<defs>\n"
        '<filter id="lift" x="-10%" y="-10%" width="120%" height="140%">'
        '<feDropShadow dx="0" dy="1.2" stdDeviation="1.4" flood-color="#0f172a" '
        'flood-opacity="0.14"/></filter>\n' + "\n".join(markers) + "\n</defs>"
    )


# -- shapes ------------------------------------------------------------------------------------------------


def chip(canvas: Canvas, x_right: float, y: float, status: str) -> None:
    """The NEW / CHANGED / IMPACTED badge, right-aligned at x_right with its top at y."""
    stroke, _, word = STATUS.get(status, STATUS["context"])
    if not word:
        return
    width = text_width(word, 9, bold=True) + 12
    canvas.add(
        f'<rect x="{x_right - width:.1f}" y="{y:.1f}" width="{width:.1f}" height="15" '
        f'rx="7.5" fill="{stroke}"/>'
    )
    canvas.text(x_right - width / 2, y + 11, word, 9, 700, "#ffffff", "middle")


def box(
    canvas: Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    lines: list[str],
    sub: str,
    status: str,
    kind: str = "component",
    accent: str | None = None,
) -> None:
    """A node drawn by kind, label lines centred, `sub` in small muted text beneath, status chip on top."""
    stroke = color(status)
    paint = fill(status)
    width = 2 if status in ("new", "changed", "impacted", "removed") else 1.3
    dash = ' stroke-dasharray="5 4"' if kind == "external" or status == "removed" else ""
    common = f'fill="{paint}" stroke="{stroke}" stroke-width="{width}"{dash}'
    if kind == "store":
        ry = 7
        canvas.add(
            f'<path d="M{x},{y + ry} A{w / 2},{ry} 0 0 1 {x + w},{y + ry} L{x + w},{y + h - ry} '
            f'A{w / 2},{ry} 0 0 1 {x},{y + h - ry} Z" {common} filter="url(#lift)"/>'
        )
        canvas.add(
            f'<path d="M{x},{y + ry} A{w / 2},{ry} 0 0 0 {x + w},{y + ry}" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}"/>'
        )
        top = y + 2 * ry
        height = h - 2 * ry
    elif kind == "queue":
        rx = 9
        canvas.add(
            f'<path d="M{x + rx},{y} L{x + w - rx},{y} A{rx},{h / 2} 0 0 1 {x + w - rx},{y + h} '
            f'L{x + rx},{y + h} A{rx},{h / 2} 0 0 1 {x + rx},{y} Z" {common} filter="url(#lift)"/>'
        )
        canvas.add(
            f'<path d="M{x + w - rx},{y} A{rx},{h / 2} 0 0 0 {x + w - rx},{y + h}" fill="none" '
            f'stroke="{stroke}" stroke-width="{width}"/>'
        )
        top, height = y, h
    elif kind == "file":
        fold = 12
        canvas.add(
            f'<path d="M{x},{y} L{x + w - fold},{y} L{x + w},{y + fold} L{x + w},{y + h} L{x},{y + h} Z" '
            f'{common} filter="url(#lift)"/>'
        )
        canvas.add(
            f'<path d="M{x + w - fold},{y} L{x + w - fold},{y + fold} L{x + w},{y + fold}" fill="none" '
            f'stroke="{stroke}" stroke-width="1"/>'
        )
        top, height = y, h
    elif kind == "person":
        cx = x + w / 2
        canvas.add(f'<circle cx="{cx}" cy="{y + 11}" r="9" {common}/>')
        canvas.add(
            f'<path d="M{x + 6},{y + h} L{x + 6},{y + 34} Q{x + 6},{y + 23} {cx},{y + 23} '
            f'Q{x + w - 6},{y + 23} {x + w - 6},{y + 34} L{x + w - 6},{y + h} Z" '
            f'{common} filter="url(#lift)"/>'
        )
        top, height = y + 26, h - 26
    else:
        radius = 14 if kind in ("screen", "job") else 9
        canvas.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" {common} filter="url(#lift)"/>'
        )
        if accent:
            canvas.add(
                f'<path d="M{x + radius},{y} L{x + 4 + radius},{y} L{x + 4 + radius},{y + h} '
                f"L{x + radius},{y + h} "
                f"A{radius},{radius} 0 0 1 {x},{y + h - radius} L{x},{y + radius} A{radius},{radius} 0 0 1 "
                f'{x + radius},{y} Z" fill="{accent}" opacity="0.9"/>'
            )
        top, height = y, h
    line_h = 16
    block = len(lines) * line_h + (15 if sub else 0)
    cursor = top + (height - block) / 2 + 12
    for line in lines:
        canvas.text(x + w / 2, cursor, line, 13, 600, INK, "middle")
        cursor += line_h
    if sub:
        canvas.text(x + w / 2, cursor + 2, sub, 11.5, 400, MUTED, "middle")
    chip(canvas, x + w - 6, y - 8, status)


def pill(
    canvas: Canvas, cx: float, cy: float, lines: list[str], status: str
) -> tuple[float, float, float, float]:
    """An edge label: white rounded box so the line never runs through the text. Returns its rectangle."""
    size = 12
    width = max(text_width(line, size) for line in lines) + 12
    height = len(lines) * 14 + 6
    x, y = cx - width / 2, cy - height / 2
    stroke = color(status) if status in ("new", "changed", "impacted", "removed") else RULE
    canvas.add(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="6" fill="#ffffff" '
        f'stroke="{stroke}" stroke-width="1"/>'
    )
    tone = color(status) if status in ("new", "changed", "impacted", "removed") else MUTED
    for i, line in enumerate(lines):
        canvas.text(cx, y + 14 + i * 14, line, size, 500, tone, "middle")
    return x, y, width, height


def line_style(status: str, style: str) -> tuple[str, str, float]:
    """(stroke, dasharray attribute, width) for a link."""
    stroke = color(status) if status != "context" else "#64748b"
    width = 2.0 if status in ("new", "changed", "impacted", "removed") else 1.4
    dash = ""
    if style == "async":
        dash = ' stroke-dasharray="7 5"'
    elif style == "data":
        dash = ' stroke-dasharray="2 4"'
    if status == "removed":
        dash = ' stroke-dasharray="3 3"'
    return stroke, dash, width


def title_block(canvas: Canvas, x: float, y: float, title: str, subtitle: str) -> float:
    """Title and subtitle; returns the y where the drawing starts."""
    canvas.text(x, y + 18, title, 17, 700, INK)
    canvas.grow(x + text_width(title, 17, True), y + 24)
    if subtitle:
        canvas.text(x, y + 38, subtitle, 12.5, 400, MUTED)
        canvas.grow(x + text_width(subtitle, 12.5), y + 44)
        return y + 58
    return y + 38


def legend(canvas: Canvas, x: float, y: float, statuses: list[str], styles: list[tuple[str, str]]) -> float:
    """One row: a swatch per status present, then a sample per line style. Returns the row's bottom."""
    cursor = x
    for status in statuses:
        if status not in LEGEND:
            continue
        stroke, paint, _ = STATUS[status]
        canvas.add(
            f'<rect x="{cursor}" y="{y}" width="16" height="12" rx="3" fill="{paint}" stroke="{stroke}" '
            f'stroke-width="1.8"/>'
        )
        label = LEGEND[status]
        canvas.text(cursor + 22, y + 11, label, 12, 400, MUTED)
        cursor += 22 + text_width(label, 12) + 18
    for style, label in styles:
        stroke, dash, _ = line_style("touched", style)
        canvas.add(
            f'<path d="M{cursor},{y + 6} L{cursor + 26},{y + 6}" stroke="{stroke}" stroke-width="1.4"{dash} '
            f'marker-end="url(#a-touched)"/>'
        )
        canvas.text(cursor + 32, y + 11, label, 12, 400, MUTED)
        cursor += 32 + text_width(label, 12) + 18
    canvas.grow(cursor, y + 14)
    return y + 14


def caption(canvas: Canvas, x: float, y: float, text: str, width: float) -> float:
    if not text:
        return y
    for line in wrap(text, width, 12, max_lines=4):
        canvas.text(x, y + 13, line, 12, 400, MUTED, italic=True)
        y += 17
    canvas.grow(x + width, y)
    return y
