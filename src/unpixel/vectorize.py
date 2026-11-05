"""Turn a class map into SVG paths, one compound path per outer shape."""

from __future__ import annotations

import numpy as np
import potrace
from scipy import ndimage as ni

from .color import to_hex

OVERLAP = 8  # working pixels a lower layer extends beneath the layers above it
OVERLAP_MARGIN = 2  # stay this far inside the artwork, so a lower color never peeks out around an upper one


def _trace_layer(mask: np.ndarray, turd: int, scale: float, decimals: int) -> list[str]:
    """Trace each connected shape in its own crop.

    potracer scans the whole bitmap once per outline, so tracing a large bitmap with thousands
    of outlines gets very slow. Crops keep each scan small. A shape inside a hole of another is
    its own connected shape, so holes and outer outlines stay correctly paired.
    """
    fmt = f"%.{decimals}f"

    def num(v: float) -> str:
        return (fmt % (v / scale)).rstrip("0").rstrip(".") if decimals else fmt % (v / scale)

    parts, _ = ni.label(mask, structure=np.ones((3, 3), bool))
    shapes = []
    for index, box in enumerate(ni.find_objects(parts), start=1):
        ys, xs = box
        crop = np.pad(parts[box] == index, 2)
        if crop.sum() < turd:
            continue
        x0, y0 = xs.start - 2, ys.start - 2

        def pt(p) -> str:
            return f"{num(p.x + x0)} {num(p.y + y0)}"

        def path(curve) -> str:
            pieces = [f"M{pt(curve.start_point)}"]
            for seg in curve.segments:
                if seg.is_corner:
                    pieces.append(f"L{pt(seg.c)}L{pt(seg.end_point)}")
                else:
                    pieces.append(f"C{pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
            return "".join(pieces) + "Z"

        curves = potrace.Bitmap(~crop).trace(turdsize=turd, alphamax=1.15, opticurve=True, opttolerance=1.0)
        if curves:
            shapes.append((ys.start // max(1, mask.shape[0] // 20), xs.start, "".join(path(c) for c in curves)))
    shapes.sort(key=lambda item: item[:2])
    return [item[2] for item in shapes]


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
