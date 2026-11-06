"""Reduce a segmentation to lines only: the darkest color's shapes, or the edges between colors."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ni

from .color import srgb_to_lab, to_hex
from .segment import Segmentation

LINES_MAX_AREA = 0.35  # share of the artwork above which the darkest color is unlikely to be a line
EDGE_WARNINGS = ("Interior areas colored",)  # about colors this mode removes


def _darkest(colors: list[tuple[int, int, int]]) -> int:
    lightness = [float(srgb_to_lab(np.array(color, dtype=np.float32))[0]) for color in colors]
    return int(np.argmin(lightness))


def _edges(labels: np.ndarray, radius: int) -> np.ndarray:
    """Mark every boundary between two classes, transparency included, then widen it to the stroke."""
    boundary = np.zeros(labels.shape, dtype=bool)
    across = labels[:-1, :] != labels[1:, :]
    along = labels[:, :-1] != labels[:, 1:]
    boundary[:-1, :] |= across
    boundary[:, :-1] |= along
    if radius <= 0:
        return boundary
    return ni.binary_dilation(boundary, iterations=radius)


def apply_outline(seg: Segmentation, mode: str, width: float, color: tuple[int, int, int]) -> Segmentation:
    """Return the segmentation holding one color, the one asked for, drawn only where the lines are."""
    darkest = _darkest(seg.colors)
    if mode == "lines":
        mask = seg.labels == darkest
        artwork = int((seg.labels != -1).sum())
        share = float(mask.sum()) / max(1, artwork)
        warnings = [w for w in seg.warnings if not w.startswith(EDGE_WARNINGS)]
        if share > LINES_MAX_AREA:
            warnings.append(
                f"The darkest color, {to_hex(seg.colors[darkest])}, covers {round(100 * share)}% of the artwork, so "
                "it may be a filled area and not an outline. Use --outline edges for lines between colors."
            )
    else:
        radius = max(0, int(round(width * seg.scale / 2)))
        mask = _edges(seg.labels, radius)
        warnings = [w for w in seg.warnings if not w.startswith(EDGE_WARNINGS)]
    labels = np.where(mask, 0, -1).astype(seg.labels.dtype)
    return Segmentation(
        labels=labels,
        raw_labels=labels.copy(),
        colors=[color],
        scale=seg.scale,
        speck_area=seg.speck_area,
        flat=seg.flat,
        background=seg.background,
        warnings=warnings,
    )
