#!/usr/bin/env python
"""Golden outputs: run the CLI on the battery and compare each SVG with the one recorded in tests/golden.json.

usage: tools/golden.py            check, and list the cases whose SVG changed (exit 1 if any)
       tools/golden.py --update   record the current outputs as this platform's goldens
       tools/golden.py --out DIR  also keep the SVGs it writes, to look at them

The SVG bytes depend on the platform: the same code and locked libraries give slightly different coordinates
on macOS arm64 and Linux x86_64, and even under Docker on a Mac (float32 math in OpenBLAS, numpy's SIMD
kernels and the C library). So each platform has its own goldens, and on x86_64 the CPU kernels are pinned
(PINNED_X86_64) so every GitHub runner, AMD or Intel, gives the same bytes. The linux-x86_64 goldens, the
ones CI checks, are recorded on a runner by the "Record goldens" workflow (.github/workflows/goldens.yml).

Refresh the goldens only after the owner has validated the new output on the battery (battery/README.md).
"""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden.json"
BATTERY = ROOT / "battery"
AXOLOTL = ROOT / "examples" / "axolotl" / "input.png"

# name -> (input, extra CLI arguments). The battery with no options, plus the options that take other paths.
CASES = {
    "axolotl": (AXOLOTL, []),
    "chef": (BATTERY / "chef.png", []),
    "diver": (BATTERY / "diver.png", []),
    "float": (BATTERY / "float.png", []),
    "ghost": (BATTERY / "ghost.png", []),
    "leaves": (BATTERY / "leaves.png", []),
    "principito": (BATTERY / "principito.jpeg", []),
    "sunset": (BATTERY / "sunset.png", []),
    "watchmaker": (BATTERY / "watchmaker.png", []),
    "axolotl-colors-8": (AXOLOTL, ["--colors", "8"]),
    "axolotl-cutout-6": (AXOLOTL, ["--colors", "6", "--layers", "cutout"]),
    "axolotl-brand": (AXOLOTL, ["--colors", "#FFB800,#FFC2D6,#00B8D4,#0090A8,#FF2E7E,#6A3DF0,#14102A,#FFFFFF,#FF8A00"]),
    "float-knockout": (BATTERY / "float.png", ["--also-transparent", "#FBFBFB"]),
    "principito-keep": (BATTERY / "principito.jpeg", ["--background", "keep"]),
    "watchmaker-low": (BATTERY / "watchmaker.png", ["--detail", "low"]),
    "watchmaker-high": (BATTERY / "watchmaker.png", ["--detail", "high"]),
    "chef-outline-edges": (BATTERY / "chef.png", ["--outline", "edges"]),
}

DEPENDENCIES = ("numpy", "pillow", "scipy")

# OpenBLAS picks its kernels by CPU (Nehalem, Haswell, SkylakeX...) and numpy dispatches AVX-512 where it can,
# and either changes the last digits of some coordinates. Haswell kernels and at most AVX2 run on every
# x86_64 CI runner, so these make the bytes the same on all of them. Production sets them too (README, "Same output on every x86_64 host").
PINNED_X86_64 = {
    "OPENBLAS_CORETYPE": "Haswell",
    "NPY_DISABLE_CPU_FEATURES": "X86_V4 AVX512_ICL AVX512_SPR",
}


def platform_key():
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{sys.platform}-{machine}"


def case_env():
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1")
    if platform_key().endswith("x86_64"):
        env.update(PINNED_X86_64)
    return env


def environment():
    """What the goldens depend on besides the code: the Python minor (it picks the locked versions) and the libraries."""
    env = {"python": f"{sys.version_info.major}.{sys.version_info.minor}"}
    env.update({name: version(name) for name in DEPENDENCIES})
    return env


def run_case(name, out_dir):
    source, args = CASES[name]
    svg = Path(out_dir) / f"{name}.svg"
    cmd = [sys.executable, "-m", "unpixel", str(source), "-o", str(svg), "--no-report", "--force", "--color", "never", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900, env=case_env())
    if result.returncode:
        raise RuntimeError(f"{name}: unpixel exited {result.returncode}\n{result.stderr[-2000:]}")
    data = svg.read_bytes()
    return {
        "args": args,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "palette": re.findall(r'<g id="color-\d+" fill="(#[0-9A-Fa-f]{6})"', data.decode("utf-8")),
    }


def run_all(out_dir, names=None, jobs=None):
    names = list(names or CASES)
    jobs = jobs or min(len(names), os.cpu_count() or 1)
    with ThreadPoolExecutor(jobs) as pool:
        return dict(zip(names, pool.map(lambda n: run_case(n, out_dir), names)))


def load():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def goldens_for_platform(golden=None):
    """This platform's recorded goldens ({"environment", "cases"}), or None when there are none."""
    golden = golden if golden is not None else load()
    return golden.get(platform_key())


def compare(recorded, actual):
    """Lines describing every case whose output differs from its golden, empty when all match."""
    lines = []
    for name in sorted(set(recorded["cases"]) | set(actual)):
        want, got = recorded["cases"].get(name), actual.get(name)
        if want is None:
            lines.append(f"{name}: no golden recorded")
        elif got is None:
            lines.append(f"{name}: golden recorded but the case was not run")
        elif want["sha256"] != got["sha256"]:
            if want["palette"] != got["palette"]:
                why = f"palette {len(want['palette'])} -> {len(got['palette'])} colors: {' '.join(want['palette'])} -> {' '.join(got['palette'])}"
            else:
                why = "same palette, different shapes"
            lines.append(f"{name}: SVG changed, {want['bytes']} -> {got['bytes']} bytes, {why}")
    return lines


def environment_note(recorded):
    now = environment()
    changed = [f"{k} {recorded['environment'].get(k)} -> {now[k]}" for k in now if recorded["environment"].get(k) != now[k]]
    return ("Environment differs from the one the goldens were made with: " + ", ".join(changed)) if changed else ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--update", action="store_true", help="record the current outputs as the goldens")
    p.add_argument("--out", help="directory to keep the SVGs in (default: a temporary one)")
    p.add_argument("--jobs", type=int)
    a = p.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        out = a.out or tmp
        os.makedirs(out, exist_ok=True)
        actual = run_all(out, jobs=a.jobs)

    key = platform_key()
    if a.update:
        golden = load() if GOLDEN.exists() else {}
        golden[key] = {"environment": environment(), "cases": actual}
        GOLDEN.write_text(json.dumps(dict(sorted(golden.items())), indent=1) + "\n", encoding="utf-8")
        print(f"Recorded {len(actual)} {key} goldens in {GOLDEN.relative_to(ROOT)} with {environment()}")
        return 0

    recorded = goldens_for_platform()
    if recorded is None:
        print(f"No goldens recorded for {key}; record them with --update")
        return 1
    note = environment_note(recorded)
    if note:
        print(note)
    diff = compare(recorded, actual)
    for line in diff:
        print(line)
    print(f"{len(diff)} of {len(actual)} outputs changed" if diff else f"All {len(actual)} outputs match their goldens")
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
