#!/usr/bin/env python
"""Run one variant on one image: writes the SVG and prints timings, peak memory and palette as JSON."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("variant", choices=["cutout", "stacked"])
    p.add_argument("out")
    p.add_argument("--colors", type=int)
    a = p.parse_args()
    from unpixel.engine import pipeline

    rgba = Image.open(a.image).convert("RGBA")
    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    base.alpha_composite(rgba)
    rgb = np.asarray(base.convert("RGB"))
    title = Path(a.image).stem
    t0 = time.perf_counter()
    r = pipeline.run(rgb, a.variant, title, a.colors)
    total = time.perf_counter() - t0
    Path(a.out).write_text(r.svg, encoding="utf-8")
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    print(json.dumps({"image": title, "variant": a.variant, "kind": r.kind, "seconds": round(total, 3),
                      "peak_rss_mb": round(rss_mb, 1), "stages": {k: round(v, 3) for k, v in r.timings.items()},
                      "info": r.info}))


if __name__ == "__main__":
    main()
