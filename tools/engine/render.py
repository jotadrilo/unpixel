#!/usr/bin/env python
"""Render an SVG with rsvg-convert to a JPEG, on white, at most 1400 px on the long side."""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def render_png(svg: str, width: int | None = None, height: int | None = None, out: str | None = None) -> Image.Image:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cmd = ["rsvg-convert", svg, "-o", f.name]
        if width:
            cmd += ["-w", str(width)]
        if height:
            cmd += ["-h", str(height)]
        subprocess.run(cmd, check=True)
        return Image.open(f.name).convert("RGBA").copy()


def render_jpg(svg: str, jpg: str, long_side: int = 1400) -> None:
    image = render_png(svg)
    w, h = image.size
    if max(w, h) > long_side:
        k = long_side / max(w, h)
        image = render_png(svg, round(w * k), round(h * k))
    base = Image.new("RGBA", image.size, (255, 255, 255, 255))
    base.alpha_composite(image)
    base.convert("RGB").save(jpg, quality=93, subsampling=0)


if __name__ == "__main__":
    render_jpg(sys.argv[1], sys.argv[2])
