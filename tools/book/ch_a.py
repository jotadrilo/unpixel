"""Figures for chapters 1 to 4: raster and vector, the pipeline, kinds of image, and color."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ni
from scipy.cluster.vq import kmeans2

from draw import crop, classes, groups, num, only_group, outlines_only, over, pct, save, scaled, shrink, svg_crop, tr, zoom
from harness import ROOT, SOURCES, classify_mod, lab_mod, load, locals_of, patched, patches, pipe_mod, recorder
from unpixel.cli import Options
from unpixel.color import delta_e, srgb_to_lab, to_hex
from unpixel.engine import adapter

sys.path.insert(0, str(ROOT / "tools/engine"))
import synth  # noqa: E402

HERE = Path(__file__).resolve().parent


def lab_rgb(lab):
    """A working-space image back in sRGB, through the engine's own inverse."""
    return lab_mod.lab_to_srgb(lab_mod.from_perceptual(lab))


def swatches(rows):
    """A palette as HTML: rows of (hex, note)."""
    return '<div class="swatches">' + "".join(
        f'<span class="sw" style="background:{c}" title="{c}{" · " + n if n else ""}"></span>' for c, n in rows) + "</div>"


def steps(strip, prefix):
    cells = []
    for i, (label, im) in enumerate(strip):
        p = save(im.convert("RGB") if hasattr(im, "convert") else im, f"{prefix}-{i}.png")
        cells.append(f'<figure class="step"><img loading="lazy" src="{p}" alt=""><figcaption>{label}</figcaption></figure>')
    return "".join(cells)


def chapter1(ctx):
    d = {}
    rgb = load(SOURCES["axolotl"])
    svg = ctx.svg("axolotl", "stacked")
    star = (462, 262, 512, 316)
    d["f1_raster"] = save(zoom(crop(rgb, star), 8), "1-raster.png")
    d["f1_vector"] = save(svg_crop(svg, star, 8), "1-vector.png")
    d["axolotl_source_colors"] = num(classify_mod.classify(rgb).colors)
    d["axolotl_colors"] = num(len(groups(svg)))
    art = (250, 20, 1160, 750)
    tiles = []
    for name, color in groups(svg):
        path = save(svg_crop(only_group(svg, name), art, width=260).convert("RGB"), f"1-layer-{name}.png")
        tiles.append(f'<figure class="tile"><img loading="lazy" src="{path}" alt="{color}"><figcaption><span class="dot" style="background:{color}"></span>{color}</figcaption></figure>')
    d["f1_layers"] = "".join(tiles)
    ufo = (420, 60, 640, 215)
    cut = ctx.svg("axolotl", "cutout")
    d["f1_filled"] = save(svg_crop(svg, ufo, 3), "1-ufo-filled.png")
    d["f1_pen"] = save(svg_crop(outlines_only(cut, 0.35, "#16202c"), ufo, 3), "1-ufo-pen.png")
    return d


def chapter2(ctx):
    d = {}
    box = (560, 130, 720, 250)
    rgb = load(SOURCES["axolotl"])
    tn = ctx.run("axolotl")
    last = tn.assigns[-1]["result"]
    pal = tn.palettes[-1]["result"]
    b2 = scaled(box, 2)
    d["f2_steps"] = steps([
        (tr("Source", "Fuente"), zoom(crop(rgb, box), 2)),
        ("<code>bilateral</code>, <code>flatten_gradients</code>", zoom(lab_rgb(crop(tn.lab, box)), 2)),
        (tr("<code>transition_mask</code> (magenta)", "<code>transition_mask</code> (magenta)"), zoom(over(crop(rgb, box), crop(tn.transition, box), (214, 0, 120)), 2)),
        (tr("<code>assign</code> to the palette", "<code>assign</code> en la paleta"), zoom(classes(crop(last, box), pal.rgb), 2)),
        (tr("<code>dissolve_fringes</code>, <code>refine_double</code> at 2×", "<code>dissolve_fringes</code>, <code>refine_double</code> a 2×"), crop(classes(tn.refine[-1]["result"][0], tn.result.colors), b2)),
        (tr("<code>absorb_specks</code> and friends", "<code>absorb_specks</code> y compañía"), crop(classes(tn.result.labels, tn.result.colors), b2)),
        (tr("Planar map and shared curves", "Mapa plano y curvas compartidas"), svg_crop(ctx.svg("axolotl", "stacked"), box, 2)),
    ], "2-step")
    return d


def scan_chart(values, label):
    """Bars of the color step between neighboring pixels along one row of a real image."""
    w, h, pad = 560, 120, 26
    n = len(values)
    top = max(max(values), 15.0 * 1.3, 1.0)
    bars = []
    for i, v in enumerate(values):
        x = pad + (w - pad - 6) * i / n
        bh = (h - 22) * v / top
        bars.append(f'<rect x="{x:.1f}" y="{h - 14 - bh:.1f}" width="{max(1.2, (w - pad - 6) / n - 1):.1f}" height="{bh:.1f}" rx="1" fill="var(--s1)"><title>ΔE {num(v, 1)}</title></rect>')
    y15 = h - 14 - (h - 22) * 15.0 / top
    y3 = h - 14 - (h - 22) * 3.0 / top
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
            f'<line x1="{pad}" x2="{w - 4}" y1="{y15:.1f}" y2="{y15:.1f}" stroke="var(--muted)" stroke-dasharray="3 3"/>'
            f'<text x="{w - 4}" y="{y15 - 3:.1f}" text-anchor="end" class="ct">{tr("strong &gt; 15", "fuerte &gt; 15")}</text>'
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
    for name, rgb in (("synth-pixel", pix), ("synth-hard", hard), ("synth-aa", aa), ("axolotl", soft), ("ghost", load(SOURCES["ghost"]))):
        k = classify_mod.classify(rgb)
        rows.append(f"<tr><td><code>{name}</code></td><td><b>{k.name}</b></td><td>{num(k.block)}</td><td>{num(k.hard_share, 3)}</td><td>{num(k.colors)}</td></tr>")
    d["t3_kinds"] = "".join(rows)
    kinds = {classify_mod.classify(load(src)).name for src in SOURCES.values()}
    if kinds != {"soft"}:
        raise SystemExit(f"the book says every battery image is soft, but got {kinds}")
    charts = {}
    row = srgb_to_lab(soft[200]).astype(np.float64)
    at = int(np.argmax(np.sqrt(((row[1:] - row[:-1]) ** 2).sum(-1))))
    at = min(max(at, 30), soft.shape[1] - 31)
    for name, rgb, (y, x0, x1) in (("pix", pix, (40, 20, 80)), ("hard", hard, (190, 110, 170)), ("aa", aa, (190, 110, 170)), ("soft", soft, (200, at - 30, at + 30))):
        line = srgb_to_lab(rgb[y, x0:x1]).astype(np.float64)
        charts[name] = scan_chart(np.sqrt(((line[1:] - line[:-1]) ** 2).sum(-1)).tolist(), tr(f"Color step per pixel in {name}", f"Salto de color por píxel en {name}"))
    d["c3_pix"], d["c3_hard"], d["c3_aa"], d["c3_soft"] = charts["pix"], charts["hard"], charts["aa"], charts["soft"]
    out = pipe_mod.run(pix, "stacked", "pix")
    box = (16, 16, 112, 112)
    d["f3_px_src"] = save(zoom(crop(pix, box), 4), "3-px-src.png")
    d["f3_px_out"] = save(svg_crop(out.svg, box, 4), "3-px-out.png")
    d["px_block"] = num(classify_mod.classify(pix).block)
    hard_out = pipe_mod.run(hard, "stacked", "hard")
    tip = (540, 60, 640, 140)
    d["f3_h_src"] = save(zoom(crop(hard, tip), 4), "3-h-src.png")
    d["f3_h_out"] = save(svg_crop(hard_out.svg, tip, 4), "3-h-out.png")

    # A busy image with no retry, and through the command line, which retries: noise over a ramp, seed fixed.
    noise_rng = np.random.default_rng(3)
    ramp = np.linspace(0, 255, 600)[None, :, None] * np.ones((400, 600, 3))
    noisy = np.clip(ramp + noise_rng.normal(0, 28, (400, 600, 3)), 0, 255).astype(np.uint8)
    src = work / "noise-ramp.png"
    Image.fromarray(noisy).save(src)
    t = time.perf_counter()
    r = pipe_mod.run(noisy, "stacked", "noise")
    d["noise_before_s"] = num(time.perf_counter() - t, 1)
    d["f3_noise_src"] = save(noisy, "3-noise-src.png")
    d["f3_noise_before"] = save(svg_crop(r.svg).convert("RGB"), "3-noise-before.png")
    d["noise_colors"] = num(len(r.colors))
    d["noise_before_kb"] = num(len(r.svg) / 1024)
    d["noise_before_regions"] = num(lab_mod._regions(r.labels, len(r.colors) + 1)[1])

    def cli(image, out_svg):
        done = subprocess.run([sys.executable, str(HERE / "run_cli_measured.py"), str(image), str(out_svg)],
                              capture_output=True, text=True, timeout=1800)
        if done.returncode:
            raise RuntimeError(done.stderr[-1500:])
        return json.loads(done.stdout)

    out_ramp = work / "noise-ramp.svg"
    after = cli(src, out_ramp)
    d["f3_noise_after"] = save(svg_crop(out_ramp.read_text(encoding="utf-8")).convert("RGB"), "3-noise-after.png")
    d["noise_after_kb"] = num(after["svg_kb"])
    d["noise_after_s"] = num(after["seconds"], 1)
    d["noise_after_mb"] = num(after["peak_rss_mb"])
    d["noise_warning"] = next((w for w in after["warnings"] if "busy" in w), "—")
    tries: list = []
    with patches((pipe_mod, "clean_labels", recorder(tries))), locals_of(adapter.segment) as seen:
        adapter.segment(noisy, Options())
    d["noise_blur"] = num(seen["segment"][0]["blur"])
    d["noise_attempts"] = " → ".join(num(lab_mod._regions(c["result"][0], len(c["result"][4]))[1]) for c in tries)
    d["busy_limit"] = num(adapter.BUSY_REGIONS)
    pure = np.random.default_rng(4).integers(0, 256, (1224, 1224, 3), dtype=np.uint8)
    src_pure = work / "noise-pure.png"
    Image.fromarray(pure).save(src_pure)
    p = cli(src_pure, work / "noise-pure.svg")
    d["pure_s"], d["pure_mb"], d["pure_kb"] = num(p["seconds"], 1), num(p["peak_rss_mb"]), num(p["svg_kb"])
    return d


def real_kmeans(rgb, k=16, seed=1):
    """K-means itself, from scipy, on the median-filtered image in Lab."""
    den = np.stack([ni.median_filter(rgb[..., i], size=3) for i in range(3)], -1)
    lab = srgb_to_lab(den).reshape(-1, 3)
    centers, _ = kmeans2(lab[::5].astype(np.float64), k, minit="++", iter=30, seed=seed)
    label = np.empty(lab.shape[0], dtype=np.int16)
    for s in range(0, lab.shape[0], 200_000):
        label[s : s + 200_000] = ((lab[s : s + 200_000, None, :] - centers[None]) ** 2).sum(-1).argmin(1)
    return centers.astype(np.float32), label.reshape(rgb.shape[:2])


def compression_chart():
    """The real `perceptual` measured on a grid: how much of a color's chroma survives."""
    w, h, l, b = 560, 200, 34, 24
    lines = []
    for lightness, color, name in ((60.0, "var(--s1)", "L = 60"), (20.0, "var(--s2)", "L = 20"), (10.0, "var(--s3)", "L = 10")):
        cs = np.arange(0.0, 111.0, 5.0)
        lab = np.stack([np.full_like(cs, lightness), cs, np.zeros_like(cs)], -1).astype(np.float32)
        kept = lab_mod.perceptual(lab)[:, 1] / np.maximum(cs, 1e-3)
        kept[0] = lab_mod.perceptual(np.array([lightness, 1.0, 0.0], dtype=np.float32))[1]
        pts = " ".join(f"{l + (w - l - 56) * c / 110:.1f},{10 + (h - b - 10) * (1 - v):.1f}" for c, v in zip(cs, kept))
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>')
        lines.append(f'<text x="{l + (w - l - 56) + 4}" y="{10 + (h - b - 10) * (1 - kept[-1]) + 4:.1f}" class="ct">{name}</text>')
    axis = (f'<line x1="{l}" x2="{w - 56}" y1="{h - b}" y2="{h - b}" stroke="var(--muted)"/>'
            + "".join(f'<text x="{l + (w - l - 56) * c / 110:.0f}" y="{h - 8}" text-anchor="middle" class="ct">{c}</text>' for c in (0, 25, 50, 75, 100))
            + "".join(f'<line x1="{l}" x2="{w - 56}" y1="{10 + (h - b - 10) * (1 - v):.1f}" y2="{10 + (h - b - 10) * (1 - v):.1f}" stroke="var(--grid)"/>'
                      f'<text x="{l - 4}" y="{14 + (h - b - 10) * (1 - v):.1f}" text-anchor="end" class="ct">{int(v * 100)}%</text>' for v in (0.25, 0.5, 0.75, 1.0)))
    label = tr("Share of chroma kept, by chroma and lightness", "Porcentaje de croma conservado según croma y luminosidad")
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">{axis}{"".join(lines)}</svg>'


def chapter4(ctx):
    d = {"c4_compress": compression_chart()}
    pairs = [(tr("two saturated violets", "dos violetas saturados"), (153, 87, 250), (113, 96, 225)),
             (tr("two tinted blacks", "dos negros tintados"), (28, 21, 43), (9, 12, 25)),
             (tr("two pale pinks", "dos rosas pálidos"), (251, 187, 206), (246, 166, 190)),
             (tr("two mid browns", "dos marrones medios"), (176, 119, 40), (205, 138, 51))]
    rows = []
    for name, a, b in pairs:
        la, lb = srgb_to_lab(np.array(a, dtype=np.float32)), srgb_to_lab(np.array(b, dtype=np.float32))
        rows.append(f'<tr><td><span class="dot" style="background:{to_hex(a)}"></span><span class="dot" style="background:{to_hex(b)}"></span> {name}</td>'
                    f'<td>{num(float(delta_e(la, lb)), 1)}</td><td>{num(float(delta_e(lab_mod.perceptual(la), lab_mod.perceptual(lb))), 1)}</td></tr>')
    d["t4_pairs"] = "".join(rows)

    # The same run with the warp turned off: both functions become the identity.
    rgb = load(SOURCES["axolotl"])
    with_warp = ctx.run("axolotl").result
    ident = lambda fn: (lambda lab: np.asarray(lab, dtype=np.float32))  # noqa: E731
    with patches((lab_mod, "perceptual", ident), (lab_mod, "from_perceptual", ident)):
        no_warp = pipe_mod.run(rgb, "stacked", "axolotl")

    def strip(colors):
        lab = srgb_to_lab(np.array(colors, dtype=np.float32))
        return swatches([(to_hex(colors[i]), "") for i in np.argsort(lab[:, 0])])

    def darks(colors):
        return int((srgb_to_lab(np.array(colors, dtype=np.float32))[:, 0] < 25).sum())

    def violets(colors):
        lab = srgb_to_lab(np.array(colors, dtype=np.float32))
        hue = np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
        chroma = np.hypot(lab[:, 1], lab[:, 2])
        return ", ".join(to_hex(c) for c, h_, ch in zip(colors, hue, chroma) if 270 <= h_ <= 330 and ch > 30)

    d["s4_warp"], d["s4_nowarp"] = strip(with_warp.colors), strip(no_warp.colors)
    d["warp_n"], d["nowarp_n"] = num(len(with_warp.colors)), num(len(no_warp.colors))
    d["warp_violets"], d["nowarp_violets"] = violets(with_warp.colors), violets(no_warp.colors)
    rows, most = [], 0
    for name in SOURCES:
        base = with_warp if name == "axolotl" else ctx.run(name).result
        if name == "axolotl":
            off = no_warp
        else:
            with patches((lab_mod, "perceptual", ident), (lab_mod, "from_perceptual", ident)):
                off = pipe_mod.run(load(SOURCES[name]), "stacked", name)
        most = max(most, darks(off.colors))
        rows.append(f"<tr><td><code>{name}</code></td><td>{num(len(base.colors))} ({num(darks(base.colors))})</td><td>{num(len(off.colors))} ({num(darks(off.colors))})</td></tr>")
    d["t4_nowarp"] = "".join(rows)
    d["nowarp_darks_max"] = num(most)
    head = (640, 120, 800, 260)
    d["f4_warp"] = save(svg_crop(with_warp.svg, head, 2), "4-warp.png")
    d["f4_nowarp"] = save(svg_crop(no_warp.svg, head, 2), "4-nowarp.png")

    # The Little Prince: generic k-means against unpixel, in the same places.
    rgb = load(SOURCES["principito"])
    centers, km = real_kmeans(rgb)
    km_img = lab_mod.lab_to_srgb(centers)[km].astype(np.uint8)
    tn = ctx.run("principito")
    svg_n = ctx.svg("principito", "stacked")
    spots = {"hand": (400, 330, 560, 460), "glass": (740, 560, 860, 760), "shine": (960, 620, 1200, 860)}
    plain = srgb_to_lab(rgb)
    for name, box in spots.items():
        d[f"f4_{name}_src"] = save(zoom(crop(rgb, box), 2), f"4-{name}-src.png")
        d[f"f4_{name}_km"] = save(zoom(crop(km_img, box), 2), f"4-{name}-km.png")
        d[f"f4_{name}_out"] = save(svg_crop(svg_n, box, 2), f"4-{name}-out.png")
    painted = np.asarray(svg_crop(svg_n).convert("RGB"))
    wanted = [(tr("skin", "piel"), "#FCD0AB"), (tr("glass", "vidrio"), "#B8C3F9"), (tr("ground shine", "brillo del suelo"), "#CD8A33"),
              (tr("shadow", "sombra"), "#8B531E"), (tr("telescope", "catalejo"), "#2348AE"), (tr("shoe", "zapato"), "#740C11"),
              (tr("navy", "azul marino"), "#09295F"), (tr("sky band", "banda de cielo"), "#505BAD")]
    rows, spot_of = [], {}
    for name, hx in wanted:
        target = srgb_to_lab(np.array([int(hx[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float32))
        depth = ni.distance_transform_edt(delta_e(plain, target) < 7.0)
        y, x = np.unravel_index(int(np.argmax(depth)), depth.shape)
        spot_of[hx] = (int(x), int(y))
        cells = [f'<td><span class="dot" style="background:{to_hex(rgb[y, x])}"></span>{name}</td>']
        for im in (km_img, painted):
            v = im[y, x]
            cells.append(f'<td><span class="dot" style="background:{to_hex(v)}"></span>{num(float(delta_e(srgb_to_lab(v.astype(np.float32)), plain[y, x])), 1)}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    d["t4_probes"] = "".join(rows)

    # Farthest point, one color at a time, on the real seeds.
    pl = tn.palette_locals[-1]
    seeds = np.asarray(pl["seeds"], dtype=np.float32)
    zeros = np.zeros(tn.lab.shape[:2], bool)
    nothing = lab_mod.Background(zeros, None)
    strip_seeds = []
    for n in (1, 2, 3, 5, 9, len(seeds)):
        mapped = lab_mod.assign(tn.lab, zeros, nothing, seeds[:n], smoothness=0.0, rounds=0)
        p = save(shrink(lab_rgb(seeds[:n])[np.minimum(mapped, n - 1)], 420), f"4-seeds-{n}.jpg")
        strip_seeds.append(f'<figure class="step"><img loading="lazy" src="{p}" alt=""><figcaption>{n} {tr("color" if n == 1 else "colors", "color" if n == 1 else "colores")}</figcaption></figure>')
    d["f4_seeds"] = "".join(strip_seeds)
    seed_hex = [to_hex(c) for c in lab_rgb(seeds)]
    kinds = [f'<tr><td>1</td><td><span class="dot" style="background:{seed_hex[0]}"></span>{seed_hex[0]}</td><td>{tr("largest mass", "mayor masa")}</td><td>—</td><td>—</td></tr>']
    for line in pl["log"]:
        parts = line.split()
        if not parts[0].startswith("+") or int(parts[0][1:]) > len(seed_hex):
            continue
        n = int(parts[0][1:])
        why = {"highlight": tr("highlight", "brillo"), "saturated": tr("saturated dark", "oscuro saturado")}.get(parts[1], tr("distance × mass", "distancia × masa"))
        de = [p for p in parts if p.startswith("d=")][0][2:]
        mass = [p for p in parts if p.startswith("mass=")][0][5:].rstrip("%")
        kinds.append(f'<tr><td>{n}</td><td><span class="dot" style="background:{seed_hex[n - 1]}"></span>{seed_hex[n - 1]}</td><td>{why}</td><td>{num(float(de), 1)}</td><td>{pct(float(mass), 3)}</td></tr>')
    d["t4_seeds"] = "".join(kinds)

    # Counterexperiments: the same run without each protection.
    off_hl = lambda fn: (lambda lab, solid, **k: np.zeros(solid.shape, bool))  # noqa: E731
    with patched(lab_mod, "highlight_mask", off_hl):
        no_hl = pipe_mod.run(rgb, "stacked", "principito")
    old = lab_mod.SAT_DARK_SLOTS
    lab_mod.SAT_DARK_SLOTS = 0
    try:
        no_sat = pipe_mod.run(rgb, "stacked", "principito")
    finally:
        lab_mod.SAT_DARK_SLOTS = old
    d["full_n"], d["nosat_n"] = num(len(tn.result.colors)), num(len(no_sat.colors))
    cx, cy = spot_of["#740C11"]
    shoe = (cx - 45, cy - 30, cx + 45, cy + 30)
    cx, cy = spot_of["#2348AE"]
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
    dv_rgb = load(SOURCES["diver"])
    dv = ctx.run("diver").result
    with patched(lab_mod, "highlight_mask", off_hl):
        dv_off = pipe_mod.run(dv_rgb, "stacked", "diver")
    d["nohl_lost_d"] = ", ".join(lost(dv.colors, dv_off.colors))
    d["dv_on_n"], d["dv_off_n"] = num(len(dv.colors)), num(len(dv_off.colors))
    d["s4_dv_on"] = swatches([(to_hex(c), "") for c in dv.colors])
    d["s4_dv_off"] = swatches([(to_hex(c), "") for c in dv_off.colors])
    from ch_b import densest

    target = srgb_to_lab(np.array((132, 241, 237), dtype=np.float32))
    near = delta_e(srgb_to_lab(np.asarray(svg_crop(ctx.svg("diver", "stacked")).convert("RGB"))), target) < 3.0
    box = densest(near, 90)
    d["f4_hl_src"] = save(zoom(crop(dv_rgb, box), 4), "4-hl-src.png")
    d["f4_hl_on"] = save(svg_crop(dv.svg, box, 4), "4-hl-on.png")
    d["f4_hl_off"] = save(svg_crop(dv_off.svg, box, 4), "4-hl-off.png")
    return d
