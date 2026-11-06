"""What the CLI needs from the engine: a Segmentation it can report on, and tracing of what it hands back."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..color import delta_e, srgb_to_lab, to_hex
from ..segment import InvalidRequest, Segmentation
from . import classify as classify_mod
from . import labels as lab_mod
from . import pipeline

DETAIL = {"low": 1.5, "medium": 1.0, "high": 0.6}
TRANSPARENT_MATCH_DE = 8.0  # as today's engine
LOOKS_LIKE_BACKGROUND_DE = 8.0
FAR_FROM_PALETTE_DE = 25.0


@dataclass
class Context:
    """What tracing needs besides the labels. Source colors stay here, since a recolored class has to find its wall."""

    fine_lab: np.ndarray | None
    source_lab: np.ndarray  # per class, the color as found, for finding walls; the last row is the background
    grid_scale: float  # grid units per working pixel
    output_scale: tuple[float, float]
    exact: bool  # pixel art: straight walls, no smoothing
    info: dict
    clock: pipeline._Clock


def _lab(rgb) -> np.ndarray:
    return lab_mod.perceptual(srgb_to_lab(np.array(rgb, dtype=np.float32)))


def _map_classes(label: np.ndarray, mapping: np.ndarray) -> np.ndarray:
    return mapping[label].astype(label.dtype)


def _pixel_art(rgb, kind, options, clock, info):
    block = max(kind.block, 1)
    small = rgb[block // 2 :: block, block // 2 :: block]
    lab = lab_mod.perceptual(srgb_to_lab(small))
    colors, inverse = pipeline._exact_palette(small, 256)
    wanted = options.color_count or None
    if colors is None or len(colors) > 24 or (wanted and len(colors) > wanted):
        pal = lab_mod.build_palette(lab, np.ones(lab.shape[:2], bool), count=wanted)
        nothing = lab_mod.Background(np.zeros(lab.shape[:2], bool), None)
        inverse = lab_mod.assign(lab, np.zeros(lab.shape[:2], bool), nothing, pal.lab, smoothness=0.0, rounds=0)
        colors, palette = pal.rgb, pal.lab
    else:
        palette = lab_mod.perceptual(srgb_to_lab(colors))
    asked = _lab(options.background_rgb) if options.background == "color" else None
    background = lab_mod.find_background(lab, erode=False, mode=options.background, color=asked)
    bg_row = background.lab if background.lab is not None else np.full((1, 3), 1e4, dtype=np.float32)
    label = inverse.copy()
    if background.lab is not None:
        label[background.mask] = len(palette)
    return label, None, palette, colors, background, np.vstack([palette, bg_row]), 1.0 / block, np.ones(label.shape, bool)


def segment_new(rgb: np.ndarray, options) -> tuple[Segmentation, Context]:
    clock = pipeline._Clock()
    info: dict = {"detail_factor": DETAIL.get(options.detail, 1.0)}
    warnings: list[str] = []
    with clock.stage("classify"):
        kind = classify_mod.classify(rgb)
    info["kind"] = kind.name
    height, width = rgb.shape[:2]
    if kind.name == "pixel":
        label, fine_lab, palette, colors, background, palette_all, grid_scale, flat = _pixel_art(rgb, kind, options, clock, info)
        output_scale = (1.0, 1.0)
        exact = True
    else:
        work, scale = pipeline.working_image(rgb)
        output_scale = (width / work.shape[1], height / work.shape[0])
        label, fine_lab, pal, background, palette_all, _bg, flat = pipeline.clean_labels(
            work, clock, info, options.color_count, options.background, options.background_rgb, scale
        )
        palette, colors = pal.lab, pal.rgb
        grid_scale = float(scale)
        exact = False
    if background.note:
        warnings.append(background.note)

    k = len(palette)
    if options.color_count is not None and k < options.color_count:
        warnings.append(f"Asked for {options.color_count} colors but only {k} were found.")
    color_lab = srgb_to_lab(np.array(colors, dtype=np.float32))
    colors = [tuple(int(round(float(v))) for v in c) for c in colors]
    present = np.bincount(label.ravel(), minlength=k + 1)[: k]

    # Colors asked to be transparent are judged on what the image contains, before any recoloring.
    removed = np.zeros(k, dtype=bool)
    for wanted in options.also_transparent:
        target = srgb_to_lab(np.array(wanted, dtype=np.float32))
        hit = (delta_e(color_lab, target) <= TRANSPARENT_MATCH_DE) & (present > 0)
        if not hit.any():
            warnings.append(f"--also-transparent {to_hex(wanted)} matched no color in the image.")
        removed |= hit
    if removed[present > 0].all() and (present > 0).any():
        raise InvalidRequest("--also-transparent would remove every color in the image")

    bg_lab = None
    if background.lab is not None:
        bg_lab = srgb_to_lab(lab_mod.lab_to_srgb(lab_mod.from_perceptual(background.lab)))
        for c in range(k):
            if present[c] and not removed[c] and float(delta_e(color_lab[c], bg_lab)) <= LOOKS_LIKE_BACKGROUND_DE:
                warnings.append(
                    f"Interior areas colored {to_hex(colors[c])} look like the background but stayed opaque. To make "
                    f"them transparent too, add --also-transparent '{to_hex(colors[c])}'."
                )

    # From here on: keep the classes in use, recolor them if asked, and write -1 for transparent.
    final_colors: list[tuple[int, int, int]] = []
    source_rows: list[np.ndarray] = []
    mapping = np.full(k + 1, -1, dtype=np.int32)
    if options.palette:
        asked = np.array(options.palette, dtype=np.float32)
        asked_lab = srgb_to_lab(asked)
        dist = delta_e(color_lab[:, None], asked_lab[None])
        chosen = dist.argmin(1)
        order = np.argsort(-present)
        used: dict[int, int] = {}
        for c in order.tolist():
            if not present[c] or removed[c]:
                continue
            target = int(chosen[c])
            if dist[c, target] > FAR_FROM_PALETTE_DE and len(asked) > 1:
                warnings.append(f"Detected color {to_hex(colors[c])} is far from every --colors value; it became {to_hex(asked[target])}.")
            if target not in used:
                used[target] = len(final_colors)
                final_colors.append(tuple(int(v) for v in asked[target]))
                source_rows.append(palette_all[c])
            mapping[c] = used[target]
        for i in set(range(len(asked))) - set(used):
            warnings.append(f"--colors value {to_hex(asked[i])} did not match anything in the image.")
    else:
        for c in range(k):
            if present[c] and not removed[c]:
                mapping[c] = len(final_colors)
                final_colors.append(colors[c])
                source_rows.append(palette_all[c])
    out = _map_classes(label, mapping)

    bg_row = palette_all[k]
    if removed.any() and background.lab is None:
        bg_row = palette_all[int(np.argmax(removed))]  # walls with what was removed still have a color to cross
    source_lab = np.vstack([np.array(source_rows, dtype=np.float32).reshape(-1, 3), bg_row])
    background_hex = None
    if background.lab is not None:
        background_hex = to_hex(lab_mod.lab_to_srgb(lab_mod.from_perceptual(background.lab)))
    speck = max(4, int(pipeline.SPECK_AREA * info["detail_factor"] ** 2 * (grid_scale**2)))
    seg = Segmentation(
        labels=out, raw_labels=out.copy(), colors=final_colors, scale=grid_scale, speck_area=speck,
        flat=flat, background=background_hex, warnings=warnings,
    )
    return seg, Context(fine_lab, source_lab, grid_scale, output_scale, exact, info, clock)


def trace_new(seg: Segmentation, ctx: Context, width: int, height: int, layers_mode: str, title: str,
              outlined: bool = False) -> tuple[str, list[dict]]:
    """Trace what the CLI holds. After --outline the labels are lines, with no wall in the source to follow."""
    k = len(seg.colors)
    classes = np.where(seg.labels < 0, k, seg.labels).astype(np.int16)
    has_background = bool((seg.labels < 0).any())
    if outlined:
        palette_all = np.vstack([_lab(seg.colors[0])[None], np.full((1, 3), 1e4, dtype=np.float32)])
        fine_lab = None
    else:
        palette_all, fine_lab = ctx.source_lab, ctx.fine_lab
    under = pipeline.UNDER if layers_mode == "stacked" else 0.0
    info = dict(ctx.info)
    svg = pipeline._trace(classes, fine_lab, palette_all, seg.colors, width, height, ctx.grid_scale, title, ctx.clock,
                          has_background, ctx.exact, under, info, output_scale=ctx.output_scale)
    ctx.info.update(info)
    return svg, info["layers"]
