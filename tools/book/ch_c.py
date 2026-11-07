"""Figures for chapters 8 to 10: geometry, the results on the battery, and what is still imperfect."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from ch_b import densest
from draw import OUT, annotate, bezier_path, classes, crop, faded, groups, num, only_group, only_traps, outlines_only, path_of, pct, save, shrink, svg_crop, tr, without_traps, zoom
from harness import ROOT, SOURCES, load, pipe_mod, svg_mod
from measures import shared_segments
from unpixel.render import render_svg
from unpixel.segment import _smooth_partition
from unpixel.vectorize import OVERLAP, build_svg

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


def independent_layers(result, width, height, mode):
    """The general technique of tracing each color alone with potrace, on the very class map unpixel produced.

    A demonstration for the geometry chapter: same regions, same colors, only the tracing differs.
    """
    labels = np.where(result.labels >= len(result.colors), -1, result.labels).astype(np.int16)
    smooth = _smooth_partition(labels, sorted(int(c) for c in np.unique(labels)), 2.0)
    return build_svg(smooth, result.colors, width, height, mode, 30, "layers")[0]


def chapter8(ctx):
    d = {}
    rgb = load(SOURCES["axolotl"])
    t = ctx.new("axolotl")
    L = t.trace_locals[-1]
    pmap = t.planar[-1]["result"]
    scale = L["scale"]
    xy = L["xy"]
    arcs = pmap.arcs
    colors = t.result.colors
    h, w = rgb.shape[:2]
    # The window of the image where most walls meet.
    junction_map = np.zeros(rgb.shape[:2], bool)
    for arc in arcs:
        if arc.start >= 0:
            for v in (arc.start, arc.end):
                vx, vy = (pmap.vertex_xy[v] / scale).astype(int)
                if 0 < vx < w - 1 and 0 < vy < h - 1:
                    junction_map[vy, vx] = True
    box = densest(junction_map, 40)
    z = 12
    fine = (np.array(box) * scale).astype(int)
    base = zoom(classes(t.result.labels[fine[1] : fine[3], fine[0] : fine[2]], colors), z // scale)
    d["f8_cl"] = save(base, "8-classes.png")
    d["f8_src"] = save(zoom(crop(rgb, box), z), "8-src.png")

    def in_box(p):
        return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]

    marks, used, junctions = [], 0, set()
    for arc in arcs:
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
    jdots = dots([pmap.vertex_xy[v] / scale for v in junctions], box, z, "#111", 6)
    d["f8_arcs"] = save(annotate(faded(base, 0.35), "".join(marks) + jdots), "8-arcs.png")
    d["arcs_here"], d["junctions_here"] = num(used), num(len(junctions))
    d["arcs_total"], d["junctions_total"] = num(len(arcs)), num(len(t.result.info["junctions"]))

    # The general technique on the same class map: each color traced alone.
    ind_cut = independent_layers(t.result, w, h, "cutout")
    ind_stk = independent_layers(t.result, w, h, "stacked")
    nw_cut, nw_stk = ctx.svg("axolotl", "cutout"), ctx.svg("axolotl", "stacked")
    d["f8_lines_ind_cut"] = save(svg_crop(outlines_only(ind_cut, 0.18), box, z), "8-lines-ind-cut.png")
    d["f8_lines_ind"] = save(svg_crop(outlines_only(ind_stk, 0.18), box, z), "8-lines-ind.png")
    d["f8_lines_out"] = save(svg_crop(outlines_only(nw_cut, 0.18), box, z), "8-lines-out.png")

    # One wall, from cracks to curve.
    soft_ids, smoothed, owner, fitted = L["soft_ids"], L["smoothed"], L["piece_owner"], L["fitted"]
    boxw = (632, 150, 672, 190)
    zw = 12

    def inside_w(i):
        return sum(1 for p in pmap.crack_xy[arcs[i].cracks] / scale if boxw[0] <= p[0] <= boxw[2] and boxw[1] <= p[1] <= boxw[3])

    k = max(range(len(soft_ids)), key=lambda c: inside_w(soft_ids[c]))
    arc = arcs[soft_ids[k]]
    raw, sub = pmap.crack_xy[arc.cracks] / scale, xy[arc.cracks]
    pids = [p for p, o in enumerate(owner) if o == k]
    smooth_pts = np.vstack([smoothed[p] for p in pids])
    faint = faded(zoom(crop(rgb, boxw), zw), 0.45)
    d["f8_w1"] = save(annotate(faint, f'<path d="{path_of(raw, zw, boxw)}" fill="none" stroke="#111" stroke-width="2"/>'), "8-w1.png")
    d["f8_w2"] = save(annotate(faint, f'<path d="{path_of(sub, zw, boxw)}" fill="none" stroke="#d6007a" stroke-width="2"/>'), "8-w2.png")
    d["f8_w3"] = save(annotate(faint, f'<path d="{path_of(sub, zw, boxw)}" fill="none" stroke="#d6007a" stroke-opacity=".35" stroke-width="2"/><path d="{path_of(smooth_pts, zw, boxw)}" fill="none" stroke="#2a78d6" stroke-width="2.5"/>'), "8-w3.png")
    segs = np.vstack([fitted.points[fitted.starts[p] : fitted.starts[p + 1]] for p in pids])
    curve = "".join(f'<path d="{bezier_path(s, zw, boxw)}" fill="none" stroke="#111" stroke-width="2.5"/>' for s in segs)
    handles = "".join(
        f'<line x1="{(s[0][0] - boxw[0]) * zw:.1f}" y1="{(s[0][1] - boxw[1]) * zw:.1f}" x2="{(s[1][0] - boxw[0]) * zw:.1f}" y2="{(s[1][1] - boxw[1]) * zw:.1f}" stroke="#eb6834"/>'
        f'<line x1="{(s[3][0] - boxw[0]) * zw:.1f}" y1="{(s[3][1] - boxw[1]) * zw:.1f}" x2="{(s[2][0] - boxw[0]) * zw:.1f}" y2="{(s[2][1] - boxw[1]) * zw:.1f}" stroke="#eb6834"/>'
        for s in segs)
    d["f8_w4"] = save(annotate(faint, handles + curve + dots([s[0] for s in segs] + [segs[-1][3]], boxw, zw, "#eb6834", 5)), "8-w4.png")
    d["wall_cracks"], d["wall_segments"] = num(len(arc.cracks)), num(len(segs))

    # Corners: all candidates against those that survived.
    star = (462, 262, 512, 316)
    ends = (452, 72, 502, 112)
    zs = 10
    chains, raw_corners, kept = L["soft_chains"], t.find_corners[-1]["result"], L["corners"]
    cand = [chains[k_][c] for k_ in raw_corners for c in raw_corners[k_]]
    good = [chains[k_][c] for k_ in kept for c in kept[k_]]

    def inside(pts, b):
        return [p for p in pts if b[0] <= p[0] < b[2] and b[1] <= p[1] < b[3]]

    for key, b in (("star", star), ("ends", ends)):
        d[f"f8_{key}"] = save(annotate(faded(svg_crop(nw_stk, b, zs).convert("RGB"), .45), dots(inside(cand, b), b, zs, "#eda100", 7) + dots(inside(good, b), b, zs, "#d6007a", 5)), f"8-{key}.png")
        d[f"corners_{key}_cand"], d[f"corners_{key}_kept"] = num(len(inside(cand, b))), num(len(inside(good, b)))
    d["corners_found"], d["corners_kept"] = num(t.result.info["corners_found"]), num(t.result.info["corners"])
    tp = ctx.new("principito")
    Lp = tp.trace_locals[-1]
    raw_p, kept_p, chains_p = tp.find_corners[-1]["result"], Lp["corners"], Lp["soft_chains"]
    cand_p = [chains_p[k_][c] for k_ in raw_p for c in raw_p[k_]]
    good_p = [chains_p[k_][c] for k_ in kept_p for c in kept_p[k_]]
    hair = (250, 90, 400, 210)
    zh = 5
    d["f8_hair"] = save(annotate(faded(svg_crop(ctx.svg("principito", "stacked"), hair, zh).convert("RGB"), .45), dots(inside(cand_p, hair), hair, zh, "#eda100", 6) + dots(inside(good_p, hair), hair, zh, "#d6007a", 4)), "8-hair.png")
    d["f8_hair_src"] = save(zoom(crop(load(SOURCES["principito"]), hair), zh), "8-hair-src.png")
    d["corners_hair_cand"], d["corners_hair_kept"] = num(len(inside(cand_p, hair))), num(len(inside(good_p, hair)))
    d["corners_found_p"], d["corners_kept_p"] = num(tp.result.info["corners_found"]), num(tp.result.info["corners"])

    # Nodes in the same window for the two ways of tracing.
    win = (604, 92, 684, 172)
    zn = 6
    n_i, n_o = path_nodes(ind_stk, win), path_nodes(nw_stk, win)
    d["f8_nodes_i"] = save(annotate(faded(svg_crop(without_traps(ind_stk), win, zn).convert("RGB"), .55), dots(n_i, win, zn, "#111", 2.6)), "8-nodes-i.png")
    d["f8_nodes_o"] = save(annotate(faded(svg_crop(without_traps(nw_stk), win, zn).convert("RGB"), .55), dots(n_o, win, zn, "#111", 2.6)), "8-nodes-o.png")
    d["nodes_i"], d["nodes_o"] = num(len(n_i)), num(len(n_o))

    # At real size, then magnified with no smoothing: this is where a renderer's antialiasing shows.
    for key, svg in (("ic", ind_cut), ("is", ind_stk), ("oc", nw_cut), ("os", nw_stk)):
        d[f"f8_real_{key}"] = save(zoom(np.asarray(svg_crop(svg, box, 1, "#00d000").convert("RGB")), 8), f"8-real-{key}.png")

    wide = (560, 60, 800, 240)
    d["f8_traps"] = save(svg_crop(only_traps(nw_stk), wide, 2), "8-traps.png")
    d["f8_fills"] = save(svg_crop(without_traps(nw_stk), wide, 2), "8-fills.png")
    d["trap_paths"] = num(len(re.findall(r'class="trap"', nw_stk)))
    widths = sorted({float(v) for v in re.findall(r'class="trap"[^>]*stroke-width="([\d.]+)"', nw_stk)})
    d["trap_widths"] = ", ".join(num(v, 1) for v in widths)
    d["under"] = num(pipe_mod.UNDER)
    d["trap_tol"] = num(svg_mod.TRAP_TOLERANCE, 2)

    # A lower layer grown under the ones above it, as the general technique needs.
    area = []
    for name, color in groups(ind_stk):
        a = np.asarray(svg_crop(only_group(ind_stk, name), wide, 1, None))[..., 3] > 127
        b = np.asarray(svg_crop(only_group(ind_cut, name), wide, 1, None))[..., 3] > 127
        area.append((int(a.sum() - b.sum()), name, color))
    _, name, color = max(area)
    d["f8_hid_stk"] = save(svg_crop(only_group(ind_stk, name), wide, 2), "8-hid-stk.png")
    d["f8_hid_cut"] = save(svg_crop(only_group(ind_cut, name), wide, 2), "8-hid-cut.png")
    d["hid_color"] = color
    d["overlap_src"] = num(OVERLAP / t.result.scale)

    on_bg = sum(L["arc_chain"][i][1] - L["arc_chain"][i][0] for i, arc_ in enumerate(arcs) if arc_.left == 0 or arc_.right == 0)
    written = ctx.runs["axolotl/cutout"]["measure"]["shared"]
    d["once_axolotl"], d["on_bg_axolotl"] = num(written["once"]), num(int(on_bg))
    rows = []
    for name in SOURCES:
        res = ctx.new(name).result
        rgb_n = load(SOURCES[name])
        a = shared_segments(independent_layers(res, rgb_n.shape[1], rgb_n.shape[0], "cutout"))
        b = ctx.runs[f"{name}/cutout"]["measure"]["shared"]
        rows.append(f"<tr><td><code>{name}</code></td><td>{num(a['segments'])}</td><td>{pct(100 * a['twice_share'])}</td><td>{num(b['segments'])}</td><td>{pct(100 * b['twice_share'])}</td><td>{num(b['more'])}</td></tr>")
    d["t8_shared"] = "".join(rows)
    rows = []
    for name in SOURCES:
        cell = []
        for layers in ("stacked", "cutout"):
            hair_px = ctx.runs[f"{name}/{layers}"]["measure"]["hairlines"]
            cell.append(f"<td>{num(hair_px['1.0']['pixels'])}</td>")
        rows.append(f"<tr><td><code>{name}</code></td>{''.join(cell)}</tr>")
    d["t8_hair"] = "".join(rows)
    return d


STAGE_GROUPS = [
    (tr("Prepare", "Preparar"), "var(--s1)", ["classify", "denoise", "antialiasing", "background"]),
    (tr("Color", "Color"), "var(--s2)", ["palette"]),
    (tr("Assign", "Asignar"), "var(--s3)", ["assign", "fringes", "refine"]),
    (tr("Clean", "Limpiar"), "var(--s4)", ["specks"]),
    (tr("Contours", "Contornos"), "var(--s5)", ["regions", "planar_map", "curves", "svg"]),
]


def timing_chart(ctx):
    names = list(SOURCES)
    w, row, l, gap = 640, 22, 76, 6
    top = max(ctx.runs[f"{n}/stacked"]["seconds"] for n in names)
    width = w - l - 70
    h = (row + gap) * len(names) + 12
    parts = []
    y = 6
    for n in names:
        st = ctx.runs[f"{n}/stacked"]["stages"]
        parts.append(f'<text x="{l - 6}" y="{y + row - 8}" text-anchor="end" class="ct">{n}</text>')
        x = float(l)
        total = 0.0
        for label, color, keys in STAGE_GROUPS:
            v = sum(st.get(k, 0.0) for k in keys)
            total += v
            bw = width * v / top
            if bw >= 0.5:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{max(0.5, bw - 1.2):.1f}" height="{row - 4}" rx="1.5" fill="{color}"><title>{n}, {label}: {num(v, 2)} s</title></rect>')
            x += bw
        parts.append(f'<text x="{x + 3:.1f}" y="{y + row - 8}" class="ct">{num(total, 1)} s</text>')
        y += row + gap
    legend = "".join(f'<span class="lg"><i style="background:{c}"></i>{name}</span>' for name, c, _ in STAGE_GROUPS)
    label = tr("Seconds per stage on each image", "Segundos por etapa en cada imagen")
    return f'<div class="legend">{legend}</div><svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">{"".join(parts)}</svg>'


def chapter9(ctx):
    d = {}
    viewer = {}
    svgdir = OUT.parent / "svg"
    svgdir.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        rgb = load(src)
        width = min(rgb.shape[1], 1100)
        s = save(shrink(rgb, width), f"cmp/{name}-src.jpg", 86)
        text = ctx.svg(name, "stacked")
        out = save(svg_crop(text, width=width).convert("RGB"), f"cmp/{name}-unpixel.jpg", 90)
        (svgdir / f"{name}.svg").write_text(text, encoding="utf-8")
        viewer[name] = {"src": s, "out": out, "svg": f"svg/{name}.svg"}
    d["viewer_json"] = json.dumps(viewer)
    d["viewer_first"] = viewer["principito"]["src"]
    rows = []
    for name in SOURCES:
        m = ctx.runs[f"{name}/stacked"]["measure"]
        rows.append(
            f"<tr><td><code>{name}</code></td><td>{num(m['colors'])}</td><td>{num(m['paths'])}</td><td>{num(m['nodes'])}</td><td>{num(m['nodes_per_100px'], 1)}</td>"
            f"<td>{num(m['sharp30_per_1000px'], 1)}</td><td>{num(m['svg_kb'])}</td><td>{num(m['mean_de'], 2)}</td><td>{num(m['p95_de'], 1)}</td></tr>")
    d["t9_all"] = "".join(rows)
    d["c9_time"] = timing_chart(ctx)
    d["t9_time"] = "".join(f"<tr><td><code>{n}</code></td><td>{num(ctx.runs[f'{n}/stacked']['seconds'], 1)}</td><td>{num(ctx.runs[f'{n}/stacked']['peak_rss_mb'])}</td></tr>" for n in SOURCES)
    stages: dict = {}
    for name in SOURCES:
        for k, v in ctx.runs[f"{name}/stacked"]["stages"].items():
            stages.setdefault(k, []).append(v)
    d["t9_stages"] = "".join(f"<tr><td><code>{k}</code></td><td>{num(float(np.mean(v)), 2)}</td></tr>" for k, v in stages.items())
    big = ctx.runs["leaves24/stacked"]
    d["big_s"], d["big_mb"] = num(big["seconds"], 1), num(big["peak_rss_mb"])
    return d


def pair_box(ctx, name, box, key, z):
    rgb = load(SOURCES[name])
    return {
        f"f10_{key}_src": save(zoom(crop(rgb, box), z), f"10-{key}-src.png"),
        f"f10_{key}_out": save(svg_crop(ctx.svg(name, "stacked"), box, z), f"10-{key}-out.png"),
    }


def run_cli(src, out, *args):
    """The real command line, in its own process, as a user would run it."""
    env = {"PYTHONPATH": str(ROOT / "src"), "PATH": os.environ["PATH"]}
    return subprocess.run([sys.executable, "-m", "unpixel", str(src), "-o", str(out), "--force", "--no-report", "--json", "--engine", "new", *args],
                          capture_output=True, text=True, env=env, timeout=900)


def chapter10(ctx):
    d = {}
    rows = []
    over16, cut_saving = [], []
    for name in SOURCES:
        m = ctx.runs[f"{name}/stacked"]["measure"]
        c = ctx.runs[f"{name}/cutout"]["measure"]
        rows.append(f"<tr><td><code>{name}</code></td><td>{num(m['sharp30_per_1000px'], 1)}</td><td>{num(m['colors'])}</td><td>{num(m['svg_kb'])}</td><td>{num(c['svg_kb'])}</td></tr>")
        if m["colors"] > 16:
            over16.append(f"<code>{name}</code> {num(m['colors'])}")
        cut_saving.append(100 * (m["svg_kb"] - c["svg_kb"]) / m["svg_kb"])
    d["t10_costs"] = "".join(rows)
    d["over16"] = ", ".join(over16)
    d["trap_share_lo"], d["trap_share_hi"] = pct(min(cut_saving), 0), pct(max(cut_saving), 0)
    for spec in ctx.defect_boxes:
        d.update(pair_box(ctx, *spec))
    for name in ("leaves", "float"):
        d[f"f10_ground_{name}"] = save(svg_crop(ctx.svg(name, "stacked"), width=620, background="#39506b").convert("RGB"), f"10-ground-{name}.jpg")
    # --also-transparent, through the real CLI, with the color its own warning suggests.
    src = SOURCES["float"]
    probe = ctx.work / "alsot-probe.svg"
    data = json.loads(run_cli(src, probe).stdout)
    color = re.search(r"--also-transparent '(#[0-9A-Fa-f]{6})'", " ".join(data.get("warnings", []))).group(1)
    d["also_color"] = color
    out = ctx.work / "alsot.svg"
    run_cli(src, out, "--also-transparent", color)
    text = out.read_text()
    d["f10_also"] = save(svg_crop(text, ctx.also_box, 3, background="#39506b"), "10-also.png")
    d["f10_also_src"] = save(zoom(crop(load(src), ctx.also_box), 3), "10-also-src.png")
    # Pinholes: the CLI's own check against two independent renderers, at the points it reports.
    pin_rows = []
    bj = Path(__file__).parent / "data/browser.json"
    browser = json.loads(bj.read_text()) if bj.exists() else {}
    pins = browser.get("pins", {})
    for name in ("float", "leaves"):
        probe = ctx.work / f"pin-{name}.svg"
        data = json.loads(run_cli(SOURCES[name], probe).stdout)
        text = probe.read_text()
        rgb = load(SOURCES[name])
        h, w = rgb.shape[:2]
        inner_rgba = render_svg(text, w, h)
        other = np.asarray(svg_crop(text, background=None))[..., 3]
        x, y = {"float": (347, 200), "leaves": (816, 454)}[name]
        pin_rows.append(f"<tr><td><code>{name}</code></td><td>{x}, {y}</td><td>{num(data['metrics']['holes_in_artwork'])}</td><td>{num(inner_rgba[y, x, 3])}</td><td>{num(other[y, x])}</td><td>{num(pins[name]) if name in pins else '—'}</td></tr>")
        box = (x - 12, y - 12, x + 13, y + 13)
        patch = inner_rgba[box[1] : box[3], box[0] : box[2]]
        shown = np.where(patch[..., 3:] > 127, patch[..., :3], np.array((255, 0, 170), dtype=np.uint8))
        d[f"f10_pin_{name}_inner"] = save(zoom(shown, 10), f"10-pin-{name}-inner.png")
        d[f"f10_pin_{name}_rsvg"] = save(svg_crop(text, box, 10, MAGENTA), f"10-pin-{name}-rsvg.png")
        d[f"f10_pin_{name}_src"] = save(zoom(crop(rgb, box), 10), f"10-pin-{name}-src.png")
    d["t10_pin"] = "".join(pin_rows)
    rows = {r["file"]: r["scales"] for r in browser.get("rows", [])}
    out_rows = []
    for name in SOURCES:
        cells = []
        for layers in ("stacked", "cutout"):
            s = rows.get(f"{name}-{layers}")
            cells.append("<td>" + (" / ".join(num(s[k]["under_200"]) for k in ("1", "3", "0.25")) if s else "—") + "</td>")
        out_rows.append(f"<tr><td><code>{name}</code></td>{''.join(cells)}</tr>")
    d["t10_browser"] = "".join(out_rows)
    d["browser_version"] = browser.get("browser", "—")
    d["browser_commit"] = browser.get("commit", "—")
    return d
