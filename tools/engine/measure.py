#!/usr/bin/env python
"""Measure every <image>-<variant>.svg in a directory and write measurements.json and a text table.

usage: measure.py INPUT_DIR OUTPUT_DIR [--scales 1,0.73,2]

Numbers come from the written SVG and from what rsvg-convert renders of it, not from internal state.
Boundary numbers count fills only, without the trap strokes, and skip nothing else. A turn is the change of direction at a node,
in degrees, and "sharp" is a turn above 30 degrees. Segments along the image frame are not counted.
"""
import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ni

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import render_png  # noqa: E402

from unpixel.color import srgb_to_lab  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
_TOKEN = re.compile(r"[MLCZ]|-?\d+(?:\.\d+)?")
_GROUP = re.compile(r'<g id="[^"]*" fill="(#[0-9A-Fa-f]{6})"[^>]*>(.*?)</g>', re.S)
_PATH = re.compile(r"<path ([^>]*)/?>")
_D = re.compile(r'\bd="([^"]+)"')


def _bezier_length(p0, p1, p2, p3, steps=12):
    t = np.linspace(0, 1, steps + 1)[:, None]
    q = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3
    return float(np.hypot(*(q[1:] - q[:-1]).T).sum())


def analyze_paths(svg: str, width: int, height: int, junctions=()) -> dict:
    """Paths, nodes, boundary length and turning angles from the SVG text.

    `junctions`, where known, are where three or more regions meet. A region's outline turns there by
    construction, and the wall itself does not; those turns are counted apart from turns along a wall.
    """
    at_junction = {(round(float(x), 2), round(float(y), 2)) for x, y in junctions}
    junction_turns: list[float] = []
    paths = traps = nodes = 0
    length = 0.0
    turns: list[float] = []
    per_color: dict[str, int] = {}
    for color, body in _GROUP.findall(svg):
        for attrs in _PATH.findall(body):
            d = _D.search(attrs).group(1)
            if 'class="trap"' in attrs:
                traps += 1
                continue
            paths += 1
            per_color[color] = per_color.get(color, 0) + 1
            tokens = _TOKEN.findall(d)
            i = 0
            pos = np.zeros(2)
            ins: list = []
            outs: list = []
            nodes_at: list = []
            lens: list = []
            starts = pos
            first_out = None

            def close():
                n = len(ins)
                for k in range(n):
                    a, b = ins[k], outs[(k + 1) % n]
                    if a is None or b is None:
                        continue
                    na, nb = float(np.hypot(*a)), float(np.hypot(*b))
                    if na < 1e-6 or nb < 1e-6:
                        continue
                    cos = float(np.clip(np.dot(a, b) / (na * nb), -1, 1))
                    angle = float(np.degrees(np.arccos(cos)))
                    where = tuple(round(float(v), 2) for v in nodes_at[k])
                    if where in at_junction:
                        junction_turns.append(angle)
                    else:
                        turns.append(angle)

            while i < len(tokens):
                t = tokens[i]
                i += 1
                if t == "M":
                    pos = np.array([float(tokens[i]), float(tokens[i + 1])])
                    starts = pos
                    i += 2
                    ins, outs, lens, nodes_at = [], [], [], []
                elif t == "L" or t == "C":
                    if t == "L":
                        q = np.array([float(tokens[i]), float(tokens[i + 1])])
                        i += 2
                        v = q - pos
                        seg_in, seg_out, seg_len = v, v, float(np.hypot(*v))
                    else:
                        vals = np.array([float(v) for v in tokens[i : i + 6]]).reshape(3, 2)
                        i += 6
                        q = vals[2]
                        out = vals[0] - pos
                        if np.hypot(*out) < 1e-6:
                            out = vals[1] - pos
                        inn = q - vals[1]
                        if np.hypot(*inn) < 1e-6:
                            inn = q - vals[0]
                        seg_in, seg_out, seg_len = inn, out, _bezier_length(pos, vals[0], vals[1], q)
                    on_frame = (
                        (pos[0] <= 0 and q[0] <= 0)
                        or (pos[1] <= 0 and q[1] <= 0)
                        or (pos[0] >= width and q[0] >= width)
                        or (pos[1] >= height and q[1] >= height)
                    )
                    nodes_at.append(q)
                    if on_frame:
                        ins.append(None)
                        outs.append(None)
                    else:
                        ins.append(seg_in)
                        outs.append(seg_out)
                        nodes += 1
                        length += seg_len
                    pos = q
                elif t == "Z":
                    if ins:
                        close()
                    ins, outs, nodes_at = [], [], []
                    pos = starts
    turns_a = np.array(turns) if turns else np.zeros(1)
    return {
        "paths": paths,
        "trap_paths": traps,
        "nodes": nodes,
        "boundary_px": round(length, 1),
        "nodes_per_100px": round(100.0 * nodes / max(length, 1.0), 2),
        "sharp30_share": round(float((turns_a > 30).mean()), 4),
        "sharp30_per_1000px": round(1000.0 * float((turns_a > 30).sum()) / max(length, 1.0), 2),
        "sharp60_share": round(float((turns_a > 60).mean()), 4),
        "junction_turns": len(junction_turns),
        "shapes_per_color": per_color,
    }


def rendered_colors(rgba: np.ndarray, svg: str) -> dict:
    """Share of the image each palette color takes in the rendering, by exact match on opaque pixels."""
    size = rgba.shape[0] * rgba.shape[1]
    out = {}
    codes = rgba[..., 0].astype(np.int64) << 16 | rgba[..., 1].astype(np.int64) << 8 | rgba[..., 2]
    opaque = rgba[..., 3] == 255
    values, counts = np.unique(codes[opaque], return_counts=True)
    table = dict(zip(values.tolist(), counts.tolist()))
    for color in dict.fromkeys(c for c, _ in _GROUP.findall(svg)):
        key = int(color[1:], 16)
        out[color] = round(100.0 * table.get(key, 0) / size, 2)
    return out


def hairlines(path: str, width: int, height: int, scales) -> dict:
    """Pixels inside the artwork that the renderer leaves see-through. There should be none."""
    out = {}
    for s in scales:
        w, h = max(1, round(width * s)), max(1, round(height * s))
        a = np.asarray(render_png(path, w, h))[..., 3]
        art = ni.binary_closing(a > 127, iterations=2, border_value=0)
        inside = ni.binary_erosion(art, iterations=3, border_value=1)
        bad = inside & (a < 250)
        out[str(s)] = {"pixels": int(bad.sum()), "min_alpha": int(a[inside].min()) if inside.any() else 255}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("out")
    p.add_argument("--scales", default="1,0.73,2")
    a = p.parse_args()
    scales = [float(v) for v in a.scales.split(",")]
    results = []
    for svg_path in sorted(glob.glob(f"{a.out}/*.svg")):
        stem = Path(svg_path).stem
        image, variant = stem.rsplit("-", 1)
        found = [f for d in a.input.split(",") for f in glob.glob(f"{d}/{image}.*")]
        if not found:
            continue
        src = Image.open(found[0]).convert("RGBA")
        base = Image.new("RGBA", src.size, (255, 255, 255, 255))
        base.alpha_composite(src)
        source = np.asarray(base.convert("RGB"))
        h, w = source.shape[:2]
        text = Path(svg_path).read_text(encoding="utf-8")
        sidecar = Path(a.out) / f"{stem}.json"
        side = json.loads(sidecar.read_text()) if sidecar.exists() else {}
        m = analyze_paths(text, w, h, side.get("info", {}).get("junctions", ()))
        rgba = np.asarray(render_png(svg_path, w, h))
        flat = Image.new("RGBA", (w, h), (255, 255, 255, 255))
        flat.alpha_composite(Image.fromarray(rgba))
        dE = np.sqrt(((srgb_to_lab(source) - srgb_to_lab(np.asarray(flat.convert("RGB")))) ** 2).sum(-1))
        row = {"image": image, "variant": variant, "svg_kb": round(os.path.getsize(svg_path) / 1024, 1), **m,
               "mean_de": round(float(dE.mean()), 2), "p95_de": round(float(np.percentile(dE, 95)), 2),
               "colors": len(set(c for c, _ in _GROUP.findall(text))),
               "area_percent": rendered_colors(rgba, text), "hairlines": hairlines(svg_path, w, h, scales)}
        if side:
            row.update(seconds=side["seconds"], peak_rss_mb=side["peak_rss_mb"], stages=side.get("stages", {}))
        results.append(row)
        print(f"{image:11s} {variant:8s} {row.get('seconds', 0):6.1f}s {row.get('peak_rss_mb', 0):5.0f}MB c={row['colors']:2d} "
              f"paths={row['paths']:5d} nodes={row['nodes']:6d} n/100px={row['nodes_per_100px']:5.2f} "
              f"sharp30={100 * row['sharp30_share']:5.1f}%/{row['sharp30_per_1000px']:5.1f}perK {row['svg_kb']:6.0f}KB dE={row['mean_de']:5.2f} "
              f"hair={[v['pixels'] for v in row['hairlines'].values()]} minA={[v['min_alpha'] for v in row['hairlines'].values()]} junc={row['junction_turns']}", flush=True)
    Path(a.out, "measurements.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
