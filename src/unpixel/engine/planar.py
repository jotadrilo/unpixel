"""A planar map of the regions: each wall between two regions is one arc, walked once.

Walls run along the cracks between pixels. A vertex where three or four cracks meet is a junction, and so is
a vertex where a wall leaves the image frame. Every arc ends at junctions or closes on itself. Regions are
then loops of arcs, so the two sides of a wall cannot disagree and junctions meet exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Arc:
    cracks: list[int]  # crack ids in walking order
    start: int  # start vertex, -1 for a closed loop
    end: int
    left: int  # region on the left of the walking direction (x right, y down)
    right: int
    start_dir: int  # direction of the first step: 0 +x, 1 +y, 2 -x, 3 -y
    end_dir: int  # direction of the last step
    frame: bool  # runs along the image frame


@dataclass
class PlanarMap:
    height: int
    width: int
    arcs: list[Arc]
    crack_xy: np.ndarray  # middle of each crack, in grid units, shape (n, 2)
    crack_vertical: np.ndarray  # True for a crack between horizontal neighbors
    crack_frame: np.ndarray  # True on the image frame
    crack_a: np.ndarray  # (y, x) of the pixel on the low side (above or west), shape (n, 2)
    crack_b: np.ndarray  # (y, x) of the pixel on the high side (below or east)
    vertex_xy: np.ndarray  # compact vertex -> (x, y)
    loops: dict[int, list[list[tuple[int, bool]]]]  # region -> loops of (arc, walked backward)


def build(regions: np.ndarray) -> PlanarMap:
    """Walk the walls of a region map. Region 0 is unpainted and runs on beyond the image frame."""
    h, w = regions.shape
    pad = np.zeros((h + 2, w + 2), dtype=np.int32)
    pad[1:-1, 1:-1] = regions
    # Horizontal crack (y, x): from vertex (y, x) to (y, x + 1), y in 0..h, x in 0..w-1.
    above, below = pad[:-1, 1:-1], pad[1:, 1:-1]
    hy, hx = np.nonzero(above != below)
    # Vertical crack (y, x): from vertex (y, x) to (y + 1, x), y in 0..h-1, x in 0..w.
    west, east = pad[1:-1, :-1], pad[1:-1, 1:]
    vy, vx = np.nonzero(west != east)
    nh, nv = hy.size, vy.size
    n = nh + nv
    vw = w + 1

    va = np.concatenate([hy * vw + hx, vy * vw + vx])
    vb = np.concatenate([hy * vw + hx + 1, (vy + 1) * vw + vx])
    used, inverse = np.unique(np.concatenate([va, vb]), return_inverse=True)
    ca, cb = inverse[:n], inverse[n:]
    # For each vertex, the crack leaving in each direction: 0 +x, 1 +y, 2 -x, 3 -y.
    leave = np.full((used.size, 4), -1, dtype=np.int64)
    ids = np.arange(n)
    leave[ca[:nh], 0] = ids[:nh]
    leave[cb[:nh], 2] = ids[:nh]
    leave[ca[nh:], 1] = ids[nh:]
    leave[cb[nh:], 3] = ids[nh:]
    degree = (leave >= 0).sum(1)

    on_frame = np.concatenate([(hy == 0) | (hy == h), (vx == 0) | (vx == w)])
    touches_frame = np.zeros(used.size, dtype=bool)
    touches_inner = np.zeros(used.size, dtype=bool)
    touches_frame[ca[on_frame]] = True
    touches_frame[cb[on_frame]] = True
    touches_inner[ca[~on_frame]] = True
    touches_inner[cb[~on_frame]] = True
    junction = (degree >= 3) | (touches_frame & touches_inner)

    # Region on the left when walking a crack in its positive direction; the other is on its right.
    left_pos = np.concatenate([above[hy, hx], east[vy, vx]]).tolist()
    right_pos = np.concatenate([below[hy, hx], west[vy, vx]]).tolist()

    flat = leave.ravel().tolist()
    ea, eb = ca.tolist(), cb.tolist()
    is_j = junction.tolist()
    seen = bytearray(n)
    frame = on_frame.tolist()
    arcs: list[Arc] = []

    def walk(vertex: int, d: int) -> tuple[list[int], int, int]:
        path: list[int] = []
        while True:
            c = flat[4 * vertex + d]
            path.append(c)
            seen[c] = 1
            vertex = eb[c] if d < 2 else ea[c]
            if is_j[vertex]:
                return path, vertex, d
            at = 4 * vertex
            # A plain vertex has two cracks. Leave by the one not walked in on.
            if flat[at + d] >= 0:
                nd = d
            elif flat[at + (d + 1) % 4] >= 0:
                nd = (d + 1) % 4
            else:
                nd = (d + 3) % 4
            if seen[flat[at + nd]]:
                return path, -1, d
            d = nd

    def make(start: int, d: int, path: list[int], end: int, last: int) -> Arc:
        c = path[0]
        left, right = (left_pos[c], right_pos[c]) if d < 2 else (right_pos[c], left_pos[c])
        return Arc(path, start, end, left, right, d, last, frame[c])

    for vertex in np.nonzero(junction)[0].tolist():
        for d in range(4):
            c = flat[4 * vertex + d]
            if c < 0 or seen[c]:
                continue
            path, end, last = walk(vertex, d)
            arcs.append(make(vertex, d, path, end, last))
    for c in range(n):
        if not seen[c]:
            d = 0 if c < nh else 1
            path, _, last = walk(ea[c], d)
            arcs.append(make(-1, d, path, -1, last))

    crack_xy = np.concatenate(
        [np.stack([hx + 0.5, hy.astype(np.float64)], -1), np.stack([vx.astype(np.float64), vy + 0.5], -1)]
    ).astype(np.float32)
    vertical = np.zeros(n, dtype=bool)
    vertical[nh:] = True
    crack_a = np.concatenate([np.stack([hy - 1, hx], -1), np.stack([vy, vx - 1], -1)])
    crack_b = np.concatenate([np.stack([hy, hx], -1), np.stack([vy, vx], -1)])
    vertex_xy = np.stack([used % vw, used // vw], -1).astype(np.float32)
    return PlanarMap(h, w, arcs, crack_xy, vertical, on_frame, crack_a, crack_b, vertex_xy, _loops(arcs))


def _loops(arcs: list[Arc]) -> dict[int, list[list[tuple[int, bool]]]]:
    """Follow each region's walls with the region on the left: at a junction, always the leftmost turn."""
    outgoing: dict[tuple[int, int], tuple[int, bool]] = {}
    for i, arc in enumerate(arcs):
        if arc.start >= 0:
            outgoing[(arc.start, arc.start_dir)] = (i, False)
            outgoing[(arc.end, (arc.end_dir + 2) % 4)] = (i, True)

    loops: dict[int, list[list[tuple[int, bool]]]] = {}
    done: set[tuple[int, bool]] = set()
    for i, arc in enumerate(arcs):
        for backward in (False, True):
            region = arc.right if backward else arc.left
            if region == 0 or (i, backward) in done:
                continue
            if arc.start < 0:
                done.add((i, backward))
                loops.setdefault(region, []).append([(i, backward)])
                continue
            loop = []
            current = (i, backward)
            while current not in done:
                done.add(current)
                loop.append(current)
                a = arcs[current[0]]
                vertex, d = (a.start, (a.start_dir + 2) % 4) if current[1] else (a.end, a.end_dir)
                # With x right and y down, the left of direction d is d - 1.
                for turn in (d + 3, d, d + 1):
                    nxt = outgoing.get((vertex, turn % 4))
                    if nxt is None:
                        continue
                    b = arcs[nxt[0]]
                    if (b.right if nxt[1] else b.left) == region:
                        current = nxt
                        break
                else:
                    raise RuntimeError("open wall: no continuation with the region on the left")
            loops.setdefault(region, []).append(loop)
    return loops
