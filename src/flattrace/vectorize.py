"""Turn a class map into SVG paths, one compound path per outer shape."""

from __future__ import annotations

import numpy as np
import potrace
from scipy import ndimage as ni

from .color import to_hex

OVERLAP = 8  # working pixels a lower layer extends beneath the layers above it
OVERLAP_MARGIN = 2  # stay this far inside the artwork, so a lower color never peeks out around an upper one


def _control_polygon(curve) -> np.ndarray:
    points = [curve.start_point]
    for seg in curve.segments:
        points += [seg.c, seg.end_point] if seg.is_corner else [seg.c1, seg.c2, seg.end_point]
    return np.array([(p.x, p.y) for p in points])


def _area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2


def _inside(point: np.ndarray, poly: np.ndarray) -> bool:
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    crossing = (y > point[1]) != (y2 > point[1])
    xs = x[crossing] + (point[1] - y[crossing]) * (x2[crossing] - x[crossing]) / (y2[crossing] - y[crossing])
    return np.count_nonzero(point[0] < xs) % 2 == 1


def _trace_layer(mask: np.ndarray, turd: int, scale: float, decimals: int) -> list[str]:
    curves = potrace.Bitmap(~mask).trace(turdsize=turd, alphamax=1.15, opticurve=True, opttolerance=1.0)
    fmt = f"%.{decimals}f"

    def num(v: float) -> str:
        return (fmt % (v / scale)).rstrip("0").rstrip(".") if decimals else fmt % (v / scale)

    def pt(p) -> str:
        return f"{num(p.x)} {num(p.y)}"

    def path(curve) -> str:
        parts = [f"M{pt(curve.start_point)}"]
        for seg in curve.segments:
            if seg.is_corner:
                parts.append(f"L{pt(seg.c)}L{pt(seg.end_point)}")
            else:
                parts.append(f"C{pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
        return "".join(parts) + "Z"

    items = [(c, _control_polygon(c)) for c in curves]
    outers = [
        {"curve": c, "poly": p, "area": _area(p), "low": p.min(0), "high": p.max(0), "holes": []}
        for c, p in items
        if c._path.sign
    ]
    for curve, poly in items:
        if curve._path.sign:
            continue
        point = poly[0]
        best = None
        for outer in outers:
            if (outer["low"] <= point).all() and (point <= outer["high"]).all() and _inside(point, outer["poly"]):
                if best is None or outer["area"] < best["area"]:
                    best = outer
        if best is not None:
            best["holes"].append(curve)
    outers.sort(key=lambda o: (o["low"][1] // (mask.shape[0] / 20), o["low"][0]))
    return [path(o["curve"]) + "".join(path(h) for h in o["holes"]) for o in outers]


def build_svg(labels, colors, width, height, layers_mode, speck_area, title) -> tuple[str, list[dict]]:
    scale = labels.shape[1] / width
    decimals = 2 if width < 3000 else 1
    areas = [int((labels == i).sum()) for i in range(len(colors))]
    order = sorted(range(len(colors)), key=lambda i: -areas[i])  # largest color at the bottom
    groups = []
    summary = []
    for position, cls in enumerate(order):
        mask = labels == cls
        if layers_mode == "stacked" and position + 1 < len(order):
            above = np.isin(labels, order[position + 1 :])
            core = ni.binary_erosion(above | mask, iterations=OVERLAP_MARGIN) & above
            mask = mask | (ni.binary_dilation(mask, iterations=OVERLAP) & core)
        paths = _trace_layer(mask, speck_area, scale, decimals)
        name = f"color-{position + 1}"
        color = to_hex(colors[cls])
        body = "".join(f'<path d="{d}"/>\n' for d in paths)
        groups.append(f'<g id="{name}" fill="{color}" fill-rule="evenodd" stroke="none">\n{body}</g>\n')
        summary.append({"layer": name, "color": color, "shapes": len(paths),
                        "area_percent": round(100.0 * areas[cls] / labels.size, 2)})
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">\n'
        f"<title>{title}</title>\n{''.join(groups)}</svg>\n"
    )
    return svg, summary
