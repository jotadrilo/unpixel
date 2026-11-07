#!/usr/bin/env python
"""Run variants over the battery and write <image>-<variant>.svg/.jpg and <image>-<variant>.json.

usage: run_battery.py INPUT_DIR OUTPUT_DIR [--variants a,b] [--images a,b] [--jobs N]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render import render_jpg  # noqa: E402

IMAGES = "axolotl diver leaves chef ghost watchmaker float sunset principito".split()
VARIANTS = ["stacked", "cutout"]


def one(args):
    image, variant, input_dir, out = args
    src = glob.glob(f"{input_dir}/{image}.*")[0]
    svg = f"{out}/{image}-{variant}.svg"
    r = subprocess.run([sys.executable, str(HERE / "run_one.py"), src, variant, svg], capture_output=True, text=True, timeout=600)
    if r.returncode:
        return f"{image} {variant} FAILED\n{r.stderr[-1500:]}"
    data = json.loads(r.stdout)
    Path(f"{out}/{image}-{variant}.json").write_text(json.dumps(data, indent=1))
    render_jpg(svg, f"{out}/{image}-{variant}.jpg")
    return f"{image:11s} {variant:8s} {data['seconds']:6.2f}s rss {data['peak_rss_mb']:6.0f}MB colors {len(data['info'].get('layers', [])):2d} {os.path.getsize(svg)//1024:5d}KB {data['kind']}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("out")
    p.add_argument("--variants", default=",".join(VARIANTS))
    p.add_argument("--images", default=",".join(IMAGES))
    p.add_argument("--jobs", type=int, default=1)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tasks = [(i, v, a.input, a.out) for i in a.images.split(",") for v in a.variants.split(",")]
    with ThreadPoolExecutor(a.jobs) as pool:
        for line in pool.map(one, tasks):
            print(line, flush=True)


if __name__ == "__main__":
    main()
