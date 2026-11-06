#!/usr/bin/env python
"""Build the book at docs/vectorizing/: every processing image and number comes from running the real engines here.

    uv run --no-project --with numpy --with pillow --with scipy --with potracer python tools/book/make.py

Takes about twenty minutes. Set BOOK_CACHE to a directory to keep the engine runs between builds while writing; left
unset, everything is recomputed. The numbers from Chromium are the exception: see browser_counts.py.
"""

from __future__ import annotations

import base64
import functools
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ch_a  # noqa: E402
import ch_b  # noqa: E402
import ch_c  # noqa: E402
import measures  # noqa: E402
from draw import OUT  # noqa: E402
from harness import ROOT, SOURCES, ClassicOptions, lab_mod, load, trace_classic, trace_new  # noqa: E402

PAGE = OUT.parent / "index.html"


class Context:
    """What the chapters share: the measured runs, and traces kept while they are in use."""

    options = ClassicOptions
    # Windows onto what chapter 10 discusses, in source pixels: (image, box, key, zoom).
    defect_boxes = [
        ("watchmaker", (800, 470, 960, 570), "lathe", 4),
        ("diver", (810, 330, 950, 520), "lantern", 3),
        ("sunset", (560, 80, 860, 300), "sunset", 2),
        ("axolotl", (640, 200, 780, 290), "mouth", 4),
        ("float", (670, 225, 760, 290), "mouth2", 5),
        ("ghost", (520, 140, 640, 220), "ghost", 5),
    ]
    also_box = (540, 100, 840, 340)

    def __init__(self, work: Path, runs: dict):
        self.work, self.runs = work, runs
        self._new: dict = {}
        self._classic: dict = {}

    def svg(self, name, engine, layers):
        return (self.work / "runs" / f"{name}-{engine}-{layers}.svg").read_text(encoding="utf-8")

    def new(self, name):
        if name not in self._new:
            if len(self._new) >= 3:
                self._new.pop(next(iter(self._new)))
            self._new[name] = trace_new(load(SOURCES[name]), name)
        return self._new[name]

    def new_window(self, name, window):
        return trace_new(load(SOURCES[name]), name, window=window)

    def classic(self, name):
        if name not in self._classic:
            if len(self._classic) >= 2:
                self._classic.pop(next(iter(self._classic)))
            self._classic[name] = trace_classic(load(SOURCES[name]), name)
        return self._classic[name]


FIG_OPEN = re.compile(r"^<<<\s+(real|data|diagram)(?:\s+(\S+))?(?:\s+(pix))?\s*$")
TAGS = {"real": "Ejecución real", "data": "Datos reales", "diagram": "Diagrama"}


def expand_figures(text: str) -> str:
    """`<<< kind cols pix` ... `===` caption `>>>` becomes a numbered figure, with its kind on the caption."""
    out, lines, chapter, number = [], text.split("\n"), 0, 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r'<h2 id="c(\d+)"', line)
        if m:
            chapter, number = int(m.group(1)), 0
        m = re.search(r'<figure class="fig" id="f\d+-(\d+)"', line)
        if m:
            number = int(m.group(1))
        m = FIG_OPEN.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        kind, cols, pix = m.group(1), m.group(2) or "1", m.group(3)
        number += 1
        i += 1
        body = []
        while lines[i].strip() != "===":
            body.append(lines[i])
            i += 1
        i += 1
        caption = []
        while lines[i].strip() != ">>>":
            caption.append(lines[i])
            i += 1
        i += 1
        cells, loose = [], []
        for row in body:
            if " | " in row and row.lstrip().startswith("{{"):
                src, label = row.strip().split(" | ", 1)
                cells.append(f'<figure><img loading="lazy" src="{src}" alt="{html.escape(re.sub("<[^>]+>", "", label), quote=True)}"><figcaption>{label}</figcaption></figure>')
            elif row.strip():
                loose.append(row)
        inner = f'<div class="g g{cols}{" pix" if pix else ""}">{"".join(cells)}</div>' if cells else ""
        inner += "\n".join(loose)
        out.append(f'<figure class="fig {kind}" id="f{chapter}-{number}">{inner}<figcaption class="cap"><b>Figura {chapter}.{number}</b> <span class="tag {kind}">{TAGS[kind]}</span> {" ".join(caption)}</figcaption></figure>')
    return "\n".join(out)


def fill(template: str, values: dict) -> str:
    missing = set()

    def sub(m):
        key = m.group(1)
        if key not in values:
            missing.add(key)
            return ""
        return str(values[key])

    done = re.sub(r"\{\{(\w+)\}\}", sub, template)
    if missing:
        raise SystemExit(f"template names values no chapter produced: {sorted(missing)}")
    return done


def main():
    t0 = time.time()
    cached = os.environ.get("BOOK_CACHE")
    work = Path(cached) if cached else Path(tempfile.mkdtemp(prefix="unpixel-book-"))
    only = sys.argv[1:]  # chapter functions, while writing
    if not only:
        shutil.rmtree(OUT.parent, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    runs_file = work / "runs.json"
    if cached and runs_file.exists():
        runs = json.loads(runs_file.read_text())
    else:
        print("Running the engines over the battery", flush=True)
        runs = measures.collect(work / "runs")
        runs_file.write_text(json.dumps(runs))
    ctx = Context(work, runs)
    chapters = [ch_a.chapter1, ch_a.chapter2, ch_a.chapter3, ch_a.chapter4, ch_b.chapter5, ch_b.chapter6, ch_b.chapter7,
                ch_c.chapter8, ch_c.chapter9, ch_c.chapter10]
    values_file = work / "values.json"
    values = json.loads(values_file.read_text()) if cached and values_file.exists() else {}
    for fn in chapters:
        if only and fn.__name__ not in only:
            continue
        t = time.time()
        values.update(fn(ctx))
        print(f"{fn.__name__}: {time.time() - t:.0f} s", flush=True)
    if cached:
        values_file.write_text(json.dumps({k: v for k, v in values.items() if isinstance(v, (str, int, float))}))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    font = base64.b64encode((HERE / "assets/PixelifySans-subset.woff2").read_bytes()).decode()
    values.update(commit=commit, font=font, assign_window=lab_mod.ASSIGN_WINDOW, background_window=lab_mod.BACKGROUND_WINDOW)
    body = expand_figures((HERE / "book.html").read_text(encoding="utf-8"))
    body = body.replace("IMG_BUTTONS", "".join(f'<button type="button" data-image="{n}">{n}</button>' for n in SOURCES))
    values["toc"] = "".join(f'<li><a href="#{a}">{re.sub("<[^>]+>", "", t)}</a></li>' for a, t in re.findall(r'<h2 id="(\w+)"[^>]*>(.*?)</h2>', body))
    template = (HERE / "head.html").read_text(encoding="utf-8") + body + (HERE / "tail.html").read_text(encoding="utf-8")
    page = fill(template, values)
    # Decimal commas in table cells; a point followed by three digits is a thousands separator.
    page = re.sub(r'(<td>(?:<span [^>]*></span>)?\d+)\.(\d{1,2})(?=(?: ?%)?</td>)', r"\1,\2", page)
    PAGE.write_text(page, encoding="utf-8")
    shutil.copy(HERE / "assets/OFL-PixelifySans.txt", OUT.parent / "OFL-PixelifySans.txt")
    raw = {k: {f: v[f] for f in ("seconds", "peak_rss_mb", "stages", "measure", "colors") if f in v} for k, v in runs.items()}
    (OUT.parent / "measurements.json").write_text(json.dumps({"commit": commit, "runs": raw}, indent=0))
    total = sum(f.stat().st_size for f in OUT.parent.rglob("*") if f.is_file())
    print(f"{PAGE}: {total / 1e6:.1f} MB in all, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
