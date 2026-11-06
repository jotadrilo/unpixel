#!/usr/bin/env python
"""Write compare-<image>.jpg: source, today and the new engine side by side. usage: compare.py INPUT_DIR OUTPUT_DIR"""
import glob
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_battery import IMAGES  # noqa: E402

input_dir, out = sys.argv[1:3]
for name in IMAGES:
    panels = [("source", glob.glob(f"{input_dir}/{name}.*")[0]), ("today", f"{out}/{name}-today.jpg"),
              ("engine, stacked", f"{out}/{name}-stacked.jpg")]
    images = []
    for label, path in panels:
        im = Image.open(path).convert("RGBA")
        base = Image.new("RGBA", im.size, "white")
        base.alpha_composite(im)
        base = base.convert("RGB")
        base.thumbnail((1000, 1000))
        images.append((label, base))
    h = max(i.height for _, i in images)
    sheet = Image.new("RGB", (sum(i.width for _, i in images) + 12, h + 22), "white")
    x = 0
    draw = ImageDraw.Draw(sheet)
    for label, im in images:
        sheet.paste(im, (x, 22))
        draw.text((x + 6, 5), label, fill="black")
        x += im.width + 6
    sheet.save(f"{out}/compare-{name}.jpg", quality=90)
