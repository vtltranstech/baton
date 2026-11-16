"""Sequence diagrams: lifelines, numbered steps, activation bars, error fragments, impact notes."""

from __future__ import annotations

from baton.diagram import svg
from baton.diagram.shapes import TOUCHED, Sequence

MARGIN = 24
HEAD_H = 50
ROW = 36
SELF_ROW = 50
MIN_SPACING = 130


def _head_size(label: str, sub: str, kind: str) -> tuple[list[str], float, float]:
    lines = svg.wrap(label, 170, 13, bold=True, max_lines=2)
    width = max([svg.text_width(t, 13, True) for t in lines] + [svg.text_width(sub, 11.5), 84]) + 28
    height = 20 + 16 * len(lines) + (15 if sub else 0)
    if kind == "store":
        height += 14
    if kind == "person":
        height += 26
    return lines, width, max(height, 44)


def draw(seq: Sequence) -> str:
    canvas = svg.Canvas()
    top = svg.title_block(canvas, MARGIN, MARGIN - 6, seq.title, seq.subtitle)
    heads = {p.id: _head_size(p.label, p.sub, p.kind) for p in seq.participants}
    order = [p.id for p in seq.participants]
    index = {pid: i for i, pid in enumerate(order)}
    # spacing: neighbours never overlap; every message label fits between its two lifelines
    gaps = []
    for a, b in zip(order, order[1:], strict=False):
        gaps.append(max(MIN_SPACING, heads[a][1] / 2 + heads[b][1] / 2 + 26))
    gaps.append(0)
    numbered = [m for m in seq.messages if m.kind != "return"]
    for msg in seq.messages:
        if msg.src not in index or msg.dst not in index or not msg.label:
            continue
        i, j = sorted((index[msg.src], index[msg.dst]))
        # a label may wrap onto two lines, so a gap needs room for the longer half, not the whole label
        lines = svg.wrap(msg.label, _half(msg.label), 12.5, msg.status in ("new", "changed"), max_lines=2)
        need = max(svg.text_width(t, 12.5, msg.status in ("new", "changed")) for t in lines) + (
            52 if msg in numbered else 30
        )
        if i == j:
            gaps[i] = max(gaps[i], need + 20) if i < len(gaps) - 1 else gaps[i]
            continue
        have = sum(gaps[i:j])
        if have < need:
            extra = (need - have) / (j - i)
            for k in range(i, j):
                gaps[k] += extra
    head_h = max((h for _, _, h in heads.values()), default=HEAD_H)
    xs = {}
    cursor = MARGIN + max((heads[order[0]][1] / 2 if order else 0), 60)
    for i, pid in enumerate(order):
        xs[pid] = cursor
        cursor += gaps[i]
    width = (xs[order[-1]] + heads[order[-1]][1] / 2 + MARGIN) if order else 400
    # rows
    rows: list[float] = []
    extra: list[int] = []  # label lines above the first, per message
    y = top + head_h + 30
    opens = {f.first for f in seq.fragments}
    closes = {f.last for f in seq.fragments}
    for position, msg in enumerate(seq.messages):
        if position in opens:
            y += 26
        if msg.kind == "return" and not msg.label:
            rows.append(y - 8)  # closes an activation without a drawn arrow
            extra.append(0)
            continue
        span = abs(xs.get(msg.dst, 0) - xs.get(msg.src, 0)) - 30
        lines = svg.wrap(msg.label, max(span, 140), 12.5, max_lines=2) if msg.label else []
        if position in opens:
            y += 14 * max(0, len(lines) - 1)  # a wrapped first label stays below the fragment's tag
        height = (SELF_ROW if msg.src == msg.dst else ROW) + 14 * max(0, len(lines) - 1)
        extra.append(max(0, len(lines) - 1))
        rows.append(y + 14 * max(0, len(lines) - 1))
        y += height + (12 if position in closes else 0)
    bottom = y + 10
    kinds = {p.id: p.kind for p in seq.participants}
    # fragments behind everything; their tags go on top at the end
    tags: list[tuple[float, float, str, str, str]] = []
    for frag in seq.fragments:
        involved = [
            xs[p] for m in seq.messages[frag.first : frag.last + 1] for p in (m.src, m.dst) if p in xs
        ]
        if not involved:
            continue
        fx = min(involved) - 40
        fw = max(involved) - min(involved) + 80
        fy = rows[frag.first] - 44 - 14 * extra[frag.first]
        fh = rows[frag.last] - fy + 14
        tone = "#dc2626" if frag.kind == "alt" else svg.MUTED
        canvas.add(
            f'<rect x="{fx:.1f}" y="{fy:.1f}" width="{fw:.1f}" height="{fh:.1f}" rx="4" fill="#fff5f5" '
            f'fill-opacity="0.55" stroke="{tone}" stroke-width="1" stroke-dasharray="4 3"/>'
        )
        tags.append((fx, fy, frag.kind, frag.label, tone))
    # heads and lifelines
    for p in seq.participants:
        lines, w, h = heads[p.id]
        x = xs[p.id] - w / 2
        canvas.add(
            f'<line x1="{xs[p.id]:.1f}" y1="{top + h:.1f}" x2="{xs[p.id]:.1f}" y2="{bottom:.1f}" '
            f'stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="5 5"/>'
        )
        svg.box(canvas, x, top, w, h, lines, p.sub, p.status, p.kind)
    # activation bars
    stacks: dict[str, list[float]] = {}
    bars: list[tuple[str, float, float, int]] = []
    for msg, row in zip(seq.messages, rows, strict=True):
        if msg.kind == "sync" and msg.src != msg.dst and kinds.get(msg.dst) not in ("store", "queue", "file"):
            stacks.setdefault(msg.dst, []).append(row)
        elif msg.kind in ("return", "error") and stacks.get(msg.src):
            start = stacks[msg.src].pop()
            bars.append((msg.src, start, row, len(stacks[msg.src])))
    for pid, rest in stacks.items():
        for depth, start in enumerate(rest):
            bars.append((pid, start, bottom - 14, depth))
    for pid, start, end, depth in sorted(bars, key=lambda b: (b[3], b[1])):
        x = xs[pid] - 6 + depth * 5
        canvas.add(
            f'<rect x="{x:.1f}" y="{start - 4:.1f}" width="12" height="{max(end - start + 8, 14):.1f}" '
            f'rx="2" fill="#e2e8f0" stroke="#64748b" stroke-width="1"/>'
        )
    # messages
    number = 0
    for msg, row in zip(seq.messages, rows, strict=True):
        if msg.kind == "return" and not msg.label:
            continue
        if msg.src not in xs or msg.dst not in xs:
            continue
        status = msg.status if msg.status in svg.STATUS else TOUCHED
        stroke, dash, line_w = svg.line_style(status, "async" if msg.kind == "async" else "sync")
        if msg.kind in ("return", "error"):
            dash = ' stroke-dasharray="6 4"'
            line_w = 1.3
        if msg.kind == "error":
            stroke = "#dc2626"
        marker = f"{'o' if msg.kind in ('async', 'return', 'error') else 'a'}-{status}"
        if msg.kind == "error":
            marker = "o-impacted"
        x1, x2 = xs[msg.src], xs[msg.dst]
        bold = status in ("new", "changed")
        tone = stroke if (bold or msg.kind == "error") else svg.INK
        if msg.src == msg.dst:
            canvas.add(
                f'<path d="M{x1 + 6:.1f},{row:.1f} h38 v16 h-32" fill="none" stroke="{stroke}" '
                f'stroke-width="{line_w}"{dash} marker-end="url(#{marker})"/>'
            )
            label_x, anchor = x1 + 50, "start"
            label_y = row + 12
        else:
            direction = 1 if x2 > x1 else -1
            start = x1 + 6 * direction
            end = x2 - 7 * direction
            canvas.add(
                f'<line x1="{start:.1f}" y1="{row:.1f}" x2="{end:.1f}" y2="{row:.1f}" stroke="{stroke}" '
                f'stroke-width="{line_w}"{dash} marker-end="url(#{marker})"/>'
            )
            label_x, anchor = (x1 + x2) / 2, "middle"
            label_y = row - 7
        if msg.kind not in ("return", "error"):
            number += 1
            cx = x1 + (14 if x2 >= x1 else -14)
            if msg.src == msg.dst:
                cx = x1 + 14
            circle = stroke if bold else "#475569"
            canvas.add(f'<circle cx="{cx:.1f}" cy="{row - 10:.1f}" r="8" fill="{circle}"/>')
            canvas.text(cx, row - 6.5, str(number), 9.5, 700, "#ffffff", "middle")
            if anchor == "middle":
                label_x += 8 if x2 >= x1 else -8
        span = abs(x2 - x1) - 30
        lines = svg.wrap(msg.label, max(span, 140), 12.5, max_lines=2) if msg.label else []
        for k, line in enumerate(lines):
            offset = (k - len(lines) + 1) * 14 if msg.src != msg.dst else k * 14
            canvas.text(
                label_x,
                label_y + offset,
                line,
                12.5,
                600 if bold else 400,
                tone,
                anchor,
                mono=False,
                italic=msg.kind in ("return", "error"),
            )
        if msg.note:
            nx = max(x1, x2) + 18
            note_w = svg.text_width(msg.note, 12) + 16
            canvas.add(
                f'<path d="M{nx:.1f},{row - 11:.1f} h{note_w:.1f} v22 h{-note_w:.1f} Z" fill="#fefce8" '
                f'stroke="#ca8a04" stroke-width="1"/>'
            )
            canvas.text(nx + 8, row + 4, msg.note, 12, 500, "#854d0e")
            width = max(width, nx + note_w + MARGIN)
        width = max(
            width, label_x + (svg.text_width(lines[0], 12.5) if lines and anchor == "start" else 0) + MARGIN
        )
    for fx, fy, kind, label, tone in tags:
        tag_w = svg.text_width(kind, 10.5, True) + 16
        canvas.add(
            f'<path d="M{fx:.1f},{fy:.1f} h{tag_w:.1f} v11 l-6,6 h{-(tag_w - 6):.1f} Z" fill="{tone}"/>'
        )
        canvas.text(fx + 7, fy + 12, kind, 10.5, 700, "#ffffff")
        label_w = svg.text_width(f"[{label}]", 12) + 8
        canvas.add(
            f'<rect x="{fx + tag_w + 4:.1f}" y="{fy + 2:.1f}" width="{label_w:.1f}" height="15" '
            f'fill="#ffffff" fill-opacity="0.9"/>'
        )
        canvas.text(fx + tag_w + 8, fy + 13, f"[{label}]", 12, 600, tone)
    canvas.grow(width, bottom)
    present = sorted({p.status for p in seq.participants} | {m.status for m in seq.messages}, key=_order)
    styles = [("sync", "call")]
    if any(m.kind == "async" for m in seq.messages):
        styles.append(("async", "event / message"))
    y = svg.legend(canvas, MARGIN, bottom + 18, present, styles)
    svg.caption(canvas, MARGIN, y + 8, seq.caption, max(400.0, canvas.width - 2 * MARGIN))
    return canvas.render(seq.title)


def _half(label: str) -> float:
    """The width to wrap a message label at so it splits into two near-equal lines (never under 140)."""
    return max(140.0, svg.text_width(label, 12.5) / 2 + 24)


def _order(status: str) -> int:
    return ("new", "changed", "removed", "impacted", "touched", "context").index(status)
