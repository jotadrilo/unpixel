import colorsys
import io
import json
import shlex

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from unpixel.cli import main
from unpixel.color import delta_e, parse_hex, srgb_to_lab
from unpixel.render import render_svg
from unpixel.ui import Style, stage

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


def test_photo_is_traced_and_not_refused(save, photo, capsys):
    code, result = run(capsys, save(photo))
    assert code == 0
    assert result["status"] == "ok" and result["layers"]
    assert open(result["svg"]).read(4) == "<svg"


def test_too_many_colors_are_reduced_to_the_palette_cap(save, capsys):
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    for i in range(20):
        hue = colorsys.hsv_to_rgb(i / 20, 0.5 + (i % 2) * 0.5, 0.55 + (i % 3) * 0.2)
        x, y = 20 + (i % 5) * 120, 20 + (i // 5) * 110
        draw.rectangle((x, y, x + 90, y + 80), fill=tuple(int(v * 255) for v in hue))
    code, result = run(capsys, save(image))
    assert code == 0
    assert len(result["layers"]) == 18  # of the 20 drawn: the engine drops colors close to others, with no warning


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


def test_transparency_is_decided_before_recoloring(save, stamp, capsys):
    _, first = run(capsys, save(stamp))
    white = [l["color"] for l in first["layers"] if close(l["color"], (255, 255, 255))][0]
    code, result = run(capsys, save(stamp, "again.png"), "--also-transparent", white, "--colors", "#F2F2F2")
    assert code == 0
    assert [l["color"] for l in result["layers"]] == ["#F2F2F2"]
    rgba = drawn(result)
    assert rgba[400, 400, 3] == 0  # the enclosed white is still removed
    assert tuple(rgba[200, 400, :3]) == (0xF2, 0xF2, 0xF2)  # the black ring became light
    assert not any("look like the background" in w for w in result["warnings"])  # judged on source colors


def test_removing_every_color_is_a_usage_error(save, no_outline, capsys):
    _, first = run(capsys, save(no_outline))
    only = first["layers"][0]["color"]
    code, result = run(capsys, save(no_outline, "again.png"), "--also-transparent", only)
    assert code == 2 and "every color" in result["error"]


def test_preview_background_is_used_and_stays_out_of_the_svg(save, ticket, capsys):
    _, result = run(capsys, save(ticket), "--preview-background", "#1C1C1E")
    assert result["preview_background"] == "#1C1C1E"
    assert Image.open(result["preview"]).convert("RGB").getpixel((3, 3)) == (0x1C, 0x1C, 0x1E)
    with open(result["svg"], encoding="utf-8") as handle:
        assert "1C1C1E" not in handle.read()


def test_output_directory_is_created(save, ticket, tmp_path, capsys):
    target = tmp_path / "new" / "folder" / "out.svg"
    code, result = run(capsys, save(ticket), "-o", target)
    assert code == 0 and target.exists() and result["preview"].endswith("out.preview.png")


def test_color_used_only_in_thin_strokes_is_kept(save, capsys):
    """Thin dark lines on a mid-tone panel have almost no flat pixels, and must keep their own color."""
    image = Image.new("RGB", (900, 700), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 800, 600), fill=(104, 110, 131))
    for y in range(160, 560, 40):
        draw.line((180, y, 720, y + 20), fill=(26, 29, 49), width=4)
    soft = image.filter(ImageFilter.GaussianBlur(0.8))
    _, result = run(capsys, save(soft))
    assert len(result["layers"]) == 2
    rgba = drawn(result)
    dark = next(l["color"] for l in result["layers"] if close(l["color"], (26, 29, 49), 25))
    is_dark = (rgba[..., :3] == np.array(parse_hex(dark), dtype=np.uint8)).all(-1) & (rgba[..., 3] > 128)
    assert is_dark.mean() > 0.01
    assert is_dark[:, 450].sum() >= 10 * 2  # every line still crosses the middle


def test_tiny_color_does_not_take_a_slot_from_a_real_one(save, capsys):
    image = Image.new("RGB", (1000, 800), (12, 18, 50))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 450, 700), fill=(204, 52, 7))
    draw.rectangle((550, 100, 900, 400), fill=(245, 149, 98))
    draw.rectangle((550, 450, 900, 700), fill=(253, 237, 170))
    draw.rectangle((20, 20, 60, 60), fill=(60, 200, 90))  # a tiny patch, unlike anything else
    _, result = run(capsys, save(image), "--background", "keep", "--colors", "4")
    assert len(result["layers"]) == 4
    for real in ((12, 18, 50), (204, 52, 7), (245, 149, 98), (253, 237, 170)):
        assert has_color(result, real)


def test_piped_output_has_no_escape_codes(save, stamp, capsys, monkeypatch):
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    code = main([str(save(stamp))])
    captured = capsys.readouterr()
    assert code == 0
    assert "\x1b[" not in captured.out + captured.err
    assert "SVG" in captured.out and "Background" in captured.out


def test_color_always_shows_swatches_and_a_thumbnail(save, stamp, capsys, monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    code = main([str(save(stamp)), "--color", "always"])
    out = capsys.readouterr().out
    assert code == 0
    assert "\x1b[48;2;" in out  # a real color behind its name
    assert "\u2580" in out  # the half-block miniature


def test_no_color_and_force_color_are_respected(save, stamp, capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    main([str(save(stamp))])
    assert "\x1b[" not in capsys.readouterr().out
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("FORCE_COLOR", "1")
    main([str(save(stamp, "b.png"))])
    assert "\x1b[" in capsys.readouterr().out


def test_json_stays_clean_with_color_forced(save, stamp, capsys):
    code = main([str(save(stamp)), "--json", "--color", "always"])
    captured = capsys.readouterr()
    assert code == 0
    assert "\x1b[" not in captured.out
    assert json.loads(captured.out)["status"] == "ok"


def test_warning_offers_a_complete_command_that_works(save, stamp, capsys, monkeypatch):
    path = save(stamp)
    main([str(path)])
    line = next(l for l in capsys.readouterr().err.splitlines() if "Run:" in l)
    command = shlex.split(line.split("Run:", 1)[1])
    assert command[0] == "unpixel" and "--also-transparent" in command and "--force" in command
    assert main(command[1:]) == 0
    assert "--also-transparent" not in capsys.readouterr().err


def test_failed_stage_ends_its_line_before_the_error():
    stream = io.StringIO()
    with pytest.raises(ValueError):
        with stage(Style(stream, "never"), "Finding colors", active=True):
            raise ValueError("boom")
    assert stream.getvalue().endswith("Finding colors\n\n")


def test_thumbnail_is_cropped_to_the_artwork(monkeypatch):
    monkeypatch.setenv("COLORTERM", "truecolor")
    rgba = np.zeros((1000, 1000, 4), dtype=np.uint8)
    rgba[450:550, 300:700] = (10, 20, 30, 255)
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    lines = Style(stream, "always").thumbnail(rgba)
    assert len(lines) < 12  # a wide, short drawing fills the width, not a square of empty margin
    assert len(lines[0].split("\u2580")) - 1 >= 60


def test_grey_uses_the_grey_ramp_without_truecolor(monkeypatch):
    monkeypatch.delenv("COLORTERM", raising=False)
    style = Style(io.StringIO(), "always")
    assert style._channel((150, 150, 150), 38).startswith("38;5;2")
    assert int(style._channel((150, 150, 150), 38).split(";")[2]) >= 232


def test_open_shows_the_preview(save, stamp, capsys, monkeypatch):
    opened = []
    monkeypatch.setattr("unpixel.cli.open_file", lambda path: opened.append(path) or True)
    _, result = run(capsys, save(stamp), "--open")
    assert opened == [result["preview"]]


def test_nothing_opens_without_the_flag(save, stamp, capsys, monkeypatch):
    opened = []
    monkeypatch.setattr("unpixel.cli.open_file", lambda path: opened.append(path) or True)
    run(capsys, save(stamp))
    assert opened == []


def test_failing_to_open_is_a_warning_and_the_svg_is_kept(save, stamp, capsys, monkeypatch):
    monkeypatch.setattr("unpixel.cli.open_file", lambda path: False)
    code, result = run(capsys, save(stamp), "--open")
    assert code == 0
    assert any("Could not open" in w for w in result["warnings"])
    assert open(result["svg"]).read(4) == "<svg"


def test_open_with_no_report_is_a_usage_error(save, stamp):
    with pytest.raises(SystemExit) as info:
        main([str(save(stamp)), "--open", "--no-report"])
    assert info.value.code == 2


def test_outline_lines_keeps_only_the_darkest_colors_shapes_in_black(save, ticket, capsys):
    code, result = run(capsys, save(ticket), "--outline", "lines")
    assert code == 0
    assert result["outline"] == "lines"
    assert len(result["layers"]) == 1
    assert result["layers"][0]["color"] == "#000000"
    assert not has_color(result, RED)
    assert not has_color(result, CREAM)
    rgba = drawn(result)
    assert rgba[5, 5, 3] == 0  # the page stays transparent
    assert (rgba[..., 3] == 0).mean() > 0.5  # filled areas are gone


def test_outline_edges_draws_a_line_where_flat_colors_meet(save, capsys):
    image = Image.new("RGB", (600, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 300, 300), fill=RED)
    draw.rectangle((300, 100, 500, 300), fill=NAVY)
    code, result = run(capsys, save(image), "--outline", "edges", "--outline-width", "4")
    assert code == 0
    assert len(result["layers"]) == 1
    assert result["layers"][0]["color"] == "#000000"
    rgba = drawn(result)
    assert rgba[200, 200, 3] == 0  # inside a fill: empty
    assert rgba[200, 400, 3] == 0
    assert rgba[200, 300, 3] > 0  # between the two colors: a line
    assert rgba[200, 100, 3] > 0  # between a color and the removed background: a line
    assert rgba[50, 50, 3] == 0  # the page stays transparent


def test_outline_lines_warns_when_the_darkest_color_is_a_fill(save, capsys):
    image = Image.new("RGB", (600, 400), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((100, 100, 500, 300), fill=NAVY)
    code, result = run(capsys, save(image), "--outline", "lines")
    assert code == 0
    assert any("--outline edges" in warning for warning in result["warnings"])


def test_outline_width_needs_edges(save, ticket):
    with pytest.raises(SystemExit) as stopped:
        main([str(save(ticket)), "--outline", "lines", "--outline-width", "3"])
    assert stopped.value.code == 2


@pytest.mark.parametrize("mode", ["lines", "edges"])
def test_outline_color_sets_the_lines_color(save, ticket, capsys, mode):
    code, result = run(capsys, save(ticket), "--outline", mode, "--outline-color", "#E6007E")
    assert code == 0
    assert [layer["color"] for layer in result["layers"]] == ["#E6007E"]
    assert 'fill="#E6007E"' in open(result["svg"], encoding="utf-8").read()


def test_outline_color_needs_outline(save, ticket):
    with pytest.raises(SystemExit) as stopped:
        main([str(save(ticket)), "--outline-color", "#E6007E"])
    assert stopped.value.code == 2


def test_outline_color_must_be_a_color(save, ticket):
    with pytest.raises(SystemExit) as stopped:
        main([str(save(ticket)), "--outline", "lines", "--outline-color", "pink"])
    assert stopped.value.code == 2
