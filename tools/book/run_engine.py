#!/usr/bin/env python
"""unpixel on one image in its own process, so peak memory is that run's alone. Prints JSON; writes the SVG.

usage: run_engine.py IMAGE {stacked,cutout} OUT.svg [--window N]

This is `pipeline.run` with no report or preview. `--window` sets the reach of transition pixels.
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
from harness import lab_mod, load, pipe_mod  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("layers", choices=["stacked", "cutout"])
    p.add_argument("out")
    p.add_argument("--window", type=int)
    a = p.parse_args()
    rgb = np.asarray(load(a.image))
    t0 = time.perf_counter()
    if a.window:
        lab_mod.assign = functools.partial(lab_mod.assign, window=a.window)
    r = pipe_mod.run(rgb, a.layers, Path(a.image).stem)
    total = time.perf_counter() - t0
    Path(a.out).write_text(r.svg, encoding="utf-8")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({
        "seconds": round(total, 3),
        "peak_rss_mb": round(rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024, 1),
        "stages": {k: round(v, 3) for k, v in r.timings.items()},
        "junctions": r.info.get("junctions", []),
        "colors": [list(int(v) for v in c) for c in r.colors],
        "pixels": int(rgb.shape[0] * rgb.shape[1]),
    }))


if __name__ == "__main__":
    main()
