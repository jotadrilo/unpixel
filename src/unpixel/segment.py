"""Split an image into flat color regions plus an optional transparent background.

The hard cases this module exists for:

* Anti-aliased edges pass through colors that are not in the artwork. Classifying in
  Lab keeps a navy/white transition from being mistaken for red.
* Two pale colors (white paper, cream card) are too close to separate per pixel without
  leaving a false ring around dark outlines. They are classified together as one
  *group*, and connected regions of the group are then colored as a whole.
* "Transparent" must only reach the background, not every pixel that resembles it, so
  the background is the set of regions connected to the image border.
* Soft or upscaled sources lose contrast in thin lines. A sharpening pass restores them
  before thresholding. Work happens at a fixed artwork resolution, so the same constants
  suit a 500 px icon and an 8000 px poster, and smoothing stays visually negligible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage as ni
from scipy.spatial import Delaunay, QhullError

from .color import delta_e, parse_hex, srgb_to_lab, to_hex

# Long side, in working pixels, that the scale constants below are tuned for.
TARGET_LONG_SIDE = 6400
MAX_UPSCALE = 4.0
MAX_WORKING_PIXELS = 40_000_000
PRE_BLUR = 1.2
UNSHARP_SIGMA = 10.0
UNSHARP_AMOUNT = 2.0
FLAT_GRADIENT = 2.0  # delta-E per working pixel below which a pixel counts as flat
HIST_BIN = 4.0
HIST_SMOOTH_BINS = 1.5
MAX_PEAKS = 48
GROUP_DE = 20.0  # peaks this close are classified together and then separated by region
GROUP_MIN_SHARE = 0.001
CLUSTER_DE = 8.0  # regions this close are the same color
MINOR_CLUSTER_SHARE = 0.005
MINOR_CLUSTER_DE = 20.0
DUPLICATE_DE = 4.0
MAX_AUTO_COLORS = 16
FRINGE_DE = 12.0
ISLAND_DE = 5.0  # an island this close to its only neighbor is a sharpening artifact, not a thin line
UNEXPLAINED_DE = 18.0
UNEXPLAINED_BIN = 2.0
RIDGE_GRADIENT = 3.0
UNEXPLAINED_MIN_SHARE = 0.0003
MAX_EXPLAINED_CENTERS = 12
SPLIT_MIN_DE = 7.0  # one region with two sides this far apart is two colors
SPLIT_MIN_SHARE = 0.05
SPLIT_MAX_MIDDLE = 0.1
SPLIT_COHERENCE = 0.6
BORDER_SHARE = 0.85
BACKGROUND_MATCH_DE = 15.0
TRANSPARENT_MATCH_DE = 8.0
MAX_REGIONS = 20_000
MIN_FLAT_SHARE = 0.5  # of the artwork; below this, warn that tones will be flattened
REJECT_FLAT_SHARE = 0.25  # of the artwork; below this, it is not flat-color art at all
DETAIL_FACTORS = {"low": 1.5, "medium": 1.0, "high": 0.6}
BASE_SMOOTH = 3.0
BASE_SPECK = 40


class UnsuitableImage(Exception):
    """The image is not flat-color artwork (photo, gradients, heavy texture)."""


class InvalidRequest(Exception):
    """The options cannot produce a result for this image."""


@dataclass
class Segmentation:
    labels: np.ndarray  # working-scale class per pixel; -1 means transparent
    raw_labels: np.ndarray  # same classes before smoothing, used for verification
    colors: list[tuple[int, int, int]]
    scale: float
    speck_area: int
    flat: np.ndarray  # working-scale mask of pixels away from any edge
    background: str | None
    warnings: list[str] = field(default_factory=list)


_TILE = 256
import os as _os
_THREADS = int(_os.environ.get("UNPIXEL_THREADS", "1"))


def _pmap(fn, jobs):
    if _THREADS <= 1:
        return [fn(j) for j in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(_THREADS) as ex:
        return list(ex.map(fn, jobs))


def _gauss_rgb(rgb: np.ndarray, sigma: float) -> np.ndarray:
    return np.stack([ni.gaussian_filter(rgb[..., i], sigma) for i in range(3)], axis=-1)


def _sq3(d):
    return d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2]


def _find_groups(flat_lab: np.ndarray) -> np.ndarray:
    """Return one Lab center per group of close flat colors.

    Colors are the peaks of a smoothed histogram. Nearby peaks join one group, but a group's
    diameter is limited, so a continuous range of tones cannot chain into a single group.
    """
    origin = np.array([0.0, -128.0, -128.0], dtype=np.float32)
    idx = np.clip(((flat_lab - origin) / HIST_BIN).astype(int), 0, None)
    shape = tuple(idx.max(0) + 1)
    hist = np.zeros(shape, dtype=np.float32)
    np.add.at(hist, tuple(idx.T), 1.0)
    smooth = ni.gaussian_filter(hist, HIST_SMOOTH_BINS, mode="constant")
    peaks = (smooth == ni.maximum_filter(smooth, size=3)) & (hist > 0)
    coords = np.argwhere(peaks)
    order = np.argsort(-smooth[peaks])[:MAX_PEAKS]
    peak_lab = coords[order] * HIST_BIN + origin + HIST_BIN / 2
    sample = flat_lab[:: max(1, flat_lab.shape[0] // 500_000)]
    owner = delta_e(sample[:, None, :], peak_lab[None, :, :]).argmin(1)
    keep = [i for i in range(len(peak_lab)) if (owner == i).mean() >= GROUP_MIN_SHARE]
    if not keep:
        return np.zeros((0, 3), dtype=np.float32)
    peak_lab = peak_lab[keep]
    owner = delta_e(sample[:, None, :], peak_lab[None, :, :]).argmin(1)
    groups = [[i] for i in range(len(peak_lab))]
    while True:
        best = None
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                reach = max(float(delta_e(peak_lab[p], peak_lab[q])) for p in groups[i] for q in groups[j])
                if reach <= GROUP_DE and (best is None or reach < best[0]):
                    best = (reach, i, j)
        if best is None:
            break
        groups[best[1]] += groups.pop(best[2])
    return np.array(
        [np.median(sample[np.isin(owner, members)], axis=0) for members in groups], dtype=np.float32
    )


def _add_unexplained_colors(lab: np.ndarray, rgb: np.ndarray, grad: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Add colors that thin strokes carry but flat areas do not.

    A thin line has almost no pixels away from an edge, so looking only at flat areas can miss
    its color entirely. Pixels that no sRGB mix of two known colors can explain may belong to a
    color not found yet. Edges of real images also carry halos that are not pure mixes, but those
    sit on a slope, while the center of a stroke is a ridge. So only low-gradient pixels count.
    """
    ridge = grad[::3, ::3] <= RIDGE_GRADIENT
    sample_lab = lab[::3, ::3][ridge]
    sample_rgb = rgb[::3, ::3][ridge]
    if sample_lab.shape[0] == 0:
        return centers
    # Comparing distinct colors instead of pixels keeps this fast on large images.
    keys, index, counts = np.unique(
        np.round(sample_lab / UNEXPLAINED_BIN).astype(np.int32), axis=0, return_index=True, return_counts=True
    )
    distinct = sample_lab[index]
    weights = np.asarray(counts, dtype=np.float64)
    del keys
    steps = np.linspace(0.0, 1.0, 17)[:, None, None]
    for _ in range(3):
        if centers.shape[0] >= MAX_EXPLAINED_CENTERS:
            break
        anchors = np.stack(
            [sample_rgb[d <= d.min() + 9.0].mean(0)
             for d in (_sq3(sample_lab - c) for c in centers)]
        ).astype(np.float32)
        left, right = np.triu_indices(centers.shape[0])
        mixes = srgb_to_lab((anchors[left][None] * (1 - steps) + anchors[right][None] * steps).reshape(-1, 3))
        worst = np.full(distinct.shape[0], np.inf, dtype=np.float32)
        for mix in mixes:
            worst = np.minimum(worst, _sq3(distinct - mix))
        far = np.sqrt(worst) > UNEXPLAINED_DE
        # A blend of three or more known colors, as in a thin line between two regions, stays inside
        # the range of those colors. A stroke in a genuinely new color falls outside it.
        try:
            far &= Delaunay(centers.astype(np.float64)).find_simplex(distinct) < 0
        except (QhullError, ValueError):  # too few colors, or all on one plane, to define a volume
            pass
        if weights[far].sum() < UNEXPLAINED_MIN_SHARE * ridge.size:
            break
        found = _find_groups(np.repeat(distinct[far], np.minimum(counts[far], 2000), axis=0))
        if found.shape[0] == 0:
            break
        centers = np.vstack([centers, found]).astype(np.float32)
    return centers


def _nearest(lab: np.ndarray, centers: np.ndarray) -> np.ndarray:
    out = np.zeros(lab.shape[:2], dtype=np.int16)

    def work(y):
        sub = lab[y:y + 128]
        o = out[y:y + 128]
        best = np.full(sub.shape[:2], np.inf, dtype=np.float32)
        for i, center in enumerate(centers):
            dist = _sq3(sub - center)
            hit = dist < best
            o[hit] = i
            best[hit] = dist[hit]

    _pmap(work, range(0, lab.shape[0], 128))
    return out


def _label_regions(groups: np.ndarray) -> tuple[np.ndarray, int]:
    regions = np.zeros(groups.shape, dtype=np.int32)
    total = 0
    for gid in np.unique(groups):
        part, count = ni.label(groups == gid)
        regions[part > 0] = part[part > 0] + total
        total += count
    return regions, total


def _try_split(lab_box: np.ndarray, flat_box: np.ndarray):
    """Detect one region holding two spatially coherent colors, as with no outline between them."""
    samples = lab_box[flat_box]
    if samples.shape[0] > 200_000:
        samples = samples[:: samples.shape[0] // 200_000]
    mean = samples.mean(0)
    _, _, vt = np.linalg.svd((samples - mean)[:: max(1, samples.shape[0] // 5000)], full_matrices=False)
    proj = (samples - mean) @ vt[0]
    a, b = samples[proj.argmin()], samples[proj.argmax()]
    for _ in range(8):
        side = _sq3(samples - a) > _sq3(samples - b)
        if side.all() or not side.any():
            return None
        a, b = samples[~side].mean(0), samples[side].mean(0)
    if float(delta_e(a, b)) < SPLIT_MIN_DE or min(side.mean(), 1 - side.mean()) < SPLIT_MIN_SHARE:
        return None
    # Two real colors leave few pixels in between. A smooth gradient is full of them.
    axis = b - a
    position = (samples - a) @ axis / float(axis @ axis)
    if ((position > 1 / 3) & (position < 2 / 3)).mean() > SPLIT_MAX_MIDDLE:
        return None
    full = _sq3(lab_box - a) > _sq3(lab_box - b)
    for piece in (flat_box & full, flat_box & ~full):
        parts, count = ni.label(piece)
        if count == 0:
            return None
        sizes = np.bincount(parts.ravel())[1:]
        if sizes.max() < SPLIT_COHERENCE * piece.sum():
            return None
    return a, b, full


def _split_mixed_regions(groups, regions, count, lab, flat, min_flat, centers):
    objects = ni.find_objects(regions)
    flat_counts = np.bincount(regions[flat], minlength=count + 1)
    changed = False
    centers = list(centers)
    for rid in np.nonzero(flat_counts >= min_flat)[0]:
        if rid == 0:
            continue
        box = objects[rid - 1]
        mask = regions[box] == rid
        found = _try_split(lab[box], mask & flat[box])
        if found is None:
            continue
        a, b, side = found
        group = int(groups[box][mask][0])
        centers[group] = a
        centers.append(b)
        groups[box][mask & side] = len(centers) - 1
        changed = True
    return changed, np.array(centers, dtype=np.float32)


def _cluster_regions(means, weights, solid):
    """Greedily cluster solid regions, largest first. Returns (region -> cluster, centers)."""
    assign = np.full(means.shape[0], -1, dtype=np.int32)
    centers: list[np.ndarray] = []
    totals: list[float] = []
    for rid in np.argsort(-weights):
        if not solid[rid]:
            continue
        if centers:
            dist = delta_e(np.array(centers), means[rid])
            near = int(dist.argmin())
            if dist[near] <= CLUSTER_DE:
                assign[rid] = near
                totals[near] += float(weights[rid])
                centers[near] += (means[rid] - centers[near]) * float(weights[rid]) / totals[near]
                continue
        assign[rid] = len(centers)
        centers.append(means[rid].astype(np.float64).copy())
        totals.append(float(weights[rid]))
    return assign, np.array(centers, dtype=np.float32).reshape(-1, 3)


def _rim(mask: np.ndarray) -> np.ndarray:
    d = mask.copy()
    d[1:] |= mask[:-1]
    d[:-1] |= mask[1:]
    d[:, 1:] |= mask[:, :-1]
    d[:, :-1] |= mask[:, 1:]
    return d & ~mask


def _remove_specks(labels: np.ndarray, min_area: int) -> np.ndarray:
    """Give regions smaller than min_area to their most common neighbor."""
    regions, count = _label_regions(labels)
    if count == 0:
        return labels
    sizes = np.bincount(regions.ravel(), minlength=count + 1)
    objects = ni.find_objects(regions)
    h, w = labels.shape
    for rid in np.nonzero(sizes < min_area)[0]:
        if rid == 0 or objects[rid - 1] is None:
            continue
        ys, xs = objects[rid - 1]
        box = (slice(max(ys.start - 1, 0), min(ys.stop + 1, h)), slice(max(xs.start - 1, 0), min(xs.stop + 1, w)))
        mask = regions[box] == rid
        rim = _rim(mask)
        if not rim.any():
            continue
        values, counts = np.unique(labels[box][rim], return_counts=True)
        labels[box][mask] = values[counts.argmax()]
    return labels


def _dissolve_fringes(raw, base, flat, colors, background_rgb, min_flat) -> np.ndarray:
    """Remove false colors along edges.

    An edge between two colors can pass close to an unrelated third. A region with no flat
    core whose color is explained as a mix of its two neighbors is such an edge. A real thin
    line is not, since its color is not on the path between the colors either side of it.
    Colors are judged on the unsharpened image, because sharpening can cause these regions.
    """
    palette = {i: np.array(c, dtype=np.float32) for i, c in enumerate(colors)}
    if background_rgb is not None:
        palette[-1] = np.array(background_rgb, dtype=np.float32)
    regions, count = _label_regions(raw)
    flat_counts = np.bincount(regions[flat], minlength=count + 1)
    objects = ni.find_objects(regions)
    h, w = raw.shape
    mix = np.linspace(0.0, 1.0, 21)[:, None]
    path_cache, own_cache = {}, {}
    for rid in np.nonzero(flat_counts < min_flat)[0]:
        if rid == 0 or objects[rid - 1] is None:
            continue
        ys, xs = objects[rid - 1]
        box = (slice(max(ys.start - 1, 0), min(ys.stop + 1, h)), slice(max(xs.start - 1, 0), min(xs.stop + 1, w)))
        mask = regions[box] == rid
        rim = _rim(mask)
        values, counts = np.unique(raw[box][rim], return_counts=True)
        values = values[np.argsort(-counts)][:2]
        own = int(raw[box][mask][0])
        if len(values) == 0 or any(int(v) not in palette for v in values) or own == -1:
            continue
        # With one neighbor the "path" is that color: an island sharpening pushed off its true color.
        single = len(values) == 1
        values = np.array([values[0], values[-1]])
        a, b = palette[int(values[0])], palette[int(values[1])]
        mean = srgb_to_lab(base[box][mask].mean(0))
        key = (int(values[0]), int(values[1]))
        path = path_cache.get(key)
        if path is None:
            path = path_cache[key] = srgb_to_lab(a * (1 - mix) + b * mix)
        to_path = float(delta_e(path, mean).min())
        limit = ISLAND_DE if single else FRINGE_DE
        if own not in own_cache:
            own_cache[own] = srgb_to_lab(palette[own])
        if to_path <= limit and to_path < float(delta_e(own_cache[own], mean)):
            closer_a = ((base[box][mask] - a) ** 2).sum(-1) <= ((base[box][mask] - b) ** 2).sum(-1)
            raw[box][mask] = np.where(closer_a, values[0], values[1])
    return raw


def _smooth_partition(labels: np.ndarray, classes: list[int], sigma: float) -> np.ndarray:
    """Smooth region outlines. Taking the strongest class per pixel leaves no gaps or overlaps."""
    radius = int(4.0 * sigma + 0.5)  # scipy's default truncate
    tile = _TILE
    h, w = labels.shape
    out = labels.copy()
    jobs = [(y, x) for y in range(0, h, tile) for x in range(0, w, tile)]
    order = {c: i for i, c in enumerate(classes)}

    def work(job):
        y0, x0 = job
        y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
        Y0, X0, Y1, X1 = max(y0 - radius, 0), max(x0 - radius, 0), min(y1 + radius, h), min(x1 + radius, w)
        crop = labels[Y0:Y1, X0:X1]
        lo, hi = int(crop.min()), int(crop.max())
        if lo == hi:
            out[y0:y1, x0:x1] = lo
            return
        here = sorted(np.unique(crop).tolist(), key=order.__getitem__)
        cy, cx = slice(y0 - Y0, y1 - Y0), slice(x0 - X0, x1 - X0)
        best = np.full((y1 - y0, x1 - x0), -1.0, dtype=np.float32)
        res = out[y0:y1, x0:x1]
        for cls in here:
            soft = ni.gaussian_filter((crop == cls).astype(np.float32), sigma)[cy, cx]
            hit = soft > best
            res[hit] = cls
            best[hit] = soft[hit]

    _pmap(work, jobs)
    return out


def segment(rgb: np.ndarray, options) -> Segmentation:
    warnings: list[str] = []
    height, width = rgb.shape[:2]
    long_side = max(width, height)
    scale = min(max(TARGET_LONG_SIDE / long_side, 1.0), MAX_UPSCALE)
    scale = min(scale, max(1.0, (MAX_WORKING_PIXELS / (width * height)) ** 0.5))
    if scale > 1.0:
        size = (int(round(width * scale)), int(round(height * scale)))
        rgb = np.asarray(Image.fromarray(rgb).resize(size, Image.BICUBIC))
    factor = float(np.clip(long_side / TARGET_LONG_SIDE, 1.0, 2.5))  # only very large images need more
    detail = DETAIL_FACTORS[options.detail]
    speck_area = max(4, int(BASE_SPECK * (factor * detail) ** 2))

    base = _gauss_rgb(rgb.astype(np.float32), PRE_BLUR * factor)
    lab = srgb_to_lab(base)
    grad = np.zeros(lab.shape[:2], dtype=np.float32)
    for i in range(3):
        gy, gx = np.gradient(lab[..., i])
        grad += gx * gx + gy * gy
    grad = np.sqrt(grad)
    edges = grad > FLAT_GRADIENT
    flat = ~ni.binary_dilation(edges, iterations=max(1, int(round(2 * factor))))
    if flat.mean() < 0.02:
        raise UnsuitableImage("almost no flat color areas found; this looks like a photo or a gradient")

    samples = lab[flat]
    if samples.shape[0] > 3_000_000:
        samples = samples[:: samples.shape[0] // 3_000_000]
    centers = _find_groups(samples)
    if centers.shape[0] == 0:
        raise UnsuitableImage("no dominant flat colors found")
    centers = _add_unexplained_colors(lab, base, grad, centers)
    del grad

    blurred = base + UNSHARP_AMOUNT * (base - _gauss_rgb(base, UNSHARP_SIGMA * factor))
    sharp_lab = srgb_to_lab(np.clip(blurred, 0, 255))
    del blurred, samples
    groups = _nearest(sharp_lab, centers)
    del sharp_lab

    min_flat = int(2500 * factor**2)
    for _ in range(3):
        regions, count = _label_regions(groups)
        real = int((np.bincount(regions.ravel(), minlength=count + 1)[1:] >= speck_area).sum())
        if real > MAX_REGIONS:
            raise UnsuitableImage(f"{real} separate regions found; this looks like a photo or heavy texture")
        changed, centers = _split_mixed_regions(groups, regions, count, lab, flat, min_flat, centers)
        if not changed:
            break
    else:
        regions, count = _label_regions(groups)

    # Per-region statistics over flat pixels. Index 0 of the bincounts is unused.
    flat_ids = regions[flat]
    weights = np.bincount(flat_ids, minlength=count + 1).astype(np.float64)
    safe = np.maximum(weights, 1.0)
    means = np.stack(
        [np.bincount(flat_ids, weights=lab[..., i][flat], minlength=count + 1) / safe for i in range(3)], axis=-1
    ).astype(np.float32)
    region_group = np.zeros(count + 1, dtype=np.int16)
    region_group[regions.ravel()] = groups.ravel()
    solid = weights >= max(1, int(400 * factor**2))
    solid[0] = False

    # Background: regions on the border that share the dominant border color.
    ring = np.r_[regions[0], regions[-1], regions[:, 0], regions[:, -1]]
    ring_ids, ring_counts = np.unique(ring, return_counts=True)
    background_ids: list[int] = []
    background_lab = None
    if options.background != "keep":
        if options.background == "auto":
            lead = int(ring_ids[ring_counts.argmax()])
            background_lab = means[lead] if weights[lead] > 0 else None
        else:
            background_lab = srgb_to_lab(np.array(options.background_rgb, dtype=np.float32))
        if background_lab is not None:
            hits = np.array(
                [weights[r] > 0 and float(delta_e(means[r], background_lab)) <= (
                    CLUSTER_DE if options.background == "auto" else BACKGROUND_MATCH_DE) for r in ring_ids]
            )
            share = ring_counts[hits].sum() / ring_counts.sum()
            if options.background == "auto" and share < BORDER_SHARE:
                warnings.append(
                    f"The image border is not one uniform color (dominant color covers {share:.0%}), so no "
                    "background was removed. Pass --background '#RRGGBB' to name it."
                )
            elif not hits.any():
                warnings.append("The requested background color was not found on the image border; nothing removed.")
            else:
                background_ids = [int(r) for r in ring_ids[hits]]
                background_lab = np.average(means[background_ids], axis=0, weights=weights[background_ids] + 1)
    is_background = np.zeros(count + 1, dtype=bool)
    is_background[background_ids] = True
    background_hex = None
    if background_ids:
        pixels = base[np.isin(regions, background_ids) & flat]
        background_hex = to_hex(np.median(pixels[:: max(1, pixels.shape[0] // 200_000)], axis=0))

    artwork = ~np.isin(regions, background_ids)
    flat_share = float((flat & artwork).sum()) / max(1, int(artwork.sum()))
    if flat_share < REJECT_FLAT_SHARE:
        raise UnsuitableImage(
            f"only {flat_share:.0%} of the artwork is flat color; this looks like a photo or a shaded painting"
        )

    # Colors: cluster solid interior regions, then attach the small ones to their group.
    interior_solid = solid & ~is_background
    assign, cluster_lab = _cluster_regions(means, weights, interior_solid)
    if cluster_lab.shape[0] == 0:
        raise UnsuitableImage("no artwork found: the image is a single flat color")
    cluster_group: dict[int, list[int]] = {}
    for rid in np.nonzero(assign >= 0)[0]:
        cluster_group.setdefault(int(region_group[rid]), [])
        if int(assign[rid]) not in cluster_group[int(region_group[rid])]:
            cluster_group[int(region_group[rid])].append(int(assign[rid]))
    # Sharpening can pull a band of one color into another color's group. That cluster does not
    # describe the group, so it must not be offered to the group's real thin strokes.
    for gid, members_of_group in list(cluster_group.items()):
        kept = [c for c in members_of_group if float(delta_e(cluster_lab[c], centers[gid])) <= GROUP_DE]
        if kept:
            cluster_group[gid] = kept
        else:
            del cluster_group[gid]
    # A color used only in thin strokes has no solid region, but it is still a color.
    # Slivers enclosed in the background's own group are not a color of their own.
    sizes = np.bincount(regions.ravel(), minlength=count + 1)
    background_groups = set(region_group[background_ids].tolist()) if background_ids else set()
    for gid in range(centers.shape[0]):
        members = (region_group == gid) & ~is_background
        members[0] = False
        if gid not in cluster_group and gid not in background_groups and sizes[members].sum() >= speck_area:
            cluster_group[gid] = [cluster_lab.shape[0]]
            cluster_lab = np.vstack([cluster_lab, centers[gid]]).astype(np.float32)
    for rid in range(1, count + 1):
        if assign[rid] >= 0 or is_background[rid]:
            continue
        options_here = cluster_group.get(int(region_group[rid]))
        reference = means[rid] if weights[rid] > 0 else centers[region_group[rid]]
        if options_here:
            dist = delta_e(cluster_lab[options_here], reference)
            assign[rid] = options_here[int(dist.argmin())]
        else:
            assign[rid] = int(delta_e(cluster_lab, reference).argmin())

    # Final color per cluster, taken from the source rather than the sharpened copy.
    cluster_of_region = assign.copy()
    cluster_of_region[0] = -1
    pixel_cluster = cluster_of_region[regions]
    pixel_cluster[np.isin(regions, background_ids)] = -1
    k = cluster_lab.shape[0]
    rgbs = []
    areas = []
    for c in range(k):
        mask = pixel_cluster == c
        areas.append(int(mask.sum()))
        picked = base[mask & flat]
        if picked.shape[0] < 50:  # thin strokes: use their core, as their edges are mixed with neighbors
            picked = base[mask]
            if picked.shape[0]:
                closeness = delta_e(srgb_to_lab(picked), cluster_lab[c])
                picked = picked[closeness <= np.median(closeness)]
        rgbs.append(np.median(picked[:: max(1, picked.shape[0] // 200_000)], axis=0) if picked.size else np.zeros(3))
    rgbs = np.array(rgbs, dtype=np.float32)

    # A trace color very close to a much larger one is drift within that color, not a color.
    mapping = np.arange(k)
    rgb_lab = srgb_to_lab(rgbs)
    total_area = sum(areas)
    for c in sorted(range(k), key=lambda i: areas[i]):
        if areas[c] >= MINOR_CLUSTER_SHARE * total_area:
            continue
        larger = [o for o in range(k) if areas[o] > areas[c] and mapping[o] == o]
        if larger:
            dist = delta_e(rgb_lab[larger], rgb_lab[c])
            if dist.min() <= MINOR_CLUSTER_DE:
                mapping[mapping == c] = larger[int(dist.argmin())]

    # Regions can drift into separate clusters and still measure as one color.
    for c in sorted(range(k), key=lambda i: -areas[i]):
        for o in range(k):
            if o != c and mapping[o] == o and mapping[c] == c and areas[o] <= areas[c]:
                if float(delta_e(rgb_lab[c], rgb_lab[o])) <= DUPLICATE_DE:
                    mapping[mapping == o] = c

    # Decide transparency on the colors found in the image, before any requested recoloring.
    removed_reps: set[int] = set()
    for rgb_value in options.also_transparent:
        target = srgb_to_lab(np.array(rgb_value, dtype=np.float32))
        hit = [c for c in set(mapping.tolist()) if float(delta_e(rgb_lab[c], target)) <= TRANSPARENT_MATCH_DE]
        if not hit:
            warnings.append(f"--also-transparent {to_hex(rgb_value)} matched no color in the image.")
        removed_reps.update(hit)
    is_removed = np.isin(mapping, list(removed_reps))
    if is_removed.all():
        raise InvalidRequest("--also-transparent would remove every color in the image")

    # An image with more colors than the automatic limit is reduced to it, by the path a count takes.
    color_count = options.color_count
    if not options.palette and color_count is None and len(set(mapping[~is_removed].tolist())) > MAX_AUTO_COLORS:
        found = len(set(mapping[~is_removed].tolist()))
        color_count = MAX_AUTO_COLORS
        warnings.append(
            f"{found} colors found, so the {MAX_AUTO_COLORS} most relevant were kept. "
            "Shading and gradients were flattened; pass --colors N to choose another count."
        )

    # User palette and color-count requests only change which color each cluster becomes.
    if color_count is not None:
        labs = rgb_lab.astype(np.float64)
        alive = {c: 0.0 for c in set(mapping[~is_removed].tolist())}
        for c in range(k):
            if not is_removed[c]:
                alive[int(mapping[c])] += float(max(areas[c], 1))
        # A speck-sized color must not take a slot from a real one, however different it looks.
        if len(alive) > color_count:
            floor = MINOR_CLUSTER_SHARE * sum(alive.values())
            for tiny in sorted((c for c in alive if alive[c] < floor), key=lambda c: alive[c]):
                others = [c for c in alive if c != tiny and alive[c] >= floor]
                if others and len(alive) > color_count:
                    nearest = others[int(delta_e(labs[others], labs[tiny]).argmin())]
                    alive[nearest] += alive.pop(tiny)
                    mapping[mapping == tiny] = nearest
        if len(alive) < color_count:
            warnings.append(f"Asked for {color_count} colors but only {len(alive)} were found.")
        while len(alive) > color_count:
            keys = list(alive)
            pairs = [(float(delta_e(labs[p], labs[q])), p, q) for i, p in enumerate(keys) for q in keys[i + 1:]]
            _, p, q = min(pairs)
            keep, drop = (p, q) if alive[p] >= alive[q] else (q, p)
            alive[keep] += alive.pop(drop)
            mapping[mapping == drop] = keep
    source_mapping = mapping.copy()  # the image's own colors, before recoloring
    source_reps = sorted(set(source_mapping[~is_removed].tolist()))
    final_rgbs = rgbs
    if options.palette:
        palette = np.array(options.palette, dtype=np.float32)
        pal_lab = srgb_to_lab(palette)
        dist = np.stack([delta_e(pal_lab, rgb_lab[c]) for c in range(k)])
        chosen = dist.argmin(1)
        for c in sorted(set(mapping[~is_removed].tolist())):
            if dist[c, chosen[c]] > 25 and len(palette) > 1:
                warnings.append(f"Detected color {to_hex(rgbs[c])} is far from every --colors value; "
                                f"it became {to_hex(palette[chosen[c]])}.")
        mapping = chosen[mapping]
        final_rgbs = palette
        for i in set(range(len(palette))) - set(mapping[~is_removed].tolist()):
            warnings.append(f"--colors value {to_hex(palette[i])} did not match anything in the image.")

    used = sorted(set(mapping[~is_removed].tolist()))
    remap = {old: new for new, old in enumerate(used)}
    colors = [tuple(int(round(float(v))) for v in final_rgbs[old]) for old in used]
    lookup = np.array([-1 if is_removed[c] else remap[int(mapping[c])] for c in range(k)] + [-1], dtype=np.int16)
    raw = lookup[pixel_cluster]  # -1 indexes the trailing transparent entry
    if len(source_reps) > 1:
        # False edge colors are judged on what the image contains, so this happens before recoloring.
        position = {rep: i for i, rep in enumerate(source_reps)}
        source_lookup = np.array(
            [-1 if is_removed[c] else position[int(source_mapping[c])] for c in range(k)] + [-1], dtype=np.int16
        )
        source_raw = source_lookup[pixel_cluster]
        bg_rgb = parse_hex(background_hex) if background_hex else None
        source_colors = [tuple(float(v) for v in rgbs[rep]) for rep in source_reps]
        source_raw = _dissolve_fringes(source_raw, base, flat, source_colors, bg_rgb, min_flat=int(400 * factor**2))
        final_of_source = np.array(
            [0] * len(source_reps) + [-1], dtype=np.int16
        )
        for rep, i in position.items():
            cluster = int(np.nonzero(source_mapping == rep)[0][0])
            final_of_source[i] = remap[int(mapping[cluster])]
        raw = final_of_source[source_raw]
    del pixel_cluster, regions, groups, lab, base
    final_lab = srgb_to_lab(np.array(colors, dtype=np.float32))

    if background_lab is not None and background_ids:
        for c in source_reps:
            if float(delta_e(rgb_lab[c], background_lab)) <= CLUSTER_DE:
                color = to_hex(rgbs[c])
                warnings.append(
                    f"Interior areas colored {color} look like the background but stayed opaque. To make "
                    f"them transparent too, add --also-transparent '{color}'."
                )
    if flat_share < MIN_FLAT_SHARE:
        warnings.append(
            f"Only {flat_share:.0%} of the artwork is flat color, so gradients and fine texture were flattened. "
            "The SVG is valid; no flag changes this, so judge the preview, and use a larger source if you have one."
        )

    classes = list(range(len(colors))) + ([-1] if (raw == -1).any() else [])
    cleaned = _remove_specks(raw.copy(), speck_area)
    smooth = _smooth_partition(cleaned, classes, BASE_SMOOTH * factor * detail)
    smooth = _remove_specks(smooth, speck_area)
    return Segmentation(
        labels=smooth, raw_labels=raw, colors=colors, scale=scale,
        speck_area=speck_area, flat=flat, background=background_hex, warnings=warnings,
    )
