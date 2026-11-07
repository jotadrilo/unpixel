"""Run unpixel and keep what passes through it, without copying a line of its logic.

Two tools do all the work. `patched` swaps a module's function for a wrapper that records its arguments and its
result and then returns that result untouched. `locals_of` reads a function's local variables at the moment it
returns, through `sys.setprofile`, for the values that are never handed to another function. Everything the
book shows of its inside comes from these recordings.
"""

from __future__ import annotations

import functools
import inspect
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from unpixel.engine import classify as classify_mod  # noqa: E402
from unpixel.engine import curves as curves_mod  # noqa: E402
from unpixel.engine import labels as lab_mod  # noqa: E402
from unpixel.engine import pipeline as pipe_mod  # noqa: E402
from unpixel.engine import planar as planar_mod  # noqa: E402
from unpixel.engine import svgout as svg_mod  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

SOURCES = {
    "axolotl": ROOT / "examples/axolotl/input.png",
    "diver": ROOT / "battery/diver.png",
    "leaves": ROOT / "battery/leaves.png",
    "chef": ROOT / "battery/chef.png",
    "ghost": ROOT / "battery/ghost.png",
    "watchmaker": ROOT / "battery/watchmaker.png",
    "float": ROOT / "battery/float.png",
    "sunset": ROOT / "battery/sunset.png",
    "principito": ROOT / "battery/principito.jpeg",
}


def load(path) -> np.ndarray:
    """The source on white, as tools/engine reads it."""
    rgba = Image.open(path).convert("RGBA")
    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    base.alpha_composite(rgba)
    return np.asarray(base.convert("RGB"))


@contextmanager
def patched(module, name, wrapper):
    original = getattr(module, name)
    setattr(module, name, wrapper(original))
    try:
        yield original
    finally:
        setattr(module, name, original)


@contextmanager
def patches(*triples):
    """Apply several (module, name, wrapper) at once."""
    if not triples:
        yield
        return
    with patched(*triples[0]):
        with patches(*triples[1:]):
            yield


def recorder(store: list, keep_args=True, snapshot=False):
    """A wrapper factory that appends {args, kwargs, result} of each call to `store`.

    `snapshot` keeps a copy of the result, for a function whose caller goes on to change it in place.
    """

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            result = fn(*args, **kwargs)
            kept = result.copy() if snapshot else result
            store.append({"args": args if keep_args else None, "kwargs": kwargs if keep_args else None, "result": kept})
            return result

        return inner

    return wrap


@contextmanager
def locals_of(*codes):
    """Yield a dict filled, on each return of the given functions, with their locals: name -> list of dicts."""
    codes = [inspect.unwrap(f) for f in codes]  # past a recorder, to the function itself
    wanted = {f.__code__: f.__name__ for f in codes}
    seen: dict[str, list[dict]] = {f.__name__: [] for f in codes}

    def profiler(frame, event, arg):
        if event == "return" and frame.f_code in wanted:
            seen[wanted[frame.f_code]].append(dict(frame.f_locals))

    previous = sys.getprofile()
    sys.setprofile(profiler)
    try:
        yield seen
    finally:
        sys.setprofile(previous)


@dataclass
class Trace:
    rgb: np.ndarray
    result: object = None
    lab_raw: np.ndarray | None = None
    bilateral: np.ndarray | None = None
    lab: np.ndarray | None = None  # after flatten_gradients
    transition: np.ndarray | None = None
    background: object = None
    palettes: list = field(default_factory=list)  # each build_palette: args, kwargs, result
    palette_locals: list = field(default_factory=list)
    assigns: list = field(default_factory=list)
    fringes: list = field(default_factory=list)
    settled: list = field(default_factory=list)
    refine: list = field(default_factory=list)
    specks: list = field(default_factory=list)
    speckle: list = field(default_factory=list)
    floating: list = field(default_factory=list)
    planar: list = field(default_factory=list)
    trace_locals: list = field(default_factory=list)
    find_corners: list = field(default_factory=list)
    fit: list = field(default_factory=list)
    smooth: list = field(default_factory=list)
    write_svg: list = field(default_factory=list)


def trace_run(rgb: np.ndarray, title: str = "image", variant: str = "stacked", window: int | None = None) -> Trace:
    """The real `pipeline.run`, with every stage's input and output kept."""
    t = Trace(rgb)
    rec: dict[str, list] = {k: [] for k in "perceptual bilateral flatten transition find_background guard".split()}
    triples = [
        (lab_mod, "perceptual", recorder(rec["perceptual"])),
        (lab_mod, "bilateral", recorder(rec["bilateral"], keep_args=False)),
        (lab_mod, "flatten_gradients", recorder(rec["flatten"], keep_args=False)),
        (lab_mod, "transition_mask", recorder(rec["transition"], keep_args=False)),
        (lab_mod, "nothing_left_guard", recorder(rec["guard"], keep_args=False)),
        (lab_mod, "build_palette", recorder(t.palettes)),
        (lab_mod, "assign_large", recorder(t.assigns)),
        (lab_mod, "dissolve_fringes", recorder(t.fringes)),
        (lab_mod, "settle_colors", recorder(t.settled)),
        (lab_mod, "refine_double", recorder(t.refine)),
        (lab_mod, "absorb_specks", recorder(t.specks)),
        (lab_mod, "dissolve_speckle", recorder(t.speckle)),
        (lab_mod, "drop_floating_pale", recorder(t.floating)),
        (planar_mod, "build", recorder(t.planar)),
        (curves_mod, "find_corners", recorder(t.find_corners)),
        (curves_mod, "smooth_chains", recorder(t.smooth)),
        (curves_mod, "fit_chains", recorder(t.fit)),
        (svg_mod, "write_svg", recorder(t.write_svg)),
    ]
    original_assign = lab_mod.assign
    if window is not None:
        lab_mod.assign = functools.partial(original_assign, window=window)
    try:
        with patches(*triples), locals_of(lab_mod.build_palette, pipe_mod._trace) as seen:
            t.result = pipe_mod.run(rgb, variant, title)
    finally:
        lab_mod.assign = original_assign
    t.palette_locals = seen["build_palette"]
    t.trace_locals = seen["_trace"]
    t.lab_raw = rec["perceptual"][0]["result"] if rec["perceptual"] else None
    t.bilateral = rec["bilateral"][0]["result"] if rec["bilateral"] else None
    t.lab = rec["flatten"][0]["result"] if rec["flatten"] else t.lab_raw
    t.transition = rec["transition"][0]["result"] if rec["transition"] else None
    t.background = rec["guard"][0]["result"] if rec["guard"] else None
    return t
