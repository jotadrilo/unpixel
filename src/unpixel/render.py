"""A small rasterizer for the SVG subset unpixel writes.

It reads the written file rather than internal state, so verification and previews show
what a viewer will show, without requiring a system SVG library.
"""

from __future__ import annotations

import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from .color import parse_hex

_GROUP = re.compile(r'<g id="[^"]*" fill="(#[0-9A-Fa-f]{6})"[^>]*>(.*?)</g>', re.S)
_PATH = re.compile(r'<path d="([^"]+)"')
_TOKEN = re.compile(r"[MLCZ]|-?\d+(?:\.\d+)?")
_T = np.linspace(0, 1, 13)[1:, None]


def _subpaths(d: str, scale: float) -> list[np.ndarray]:
    tokens = _TOKEN.findall(d)
    out, current, i = [], [], 0
    pos = np.zeros(2)
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "M":
            current = []
            pos = np.array([float(tokens[i]), float(tokens[i + 1])])
            current.append(pos[None])
            i += 2
        elif cmd == "L":
            pos = np.array([float(tokens[i]), float(tokens[i + 1])])
            current.append(pos[None])
            i += 2
        elif cmd == "C":
            values = np.array([float(v) for v in tokens[i : i + 6]]).reshape(3, 2)
            a, b, c = values
            t = _T
            current.append((1 - t) ** 3 * pos + 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t**2 * b + t**3 * c)
            pos = c
            i += 6
        elif cmd == "Z":
            out.append(np.concatenate(current) * scale)
    return out


def render_svg(svg: str, width: int, height: int, scale: float = 1.0) -> np.ndarray:
    """Return an RGBA uint8 array. Coverage is binary; supersample for anti-aliasing."""
    size = (int(round(width * scale)), int(round(height * scale)))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for color, body in _GROUP.findall(svg):
        fill = parse_hex(color) + (255,)
        for d in _PATH.findall(body):
            subs = _subpaths(d, scale)
            low = np.floor(np.concatenate(subs).min(0)).astype(int) - 1
            high = np.ceil(np.concatenate(subs).max(0)).astype(int) + 2
            mask = None
            for sub in subs:
                layer = Image.new("1", tuple(high - low), 0)
                ImageDraw.Draw(layer).polygon([tuple(p) for p in sub - low], fill=1)
                mask = layer if mask is None else ImageChops.logical_xor(mask, layer)
            canvas.paste(fill, tuple(low.tolist()), mask)
    return np.asarray(canvas)


def composite(rgba: np.ndarray, background: tuple[int, int, int]) -> Image.Image:
    image = Image.fromarray(rgba)
    base = Image.new("RGBA", image.size, background + (255,))
    base.alpha_composite(image)
    return base.convert("RGB")
