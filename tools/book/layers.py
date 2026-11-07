"""A demonstration for chapter 8: the general technique of tracing each color alone with potrace.

unpixel does not work this way. This traces its class map per color, so the book can show what shared walls change on
the same regions and colors. It is the only thing in the book that needs potrace.
"""

from __future__ import annotations

import numpy as np
import potrace
from scipy import ndimage as ni

from unpixel.color import to_hex

OVERLAP = 8  # map pixels a lower layer extends beneath the layers above it
OVERLAP_MARGIN = 2  # stay this far inside the artwork, so a lower color never peeks out around an upper one
SMOOTH_SIGMA = 2.0
TURD = 30


def smooth(labels: np.ndarray, classes: list[int]) -> np.ndarray:
    """Soften the regions' outlines: each pixel takes its strongest class, which leaves no gaps or overlaps."""
    best = np.full(labels.shape, -1.0, dtype=np.float32)
    out = labels.copy()
    for cls in classes:
        soft = ni.gaussian_filter((labels == cls).astype(np.float32), SMOOTH_SIGMA)
        hit = soft > best
        out[hit] = cls
        best[hit] = soft[hit]
    return out


def trace_mask(mask: np.ndarray, scale: float) -> list[str]:
    """Each connected shape in its own crop, as compound SVG path data."""

    def num(v: float) -> str:
        return f"{v / scale:.2f}".rstrip("0").rstrip(".")

    parts, _ = ni.label(mask, structure=np.ones((3, 3), bool))
    shapes = []
    for index, box in enumerate(ni.find_objects(parts), start=1):
        ys, xs = box
        crop = np.pad(parts[box] == index, 2)
        if crop.sum() < TURD:
            continue
        x0, y0 = xs.start - 2, ys.start - 2

        def pt(p) -> str:
            return f"{num(p.x + x0)} {num(p.y + y0)}"

        def path(curve) -> str:
            pieces = [f"M{pt(curve.start_point)}"]
            for seg in curve.segments:
                pieces.append(f"L{pt(seg.c)}L{pt(seg.end_point)}" if seg.is_corner else f"C{pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
            return "".join(pieces) + "Z"

        curves = potrace.Bitmap(~crop).trace(turdsize=TURD, alphamax=1.15, opticurve=True, opttolerance=1.0)
        if curves:
            shapes.append("".join(path(c) for c in curves))
    return shapes


def per_color_svg(result, width: int, height: int, underlap: bool) -> str:
    """Largest color at the bottom. With `underlap`, each lower layer also runs on beneath the layers above it."""
    colors = result.colors
    labels = np.where(result.labels >= len(colors), -1, result.labels).astype(np.int16)
    labels = smooth(labels, sorted(int(c) for c in np.unique(labels)))
    scale = labels.shape[1] / width
    areas = [int((labels == i).sum()) for i in range(len(colors))]
    order = sorted(range(len(colors)), key=lambda i: -areas[i])
    rank_of = np.full(len(colors) + 1, -1, dtype=np.int16)  # index -1, the transparent class, stays -1
    for position, cls in enumerate(order):
        rank_of[cls] = position
    ranks = rank_of[labels]
    groups = []
    for position, cls in enumerate(order):
        mask = ranks == position
        if underlap and position + 1 < len(order):
            core = ni.binary_erosion(ranks >= position, iterations=OVERLAP_MARGIN) & (ranks > position)
            mask = mask | (ni.binary_dilation(mask, iterations=OVERLAP) & core)
        paths = trace_mask(mask, scale)
        if paths:
            body = "".join(f'<path d="{d}"/>\n' for d in paths)
            groups.append(f'<g id="color-{position + 1}" fill="{to_hex(colors[cls])}" fill-rule="evenodd" stroke="none">\n{body}</g>\n')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">\n{"".join(groups)}</svg>\n'
