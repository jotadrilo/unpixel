#!/usr/bin/env python
"""Count see-through pixels in Chromium, the way tools/engine/browser_check.py does, for the book's chapter 10.

This pass is separate from make.py because it needs Playwright. Run it from a Python with Playwright, on the SVGs
that make.py wrote to its work directory (set BOOK_CACHE to keep them), and commit its output, tools/book/data/browser.json.
usage: browser_counts.py DIR_WITH_SVGS. The directory holds <image>-<new|classic>-<stacked|cutout>.svg. Set CHROMIUM to pick a binary.
"""
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from browser_check import see_through  # noqa: E402

HERE = Path(__file__).resolve().parent


def main():
    source = Path(sys.argv[1])  # pin-*.svg sit one level up from the runs, in the work directory
    rows = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        version = browser.version
        for path in sorted(source.glob("*-*-*.svg")):
            if path.stem.split("-")[1] not in ("new", "classic") or path.stem.startswith("leaves24"):
                continue
            text = path.read_text(encoding="utf-8")
            w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', text).groups())
            row = {"file": path.stem, "scales": {}}
            for s in (1, 3, 0.25):
                vw, vh = max(1, round(w * s)), max(1, round(h * s))
                page = browser.new_page(viewport={"width": vw, "height": vh}, device_scale_factor=1)
                svg = re.sub(r'width="\d+" height="\d+"', f'width="{vw}" height="{vh}"', text, count=1)
                page.set_content(f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent">{svg}</body></html>')
                shot = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": vw, "height": vh})
                page.close()
                row["scales"][str(s)] = see_through(np.asarray(Image.open(io.BytesIO(shot)).convert("RGBA"))[..., 3])
            rows.append(row)
            print(row["file"], {k: v["under_200"] for k, v in row["scales"].items()}, flush=True)
        pins = {}
        for name, x, y in (("float", 347, 200), ("leaves", 816, 454)):
            text = (source.parent / f"pin-{name}.svg").read_text(encoding="utf-8")
            w, h = (int(v) for v in re.search(r'width="(\d+)" height="(\d+)"', text).groups())
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(f'<!doctype html><html style="background:transparent"><body style="margin:0;background:transparent">{text}</body></html>')
            shot = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
            pins[name] = int(np.asarray(Image.open(io.BytesIO(shot)).convert("RGBA"))[y, x, 3])
        browser.close()
    commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", "src"], capture_output=True, text=True, cwd=HERE.parents[1]).stdout.strip()
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data/browser.json").write_text(json.dumps({"browser": f"Chromium {version}", "commit": commit, "pins": pins, "rows": rows}, indent=0))


if __name__ == "__main__":
    main()
