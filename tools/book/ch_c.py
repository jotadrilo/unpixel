"""Figures for chapters 8 to 10: geometry, the final comparison, and what is still worse."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from ch_a import lab_rgb, swatches
from ch_b import densest
from draw import OUT, annotate, as_image, bezier_path, classes, crop, faded, groups, only_group, only_traps, outlines_only, path_of, save, shrink, svg_crop, without_traps, zoom
from harness import ROOT, SOURCES, load, pipe_mod, svg_mod, vec_mod
from unpixel.color import to_hex

MAGENTA = "#ff00aa"
ARC_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#e34948", "#008300"]


def path_nodes(svg_text: str, box) -> list[tuple[float, float]]:
    """The on-curve points of every fill path inside a window."""
    x0, y0, x1, y1 = box
    out = []
    for attrs in re.findall(r"<path ([^>]*)/?>", svg_text):
        if 'class="trap"' in attrs:
            continue
        tokens = re.findall(r"[MLCZ]|-?\d+(?:\.\d+)?", re.search(r'\bd="([^"]+)"', attrs).group(1))
        i = 0
        while i < len(tokens):
            t = tokens[i]
            i += 1
            if t in ("M", "L"):
                p = (float(tokens[i]), float(tokens[i + 1]))
                i += 2
            elif t == "C":
                p = (float(tokens[i + 4]), float(tokens[i + 5]))
                i += 6
            else:
                continue
            if x0 <= p[0] < x1 and y0 <= p[1] < y1:
                out.append(p)
    return out


def dots(points, box, z, color, r=3.5):
    return "".join(f'<circle cx="{(x - box[0]) * z:.1f}" cy="{(y - box[1]) * z:.1f}" r="{r}" fill="{color}" stroke="#fff" stroke-width="1.2"/>' for x, y in points)


def chapter8(ctx):
    d = {}
    rgb = load(SOURCES["axolotl"])
    t = ctx.new("axolotl")
    L = t.trace_locals[-1]
    pmap = t.planar[-1]["result"]
    scale = L["scale"]
    xy, vertex_xy = L["xy"], L["vertex_xy"]
    arcs = pmap.arcs
    colors = t.result.colors
    # A small window with several colors meeting: where the antenna ball meets its stalk and the helmet's rim.
    # The window of the image where most walls meet.
    junction_map = np.zeros(rgb.shape[:2], bool)
    for arc in arcs:
        if arc.start >= 0:
            for v in (arc.start, arc.end):
                vx, vy = (pmap.vertex_xy[v] / scale).astype(int)
                if 0 < vx < rgb.shape[1] - 1 and 0 < vy < rgb.shape[0] - 1:
                    junction_map[vy, vx] = True
    box = densest(junction_map, 40)
    d["junction_box"] = str(box)
    z = 12
    fine = (np.array(box) * scale).astype(int)
    labels = t.result.labels
    base = zoom(classes(labels[fine[1] : fine[3], fine[0] : fine[2]], colors), z // scale)
    d["f8_cl"] = save(base, "8-classes.png")
    d["f8_src"] = save(zoom(crop(rgb, box), z), "8-src.png")

    def in_box(p):
        return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]

    # Each wall in its own color, junctions as dots: the real arcs of the real map.
    marks, used, junctions = [], 0, set()
    for i, arc in enumerate(arcs):
        pts = pmap.crack_xy[arc.cracks] / scale
        if not any(in_box(p) for p in pts):
            continue
        if arc.start >= 0:
            pts = np.vstack([pmap.vertex_xy[arc.start] / scale, pts, pmap.vertex_xy[arc.end] / scale])
            for v in (arc.start, arc.end):
                if in_box(pmap.vertex_xy[v] / scale):
                    junctions.add(v)
        c = ARC_COLORS[used % len(ARC_COLORS)]
        marks.append(f'<path d="{path_of(pts, z, box)}" fill="none" stroke="#fff" stroke-width="5"/><path d="{path_of(pts, z, box)}" fill="none" stroke="{c}" stroke-width="3"/>')
        used += 1
    faint = faded(base, 0.35)
    jdots = dots([pmap.vertex_xy[v] / scale for v in junctions], box, z, "#111", 6)
    d["f8_arcs"] = save(annotate(faint, "".join(marks) + jdots), "8-arcs.png")
    d["arcs_here"], d["junctions_here"] = used, len(junctions)
    d["arcs_total"] = f"{len(arcs):,}".replace(",", ".")
    d["junctions_total"] = f"{len(t.result.info['junctions']):,}".replace(",", ".")
    d["regions_total"] = f"{L['total']:,}".replace(",", ".") if isinstance(L.get("total"), int) else "—"

    # The classic engine's outlines in the same window: every layer's own trace.
    cl_cut = ctx.svg("axolotl", "classic", "cutout")
    cl_stk = ctx.svg("axolotl", "classic", "stacked")
    nw_cut = ctx.svg("axolotl", "new", "cutout")
    nw_stk = ctx.svg("axolotl", "new", "stacked")
    d["f8_lines_classic_cut"] = save(svg_crop(outlines_only(cl_cut, 0.18), box, z), "8-lines-classic-cut.png")
    d["f8_lines_classic"] = save(svg_crop(outlines_only(cl_stk, 0.18), box, z), "8-lines-classic.png")
    d["f8_lines_new"] = save(svg_crop(outlines_only(nw_cut, 0.18), box, z), "8-lines-new.png")

    # One wall, from cracks to curve.
    soft_ids, pieces, smoothed, owner = L["soft_ids"], L["pieces"], L["smoothed"], L["piece_owner"]
    fitted = L["fitted"]
    boxw = (632, 150, 672, 190)  # part of the helmet's rim
    zw = 12
    candidates = [k for k, i in enumerate(soft_ids) if sum(1 for p in pmap.crack_xy[arcs[i].cracks] / scale if boxw[0] <= p[0] <= boxw[2] and boxw[1] <= p[1] <= boxw[3]) > 40]
    if not candidates:
        candidates = [int(np.argmax([len(arcs[i].cracks) for i in soft_ids]))]
    k = max(candidates, key=lambda c: sum(1 for p in pmap.crack_xy[arcs[soft_ids[c]].cracks] / scale if boxw[0] <= p[0] <= boxw[2] and boxw[1] <= p[1] <= boxw[3]))
    arc = arcs[soft_ids[k]]
    raw = pmap.crack_xy[arc.cracks] / scale
    sub = xy[arc.cracks]
    pids = [p for p, o in enumerate(owner) if o == k]
    smooth_pts = np.vstack([smoothed[p] for p in pids])
    bg_rgb = zoom(crop(rgb, boxw), zw)
    faint = faded(bg_rgb, 0.45)
    d["f8_w1"] = save(annotate(faint, f'<path d="{path_of(raw, zw, boxw)}" fill="none" stroke="#111" stroke-width="2"/>'), "8-w1.png")
    d["f8_w2"] = save(annotate(faint, f'<path d="{path_of(sub, zw, boxw)}" fill="none" stroke="#d6007a" stroke-width="2"/>'), "8-w2.png")
    d["f8_w3"] = save(annotate(faint, f'<path d="{path_of(sub, zw, boxw)}" fill="none" stroke="#d6007a" stroke-opacity=".35" stroke-width="2"/><path d="{path_of(smooth_pts, zw, boxw)}" fill="none" stroke="#2a78d6" stroke-width="2.5"/>'), "8-w3.png")
    segs = np.vstack([fitted.points[fitted.starts[p] : fitted.starts[p + 1]] for p in pids])
    curve = "".join(f'<path d="{bezier_path(s, zw, boxw)}" fill="none" stroke="#111" stroke-width="2.5"/>' for s in segs)
    handles = "".join(
        f'<line x1="{(s[0][0] - boxw[0]) * zw:.1f}" y1="{(s[0][1] - boxw[1]) * zw:.1f}" x2="{(s[1][0] - boxw[0]) * zw:.1f}" y2="{(s[1][1] - boxw[1]) * zw:.1f}" stroke="#eb6834"/>'
        f'<line x1="{(s[3][0] - boxw[0]) * zw:.1f}" y1="{(s[3][1] - boxw[1]) * zw:.1f}" x2="{(s[2][0] - boxw[0]) * zw:.1f}" y2="{(s[2][1] - boxw[1]) * zw:.1f}" stroke="#eb6834"/>'
        for s in segs)
    nodes = dots([s[0] for s in segs] + [segs[-1][3]], boxw, zw, "#eb6834", 5)
    d["f8_w4"] = save(annotate(faint, handles + curve + nodes), "8-w4.png")
    d["wall_cracks"], d["wall_segments"] = len(arc.cracks), len(segs)

    # Corners: all candidates against those that survived.
    star = (462, 262, 512, 316)
    zs = 10
    chains = L["soft_chains"]
    raw_corners = t.find_corners[-1]["result"]
    kept = L["corners"]
    cand, good = [], []
    for k_, chain in enumerate(chains):
        for c in raw_corners.get(k_, []):
            cand.append(chain[c])
        for c in kept.get(k_, []):
            good.append(chain[c])
    good_in = [p for p in good if star[0] <= p[0] < star[2] and star[1] <= p[1] < star[3]]
    cand_in = [p for p in cand if star[0] <= p[0] < star[2] and star[1] <= p[1] < star[3]]
    d["f8_star"] = save(annotate(faded(svg_crop(ctx.svg("axolotl", "new", "stacked"), star, zs).convert("RGB"), .45), dots(cand_in, star, zs, "#eda100", 7) + dots(good_in, star, zs, "#d6007a", 5)), "8-star.png")
    d["corners_found"] = t.result.info["corners_found"]
    d["corners_kept"] = t.result.info["corners"]
    # A rounded stroke end, from the UFO's little lines: no corner should stay on it.
    ends = (452, 72, 502, 112)
    gd = [p for p in good if ends[0] <= p[0] < ends[2] and ends[1] <= p[1] < ends[3]]
    cd = [p for p in cand if ends[0] <= p[0] < ends[2] and ends[1] <= p[1] < ends[3]]
    d["f8_ends"] = save(annotate(faded(svg_crop(ctx.svg("axolotl", "new", "stacked"), ends, zs).convert("RGB"), .45), dots(cd, ends, zs, "#eda100", 7) + dots(gd, ends, zs, "#d6007a", 5)), "8-ends.png")
    d["corners_ends_cand"], d["corners_ends_kept"] = len(cd), len(gd)
    d["corners_star_cand"], d["corners_star_kept"] = len(cand_in), len(good_in)

    # And where corners do survive: the Little Prince's spiky hair.
    tp = ctx.new("principito")
    Lp = tp.trace_locals[-1]
    raw_p, kept_p, chains_p = tp.find_corners[-1]["result"], Lp["corners"], Lp["soft_chains"]
    cand_p = [chains_p[k_][c] for k_ in raw_p for c in raw_p[k_]]
    good_p = [chains_p[k_][c] for k_ in kept_p for c in kept_p[k_]]
    hair = (250, 90, 400, 210)
    zh = 5
    svg_p = ctx.svg("principito", "new", "stacked")
    def inside(pts, b):
        return [p for p in pts if b[0] <= p[0] < b[2] and b[1] <= p[1] < b[3]]
    d["f8_hair"] = save(annotate(faded(svg_crop(svg_p, hair, zh).convert("RGB"), .45), dots(inside(cand_p, hair), hair, zh, "#eda100", 6) + dots(inside(good_p, hair), hair, zh, "#d6007a", 4)), "8-hair.png")
    d["f8_hair_src"] = save(zoom(crop(load(SOURCES["principito"]), hair), zh), "8-hair-src.png")
    d["corners_hair_cand"], d["corners_hair_kept"] = len(inside(cand_p, hair)), len(inside(good_p, hair))
    d["corners_found_p"], d["corners_kept_p"] = tp.result.info["corners_found"], tp.result.info["corners"]

    # Nodes in the same window for the two engines.
    win = (604, 92, 684, 172)
    zn = 6
    n_c, n_n = path_nodes(cl_stk, win), path_nodes(nw_stk, win)
    d["f8_nodes_c"] = save(annotate(faded(svg_crop(without_traps(cl_stk), win, zn).convert("RGB"), .55), dots(n_c, win, zn, "#111", 2.6)), "8-nodes-c.png")
    d["f8_nodes_n"] = save(annotate(faded(svg_crop(without_traps(nw_stk), win, zn).convert("RGB"), .55), dots(n_n, win, zn, "#111", 2.6)), "8-nodes-n.png")
    d["nodes_c"], d["nodes_n"] = len(n_c), len(n_n)

    # Gaps: the four ways of drawing, on a color no artwork has.
    gap = box
    zg = 10
    for key, svg in (("cc", cl_cut), ("cs", cl_stk), ("nc", nw_cut), ("ns", nw_stk)):
        d[f"f8_gap_{key}"] = save(svg_crop(svg, gap, zg, MAGENTA), f"8-gap-{key}.png")
        # At its real size, then magnified with no smoothing: this is where a renderer's antialiasing shows.
        d[f"f8_real_{key}"] = save(zoom(np.asarray(svg_crop(svg, gap, 1, "#00d000").convert("RGB")), 8), f"8-real-{key}.png")
    # A fill's real outline at one to one on the same ground: what antialiasing lets through.
    gap1 = (560, 60, 800, 240)
    for key, svg in (("nc", nw_cut), ("ns", nw_stk)):
        d[f"f8_one_{key}"] = save(svg_crop(svg, gap1, 2, MAGENTA), f"8-one-{key}.png")

    # The strokes alone, then the fills alone.
    wide = (560, 60, 800, 240)
    d["f8_traps"] = save(svg_crop(only_traps(nw_stk), wide, 2), "8-traps.png")
    d["f8_fills"] = save(svg_crop(without_traps(nw_stk), wide, 2), "8-fills.png")
    trap_paths = len(re.findall(r'class="trap"', nw_stk))
    d["trap_paths"] = trap_paths
    widths = sorted({float(v) for v in re.findall(r'class="trap"[^>]*stroke-width="([\d.]+)"', nw_stk)})
    d["trap_widths"] = ", ".join(f"{w:g}".replace(".", ",") for w in widths)
    d["under"] = f"{pipe_mod.UNDER:g}"
    d["trap_tol"] = f"{svg_mod.TRAP_TOLERANCE:g}".replace(".", ",")
    # Layers hidden under layers, as the classic engine writes them, and the new order.
    gs = groups(cl_stk)
    tiles_c, tiles_n = [], []
    # the classic layer that hides most: compare its stacked and cutout areas
    area = []
    for name, color in gs:
        a = np.asarray(svg_crop(only_group(cl_stk, name), wide, 1, None))[..., 3] > 127
        b = np.asarray(svg_crop(only_group(cl_cut, name), wide, 1, None))[..., 3] > 127
        area.append((int(a.sum() - b.sum()), name, color))
    area.sort(reverse=True)
    extra, name, color = area[0]
    d["f8_hid_stk"] = save(svg_crop(only_group(cl_stk, name), wide, 2), "8-hid-stk.png")
    d["f8_hid_cut"] = save(svg_crop(only_group(cl_cut, name), wide, 2), "8-hid-cut.png")
    d["hid_color"] = color
    d["overlap_px"] = vec_mod.OVERLAP
    d["overlap_src"] = f"{vec_mod.OVERLAP / ctx.classic('axolotl').seg.scale:g}"
    del tiles_c, tiles_n
    # The segments drawn only once should be exactly those against the unpainted background.
    on_bg = sum(L["arc_chain"][i][1] - L["arc_chain"][i][0] for i, arc_ in enumerate(arcs) if arc_.left == 0 or arc_.right == 0)
    written = ctx.runs["axolotl/new/cutout"]["measure"]["shared"]
    d["once_axolotl"], d["on_bg_axolotl"] = written["once"], on_bg
    # Share of segments shared by two sides, from the written SVGs.
    rows = []
    for name in SOURCES:
        a = ctx.runs[f"{name}/classic/cutout"]["measure"]["shared"]
        b = ctx.runs[f"{name}/new/cutout"]["measure"]["shared"]
        rows.append(f"<tr><td><code>{name}</code></td><td>{a['segments']}</td><td>{100 * a['twice_share']:.1f} %</td><td>{b['segments']}</td><td>{100 * b['twice_share']:.1f} %</td><td>{b['more']}</td></tr>")
    d["t8_shared"] = "".join(rows)
    # See-through pixels by renderer scale.
    rows = []
    for name in SOURCES:
        cell = []
        for key in ("classic/stacked", "classic/cutout", "new/stacked", "new/cutout"):
            h = ctx.runs[f"{name}/{key}"]["measure"]["hairlines"]
            cell.append(f"<td>{h['1.0']['pixels']:,}</td>".replace(",", "."))
        rows.append(f"<tr><td><code>{name}</code></td>{''.join(cell)}</tr>")
    d["t8_hair"] = "".join(rows)
    return d


STAGE_GROUPS = [
    ("Preparar", "var(--s1)", {"new": ["classify", "denoise", "antialiasing", "background"], "classic": ["blur", "other"]}),
    ("Color", "var(--s2)", {"new": ["palette"], "classic": ["groups", "unexplained", "split"]}),
    ("Asignar", "var(--s3)", {"new": ["assign", "fringes", "refine"], "classic": ["nearest"]}),
    ("Limpiar", "var(--s4)", {"new": ["specks"], "classic": ["fringes", "specks", "smooth"]}),
    ("Contornos", "var(--s5)", {"new": ["regions", "planar_map", "curves", "svg"], "classic": ["trace"]}),
]


def timing_chart(ctx):
    names = list(SOURCES)
    w, row, l, gap = 640, 15, 76, 8
    top = max(ctx.runs[f"{n}/classic/stacked"]["seconds"] for n in names)
    width = w - l - 70
    h = (2 * row + gap + 3) * len(names) + 30
    parts = []
    y = 26
    for n in names:
        parts.append(f'<text x="{l - 6}" y="{y + row + 1}" text-anchor="end" class="ct">{n}</text>')
        for engine, tag in (("classic", "cl"), ("new", "nu")):
            st = ctx.runs[f"{n}/{engine}/stacked"]["stages"]
            x = float(l)
            total = 0.0
            for label, color, keys in STAGE_GROUPS:
                v = sum(st.get(k, 0.0) for k in keys[engine])
                total += v
                bw = width * v / top
                if bw >= 0.5:
                    parts.append(f'<rect x="{x:.1f}" y="{y}" width="{max(0.5, bw - 1.2):.1f}" height="{row - 2}" rx="1.5" fill="{color}"><title>{n}, {engine}, {label}: {es(v, 2)} s</title></rect>')
                x += bw
            parts.append(f'<text x="{x + 3:.1f}" y="{y + row - 4}" class="ct">{tag} {es(total)} s</text>')
            y += row
        y += gap + 3
    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{name}</span>' for name, c, _ in STAGE_GROUPS)
    return f'<div class="legend">{legend}</div><svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Segundos por etapa en cada imagen, motor clásico y nuevo">{"".join(parts)}</svg>'


def es(v, digits=1):
    return f"{v:.{digits}f}".replace(".", ",")


def chapter9(ctx):
    d = {}
    viewer = {}
    svgdir = OUT.parent / "svg"
    svgdir.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        rgb = load(src)
        width = min(rgb.shape[1], 1100)
        s = save(shrink(rgb, width), f"cmp/{name}-src.jpg", 86)
        cl = ctx.svg(name, "classic", "stacked")
        nw = ctx.svg(name, "new", "stacked")
        c = save(svg_crop(cl, width=width).convert("RGB"), f"cmp/{name}-classic.jpg", 90)
        n = save(svg_crop(nw, width=width).convert("RGB"), f"cmp/{name}-new.jpg", 90)
        (svgdir / f"{name}-classic.svg").write_text(cl, encoding="utf-8")
        (svgdir / f"{name}-new.svg").write_text(nw, encoding="utf-8")
        viewer[name] = {"src": s, "classic": c, "new": n, "w": width, "h": round(rgb.shape[0] * width / rgb.shape[1]),
                        "svg_c": f"svg/{name}-classic.svg", "svg_n": f"svg/{name}-new.svg"}
    d["viewer_json"] = json.dumps(viewer)
    d["viewer_first"] = viewer["axolotl"]["src"]
    # The whole table.
    rows = []
    for name in SOURCES:
        a, b = ctx.runs[f"{name}/classic/stacked"], ctx.runs[f"{name}/new/stacked"]
        ma, mb = a["measure"], b["measure"]
        rows.append(
            f"<tr><td><code>{name}</code></td><td>{ma['colors']}<br>{mb['colors']}</td><td>{ma['paths']}<br>{mb['paths']}</td>"
            f"<td>{ma['nodes']}<br>{mb['nodes']}</td><td>{es(ma['nodes_per_100px'])}<br>{es(mb['nodes_per_100px'])}</td>"
            f"<td>{es(ma['sharp30_per_1000px'])}<br>{es(mb['sharp30_per_1000px'])}</td><td>{ma['svg_kb']:.0f}<br>{mb['svg_kb']:.0f}</td>"
            f"<td>{es(ma['mean_de'],2)}<br>{es(mb['mean_de'],2)}</td><td>{es(ma['p95_de'])}<br>{es(mb['p95_de'])}</td></tr>")
    d["t9_all"] = "".join(rows)
    d["c9_time"] = timing_chart(ctx)
    rows = []
    for name in SOURCES:
        a, b = ctx.runs[f"{name}/classic/stacked"], ctx.runs[f"{name}/new/stacked"]
        rows.append(f"<tr><td><code>{name}</code></td><td>{es(a['seconds'])}</td><td>{es(b['seconds'])}</td><td>{a['peak_rss_mb']:.0f}</td><td>{b['peak_rss_mb']:.0f}</td></tr>")
    big_c, big_n = ctx.runs["leaves24/classic/stacked"], ctx.runs["leaves24/new/stacked"]
    d["t9_time"] = "".join(rows)
    d["big_c_s"], d["big_n_s"] = es(big_c["seconds"]), es(big_n["seconds"])
    d["big_c_mb"], d["big_n_mb"] = f"{big_c['peak_rss_mb']:.0f}", f"{big_n['peak_rss_mb']:.0f}"
    stages = {}
    for name in SOURCES:
        for k, v in ctx.runs[f"{name}/new/stacked"]["stages"].items():
            stages.setdefault(k, []).append(v)
    d["t9_stages"] = "".join(f"<tr><td><code>{k}</code></td><td>{es(float(np.mean(v)), 2)}</td></tr>" for k, v in stages.items())
    cstages = {}
    for name in SOURCES:
        for k, v in ctx.runs[f"{name}/classic/stacked"]["stages"].items():
            cstages.setdefault(k, []).append(v)
    d["t9_cstages"] = "".join(f"<tr><td><code>{k}</code></td><td>{es(float(np.mean(v)), 2)}</td></tr>" for k, v in cstages.items())
    return d


def trio_box(ctx, name, box, key, z):
    rgb = load(SOURCES[name])
    return {
        f"f10_{key}_src": save(zoom(crop(rgb, box), z), f"10-{key}-src.png"),
        f"f10_{key}_c": save(svg_crop(ctx.svg(name, "classic", "stacked"), box, z), f"10-{key}-c.png"),
        f"f10_{key}_n": save(svg_crop(ctx.svg(name, "new", "stacked"), box, z), f"10-{key}-n.png"),
    }


def run_cli(ctx, src, out, *args):
    """The real command line, in its own process, as a user would run it."""
    env = {"PYTHONPATH": str(ROOT / "src"), "PATH": __import__("os").environ["PATH"]}
    done = subprocess.run([sys.executable, "-m", "unpixel", str(src), "-o", str(out), "--force", "--no-report", "--json", *args],
                          capture_output=True, text=True, env=env, timeout=900)
    return done


def chapter10(ctx):
    d = {}
    worse_colors, worse_sharp, worse_kb, better_nodes, better_de = [], [], [], [], []
    for name in SOURCES:
        a = ctx.runs[f"{name}/classic/stacked"]["measure"]
        b = ctx.runs[f"{name}/new/stacked"]["measure"]
        if b["colors"] > a["colors"]:
            worse_colors.append(f"<code>{name}</code> {a['colors']} → {b['colors']}")
        if b["sharp30_per_1000px"] > a["sharp30_per_1000px"]:
            worse_sharp.append(f"<code>{name}</code> {es(a['sharp30_per_1000px'])} → {es(b['sharp30_per_1000px'])}")
        if b["svg_kb"] > a["svg_kb"]:
            worse_kb.append(f"<code>{name}</code> {a['svg_kb']:.0f} → {b['svg_kb']:.0f} KB")
        if b["nodes_per_100px"] < a["nodes_per_100px"]:
            better_nodes.append(name)
        if b["mean_de"] < a["mean_de"]:
            better_de.append(name)
    d["worse_colors"] = "; ".join(worse_colors) or "ninguna"
    d["worse_colors_n"] = len(worse_colors)
    d["worse_sharp"] = "; ".join(worse_sharp) or "ninguna"
    d["worse_sharp_n"] = len(worse_sharp)
    d["worse_kb"] = "; ".join(worse_kb) or "ninguna"
    d["worse_kb_n"] = len(worse_kb)
    d["better_nodes_n"] = len(better_nodes)
    d["better_de_n"] = len(better_de)
    # Sharp turns: all fills, marked, on a hard case.
    for spec in ctx.defect_boxes:
        d.update(trio_box(ctx, *spec))
    # Colored ground: what is left of a sticker's border.
    for name in ("leaves", "float"):
        for engine in ("classic", "new"):
            d[f"f10_ground_{name}_{engine}"] = save(svg_crop(ctx.svg(name, engine, "stacked"), width=620, background="#39506b").convert("RGB"), f"10-ground-{name}-{engine}.jpg")
    # --also-transparent, through the real CLI, on the same image and color.
    src = SOURCES["float"]
    wanted = {"classic": None, "new": None}
    for engine in wanted:
        probe = ctx.work / f"alsot-{engine}-probe.svg"
        done = run_cli(ctx, src, probe, "--engine", engine)
        data = json.loads(done.stdout)
        hit = re.search(r"--also-transparent '(#[0-9A-Fa-f]{6})'", " ".join(data.get("warnings", [])))
        wanted[engine] = hit.group(1) if hit else None
    d["also_c_color"], d["also_n_color"] = wanted["classic"], wanted["new"]
    box = (620, 330, 860, 500)
    for engine, tag in (("classic", "c"), ("new", "n")):
        out = ctx.work / f"alsot-{engine}.svg"
        done = run_cli(ctx, src, out, "--engine", engine, "--also-transparent", wanted[engine])
        d[f"also_{tag}_ok"] = done.returncode
        text = out.read_text()
        d[f"f10_also_{tag}"] = save(svg_crop(text, ctx.also_box, 3, background="#39506b"), f"10-also-{tag}.png")
        d[f"also_{tag}_layers"] = len(groups(text))
    del box
    d["f10_also_src"] = save(zoom(crop(load(src), ctx.also_box), 3), "10-also-src.png")
    for engine, tag in (("classic", "c"), ("new", "n")):
        d[f"f10_also_all_{tag}"] = save(svg_crop((ctx.work / f"alsot-{engine}.svg").read_text(), width=620, background="#39506b").convert("RGB"), f"10-also-all-{tag}.jpg")
    # Pinholes: the CLI's own check against two independent renderers, at the points it reports.
    from unpixel.render import render_svg
    pin_rows = []
    pins = []
    for name in ("float", "leaves"):
        probe = ctx.work / f"pin-{name}.svg"
        done = run_cli(ctx, SOURCES[name], probe, "--engine", "new")
        data = json.loads(done.stdout)
        text = probe.read_text()
        rgb = load(SOURCES[name])
        h, w = rgb.shape[:2]
        inner = render_svg(text, w, h)[..., 3]
        other = np.asarray(svg_crop(text, background=None))[..., 3]
        (x, y) = {"float": (347, 200), "leaves": (816, 454)}[name]
        pin_rows.append(f"<tr><td><code>{name}</code></td><td>{x}, {y}</td><td>{data['metrics']['holes_in_artwork']}</td><td>{inner[y, x]}</td><td>{other[y, x]}</td><td>{{{{pin_chromium_{name}}}}}</td></tr>")
        pins.append(name)
        box = (x - 12, y - 12, x + 13, y + 13)
        d[f"f10_pin_{name}_inner"] = save(zoom(np.asarray(as_image(np.dstack([np.where(inner[y - 12 : y + 13, x - 12 : x + 13, None] > 127, render_svg(text, w, h)[y - 12 : y + 13, x - 12 : x + 13, :3], np.array((255, 0, 170), dtype=np.uint8))])))[..., :3], 10), f"10-pin-{name}-inner.png")
        d[f"f10_pin_{name}_rsvg"] = save(svg_crop(text, box, 10, MAGENTA), f"10-pin-{name}-rsvg.png")
        d[f"f10_pin_{name}_src"] = save(zoom(crop(rgb, box), 10), f"10-pin-{name}-src.png")
    d["t10_pin_template"] = "".join(pin_rows)
    # Numbers from Chromium, when the separate browser pass has been run.
    bj = Path(__file__).parent / "data/browser.json"
    d["t10_browser"] = ""
    if bj.exists():
        data = json.loads(bj.read_text())
        rows = {}
        for r in data["rows"]:
            rows[r["file"]] = r["scales"]
        out = []
        for name in SOURCES:
            cells = []
            for variant in ("classic-stacked", "new-stacked", "new-cutout"):
                s = rows.get(f"{name}-{variant}")
                cells.append("<td>" + (" / ".join(f"{s[k]['under_200']:,}".replace(",", ".") for k in ("1", "3", "0.25")) if s else "—") + "</td>")
            out.append(f"<tr><td><code>{name}</code></td>{''.join(cells)}</tr>")
        d["t10_browser"] = "".join(out)
        d["browser_version"] = data.get("browser", "")
        d["browser_commit"] = data.get("commit", "")
        for key, value in data.get("pins", {}).items():
            d[f"pin_chromium_{key}"] = value
    d["t10_pin"] = re.sub(r"\{\{(\w+)\}\}", lambda m: str(d.get(m.group(1), "—")), d.pop("t10_pin_template"))
    return d
