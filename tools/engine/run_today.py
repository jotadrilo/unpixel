#!/usr/bin/env python
"""Today's engine, untouched, on one image, for the baseline: writes <image>-today.svg/.json/.jpg."""
import glob
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import render_jpg  # noqa: E402

from unpixel.cli import main as cli  # noqa: E402

image, input_dir, out = sys.argv[1:4]
src = glob.glob(f"{input_dir}/{image}.*")[0]
svg = f"{out}/{image}-today.svg"
t0 = time.perf_counter()
code = cli([src, "-o", svg, "--force", "--no-report", "--json"])
seconds = time.perf_counter() - t0
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
if code:
    sys.exit(code)
render_jpg(svg, f"{out}/{image}-today.jpg")
Path(f"{out}/{image}-today.json").write_text(
    json.dumps({"image": image, "variant": "today", "seconds": round(seconds, 3), "peak_rss_mb": round(rss, 1)}))
