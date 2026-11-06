"""From walls to curves: corners that survive across scales, smoothing, and a batched Bezier fit.

Everything runs over one flat array holding all the chains, each with its own padding, so that one
convolution and one least-squares solve serve thousands of arcs at once. Numpy on small arrays spends its
time on call overhead; this is what keeps the stage fast without a compiled dependency.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ni


TANGENT_LAG = 8
MIN_LINE_LENGTH = 6.0  # source pixels: shorter straight pieces stay curves, whose ends share tangents


def gauss_kernel(sigma: float) -> np.ndarray:
    radius = max(1, int(np.ceil(3 * sigma)))
    x = np.arange(-radius, radius + 1)
    g = np.exp(-x * x / (2 * sigma * sigma))
    return g / g.sum()


class Flat:
    """Chains in one array with `pad` points of padding each side of every chain.

    Open chains pad by odd reflection around their ends, which pins the end and keeps its direction. Closed
    chains pad circularly; their first point is not repeated at the end.
    """

    def __init__(self, chains: list[np.ndarray], closed: np.ndarray, pad: int):
        self.pad = pad
        self.closed = closed
        self.sizes = np.fromiter((len(c) for c in chains), dtype=np.int64, count=len(chains))
        self.offsets = np.concatenate([[0], np.cumsum(self.sizes)])
        source = np.concatenate(chains).astype(np.float64) if chains else np.zeros((0, 2))
        total = self.sizes + 2 * pad
        self.starts = np.concatenate([[0], np.cumsum(total)]) + 0
        owner = np.repeat(np.arange(len(chains)), total)
        rel = np.arange(total.sum()) - self.starts[owner] - pad
        n = self.sizes[owner]
        base = self.offsets[owner]
        is_closed = closed[owner]
        low = rel < 0
        high = rel >= n
        out = np.empty((rel.size, 2), dtype=np.float64)
        mid = ~low & ~high & ~is_closed
        out[mid] = source[base[mid] + rel[mid]]
        c = is_closed
        out[c] = source[base[c] + np.mod(rel[c], n[c])]
        lo = low & ~is_closed
        m = np.minimum(-rel[lo], n[lo] - 1)
        out[lo] = 2 * source[base[lo]] - source[base[lo] + m]
        hi = high & ~is_closed
        last = base[hi] + n[hi] - 1
        m = np.minimum(rel[hi] - (n[hi] - 1), n[hi] - 1)
        out[hi] = 2 * source[last] - source[last - m]
        self.padded = out
        self.first = self.starts[:-1] + pad  # where each chain's own points begin in `padded`

    def blur(self, sigma: float) -> np.ndarray:
        return ni.convolve1d(self.padded, gauss_kernel(sigma), axis=0, mode="nearest")


def _turning(xy: np.ndarray, lag: int) -> np.ndarray:
    back = xy - np.roll(xy, lag, axis=0)
    ahead = np.roll(xy, -lag, axis=0) - xy
    dot = (back * ahead).sum(-1)
    cross = back[:, 0] * ahead[:, 1] - back[:, 1] * ahead[:, 0]
    return np.degrees(np.abs(np.arctan2(cross, dot)))


def find_corners(
    chains: list[np.ndarray],
    closed: np.ndarray,
    step: float,
    scales=(0.8, 1.5, 2.4),
    threshold: float = 50.0,
    min_gap: float = 3.0,
) -> dict[int, list[int]]:
    """Corners that stay corners at every scale, per chain. Scales are smoothing in source pixels.

    A pixel staircase turns sharply only at the finest scale. A gentle curve reaches a high angle only at the
    coarsest. A corner of the drawing turns at all of them.
    """
    if not chains:
        return {}
    pad = int(np.ceil(3 * scales[-1] / step)) + int(round(2.5 * scales[-1] / step)) + 4
    flat = Flat(chains, closed, pad)
    worst = None
    finest = None
    for s in scales:
        sigma = s / step
        blurred = flat.blur(sigma)
        lag = max(1, int(round(2.5 * s / step)))
        angle = _turning(blurred, lag)
        if finest is None:
            finest = angle
        spread = 2 * max(1, int(round(s / step))) + 1
        angle = ni.maximum_filter1d(angle, size=spread)
        worst = angle if worst is None else np.minimum(worst, angle)
    hit = worst >= threshold
    # Padding and seams never count.
    keep = np.zeros(hit.size, dtype=bool)
    owner = np.searchsorted(flat.starts, np.arange(hit.size), side="right") - 1
    rel = np.arange(hit.size) - flat.first[owner]
    keep = (rel >= 0) & (rel < flat.sizes[owner])
    candidates = np.nonzero(hit & keep)[0]
    out: dict[int, list[int]] = {}
    if candidates.size == 0:
        return out
    gap = int(round(min_gap / step))
    runs = np.split(candidates, np.nonzero(np.diff(candidates) > 1)[0] + 1)
    for run in runs:
        i = int(run[int(np.argmax(finest[run]))])
        k = int(owner[i])
        at = int(rel[i])
        if not closed[k] and (at < gap or at >= flat.sizes[k] - gap):
            continue
        items = out.setdefault(k, [])
        if items and at - items[-1] < gap:
            if finest[i] > finest[flat.first[k] + items[-1]]:
                items[-1] = at
            continue
        items.append(at)
    # A closed chain wraps: a corner at its seam can be found at both ends.
    for k, items in out.items():
        if closed[k] and len(items) > 1 and items[0] + flat.sizes[k] - items[-1] < gap:
            drop = 0 if finest[flat.first[k] + items[0]] < finest[flat.first[k] + items[-1]] else -1
            items.pop(drop)
    return out


def smooth_chains(chains: list[np.ndarray], closed: np.ndarray, sigmas: np.ndarray) -> list[np.ndarray]:
    """Gaussian smoothing with its shrinkage put back: G(x) + G(x - G(x)). Sigma is per chain, in points."""
    out = list(chains)
    levels = np.unique(sigmas[sigmas > 0])
    if levels.size == 0:
        return out
    # Two convolutions in a row reach twice the kernel's radius.
    pad = 2 * int(np.ceil(3 * levels.max())) + 2
    flat = Flat(chains, closed, pad)
    for level in levels:
        once = flat.blur(float(level))
        kernel = gauss_kernel(float(level))
        twice = once + ni.convolve1d(flat.padded - once, kernel, axis=0, mode="nearest")
        for k in np.nonzero(sigmas == level)[0].tolist():
            s = flat.first[k]
            res = twice[s : s + flat.sizes[k]]
            if not closed[k]:
                res = res.copy()
                res[0], res[-1] = chains[k][0], chains[k][-1]
            out[k] = res
    return out


@dataclass
class Fitted:
    """Fitted segments of all chains, in walking order. kinds: 0 line, 1 cubic. A chain's run is contiguous."""

    points: np.ndarray  # (m, 4, 2)
    kinds: np.ndarray
    starts: np.ndarray  # chain k owns segments starts[k]:starts[k + 1]


def _align_junctions(tangents: np.ndarray, first: np.ndarray, last: np.ndarray, junctions: list[list[tuple[int, bool]]]):
    """Where a wall runs straight through a junction, give both sides the same direction, so it has no kink."""
    for ends in junctions:
        if len(ends) < 2:
            continue
        out = []
        for chain, at_end in ends:
            at = last[chain] if at_end else first[chain]
            t = tangents[at]
            out.append((at, -t[0] if at_end else t[0], -t[1] if at_end else t[1], at_end))
        best, pair = -0.86, None
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                dot = out[i][1] * out[j][1] + out[i][2] * out[j][2]
                if dot < best:
                    best, pair = dot, (i, j)
        if pair is None:
            continue
        a, b = out[pair[0]], out[pair[1]]
        vx, vy = a[1] - b[1], a[2] - b[2]
        norm = (vx * vx + vy * vy) ** 0.5
        if norm < 1e-9:
            continue
        vx, vy = vx / norm, vy / norm
        # Back from outward directions to walking directions.
        tangents[a[0]] = (-vx, -vy) if a[3] else (vx, vy)
        tangents[b[0]] = (vx, vy) if b[3] else (-vx, -vy)


def fit_chains(
    chains: list[np.ndarray],
    closed: np.ndarray,
    tolerance: float = 0.3,
    line_tolerance: float = 0.12,
    samples: int = 24,
    junctions: list[list[tuple[int, bool]]] | None = None,
) -> Fitted:
    """Fit every chain to a tolerance, with cubics that share tangents at their knots, so joins stay smooth.

    Tangents come from the smoothed chain. Only the two handle lengths are solved for, which has a closed
    form, so a whole round of pieces is one array operation. Pieces over tolerance split at their worst
    point and go to the next round.
    """
    count = len(chains)
    if count == 0:
        return Fitted(np.zeros((0, 4, 2)), np.zeros(0, dtype=np.int8), np.zeros(1, dtype=np.int64))
    # Directions measured over a few points, since a knot's tangent decides how well both its curves fit.
    lag = TANGENT_LAG
    pad_flat = Flat(chains, closed, lag)
    tan_all = pad_flat.padded[2 * lag :] - pad_flat.padded[: -2 * lag]  # index i in padded is i - lag here
    # Per chain, own points plus the first again for closed ones.
    sizes = pad_flat.sizes + closed.astype(np.int64)
    offsets = np.concatenate([[0], np.cumsum(sizes)])
    total = int(offsets[-1])
    P = np.empty((total, 2))
    T = np.empty((total, 2))
    owner = np.repeat(np.arange(count), sizes)
    rel = np.arange(total) - offsets[owner]
    wrap = rel >= pad_flat.sizes[owner]  # the repeated first point of a closed chain
    src = pad_flat.first[owner] + np.where(wrap, 0, rel)
    P[:] = pad_flat.padded[src]
    T[:] = tan_all[src - lag]
    # Very short open chains have no useful local direction but their chord.
    norm = np.hypot(T[:, 0], T[:, 1])
    T /= np.maximum(norm, 1e-9)[:, None]
    step = np.hypot(*(P[1:] - P[:-1]).T)
    step[offsets[1:-1] - 1] = 0.0
    S = np.concatenate([[0.0], np.cumsum(step)])

    first, last = offsets[:-1], offsets[1:] - 1
    if junctions:
        _align_junctions(T, first, last, junctions)

    has_points = last > first
    n_closed = (closed & has_points)
    third = np.maximum((last - first) // 3, 1)
    i0 = np.concatenate([first[has_points & ~closed], first[n_closed], (first + third)[n_closed], (first + 2 * third)[n_closed]])
    i1 = np.concatenate([last[has_points & ~closed], (first + third)[n_closed], (first + 2 * third)[n_closed], last[n_closed]])

    done_pts, done_kind, done_key = [], [], []
    grid = np.linspace(0.0, 1.0, samples)
    while i0.size:
        span = i1 - i0
        idx = i0[:, None] + np.rint(span[:, None] * grid).astype(np.int64)
        d = P[idx]
        p0, p3 = P[i0], P[i1]
        chord = p3 - p0
        length = np.maximum(S[i1] - S[i0], 1e-9)
        u = (S[idx] - S[i0][:, None]) / length[:, None]
        chord_len = np.hypot(chord[:, 0], chord[:, 1])
        unit = chord / np.maximum(chord_len, 1e-9)[:, None]
        rel = d - p0[:, None]
        off = np.abs(rel[..., 0] * unit[:, 1, None] - rel[..., 1] * unit[:, 0, None]).max(1)
        straight = (off <= line_tolerance) & (chord_len >= 0.7 * length) & (chord_len >= MIN_LINE_LENGTH)
        t0, t3 = T[i0], -T[i1]
        for _ in range(3):
            b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u**3
            a1 = t0[:, None] * b1[..., None]
            a2 = t3[:, None] * b2[..., None]
            rest = d - (p0[:, None] * (b0 + b1)[..., None] + p3[:, None] * (b2 + b3)[..., None])
            c00, c01, c11 = (a1 * a1).sum((1, 2)), (a1 * a2).sum((1, 2)), (a2 * a2).sum((1, 2))
            x0, x1 = (a1 * rest).sum((1, 2)), (a2 * rest).sum((1, 2))
            det = c00 * c11 - c01 * c01
            good = np.abs(det) > 1e-9
            safe = np.where(good, det, 1.0)
            alpha = np.where(good, (x0 * c11 - x1 * c01) / safe, 0.0)
            beta = np.where(good, (c00 * x1 - c01 * x0) / safe, 0.0)
            small = length * 1e-3
            bad = (alpha < small) | (beta < small) | (alpha > 1.5 * length) | (beta > 1.5 * length)
            alpha = np.where(bad, length / 3, alpha)
            beta = np.where(bad, length / 3, beta)
            p1 = p0 + t0 * alpha[:, None]
            p2 = p3 + t3 * beta[:, None]
            # One Newton step per round moves each parameter toward its closest point on the curve.
            q = p0[:, None] * b0[..., None] + p1[:, None] * b1[..., None] + p2[:, None] * b2[..., None] + p3[:, None] * b3[..., None]
            q1 = (
                3 * (p1 - p0)[:, None] * ((1 - u) ** 2)[..., None]
                + 6 * (p2 - p1)[:, None] * (u * (1 - u))[..., None]
                + 3 * (p3 - p2)[:, None] * (u * u)[..., None]
            )
            q2 = 6 * (p2 - 2 * p1 + p0)[:, None] * (1 - u)[..., None] + 6 * (p3 - 2 * p2 + p1)[:, None] * u[..., None]
            diff = q - d
            num = (diff * q1).sum(-1)
            den = (q1 * q1).sum(-1) + (diff * q2).sum(-1)
            ok_den = np.abs(den) > 1e-9
            u = np.clip(u - np.where(ok_den, num / np.where(ok_den, den, 1.0), 0.0), 0.0, 1.0)
            u[:, 0], u[:, -1] = 0.0, 1.0
        b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u**3
        q = p0[:, None] * b0[..., None] + p1[:, None] * b1[..., None] + p2[:, None] * b2[..., None] + p3[:, None] * b3[..., None]
        err = np.sqrt(((q - d) ** 2).sum(-1))
        accept = (err.max(1) <= tolerance) | (span < 4) | straight
        bez = np.stack([p0, p1, p2, p3], axis=1)
        line = np.stack([p0, p0 + chord / 3, p0 + 2 * chord / 3, p3], axis=1)
        chosen = np.where(straight[:, None, None], line, bez)
        done_pts.append(chosen[accept])
        done_kind.append((~straight[accept]).astype(np.int8))
        done_key.append(i0[accept])
        todo = ~accept
        if not todo.any():
            break
        at = np.argmax(err[todo], axis=1)
        split = idx[todo][np.arange(at.size), at]
        a, b = i0[todo], i1[todo]
        margin = np.minimum(2, (b - a) // 2)
        split = np.clip(split, a + margin, b - margin)
        i0, i1 = np.concatenate([a, split]), np.concatenate([split, b])

    pts = np.concatenate(done_pts)
    kinds = np.concatenate(done_kind)
    key = np.concatenate(done_key)
    order = np.argsort(key, kind="stable")
    pts, kinds, key = pts[order], kinds[order], key[order]
    starts = np.searchsorted(key, offsets)
    starts[-1] = len(key)
    return Fitted(pts, kinds, starts)
