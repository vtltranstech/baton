"""Flow diagrams (architecture views, flow with impacts): swim lanes as rows, call depth as columns.

Layout: longest-path layering left to right, sources pulled next to what they call, barycentre ordering in
each lane, curved links with ports spread along a box side, links routed round boxes they would cross,
labels kept off each other. Deterministic: the same input draws the same file.
"""

from __future__ import annotations

from dataclasses import dataclass

from baton.diagram import svg
from baton.diagram.shapes import CONTEXT, Flow, Link, Node

LANE_HEAD = 118
MARGIN = 24
NODE_GAP = 22
LANE_PAD = 30
MIN_GAP = 56
MAX_GAP = 170
MAX_STACK = 8
SUB_GAP = 26
LABEL_WRAP = 120


@dataclass
class _Placed:
    node: Node
    lines: list[str]
    w: float
    h: float
    rank: int = 0
    x: float = 0.0
    y: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _size(node: Node) -> tuple[list[str], float, float]:
    lines = svg.wrap(node.label, 168, 13, bold=True)
    width = max([svg.text_width(t, 13, True) for t in lines] + [svg.text_width(node.sub, 11.5), 96]) + 30
    height = 20 + 16 * len(lines) + (15 if node.sub else 0)
    if node.kind == "store":
        height += 14
    elif node.kind == "person":
        height += 26
        width = max(width, 120)
    return lines, width, max(height, 46)


def _ranks(ids: list[str], links: list[Link]) -> dict[str, int]:
    succ: dict[str, list[str]] = {i: [] for i in ids}
    for link in links:
        if link.src != link.dst and link.dst not in succ[link.src]:
            succ[link.src].append(link.dst)
    # break cycles: an edge back to a node on the DFS stack is ignored for ranking
    state: dict[str, int] = {}
    forward: dict[str, list[str]] = {i: [] for i in ids}

    def visit(start: str) -> None:
        stack = [(start, iter(succ[start]))]
        state[start] = 1
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[node] = 2
                stack.pop()
                continue
            if state.get(child) == 1:
                continue
            forward[node].append(child)
            if child not in state:
                state[child] = 1
                stack.append((child, iter(succ[child])))

    for node_id in ids:
        if node_id not in state:
            visit(node_id)
    preds: dict[str, list[str]] = {i: [] for i in ids}
    for src, targets in forward.items():
        for dst in targets:
            preds[dst].append(src)
    rank: dict[str, int] = {}
    order: list[str] = []
    pending = {i: len(preds[i]) for i in ids}
    ready = [i for i in ids if pending[i] == 0]
    while ready:
        node = ready.pop(0)
        order.append(node)
        rank[node] = max((rank[p] + 1 for p in preds[node]), default=0)
        for child in forward[node]:
            pending[child] -= 1
            if pending[child] == 0:
                ready.append(child)
    # a pure source sits just before the first thing it calls, not at the far left
    for node in reversed(order):
        if not preds[node] and forward[node]:
            rank[node] = max(rank[node], min(rank[c] for c in forward[node]) - 1)
    return rank


def layout(flow: Flow) -> tuple[dict[str, _Placed], list[tuple[str, float, float]], float]:
    """Places every node; returns (placed by id, lane bands (title, top, bottom), right edge)."""
    placed: dict[str, _Placed] = {}
    for node in flow.nodes:
        lines, w, h = _size(node)
        placed[node.id] = _Placed(node, lines, w, h)
    ids = [n.id for n in flow.nodes]
    links = [lk for lk in flow.links if lk.src in placed and lk.dst in placed]
    ranks = _ranks(ids, links)
    for node_id, item in placed.items():
        item.rank = ranks.get(node_id, 0)
    lane_ids = [lane.id for lane in flow.lanes]
    for node in flow.nodes:
        if node.lane not in lane_ids:
            lane_ids.append(node.lane)
    lane_ids = [lane for lane in lane_ids if any(n.lane == lane for n in flow.nodes)]
    max_rank = max((p.rank for p in placed.values()), default=0)
    cells: dict[tuple[str, int], list[str]] = {}
    for node in flow.nodes:
        cells.setdefault((node.lane, placed[node.id].rank), []).append(node.id)
    preds: dict[str, list[str]] = {}
    for link in links:
        preds.setdefault(link.dst, []).append(link.src)
    # barycentre ordering inside each cell, two sweeps
    for _ in range(2):
        position = {}
        for lane_index, lane in enumerate(lane_ids):
            for r in range(max_rank + 1):
                for i, node_id in enumerate(cells.get((lane, r), [])):
                    position[node_id] = lane_index * 100 + i
        for _key, members in cells.items():
            members.sort(
                key=lambda n: (
                    sum(position[p] for p in preds.get(n, [])) / len(preds[n])
                    if preds.get(n)
                    else position[n]
                )
            )
    # a crowded cell wraps into sub-columns of at most MAX_STACK boxes, so no lane grows without bound
    chunks: dict[tuple[str, int], list[list[str]]] = {
        key: [members[i : i + MAX_STACK] for i in range(0, len(members), MAX_STACK)]
        for key, members in cells.items()
    }
    col_w = [0.0] * (max_rank + 1)
    for (_lane, r), parts in chunks.items():
        width = sum(max(placed[n].w for n in part) for part in parts) + SUB_GAP * (len(parts) - 1)
        col_w[r] = max(col_w[r], width)
    gaps = [MIN_GAP] * (max_rank + 1)
    for link in links:
        a, b = placed[link.src].rank, placed[link.dst].rank
        if link.label and b > a:
            label_w = max(svg.text_width(t, 12) for t in svg.wrap(link.label, LABEL_WRAP, 12)) + 40
            gaps[a] = min(MAX_GAP, max(gaps[a], label_w))
    left = MARGIN + (LANE_HEAD if any(lane for lane in lane_ids) or len(lane_ids) > 1 else 0)
    col_x = []
    cursor = left + 16
    for r in range(max_rank + 1):
        col_x.append(cursor)
        cursor += col_w[r] + gaps[r]
    right = cursor - gaps[-1] + 28 if col_w else left + 200
    bands: list[tuple[str, float, float]] = []
    top = 0.0
    for lane in lane_ids:
        tallest = 0.0
        for r in range(max_rank + 1):
            for part in chunks.get((lane, r), []):
                stack = sum(placed[n].h for n in part) + NODE_GAP * max(0, len(part) - 1)
                tallest = max(tallest, stack)
        height = max(tallest + 2 * LANE_PAD, 96)
        for r in range(max_rank + 1):
            parts = chunks.get((lane, r), [])
            widths = [max(placed[n].w for n in part) for part in parts]
            used = sum(widths) + SUB_GAP * max(0, len(parts) - 1)
            x = col_x[r] + (col_w[r] - used) / 2
            for part, part_w in zip(parts, widths, strict=True):
                stack = sum(placed[n].h for n in part) + NODE_GAP * max(0, len(part) - 1)
                y = top + (height - stack) / 2
                for node_id in part:
                    item = placed[node_id]
                    item.x = x + (part_w - item.w) / 2
                    item.y = y
                    y += item.h + NODE_GAP
                x += part_w + SUB_GAP
        bands.append((lane, top, top + height))
        top += height
    return placed, bands, right


def _bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _hits(points, boxes) -> bool:
    for x, y in points:
        for bx, by, bw, bh in boxes:
            if bx - 4 < x < bx + bw + 4 and by - 4 < y < by + bh + 4:
                return True
    return False


def _overlap(a, b, pad=3.0) -> bool:
    return not (
        a[0] + a[2] + pad <= b[0]
        or b[0] + b[2] + pad <= a[0]
        or a[1] + a[3] + pad <= b[1]
        or b[1] + b[3] + pad <= a[1]
    )


def draw(flow: Flow) -> str:
    canvas = svg.Canvas()
    start_y = svg.title_block(canvas, MARGIN, MARGIN - 6, flow.title, flow.subtitle)
    placed, bands, right = layout(flow)
    for item in placed.values():
        item.y += start_y
    lane_titles = {lane.id: lane for lane in flow.lanes}
    width = max(right, canvas.width)
    show_heads = len(bands) > 1 or any(b[0] for b in bands)
    for index, (lane_id, top, bottom) in enumerate(bands):
        top += start_y
        bottom += start_y
        canvas.add(
            f'<rect x="{MARGIN}" y="{top:.1f}" width="{width - MARGIN:.1f}" height="{bottom - top:.1f}" '
            f'fill="{svg.LANE_FILLS[index % 2]}"/>'
        )
        canvas.add(
            f'<line x1="{MARGIN}" y1="{top:.1f}" x2="{width:.1f}" y2="{top:.1f}" '
            'stroke="#e2e8f0" stroke-width="1"/>'
        )
        if show_heads:
            lane = lane_titles.get(lane_id)
            title = lane.title if lane else lane_id
            sub = lane.sub if lane else ""
            canvas.add(
                f'<line x1="{MARGIN + LANE_HEAD}" y1="{top:.1f}" x2="{MARGIN + LANE_HEAD}" y2="{bottom:.1f}" '
                f'stroke="#e2e8f0" stroke-width="1"/>'
            )
            lines = svg.wrap(title.upper(), LANE_HEAD - 22, 11, bold=True, max_lines=3)
            sub_lines = svg.wrap(sub, LANE_HEAD - 22, 10.5, max_lines=3) if sub else []
            block = len(lines) * 14 + len(sub_lines) * 13 + (4 if sub_lines else 0)
            y = top + (bottom - top - block) / 2 + 11
            for line in lines:
                canvas.text(MARGIN + 12, y, line, 11, 700, "#334155", extra=' letter-spacing="0.6"')
                y += 14
            y += 4
            for line in sub_lines:
                canvas.text(MARGIN + 12, y, line, 10.5, 400, svg.MUTED)
                y += 13
    canvas.add(
        f'<rect x="{MARGIN}" y="{start_y:.1f}" width="{width - MARGIN:.1f}" '
        f'height="{bands[-1][2] if bands else 0:.1f}" '
        f'fill="none" stroke="#e2e8f0" rx="2"/>'
        if bands
        else ""
    )
    boxes = {nid: (p.x, p.y, p.w, p.h) for nid, p in placed.items()}
    links = [lk for lk in flow.links if lk.src in placed and lk.dst in placed and lk.src != lk.dst]
    # ports: spread the links leaving / entering a side so they do not stack on one point
    outgoing: dict[str, list[Link]] = {}
    incoming: dict[str, list[Link]] = {}
    for link in links:
        if placed[link.dst].rank > placed[link.src].rank:
            outgoing.setdefault(link.src, []).append(link)
            incoming.setdefault(link.dst, []).append(link)

    def port(node_id: str, link: Link, side: str) -> float:
        group = (outgoing if side == "out" else incoming).get(node_id, [])
        other = (lambda lk: placed[lk.dst].cy) if side == "out" else (lambda lk: placed[lk.src].cy)
        group = sorted(group, key=lambda lk: (other(lk), lk.label))
        item = placed[node_id]
        if len(group) <= 1:
            return item.cy
        index = group.index(link)
        span = item.h * 0.56
        return item.y + item.h * 0.22 + span * index / (len(group) - 1)

    labels: list[tuple[float, float, float, float]] = list(boxes.values())
    paths: list[str] = []
    pills: list[tuple[float, float, list[str], str]] = []
    back_offset = 0
    bottom_all = max((p.y + p.h for p in placed.values()), default=start_y)
    for link in sorted(links, key=lambda lk: (placed[lk.src].rank, placed[lk.src].cy, placed[lk.dst].cy)):
        s, d = placed[link.src], placed[link.dst]
        stroke, dash, width_px = svg.line_style(link.status, link.style)
        marker = (
            f"{'o' if link.style == 'async' else 'a'}-{link.status if link.status in svg.STATUS else CONTEXT}"
        )
        label_lines = svg.wrap(link.label, LABEL_WRAP, 12, max_lines=2) if link.label else []
        if d.rank > s.rank:
            p0 = (s.x + s.w, port(link.src, link, "out"))
            p3 = (d.x - 2, port(link.dst, link, "in"))
            dx = max(40.0, (p3[0] - p0[0]) / 2)
            p1, p2 = (p0[0] + dx, p0[1]), (p3[0] - dx, p3[1])
            samples = [_bezier(p0, p1, p2, p3, t / 24) for t in range(2, 23)]
            others = [b for nid, b in boxes.items() if nid not in (link.src, link.dst)]
            if _hits(samples, others):
                d_path, label_at = _routed(p0, p3, s, d, placed, others)
            else:
                d_path = (
                    f"M{p0[0]:.1f},{p0[1]:.1f} C{p1[0]:.1f},{p1[1]:.1f} "
                    f"{p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"
                )
                gap_mid = s.x + s.w + min(80.0, (p3[0] - p0[0]) / 2)
                t = _t_at_x(p0, p1, p2, p3, gap_mid)
                label_at = _bezier(p0, p1, p2, p3, t)
        else:
            back_offset += 1
            if s.rank == d.rank and abs(s.cx - d.cx) < 1:
                xr = max(s.x + s.w, d.x + d.w) + 34 + 10 * back_offset
                p0, p3 = (s.x + s.w, s.cy), (d.x + d.w + 2, d.cy)
                d_path = (
                    f"M{p0[0]:.1f},{p0[1]:.1f} C{xr:.1f},{p0[1]:.1f} "
                    f"{xr:.1f},{p3[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"
                )
                label_at = (xr - 6, (p0[1] + p3[1]) / 2)
            else:
                low = max(s.y + s.h, d.y + d.h) + 26 + 12 * back_offset
                low = min(low, bottom_all + 26 + 12 * back_offset)
                p0, p3 = (s.cx, s.y + s.h), (d.cx, d.y + d.h + 2)
                d_path = (
                    f"M{p0[0]:.1f},{p0[1]:.1f} C{p0[0]:.1f},{low:.1f} "
                    f"{p3[0]:.1f},{low:.1f} {p3[0]:.1f},{p3[1]:.1f}"
                )
                label_at = ((p0[0] + p3[0]) / 2, low - 6)
        paths.append(
            f'<path d="{d_path}" fill="none" stroke="{stroke}" stroke-width="{width_px}"{dash} '
            f'marker-end="url(#{marker})"/>'
        )
        if label_lines:
            pills.append((label_at[0], label_at[1], label_lines, link.status))
    for item in paths:
        canvas.add(item)
    for item in placed.values():
        node = item.node
        canvas.grow(item.x + item.w, item.y + item.h)
        accent = svg.ACCENT.get(_role(node)) if node.status == CONTEXT and node.kind == "component" else None
        svg.box(canvas, item.x, item.y, item.w, item.h, item.lines, node.sub, node.status, node.kind, accent)
    for cx, cy, lines, status in pills:
        w = max(svg.text_width(t, 12) for t in lines) + 12
        h = len(lines) * 14 + 6
        rect = (cx - w / 2, cy - h / 2, w, h)
        for step in (0, 1, -1, 2, -2, 3, -3, 4, -4):
            trial = (rect[0], rect[1] + step * (h + 4), w, h)
            if not any(_overlap(trial, other) for other in labels):
                rect = trial
                break
        labels.append(rect)
        svg.pill(canvas, rect[0] + w / 2, rect[1] + h / 2, lines, status)
        canvas.grow(rect[0] + w, rect[1] + h)
    canvas.grow(width, (bands[-1][2] + start_y) if bands else start_y)
    y = canvas.height + 18
    present = sorted({n.status for n in flow.nodes} | {lk.status for lk in flow.links}, key=svg_order)
    styles = []
    if any(lk.style == "sync" for lk in flow.links):
        styles.append(("sync", "call"))
    if any(lk.style == "async" for lk in flow.links):
        styles.append(("async", "event / message"))
    if any(lk.style == "data" for lk in flow.links):
        styles.append(("data", "reads / writes data"))
    y = svg.legend(canvas, MARGIN, y, present, styles)
    svg.caption(canvas, MARGIN, y + 8, flow.caption, max(400.0, canvas.width - 2 * MARGIN))
    return canvas.render(flow.title)


def svg_order(status: str) -> int:
    return ("new", "changed", "removed", "impacted", "touched", "context").index(status)


def _role(node: Node) -> str:
    sub = node.sub.lower()
    if any(word in sub for word in ("controller", "listener", "screen", "job", "scheduled")):
        return "entry"
    if any(word in sub for word in ("repository", "client", "publisher", "adapter", "store")):
        return "adapter"
    return "app"


def _t_at_x(p0, p1, p2, p3, x: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if _bezier(p0, p1, p2, p3, mid)[0] < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _routed(
    p0, p3, s: _Placed, d: _Placed, placed: dict[str, _Placed], others
) -> tuple[str, tuple[float, float]]:
    """A smooth path through the columns between s and d at heights where no box is in the way."""
    columns: dict[int, list[_Placed]] = {}
    for item in placed.values():
        columns.setdefault(item.rank, []).append(item)
    points = [p0]
    for r in range(s.rank + 1, d.rank):
        members = sorted(columns.get(r, []), key=lambda p: p.y)
        if not members:
            continue
        x_left = min(p.x for p in members) - 10
        x_right = max(p.x + p.w for p in members) + 10
        frac = (r - s.rank) / (d.rank - s.rank)
        want = p0[1] + (p3[1] - p0[1]) * frac
        candidates = [members[0].y - 18, members[-1].y + members[-1].h + 18]
        for a, b in zip(members, members[1:], strict=False):
            if b.y - (a.y + a.h) > 16:
                candidates.append((a.y + a.h + b.y) / 2)
        free = [c for c in candidates if not _hits([(x_left + 12, c), ((x_left + x_right) / 2, c)], others)]
        y = min(free or candidates, key=lambda c: abs(c - want))
        points += [(x_left, y), (x_right, y)]
    points.append(p3)
    parts = [f"M{points[0][0]:.1f},{points[0][1]:.1f}"]
    for a, b in zip(points, points[1:], strict=False):
        if abs(a[1] - b[1]) < 0.5:
            parts.append(f"L{b[0]:.1f},{b[1]:.1f}")
            continue
        dx = max(24.0, (b[0] - a[0]) / 2)
        parts.append(f"C{a[0] + dx:.1f},{a[1]:.1f} {b[0] - dx:.1f},{b[1]:.1f} {b[0]:.1f},{b[1]:.1f}")
    first = points[1] if len(points) > 1 else p3
    label = ((points[0][0] + first[0]) / 2, (points[0][1] + first[1]) / 2)
    return " ".join(parts), label
