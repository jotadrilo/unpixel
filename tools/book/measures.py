"""Every number in the book: real runs of both engines over the battery, measured with tools/engine/measure.py."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools/engine"))
from harness import SOURCES, load  # noqa: E402

BIG_PIXELS = 24_000_000
WINDOWS = (3, 6, 9, 12)


def run(image, engine, layers, svg: Path, window=None, redo=False) -> dict:
    side = svg.with_suffix(".json")
    if side.exists() and not redo:
        return json.loads(side.read_text())
    cmd = [sys.executable, str(HERE / "run_engine.py"), str(image), engine, layers, str(svg)]
    if window:
        cmd += ["--window", str(window)]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if done.returncode:
        raise RuntimeError(f"{cmd}\n{done.stderr[-2000:]}")
    data = json.loads(done.stdout)
    side.write_text(json.dumps(data))
    return data


def shared_segments(svg_text: str) -> dict:
    """How many times each drawn segment appears in the fills: twice means two regions share that very curve."""
    seen = Counter()
    for attrs in re.findall(r"<path ([^>]*)/?>", svg_text):
        if 'class="trap"' in attrs:
            continue
        d = re.search(r'\bd="([^"]+)"', attrs).group(1)
        tokens = re.findall(r"[MLCZ]|-?\d+(?:\.\d+)?", d)
        i, pos, start = 0, None, None
        while i < len(tokens):
            t = tokens[i]
            i += 1
            if t == "M":
                pos = start = (tokens[i], tokens[i + 1])
                i += 2
            elif t == "L":
                q = (tokens[i], tokens[i + 1])
                i += 2
                seen[tuple(sorted((pos, q)))] += 1
                pos = q
            elif t == "C":
                vals = tokens[i : i + 6]
                i += 6
                p1, p2, q = tuple(vals[:2]), tuple(vals[2:4]), tuple(vals[4:6])
                a, b = (pos, p1, p2, q), (q, p2, p1, pos)
                seen[min(a, b)] += 1
                pos = q
            elif t == "Z":
                pos = start
    counts = Counter(seen.values())
    total = sum(counts.values())
    return {"segments": total, "once": counts.get(1, 0), "twice": counts.get(2, 0), "more": total - counts.get(1, 0) - counts.get(2, 0),
            "twice_share": round(counts.get(2, 0) / max(total, 1), 4)}


def measure_svg(job) -> dict:
    """The repository's own measurements on a written SVG, plus how much of its geometry is shared."""
    from measure import analyze_paths, hairlines, rendered_colors
    from render import render_png
    from unpixel.color import srgb_to_lab

    image, svg_path, junctions, scales = job
    text = Path(svg_path).read_text(encoding="utf-8")
    source = load(image)
    h, w = source.shape[:2]
    row = analyze_paths(text, w, h, junctions)
    rgba = render_png(str(svg_path), w, h)
    flat = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    d_e = np.sqrt(((srgb_to_lab(source) - srgb_to_lab(np.asarray(flat.convert("RGB")))) ** 2).sum(-1))
    row.update(
        svg_kb=round(Path(svg_path).stat().st_size / 1024, 1),
        mean_de=round(float(d_e.mean()), 2),
        p95_de=round(float(np.percentile(d_e, 95)), 2),
        colors=len(set(re.findall(r'<g id="[^"]*" fill="(#[0-9A-Fa-f]{6})"', text))),
        area_percent=rendered_colors(np.asarray(rgba), text),
        hairlines=hairlines(str(svg_path), w, h, scales),
        shared=shared_segments(text),
    )
    return row


def collect(work: Path, log=print) -> dict:
    """Run everything once. Timed runs go one at a time; only the measuring of written files runs in parallel."""
    work.mkdir(parents=True, exist_ok=True)
    runs: dict = {}
    for engine in ("new", "classic"):
        for name, src in SOURCES.items():
            data = run(src, engine, "stacked", work / f"{name}-{engine}-stacked.svg")
            runs[f"{name}/{engine}/stacked"] = data
            log(f"  {name:11s} {engine:8s} stacked {data['seconds']:6.1f} s {data['peak_rss_mb']:6.0f} MB")
    for engine in ("new", "classic"):
        for name, src in SOURCES.items():
            runs[f"{name}/{engine}/cutout"] = run(src, engine, "cutout", work / f"{name}-{engine}-cutout.svg")
    log("  cutout done")
    for win in WINDOWS:
        for name, src in SOURCES.items():
            runs[f"{name}/reach{win}/stacked"] = run(src, "new", "stacked", work / f"{name}-reach{win}-stacked.svg", window=win)
    log("  reach done")
    big = work / "leaves-24mp.png"
    if not big.exists():
        im = Image.open(SOURCES["leaves"]).convert("RGB")
        k = (BIG_PIXELS / (im.width * im.height)) ** 0.5
        im.resize((round(im.width * k), round(im.height * k)), Image.BICUBIC).save(big)
    for engine in ("new", "classic"):
        d = run(big, engine, "stacked", work / f"leaves24-{engine}-stacked.svg")
        runs[f"leaves24/{engine}/stacked"] = d
        log(f"  leaves 24 MP {engine}: {d['seconds']:.1f} s {d['peak_rss_mb']:.0f} MB")

    jobs, keys = [], []
    for key, data in runs.items():
        name, variant, layers = key.split("/")
        if name == "leaves24":
            continue
        scales = (1.0, 0.73, 2.0)
        jobs.append((SOURCES[name], work / f"{name}-{variant}-{layers}.svg", data["junctions"], scales))
        keys.append(key)
    with ProcessPoolExecutor(8) as pool:
        for key, row in zip(keys, pool.map(measure_svg, jobs)):
            runs[key]["measure"] = row
    log("  measured")
    return runs
