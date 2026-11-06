"""Write a planar map as SVG. Each region is one path, with its holes, and its walls are the shared arcs."""

from __future__ import annotations

import numpy as np

from ..color import to_hex


TRAP_TOLERANCE = 0.25  # source pixels; the stroke reaches a pixel to each side, so this still covers the wall


def _num(value: float) -> str:
    text = f"{value:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _segments_text(points: np.ndarray, kinds: np.ndarray) -> str:
    """Curves after the pen is at the first point. Numbers rounded here are the same on both sides of a wall."""
    parts = []
    values = points.tolist()
    for seg, kind in zip(values, kinds.tolist()):
        (_, _), p1, p2, p3 = seg
        if kind:
            parts.append(f"C{_num(p1[0])} {_num(p1[1])} {_num(p2[0])} {_num(p2[1])} {_num(p3[0])} {_num(p3[1])}")
        else:
            parts.append(f"L{_num(p3[0])} {_num(p3[1])}")
    return "".join(parts)


def _reverse(points: np.ndarray) -> np.ndarray:
    return points[::-1, ::-1]


def _trim(points: np.ndarray, kinds: np.ndarray, at_start: bool, at_end: bool, by: float):
    """Shorten a run of segments at its ends, for a stroke that must not poke past the artwork's edge."""
    pts = points.copy()
    if at_start and len(pts):
        chord = float(np.hypot(*(pts[0, 3] - pts[0, 0]))) or 1.0
        t = min(0.5, by / chord)
        pts[0] = _split(pts[0], t)[1]
    if at_end and len(pts):
        chord = float(np.hypot(*(pts[-1, 3] - pts[-1, 0]))) or 1.0
        t = min(0.5, by / chord)
        pts[-1] = _split(pts[-1], 1.0 - t)[0]
    return pts


def _split(seg: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
    a = seg[0] + (seg[1] - seg[0]) * t
    b = seg[1] + (seg[2] - seg[1]) * t
    c = seg[2] + (seg[3] - seg[2]) * t
    d = a + (b - a) * t
    e = b + (c - b) * t
    f = d + (e - d) * t
    return np.stack([seg[0], a, d, f]), np.stack([f, e, c, seg[3]])


def _polyline(points: np.ndarray, kinds: np.ndarray, tolerance: float) -> str:
    """A run of segments as few straight lines, for a trap stroke, where nobody sees the path itself."""
    if len(points) == 0:
        return ""
    sample = [points[0, 0]]
    for seg, kind in zip(points, kinds.tolist()):
        if kind:
            # Fine enough that the samples themselves stay within tolerance of the curve.
            steps = max(4, int(np.ceil(float(np.hypot(*(seg[3] - seg[0]))) / 3.0)))
            for t in (i / steps for i in range(1, steps)):
                u = 1.0 - t
                sample.append(u**3 * seg[0] + 3 * u * u * t * seg[1] + 3 * u * t * t * seg[2] + t**3 * seg[3])
        sample.append(seg[3])
    xy = np.array(sample)
    keep = [0, len(xy) - 1]
    stack = [(0, len(xy) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        chord = xy[b] - xy[a]
        length = float(np.hypot(*chord))
        rel = xy[a + 1 : b] - xy[a]
        if length < 1e-6:  # a closed loop: measure from its start
            d = np.hypot(rel[:, 0], rel[:, 1])
        else:
            d = np.abs(rel[:, 0] * chord[1] - rel[:, 1] * chord[0]) / length
        i = int(np.argmax(d))
        if d[i] > tolerance:
            at = a + 1 + i
            keep.append(at)
            stack += [(a, at), (at, b)]
    keep.sort()
    first = xy[keep[0]]
    return f"M{first[0]:.1f} {first[1]:.1f}" + "".join(f"L{xy[k][0]:.1f} {xy[k][1]:.1f}" for k in keep[1:])


def write_svg(
    pmap,
    fitted,
    arc_chain: list[tuple[int, int]],
    region_class: np.ndarray,
    region_stats: tuple[np.ndarray, np.ndarray] | None,
    colors: list[tuple[int, int, int]],
    width: int,
    height: int,
    title: str,
    z_of_class: np.ndarray,
    under: float = 0.0,
) -> tuple[str, list[dict]]:
    """Regions drawn from the bottom class up, each wall the same curve on both sides.

    With `under` at 0, regions only abut (cutout), and a renderer may show a hairline along each wall. Above
    0, the lower color of a wall also strokes that wall, right after its fills, so the upper region lands on
    its own color: two sides of an antialiased wall cannot let anything through.
    """
    arcs = pmap.arcs
    thickness = 2.0 * region_stats[0] / np.maximum(region_stats[1], 1.0) if region_stats is not None else None

    forward: dict[int, str] = {}
    backward_text: dict[int, str] = {}
    start_of: dict[int, str] = {}
    end_of: dict[int, str] = {}

    def arc_points(i: int) -> tuple[np.ndarray, np.ndarray]:
        a, b = arc_chain[i]
        return fitted.points[a:b], fitted.kinds[a:b]

    def text(i: int, backward: bool) -> str:
        cache = backward_text if backward else forward
        got = cache.get(i)
        if got is None:
            pts, kinds = arc_points(i)
            got = _segments_text(_reverse(pts), kinds[::-1]) if backward else _segments_text(pts, kinds)
            cache[i] = got
        return got

    def ends(i: int) -> tuple[str, str]:
        got = start_of.get(i)
        if got is None:
            pts, _ = arc_points(i)
            got = f"{_num(pts[0, 0, 0])} {_num(pts[0, 0, 1])}"
            start_of[i] = got
            end_of[i] = f"{_num(pts[-1, 3, 0])} {_num(pts[-1, 3, 1])}"
        return got, end_of[i]

    # The lowest thing at each junction, -1 for the unpainted outside. A stroke's square end pokes over it.
    lowest: dict[int, int] = {}
    for arc in arcs:
        if arc.start < 0:
            continue
        here = min(-1 if r == 0 else int(z_of_class[region_class[r]]) for r in (arc.left, arc.right))
        for v in (arc.start, arc.end):
            lowest[v] = min(lowest.get(v, 1 << 30), here)

    # Walls each lower color strokes, by stroke width.
    traps: dict[int, dict[float, list[tuple[str, int]]]] = {}
    if under > 0:
        for i, arc in enumerate(arcs):
            if arc.left == 0 or arc.right == 0:
                continue
            ca, cb = int(region_class[arc.left]), int(region_class[arc.right])
            low, high = (arc.left, arc.right) if z_of_class[ca] < z_of_class[cb] else (arc.right, arc.left)
            reach = under if thickness is None else min(under, 0.5 * float(thickness[high]))
            # Wide enough for the stroke's own simplification; few stroke widths, so few paths.
            width_key = round((max(reach, 0.2) + TRAP_TOLERANCE) * 2 * 5) / 5
            pts, kinds = arc_points(i)
            if len(pts) == 0:
                continue
            # A stroke's square end must not poke past its wall, over the artwork's edge or a third color.
            z_low = int(z_of_class[region_class[low]])
            cut_start = arc.start >= 0 and lowest[arc.start] < z_low
            cut_end = arc.end >= 0 and lowest[arc.end] < z_low
            pts = _trim(pts, kinds, cut_start, cut_end, width_key / 2)
            d = _polyline(pts, kinds, TRAP_TOLERANCE)
            traps.setdefault(int(region_class[low]), {}).setdefault(width_key, []).append((d, low))

    by_class: dict[int, list[int]] = {}
    for region in pmap.loops:
        by_class.setdefault(int(region_class[region]), []).append(region)
    order = sorted(by_class, key=lambda c: z_of_class[c])
    groups, summary = [], []
    for position, cls in enumerate(order):
        body = []
        regions = sorted(by_class[cls])
        place = {region: at for at, region in enumerate(regions)}
        for region in regions:
            d = []
            for loop in pmap.loops[region]:
                first = True
                for i, backward in loop:
                    a, b = ends(i)
                    if first:
                        d.append(f"M{b if backward else a}")
                        first = False
                    d.append(text(i, backward))
                d.append("Z")
            body.append('<path d="' + "".join(d) + '"/>\n')
        for width_key, walls in sorted(traps.get(cls, {}).items()):
            # Which shape of this group each wall of the stroke belongs to, for a tool that recolors one shape.
            owners = " ".join(str(place[region]) for _, region in walls)
            body.append(
                f'<path class="trap" fill="none" stroke="{to_hex(colors[cls])}" stroke-width="{_num(width_key)}" '
                f'stroke-linejoin="round" data-shapes="{owners}" d="{"".join(d for d, _ in walls)}"/>\n'
            )
        name = f"color-{position + 1}"
        color = to_hex(colors[cls])
        groups.append(f'<g id="{name}" fill="{color}" fill-rule="evenodd" stroke="none">\n{"".join(body)}</g>\n')
        summary.append({"layer": name, "color": color, "shapes": len(by_class[cls])})
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">\n'
        f"<title>{title}</title>\n{''.join(groups)}</svg>\n"
    )
    return svg, summary
