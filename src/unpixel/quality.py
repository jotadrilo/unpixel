"""Whether an input was enlarged from a smaller image, or is small, to say so before tracing it.

Tracing keeps whatever edges the input has: a small image gives few details, and one enlarged from a
smaller one keeps its steps, blur or halos. This only reports it; it never changes the result.

Two measures, both on the luminance:

- **The enlargement grid.** Enlarging repeats each source pixel over a block, so the changes between
  neighboring columns (and rows) bunch at a fixed period, the enlargement factor, even after smoothing,
  sharpening or JPEG. Summed over the image, that shows as a sharp peak in the spectrum of the column
  (and row) profile, at the same period on both axes. An image drawn at its own size has no such peak.
  JPEG's own 8-pixel grid peaks at 8 and its harmonics (4, 8/3), so those periods are not taken as an
  enlargement.
- **Missing detail.** An image enlarged with smoothing loses almost nothing when shrunk by 2 and
  enlarged back (median-filtered first, so noise does not count), against what it loses at 12.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

SMALL_SIDE = 512  # a longer side below this is a low-resolution image, whatever its content
MAX_SIDE = 2400  # larger inputs are measured on a copy this size
GRID_PEAK = 10.0  # a period's peak over the spectrum around it, needed on both axes
GRID_PERIODS = (2.0, 24.0)
JPEG_PERIODS = (8.0, 4.0, 8 / 3)
SOFT_BELOW = 0.10
MIN_EDGE_PIXELS = 2000


def _grid(a: np.ndarray) -> tuple[float, float] | None:
    """The enlargement factor and its weaker axis's peak, when both axes show the same period."""
    found = []
    for axis in (0, 1):
        changes = np.abs(np.diff(a, axis=1 - axis)).sum(axis=axis)
        changes = changes - np.convolve(changes, np.ones(31) / 31, "same")
        n = len(changes)
        if n < 64:
            return None
        spectrum = np.abs(np.fft.rfft(changes * np.hanning(n)))
        best = (0.0, 0.0)
        for period in np.arange(GRID_PERIODS[0], GRID_PERIODS[1], 0.05):
            i = int(round(n / period))
            if 2 <= i < len(spectrum) - 1:
                around = np.median(spectrum[max(1, i - 40): i + 40])
                peak = spectrum[i - 1: i + 2].max() / max(around, 1e-9)
                if peak > best[0]:
                    best = (float(peak), float(period))
        found.append(best)
    (peak_x, period_x), (peak_y, period_y) = found
    if min(peak_x, peak_y) < GRID_PEAK or abs(period_x - period_y) > 0.3:
        return None
    period = (period_x + period_y) / 2
    if any(abs(period - jpeg) < 0.15 for jpeg in JPEG_PERIODS):
        return None
    return period, min(peak_x, peak_y)


def _detail_ratio(gray: Image.Image) -> float | None:
    if min(gray.size) < 24:
        return None
    gray = gray.filter(ImageFilter.MedianFilter(5))
    a = np.asarray(gray, dtype=np.float32)
    gy, gx = np.gradient(a)
    edges = np.hypot(gx, gy) > 4
    if int(edges.sum()) < MIN_EDGE_PIXELS:
        return None
    width, height = gray.size
    losses = []
    for factor in (2.0, 12.0):
        small = gray.resize((max(1, round(width / factor)), max(1, round(height / factor))), Image.LANCZOS)
        back = np.asarray(small.resize((width, height), Image.LANCZOS), dtype=np.float32)
        losses.append(float(np.abs(a - back)[edges].mean()))
    return losses[0] / losses[1] if losses[1] > 0 else None


def assess(rgb: np.ndarray, kind: str, block: float = 1.0) -> dict:
    """The input's quality: `verdict` is ok, low_resolution, pixelated or upscaled.

    `kind` is the engine's classification ("pixel" for blocky art) and `block` its block size. An
    upscaled verdict carries `factor` when the enlargement grid gives it, and `source_size`, the size
    the image was enlarged from."""
    height, width = rgb.shape[:2]
    gray = Image.fromarray(rgb).convert("L")
    if max(width, height) > MAX_SIDE:
        shrink = MAX_SIDE / max(width, height)
        gray = gray.resize((round(width * shrink), round(height * shrink)), Image.LANCZOS)
    else:
        shrink = 1.0
    if kind == "pixel" and block >= 2:
        return {"verdict": "pixelated", "block": int(round(block))}
    if max(width, height) < SMALL_SIDE:
        return {"verdict": "low_resolution"}
    grid = _grid(np.asarray(gray, dtype=np.float32))
    if grid is not None:
        factor = grid[0] / shrink
        return {"verdict": "upscaled", "factor": round(factor, 1),
                "source_size": [round(width / factor), round(height / factor)]}
    ratio = _detail_ratio(gray)
    if ratio is not None and ratio < SOFT_BELOW:
        return {"verdict": "upscaled", "factor": None, "source_size": None, "detail_ratio": round(ratio, 3)}
    return {"verdict": "ok"}


def warning(quality: dict, width: int, height: int) -> str | None:
    verdict = quality["verdict"]
    if verdict == "pixelated":
        return (f"This image is made of {quality['block']}-pixel blocks, so the result keeps its steps. That is "
                "right for pixel art; for smooth edges, convert a redrawn or higher-resolution version.")
    if verdict == "low_resolution":
        return (f"This image is small ({width}×{height}), so the result has few details. A higher-resolution or "
                "redrawn version converts better.")
    if verdict == "upscaled":
        source = quality.get("source_size")
        origin = f" (about {source[0]}×{source[1]})" if source else ""
        return (f"This image looks enlarged from a smaller one{origin}, so the result keeps its soft, stepped or "
                "noisy edges. A redrawn or higher-resolution version converts better.")
    return None
