import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from flattrace.cli import main
from flattrace.color import delta_e, parse_hex, srgb_to_lab
from flattrace.render import render_svg

from conftest import CREAM, NAVY, RED


def run(capsys, *args):
    code = main([str(a) for a in args] + ["--json"])
    return code, json.loads(capsys.readouterr().out)


def drawn(result):
    width, height = result["input_size"]
    with open(result["svg"], encoding="utf-8") as handle:
        return render_svg(handle.read(), width, height)


def close(hex_color, rgb, tolerance=6.0):
    return float(delta_e(srgb_to_lab(np.array(parse_hex(hex_color), dtype=np.float32)),
                         srgb_to_lab(np.array(rgb, dtype=np.float32)))) <= tolerance


def has_color(result, rgb):
    return any(close(layer["color"], rgb) for layer in result["layers"])


def test_ticket_keeps_three_colors_and_removes_only_the_outside(save, ticket, capsys):
    code, result = run(capsys, save(ticket))
    assert code == 0
    assert len(result["layers"]) == 3
    assert has_color(result, CREAM) and has_color(result, NAVY) and has_color(result, RED)
    rgba = drawn(result)
    assert rgba[5, 5, 3] == 0 and rgba[-5, -5, 3] == 0
    assert rgba[250, 150, 3] == 255  # the cream card, nearly white, stays opaque
    assert result["metrics"]["opaque_pixels_in_background"] == 0
    assert result["metrics"]["transparent_pixels_in_artwork"] == 0


def test_no_seams_or_transparent_gaps_inside_artwork(save, ticket, capsys):
    _, result = run(capsys, save(ticket))
    rgba = drawn(result)
    assert (rgba[70:430, 70:930, 3] == 255).all()


def test_thin_line_survives(save, ticket, capsys):
    _, result = run(capsys, save(ticket))
    rgba = drawn(result)
    across = rgba[250, 480:520, :3].astype(int)
    assert (np.abs(across - np.array(CREAM)).sum(-1) < 12).sum() >= 3
    assert (np.abs(across - np.array(RED)).sum(-1) < 12).sum() >= 20


def test_enclosed_white_stays_opaque_and_warns(save, stamp, capsys):
    code, result = run(capsys, save(stamp))
    assert code == 0
    assert drawn(result)[400, 400, 3] == 255
    assert any("--also-transparent" in w for w in result["warnings"])


def test_also_transparent_opens_enclosed_areas(save, stamp, capsys):
    _, first = run(capsys, save(stamp))
    hint = [l["color"] for l in first["layers"] if close(l["color"], (255, 255, 255))][0]
    code, result = run(capsys, save(stamp, "again.png"), "--also-transparent", hint)
    assert code == 0
    rgba = drawn(result)
    assert rgba[400, 400, 3] == 0 and rgba[200, 400, 3] == 255
    assert len(result["layers"]) == 1


def test_background_keep_makes_everything_opaque(save, stamp, capsys):
    _, result = run(capsys, save(stamp), "--background", "keep")
    assert result["background_removed"] is None
    assert (drawn(result)[..., 3] == 255).mean() > 0.999


def test_adjacent_pale_colors_without_outline_are_separated(save, no_outline, capsys):
    _, result = run(capsys, save(no_outline))
    assert len(result["layers"]) == 1 and has_color(result, CREAM)
    rgba = drawn(result)
    assert rgba[10, 10, 3] == 0 and rgba[300, 400, 3] == 255


def test_color_count_merges_closest(save, ticket, capsys):
    _, result = run(capsys, save(ticket), "--colors", "2")
    assert len(result["layers"]) == 2


def test_exact_palette_is_used(save, ticket, capsys):
    _, result = run(capsys, save(ticket), "--colors", "#112233,#AA0000,#FFEEDD")
    assert {l["color"] for l in result["layers"]} == {"#112233", "#AA0000", "#FFEEDD"}


def test_cutout_layers_do_not_overlap(save, ticket, capsys):
    _, stacked = run(capsys, save(ticket), "--layers", "stacked")
    _, cutout = run(capsys, save(ticket, "b.png"), "--layers", "cutout")
    rendered = drawn(cutout)
    assert abs((rendered[..., 3] == 255).mean() - (drawn(stacked)[..., 3] == 255).mean()) < 0.01
    with open(cutout["svg"], encoding="utf-8") as handle:
        svg = handle.read()
    cream = next(l["layer"] for l in cutout["layers"] if close(l["color"], CREAM))
    single = svg[:svg.index("<g ")] + svg[svg.index(f'<g id="{cream}"'):].split("</g>")[0] + "</g></svg>"
    alone = render_svg(single, *cutout["input_size"])
    assert alone[250, 300, 3] == 0  # no cream under the red banner


def test_svg_has_no_background_shapes_or_embedded_rasters(save, ticket, capsys):
    _, result = run(capsys, save(ticket))
    with open(result["svg"], encoding="utf-8") as handle:
        svg = handle.read()
    assert "<rect" not in svg and "<image" not in svg


def test_outputs_are_written_and_not_overwritten(save, ticket, capsys):
    path = save(ticket)
    code, result = run(capsys, path)
    assert code == 0
    for key in ("svg", "report", "preview"):
        assert Image.open(result[key]) if key == "preview" else open(result[key]).read(1)
    code, result = run(capsys, path)
    assert code == 2 and "--force" in result["error"]
    code, _ = run(capsys, path, "--force")
    assert code == 0


def test_no_report_writes_only_svg(save, ticket, capsys):
    _, result = run(capsys, save(ticket), "--no-report")
    assert result["report"] is None and result["preview"] is None


def test_photo_is_rejected_with_exit_code_3(save, photo, capsys):
    code, result = run(capsys, save(photo))
    assert code == 3
    assert result["status"] == "error" and "suitable" in result["error"]


def test_unreadable_input_exits_2(tmp_path, capsys):
    bad = tmp_path / "bad.png"
    bad.write_text("not an image")
    code, result = run(capsys, bad)
    assert code == 2


def test_invalid_color_is_a_usage_error(save, ticket, capsys):
    with pytest.raises(SystemExit) as info:
        main([str(save(ticket)), "--background", "blue"])
    assert info.value.code == 2


def test_no_false_color_at_corners_of_dark_on_dark_boxes(save, capsys):
    """Sharpening a maroon box inside a black frame must not produce specks of a third, orange color."""
    image = Image.new("RGB", (600, 500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 240, 440), fill=(0, 0, 0))
    draw.rectangle((50, 50, 230, 430), fill=(121, 0, 0))
    draw.rectangle((300, 100, 560, 400), fill=(255, 125, 65))
    _, result = run(capsys, save(image))
    rgba = drawn(result)
    orange = (rgba[..., :3] == np.array(parse_hex(next(
        l["color"] for l in result["layers"] if close(l["color"], (255, 125, 65))
    )), dtype=np.uint8)).all(-1) & (rgba[..., 3] > 128)
    assert not orange[:, :260].any()
