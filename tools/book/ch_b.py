"""Figures for chapters 5 to 7: masks, assignment and the story of ASSIGN_WINDOW, and cleaning."""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ni

from ch_a import lab_rgb, swatches
from draw import annotate, classes, crop, faded, over, rsvg, save, scaled, shrink, svg_crop, zoom
from harness import SOURCES, lab_mod, load, locals_of, patched, pipe_mod, seg_mod
from measures import WINDOWS
from unpixel.color import srgb_to_lab, to_hex

MASK = (214, 0, 120)
SOLID = (0, 130, 90)
FLOOD = (30, 110, 220)
LIGHT = (235, 130, 0)


def densest(mask, size):
    """The window of a given size that holds most of a mask, as (x0, y0, x1, y1)."""
    h, w = mask.shape
    size = min(size, h, w)
    weight = ni.uniform_filter(mask.astype(np.float32), size=size, mode="constant")
    half = size // 2
    weight[:half] = 0
    weight[h - half:] = 0
    weight[:, :half] = 0
    weight[:, w - half:] = 0
    y, x = np.unravel_index(int(np.argmax(weight)), weight.shape)
    return (int(x - half), int(y - half), int(x - half + size), int(y - half + size))


def chapter5(ctx):
    d = {}
    # Flood, step by step: the real function's locals.
    rgb = load(SOURCES["float"])
    tn = ctx.new("float")
    with locals_of(lab_mod.find_background) as seen:
        bg = lab_mod.find_background(tn.lab)
    L = seen["find_background"][0]
    d["bg_tau"] = f"{L['tau']:g}".replace(".", ",")
    d["bg_hex"] = to_hex(lab_rgb(L["center"]))
    W = 640
    d["f5_src"] = save(shrink(rgb, W), "5-float-src.jpg")
    d["f5_near"] = save(shrink(over(rgb, L["near"], FLOOD, 0.8), W), "5-float-near.jpg")
    d["f5_flood"] = save(shrink(over(rgb, L["flood"], FLOOD, 0.8), W), "5-float-flood.jpg")
    enclosed = L["near"] & ~bg.mask
    base = over(rgb, bg.mask, FLOOD, 0.8)
    base = base * (1 - enclosed[..., None]) + np.array(SOLID, dtype=np.float32) * enclosed[..., None]
    d["f5_final"] = save(shrink(base, W), "5-float-final.jpg")
    d["bg_share"] = f"{100 * bg.mask.mean():.1f}".replace(".", ",")
    d["bg_enclosed"] = f"{100 * enclosed.mean():.1f}".replace(".", ",")
    # A closer look at the opening rule: same window on near and on the final flood.
    box = densest(enclosed, 100)
    d["f5_near_z"] = save(zoom(over(crop(rgb, box), crop(L["near"], box), FLOOD, 0.8), 4), "5-near-zoom.png")
    d["f5_final_z"] = save(zoom(crop(base, box), 4).astype(np.uint8), "5-final-zoom.png")
    d["f5_src_z"] = save(zoom(crop(rgb, box), 4), "5-src-zoom.png")
    # Where the border is not one color there is no background at all.
    notes = {}
    for name in ("sunset", "principito"):
        notes[name] = ctx.new(name).background.note
    d["note_sunset"] = notes["sunset"]
    d["note_principito"] = notes["principito"]

    # Transition pixels.
    gills = (500, 150, 620, 270)
    d["f5_gill_src"] = save(zoom(crop(rgb, gills), 4), "5-gill-src.png")
    d["f5_gill_tr"] = save(zoom(over(crop(rgb, gills), crop(tn.transition, gills), MASK), 4), "5-gill-tr.png")
    solid = ~tn.transition & ~tn.background.mask
    d["f5_gill_solid"] = save(zoom(over(crop(rgb, gills), crop(solid, gills), SOLID), 4), "5-gill-solid.png")
    d["f5_all_tr"] = save(shrink(over(rgb, tn.transition, MASK, 1.0, 0.25), W), "5-all-tr.png")
    d["f5_all_solid"] = save(shrink(over(rgb, solid, SOLID, 0.85, 0.25), W), "5-all-solid.png")
    d["tr_share"] = f"{100 * tn.transition.mean():.1f}".replace(".", ",")
    d["solid_share"] = f"{100 * solid.mean():.1f}".replace(".", ",")

    # A column across three whiskers: each pixel, its lightness, whether it was called a transition.
    ax = ctx.new("axolotl")
    axrgb = load(SOURCES["axolotl"])
    x, y0, y1 = 632, 225, 285
    d["c5_row"] = row_chart(ax.lab[y0:y1, x], ax.transition[y0:y1, x], axrgb[y0:y1, x])
    d["row_x"], d["row_y0"], d["row_y1"] = x, y0, y1
    d["f5_row"] = save(zoom(np.swapaxes(crop(axrgb, (x - 3, y0, x + 4, y1)), 0, 1), 8), "5-row.png")
    whisk = (608, 225, 668, 285)
    d["f5_wh_src"] = save(zoom(crop(axrgb, whisk), 6), "5-wh-src.png")
    d["f5_wh_tr"] = save(zoom(over(crop(axrgb, whisk), crop(ax.transition, whisk), MASK), 6), "5-wh-tr.png")

    # Highlights.
    dv = ctx.new("diver")
    dvrgb = load(SOURCES["diver"])
    dsolid = ~dv.transition & ~dv.background.mask
    hl = lab_mod.highlight_mask(dv.lab, dsolid)
    d["f5_hl_src"] = save(shrink(dvrgb, W), "5-hl-src.jpg")
    d["f5_hl"] = save(shrink(over(dvrgb, ni.binary_dilation(hl), LIGHT, 1.0, 0.25), W), "5-hl.jpg")
    helmet = densest(hl, 160)
    d["f5_hl_z_src"] = save(zoom(crop(dvrgb, helmet), 3), "5-hl-z-src.png")
    d["f5_hl_z"] = save(zoom(over(crop(dvrgb, helmet), crop(hl, helmet), LIGHT, 1.0), 3), "5-hl-z.png")
    d["hl_share"] = f"{100 * hl.mean():.1f}".replace(".", ",")

    # The classic engine's closest idea: pixels far from any edge.
    tc = ctx.classic("float")
    s = tc.seg.scale
    flat = np.asarray(tc.segment_locals["flat"])[:: int(round(s)), :: int(round(s))]
    flat = flat[: rgb.shape[0], : rgb.shape[1]]
    d["f5_flat"] = save(zoom(over(crop(rgb, gills), crop(flat, gills), SOLID), 4), "5-flat.png")
    return d


def row_chart(lab_row, flagged, rgb_row):
    """Lightness along a real row; magenta where `transition_mask` said mix."""
    w, h, l, b = 560, 150, 30, 18
    n = len(lab_row)
    values = lab_row[:, 0]
    pts = " ".join(f"{l + (w - l - 8) * (i + .5) / n:.1f},{10 + (h - b - 10) * (1 - v / 100):.1f}" for i, v in enumerate(values))
    marks = []
    for i, v in enumerate(values):
        x = l + (w - l - 8) * (i + .5) / n
        y = 10 + (h - b - 10) * (1 - v / 100)
        c = "var(--s5)" if flagged[i] else "var(--s1)"
        tag = "transición" if flagged[i] else "sólido"
        marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{c}" stroke="var(--paper)" stroke-width="1.5"><title>x+{i}: L {v:.0f}, {tag}</title></circle>')
    ticks = "".join(f'<line x1="{l}" x2="{w - 8}" y1="{10 + (h - b - 10) * (1 - v / 100):.1f}" y2="{10 + (h - b - 10) * (1 - v / 100):.1f}" stroke="var(--grid)"/><text x="{l - 4}" y="{14 + (h - b - 10) * (1 - v / 100):.1f}" text-anchor="end" class="ct">{v}</text>' for v in (0, 50, 100))
    legend = ('<circle cx="40" cy="146" r="4" fill="var(--s1)"/><text x="48" y="149" class="ct">sólido</text>'
              '<circle cx="110" cy="146" r="4" fill="var(--s5)"/><text x="118" y="149" class="ct">transición</text>')
    return f'<svg class="chart" viewBox="0 0 {w} {h + 4}" role="img" aria-label="Luminosidad a lo largo de una fila de píxeles">{ticks}<polyline fill="none" stroke="var(--muted)" stroke-width="1.5" points="{pts}"/>{"".join(marks)}{legend}</svg>'


def wrong_dark(source_rgb, output_rgb):
    """Pixels the output paints dark where the source is a lit, colored tone: the failure of a narrow window."""
    plain = srgb_to_lab(source_rgb)
    out = srgb_to_lab(output_rgb)
    chroma = np.hypot(plain[..., 1], plain[..., 2])
    return (out[..., 0] < 25) & (plain[..., 0] - out[..., 0] > 18) & (chroma > 25)


def chapter6(ctx):
    d = {}
    rgb = load(SOURCES["float"])
    gills = (500, 150, 620, 270)
    ears = (490, 130, 850, 350)
    for win in WINDOWS:
        svg = ctx.svg("float", f"reach{win}", "stacked")
        d[f"f6_r{win}"] = save(svg_crop(svg, gills, 4), f"6-r{win}.png")
        d[f"f6_wide_r{win}"] = save(svg_crop(svg, ears, 2), f"6-wide-r{win}.png")
    d["f6_src"] = save(zoom(crop(rgb, gills), 4), "6-src.png")
    d["f6_wide_src"] = save(zoom(crop(rgb, ears), 2), "6-wide-src.png")

    # The count of wrongly dark pixels on the rendered result, for every window and image.
    rows, totals = [], {w: 0 for w in WINDOWS}
    from draw import svg_crop as render_all
    per = {}
    for name in SOURCES:
        src = load(SOURCES[name])
        row = []
        for win in WINDOWS:
            out = np.asarray(render_all(ctx.svg(name, f"reach{win}", "stacked")).convert("RGB"))
            n = int(wrong_dark(src, out).sum())
            totals[win] += n
            row.append(n)
        per[name] = row
        rows.append(f"<tr><td><code>{name}</code></td>" + "".join(f"<td>{v:,}</td>".replace(",", ".") for v in row) + "</tr>")
    d["t6_wrong"] = "".join(rows) + "<tr class=\"sum\"><td>Total</td>" + "".join(f"<td>{totals[w]:,}</td>".replace(",", ".") for w in WINDOWS) + "</tr>"
    d["wrong_float_3"], d["wrong_float_9"] = per["float"][0], per["float"][2]
    out3 = np.asarray(render_all(ctx.svg("float", "reach3", "stacked")).convert("RGB"))
    out9 = np.asarray(render_all(ctx.svg("float", "reach9", "stacked")).convert("RGB"))
    wrong3 = wrong_dark(rgb, out3)
    wrong9 = wrong_dark(rgb, out9)
    d["f6_wrong3"] = save(zoom(over(crop(rgb, gills), crop(wrong3, gills), (20, 20, 20), 1.0, 0.5), 4), "6-wrong3.png")
    d["f6_wrong9"] = save(zoom(over(crop(rgb, gills), crop(wrong9, gills), (20, 20, 20), 1.0, 0.5), 4), "6-wrong9.png")

    # What one wrong pixel can see: reach 3 against reach 9, from the labels `assign` itself produced.
    t3 = ctx.new_window("float", 3)
    a = t3.assigns[-1]
    transition = a["args"][1]
    label3 = a["result"]
    palette = a["args"][3]
    colors = lab_rgb(palette)
    bgmask = a["args"][2].mask
    seed = np.where(transition & ~bgmask, -1, label3)
    pick = np.nonzero(crop(wrong3 & transition, gills))
    # The wrong transition pixel whose reach holds the fewest classes at 3 and the most at 9.
    best, how = None, None
    for y, x in zip(pick[0][::3] + gills[1], pick[1][::3] + gills[0]):
        near3 = np.unique(seed[y - 3 : y + 4, x - 3 : x + 4])
        near9 = np.unique(seed[y - 9 : y + 10, x - 9 : x + 10])
        near3, near9 = near3[near3 >= 0], near9[near9 >= 0]
        score = len(near9) - 3 * len(near3)
        if best is None or score > best:
            best, how = score, (int(x), int(y), near3, near9)
    x, y, n3, n9 = how
    d["pick_x"], d["pick_y"] = x, y
    def names(ids):
        return swatches([(to_hex(colors[i]) if i < len(colors) else "#ffffff", "") for i in ids])
    d["s6_near3"], d["s6_near9"] = names(n3), names(n9)
    d["pick_src"] = to_hex(rgb[y, x])
    d["pick_got3"] = to_hex(colors[label3[y, x]])
    box = (x - 20, y - 20, x + 21, y + 21)
    z = 10
    def square(r, color):
        return (f'<rect x="{(20 - r) * z}" y="{(20 - r) * z}" width="{(2 * r + 1) * z}" height="{(2 * r + 1) * z}" fill="none" stroke="{color}" stroke-width="3"/>')
    marks = square(3, "#ffffff") + square(3, "#000000").replace('stroke-width="3"', 'stroke-width="1"') + square(9, "#ffffff") + square(9, "#000000").replace('stroke-width="3"', 'stroke-width="1"')
    marks += f'<rect x="{20 * z}" y="{20 * z}" width="{z}" height="{z}" fill="none" stroke="#ff0066" stroke-width="3"/>'
    d["f6_window"] = save(annotate(zoom(crop(rgb, box), z), marks), "6-window.png")
    d["f6_window_out"] = save(annotate(zoom(classes(crop(label3, box), colors), z), marks), "6-window-out.png")

    # The halo: no limit at all, on the same image.
    ax = ctx.new("axolotl")
    axrgb = load(SOURCES["axolotl"])
    lim = ctx.new_window("axolotl", 100000)
    assign_a, assign_b = ax.assigns[-1], lim.assigns[-1]
    pale = ax.result.labels
    table = np.array(ax.result.colors)
    # Where the unlimited run has a class the limited one does not, along edges.
    labels_a = assign_a["result"]
    colors_a = lab_rgb(assign_a["args"][3])
    labels_b = assign_b["result"]
    colors_b = lab_rgb(assign_b["args"][3])
    rgb_a = classes(labels_a, colors_a)
    rgb_b = classes(labels_b, colors_b)
    diff = np.abs(rgb_a.astype(int) - rgb_b.astype(int)).sum(-1) > 30
    d["halo_changed"] = f"{int(diff.sum()):,}".replace(",", ".")
    halo = densest(diff, 70)
    d["halo_box"] = str(halo)
    d["f6_h_src"] = save(zoom(crop(axrgb, halo), 5), "6-h-src.png")
    d["f6_h_lim"] = save(zoom(crop(rgb_a, halo), 5), "6-h-lim.png")
    d["f6_h_free"] = save(zoom(crop(rgb_b, halo), 5), "6-h-free.png")
    d["f6_h_diff"] = save(zoom(over(crop(axrgb, halo), crop(diff, halo), MASK, 1.0), 5), "6-h-diff.png")
    del pale, table

    # Second act: the background's own, shorter reach. The same run with the old reach for the background.
    ctx_rgb = load(SOURCES["axolotl"])
    runs = {}
    keep = lab_mod.BACKGROUND_WINDOW
    try:
        for reach in (lab_mod.ASSIGN_WINDOW, keep):
            lab_mod.BACKGROUND_WINDOW = reach
            runs[reach] = pipe_mod.run(ctx_rgb, "stacked", "axolotl", colors_wanted=8)
    finally:
        lab_mod.BACKGROUND_WINDOW = keep
    alpha = {r: np.asarray(rsvg(v.svg))[..., 3] for r, v in runs.items()}
    hole = (alpha[lab_mod.ASSIGN_WINDOW] < 127) & (alpha[keep] >= 127)
    parts, count = ni.label(hole)
    sizes = np.bincount(parts.ravel())[1:] if count else np.zeros(0)
    d["hole_px"] = int(sizes.max()) if count else 0
    d["hole_pieces"] = int(count)
    y, x = np.nonzero(parts == int(np.argmax(sizes)) + 1) if count else (np.array([134]), np.array([410]))
    cx, cy = int(x.mean()), int(y.mean())
    d["hole_x"], d["hole_y"] = cx, cy
    box = (cx - 40, cy - 40, cx + 40, cy + 40)
    d["f6_hole_src"] = save(zoom(crop(ctx_rgb, box), 5), "6-hole-src.png")
    d["f6_hole_9"] = save(svg_crop(runs[lab_mod.ASSIGN_WINDOW].svg, box, 5, "#ff00aa"), "6-hole-9.png")
    d["f6_hole_3"] = save(svg_crop(runs[keep].svg, box, 5, "#ff00aa"), "6-hole-3.png")
    d["hole_colors"] = len(runs[keep].colors)

    # Cost: what the runs measured.
    rows = []
    sums = {w: dict(kb=0.0, paths=0, nodes=0, s=0.0, mb=0.0) for w in WINDOWS}
    for name in SOURCES:
        cells = []
        for win in WINDOWS:
            r = ctx.runs[f"{name}/reach{win}/stacked"]
            m = r["measure"]
            sums[win]["kb"] += m["svg_kb"]
            sums[win]["paths"] += m["paths"]
            sums[win]["nodes"] += m["nodes"]
            sums[win]["s"] += r["seconds"]
            sums[win]["mb"] = max(sums[win]["mb"], r["peak_rss_mb"])
            cells.append(f"<td>{m['svg_kb']:.0f}</td>")
        rows.append(f"<tr><td><code>{name}</code></td>{''.join(cells)}</tr>")
    d["t6_kb"] = "".join(rows) + '<tr class="sum"><td>Total</td>' + "".join(f"<td>{sums[w]['kb']:.0f}</td>" for w in WINDOWS) + "</tr>"
    d["t6_cost"] = "".join(
        f"<tr><td>{w}</td><td>{sums[w]['kb']:.0f}</td><td>{sums[w]['paths']}</td><td>{sums[w]['nodes']}</td><td>{sums[w]['s']:.1f}</td><td>{sums[w]['mb']:.0f}</td></tr>"
        for w in WINDOWS)
    k3, k9, k12 = sums[3]["kb"], sums[9]["kb"], sums[12]["kb"]
    d["kb_3_to_9"] = f"{100 * (k9 - k3) / k3:+.1f}".replace(".", ",")
    d["kb_9_to_12"] = f"{100 * (k12 - k9) / k9:+.1f}".replace(".", ",")
    d["t_3"], d["t_9"], d["t_12"] = f"{sums[3]['s']:.1f}", f"{sums[9]['s']:.1f}", f"{sums[12]['s']:.1f}"
    d["window_now"] = lab_mod.ASSIGN_WINDOW
    grow = sum(1 for n in SOURCES if ctx.runs[f"{n}/reach12/stacked"]["measure"]["svg_kb"] > ctx.runs[f"{n}/reach9/stacked"]["measure"]["svg_kb"])
    d["grow_9_12"] = grow
    d["grow_names_shrink"] = ", ".join(f"<code>{n}</code>" for n in SOURCES if ctx.runs[f"{n}/reach9/stacked"]["measure"]["svg_kb"] < ctx.runs[f"{n}/reach3/stacked"]["measure"]["svg_kb"])
    return d


def chapter7(ctx):
    d = {}
    def trio(prefix, before, after, colors, box, z, background=(255, 255, 255)):
        changed = before != after
        a = classes(crop(before, box), colors, background)
        b = classes(crop(after, box), colors, background)
        d[f"{prefix}_before"] = save(zoom(a, z), f"7-{prefix}-before.png")
        d[f"{prefix}_after"] = save(zoom(b, z), f"7-{prefix}-after.png")
        d[f"{prefix}_diff"] = save(zoom(over(a, crop(changed, box), MASK, 1.0, 0.45), z), f"7-{prefix}-diff.png")

    # Fringes: the second pass's first call, in class space at source size.
    t = ctx.new("float")
    call = t.fringes[-2]
    before = call["args"][0]
    after, bands = call["result"]
    palette = call["args"][2]
    colors = lab_rgb(palette[:-1])
    box = densest(bands, 90)
    trio("fr", before, after, colors, box, 5)
    d["fr_src"] = save(zoom(crop(load(SOURCES["float"]), box), 5), "7-fr-src.png")
    d["fr_count"] = f"{t.result.info['fringe_pixels']:,}".replace(",", ".")
    # The two palette passes.
    d["s7_pass1"] = swatches([(to_hex(c), "") for c in t.palettes[0]["result"].rgb])
    d["s7_pass2"] = swatches([(to_hex(c), "") for c in t.palettes[1]["result"].rgb])
    d["pass1_n"], d["pass2_n"] = len(t.palettes[0]["result"].rgb), len(t.palettes[1]["result"].rgb)

    # Specks.
    t = ctx.new("diver")
    call = t.specks[0]
    before, after = call["args"][0], call["result"]
    colors = lab_rgb(call["args"][1][:-1])
    box = densest(before != after, 140)
    trio("sp", before, after, colors, box, 3)
    d["sp_changed"] = f"{int((before != after).sum() / 4):,}".replace(",", ".")
    src2 = zoom(load(SOURCES["diver"]), 2)
    d["sp_src"] = save(zoom(crop(src2, box), 3), "7-sp-src.png")
    # The same rule where it does what it is for.
    t = ctx.new("principito")
    call = t.specks[0]
    before, after = call["args"][0], call["result"]
    colors = lab_rgb(call["args"][1][:-1])
    box = densest(before != after, 120)
    trio("sq", before, after, colors, box, 3)
    src2 = zoom(load(SOURCES["principito"]), 2)
    d["sq_src"] = save(zoom(crop(src2, box), 3), "7-sq-src.png")

    # A crowd of islands.
    t = ctx.new("watchmaker")
    call = t.speckle[0]
    before, (after, n) = call["args"][0], call["result"]
    colors = lab_rgb(call["args"][1][:-1])
    box = densest(before != after, 150)
    trio("cr", before, after, colors, box, 3)
    src2 = zoom(load(SOURCES["watchmaker"]), 2)
    d["cr_src"] = save(zoom(crop(src2, box), 3), "7-cr-src.png")
    d["cr_islands"] = n
    # And where a crowd really is texture.
    t = ctx.new("float")
    call = t.speckle[0]
    before, (after, nf) = call["args"][0], call["result"]
    colors = lab_rgb(call["args"][1][:-1])
    box = densest(before != after, 150)
    trio("cf", before, after, colors, box, 3)
    src2 = zoom(load(SOURCES["float"]), 2)
    d["cf_src"] = save(zoom(crop(src2, box), 3), "7-cf-src.png")
    d["cf_islands"] = nf
    per = {name: ctx.new(name).result.info.get("speckle_islands", 0) for name in SOURCES}
    d["cr_per"] = ", ".join(f"<code>{k}</code> {v}" for k, v in per.items())

    # Pale pieces adrift, on a dark ground so they show.
    t = ctx.new("leaves")
    call = t.floating[0]
    before, (after, n) = call["args"][0], call["result"]
    palette_all = call["args"][1]
    colors = lab_rgb(palette_all[:-1])
    dark = (40, 44, 60)
    W = 620
    changed = before != after
    d["fl_before"] = save(shrink(classes(before, colors, dark), W), "7-fl-before.png")
    d["fl_after"] = save(shrink(classes(after, colors, dark), W), "7-fl-after.png")
    box = densest(changed, 160)
    z = 2
    d["fl_z_before"] = save(zoom(classes(crop(before, box), colors, dark), z), "7-fl-z-before.png")
    d["fl_z_after"] = save(zoom(classes(crop(after, box), colors, dark), z), "7-fl-z-after.png")
    src2 = zoom(load(SOURCES["leaves"]), 2)
    d["fl_z_src"] = save(zoom(crop(src2, box), z), "7-fl-z-src.png")
    d["fl_count"] = n

    # The neighbor vote: the very function, with and without its rounds.
    t = ctx.new("axolotl")
    a = t.assigns[-1]["args"]
    r0 = lab_mod.assign(a[0], a[1], a[2], a[3], rounds=0)
    r3 = t.assigns[-1]["result"]
    colors = lab_rgb(a[3])
    changed = r0 != r3
    box = densest(changed, 60)
    d["v_a"] = save(zoom(classes(crop(r0, box), colors), 6), "7-v-a.png")
    d["v_b"] = save(zoom(classes(crop(r3, box), colors), 6), "7-v-b.png")
    d["v_changed"] = f"{int(changed.sum()):,}".replace(",", ".")

    # Doubling the map along the walls.
    t = ctx.new("principito")
    call = t.refine[-1]
    label = call["args"][0]
    fine = call["result"][0]
    colors = lab_rgb(call["args"][2])
    block = np.repeat(np.repeat(label, 2, 0), 2, 1)
    box = densest(block != fine, 60)
    d["re_a"] = save(zoom(classes(crop(block, box), colors), 5), "7-re-a.png")
    d["re_b"] = save(zoom(classes(crop(fine, box), colors), 5), "7-re-b.png")
    return d
