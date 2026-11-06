#!/usr/bin/env python
"""Render SVGs in Chromium through Playwright and count see-through pixels inside the artwork.

Run with the venv that has Playwright: browser_check.py OUTPUT_DIR [--variants a,b] [--scales 1,3,0.25]
Writes browser.json in OUTPUT_DIR. The page is transparent, so alpha shows exactly what Chromium left uncovered.
"""
import argparse
import glob
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
from scipy import ndimage as ni

Image.MAX_IMAGE_PIXELS = None


def see_through(alpha: np.ndarray) -> dict:
    art = ni.binary_closing(alpha > 127, iterations=2, border_value=0)
    inside = ni.binary_erosion(art, iterations=3, border_value=1)
    bad = inside & (alpha < 250)
    worst = int(alpha[inside].min()) if inside.any() else 255
    return {"pixels": int(bad.sum()), "under_200": int((inside & (alpha < 200)).sum()), "min_alpha": worst,
            "inside": int(inside.sum())}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--variants", default="stacked2,cutout2,today")
    p.add_argument("--scales", default="1,3,0.25")
    a = p.parse_args()
    scales = [float(v) for v in a.scales.split(",")]
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for variant in a.variants.split(","):
            for path in sorted(glob.glob(f"{a.out}/*-{variant}.svg")):
                text = Path(path).read_text(encoding="utf-8")
                w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', text).groups())
                row = {"file": Path(path).stem, "scales": {}}
                for s in scales:
                    vw, vh = max(1, round(w * s)), max(1, round(h * s))
                    page = browser.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=1)
                    svg = re.sub(r'width="\d+" height="\d+"', f'width="{vw}" height="{vh}"', text, count=1)
                    page.set_content(f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent">{svg}</body></html>')
                    shot = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": vw, "height": vh})
                    page.close()
                    alpha = np.asarray(Image.open(io.BytesIO(shot)).convert("RGBA"))[..., 3]
                    row["scales"][str(s)] = see_through(alpha)
                results.append(row)
                print(row["file"], {k: (v["pixels"], v["under_200"], v["min_alpha"]) for k, v in row["scales"].items()}, flush=True)
        browser.close()
    Path(a.out, "browser.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
