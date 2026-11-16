"""Use-case diagrams: people on the left, systems on the right, use cases inside the product boundary."""

from __future__ import annotations

from baton.diagram import svg
from baton.diagram.shapes import UseCaseDiagram

MARGIN = 24
ACTOR_W = 150
CASE_GAP = 22
BOUND_PAD = 34


def _case_size(label: str, sub: str) -> tuple[list[str], float, float]:
    lines = svg.wrap(label, 230, 13, bold=True, max_lines=2)
    width = max([svg.text_width(t, 13, True) for t in lines] + [svg.text_width(sub, 10.5)]) + 70
    height = 26 + 16 * len(lines) + (13 if sub else 0)
    return lines, max(width, 190), max(height, 50)


def _actor(canvas: svg.Canvas, cx: float, y: float, label: str, kind: str) -> tuple[float, float]:
    """Draws an actor with its top at y; returns the (x, y) its links attach to."""
    lines = svg.wrap(label, ACTOR_W - 10, 12, bold=True, max_lines=2)
    if kind == "person":
        stroke = "#334155"
        canvas.add(
            f'<circle cx="{cx}" cy="{y + 9}" r="8" fill="#ffffff" stroke="{stroke}" stroke-width="1.6"/>'
        )
        canvas.add(
            f'<path d="M{cx},{y + 17} V{y + 36} M{cx - 13},{y + 24} H{cx + 13} '
            f"M{cx},{y + 36} L{cx - 11},{y + 52} "
            f'M{cx},{y + 36} L{cx + 11},{y + 52}" stroke="{stroke}" stroke-width="1.6" fill="none" '
            f'stroke-linecap="round"/>'
        )
        text_y = y + 68
        anchor_y = y + 28
    else:
        canvas.add(
            f'<rect x="{cx - 26}" y="{y + 4}" width="52" height="40" rx="6" fill="#f1f5f9" stroke="#64748b" '
            f'stroke-width="1.4" stroke-dasharray="4 3"/>'
        )
        canvas.text(cx, y + 29, "system", 10, 600, "#64748b", "middle")
        text_y = y + 62
        anchor_y = y + 24
    for i, line in enumerate(lines):
        canvas.text(cx, text_y + i * 15, line, 12, 600, svg.INK, "middle")
    return cx, anchor_y


def draw(diagram: UseCaseDiagram) -> str:
    canvas = svg.Canvas()
    top = svg.title_block(canvas, MARGIN, MARGIN - 6, diagram.title, diagram.subtitle)
    sizes = {c.id: _case_size(c.label, c.sub) for c in diagram.cases}
    included = {link.dst for link in diagram.links if link.kind in ("include", "extend")}
    primary = [c for c in diagram.cases if c.id not in included]
    secondary = [c for c in diagram.cases if c.id in included]
    left = [a for a in diagram.actors if a.side == "left"]
    right = [a for a in diagram.actors if a.side != "left"]
    # order primary cases by the first left actor that uses them, so links do not cross
    first_actor = {}
    for i, actor in enumerate(left + right):
        for link in diagram.links:
            if link.src == actor.id:
                first_actor.setdefault(link.dst, i)
    primary.sort(key=lambda c: (first_actor.get(c.id, 99), diagram.cases.index(c)))
    col1_w = max((sizes[c.id][1] for c in primary), default=200)
    col2_w = max((sizes[c.id][1] for c in secondary), default=0)
    box_x = MARGIN + ACTOR_W + 40
    inner_x = box_x + BOUND_PAD
    box_w = BOUND_PAD * 2 + col1_w + (col2_w + 90 if secondary else 0)
    y = top + 44
    centers: dict[str, tuple[float, float, float, float]] = {}
    for case in primary:
        lines, w, h = sizes[case.id]
        centers[case.id] = (inner_x + col1_w / 2, y + h / 2, w, h)
        y += h + CASE_GAP
    col1_bottom = y
    for case in secondary:
        users = [
            centers[link.src][1] for link in diagram.links if link.dst == case.id and link.src in centers
        ]
        lines, w, h = sizes[case.id]
        want = sum(users) / len(users) if users else top + 44 + h / 2
        centers[case.id] = (inner_x + col1_w + 90 + col2_w / 2, want, w, h)
    # de-overlap the second column
    second = sorted(secondary, key=lambda c: centers[c.id][1])
    floor = top + 44
    for case in second:
        cx, cy, w, h = centers[case.id]
        cy = max(cy, floor + h / 2)
        centers[case.id] = (cx, cy, w, h)
        floor = cy + h / 2 + CASE_GAP
    box_bottom = (
        max([col1_bottom] + [centers[c.id][1] + centers[c.id][3] / 2 + CASE_GAP for c in secondary]) + 6
    )
    canvas.add(
        f'<rect x="{box_x}" y="{top + 6}" width="{box_w}" height="{box_bottom - top - 6:.1f}" rx="14" '
        f'fill="#f8fafc" stroke="#94a3b8" stroke-width="1.4"/>'
    )
    canvas.text(box_x + 16, top + 27, diagram.system, 13, 700, "#334155")

    # actors, centred on the cases they use
    def place(actors, x: float) -> dict[str, tuple[float, float]]:
        out = {}
        floor = top + 20
        for actor in actors:
            ys = [
                centers[link.dst][1] for link in diagram.links if link.src == actor.id and link.dst in centers
            ]
            want = (sum(ys) / len(ys) - 34) if ys else floor
            y0 = max(want, floor)
            out[actor.id] = _actor(canvas, x, y0, actor.label, actor.kind)
            floor = y0 + 96
            canvas.grow(x + ACTOR_W / 2, y0 + 90)
        return out

    anchors = place(left, MARGIN + ACTOR_W / 2)
    right_x = box_x + box_w + 40 + ACTOR_W / 2
    anchors.update(place(right, right_x))
    # links behind the ellipses
    for link in diagram.links:
        if link.dst not in centers:
            continue
        cx, cy, w, h = centers[link.dst]
        if link.src in anchors:
            ax, ay = anchors[link.src]
            tx = cx - w / 2 if ax < cx else cx + w / 2
            canvas.add(
                f'<line x1="{ax + (16 if ax < cx else -16):.1f}" y1="{ay:.1f}" x2="{tx:.1f}" y2="{cy:.1f}" '
                f'stroke="#475569" stroke-width="1.3"/>'
            )
        elif link.src in centers:
            sx, sy, sw, sh = centers[link.src]
            stroke = "#475569"
            canvas.add(
                f'<path d="M{sx + sw / 2:.1f},{sy:.1f} C{sx + sw / 2 + 40:.1f},{sy:.1f} '
                f"{cx - w / 2 - 40:.1f},{cy:.1f} "
                f'{cx - w / 2 - 2:.1f},{cy:.1f}" fill="none" stroke="{stroke}" stroke-width="1.3" '
                f'stroke-dasharray="6 4" marker-end="url(#o-touched)"/>'
            )
            label = f"<<{link.kind}>>"
            mx = (sx + sw / 2 + cx - w / 2) / 2
            my = (sy + cy) / 2
            svg.pill(canvas, mx, my, [label], "touched")
    for case in diagram.cases:
        cx, cy, w, h = centers[case.id]
        lines, _, _ = sizes[case.id]
        stroke = svg.color(case.status)
        paint = svg.fill(case.status)
        width = 2 if case.status in ("new", "changed", "impacted", "removed") else 1.3
        canvas.add(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{w / 2:.1f}" ry="{h / 2:.1f}" fill="{paint}" '
            f'stroke="{stroke}" stroke-width="{width}" filter="url(#lift)"/>'
        )
        block = len(lines) * 16 + (13 if case.sub else 0)
        ty = cy - block / 2 + 12
        for line in lines:
            canvas.text(cx, ty, line, 13, 600, svg.INK, "middle")
            ty += 16
        if case.sub:
            canvas.text(cx, ty, case.sub, 10.5, 400, svg.MUTED, "middle")
        svg.chip(canvas, cx + w / 2 - 14, cy - h / 2 - 6, case.status)
    canvas.grow(box_x + box_w + (ACTOR_W + 60 if right else 0), box_bottom)
    present = sorted({c.status for c in diagram.cases}, key=lambda s: list(svg.STATUS).index(s))
    y = svg.legend(canvas, MARGIN, box_bottom + 20, present, [])
    svg.caption(canvas, MARGIN, y + 8, diagram.caption, max(400.0, canvas.width - 2 * MARGIN))
    return canvas.render(diagram.title)
