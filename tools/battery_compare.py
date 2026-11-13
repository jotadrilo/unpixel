#!/usr/bin/env python
"""Compare the golden cases between two environments, for the owner to judge on the battery before goldens move.

usage: tools/battery_compare.py run --label NAME --out DIR [--pinned] [--threads N]
           run every golden case with the Python running this script, in a clean environment like
           production's (PATH, HOME, TMPDIR only), plus the two x86_64 kernel pins with --pinned and
           OPENBLAS_NUM_THREADS with --threads; writes DIR/NAME/<case>.svg and DIR/NAME.json
       tools/battery_compare.py report --runs DIR --out DIR
           read every runner's outputs (DIR/<job>/cpu.txt, base/, cand/...), group the baseline into
           the variants the CPUs produced, render each SVG with rsvg-convert, and write the PNGs,
           pixel diffs and manifest.json the owner looks at

Used by .github/workflows/battery-compare.yml. Not part of the tests.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import golden  # noqa: E402

PREVIEW = 800  # longest side of the PNGs kept for the owner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd_run(a):
    out = Path(a.out) / a.label
    out.mkdir(parents=True, exist_ok=True)
    env_extra = dict(golden.PINNED_X86_64) if a.pinned else {}
    if a.threads:
        env_extra["OPENBLAS_NUM_THREADS"] = str(a.threads)

    def one(name):
        source, args = golden.CASES[name]
        svg = out / f"{name}.svg"
        with tempfile.TemporaryDirectory() as home:
            env = {"PATH": os.environ["PATH"], "HOME": home, "TMPDIR": home, **env_extra}
            cmd = [sys.executable, "-m", "unpixel", str(source), "-o", str(svg), "--no-report", "--force", "--color", "never", *args]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, env=env)
        if r.returncode:
            raise RuntimeError(f"{name}: unpixel exited {r.returncode}\n{r.stderr[-2000:]}")
        return name, sha(svg)

    with ThreadPoolExecutor(a.jobs or os.cpu_count() or 1) as pool:
        hashes = dict(pool.map(one, golden.CASES))
    meta = {"label": a.label, "env": env_extra, "environment": golden.environment(), "sha256": hashes}
    (Path(a.out) / f"{a.label}.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(json.dumps(meta["environment"]), a.label, "done")


# ---------- report ----------

NUM = re.compile(r"-?\d+(?:\.\d+)?")
GROUP = re.compile(r'<g id="color-\d+" fill="(#[0-9A-Fa-f]{6})"[^>]*>(.*?)</g>', re.S)
PATH_D = re.compile(r'<path d="([^"]*)"')


def parse_svg(path):
    text = Path(path).read_text(encoding="utf-8")
    groups = [(fill.upper(), PATH_D.findall(body)) for fill, body in GROUP.findall(text)]
    m = re.search(r'width="(\d+)" height="(\d+)"', text)
    return {"groups": groups, "size": (int(m.group(1)), int(m.group(2))), "paths": text.count("<path")}


def points(ds):
    import numpy as np

    nums = [float(x) for d in ds for x in NUM.findall(d)]
    return np.array(nums, dtype=np.float64).reshape(-1, 2) if nums else np.zeros((0, 2))


def geometry(a, b):
    """Max coordinate shift when the paths line up one to one, and the vertex Hausdorff distance always."""
    import numpy as np
    from scipy.spatial import cKDTree

    same_structure = [f for f, _ in a["groups"]] == [f for f, _ in b["groups"]] and all(
        len(pa) == len(pb) and all(NUM.sub("#", x) == NUM.sub("#", y) for x, y in zip(pa, pb))
        for (_, pa), (_, pb) in zip(a["groups"], b["groups"])
    )
    max_shift = None
    if same_structure:
        diffs = [np.abs(points(pa) - points(pb)).max() for (_, pa), (_, pb) in zip(a["groups"], b["groups"]) if pa]
        max_shift = round(float(max(diffs, default=0.0)), 3)
    ga, gb = dict(a["groups"]), dict(b["groups"])
    haus = 0.0
    for fill in set(ga) & set(gb):
        pa, pb = points(ga[fill]), points(gb[fill])
        if len(pa) and len(pb):
            haus = max(haus, cKDTree(pb).query(pa)[0].max(), cKDTree(pa).query(pb)[0].max())
    return same_structure, max_shift, round(float(haus), 3)


def render(svg, png, width):
    subprocess.run(["rsvg-convert", "-w", str(width), "-o", str(png), str(svg)], check=True)


def load_rgba(png):
    import numpy as np
    from PIL import Image

    return np.asarray(Image.open(png).convert("RGBA"), dtype=np.int16)


def save_preview(src_png, dst_png):
    from PIL import Image

    im = Image.open(src_png).convert("RGBA")
    im.thumbnail((PREVIEW, PREVIEW), Image.LANCZOS)
    im.save(dst_png, optimize=True)


def pixel_diff(a_png, b_png, diff_png):
    """Numbers on the full-size renders, and a preview: the image faded to gray, changed pixels in red."""
    import numpy as np
    from PIL import Image

    a, b = load_rgba(a_png), load_rgba(b_png)
    delta = np.abs(a - b)
    per_px = delta.max(axis=2)
    changed = per_px > 0
    stats = {
        "changed_pixels_pct": round(100 * float(changed.mean()), 4),
        "changed_pixels_gt8_pct": round(100 * float((per_px > 8).mean()), 4),
        "max_channel_delta": int(delta.max()),
        "mean_channel_delta": round(float(delta.mean()), 4),
        "mean_channel_delta_changed": round(float(delta[changed].mean()), 3) if changed.any() else 0.0,
    }
    alpha = a[..., 3:4] / 255.0
    gray = (a[..., :3].mean(axis=2, keepdims=True) * alpha + 255 * (1 - alpha))
    base = (255 - (255 - gray) * 0.25).repeat(3, axis=2)
    strength = np.clip(per_px / 64.0, 0.35, 1.0)[..., None] * changed[..., None]
    red = np.array([220, 0, 0])
    out = (base * (1 - strength) + red * strength).astype(np.uint8)
    im = Image.fromarray(out, "RGB")
    im.thumbnail((PREVIEW, PREVIEW), Image.LANCZOS)
    im.save(diff_png, optimize=True)
    return stats


def compare_pair(name, a_svg, b_svg, a_full, b_full, diff_png):
    pa, pb = parse_svg(a_svg), parse_svg(b_svg)
    same_structure, max_shift, haus = geometry(pa, pb)
    stats = pixel_diff(a_full, b_full, diff_png)
    return {
        "identical_svg": sha(a_svg) == sha(b_svg),
        "paths": [pa["paths"], pb["paths"]],
        "palette_equal": [f for f, _ in pa["groups"]] == [f for f, _ in pb["groups"]],
        "palette_set_equal": sorted(f for f, _ in pa["groups"]) == sorted(f for f, _ in pb["groups"]),
        "same_path_structure": same_structure,
        "max_coordinate_shift_px": max_shift,
        "vertex_hausdorff_px": haus,
        **stats,
    }


def cmd_report(a):
    runs, out = Path(a.runs), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for d in sorted(p for p in runs.iterdir() if p.is_dir()):
        cpu = (d / "cpu.txt").read_text().strip()
        labels = {j.stem: json.loads(j.read_text()) for j in d.glob("*.json")}
        jobs.append({"dir": d, "job": d.name, "cpu": cpu, "runs": labels})
    cases = list(golden.CASES)

    def variants(label):
        groups = {}
        for j in jobs:
            key = tuple(j["runs"][label]["sha256"][c] for c in cases)
            groups.setdefault(key, []).append(j)
        return sorted(groups.values(), key=lambda g: -len(g))

    base_variants = variants("base")
    cand_variants = variants("cand")
    extra_labels = sorted({l for j in jobs for l in j["runs"]} - {"base", "cand"})
    extra = {}
    for l in extra_labels:
        ref = cand_variants[0][0]["runs"]["cand"]["sha256"]
        extra[l] = {
            "env": jobs[0]["runs"][l]["env"],
            "identical_to_candidate_on_every_job": all(j["runs"][l]["sha256"] == ref for j in jobs),
        }

    sets = {}
    for i, g in enumerate(base_variants):
        sets[f"baseline-{chr(65 + i)}"] = ("base", g)
    for i, g in enumerate(cand_variants):
        sets["candidate" if len(cand_variants) == 1 else f"candidate-{chr(65 + i)}"] = ("cand", g)

    describe = {
        k: {
            "label": lbl,
            "environment": g[0]["runs"][lbl]["environment"],
            "env": g[0]["runs"][lbl]["env"],
            "jobs": len(g),
            "cpus": sorted({j["cpu"] for j in g}),
        }
        for k, (lbl, g) in sets.items()
    }
    cand_key = next(k for k in sets if k.startswith("candidate"))
    base_keys = [k for k in sets if k.startswith("baseline")]
    pairs = [(b, cand_key) for b in base_keys] + [(base_keys[0], b) for b in base_keys[1:]]

    tmp = Path(tempfile.mkdtemp())
    manifest_cases = []

    def do_case(name):
        source, args = golden.CASES[name]
        files, full, seen = {}, {}, {}
        for k, (lbl, g) in sets.items():
            src = g[0]["dir"] / lbl / f"{name}.svg"
            digest = sha(src)
            if digest in seen:  # same bytes as another set's: point at its files instead of storing them twice
                files[k], full[k] = dict(files[seen[digest]]), full[seen[digest]]
                continue
            seen[digest] = k
            svg = out / "svg" / k / f"{name}.svg"
            svg.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, svg)
            w = parse_svg(svg)["size"][0]
            full[k] = tmp / f"{k}-{name}.png"
            render(svg, full[k], w)
            png = out / "png" / k / f"{name}.png"
            png.parent.mkdir(parents=True, exist_ok=True)
            save_preview(full[k], png)
            files[k] = {"svg": str(svg.relative_to(out)), "png": str(png.relative_to(out)), "sha256": sha(svg)}
        comps = []
        for x, y in pairs:
            diff = out / "diff" / f"{x}__vs__{y}" / f"{name}.png"
            diff.parent.mkdir(parents=True, exist_ok=True)
            c = compare_pair(name, out / files[x]["svg"], out / files[y]["svg"], full[x], full[y], diff)
            comps.append({"a": x, "b": y, "diff_png": str(diff.relative_to(out)), **c})
        return {
            "name": name,
            "input": str(Path(source).relative_to(golden.ROOT)),
            "options": args,
            "files": files,
            "comparisons": comps,
        }

    with ThreadPoolExecutor(os.cpu_count() or 1) as pool:
        manifest_cases = list(pool.map(do_case, cases))

    manifest = {
        "description": "Golden cases: production today (baseline, Python 3.13, locked deps, no env vars) vs "
        "candidate (Python 3.15, locked deps, OPENBLAS_CORETYPE=Haswell and NPY_DISABLE_CPU_FEATURES). "
        "PNGs are rsvg-convert renders downscaled to <= 800 px; the numbers are measured on full-size renders. "
        "diff PNG: image faded to gray, changed pixels in red (stronger = larger delta).",
        "cpu_models_seen": sorted({j["cpu"] for j in jobs}),
        "jobs": [{"job": j["job"], "cpu": j["cpu"], "baseline_variant": next(k for k, (l, g) in sets.items() if l == "base" and j in g),
                  "candidate_variant": next(k for k, (l, g) in sets.items() if l == "cand" and j in g)} for j in jobs],
        "sets": describe,
        "candidate_identical_across_cpus": len(cand_variants) == 1,
        "baseline_variants": len(base_variants),
        "extra_candidate_runs": extra,
        "cases": manifest_cases,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k != "cases"}, indent=1))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--label", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--pinned", action="store_true")
    r.add_argument("--threads", type=int)
    r.add_argument("--jobs", type=int)
    s = sub.add_parser("report")
    s.add_argument("--runs", required=True)
    s.add_argument("--out", required=True)
    a = p.parse_args()
    return {"run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
