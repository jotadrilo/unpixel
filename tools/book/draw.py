"""Small drawing helpers. They only present data the engines produced; none of them computes a result."""

from __future__ import annotations

import base64
import io
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/vectorizing/img"


def as_image(a) -> Image.Image:
    return a if isinstance(a, Image.Image) else Image.fromarray(np.asarray(a).astype(np.uint8))


def save(a, name: str, quality: int = 84) -> str:
    """Write under img/ and return the path relative to the page."""
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    im = as_image(a)
    if name.endswith(".jpg"):
        im.convert("RGB").save(path, quality=quality, subsampling=0, optimize=True)
    else:
        colors = len(im.convert("RGB").getcolors(maxcolors=256) or []) if im.mode != "RGBA" else 0
        if 0 < colors <= 256:
            im.convert("RGB").quantize(colors, dither=Image.Dither.NONE).save(path, optimize=True)
        else:
            im.save(path, optimize=True)
    return f"img/{name}"


def crop(a, box):
    x0, y0, x1, y1 = box
    return np.asarray(a)[y0:y1, x0:x1]


def zoom(a, z: int):
    """Magnify with no smoothing: each pixel becomes a block of z by z."""
    return np.repeat(np.repeat(np.asarray(a), z, axis=0), z, axis=1)


def scaled(box, k):
    return tuple(int(round(v * k)) for v in box)


def shrink(a, width: int) -> Image.Image:
    im = as_image(a)
    if im.width <= width:
        return im
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


def faded(rgb, keep: float = 0.35):
    """The image in gray and pale, so that a mask laid over it stands out."""
    a = np.asarray(rgb).astype(np.float32)
    gray = a[..., :3].mean(-1, keepdims=True)
    return np.repeat(gray * keep + 255.0 * (1 - keep), 3, axis=-1)


def over(rgb, mask, color, alpha: float = 0.9, keep: float = 0.35):
    """A real mask over a faded real image."""
    base = faded(rgb, keep)
    m = np.asarray(mask)[..., None].astype(np.float32) * alpha
    return base * (1 - m) + np.array(color, dtype=np.float32) * m


def classes(label, colors, background=(255, 255, 255)):
    """A class map painted with its colors; a class past the palette, or below zero, is the background."""
    table = np.vstack([np.array(colors, dtype=np.float32).reshape(-1, 3), background]).astype(np.uint8)
    idx = np.where((label < 0) | (label >= len(colors)), len(colors), label)
    return table[idx]


def rsvg(svg_text: str, background: str | None = None) -> Image.Image:
    cmd = ["rsvg-convert"]
    if background:
        cmd += ["-b", background]
    done = subprocess.run(cmd, input=svg_text.encode("utf-8"), capture_output=True, check=True)
    return Image.open(io.BytesIO(done.stdout)).convert("RGBA")


_HEAD = re.compile(r'<svg [^>]*>')


def svg_crop(svg_text: str, box=None, z: float = 1.0, background: str | None = "#ffffff", width: int | None = None) -> Image.Image:
    """A window of a real SVG, drawn as vectors at z times the size."""
    if box is None:
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg_text)
        box = (0, 0, int(m.group(1)), int(m.group(2)))
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if width:
        z = width / w
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" width="{round(w * z)}" height="{round(h * z)}">'
    return rsvg(_HEAD.sub(head, svg_text, count=1), background)


def outlines_only(svg_text: str, stroke_width: float, single_color: str | None = None, keep_traps: bool = False) -> str:
    """The same paths with no fill: what a pen would follow. Each group keeps its color unless one is given."""
    def group(m):
        color = single_color or m.group(2)
        return f'<g id="{m.group(1)}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linejoin="round">'

    out = re.sub(r'<g id="([^"]*)" fill="(#[0-9A-Fa-f]{6})"[^>]*>', group, svg_text)
    if not keep_traps:
        out = re.sub(r'<path class="trap"[^>]*/>\s*', "", out)
    return out


def without_traps(svg_text: str) -> str:
    return re.sub(r'<path class="trap"[^>]*/>\s*', "", svg_text)


def only_traps(svg_text: str) -> str:
    return re.sub(r'<path d="[^"]*"/>\s*', "", svg_text)


def groups(svg_text: str) -> list[tuple[str, str]]:
    return re.findall(r'<g id="([^"]*)" fill="(#[0-9A-Fa-f]{6})"', svg_text)


def only_group(svg_text: str, name: str) -> str:
    def keep(m):
        return m.group(0) if m.group(1) == name else ""

    return re.sub(r'<g id="([^"]*)".*?</g>\s*', keep, svg_text, flags=re.S)


def png_uri(a) -> str:
    buf = io.BytesIO()
    as_image(a).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def annotate(background, elements: str) -> Image.Image:
    """Vector marks over an already magnified real image; coordinates are in its pixels."""
    im = as_image(background)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{im.width}" '
           f'height="{im.height}"><image width="{im.width}" height="{im.height}" xlink:href="{png_uri(im)}"/>{elements}</svg>')
    return rsvg(svg).convert("RGB")


def path_of(points, z: float, box, close=False) -> str:
    x0, y0 = box[0], box[1]
    p = (np.asarray(points, dtype=np.float64) - [x0, y0]) * z
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in p) + ("Z" if close else "")


def bezier_path(seg, z: float, box) -> str:
    x0, y0 = box[0], box[1]
    p = (np.asarray(seg, dtype=np.float64) - [x0, y0]) * z
    return f"M{p[0][0]:.1f} {p[0][1]:.1f}C{p[1][0]:.1f} {p[1][1]:.1f} {p[2][0]:.1f} {p[2][1]:.1f} {p[3][0]:.1f} {p[3][1]:.1f}"


NUM_OPEN, NUM_CLOSE = "⁣", "⁣"
TR_OPEN, TR_MID, TR_CLOSE = "⁤", "⁥", "⁦"


def num(value, digits: int = 0) -> str:
    """A number, marked so that each language's page writes it in its own way."""
    return f"{NUM_OPEN}{float(value):.{digits}f}{NUM_CLOSE}"


def pct(value, digits: int = 1) -> str:
    return num(value, digits) + tr("%", " %")


def tr(en: str, es: str) -> str:
    """Text in both languages, resolved when the page for one of them is written."""
    return f"{TR_OPEN}{en}{TR_MID}{es}{TR_CLOSE}"


def localize(text: str, lang: str) -> str:
    """Resolve the marks of `num` and `tr` for one language."""
    pick = 1 if lang == "en" else 2
    text = re.sub(f"{TR_OPEN}(.*?){TR_MID}(.*?){TR_CLOSE}", lambda m: m.group(pick), text, flags=re.S)

    def write(m):
        raw = m.group(1)
        digits = len(raw.split(".")[1]) if "." in raw else 0
        out = f"{float(raw):,.{digits}f}"
        return out if lang == "en" else out.replace(",", "\0").replace(".", ",").replace("\0", ".")

    return re.sub(f"{NUM_OPEN}(-?[0-9.]+){NUM_CLOSE}", write, text)
