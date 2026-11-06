#!/usr/bin/env python
"""Write the synthetic checks: pixel art, and hard and antialiased geometry. usage: synth.py OUTPUT_DIR"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PIX = [
    "................",
    "....KKKKKKKK....",
    "...KRRRRRRRRK...",
    "..KRRWWRRRRRRK..",
    "..KRWWRRRRRRRK..",
    "..KRRRRRRRRRRK..",
    "..KKKKKKKKKKKK..",
    "..KSSKSSSSKSSK..",
    "..KSSKSSSSKSSK..",
    "..KSSSSSSSSSSK..",
    "...KSSKKKKSSK...",
    "....KSSSSSSK....",
    "...KBBKKKKBBK...",
    "..KBBBBBBBBBBK..",
    "..KKKKKKKKKKKK..",
    "................",
]
COLORS = {".": (255, 255, 255), "K": (20, 20, 30), "R": (214, 40, 40), "W": (250, 250, 250),
          "S": (247, 200, 160), "B": (40, 90, 200)}


def pixel_art(block: int = 16) -> Image.Image:
    grid = np.array([[COLORS[c] for c in row] for row in PIX], dtype=np.uint8)
    return Image.fromarray(np.repeat(np.repeat(grid, block, 0), block, 1))


def geometry(aa: int) -> Image.Image:
    """Rectangles, a triangle, a circle and a slanted bar, with `aa`x supersampling (1 for hard edges)."""
    size = 800 * aa
    im = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(im)
    s = aa
    d.rectangle((80 * s, 80 * s, 360 * s, 300 * s), fill=(30, 60, 160))
    d.rectangle((140 * s, 140 * s, 300 * s, 240 * s), fill=(250, 210, 40))
    d.polygon([(460 * s, 300 * s), (720 * s, 300 * s), (590 * s, 80 * s)], fill=(200, 40, 50))
    d.ellipse((90 * s, 420 * s, 330 * s, 660 * s), fill=(40, 160, 90))
    d.polygon([(420 * s, 440 * s), (720 * s, 620 * s), (690 * s, 670 * s), (390 * s, 490 * s)], fill=(20, 20, 30))
    return im.resize((800, 800), Image.LANCZOS) if aa > 1 else im


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    pixel_art().save(out / "synth-pixel.png")
    geometry(1).save(out / "synth-hard.png")
    geometry(4).save(out / "synth-aa.png")
