#!/usr/bin/env python
"""One engine on one image in its own process, so peak memory is that run's alone. Prints JSON; writes the SVG.

usage: run_engine.py IMAGE {new,classic} {stacked,cutout} OUT.svg [--window N]

Only the engines run here, with no report or preview, so both are measured on equal terms. The classic engine has
no stage clock of its own: its helpers are wrapped to time them, and "other" is what is left of `segment`.
"""
import argparse
import functools
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ClassicOptions, lab_mod, load, patches, pipe_mod, seg_mod, vec_mod  # noqa: E402


def timed(store, key):
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*a, **k):
            t = time.perf_counter()
            r = fn(*a, **k)
            store[key] = store.get(key, 0.0) + time.perf_counter() - t
            return r

        return inner

    return wrap


def run_classic(rgb, layers, title):
    stages = {}
    triples = [
        (seg_mod, "_gauss_rgb", timed(stages, "blur")),
        (seg_mod, "_find_groups", timed(stages, "groups")),
        (seg_mod, "_add_unexplained_colors", timed(stages, "unexplained")),
        (seg_mod, "_nearest", timed(stages, "nearest")),
        (seg_mod, "_split_mixed_regions", timed(stages, "split")),
        (seg_mod, "_dissolve_fringes", timed(stages, "fringes")),
        (seg_mod, "_remove_specks", timed(stages, "specks")),
        (seg_mod, "_smooth_partition", timed(stages, "smooth")),
    ]
    with patches(*triples):
        t = time.perf_counter()
        seg = seg_mod.segment(rgb, ClassicOptions)
        whole = time.perf_counter() - t
        t = time.perf_counter()
        svg, layer_info = vec_mod.build_svg(seg.labels, seg.colors, rgb.shape[1], rgb.shape[0], layers, seg.speck_area, title)
        stages["trace"] = time.perf_counter() - t
    stages["other"] = max(0.0, whole - sum(v for k, v in stages.items() if k != "trace"))
    return svg, stages, {"scale": float(seg.scale), "warnings": seg.warnings, "layers": layer_info}, seg.colors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("engine", choices=["new", "classic"])
    p.add_argument("layers", choices=["stacked", "cutout"])
    p.add_argument("out")
    p.add_argument("--window", type=int)
    a = p.parse_args()
    rgb = np.asarray(load(a.image))
    title = Path(a.image).stem
    t0 = time.perf_counter()
    if a.engine == "new":
        if a.window:
            lab_mod.assign = functools.partial(lab_mod.assign, window=a.window)
        r = pipe_mod.run(rgb, a.layers, title)
        svg, stages, info, colors = r.svg, r.timings, r.info, r.colors
    else:
        svg, stages, info, colors = run_classic(rgb, a.layers, title)
    total = time.perf_counter() - t0
    Path(a.out).write_text(svg, encoding="utf-8")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({
        "seconds": round(total, 3),
        "peak_rss_mb": round(rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024, 1),
        "stages": {k: round(v, 3) for k, v in stages.items()},
        "junctions": info.get("junctions", []),
        "warnings": info.get("warnings", []),
        "info": {k: v for k, v in info.items() if k not in ("junctions", "layers", "warnings", "palette_log")},
        "palette_log": info.get("palette_log", []),
        "colors": [list(int(v) for v in c) for c in colors],
        "pixels": int(rgb.shape[0] * rgb.shape[1]),
    }))


if __name__ == "__main__":
    main()
