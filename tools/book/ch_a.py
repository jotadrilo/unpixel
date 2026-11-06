"""Figures for chapters 1 to 4: raster and vector, the two pipelines, kinds of image, and color."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ni
from scipy.cluster.vq import kmeans2

from draw import annotate, classes, crop, faded, groups, only_group, outlines_only, over, save, scaled, shrink, svg_crop, zoom
from harness import ROOT, SOURCES, classify_mod, lab_mod, load, patched, patches, pipe_mod, recorder, seg_mod, trace_classic, trace_new, vec_mod
from unpixel.color import delta_e, srgb_to_lab, to_hex

sys.path.insert(0, str(ROOT / "tools/engine"))
import synth  # noqa: E402


def lab_rgb(lab):
    """A working-space image back in sRGB, through the engine's own inverse."""
    return lab_mod.lab_to_srgb(lab_mod.from_perceptual(lab))


def swatches(rows):
    """A palette as HTML: rows of (hex, note)."""
    return '<div class="swatches">' + "".join(
        f'<span class="sw" style="background:{c}" title="{c}{" · " + n if n else ""}"></span>' for c, n in rows) + "</div>"


def chapter1(ctx):
    d = {}
    rgb = load(SOURCES["axolotl"])
    svg_new = ctx.svg("axolotl", "new", "stacked")
    star = (462, 262, 512, 316)
    d["f1_raster"] = save(zoom(crop(rgb, star), 8), "1-raster.png")
    d["f1_vector"] = save(svg_crop(svg_new, star, 8), "1-vector.png")
    kind = classify_mod.classify(rgb)
    d["axolotl_source_colors"] = f"{kind.colors:,}".replace(",", ".")
    d["axolotl_new_colors"] = len(groups(svg_new))
    art = (250, 20, 1160, 750)
    d["f1_whole"] = save(shrink(rgb, 900), "1-whole.jpg")
    tiles = []
    for name, color in groups(svg_new):
        im = svg_crop(only_group(svg_new, name), art, width=260, background="#ffffff")
        path = save(im.convert("RGB"), f"1-layer-{name}.png")
        tiles.append(f'<figure class="tile"><img loading="lazy" src="{path}" alt="capa {name}"><figcaption><span class="dot" style="background:{color}"></span>{color}</figcaption></figure>')
    d["f1_layers"] = "".join(tiles)
    ufo = (420, 60, 640, 215)
    cut = ctx.svg("axolotl", "new", "cutout")
    d["f1_filled"] = save(svg_crop(svg_new, ufo, 3), "1-ufo-filled.png")
    d["f1_pen"] = save(svg_crop(outlines_only(cut, 0.35, "#16202c"), ufo, 3), "1-ufo-pen.png")
    return d


def chapter2(ctx):
    d = {}
    box = (560, 130, 720, 250)
    rgb = load(SOURCES["axolotl"])
    tc = ctx.classic("axolotl")
    s = tc.seg.scale
    bs = scaled(box, s)
    strip = [("Fuente", shrink(zoom(crop(rgb, box), 2), 320))]
    strip.append(("<code>_gauss_rgb</code>: copia a {:.0f}× y desenfocada".format(s), shrink(crop(tc.gauss[0]["result"], bs), 320)))
    sharp = tc.nearest[0]["args"][0]
    strip.append(("Enfoque: <code>base + 2 × (base − blur)</code>", shrink(lab_mod.lab_to_srgb(crop(sharp, bs)), 320)))
    centers = tc.nearest[0]["args"][1]
    strip.append(("<code>_nearest</code>: grupos de color", shrink(lab_mod.lab_to_srgb(centers)[crop(tc.nearest[0]["result"], bs)], 320)))
    strip.append(("Regiones con color propio", shrink(classes(crop(tc.seg.raw_labels, bs), tc.seg.colors), 320)))
    strip.append(("<code>_smooth_partition</code>", shrink(classes(crop(tc.seg.labels, bs), tc.seg.colors), 320)))
    strip.append(("potrace por capa, solapadas", svg_crop(ctx.svg("axolotl", "classic", "stacked"), box, 2)))
    cells = []
    for i, (label, im) in enumerate(strip):
        p = save(im.convert("RGB") if hasattr(im, "convert") else im, f"2-classic-{i}.png")
        cells.append(f'<figure class="step"><img loading="lazy" src="{p}" alt=""><figcaption>{label}</figcaption></figure>')
    d["f2_classic"] = "".join(cells)

    tn = ctx.new("axolotl")
    first = tn.assigns[0]["result"]
    pal0 = tn.palettes[0]["result"]
    last = tn.assigns[-1]["result"]
    pal1 = tn.palettes[-1]["result"]
    b2 = scaled(box, 2)
    strip = [("Fuente", zoom(crop(rgb, box), 2))]
    strip.append(("<code>bilateral</code> y <code>flatten_gradients</code>", zoom(lab_rgb(crop(tn.lab, box)), 2)))
    strip.append(("<code>transition_mask</code> (magenta)", zoom(over(crop(rgb, box), crop(tn.transition, box), (214, 0, 120)), 2)))
    strip.append(("<code>assign</code> en la paleta", zoom(classes(crop(last, box), pal1.rgb), 2)))
    strip.append(("<code>dissolve_fringes</code> y <code>refine_double</code> a 2×", crop(classes(tn.refine[-1]["result"][0], tn.result.colors), b2)))
    strip.append(("<code>absorb_specks</code> y compañía", crop(classes(tn.result.labels, tn.result.colors), b2)))
    strip.append(("Mapa plano y curvas compartidas", svg_crop(ctx.svg("axolotl", "new", "stacked"), box, 2)))
    cells = []
    for i, (label, im) in enumerate(strip):
        p = save(im.convert("RGB") if hasattr(im, "convert") else im, f"2-new-{i}.png")
        cells.append(f'<figure class="step"><img loading="lazy" src="{p}" alt=""><figcaption>{label}</figcaption></figure>')
    d["f2_new"] = "".join(cells)
    del first, pal0
    d["classic_scale"] = f"{s:.0f}"
    return d


def scan_chart(values, thresholds, label):
    """Bars of the color step between neighboring pixels along one row of a real image."""
    w, h, pad = 560, 120, 26
    n = len(values)
    top = max(max(values), thresholds[0] * 1.3, 1.0)
    bars = []
    for i, v in enumerate(values):
        x = pad + (w - pad - 6) * i / n
        bh = (h - 22) * v / top
        bars.append(f'<rect x="{x:.1f}" y="{h - 14 - bh:.1f}" width="{max(1.2, (w - pad - 6) / n - 1):.1f}" height="{bh:.1f}" rx="1" fill="var(--s1)"><title>ΔE {v:.1f}</title></rect>')
    y15 = h - 14 - (h - 22) * thresholds[0] / top
    y3 = h - 14 - (h - 22) * thresholds[1] / top
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
            f'<line x1="{pad}" x2="{w - 4}" y1="{y15:.1f}" y2="{y15:.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
            f'<text x="{w - 4}" y="{y15 - 3:.1f}" text-anchor="end" class="ct">fuerte &gt; 15</text>'
            f'<line x1="{pad}" x2="{w - 4}" y1="{y3:.1f}" y2="{y3:.1f}" stroke="var(--muted)" stroke-dasharray="1 3"/>'
            f'<text x="2" y="{y3 + 3:.1f}" class="ct">3</text><text x="2" y="{y15 + 3:.1f}" class="ct">15</text>'
            + "".join(bars) + f'<line x1="{pad}" x2="{w - 4}" y1="{h - 14}" y2="{h - 14}" stroke="var(--muted)"/></svg>')


def chapter3(ctx):
    d = {}
    work = ctx.work / "synth"
    work.mkdir(parents=True, exist_ok=True)
    pix = np.asarray(synth.pixel_art().convert("RGB"))
    hard = np.asarray(synth.geometry(1).convert("RGB"))
    aa = np.asarray(synth.geometry(4).convert("RGB"))
    soft = load(SOURCES["axolotl"])
    rows = []
    cases = [("synth-pixel", pix), ("synth-hard", hard), ("synth-aa", aa), ("axolotl", soft), ("ghost", load(SOURCES["ghost"]))]
    for name, rgb in cases:
        k = classify_mod.classify(rgb)
        rows.append(f"<tr><td><code>{name}</code></td><td><b>{k.name}</b></td><td>{k.block}</td><td>{str(round(k.hard_share, 3)).replace(".", ",")}</td><td>{str(k.colors) if k.colors < 1000 else f"{k.colors // 1000}.{k.colors % 1000:03d}"}</td></tr>")
    d["t3_kinds"] = "".join(rows)
    others = []
    for name, src in SOURCES.items():
        others.append(classify_mod.classify(load(src)).name)
    d["battery_all_soft"] = "todas" if set(others) == {"soft"} else str(others)
    d["f3_pix"] = save(shrink(pix, 256), "3-pix.png")
    d["f3_hard"] = save(shrink(hard, 400), "3-hard.png")
    d["f3_aa"] = save(shrink(aa, 400), "3-aa.png")
    # A row across an edge in each image, and the color step between each pair of neighbors.
    charts = {}
    # In the real drawing, the stretch of one row around its strongest edge.
    row = srgb_to_lab(soft[200]).astype(np.float64)
    at = int(np.argmax(np.sqrt(((row[1:] - row[:-1]) ** 2).sum(-1))))
    at = min(max(at, 30), soft.shape[1] - 31)
    for name, rgb, (y, x0, x1) in (("pix", pix, (40, 20, 80)), ("hard", hard, (190, 110, 170)), ("aa", aa, (190, 110, 170)), ("soft", soft, (200, at - 30, at + 30))):
        row = srgb_to_lab(rgb[y, x0:x1]).astype(np.float64)
        steps = np.sqrt(((row[1:] - row[:-1]) ** 2).sum(-1)).tolist()
        charts[name] = scan_chart(steps, (15.0, 3.0), f"Salto de color por píxel en {name}")
    d["c3_pix"], d["c3_hard"], d["c3_aa"], d["c3_soft"] = charts["pix"], charts["hard"], charts["aa"], charts["soft"]
    # What each engine does with pixel art: its corners, magnified.
    out_new = pipe_mod.run(pix, "stacked", "pix")
    tc = trace_classic(pix, "pix")
    box = (16, 16, 112, 112)
    d["f3_px_src"] = save(zoom(crop(pix, box), 4), "3-px-src.png")
    d["f3_px_new"] = save(svg_crop(out_new.svg, box, 4), "3-px-new.png")
    d["f3_px_classic"] = save(svg_crop(tc.svg, box, 4), "3-px-classic.png")
    d["px_new_kind"] = out_new.kind
    d["px_block"] = classify_mod.classify(pix).block
    hard_new = pipe_mod.run(hard, "stacked", "hard")
    th = trace_classic(hard, "hard")
    tip = (540, 60, 640, 140)
    d["f3_h_src"] = save(zoom(crop(hard, tip), 4), "3-h-src.png")
    d["f3_h_new"] = save(svg_crop(hard_new.svg, tip, 4), "3-h-new.png")
    d["f3_h_classic"] = save(svg_crop(th.svg, tip, 4), "3-h-classic.png")
    d["hard_new_kind"] = hard_new.kind
    # An image the classic engine turns down and the new one takes: noise over a ramp, made here, seed fixed.
    noise_rng = np.random.default_rng(3)
    ramp = np.linspace(0, 255, 600)[None, :, None] * np.ones((400, 600, 3))
    noisy = np.clip(ramp + noise_rng.normal(0, 28, (400, 600, 3)), 0, 255).astype(np.uint8)
    try:
        seg_mod.segment(noisy, ctx.options)
        d["refusal"] = "(el motor clásico la aceptó)"
    except seg_mod.UnsuitableImage as e:
        d["refusal"] = str(e)
    r = pipe_mod.run(noisy, "stacked", "noise")
    d["f3_noise_src"] = save(noisy, "3-noise-src.png")
    d["f3_noise_new"] = save(svg_crop(r.svg).convert("RGB"), "3-noise-new.png")
    d["noise_kind"] = r.kind
    d["noise_colors"] = len(r.colors)
    d["noise_kb"] = round(len(r.svg) / 1024)
    return d


def real_kmeans(rgb, k=16, seed=1):
    """K-means itself, from scipy, on the median-filtered image in Lab: the recipe of the early prototype."""
    den = np.stack([ni.median_filter(rgb[..., i], size=3) for i in range(3)], -1)
    lab = srgb_to_lab(den).reshape(-1, 3)
    centers, _ = kmeans2(lab[::5].astype(np.float64), k, minit="++", iter=30, seed=seed)
    label = np.empty(lab.shape[0], dtype=np.int16)
    for s in range(0, lab.shape[0], 200_000):
        label[s : s + 200_000] = ((lab[s : s + 200_000, None, :] - centers[None]) ** 2).sum(-1).argmin(1)
    return centers.astype(np.float32), label.reshape(rgb.shape[:2])


def plain_lab_to_rgb(lab):
    return lab_mod.lab_to_srgb(lab)


def compression_chart():
    """The real `perceptual` measured on a grid: how much of a color's chroma survives."""
    w, h, l, b = 560, 200, 34, 24
    lines = []
    for lightness, color, name in ((60.0, "var(--s1)", "L = 60"), (20.0, "var(--s2)", "L = 20"), (10.0, "var(--s3)", "L = 10")):
        cs = np.arange(0.0, 111.0, 5.0)
        lab = np.stack([np.full_like(cs, lightness), cs, np.zeros_like(cs)], -1).astype(np.float32)
        out = lab_mod.perceptual(lab)
        kept = out[:, 1] / np.maximum(cs, 1e-3)
        kept[0] = lab_mod.perceptual(np.array([lightness, 1.0, 0.0], dtype=np.float32))[1]
        pts = " ".join(f"{l + (w - l - 56) * c / 110:.1f},{10 + (h - b - 10) * (1 - v):.1f}" for c, v in zip(cs, kept))
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>')
        lx = l + (w - l - 56) + 4
        ly = 10 + (h - b - 10) * (1 - kept[-1]) + 4
        lines.append(f'<text x="{lx}" y="{ly:.1f}" class="ct">{name}</text>')
    axis = (f'<line x1="{l}" x2="{w - 56}" y1="{h - b}" y2="{h - b}" stroke="var(--muted)"/>'
            + "".join(f'<text x="{l + (w - l - 56) * c / 110:.0f}" y="{h - 8}" text-anchor="middle" class="ct">{c}</text>' for c in (0, 25, 50, 75, 100))
            + "".join(f'<line x1="{l}" x2="{w - 56}" y1="{10 + (h - b - 10) * (1 - v):.1f}" y2="{10 + (h - b - 10) * (1 - v):.1f}" stroke="var(--grid)"/>'
                      f'<text x="{l - 4}" y="{14 + (h - b - 10) * (1 - v):.1f}" text-anchor="end" class="ct">{int(v * 100)}%</text>' for v in (0.25, 0.5, 0.75, 1.0)))
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Porcentaje de croma conservado según croma y luminosidad">{axis}{"".join(lines)}</svg>'


def chapter4(ctx):
    d = {"c4_compress": compression_chart()}
    # Pairs of real colors: distance in plain Lab and in the working space.
    pairs = [("dos violetas saturados", (153, 87, 250), (113, 96, 225)), ("dos negros tintados", (28, 21, 43), (9, 12, 25)),
             ("dos rosas pálidos", (251, 187, 206), (246, 166, 190)), ("dos marrones medios", (176, 119, 40), (205, 138, 51))]
    rows = []
    for name, a, b in pairs:
        la, lb = srgb_to_lab(np.array(a, dtype=np.float32)), srgb_to_lab(np.array(b, dtype=np.float32))
        plain = float(delta_e(la, lb))
        warped = float(delta_e(lab_mod.perceptual(la), lab_mod.perceptual(lb)))
        rows.append(f'<tr><td><span class="dot" style="background:{to_hex(a)}"></span><span class="dot" style="background:{to_hex(b)}"></span> {name}</td><td>{plain:.1f}</td><td>{warped:.1f}</td></tr>')
    d["t4_pairs"] = "".join(rows)

    # The palette with the warp turned off, on the same image: both functions become the identity.
    rgb = load(SOURCES["axolotl"])
    with_warp = ctx.new("axolotl").result
    ident = lambda fn: (lambda lab: np.asarray(lab, dtype=np.float32))  # noqa: E731
    with patches((lab_mod, "perceptual", ident), (lab_mod, "from_perceptual", ident)):
        no_warp = pipe_mod.run(rgb, "stacked", "axolotl")
    def strip(colors):
        lab = srgb_to_lab(np.array(colors, dtype=np.float32))
        order = np.argsort(lab[:, 0])
        return swatches([(to_hex(colors[i]), f"L {lab[i, 0]:.0f}") for i in order])
    d["s4_warp"] = strip(with_warp.colors)
    d["s4_nowarp"] = strip(no_warp.colors)
    def darks(colors):
        lab = srgb_to_lab(np.array(colors, dtype=np.float32))
        return int((lab[:, 0] < 25).sum()), len(colors), [to_hex(c) for c, v in zip(colors, lab[:, 0]) if v < 25]
    d["warp_darks"], d["warp_n"], d["warp_darks_list"] = darks(with_warp.colors)
    d["nowarp_darks"], d["nowarp_n"], d["nowarp_darks_list"] = darks(no_warp.colors)
    def violets(colors):
        lab = srgb_to_lab(np.array(colors, dtype=np.float32))
        hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
        chroma = np.hypot(lab[:, 1], lab[:, 2])
        return [to_hex(c) for c, h, ch, l in zip(colors, hue, chroma, lab[:, 0]) if 270 <= h <= 330 and ch > 30]
    d["warp_violets"] = ", ".join(violets(with_warp.colors))
    d["nowarp_violets"] = ", ".join(violets(no_warp.colors))
    rows = []
    for name in SOURCES:
        one = load(SOURCES[name])
        base = with_warp if name == "axolotl" else ctx.new(name).result
        if name == "axolotl":
            off = no_warp
        else:
            with patches((lab_mod, "perceptual", ident), (lab_mod, "from_perceptual", ident)):
                off = pipe_mod.run(one, "stacked", name)
        rows.append(f"<tr><td><code>{name}</code></td><td>{len(base.colors)} ({darks(base.colors)[0]})</td><td>{len(off.colors)} ({darks(off.colors)[0]})</td></tr>")
    d["t4_nowarp"] = "".join(rows)
    head = (640, 120, 800, 260)
    d["f4_warp"] = save(svg_crop(with_warp.svg, head, 2), "4-warp.png")
    d["f4_nowarp"] = save(svg_crop(no_warp.svg, head, 2), "4-nowarp.png")

    # The Little Prince: k-means, classic and new, in the same three places.
    rgb = load(SOURCES["principito"])
    centers, km = real_kmeans(rgb)
    km_rgb = plain_lab_to_rgb(centers)
    km_img = km_rgb[km].astype(np.uint8)
    tc = ctx.classic("principito")
    tn = ctx.new("principito")
    svg_c = ctx.svg("principito", "classic", "stacked")
    svg_n = ctx.svg("principito", "new", "stacked")
    spots = {"mano": (400, 330, 560, 460), "vidrio": (740, 560, 860, 760), "brillo": (960, 620, 1200, 860)}
    targets = {"mano": "#FCD0AB", "vidrio": "#B5C2FA", "brillo": "#CF8931"}
    plain = srgb_to_lab(rgb)
    for name, box in spots.items():
        z = 2
        d[f"f4_{name}_src"] = save(zoom(crop(rgb, box), z), f"4-{name}-src.png")
        d[f"f4_{name}_km"] = save(zoom(crop(km_img, box), z), f"4-{name}-km.png")
        d[f"f4_{name}_c"] = save(svg_crop(svg_c, box, z), f"4-{name}-classic.png")
        d[f"f4_{name}_n"] = save(svg_crop(svg_n, box, z), f"4-{name}-new.png")
    # What each engine painted, at a spot deep inside each small color of the source.
    from draw import svg_crop as render
    painted_c = np.asarray(render(svg_c).convert("RGB"))
    painted_n = np.asarray(render(svg_n).convert("RGB"))
    wanted = [("piel", "#FCD0AB"), ("vidrio", "#B8C3F9"), ("brillo del suelo", "#CD8A33"), ("sombra", "#8B531E"),
              ("catalejo", "#2348AE"), ("zapato", "#740C11"), ("azul marino", "#09295F"), ("banda de cielo", "#505BAD")]
    rows, spot_of = [], {}
    for name, hx in wanted:
        target = srgb_to_lab(np.array([int(hx[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32))
        inside = delta_e(plain, target) < 7.0
        depth = ni.distance_transform_edt(inside)
        y, x = np.unravel_index(int(np.argmax(depth)), depth.shape)
        spot_of[name] = (int(x), int(y))
        cells = [f'<td><span class="dot" style="background:{to_hex(rgb[y, x])}"></span>{name}</td>']
        for im in (km_img, painted_c, painted_n):
            v = im[y, x]
            cells.append(f'<td><span class="dot" style="background:{to_hex(v)}"></span>{float(delta_e(srgb_to_lab(v.astype(np.float32)), plain[y, x])):.1f}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    d["t4_probes"] = "".join(rows)
    d["spots"] = str(spot_of)
    # Palette strips with area, from what was painted.
    def area_rows(labels, colors):
        counts = np.bincount(labels.ravel(), minlength=len(colors))[: len(colors)]
        total = labels.size
        order = np.argsort(-counts)
        return [(to_hex(colors[i]), f"{100 * counts[i] / total:.2f}%") for i in order]
    d["s4_km"] = swatches(area_rows(km, km_rgb))
    d["s4_classic"] = swatches(area_rows(np.where(tc.seg.labels < 0, 0, tc.seg.labels), tc.seg.colors))
    d["s4_new"] = swatches(area_rows(np.where(tn.result.labels >= len(tn.result.colors), 0, tn.result.labels), tn.result.colors))

    # Where the classic engine's small colors go: its own bookkeeping.
    L = tc.segment_locals
    rows = []
    order = np.argsort(-np.array(L["areas"]))
    total = sum(L["areas"])
    src_map = L["source_mapping"]
    for i in order:
        area = 100 * L["areas"][i] / total
        goes = to_hex(L["rgbs"][src_map[i]])
        own = to_hex(L["rgbs"][i])
        if goes != own:
            rows.append(f'<tr><td><span class="dot" style="background:{own}"></span>{own}</td><td>{f"{area:.3f}".replace(".", ",")} %</td><td><span class="dot" style="background:{goes}"></span>{goes}</td>'
                        f'<td>{float(delta_e(L["rgb_lab"][i], L["rgb_lab"][src_map[i]])):.1f}</td></tr>')
    d["t4_merged"] = "".join(rows)
    d["classic_found"] = len(L["rgbs"])
    d["classic_final"] = len(tc.seg.colors)
    # The ground of the Little Prince, as classified: lit and plain brown are one group, so one connected region.
    box = (960, 620, 1200, 860)
    s = tc.seg.scale
    bs = scaled(box, s)
    grp_img = lab_mod.lab_to_srgb(tc.nearest[-1]["args"][1])[crop(tc.nearest[-1]["result"], bs)]
    d["f4_groups"] = save(shrink(grp_img, 480), "4-classic-groups.png")
    cen = tc.nearest[-1]["args"][1]
    biggest = max(tc.splits, key=lambda v: v["flat_pixels"])
    d["split_a"], d["split_b"] = to_hex(lab_mod.lab_to_srgb(biggest["a"])), to_hex(lab_mod.lab_to_srgb(biggest["b"]))
    d["split_share"] = f"{100 * biggest['minor_share']:.1f}".replace(".", ",")
    d["split_limit"] = f"{100 * seg_mod.SPLIT_MIN_SHARE:.0f}"
    a = srgb_to_lab(np.array((176, 119, 40), dtype=np.float32))
    b = srgb_to_lab(np.array((205, 138, 51), dtype=np.float32))
    d["ground_de"] = f"{float(delta_e(a, b)):.1f}".replace(".", ",")
    d["group_de"] = f"{seg_mod.GROUP_DE:.0f}"
    d["classic_groups"] = len(cen)

    # Farthest point, one color at a time, on the real seeds.
    pl = tn.palette_locals[-1]
    seeds = np.asarray(pl["seeds"], dtype=np.float32)
    lab = tn.lab
    zeros = np.zeros(lab.shape[:2], bool)
    nothing = lab_mod.Background(zeros, None)
    strip = []
    for n in (1, 2, 3, 5, 9, len(seeds)):
        lab_seed = seeds[:n]
        lab_mapped = lab_mod.assign(lab, zeros, nothing, lab_seed, smoothness=0.0, rounds=0)
        im = lab_rgb(lab_seed)[np.minimum(lab_mapped, n - 1)]
        p = save(shrink(im, 420), f"4-seeds-{n}.jpg")
        strip.append(f'<figure class="step"><img loading="lazy" src="{p}" alt=""><figcaption>{n} {"color" if n == 1 else "colores"}</figcaption></figure>')
    d["f4_seeds"] = "".join(strip)
    kinds = []
    log = [line for line in pl["log"] if line.startswith("+") or line.startswith("-")]
    seed_hex = [to_hex(c) for c in lab_rgb(seeds)]
    kinds.append(f'<tr><td>1</td><td><span class="dot" style="background:{seed_hex[0]}"></span>{seed_hex[0]}</td><td>mayor masa</td><td>—</td><td>—</td></tr>')
    for line in log:
        parts = line.split()
        if not parts[0].startswith("+"):
            continue
        n = int(parts[0][1:])
        if n > len(seed_hex):
            continue
        why = {"highlight": "brillo", "saturated": "oscuro saturado"}.get(parts[1], "distancia × masa")
        de = [p for p in parts if p.startswith("d=")][0][2:]
        mass = [p for p in parts if p.startswith("mass=")][0][5:]
        kinds.append(f'<tr><td>{n}</td><td><span class="dot" style="background:{seed_hex[n - 1]}"></span>{seed_hex[n - 1]}</td><td>{why}</td><td>{de.replace(".", ",")}</td><td>{mass.replace(".", ",").replace("%", " %")}</td></tr>')
    d["t4_seeds"] = "".join(kinds)
    d["seed_count"] = len(seeds)

    # Counterexperiments: the same run without each protection.
    with patched(lab_mod, "highlight_mask", lambda fn: (lambda lab, solid, **k: np.zeros(solid.shape, bool))):
        no_hl = pipe_mod.run(rgb, "stacked", "principito")
    old = lab_mod.SAT_DARK_SLOTS
    lab_mod.SAT_DARK_SLOTS = 0
    try:
        no_sat = pipe_mod.run(rgb, "stacked", "principito")
    finally:
        lab_mod.SAT_DARK_SLOTS = old
    d["s4_full"] = swatches([(to_hex(c), "") for c in tn.result.colors])
    d["s4_nohl"] = swatches([(to_hex(c), "") for c in no_hl.colors])
    d["s4_nosat"] = swatches([(to_hex(c), "") for c in no_sat.colors])
    d["full_n"], d["nohl_n"], d["nosat_n"] = len(tn.result.colors), len(no_hl.colors), len(no_sat.colors)
    cx, cy = spot_of["zapato"]
    shoe = (cx - 45, cy - 30, cx + 45, cy + 30)
    cx, cy = spot_of["catalejo"]
    scope = (cx - 60, cy - 50, cx + 60, cy + 50)
    for key, box in (("shoe", shoe), ("scope", scope)):
        d[f"f4_sat_{key}_off"] = save(svg_crop(no_sat.svg, box, 3), f"4-sat-{key}-off.png")
        d[f"f4_sat_{key}_on"] = save(svg_crop(svg_n, box, 3), f"4-sat-{key}-on.png")
        d[f"f4_sat_{key}_src"] = save(zoom(crop(rgb, box), 3), f"4-sat-{key}-src.png")
    def lost(base, other):
        table = srgb_to_lab(np.array(other, dtype=np.float32))
        return [to_hex(c) for c in base if float(delta_e(table, srgb_to_lab(np.array(c, dtype=np.float32))).min()) > 8.0]
    d["nohl_lost_p"] = ", ".join(lost(tn.result.colors, no_hl.colors))
    d["nosat_lost_p"] = ", ".join(lost(tn.result.colors, no_sat.colors))
    # On the diver, the same switch costs what the rule is for.
    dv_rgb = load(SOURCES["diver"])
    dv = ctx.new("diver").result
    with patched(lab_mod, "highlight_mask", lambda fn: (lambda lab, solid, **k: np.zeros(solid.shape, bool))):
        dv_off = pipe_mod.run(dv_rgb, "stacked", "diver")
    gone = lost(dv.colors, dv_off.colors)
    d["nohl_lost_d"] = ", ".join(gone)
    d["dv_on_n"], d["dv_off_n"] = len(dv.colors), len(dv_off.colors)
    d["s4_dv_on"] = swatches([(to_hex(c), "") for c in dv.colors])
    d["s4_dv_off"] = swatches([(to_hex(c), "") for c in dv_off.colors])
    target = srgb_to_lab(np.array((132, 241, 237), dtype=np.float32))
    painted = np.asarray(render(ctx.svg("diver", "new", "stacked")).convert("RGB"))
    near = delta_e(srgb_to_lab(painted), target) < 3.0
    from ch_b import densest
    box = densest(near, 90)
    d["f4_hl_src"] = save(zoom(crop(dv_rgb, box), 4), "4-hl-src.png")
    d["f4_hl_on"] = save(svg_crop(dv.svg, box, 4), "4-hl-on.png")
    d["f4_hl_off"] = save(svg_crop(dv_off.svg, box, 4), "4-hl-off.png")
    return d
