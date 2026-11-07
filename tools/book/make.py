#!/usr/bin/env python
"""Build the book at docs/vectorizing/, in English and Spanish, with the same figures for both.

    uv run --no-project --with numpy --with pillow --with scipy --with potracer python tools/book/make.py

Every processing image and number comes from running unpixel here; potrace is only for chapter 8's demonstration of
another technique. Takes about fifteen minutes. Set BOOK_CACHE to a
directory to keep the runs between builds while writing; left unset, everything is recomputed. Pass chapter function
names to redo only those. The numbers from Chromium are the exception: see browser_counts.py.
"""

from __future__ import annotations

import base64
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
import diagrams  # noqa: E402
import measures  # noqa: E402
from draw import OUT, localize  # noqa: E402
from harness import ROOT, SOURCES, lab_mod, load, trace_run  # noqa: E402

BOOK = OUT.parent
LANGS = {
    "en": {"page": BOOK / "index.html", "template": "book.en.html", "title": "How to vectorize an image", "toc": "Chapters", "theme": "Light / dark",
           "other": "es", "href": "es/index.html", "name": "Leer en español", "figure": "Figure",
           "tags": {"real": "Real run", "data": "Real data", "diagram": "Diagram"}},
    "es": {"page": BOOK / "es/index.html", "template": "book.es.html", "title": "Cómo vectorizar una imagen", "toc": "Capítulos", "theme": "Claro / oscuro",
           "other": "en", "href": "../index.html", "name": "Read in English", "figure": "Figura",
           "tags": {"real": "Ejecución real", "data": "Datos reales", "diagram": "Diagrama"}},
}


class Context:
    """What the chapters share: the measured runs, and traces kept while they are in use."""

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
        self._traces: dict = {}

    def svg(self, name, layers):
        return (self.work / "runs" / f"{name}-{layers}.svg").read_text(encoding="utf-8")

    def run(self, name):
        if name not in self._traces:
            if len(self._traces) >= 3:
                self._traces.pop(next(iter(self._traces)))
            self._traces[name] = trace_run(load(SOURCES[name]), name)
        return self._traces[name]

    def run_window(self, name, window):
        return trace_run(load(SOURCES[name]), name, window=window)


FIG_OPEN = re.compile(r"^<<<\s+(real|data|diagram)(?:\s+(\S+))?(?:\s+(pix))?\s*$")


def expand_figures(text: str, lang: dict) -> str:
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
        out.append(f'<figure class="fig {kind}" id="f{chapter}-{number}">{inner}<figcaption class="cap"><b>{lang["figure"]} {chapter}.{number}</b> <span class="tag {kind}">{lang["tags"][kind]}</span> {" ".join(caption)}</figcaption></figure>')
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


def write_pages(values: dict, commit: str, font: str):
    for code, lang in LANGS.items():
        body = expand_figures((HERE / lang["template"]).read_text(encoding="utf-8"), lang)
        toc = "".join(f'<li><a href="#{a}">{re.sub("<[^>]+>", "", t)}</a></li>' for a, t in re.findall(r'<h2 id="(\w+)"[^>]*>(.*?)</h2>', body))
        page_values = {**values, "toc": toc, "commit": commit, "font": font, "lang": code, "title": lang["title"], "toc_label": lang["toc"],
                       "lang_href": lang["href"], "lang_other": lang["other"], "lang_name": lang["name"], "theme_label": lang["theme"],
                       "assign_window": lab_mod.ASSIGN_WINDOW, "background_window": lab_mod.BACKGROUND_WINDOW}
        template = (HERE / "head.html").read_text(encoding="utf-8") + body + (HERE / "tail.html").read_text(encoding="utf-8")
        page = localize(fill(template, page_values), code)
        if code != "en":  # the Spanish page sits one folder down and shares the figures
            page = re.sub(r'(src=")(img/)', r"\1../\2", page)
            page = re.sub(r'"(img|svg)/', r'"../\1/', page)
            page = page.replace('"../../', '"../')
        lang["page"].parent.mkdir(parents=True, exist_ok=True)
        lang["page"].write_text(page, encoding="utf-8")


def main():
    t0 = time.time()
    cached = os.environ.get("BOOK_CACHE")
    work = Path(cached) if cached else Path(tempfile.mkdtemp(prefix="unpixel-book-"))
    work.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:]
    if not only:
        shutil.rmtree(BOOK, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    runs_file = work / "runs.json"
    if cached and runs_file.exists():
        runs = json.loads(runs_file.read_text())
    else:
        print("Running unpixel over the battery", flush=True)
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
            values_file.write_text(json.dumps(values))
    values.update(diagrams.all_values(list(SOURCES), values["viewer_first"]))
    commit = subprocess.run(["git", "log", "-1", "--format=%h", "--", "src"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    write_pages(values, commit, base64.b64encode((HERE / "assets/PixelifySans-subset.woff2").read_bytes()).decode())
    shutil.copy(HERE / "assets/OFL-PixelifySans.txt", BOOK / "OFL-PixelifySans.txt")
    raw = {k: {f: v[f] for f in ("seconds", "peak_rss_mb", "stages", "measure", "colors") if f in v} for k, v in runs.items()}
    (BOOK / "measurements.json").write_text(json.dumps({"commit": commit, "runs": raw}, indent=0))
    total = sum(f.stat().st_size for f in BOOK.rglob("*") if f.is_file())
    print(f"{BOOK}: {total / 1e6:.1f} MB in all, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
