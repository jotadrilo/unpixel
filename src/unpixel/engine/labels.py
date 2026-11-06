"""From pixels to a clean class map: denoising, antialiasing, background, palette and assignment.

The three ideas that matter:

* A transition pixel is one explained as a mix of the pixels on either side of it. It tells nothing about
  the palette, and it may only take a color that exists in solid form next to it. That is what keeps a
  dark-to-light edge from growing a third color.
* The palette is a deterministic farthest-point selection over a color histogram, weighted weakly by area.
  A small color far from everything is kept; a large color near another costs nothing and is not split.
* The background is what a flood from the image border reaches, so interior whites stay.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ni
from scipy.spatial import cKDTree

from ..color import srgb_to_lab

_FROM_XYZ = np.array(
    [[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]],
    dtype=np.float32,
)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)


def lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    """Convert Lab, shape (..., 3), to sRGB values in 0..255."""
    lab = np.asarray(lab, dtype=np.float32)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    t = np.where(f > 0.20689656, f**3, (f - 16.0 / 116.0) / 7.787) * _WHITE
    c = np.clip(t @ _FROM_XYZ.T, 0.0, 1.0)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
    return c * 255.0


CHROMA_K = 0.008
DARK_START_L = 8.0
DARK_FULL_L = 28.0
DARK_MIN = 0.2


def _dark_factor(lightness: np.ndarray) -> np.ndarray:
    return np.clip((lightness - DARK_START_L) / (DARK_FULL_L - DARK_START_L), DARK_MIN, 1.0)


def perceptual(lab: np.ndarray) -> np.ndarray:
    """Lab with chroma compressed where CIE76 overstates it: at high chroma and in the darks.

    Without this, a saturated violet splits in two, and an outline gets three blacks that differ only in a
    tint nobody can see. The map is exact and invertible. It depends only on the pixel, so it is deterministic.
    """
    lab = np.asarray(lab, dtype=np.float32)
    c = np.hypot(lab[..., 1], lab[..., 2])
    k = _dark_factor(lab[..., 0]) / (1.0 + CHROMA_K * c)
    return np.stack([lab[..., 0], lab[..., 1] * k, lab[..., 2] * k], axis=-1)


def from_perceptual(warped: np.ndarray) -> np.ndarray:
    warped = np.asarray(warped, dtype=np.float32)
    dark = _dark_factor(warped[..., 0])
    a, b = warped[..., 1] / dark, warped[..., 2] / dark
    cp = np.hypot(a, b)
    grow = 1.0 / np.maximum(1.0 - CHROMA_K * cp, 0.05)
    return np.stack([warped[..., 0], a * grow, b * grow], axis=-1)


def bilateral(lab: np.ndarray, sigma_s: float = 1.5, sigma_r: float = 8.0, radius: int = 2) -> np.ndarray:
    """Edge-preserving smoothing. Each offset pair is visited once and adds to both of its pixels."""
    h, w = lab.shape[:2]
    total = lab.copy()
    weight = np.ones((h, w), dtype=np.float32)
    rr = 2.0 * sigma_r * sigma_r
    ss = 2.0 * sigma_s * sigma_s
    for dy in range(0, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx <= 0:
                continue
            ya, yb = (0, h - dy), (dy, h)
            xa, xb = ((0, w - dx), (dx, w)) if dx >= 0 else ((-dx, w), (0, w + dx))
            a = lab[ya[0] : ya[1], xa[0] : xa[1]]
            b = lab[yb[0] : yb[1], xb[0] : xb[1]]
            d = a - b
            g = np.exp(-(d * d).sum(-1) / rr - (dy * dy + dx * dx) / ss)
            total[ya[0] : ya[1], xa[0] : xa[1]] += g[..., None] * b
            total[yb[0] : yb[1], xb[0] : xb[1]] += g[..., None] * a
            weight[ya[0] : ya[1], xa[0] : xa[1]] += g
            weight[yb[0] : yb[1], xb[0] : xb[1]] += g
    return total / weight[..., None]


def _shifted(lab: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """The image sampled at (y + dy, x + dx), repeating the edge."""
    h, w = lab.shape[:2]
    ys = np.clip(np.arange(h) + dy, 0, h - 1)
    xs = np.clip(np.arange(w) + dx, 0, w - 1)
    return lab[ys][:, xs]


def transition_mask(lab: np.ndarray, min_contrast: float = 12.0, rel: float = 0.22, floor: float = 2.5) -> np.ndarray:
    """Pixels explained as a mix of the two pixels on either side, along the direction of strongest contrast.

    The center of a thin stroke is not a mix: its two sides are alike, so the contrast test fails.
    """
    out = np.zeros(lab.shape[:2], dtype=bool)
    for r in (1, 2, 3):
        # A wider span only counts for a stronger edge: over 6 pixels a soft gradient also has contrast.
        need = min_contrast if r < 3 else 2.5 * min_contrast
        best = None
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            a, b = _shifted(lab, -dy * r, -dx * r), _shifted(lab, dy * r, dx * r)
            ab = b - a
            c2 = (ab * ab).sum(-1)
            if best is None:
                best = [c2, a, ab]
            else:
                hit = c2 > best[0]
                best[0] = np.where(hit, c2, best[0])
                best[1] = np.where(hit[..., None], a, best[1])
                best[2] = np.where(hit[..., None], ab, best[2])
        c2, a, ab = best
        contrast = np.sqrt(c2)
        pa = lab - a
        u = (pa * ab).sum(-1) / np.maximum(c2, 1e-6)
        residual = np.sqrt(((pa - u[..., None] * ab) ** 2).sum(-1))
        out |= (contrast >= need) & (u > 0.12) & (u < 0.88) & (residual <= np.maximum(floor, rel * contrast))
    return out


@dataclass
class Background:
    mask: np.ndarray  # pixels the flood reached
    lab: np.ndarray | None  # its color, or None when nothing was removed
    near: np.ndarray | None = None  # pixels alike enough to the background color to join it at an edge
    note: str | None = None  # why nothing was removed, for the user


HALO_DE = 5.0
ASKED_DE = 15.0  # how far from a color the user named the flood may go
STRIPE_PIXELS = 3_000_000  # assign in stripes above this, as the cost per color is held in memory
STRIPE_MARGIN = 8
INTERIOR_DE = 5.0
INTERIOR_SHARE = 0.0005
LINE_REACH = 4
LINE_MIN_DE = 6.0
LINE_MAX_DE = 24.0
LINE_MIN_L = 70.0
LINE_MAX_CHROMA = 8.0
LINE_SHARE = 0.001
LINE_PIECE = 0.0005


def find_background(
    lab: np.ndarray, border_share: float = 0.85, erode: bool = True, mode: str = "auto", color: np.ndarray | None = None
) -> Background:
    """Flood from the border through pixels alike to the border's dominant color, or the color asked for.

    The gate is narrow, set by the noise of the border itself. So a sticker's white stays out of the flood
    wherever it is distinct, and a one-pixel opening does not let the flood through.
    """
    empty = np.zeros(lab.shape[:2], bool)
    if mode == "keep":
        return Background(empty, None)
    ring = np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    if mode == "color":
        center = np.asarray(color, dtype=np.float32)
        dist = np.sqrt(((ring - center) ** 2).sum(-1))
        if not (dist <= ASKED_DE).any():
            return Background(empty, None, note="The requested background color was not found on the image border; nothing removed.")
        tau = ASKED_DE
    else:
        center = np.median(ring, axis=0)
        dist = np.sqrt(((ring - center) ** 2).sum(-1))
        close = dist <= 6.0
        if close.mean() < border_share:
            return Background(
                empty, None,
                note=f"The image border is not one uniform color (dominant color covers {close.mean():.0%}), so no "
                "background was removed. Pass --background '#RRGGBB' to name it.",
            )
        center = ring[close].mean(0)
        dist = np.sqrt(((ring - center) ** 2).sum(-1))
        tau = float(np.clip(np.percentile(dist[dist <= 6.0], 99) + 0.5, 2.0, 6.0))
        # A pale halo around the artwork is the background too; a sticker's border is walled off by its line.
        tau = max(tau, HALO_DE)
    d = np.sqrt(((lab - center) ** 2).sum(-1))
    near = d <= tau
    core = ni.binary_erosion(near, iterations=1, border_value=1) if erode else near
    parts, _ = ni.label(core)
    touching = np.unique(np.concatenate([parts[0], parts[-1], parts[:, 0], parts[:, -1]]))
    touching = touching[touching > 0]
    flood = np.isin(parts, touching)
    if not flood.any():
        return Background(flood, None)
    grown = ni.binary_dilation(flood, iterations=2, mask=near)
    return Background(grown, center.astype(np.float32), d <= max(tau * 2, 6.0))


@dataclass
class PaletteInfo:
    lab: np.ndarray
    rgb: np.ndarray
    stop_distance: float
    worst_left: float
    log: list[str] = field(default_factory=list)


BIN = 2.5
MODE_RADIUS = 5.0
FILL_MIN_DE = 9.0
HIGHLIGHT_MIN_DE = 12.0
STOP_DE = 9.0  # nothing above the floor is farther than this from the palette: enough colors
EXTRA_MIN_DE = 4.0
PIN_RADIUS = 6.0
PRUNE_DARK_L = 22.0
PRUNE_DARK_DE = 22.0
PRUNE_DE = 11.5
PRUNE_MAX_AREA = 0.01
SAT_DARK_L = 38.0
SAT_DARK_MIN_L = 15.0  # below this, chroma is a tint nobody can see, and any ratio is high
SAT_DARK_CHROMA = 35.0
SAT_DARK_RATIO = 1.6  # chroma over lightness: crimson is 2.2, navy 1.8, a dull brown about 1
SAT_DARK_DE = 11.0  # plain Lab, from every color so far
SAT_DARK_SHARE = 0.0003
SAT_DARK_DEPTH = 2
SAT_DARK_SLOTS = 3
BEYOND_AREA_DE = 18.0
BEYOND_AREA_SHARE = 0.002
BEYOND_SOFT_DE = 26.0  # past the soft limit, a color must be this far from every other
_ORIGIN = np.array([0.0, -128.0, -128.0], dtype=np.float32)


def build_palette(
    lab: np.ndarray,
    mask: np.ndarray,
    count: int | None = None,
    soft_max: int = 16,
    hard_max: int = 24,
    floor_share: float = 0.00012,
    area_power: float = 0.3,
    highlights: np.ndarray | None = None,
    highlight_slots: int = 3,
    highlight_at: int = 9,
    extras: list | None = None,
) -> PaletteInfo:
    """Deterministic farthest-point palette over a histogram of the solid pixels.

    Each step takes the color bin with the largest `distance^2 * mass^area_power`, where mass is how many
    pixels lie around that bin. The low power is the whole point: area breaks ties, distance decides. A bin
    with less mass than the floor is noise. Selection stops when nothing above the floor is far from the
    palette; `count` overrides that. More than `soft_max` colors only if something is still very far.
    """
    pixels = lab[mask]
    if pixels.shape[0] == 0:
        pixels = lab.reshape(-1, 3)
    total = pixels.shape[0]
    idx = np.clip(((pixels - _ORIGIN) / BIN).astype(np.int32), 0, None)
    shape = (45, 104, 104)
    idx = np.minimum(idx, np.array(shape) - 1)
    flat = np.ravel_multi_index(idx.T, shape)
    bins, inverse, weights = np.unique(flat, return_inverse=True, return_counts=True)
    means = np.stack([np.bincount(inverse, pixels[:, i], bins.size) / weights for i in range(3)], -1)
    hist = np.zeros(shape, dtype=np.float32)
    hist.ravel()[bins] = weights
    mass = ni.uniform_filter(hist, size=3, mode="constant").ravel()[bins] * 27.0
    floor = max(30.0, floor_share * total)
    alive = mass >= floor
    if not alive.any():
        alive[:] = True
    weights = weights.astype(np.float64)

    first = int(np.argmax(mass))
    centers = [means[first]]
    d = np.sqrt(((means - centers[0]) ** 2).sum(-1))
    spread = float(np.average(d, weights=weights) * 2.0)
    stop = float(np.clip(0.28 * spread, 5.0, STOP_DE))
    limit = hard_max if count is None else count
    worst = float(d[alive].max())
    log = [f"spread {spread:.1f} stop {stop:.1f}"]
    # Highlights: tones lighter than their surroundings. Few pixels, but the eye goes to them first.
    hl_means = None
    if highlights is not None and highlights.any():
        hl = lab[highlights]
        hl_idx = np.minimum(np.clip(((hl - _ORIGIN) / BIN).astype(np.int32), 0, None), np.array(shape) - 1)
        hl_bins, hl_inv, hl_count = np.unique(np.ravel_multi_index(hl_idx.T, shape), return_inverse=True, return_counts=True)
        hl_means = np.stack([np.bincount(hl_inv, hl[:, i], hl_bins.size) / hl_count for i in range(3)], -1)
        hl_grid = np.zeros(shape, dtype=np.float32)
        hl_grid.ravel()[hl_bins] = hl_count
        hl_mass = ni.uniform_filter(hl_grid, size=3, mode="constant").ravel()[hl_bins] * 27.0
    slots = highlight_slots if count is None else 0
    # Saturated darks: crimson shoes, a dark blue telescope. The compressed space sees them as near their dull
    # neighbors, so they are judged here in plain Lab. They do not count toward the soft limit.
    raw_means = from_perceptual(means.astype(np.float32)).astype(np.float64)
    raw_chroma = np.hypot(raw_means[:, 1], raw_means[:, 2])
    dark_saturated = alive & (raw_means[:, 0] >= SAT_DARK_MIN_L) & (raw_means[:, 0] < SAT_DARK_L) & (raw_chroma >= SAT_DARK_CHROMA) & (raw_chroma >= SAT_DARK_RATIO * raw_means[:, 0])
    protected = 0
    pinned: set[int] = set()  # highlights and saturated darks: Lloyd must not average them with what is near
    protect_left = SAT_DARK_SLOTS if count is None else 0
    # Only an area counts here. An outline's tinted edge has the same colors but no body.
    deep = ni.binary_erosion(mask, iterations=SAT_DARK_DEPTH)
    deep_idx = np.minimum(np.clip(((lab[deep] - _ORIGIN) / BIN).astype(np.int32), 0, None), np.array(shape) - 1)
    deep_grid = np.zeros(shape, dtype=np.float32)
    if deep_idx.shape[0]:
        np.add.at(deep_grid.ravel(), np.ravel_multi_index(deep_idx.T, shape), 1.0)
    deep_mass = ni.uniform_filter(deep_grid, size=3, mode="constant").ravel()[bins] * 27.0
    while len(centers) < limit:
        if hl_means is not None and slots > 0 and len(centers) >= highlight_at:
            slots -= 1
            dh = np.sqrt(((hl_means[:, None] - np.array(centers)[None]) ** 2).sum(-1)).min(1)
            ok = (hl_mass >= floor * 0.5) & (dh >= HIGHLIGHT_MIN_DE)
            if ok.any():
                s_h = dh * dh * hl_mass**area_power
                s_h[~ok] = -1
                pick_h = int(np.argmax(s_h))
                pinned.add(len(centers))
                centers.append(hl_means[pick_h])
                log.append(f"+{len(centers)} highlight d={dh[pick_h]:.1f} mass={hl_mass[pick_h] / total * 100:.3f}%")
                d = np.minimum(d, np.sqrt(((means - hl_means[pick_h]) ** 2).sum(-1)))
                continue
            slots = 0
        if protect_left > 0 and len(centers) >= highlight_at + highlight_slots - slots:
            protect_left -= 1
            raw_centers = from_perceptual(np.array(centers, dtype=np.float32)).astype(np.float64)
            d_raw = np.sqrt(((raw_means[:, None] - raw_centers[None]) ** 2).sum(-1)).min(1)
            ok = dark_saturated & (d_raw >= SAT_DARK_DE) & (deep_mass >= SAT_DARK_SHARE * total)
            if ok.any():
                # The more saturated for its lightness, the less the compressed space can see it.
                s_d = d_raw * d_raw * mass**area_power * (raw_chroma / np.maximum(raw_means[:, 0], 1.0)) ** 2
                s_d[~ok] = -1
                pick_d = int(np.argmax(s_d))
                pinned.add(len(centers))
                centers.append(means[pick_d])
                protected += 1
                log.append(f"+{len(centers)} saturated dark d={d_raw[pick_d]:.1f} mass={mass[pick_d] / total * 100:.3f}%")
                d = np.minimum(d, np.sqrt(((means - means[pick_d]) ** 2).sum(-1)))
                limit = min(limit + 1, hard_max) if count is None else limit
                continue
            protect_left = 0
        soft_now = soft_max + protected
        # The slots after the highlights go to what is left unexplained by area: a second band of sky, say.
        fill = hl_means is None or slots <= 0 or len(centers) >= highlight_at + highlight_slots
        late = count is None and fill and len(centers) >= highlight_at and len(centers) < soft_now
        score = d * d * mass ** (1.0 if late else area_power)
        score[~alive] = -1
        if late:
            # A tone close to a large color is only its grain; it must also be well away from the palette.
            score[d < FILL_MIN_DE] = -1
            if score.max() < 0:
                score = d * d * mass**area_power
                score[~alive] = -1
        pick = int(np.argmax(score))
        worst = float(d[pick]) if d[pick] > 0 else 0.0
        far = float(d[alive].max())
        if count is None:
            if far < stop:
                break
            # Past the soft limit, only something truly far earns a color.
            # Or a real area that nothing represents, such as a pair of red shoes.
            if len(centers) >= soft_now and far < BEYOND_SOFT_DE:
                if not (alive & (d >= BEYOND_AREA_DE) & (mass >= BEYOND_AREA_SHARE * total)).any():
                    break
        centers.append(means[pick])
        log.append(f"+{len(centers)} d={d[pick]:.1f} mass={mass[pick] / total * 100:.3f}%")
        d = np.minimum(d, np.sqrt(((means - means[pick]) ** 2).sum(-1)))
    seeds = np.array(centers, dtype=np.float64)
    centers = seeds.copy()

    # A few rounds of Lloyd on the bins move each center to the middle of what it explains. A small color
    # owns only its own bins, so it stays where it is.
    for _ in range(4):
        owner = ((means[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
        for k in range(len(centers)):
            hit = owner == k
            if k in pinned:
                hit = hit & (((means - seeds[k]) ** 2).sum(-1) <= PIN_RADIUS**2)
            if hit.any():
                centers[k] = np.average(means[hit], axis=0, weights=weights[hit])
    # A center between two distinct tones is a color the image does not have. Where the mean of a cell lies in
    # an empty part of the histogram, the cell takes its densest tone instead.
    owner = ((means[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
    for k in range(len(centers)):
        hit = np.nonzero(owner == k)[0]
        if hit.size == 0:
            continue
        peak = hit[int(np.argmax(mass[hit]))]
        around_mean = ((means[hit] - centers[k]) ** 2).sum(-1) <= MODE_RADIUS**2
        here = float(weights[hit][around_mean].sum())
        around_peak = ((means[hit] - means[peak]) ** 2).sum(-1) <= MODE_RADIUS**2
        there = float(weights[hit][around_peak].sum())
        if here < 0.35 * there:
            centers[k] = np.average(means[hit][around_peak], axis=0, weights=weights[hit][around_peak])
    # Lloyd can bring two centers together. They are one color then.
    merged: list[np.ndarray] = []
    owner = ((means[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
    area = np.bincount(owner, weights, len(centers))
    for k in np.argsort(-area):
        if area[k] <= 0:
            continue
        if merged and min(float(np.sqrt(((m - centers[k]) ** 2).sum())) for m in merged) < min(3.0, stop):
            continue
        merged.append(centers[k])
    centers = np.array(merged, dtype=np.float32)
    if count is None:
        centers = _prune(centers, means, weights, soft_max + protected, log)
        for extra, why in extras or ():
            if float(np.sqrt(((centers - extra) ** 2).sum(-1)).min()) >= EXTRA_MIN_DE:
                centers = np.vstack([centers, extra.astype(np.float32)])
                log.append(f"+{len(centers)} {why}")
    return PaletteInfo(centers, lab_to_srgb(from_perceptual(centers)), stop, worst, log)


def _prune(centers, means, weights, target, log) -> np.ndarray:
    """Past the soft limit, drop the smaller of a pair of colors too close to be worth one more color."""
    centers = centers.copy()
    while len(centers) > target:
        owner = ((means[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
        area = np.bincount(owner, weights, len(centers))
        raw = from_perceptual(centers).astype(np.float64)
        dist = np.sqrt(((raw[:, None] - raw[None]) ** 2).sum(-1))
        np.fill_diagonal(dist, np.inf)
        # A color that holds a real share of the image stays, however close: the ground's lit band, for one.
        droppable = (dist.min(1) < PRUNE_DE) & (area < PRUNE_MAX_AREA * weights.sum())
        # Two blacks are one black, however much of the image they hold.
        darks = raw[:, 0] < PRUNE_DARK_L
        close_dark = darks & ((dist[:, darks].min(1) < PRUNE_DARK_DE) if darks.any() else False)
        droppable = droppable | close_dark
        if not droppable.any():
            break
        small = int(np.argmin(np.where(droppable, area, np.inf)))
        log.append(f"-pruned {small} d={dist[small].min():.1f} area={area[small] / weights.sum() * 100:.3f}%")
        centers = np.delete(centers, small, axis=0)
    return centers


def assign_large(lab, transition, background, palette, smoothness: float = 5.0, rounds: int = 3) -> np.ndarray:
    """`assign` in stripes, with a margin the window and the vote cannot see past, to bound memory."""
    h, w = lab.shape[:2]
    if h * w <= STRIPE_PIXELS:
        return assign(lab, transition, background, palette, smoothness, rounds)
    rows = max(64, STRIPE_PIXELS // w)
    out = np.empty((h, w), dtype=np.int16)
    for top in range(0, h, rows):
        y0, y1 = max(0, top - STRIPE_MARGIN), min(h, top + rows + STRIPE_MARGIN)
        band = Background(background.mask[y0:y1], background.lab)
        part = assign(lab[y0:y1], transition[y0:y1], band, palette, smoothness, rounds)
        stop = min(h, top + rows)
        out[top:stop] = part[top - y0 : stop - y0]
    return out


def assign(
    lab: np.ndarray,
    transition: np.ndarray,
    background: Background,
    palette: np.ndarray,
    smoothness: float = 5.0,
    rounds: int = 3,
    window: int = 3,
) -> np.ndarray:
    """Class per pixel: palette index, or len(palette) for the background.

    Solid pixels choose freely. Transition pixels choose only among classes held by solid pixels within
    `window`, so a mix of two colors can never become a third. Neighbors then vote a little: disagreeing
    with the whole neighborhood costs `smoothness` delta-E, which clears specks between close tones and
    leaves a dark stitch alone, since its color is far from anything around it.
    """
    h, w = lab.shape[:2]
    k = len(palette)
    bg = k
    flood = background.mask
    t = transition & ~flood
    cost = np.empty((k + 1, h, w), dtype=np.float32)
    for i, c in enumerate(palette):
        diff = lab - c
        cost[i] = np.sqrt((diff * diff).sum(-1))
    if background.lab is not None:
        diff = lab - background.lab
        cost[bg] = np.sqrt((diff * diff).sum(-1))
        # The background is only reachable from the flood, so interior whites stay in the artwork.
        cost[bg][~(flood | transition)] = np.inf
    else:
        cost[bg] = np.inf
    label = np.argmin(cost, axis=0).astype(np.int16)
    label[flood] = bg

    seed = label.copy()
    seed[t] = -1
    ys, xs = np.nonzero(t)
    limited = np.full((k + 1, ys.size), np.inf, dtype=np.float32)
    size = 2 * window + 1
    for i in range(k + 1):
        m = seed == i
        if not m.any():
            continue
        near = ni.uniform_filter(m.astype(np.float32), size=size, mode="constant") > 1e-4
        ok = near[ys, xs]
        limited[i, ok] = cost[i, ys[ok], xs[ok]]
    # A transition pixel with no solid class in reach is free.
    lost = np.isinf(limited).all(0)
    if lost.any():
        limited[:, lost] = cost[:, ys[lost], xs[lost]]
    if ys.size:
        label[ys, xs] = np.argmin(limited, axis=0)
        cost[:, ys, xs] = limited
    del limited, seed

    for _ in range(rounds):
        best = np.full((h, w), np.inf, dtype=np.float32)
        new = np.zeros((h, w), dtype=np.int16)
        for i in range(k + 1):
            m = label == i
            if not m.any() and i == bg:
                continue
            share = ni.uniform_filter(m.astype(np.float32), size=3, mode="nearest")
            e = cost[i] + smoothness * (1.0 - share)
            hit = e < best
            new[hit] = i
            best[hit] = e[hit]
        new[flood] = bg
        if (new == label).all():
            break
        label = new
    return label


def highlight_mask(lab: np.ndarray, solid: np.ndarray, lift: float = 10.0, size: int = 21) -> np.ndarray:
    """Solid pixels clearly lighter than their neighborhood, the owner's definition of a highlight."""
    around = ni.uniform_filter(lab[..., 0], size=size, mode="nearest")
    return solid & (lab[..., 0] - around >= lift)


def flatten_gradients(lab: np.ndarray, edge: float = 1.5, sigma: float = 4.0, reach: float = 8.0) -> np.ndarray:
    """Blur away from edges, so that bands across a soft gradient follow the gradient and not its grain."""
    grad = np.zeros(lab.shape[:2], dtype=np.float32)
    for i in range(3):
        gy, gx = np.gradient(lab[..., i])
        grad += gx * gx + gy * gy
    edges = grad > edge * edge
    if not edges.any():
        weight = np.ones(lab.shape[:2], dtype=np.float32)
    else:
        weight = np.clip((ni.distance_transform_edt(~edges).astype(np.float32) - 2.0) / reach, 0.0, 1.0)
    blurred = np.stack([ni.gaussian_filter(lab[..., i], sigma) for i in range(3)], -1)
    return lab + (blurred - lab) * weight[..., None]


def dissolve_fringes(
    label: np.ndarray, lab: np.ndarray, palette_all: np.ndarray, max_thickness: float = 3.5, tolerance: float = 0.25
) -> tuple[np.ndarray, np.ndarray]:
    """A thin band whose color lies between the two colors either side of it is an edge, not a color.

    Returns the corrected classes and the mask of pixels that were such bands. A real thin line stays: its
    color is not on the path between its neighbors, or it has the same color on both sides.
    """
    classes = len(palette_all)
    regions, total = _regions(label, classes)
    if total == 0:
        return label, np.zeros(label.shape, bool)
    area = np.bincount(regions.ravel(), minlength=total + 1).astype(np.float64)
    region_class = np.zeros(total + 1, dtype=np.int32)
    region_class[regions.ravel()] = label.ravel()
    a = np.concatenate([regions[:, :-1].ravel(), regions[:-1, :].ravel()])
    b = np.concatenate([regions[:, 1:].ravel(), regions[1:, :].ravel()])
    hit = a != b
    a, b = a[hit], b[hit]
    froms, tos = np.concatenate([a, b]), np.concatenate([b, a])
    perimeter = np.bincount(froms, minlength=total + 1).astype(np.float64)
    thin = 2.0 * area <= max_thickness * np.maximum(perimeter, 1.0)
    thin[0] = False
    keep = thin[froms]
    pair = froms[keep].astype(np.int64) * (classes + 1) + region_class[tos[keep]]
    if pair.size == 0:
        return label, np.zeros(label.shape, bool)
    keys, counts = np.unique(pair, return_counts=True)
    owner, neighbor = keys // (classes + 1), keys % (classes + 1)
    order = np.lexsort((-counts, owner))
    owner, neighbor, counts = owner[order], neighbor[order], counts[order]
    first = np.r_[True, owner[1:] != owner[:-1]]
    index = np.cumsum(first) - 1
    second = np.r_[False, (index[1:] == index[:-1]) & first[:-1]]
    two = np.nonzero(first)[0]
    has_two = np.zeros(two.size, dtype=bool)
    second_at = np.zeros(two.size, dtype=np.int64)
    has_two[index[second]] = True
    second_at[index[second]] = np.nonzero(second)[0]
    r = owner[two][has_two]
    ca = neighbor[two][has_two]
    cb = neighbor[second_at[has_two]]
    wall = counts[two][has_two] + counts[second_at[has_two]]
    weaker = counts[second_at[has_two]]
    A, B = palette_all[ca], palette_all[cb]
    C = palette_all[region_class[r]]
    ab = B - A
    n2 = np.maximum((ab * ab).sum(-1), 1e-6)
    u = ((C - A) * ab).sum(-1) / n2
    res = np.sqrt(((C - A - u[:, None] * ab) ** 2).sum(-1))
    length = np.sqrt(n2)
    is_fringe = (u > 0.03) & (u < 0.97) & (res <= np.maximum(3.0, tolerance * length)) & (length >= 12.0) & (wall >= 0.7 * perimeter[r]) & (weaker >= 0.25 * perimeter[r])
    r, ca, cb = r[is_fringe], ca[is_fringe], cb[is_fringe]
    if r.size == 0:
        return label, np.zeros(label.shape, bool)
    map_a = np.full(total + 1, -1, dtype=np.int32)
    map_b = np.full(total + 1, -1, dtype=np.int32)
    map_a[r], map_b[r] = ca, cb
    mask = map_a[regions] >= 0
    ys, xs = np.nonzero(mask)
    ra = map_a[regions[ys, xs]]
    rb = map_b[regions[ys, xs]]
    pix = lab[ys, xs]
    da = ((pix - palette_all[ra]) ** 2).sum(-1)
    db = ((pix - palette_all[rb]) ** 2).sum(-1)
    out = label.copy()
    out[ys, xs] = np.where(da <= db, ra, rb)
    return out, mask


def dissolve_speckle(label, palette_all, max_area: int, max_de: float, radius: float, crowd: int) -> tuple[np.ndarray, int]:
    """Islands of low contrast that come in crowds are texture: speckled rock, dots inside a shadow.

    A crumb or a star stands out strongly or stands alone, so it stays. An island here has one neighbor class.
    """
    classes = len(palette_all)
    regions, total = _regions(label, classes)
    if total == 0:
        return label, 0
    area = np.bincount(regions.ravel(), minlength=total + 1)
    region_class = np.zeros(total + 1, dtype=np.int32)
    region_class[regions.ravel()] = label.ravel()
    a = np.concatenate([regions[:, :-1].ravel(), regions[:-1, :].ravel()])
    b = np.concatenate([regions[:, 1:].ravel(), regions[1:, :].ravel()])
    hit = a != b
    froms, tos = np.concatenate([a[hit], b[hit]]), np.concatenate([b[hit], a[hit]])
    small = area <= max_area
    small[0] = False
    keep = small[froms]
    pair = np.unique(froms[keep].astype(np.int64) * (classes + 1) + region_class[tos[keep]])
    owner, neighbor = pair // (classes + 1), pair % (classes + 1)
    ids, counts = np.unique(owner, return_counts=True)
    single = ids[counts == 1]
    if single.size == 0:
        return label, 0
    only = np.full(total + 1, -1, dtype=np.int32)
    is_single = np.isin(owner, single)
    only[owner[is_single]] = neighbor[is_single]
    d = np.sqrt(((palette_all[region_class[single]] - palette_all[only[single]]) ** 2).sum(-1))
    # The background is never a surround here: what floats on it is detail by definition.
    candidates = single[(d < max_de) & (only[single] != classes - 1)]
    if candidates.size < crowd + 1:
        return label, 0
    ys, xs = np.nonzero(np.isin(regions, candidates))
    r = regions[ys, xs]
    n = np.bincount(r, minlength=total + 1)
    cx = np.bincount(r, xs, total + 1)[candidates] / n[candidates]
    cy = np.bincount(r, ys, total + 1)[candidates] / n[candidates]
    tree = cKDTree(np.stack([cx, cy], -1))
    near = tree.query_ball_point(np.stack([cx, cy], -1), radius, return_length=True)
    crowded = candidates[near > crowd]
    if crowded.size == 0:
        return label, 0
    mapping = region_class.copy()
    mapping[crowded] = only[crowded]
    return mapping[regions].astype(label.dtype), int(crowded.size)


def background_extras(lab: np.ndarray, solid: np.ndarray, background: Background) -> list:
    """Two colors the background itself calls for, when the image has them.

    Interior white: pixels like the background but enclosed, so not flooded. Sticker line: a pale line that
    hugs the flood. Both are few pixels next to everything else, and both read at once when they are missing.
    """
    if background.lab is None:
        return []
    out = []
    d = np.sqrt(((lab - background.lab) ** 2).sum(-1))
    total = lab.shape[0] * lab.shape[1]
    enclosed = solid & (d <= INTERIOR_DE) & ~background.mask
    # A sticker's own fill is enclosed too; it needs a color all the more.
    if enclosed.sum() >= INTERIOR_SHARE * total:
        out.append((np.median(lab[enclosed], axis=0), "interior white"))
    near_flood = ni.binary_dilation(background.mask, iterations=LINE_REACH)
    line = near_flood & ~background.mask & (d >= LINE_MIN_DE) & (d <= LINE_MAX_DE) & (lab[..., 0] >= LINE_MIN_L)
    line &= np.hypot(lab[..., 1], lab[..., 2]) <= LINE_MAX_CHROMA
    line &= solid
    # A sticker's line runs on and on. An edge's halo comes in short pieces.
    if line.any():
        parts, count = ni.label(line, structure=np.ones((3, 3), bool))
        sizes = np.bincount(parts.ravel())
        sizes[0] = 0
        line = sizes[parts] >= LINE_PIECE * total
    # The middle of the line, where it is darkest: its sides are a mix with the background.
    if line.sum() >= LINE_SHARE * total:
        pixels = lab[line]
        cut = np.percentile(pixels[:, 0], 40)
        out.append((np.median(pixels[pixels[:, 0] <= cut], axis=0), "sticker line"))
    return out


def settle_colors(palette: np.ndarray, label: np.ndarray, lab: np.ndarray, solid: np.ndarray) -> np.ndarray:
    """Each color becomes the median of the solid pixels it ended up with, so it is a tone the area really has."""
    out = palette.copy()
    for i in range(len(palette)):
        m = (label == i) & solid
        if m.sum() < 8:
            continue
        pixels = lab[m]
        out[i] = np.median(pixels[:: max(1, pixels.shape[0] // 100_000)], axis=0)
    return out


def upsample_lab(lab: np.ndarray) -> np.ndarray:
    """Twice the size, bilinear, with each new pixel a quarter of an old pixel in from its corner."""
    h, w = lab.shape[:2]
    y2 = np.repeat(np.arange(h), 2)
    x2 = np.repeat(np.arange(w), 2)
    near_y = np.clip(y2 + np.tile([-1, 1], h), 0, h - 1)
    near_x = np.clip(x2 + np.tile([-1, 1], w), 0, w - 1)
    ly = 0.75 * lab[y2] + 0.25 * lab[near_y]
    return 0.75 * ly[:, x2] + 0.25 * ly[:, near_x]


def refine_double(label: np.ndarray, lab: np.ndarray, palette: np.ndarray, background_lab) -> tuple[np.ndarray, np.ndarray]:
    """Class map at twice the size. Along walls each new pixel takes the closest class of its parents."""
    fine_lab = upsample_lab(lab)
    k = len(palette)
    fine = np.repeat(np.repeat(label, 2, axis=0), 2, axis=1)
    lo = ni.minimum_filter(fine, size=3, mode="nearest")
    hi = ni.maximum_filter(fine, size=3, mode="nearest")
    band = lo != hi
    ys, xs = np.nonzero(band)
    colors = fine_lab[ys, xs]
    best = np.full(ys.size, np.inf, dtype=np.float32)
    out = fine[ys, xs].copy()
    all_colors = np.vstack([palette, background_lab if background_lab is not None else np.full((1, 3), 1e4)])
    for i in range(k + 1):
        m = fine == i
        if not m.any():
            continue
        ok = ni.binary_dilation(m, structure=np.ones((3, 3), bool))[ys, xs]
        diff = colors[ok] - all_colors[i]
        d = (diff * diff).sum(-1)
        which = np.nonzero(ok)[0]
        hit = d < best[which]
        best[which[hit]] = d[hit]
        out[which[hit]] = i
    fine[ys, xs] = out
    return fine, fine_lab


def _regions(label: np.ndarray, classes: int) -> tuple[np.ndarray, int]:
    """Number the 4-connected pieces of each class, from 1."""
    regions = np.zeros(label.shape, dtype=np.int32)
    total = 0
    for c in range(classes):
        m = label == c
        if not m.any():
            continue
        part, count = ni.label(m)
        regions[m] = part[m] + total
        total += count
    return regions, total


def absorb_specks(
    label, palette_all, min_area: int, keep_area: int, keep_de: float, rounds: int = 4,
    faint_area: int = 0, faint_de: float = 0.0,
) -> np.ndarray:
    """Hand small pieces to the neighbor closest in color. A small piece that stands out keeps a lower limit.

    A piece up to `faint_area` also goes when it barely differs from a neighbor: such blotches are texture.
    """
    classes = len(palette_all)
    base_area = min_area
    min_area = max(min_area, faint_area)
    for _ in range(rounds):
        regions, total = _regions(label, classes)
        if total == 0:
            break
        area = np.bincount(regions.ravel(), minlength=total + 1)
        small = area < min_area
        small[0] = False
        if not small.any():
            break
        region_class = np.zeros(total + 1, dtype=np.int32)
        region_class[regions.ravel()] = label.ravel()
        a = np.concatenate([regions[:, :-1].ravel(), regions[:-1, :].ravel()])
        b = np.concatenate([regions[:, 1:].ravel(), regions[1:, :].ravel()])
        hit = a != b
        a, b = a[hit], b[hit]
        froms = np.concatenate([a, b])
        tos = np.concatenate([b, a])
        keep = small[froms]
        froms, tos = froms[keep], tos[keep]
        if froms.size == 0:
            break
        to_class = region_class[tos]
        d = np.sqrt(((palette_all[region_class[froms]] - palette_all[to_class]) ** 2).sum(-1))
        # Closest class first; ties go to the longer shared wall.
        order = np.lexsort((tos, d, froms))
        froms_sorted = froms[order]
        first = np.r_[True, froms_sorted[1:] != froms_sorted[:-1]]
        target = np.arange(total + 1)
        mapping_from = froms_sorted[first]
        mapping_to = to_class[order][first]
        mapping_d = d[order][first]
        # Absorbing shrinks what is left, smallest first, so a pair of specks does not swap.
        changed = False
        class_of = region_class.copy()
        for r, c, dist in zip(mapping_from.tolist(), mapping_to.tolist(), mapping_d.tolist()):
            if area[r] >= base_area and dist >= faint_de:
                continue
            if dist >= keep_de and area[r] >= keep_area:
                continue
            class_of[r] = c
            changed = True
        if not changed:
            break
        label = class_of[regions].astype(label.dtype)
        del target
    return label
