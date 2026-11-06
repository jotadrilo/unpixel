"""What the prototype engine must keep. These hold for the engine alone; the current tests are not changed."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from unpixel.color import srgb_to_lab
from unpixel.engine import classify, curves, labels, pipeline, planar

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "engine"))
import synth  # noqa: E402
from measure import analyze_paths  # noqa: E402

needs_rsvg = pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert is not installed")


def render(svg: str, tmp_path, width=None, height=None) -> np.ndarray:
    path = tmp_path / "out.svg"
    path.write_text(svg, encoding="utf-8")
    png = tmp_path / "out.png"
    cmd = ["rsvg-convert", str(path), "-o", str(png)]
    if width:
        cmd += ["-w", str(width), "-h", str(height)]
    subprocess.run(cmd, check=True)
    return np.asarray(Image.open(png).convert("RGBA"))


def soft(image: Image.Image, seed: int = 0, noise: float = 1.2) -> np.ndarray:
    blurred = image.filter(ImageFilter.GaussianBlur(1.1))
    rng = np.random.default_rng(seed)
    return np.clip(np.asarray(blurred, dtype=np.float32) + rng.normal(0, noise, (image.height, image.width, 3)), 0, 255).astype(np.uint8)


def poster(size=500, dark=(20, 15, 30), light=(250, 190, 200)) -> Image.Image:
    im = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((60, 60, size - 60, size - 60), fill=dark)
    d.ellipse((80, 80, size - 80, size - 80), fill=light)
    return im


def palette_of(rgb, **kw):
    lab = labels.bilateral(labels.perceptual(srgb_to_lab(rgb)))
    t = labels.transition_mask(lab)
    bg = labels.find_background(lab)
    s = ~t & ~bg.mask
    return labels.build_palette(lab, s, highlights=labels.highlight_mask(lab, s), **kw), lab, t, bg


def near(palette_rgb, color, tolerance=8.0) -> bool:
    d = np.sqrt(((srgb_to_lab(palette_rgb.astype(np.float32)) - srgb_to_lab(np.array(color, np.float32))) ** 2).sum(-1))
    return float(d.min()) <= tolerance


def test_palette_is_deterministic():
    rgb = soft(poster())
    a, *_ = palette_of(rgb)
    b, *_ = palette_of(rgb)
    assert np.array_equal(a.lab, b.lab)


def test_palette_keeps_a_small_distinct_color_and_does_not_split_a_large_one():
    im = Image.new("RGB", (600, 600), (176, 119, 40))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 300, 600, 600), fill=(165, 110, 37))  # a near-identical tone over half the image
    d.ellipse((280, 280, 320, 320), fill=(247, 209, 175))  # skin, 0.35%
    pal, *_ = palette_of(soft(im))
    assert near(pal.rgb, (247, 209, 175))
    assert len(pal.lab) <= 4


def test_palette_finds_colors_on_a_pale_image():
    im = Image.new("RGB", (600, 600), (254, 254, 254))
    d = ImageDraw.Draw(im)
    d.ellipse((100, 100, 500, 500), fill=(245, 242, 232))
    d.ellipse((180, 180, 260, 260), fill=(222, 218, 212))
    d.ellipse((340, 180, 420, 260), fill=(240, 210, 212))
    result = pipeline.run(soft(im, noise=0.6), "cutout")
    assert len(result.colors) >= 3


def test_count_is_capped_and_gradients_get_few_bands():
    y, x = np.mgrid[0:400, 0:600]
    arr = np.stack([x / 600 * 255, y / 400 * 255, (x + y) / 1000 * 255], -1)
    arr += np.random.default_rng(1).normal(0, 6, arr.shape)
    rgb = np.clip(arr, 0, 255).astype(np.uint8)
    pal, *_ = palette_of(rgb)
    assert len(pal.lab) <= 24


def test_an_edge_between_two_colors_does_not_become_a_third():
    result = pipeline.run(soft(poster()), "cutout")
    width_of_colors = len(result.colors)
    assert width_of_colors == 2
    # Every painted class is close to one of the two colors drawn.
    assert near(np.array(result.colors), (20, 15, 30))
    assert near(np.array(result.colors), (250, 190, 200))


def test_transition_mask_marks_a_ramp_and_not_a_thin_stroke():
    lab = np.zeros((40, 40, 3), dtype=np.float32) + np.array([90.0, 0, 0], dtype=np.float32)
    lab[:, 20:, 0] = 10.0
    lab[:, 19, 0] = 50.0
    assert labels.transition_mask(lab)[20, 19]
    lab2 = np.zeros((40, 40, 3), dtype=np.float32) + np.array([90.0, 0, 0], dtype=np.float32)
    lab2[:, 19:21, 0] = 10.0
    assert not labels.transition_mask(lab2)[20, 19]


def test_background_is_what_floods_from_the_border():
    rgb = soft(poster())
    result = pipeline.run(rgb, "cutout")
    assert result.has_background
    rgba_center = result.labels[result.labels.shape[0] // 2, result.labels.shape[1] // 2]
    assert rgba_center != len(result.colors)
    im = Image.new("RGB", (500, 500), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((100, 100, 400, 400), fill=(10, 10, 20))
    d.ellipse((200, 200, 300, 300), fill=(255, 255, 255))
    result = pipeline.run(soft(im), "cutout")
    k = len(result.colors)
    assert result.labels[500, 500] != k  # the enclosed white stays painted
    assert result.labels[10, 10] == k


def test_walls_are_shared_and_meet_exactly():
    r = np.zeros((6, 6), dtype=np.int32)
    r[:3, :3] = 1
    r[:3, 3:] = 2
    r[3:, :] = 3
    pmap = planar.build(r)
    uses: dict[int, int] = {}
    for loops in pmap.loops.values():
        for loop in loops:
            for arc, _ in loop:
                uses[arc] = uses.get(arc, 0) + 1
    for i, arc in enumerate(pmap.arcs):
        painted_sides = (arc.left != 0) + (arc.right != 0)
        assert uses.get(i, 0) == painted_sides


def test_svg_walls_use_the_same_numbers_on_both_sides():
    im = Image.new("RGB", (300, 300), (240, 60, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 300, 20), fill=(60, 200, 90))  # a mixed border, so nothing is background
    d.rectangle((0, 280, 300, 300), fill=(60, 200, 90))
    d.rectangle((0, 20, 20, 280), fill=(60, 200, 90))
    d.ellipse((60, 60, 240, 240), fill=(40, 60, 200))
    svg = pipeline.run(soft(im), "cutout").svg
    groups = re.findall(r'<g id="[^"]*" fill="(#[0-9A-F]{6})"[^>]*>(.*?)</g>', svg, re.S)
    assert len(groups) == 3
    groups = [g for g in groups if g[0] != "#3CC85A"]
    def curves_of(body):
        return set(re.findall(r"C[^CLMZ]+", " ".join(re.findall(r'd="([^"]+)"', body))))
    inner = curves_of(groups[1][1])
    outer = curves_of(groups[0][1])
    # The circle's segments appear in both, walked in opposite directions, so endpoints match as a set.
    def ends(cs):
        return {tuple(c[1:].split()[-2:]) for c in cs}
    assert ends(inner) & ends(outer)
    assert len(ends(inner) & ends(outer)) >= 0.8 * len(ends(inner))


@needs_rsvg
@pytest.mark.parametrize("scale", [1.0, 0.73, 2.0])
def test_stacked_shows_no_hairlines(tmp_path, scale):
    im = Image.new("RGB", (400, 400), (240, 60, 60))
    d = ImageDraw.Draw(im)
    d.rectangle((200, 0, 400, 400), fill=(60, 200, 90))  # a mixed border, so nothing is background
    d.ellipse((60, 60, 340, 340), fill=(40, 60, 200))
    d.ellipse((120, 120, 280, 280), fill=(250, 220, 40))
    svg = pipeline.run(soft(im), "stacked").svg
    a = render(svg, tmp_path, round(400 * scale), round(400 * scale))[..., 3]
    # A wall across a pixel leaves at most a trace; an exactly abutting pair would leave a quarter of the pixel.
    assert a[4:-4, 4:-4].min() >= (248 if scale >= 1 else 235)


def test_closed_chain_smoothing_is_clean_at_its_seam_among_other_chains():
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    circle = np.c_[100 + 100 * np.cos(t), 100 + 100 * np.sin(t)]
    line = np.c_[np.arange(50.0), np.zeros(50)]
    out = curves.smooth_chains([line, circle, line], np.array([False, True, False]), np.array([3.0, 3.0, 3.0]))
    assert np.hypot(*(out[1] - circle).T).max() < 0.05


def test_corners_persist_only_where_the_drawing_has_them():
    side = np.linspace(0, 80, 200, endpoint=False)
    square = np.vstack([np.c_[side, 0 * side], np.c_[80 + 0 * side, side], np.c_[80 - side, 80 + 0 * side], np.c_[0 * side, 80 - side]])
    found = curves.find_corners([square], np.array([True]), 0.41)
    assert len(found[0]) == 4
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    circle = np.c_[100 + 100 * np.cos(t), 100 + 100 * np.sin(t)]
    assert curves.find_corners([circle], np.array([True]), 0.41) == {}
    # A pixel staircase, on a straight diagonal, is not a corner.
    x = np.repeat(np.arange(100.0), 2)[:-1] * 0.5
    y = np.repeat(np.arange(100.0), 2)[1:] * 0.5
    assert curves.find_corners([np.c_[x, y]], np.array([False]), 0.41) == {}


def test_fit_meets_tolerance_with_few_nodes():
    t = np.linspace(0, 2 * np.pi, 800, endpoint=False)
    circle = np.c_[100 + 100 * np.cos(t), 100 + 100 * np.sin(t)]
    fitted = curves.fit_chains([circle], np.array([True]), tolerance=0.3)
    assert len(fitted.kinds) <= 12
    # A straight line is one line.
    line = np.c_[np.arange(200.0), np.arange(200.0) * 0.5]
    fitted = curves.fit_chains([line], np.array([False]), tolerance=0.3)
    assert list(fitted.kinds) == [0]


def test_pixel_art_is_detected_and_keeps_straight_edges(tmp_path):
    im = synth.pixel_art(16)
    rgb = np.asarray(im)
    kind = classify.classify(rgb)
    assert kind.name == "pixel" and kind.block == 16
    result = pipeline.run(rgb, "stacked")
    assert " C" not in result.svg and "C" not in re.sub(r"<[^p][^>]*>", "", "".join(re.findall(r'd="([^"]+)"', result.svg)))
    if shutil.which("rsvg-convert"):
        a = render(result.svg, tmp_path, rgb.shape[1], rgb.shape[0])
        flat = a[..., :3].astype(int) * (a[..., 3:] > 0) + 255 * (a[..., 3:] == 0)
        assert (np.abs(flat - rgb).sum(-1) > 10).mean() < 0.005


@pytest.mark.parametrize("aa", [1, 4])
def test_geometry_keeps_straight_edges(aa):
    rgb = np.asarray(synth.geometry(aa))
    svg = pipeline.run(rgb, "cutout").svg
    # The blue rectangle's outer edge: x = 80 runs straight, with no node out of line by a third of a pixel.
    d = re.search(r'fill="#1E3CA0"[^>]*>\s*<path d="([^"]+)"', svg).group(1)
    numbers = np.array(re.findall(r"-?\d+(?:\.\d+)?", d), dtype=float).reshape(-1, 2)
    left = numbers[(numbers[:, 0] < 90) & (numbers[:, 1] > 90) & (numbers[:, 1] < 290)]
    assert len(left) >= 1 and np.abs(left[:, 0] - 80).max() < 0.35


def test_smoothness_on_a_jagged_wall():
    # A soft circle through the whole chain: few nodes, no sharp turns.
    im = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(im).ellipse((60, 60, 340, 340), fill=(30, 30, 40))
    svg = pipeline.run(soft(im), "cutout").svg
    m = analyze_paths(svg, 400, 400)
    assert m["nodes_per_100px"] < 4.0
    assert m["sharp30_share"] == 0.0


def test_labels_variant_runs_through_todays_tracer():
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    ImageDraw.Draw(im).ellipse((60, 60, 240, 240), fill=(30, 30, 40))
    result = pipeline.run(soft(im), "labels")
    assert "<path" in result.svg
