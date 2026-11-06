"""The engine, end to end, with the time of each stage."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage as ni

from ..color import srgb_to_lab
from . import classify as classify_mod
from . import curves, labels as lab_mod, planar, svgout

SCALE = 2
DOUBLE_LIMIT = 4_000_000  # above this many pixels the class map stays at one to one
WORKING_LIMIT = 12_000_000  # above this the image is reduced to work on, and the curves scaled back
SMOOTH_SIGMA = 1.3  # source pixels
SOFT_SIGMA = 6.0  # source pixels, for walls across a soft gradient
SOFT_WALL_DE = 2.5  # delta-E per source pixel: a wall with less contrast across it than this is soft
FIT_TOLERANCE = 0.45  # source pixels
FAINT_WALL_DE = 14.0
FAINT_WALL_TOLERANCE = 0.6
UNDER = 1.0  # how far, in source pixels, the color below a wall reaches under the region above it
CORNER_SPAN = 2.6  # source pixels: a real cut does its turning within this
CORNER_TURN = 60.0  # degrees
TIP_SPAN = 5.0  # source pixels
TIP_MIN_TURN = 110.0
TIP_MAX_TURN = 165.0
SMALL_LOOP = 30.0  # source pixels of perimeter
SPECK_AREA = 12  # source pixels: smaller pieces are absorbed
SPECK_KEEP_AREA = 4  # ... unless they stand out by SPECK_KEEP_DE, as a dark stitch does
SPECK_KEEP_DE = 25.0
FLOATING_PALE_DE = 26.0
FLOATING_THICKNESS = 6.0  # source pixels
SPECKLE_AREA = 40  # source pixels
SPECKLE_DE = 32.0
SPECKLE_RADIUS = 30.0  # source pixels
SPECKLE_CROWD = 4  # this many other such islands within the radius
FAINT_AREA = 60  # source pixels: a blotch this small and closer than FAINT_DE to a neighbor is texture
FAINT_DE = 16.0


@dataclass
class Result:
    svg: str
    width: int
    height: int
    kind: str
    colors: list[tuple[int, int, int]]
    labels: np.ndarray  # class per pixel at `scale`; the last class is transparent when has_background
    scale: int
    has_background: bool
    timings: dict[str, float] = field(default_factory=dict)
    info: dict = field(default_factory=dict)


class _Clock:
    def __init__(self):
        self.t: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        s = time.perf_counter()
        yield
        self.t[name] = self.t.get(name, 0.0) + time.perf_counter() - s


def _subpixel(pmap, fine_lab, label, palette_all, scale: int) -> tuple[np.ndarray, np.ndarray]:
    """The position of each crack, source pixels, moved to where the color crosses halfway between two classes.

    Also the steepness of the source across each crack, delta-E per source pixel, or inf when unknown.
    """
    xy = pmap.crack_xy.astype(np.float64).copy()
    steep = np.full(len(xy), np.inf, dtype=np.float32)
    if fine_lab is not None:
        inner = ~pmap.crack_frame
        a = pmap.crack_a[inner]
        b = pmap.crack_b[inner]
        la, lb = label[a[:, 0], a[:, 1]], label[b[:, 0], b[:, 1]]
        ca, cb = palette_all[la], palette_all[lb]
        axis = cb - ca
        norm = np.maximum((axis * axis).sum(-1), 1e-6)
        sa = ((fine_lab[a[:, 0], a[:, 1]] - ca) * axis).sum(-1) / norm
        sb = ((fine_lab[b[:, 0], b[:, 1]] - ca) * axis).sum(-1) / norm
        slope = sb - sa
        t = np.where(slope > 1e-3, (0.5 - sa) / np.where(slope > 1e-3, slope, 1.0), 0.5)
        offset = np.clip(t, 0.0, 1.0) - 0.5
        steep[inner] = np.abs(slope) * np.sqrt(norm) * scale
        vertical = pmap.crack_vertical[inner]
        # The crack lies between a and b: x moves for vertical cracks, y for horizontal ones.
        which = np.nonzero(inner)[0]
        xy[which[vertical], 0] += offset[vertical]
        xy[which[~vertical], 1] += offset[~vertical]
    return xy / scale, steep


def _frame_polyline(pmap, arc, scale: int) -> np.ndarray:
    """An arc on the image frame or of pixel art: the corners of its crack path, exact."""
    cracks = np.asarray(arc.cracks)
    vert = pmap.crack_vertical[cracks]
    xy = pmap.crack_xy[cracks]
    pts = []
    if arc.start >= 0:
        pts.append(pmap.vertex_xy[arc.start])
    change = np.nonzero(vert[1:] != vert[:-1])[0]
    for i in change.tolist():
        p, q = xy[i], xy[i + 1]
        # The turn is at the x of the vertical crack and the y of the horizontal one.
        x = p[0] if vert[i] else q[0]
        y = q[1] if vert[i] else p[1]
        pts.append(np.array([x, y], dtype=np.float32))
    if arc.start >= 0:
        pts.append(pmap.vertex_xy[arc.end])
    else:
        # A closed loop: close at its first corner; when the first and last cracks turn, that is one more.
        if vert[0] != vert[-1]:
            p, q = xy[-1], xy[0]
            x = p[0] if vert[-1] else q[0]
            y = q[1] if vert[-1] else p[1]
            pts.append(np.array([x, y], dtype=np.float32))
        pts.append(pts[0])
    return np.array(pts, dtype=np.float64) / scale


def _lines(polyline: np.ndarray) -> np.ndarray:
    p0, p3 = polyline[:-1], polyline[1:]
    return np.stack([p0, p0 + (p3 - p0) / 3, p0 + 2 * (p3 - p0) / 3, p3], axis=1)


def _order_layers(classes: int, pairs: np.ndarray, weights: np.ndarray, areas: np.ndarray) -> np.ndarray:
    """z per class: the largest color at the bottom, as today."""
    z = np.zeros(classes, dtype=np.int32)
    z[np.argsort(-areas, kind="stable")] = np.arange(classes)
    return z


def _order_by_thickness(area: np.ndarray, perimeter: np.ndarray) -> np.ndarray:
    """z per class: thick shapes at the bottom, thin strokes on top, so walls stay exact on what is thin."""
    thick = 2.0 * area / np.maximum(perimeter, 1.0)
    z = np.zeros(len(area), dtype=np.int32)
    z[np.argsort(-thick, kind="stable")] = np.arange(len(area))
    return z


def _trace(
    label: np.ndarray,
    fine_lab,
    palette_all: np.ndarray,
    colors,
    width: int,
    height: int,
    scale: int,
    title: str,
    clock: _Clock,
    has_background: bool,
    exact: bool,
    under: float,
    info: dict,
    output_scale: tuple[float, float] = (1.0, 1.0),
) -> str:
    classes = len(palette_all)
    bg_class = classes - 1 if has_background else -1
    with clock.stage("regions"):
        regions, total = lab_mod._regions(label, classes)
        if has_background:
            regions[label == bg_class] = 0  # the background runs on past the frame as one unpainted region
        region_class = np.zeros(total + 1, dtype=np.int32)
        region_class[regions.ravel()] = label.ravel()
        area = np.bincount(regions.ravel(), minlength=total + 1).astype(np.float64)
    with clock.stage("planar_map"):
        pmap = planar.build(regions)
        # Perimeter of each region, in fine pixels, gives a thickness to limit how far others reach under it.
        a = pmap.crack_a
        b = pmap.crack_b
        h, w = regions.shape
        pad = np.pad(regions, 1)
        ra = pad[a[:, 0] + 1, a[:, 1] + 1]
        rb = pad[b[:, 0] + 1, b[:, 1] + 1]
        perimeter = np.bincount(ra, minlength=total + 1) + np.bincount(rb, minlength=total + 1)
    with clock.stage("curves"):
        arcs = pmap.arcs
        xy, steep = _subpixel(pmap, None if exact else fine_lab, label, palette_all, scale)
        vertex_xy = pmap.vertex_xy.astype(np.float64) / scale
        # A junction sits at the average of the first points of its walls, unless it is on the frame.
        if not exact:
            sums = np.zeros_like(vertex_xy)
            counts = np.zeros(len(vertex_xy))
            for arc in arcs:
                if arc.start >= 0:
                    sums[arc.start] += xy[arc.cracks[0]]
                    sums[arc.end] += xy[arc.cracks[-1]]
                    counts[arc.start] += 1
                    counts[arc.end] += 1
            hit = counts > 0
            moved = sums[hit] / counts[hit, None]
            at = vertex_xy[hit]
            on_frame = (at[:, 0] <= 0) | (at[:, 0] >= w / scale) | (at[:, 1] <= 0) | (at[:, 1] >= h / scale)
            moved[on_frame] = at[on_frame]
            vertex_xy[hit] = moved

        fixed: dict[int, np.ndarray] = {}
        soft_ids: list[int] = []
        soft_chains: list[np.ndarray] = []
        soft_closed: list[bool] = []
        soft_steep: list[float] = []
        for i, arc in enumerate(arcs):
            if exact or arc.frame:
                fixed[i] = _lines(_frame_polyline(pmap, arc, scale))
                continue
            pts = xy[arc.cracks]
            if arc.start >= 0:
                pts = np.vstack([vertex_xy[arc.start], pts, vertex_xy[arc.end]])
                soft_closed.append(False)
            else:
                soft_closed.append(True)
            soft_ids.append(i)
            soft_chains.append(pts)
            soft_steep.append(float(np.median(steep[arc.cracks])))
        closed = np.array(soft_closed, dtype=bool)

        # Split at corners; each piece is pinned at both ends and smoothed alone.
        step = 0.82 / scale
        info["arcs"] = len(arcs)
        ends = {v for arc in arcs if arc.start >= 0 for v in (arc.start, arc.end)}
        info["junctions"] = [
            [round(float(vertex_xy[v][0]) * output_scale[0], 2), round(float(vertex_xy[v][1]) * output_scale[1], 2)]
            for v in sorted(ends)
        ]
        corners = curves.find_corners(soft_chains, closed, step) if soft_chains else {}
        # A wall in a soft gradient has no real position to keep and no abrupt turn to respect.
        arc_soft = np.array(soft_steep, dtype=np.float64) < SOFT_WALL_DE
        corners = {k: v for k, v in corners.items() if not arc_soft[k]}
        # A dot or a stitch stays round: a small closed shape has no drawn corners to respect.
        corners = {k: v for k, v in corners.items() if not (closed[k] and len(soft_chains[k]) * step < SMALL_LOOP)}
        # The owner's rule: smooth, unless the source has an abrupt cut. A turn spread out is a round shape.
        found = sum(len(v) for v in corners.values())
        kept: dict[int, list[int]] = {}
        for k, cut in corners.items():
            good = []
            for c in cut:
                span, total = curves.corner_span(soft_chains[k], c, bool(closed[k]), step)
                blunt = span <= CORNER_SPAN and total >= CORNER_TURN
                # A tip, as on a star: a wide turn, a little softened by the source, and not a stroke's round
                # end, whose sides run parallel and so turn nearly all the way back.
                tip = span <= TIP_SPAN and TIP_MIN_TURN <= total <= TIP_MAX_TURN
                if blunt or tip:
                    good.append(c)
            if good:
                kept[k] = good
        corners = kept
        info["corners_found"] = found
        info["corners"] = sum(len(v) for v in corners.values())
        for k, cut in corners.items():
            soft_chains[k] = soft_chains[k].copy()
            curves.sharpen_corners(soft_chains[k], cut, bool(closed[k]), step)
        pieces: list[np.ndarray] = []
        piece_closed: list[bool] = []
        piece_owner: list[int] = []
        for k, chain in enumerate(soft_chains):
            cut = corners.get(k)
            if not cut:
                pieces.append(chain)
                piece_closed.append(bool(closed[k]))
                piece_owner.append(k)
                continue
            if closed[k]:
                chain = np.vstack([chain[cut[0] :], chain[: cut[0] + 1]])
                cut = [c - cut[0] for c in cut[1:]]
            last = 0
            for c in cut:
                pieces.append(chain[last : c + 1])
                piece_closed.append(False)
                piece_owner.append(k)
                last = c
            pieces.append(chain[last:])
            piece_closed.append(False)
            piece_owner.append(k)
        p_closed = np.array(piece_closed, dtype=bool)

        lengths = np.array([len(p) for p in pieces], dtype=np.float64) * step
        sigma = SMOOTH_SIGMA * info.get("detail_factor", 1.0)
        wanted = np.where(arc_soft[np.array(piece_owner, dtype=np.int64)], SOFT_SIGMA, sigma) if pieces else np.zeros(0)
        limit = np.minimum(wanted, lengths / 6.0)
        # Quantized so that one convolution serves many pieces.
        sigmas = np.round(limit / step * 2) / 2
        sigmas[sigmas < 0.5] = 0.0
        smoothed = curves.smooth_chains(pieces, p_closed, sigmas)

        # Tangent alignment where walls run through a junction.
        by_vertex: dict[int, list[tuple[int, bool]]] = {}
        first_piece: dict[int, int] = {}
        last_piece: dict[int, int] = {}
        for p, k in enumerate(piece_owner):
            first_piece.setdefault(k, p)
            last_piece[k] = p
        for k, i in enumerate(soft_ids):
            arc = arcs[i]
            if arc.start >= 0:
                by_vertex.setdefault(arc.start, []).append((first_piece[k], False))
                by_vertex.setdefault(arc.end, []).append((last_piece[k], True))
        # Walls with little contrast get a looser fit.
        tolerance = np.full(len(pieces), FIT_TOLERANCE)
        for p, k in enumerate(piece_owner):
            arc = arcs[soft_ids[k]]
            ca, cb = region_class[arc.left], region_class[arc.right]
            if arc.left != 0 and arc.right != 0:
                contrast = float(np.sqrt(((palette_all[ca] - palette_all[cb]) ** 2).sum()))
                if contrast < FAINT_WALL_DE:
                    tolerance[p] = FAINT_WALL_TOLERANCE
        fitted = curves.fit_chains(smoothed, p_closed, tolerance=tolerance, junctions=list(by_vertex.values()))

        # All arcs' segments, in arc order, in one array.
        all_points: list[np.ndarray] = []
        all_kinds: list[np.ndarray] = []
        arc_chain: list[tuple[int, int]] = [(0, 0)] * len(arcs)
        cursor = 0
        soft_of_arc = {i: k for k, i in enumerate(soft_ids)}
        for i in range(len(arcs)):
            if i in fixed:
                lines = fixed[i]
                all_points.append(lines)
                all_kinds.append(np.zeros(len(lines), dtype=np.int8))
                arc_chain[i] = (cursor, cursor + len(lines))
                cursor += len(lines)
            else:
                k = soft_of_arc[i]
                a0 = fitted.starts[first_piece[k]]
                a1 = fitted.starts[last_piece[k] + 1]
                all_points.append(fitted.points[a0:a1])
                all_kinds.append(fitted.kinds[a0:a1])
                arc_chain[i] = (cursor, cursor + a1 - a0)
                cursor += a1 - a0
        merged = curves.Fitted(
            np.concatenate(all_points) if all_points else np.zeros((0, 4, 2)),
            np.concatenate(all_kinds) if all_kinds else np.zeros(0, dtype=np.int8),
            np.zeros(1, dtype=np.int64),
        )
        # A large image is traced at its working size; here it goes back to the source's.
        dx, dy = output_scale
        merged.points[..., 0] *= dx
        merged.points[..., 1] *= dy
    with clock.stage("svg"):
        class_area = np.bincount(region_class[1:], weights=area[1:], minlength=classes)
        class_perimeter = np.bincount(region_class[1:], weights=perimeter[1:].astype(np.float64), minlength=classes)
        if has_background:
            class_area[bg_class] = 0
        z = _order_by_thickness(class_area, class_perimeter) if under > 0 else _order_layers(classes, None, None, class_area)
        svg, layers = svgout.write_svg(
            pmap, merged, arc_chain, region_class, (area * (dx / scale) ** 2, perimeter * dx / scale), colors, width, height, title, z, under * dx
        )
        total_paint = max(float(class_area.sum()), 1.0)
        for layer, cls in zip(layers, sorted((c for c in range(classes) if c != bg_class and class_area[c] > 0),
                                             key=lambda c: z[c])):
            layer["area_percent"] = round(100.0 * class_area[cls] / label.size, 2)
            layer["class"] = cls
        info["layers"] = layers
        del total_paint
    return svg


def _exact_palette(rgb: np.ndarray, limit: int):
    colors, inverse = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    if len(colors) > limit:
        return None, None
    return colors.astype(np.float32), inverse.reshape(rgb.shape[:2]).astype(np.int16)


def clean_labels(
    rgb: np.ndarray,
    clock: _Clock,
    info: dict,
    colors_wanted: int | None = None,
    background_mode: str = "auto",
    background_rgb=None,
    scale: int = SCALE,
):
    """Soft or hard artwork to a class map at `scale` times the size. Returns what contours and legacy tracing need."""
    detail = info.get("detail_factor", 1.0)
    with clock.stage("denoise"):
        lab_raw = lab_mod.perceptual(srgb_to_lab(rgb))
        hard = info["kind"] == "hard"
        lab = lab_raw if hard else lab_mod.flatten_gradients(lab_mod.bilateral(lab_raw))
        del lab_raw
    with clock.stage("antialiasing"):
        transition = lab_mod.transition_mask(lab)
        info["transition_share"] = round(float(transition.mean()), 4)
    with clock.stage("background"):
        asked = None
        if background_mode == "color":
            asked = lab_mod.perceptual(srgb_to_lab(np.array(background_rgb, dtype=np.float32)))
        background = lab_mod.find_background(lab, mode=background_mode, color=asked)
        bg_present = background.lab is not None
    bg_row = background.lab if bg_present else np.full((1, 3), 1e4, dtype=np.float32)
    # Two passes: edge bands found after the first assignment do not vote for the final palette.
    for attempt in range(2):
        with clock.stage("palette"):
            solid = ~transition & ~background.mask
            pal = lab_mod.build_palette(lab, solid, count=colors_wanted, highlights=lab_mod.highlight_mask(lab, solid),
                                        extras=lab_mod.background_extras(lab, solid, background))
            info["palette_log"] = pal.log
        with clock.stage("assign"):
            label = lab_mod.assign_large(lab, transition, background, pal.lab, rounds=1 if attempt == 0 else 3)
        with clock.stage("fringes"):
            palette_all = np.vstack([pal.lab, bg_row])
            label, bands = lab_mod.dissolve_fringes(label, lab, palette_all)
            if attempt == 0:
                transition = transition | bands
            else:
                label, more = lab_mod.dissolve_fringes(label, lab, palette_all)
                info["fringe_pixels"] = int(bands.sum() + more.sum())
                settled = lab_mod.settle_colors(pal.lab, label, lab, ~transition & ~background.mask)
                pal = lab_mod.PaletteInfo(settled, lab_mod.lab_to_srgb(lab_mod.from_perceptual(settled)),
                                          pal.stop_distance, pal.worst_left, pal.log)
    with clock.stage("refine"):
        if scale == 2:
            fine, fine_lab = lab_mod.refine_double(label, lab, pal.lab, background.lab)
        else:
            fine, fine_lab = label, lab
    with clock.stage("specks"):
        palette_all = np.vstack([pal.lab, bg_row])
        s2 = scale * scale
        size = detail * detail
        fine = lab_mod.absorb_specks(fine, palette_all, int(SPECK_AREA * s2 * size), int(SPECK_KEEP_AREA * s2 * size), SPECK_KEEP_DE,
                                      faint_area=int(FAINT_AREA * s2 * size), faint_de=FAINT_DE)
        fine, speckle = lab_mod.dissolve_speckle(fine, palette_all, SPECKLE_AREA * s2, SPECKLE_DE, SPECKLE_RADIUS * scale, SPECKLE_CROWD)
        info["speckle_islands"] = speckle
        if bg_present:
            fine, adrift = lab_mod.drop_floating_pale(fine, palette_all, FLOATING_PALE_DE, FLOATING_THICKNESS * scale)
            info["floating_pale"] = adrift
    flat = ~ni.binary_dilation(transition, iterations=1)
    return fine, fine_lab, pal, background, palette_all, bg_present, flat


def working_image(rgb: np.ndarray) -> tuple[np.ndarray, int]:
    """The image to work on, and the class map's scale. Large images give up the double map, then resolution."""
    h, w = rgb.shape[:2]
    pixels = h * w
    if pixels <= DOUBLE_LIMIT:
        return rgb, 2
    if pixels <= WORKING_LIMIT:
        return rgb, 1
    k = (WORKING_LIMIT / pixels) ** 0.5
    size = (max(1, int(round(w * k))), max(1, int(round(h * k))))
    return np.asarray(Image.fromarray(rgb).resize(size, Image.BOX)), 1


def run(rgb: np.ndarray, variant: str = "stacked", title: str = "image", colors_wanted: int | None = None) -> Result:
    """Variants: 'stacked' and 'cutout' draw shared curves; 'labels' hands the new class map to today's tracer."""
    clock = _Clock()
    height, width = rgb.shape[:2]
    info: dict = {}
    with clock.stage("classify"):
        kind = classify_mod.classify(rgb)
        info["kind"] = kind.name
        info["block"] = kind.block
        info["hard_share"] = round(kind.hard_share, 3)

    under = UNDER if variant == "stacked" else 0.0
    if kind.name == "pixel":
        block = max(kind.block, 1)
        small = rgb[block // 2 :: block, block // 2 :: block]
        with clock.stage("palette"):
            lab = lab_mod.perceptual(srgb_to_lab(small))
            exact_colors, inverse = _exact_palette(small, 24)
            if exact_colors is None:
                pal = lab_mod.build_palette(lab, np.ones(lab.shape[:2], bool), count=colors_wanted)
                palette_rgb = pal.rgb
                palette_lab = pal.lab
                inverse = lab_mod.assign(lab, np.zeros(lab.shape[:2], bool), lab_mod.Background(np.zeros(lab.shape[:2], bool), None), palette_lab, smoothness=0.0, rounds=0)
            else:
                palette_rgb = exact_colors
                palette_lab = lab_mod.perceptual(srgb_to_lab(exact_colors))
        with clock.stage("background"):
            background = lab_mod.find_background(lab, erode=False)
            has_background = background.lab is not None
            label = inverse.copy()
            palette_all = np.vstack([palette_lab, background.lab if has_background else np.full((1, 3), 1e4, dtype=np.float32)])
            if has_background:
                label[background.mask] = len(palette_lab)
        # A class pixel is a logical pixel, so 1 / block source pixels per grid unit.
        svg = _trace(label, None, palette_all, [tuple(c) for c in palette_rgb.tolist()], width, height, 1.0 / block, title,
                     clock, has_background, True, under, info)
        return Result(svg, width, height, kind.name, [tuple(int(round(v)) for v in c) for c in palette_rgb.tolist()],
                      label, 1, has_background, clock.t, info)

    work, scale = working_image(rgb)
    out_x, out_y = width / work.shape[1], height / work.shape[0]
    fine, fine_lab, pal, background, palette_all, bg_present, _flat = clean_labels(work, clock, info, colors_wanted, scale=scale)
    colors = [tuple(int(round(float(v))) for v in c) for c in pal.rgb]
    if variant == "labels":
        from ..vectorize import build_svg
        from ..segment import _smooth_partition

        with clock.stage("legacy_trace"):
            out = fine.copy()
            if bg_present:
                out[out == len(pal.lab)] = -1
            classes = sorted(int(c) for c in np.unique(out))
            out = _smooth_partition(out, classes, 2.0)
            svg, layers = build_svg(out, colors, width, height, "stacked", 30, title)
            info["layers"] = layers
        return Result(svg, width, height, kind.name, colors, fine, scale, bg_present, clock.t, info)

    svg = _trace(fine, fine_lab, palette_all, colors, width, height, scale, title, clock, bg_present, False, under, info,
                 output_scale=(out_x, out_y))
    return Result(svg, width, height, kind.name, colors, fine, scale, bg_present, clock.t, info)


def run_palette_only(rgb: np.ndarray, title: str = "image") -> Result:
    """The new palette with the plain assignment of the earlier hybrid prototype, through today's tracer.

    This is variant 1: it shows the palette alone, with median 3x3, nearest color and absorbed specks.
    """
    from ..vectorize import build_svg
    from ..segment import _smooth_partition

    clock = _Clock()
    height, width = rgb.shape[:2]
    info: dict = {"kind": "palette-only"}
    with clock.stage("denoise"):
        den = np.stack([ni.median_filter(rgb[..., i], size=3) for i in range(3)], -1)
        lab = lab_mod.perceptual(srgb_to_lab(den))
    with clock.stage("background"):
        background = lab_mod.find_background(lab)
        bg_present = background.lab is not None
    with clock.stage("antialiasing"):
        transition = lab_mod.transition_mask(lab)
    with clock.stage("palette"):
        pal = lab_mod.build_palette(lab, ~transition & ~background.mask)
        info["palette_log"] = pal.log
    with clock.stage("assign"):
        best = np.full(lab.shape[:2], np.inf, dtype=np.float32)
        label = np.zeros(lab.shape[:2], dtype=np.int16)
        for i, c in enumerate(pal.lab):
            d = ((lab - c) ** 2).sum(-1)
            hit = d < best
            label[hit] = i
            best[hit] = d[hit]
        k = len(pal.lab)
        if bg_present:
            label[background.mask] = k
    with clock.stage("specks"):
        palette_all = np.vstack([pal.lab, background.lab if bg_present else np.full((1, 3), 1e4, dtype=np.float32)])
        label = lab_mod.absorb_specks(label, palette_all, SPECK_AREA, SPECK_AREA, 1e9)
    colors = [tuple(int(round(float(v))) for v in c) for c in pal.rgb]
    with clock.stage("legacy_trace"):
        fine = np.repeat(np.repeat(label, 2, axis=0), 2, axis=1)
        if bg_present:
            fine[fine == k] = -1
        fine = _smooth_partition(fine, sorted(int(c) for c in np.unique(fine)), 2.0)
        svg, layers = build_svg(fine, colors, width, height, "stacked", 30, title)
        info["layers"] = layers
    return Result(svg, width, height, "palette-only", colors, label, 1, bg_present, clock.t, info)
