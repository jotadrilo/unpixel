"""Tell pixel art and hard geometry from soft artwork, on the untouched source."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..color import srgb_to_lab


@dataclass
class Kind:
    name: str  # "pixel", "hard" or "soft"
    block: int  # size of a logical pixel, 1 when there is no grid
    hard_share: float  # of strong edges, how many jump in one step with flat color either side
    colors: int  # distinct source colors


def _grid(changes: np.ndarray, min_block: int = 2) -> int:
    """The largest block size with nearly every color change on its grid. `changes[i]`: between i and i + 1."""
    count = changes.sum()
    if count == 0:
        return 1
    pos = np.nonzero(changes)[0] + 1
    best = 1
    for g in range(min_block, 65):
        if (pos % g == 0).mean() >= 0.98:
            best = g
    return best


def classify(rgb: np.ndarray) -> Kind:
    lab = srgb_to_lab(rgb)
    h, w = lab.shape[:2]
    packed = rgb[..., 0].astype(np.int32) << 16 | rgb[..., 1].astype(np.int32) << 8 | rgb[..., 2]
    present = np.zeros(1 << 24, dtype=bool)
    present[packed.ravel()] = True
    colors = int(present.sum())
    del present, packed

    def share(axis: int) -> tuple[int, int]:
        v = np.moveaxis(lab, axis, 0)
        if v.shape[0] < 4:
            return 0, 0
        step = np.sqrt(((v[1:] - v[:-1]) ** 2).sum(-1))
        strong = step[1:-1] > 15.0
        before = step[:-2] < 3.0
        after = step[2:] < 3.0
        return int((strong & before & after).sum()), int(strong.sum())

    a, b = share(0), share(1)
    hard = a[0] + b[0]
    strong = a[1] + b[1]
    hard_share = hard / strong if strong else 1.0

    changes_x = (np.abs(rgb[:, 1:].astype(int) - rgb[:, :-1]).sum(-1) > 12).any(0)
    changes_y = (np.abs(rgb[1:].astype(int) - rgb[:-1]).sum(-1) > 12).any(1)
    # A grid is only seen on columns that change in some rows and not in others.
    gx, gy = _grid(changes_x), _grid(changes_y)
    block = min(gx, gy) if min(gx, gy) > 1 else 1
    tiny = max(h, w) <= 256 and colors <= 256
    if hard_share >= 0.85 and (block > 1 or tiny):
        return Kind("pixel", block, hard_share, colors)
    # A noisy source with few strong edges can also score high here; hard art has few distinct colors.
    if hard_share >= 0.85 and strong > 0 and colors <= 4096:
        return Kind("hard", 1, hard_share, colors)
    return Kind("soft", 1, hard_share, colors)
