"""Verify the written SVG against the segmentation and build the visual report."""

from __future__ import annotations

import base64
import html
import io

import numpy as np
from PIL import Image
from scipy import ndimage as ni

from .color import delta_e, srgb_to_lab, to_hex
from .render import composite, render_svg

TEST_BACKGROUNDS = [(90, 170, 110), (255, 0, 255), (0, 170, 200), (255, 196, 80), (120, 120, 120)]


def contrast_background(colors) -> tuple[int, int, int]:
    """Pick the check color farthest from every artwork color, so halos stand out."""
    if not colors:
        return TEST_BACKGROUNDS[0]
    labs = srgb_to_lab(np.array(colors, dtype=np.float32))
    scores = [float(delta_e(labs, srgb_to_lab(np.array(c, dtype=np.float32))).min()) for c in TEST_BACKGROUNDS]
    return TEST_BACKGROUNDS[int(np.argmax(scores))]


def _down(mask: np.ndarray, shape) -> np.ndarray:
    if mask.shape == shape:
        return mask
    ys = (np.arange(shape[0]) * mask.shape[0] / shape[0]).astype(int)
    xs = (np.arange(shape[1]) * mask.shape[1] / shape[1]).astype(int)
    return mask[np.ix_(ys, xs)]


def _classes(rgba: np.ndarray, colors) -> np.ndarray:
    out = np.full(rgba.shape[:2], -1, dtype=np.int16)
    for i, color in enumerate(colors):
        out[(rgba[..., :3] == np.array(color, dtype=np.uint8)).all(-1) & (rgba[..., 3] > 128)] = i
    return out


def verify(svg: str, seg, width: int, height: int) -> tuple[dict, np.ndarray, list[tuple[int, int, int, int]]]:
    """Measure the written SVG against the unsmoothed segmentation. Returns metrics, render, hotspots."""
    rgba = render_svg(svg, width, height)
    drawn = _classes(rgba, seg.colors)
    shape = drawn.shape
    raw = _down(seg.raw_labels, shape)
    flat = _down(seg.flat, shape)
    wrong = drawn != raw
    tolerance = max(2, int(round(max(shape) / 2500)))  # differences thinner than this are ordinary edge wobble
    thick = ni.binary_erosion(wrong, iterations=tolerance)
    parts, count = ni.label(thick)
    hotspots: list[tuple[int, int, int, int]] = []
    if count:
        sizes = np.bincount(parts.ravel())[1:]
        boxes = ni.find_objects(parts)
        for i in np.argsort(-sizes)[:4]:
            ys, xs = boxes[i]
            hotspots.append((xs.start, ys.start, xs.stop, ys.stop))
    expected_clear = raw == -1
    deep_clear = ni.binary_erosion(expected_clear, iterations=4 + tolerance)
    deep_solid = ni.binary_erosion(~expected_clear, iterations=4 + tolerance)
    metrics = {
        "transparent_percent": round(100.0 * float((rgba[..., 3] == 0).mean()), 2),
        "expected_transparent_percent": round(100.0 * float(expected_clear.mean()), 2),
        "opaque_pixels_in_background": int((rgba[..., 3][deep_clear] > 5).sum()),
        "transparent_pixels_in_artwork": int((rgba[..., 3][deep_solid] < 250).sum()),
        "edge_difference_percent": round(100.0 * float(wrong.sum()) / max(1, int((raw != -1).sum())), 2),
        "large_difference_pixels": int(thick.sum()),
        "flat_area_mismatch_percent": round(100.0 * float((wrong & flat).sum()) / max(1, int(flat.sum())), 3),
    }
    return metrics, rgba, hotspots


def _detail_boxes(rgb: np.ndarray, count: int = 4) -> list[tuple[int, int, int, int]]:
    """Pick the busiest areas of the source: where fine detail is most likely to suffer."""
    h, w = rgb.shape[:2]
    gray = rgb.astype(np.float32).mean(-1)
    gy, gx = np.gradient(gray)
    energy = np.hypot(gx, gy) > 12
    side = max(32, min(w, h) // 4)
    density = ni.uniform_filter(energy.astype(np.float32), side, mode="constant")
    boxes = []
    for _ in range(count):
        y, x = np.unravel_index(int(density.argmax()), density.shape)
        if density[y, x] <= 0:
            break
        x0, y0 = max(0, int(x) - side // 2), max(0, int(y) - side // 2)
        x1, y1 = min(w, x0 + side), min(h, y0 + side)
        boxes.append((x0, y0, x1, y1))
        density[max(0, y0 - side // 2) : y1 + side // 2, max(0, x0 - side // 2) : x1 + side // 2] = 0
    return boxes


def _png_uri(image: Image.Image, max_side: int = 900) -> str:
    ratio = max(image.size) / max_side
    if ratio > 1:
        image = image.resize((int(image.width / ratio), int(image.height / ratio)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def write_preview(svg, width, height, background, path) -> None:
    """Write the result on the check color, with smooth edges, at most 2000 px wide."""
    target = min(2000, max(width, 1000))
    scale = 2.0 * target / width
    rgba = render_svg(svg, width, height, scale)
    image = composite(rgba, background).resize((target, int(round(height * target / width))), Image.LANCZOS)
    image.save(path, optimize=True)


def write_report(source_rgb, svg, seg, metrics, hotspots, layers, background, input_name, path) -> None:
    height, width = source_rgb.shape[:2]
    zoom = float(np.clip(1800 / width, 1.0, 3.0))
    rgba = render_svg(svg, width, height, zoom)
    result = composite(rgba, background)
    source = Image.fromarray(source_rgb)
    rows = []
    sections = [("Largest differences", hotspots[:2], True), ("Busiest detail", _detail_boxes(source_rgb), False)]
    for title, boxes, pad in sections:
        for box in boxes:
            x0, y0, x1, y1 = box
            if pad:
                margin = max(80, (x1 - x0), (y1 - y0))
                x0, y0, x1, y1 = max(0, x0 - margin), max(0, y0 - margin), min(width, x1 + margin), min(height, y1 + margin)
            left = _png_uri(source.crop((x0, y0, x1, y1)), 760)
            right = _png_uri(result.crop(tuple(int(v * zoom) for v in (x0, y0, x1, y1))), 760)
            rows.append(
                f'<h3>{html.escape(title)} <small>x {x0}–{x1}, y {y0}–{y1}</small></h3>'
                f'<div class="pair"><img alt="original" src="{left}"><img alt="result" src="{right}"></div>'
            )
    swatches = "".join(
        f'<li><span style="background:{l["color"]}"></span>{l["color"]} · {l["shapes"]} shapes · {l["area_percent"]}%</li>'
        for l in layers
    )
    metric_rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in metrics.items())
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in seg.warnings) or "<li>None</li>"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>unpixel report: {html.escape(input_name)}</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:1560px;padding:16px;background:#fff;color:#222}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} img{{width:100%;height:auto;display:block;border:1px solid #ccc}}
table{{border-collapse:collapse}} td{{border:1px solid #ddd;padding:3px 10px}} small{{font-weight:normal;color:#666}}
ul.pal{{list-style:none;padding:0}} ul.pal span{{display:inline-block;width:1em;height:1em;margin-right:.5em;border:1px solid #888;vertical-align:-2px}}
</style></head><body>
<h1>{html.escape(input_name)}</h1>
<p>Left: original. Right: the SVG on a check color, where any halo or gap is visible.</p>
<h2>Full image</h2><div class="pair"><img alt="original" src="{_png_uri(source)}"><img alt="result" src="{_png_uri(result)}"></div>
<h2>Layers (bottom to top)</h2><ul class="pal">{swatches}</ul>
<h2>Warnings</h2><ul>{warnings}</ul>
<h2>Metrics</h2><table>{metric_rows}</table>
<h2>Close-ups</h2><p>Metrics miss broken thin lines and clogged detail. Check these by eye.</p>{''.join(rows)}
</body></html>"""
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document)
