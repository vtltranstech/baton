"""Low-level design (class diagram) and data model: compartment boxes, layered top-down, changed rows
marked."""

from __future__ import annotations

from dataclasses import dataclass

from baton.diagram import svg
from baton.diagram.draw_flow import _ranks
from baton.diagram.shapes import CONTEXT, Box, ClassDiagram, Link, Member

MARGIN = 24
ROW_H = 19
HEAD_H = 46
COL_GAP = 46
ROW_GAP = 86
MAX_W = 620
MEMBER_SIZE = 11.5


@dataclass
class _Laid:
    box: Box
    w: float
    h: float
    rank: int = 0
    x: float = 0.0
    y: float = 0.0


def _rows(box: Box, entity: bool) -> list[list[Member]]:
    if box.collapsed:
        return []
    groups = [box.fields] if entity else [box.fields, box.methods]
    return [g for g in groups if g] or ([[]] if not entity else [])


def _measure(box: Box, entity: bool) -> tuple[float, float]:
    head = max(svg.text_width(box.name, 14, True) + 70, svg.text_width(f"<<{box.stereo}>>", 10.5) + 40)
    if box.sub:
        head = max(head, svg.text_width(box.sub, 10) + 24)
    texts = [m.text for group in _rows(box, entity) for m in group]
    tagged = any(m.status for group in _rows(box, entity) for m in group)
    body = max([svg.text_width(t, MEMBER_SIZE, mono=True) + 40 + (58 if tagged else 0) for t in texts] + [0])
    width = min(MAX_W, max(head, body, 150))
    groups = _rows(box, entity)
    height = HEAD_H + (14 if box.sub else 0)
    for group in groups:
        height += 8 + ROW_H * max(len(group), 1)
    return width, height


def draw(diagram: ClassDiagram) -> str:
    canvas = svg.Canvas()
    top = svg.title_block(canvas, MARGIN, MARGIN - 6, diagram.title, diagram.subtitle)
    laid = {b.id: _Laid(b, *_measure(b, diagram.entity)) for b in diagram.boxes}
    ids = [b.id for b in diagram.boxes]
    rank_links = []
    for rel in diagram.relations:
        if rel.src in laid and rel.dst in laid and rel.src != rel.dst:
            upper, lower = (rel.dst, rel.src) if rel.kind in ("implements", "extends") else (rel.src, rel.dst)
            rank_links.append(Link(upper, lower))
    ranks = _ranks(ids, rank_links)
    for box_id, item in laid.items():
        item.rank = ranks.get(box_id, 0)
    rows: dict[int, list[_Laid]] = {}
    for box_id in ids:
        rows.setdefault(laid[box_id].rank, []).append(laid[box_id])
    # barycentre order within a row, by the positions of the boxes above
    parents: dict[str, list[str]] = {}
    for link in rank_links:
        parents.setdefault(link.dst, []).append(link.src)
    position: dict[str, float] = {}
    for r in sorted(rows):
        members = rows[r]
        if r > 0:
            members.sort(
                key=lambda it: (
                    sum(position.get(p, 0) for p in parents.get(it.box.id, [])) / len(parents[it.box.id])
                    if parents.get(it.box.id)
                    else 1e9
                )
            )
        for i, item in enumerate(members):
            position[item.box.id] = i
    widths = {r: sum(it.w for it in m) + COL_GAP * (len(m) - 1) for r, m in rows.items()}
    widest = max(widths.values(), default=300)
    y = top + 10
    for r in sorted(rows):
        x = MARGIN + (widest - widths[r]) / 2
        tallest = max(it.h for it in rows[r])
        for item in rows[r]:
            item.x, item.y = x, y
            x += item.w + COL_GAP
        y += tallest + ROW_GAP
    bottom = y - ROW_GAP
    # relations under the boxes
    pills = []
    by_side: dict[tuple[str, str], list] = {}
    rels = [r for r in diagram.relations if r.src in laid and r.dst in laid and r.src != r.dst]
    for rel in rels:
        a, b = laid[rel.src], laid[rel.dst]
        by_side.setdefault((rel.src, "out"), []).append(rel)
        by_side.setdefault((rel.dst, "in"), []).append(rel)

    def spread(item: _Laid, rel, side: str, other: _Laid) -> float:
        group = sorted(by_side[(item.box.id, side)], key=lambda r: laid[r.dst if side == "out" else r.src].x)
        if len(group) == 1:
            return item.x + item.w / 2
        k = group.index(rel)
        return item.x + item.w * (0.2 + 0.6 * k / (len(group) - 1))

    for rel in rels:
        a, b = laid[rel.src], laid[rel.dst]
        stroke, dash, width_px = svg.line_style(rel.status if rel.status != CONTEXT else "touched", "sync")
        status = rel.status if rel.status in svg.STATUS else CONTEXT
        if rel.kind in ("implements", "extends"):
            marker = f"t-{status}"
            dash = ' stroke-dasharray="6 4"' if rel.kind == "implements" else ""
        elif rel.kind == "creates":
            marker = f"o-{status}"
            dash = ' stroke-dasharray="2 4"'
        else:
            marker = f"a-{status}"
        if abs(a.y - b.y) < 1:  # same row: side to side
            left, right = (a, b) if a.x < b.x else (b, a)
            y1 = a.y + min(a.h, b.h) / 2
            x1, x2 = (a.x + a.w, b.x - 2) if a is left else (a.x, b.x + b.w + 2)
            path = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y1:.1f}"
            mid = ((x1 + x2) / 2, y1)
        else:
            downward = b.y > a.y
            x1 = spread(a, rel, "out", b)
            x2 = spread(b, rel, "in", a)
            y1 = a.y + a.h if downward else a.y
            y2 = b.y - 2 if downward else b.y + b.h + 2
            dy = (y2 - y1) / 2
            path = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dy:.1f} {x2:.1f},{y2 - dy:.1f} {x2:.1f},{y2:.1f}"
            mid = ((x1 + x2) / 2, y1 + dy)
            others = [(o.x, o.y, o.w, o.h) for o in laid.values() if o is not a and o is not b]
            if _crosses((x1, y1), (x1, y1 + dy), (x2, y2 - dy), (x2, y2), others):
                xm = _free_x(min(y1, y2), max(y1, y2), (x1 + x2) / 2, others)
                ym = (y1 + y2) / 2
                path = (
                    f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dy / 2:.1f} "
                    f"{xm:.1f},{ym - dy / 2:.1f} {xm:.1f},{ym:.1f} "
                    f"S{x2:.1f},{y2 - dy / 2:.1f} {x2:.1f},{y2:.1f}"
                )
                mid = (xm, ym)
        canvas.add(
            f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="{width_px}"{dash} '
            f'marker-end="url(#{marker})"/>'
        )
        label = rel.label or ("<<create>>" if rel.kind == "creates" else "")
        if label:
            pills.append((mid, label, rel.status))
    for item in laid.values():
        _box(canvas, item, diagram.entity)
        canvas.grow(item.x + item.w, item.y + item.h)
    placed: list[tuple[float, float, float, float]] = [(it.x, it.y, it.w, it.h) for it in laid.values()]
    for (cx, cy), label, status in pills:
        w = svg.text_width(label, 11) + 12
        rect = (cx - w / 2, cy - 9.5, w, 19)
        for dx, dy in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0), (0, 2), (0, -2), (1, 1), (-1, -1)):
            trial = (rect[0] + dx * (w / 2 + 6), rect[1] + dy * 22, w, 19)
            if not any(_overlap(trial, other) for other in placed):
                rect = trial
                break
        placed.append(rect)
        svg.pill(canvas, rect[0] + w / 2, rect[1] + 9.5, [label], status)
    canvas.grow(MARGIN + widest, bottom)
    present = sorted(
        {b.status for b in diagram.boxes}
        | {m.status for b in diagram.boxes for m in b.fields + b.methods if m.status},
        key=_order,
    )
    y = svg.legend(canvas, MARGIN, bottom + 22, present, [])
    note = (
        ""
        if diagram.entity
        else "dashed line with |> = implements - solid arrow = uses (field or method on the arrow)"
    )
    if note:
        canvas.text(MARGIN, y + 18, note, 11, 400, svg.MUTED)
        canvas.grow(MARGIN + svg.text_width(note, 11), y + 22)
        y += 20
    svg.caption(canvas, MARGIN, y + 8, diagram.caption, max(400.0, canvas.width - 2 * MARGIN))
    return canvas.render(diagram.title)


def _crosses(p0, p1, p2, p3, boxes) -> bool:
    from baton.diagram.draw_flow import _bezier, _hits

    return _hits([_bezier(p0, p1, p2, p3, t / 20) for t in range(2, 19)], boxes)


def _free_x(top: float, bottom: float, want: float, boxes) -> float:
    """An x between top and bottom where no box stands, nearest to `want`."""
    rows = [b for b in boxes if b[1] < bottom and b[1] + b[3] > top]
    if not rows:
        return want
    candidates = [min(b[0] for b in rows) - 24, max(b[0] + b[2] for b in rows) + 24]
    ordered = sorted(rows)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b[0] - (a[0] + a[2]) > 30:
            candidates.append((a[0] + a[2] + b[0]) / 2)
    free = [c for c in candidates if not any(b[0] - 8 < c < b[0] + b[2] + 8 for b in rows)]
    return min(free or candidates, key=lambda c: abs(c - want))


def _overlap(a, b, pad=3.0) -> bool:
    return not (
        a[0] + a[2] + pad <= b[0]
        or b[0] + b[2] + pad <= a[0]
        or a[1] + a[3] + pad <= b[1]
        or b[1] + b[3] + pad <= a[1]
    )


def _order(status: str) -> int:
    return ("new", "changed", "removed", "impacted", "touched", "context").index(status)


def _box(canvas: svg.Canvas, item: _Laid, entity: bool) -> None:
    box, x, y, w, h = item.box, item.x, item.y, item.w, item.h
    stroke = svg.color(box.status if box.status != CONTEXT else "touched")
    head_fill = svg.fill(box.status) if box.status not in ("touched", CONTEXT) else "#f1f5f9"
    width = 2 if box.status in ("new", "changed", "removed", "impacted") else 1.3
    dash = ' stroke-dasharray="5 4"' if box.collapsed and box.status == CONTEXT else ""
    canvas.add(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="#ffffff" '
        f'stroke="{stroke}" stroke-width="{width}"{dash} filter="url(#lift)"/>'
    )
    head_h = HEAD_H + (14 if box.sub else 0)
    if box.collapsed:
        head_h = h
    canvas.add(
        f'<path d="M{x + 8:.1f},{y:.1f} H{x + w - 8:.1f} A8,8 0 0 1 {x + w:.1f},{y + 8:.1f} '
        f'V{y + head_h:.1f} H{x:.1f} V{y + 8:.1f} A8,8 0 0 1 {x + 8:.1f},{y:.1f} Z" fill="{head_fill}"/>'
        if not box.collapsed
        else f'<rect x="{x + 1:.1f}" y="{y + 1:.1f}" width="{w - 2:.1f}" height="{h - 2:.1f}" '
        f'rx="7" fill="{head_fill}"/>'
    )
    cy = y + 17
    if box.stereo:
        canvas.text(x + w / 2, cy, f"<<{box.stereo}>>", 10.5, 400, svg.MUTED, "middle", italic=True)
        cy += 17
    else:
        cy += 8
    canvas.text(x + w / 2, cy, box.name, 14, 700, svg.INK, "middle")
    if box.sub:
        canvas.text(x + w / 2, cy + 15, box.sub, 10, 400, svg.MUTED, "middle")
    svg.chip(canvas, x + w - 8, y - 8, box.status)
    if box.collapsed:
        return
    cursor = y + head_h
    for group in _rows(box, entity):
        canvas.add(
            f'<line x1="{x:.1f}" y1="{cursor:.1f}" x2="{x + w:.1f}" y2="{cursor:.1f}" stroke="{stroke}" '
            f'stroke-width="0.8" opacity="0.6"/>'
        )
        cursor += 4
        if not group:
            cursor += ROW_H
        for member in group:
            if member.status:
                tone = svg.color(member.status)
                canvas.add(
                    f'<rect x="{x + 1:.1f}" y="{cursor:.1f}" width="{w - 2:.1f}" height="{ROW_H}" '
                    f'fill="{svg.fill(member.status)}"/>'
                )
                canvas.add(
                    f'<rect x="{x + 1:.1f}" y="{cursor:.1f}" width="3" height="{ROW_H}" fill="{tone}"/>'
                )
            text = member.text
            limit = w - 34 - (58 if member.status else 0)
            while svg.text_width(text, MEMBER_SIZE, mono=True) > limit and len(text) > 4:
                text = text.removesuffix("...")[:-1] + "..."
            tone = svg.color(member.status) if member.status else svg.INK
            weight = 600 if member.status else 400
            canvas.text(
                x + 14,
                cursor + 14,
                text,
                MEMBER_SIZE,
                weight,
                tone,
                mono=True,
                extra=' text-decoration="line-through"' if member.status == "removed" else "",
            )
            if member.status:
                canvas.text(
                    x + w - 10,
                    cursor + 13.5,
                    member.status,
                    9.5,
                    700,
                    tone,
                    "end",
                    extra=' letter-spacing="0.4"',
                )
            cursor += ROW_H
        cursor += 4
