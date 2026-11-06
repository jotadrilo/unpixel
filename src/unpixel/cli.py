"""Command line interface. Exit codes: 0 ok, 2 bad usage or input, 3 image not suitable."""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .color import parse_hex, to_hex
from .outline import apply_outline
from .report import contrast_background, verify, write_preview, write_report
from .segment import InvalidRequest, UnsuitableImage, segment
from .ui import Style, open_file, print_error, print_header, print_summary, print_warnings, stage
from .vectorize import build_svg

Image.MAX_IMAGE_PIXELS = None


# Below this, a hole in the artwork is a pinhole at a junction: known, and no reason to send anyone to the preview.
VISIBLE_HOLE_PIXELS = 20

@dataclass
class Options:
    background: str = "auto"
    background_rgb: tuple[int, int, int] | None = None
    also_transparent: list[tuple[int, int, int]] = field(default_factory=list)
    color_count: int | None = None
    palette: list[tuple[int, int, int]] = field(default_factory=list)
    detail: str = "medium"
    layers: str = "stacked"
    outline: str | None = None
    outline_width: float = 2.0
    outline_color: tuple[int, int, int] = (0, 0, 0)
    engine: str = "classic"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unpixel",
        description="Turn flat-color raster artwork (logos, stickers, illustrations) into layered SVG, "
        "with the background made transparent. Writes INPUT.svg, plus INPUT.report.html and "
        "INPUT.preview.png so the result can be checked by eye.",
        epilog="Exit codes: 0 success; 2 bad arguments, unreadable input or existing output; "
        "3 image unsuitable (photo, gradients). Warnings do not change the exit code.",
    )
    parser.add_argument("input", type=Path, help="PNG, JPEG, WebP or any format Pillow reads")
    parser.add_argument("--colors", metavar="SPEC",
                        help="number of final colors (e.g. 3), or an exact comma-separated palette "
                             "(e.g. '#04162E,#BB100F'): each detected color becomes the closest one listed, so a single "
                             "color recolors everything. The transparent background does not count. Default: detect")
    parser.add_argument("--background", default="auto", metavar="MODE",
                        help="'auto' removes the uniform color touching the image border; 'keep' removes nothing; "
                             "'#RRGGBB' removes that color where it touches the border. Default: auto")
    parser.add_argument("--also-transparent", action="append", default=[], metavar="#RRGGBB",
                        help="also remove this color inside the artwork, such as white inside letters. Thin marks that "
                             "blend into it go too. Use the exact value from the warning or 'layers'. Repeatable")
    parser.add_argument("--layers", choices=["stacked", "cutout"], default="stacked",
                        help="'stacked' overlaps colors slightly so no seams show (print, screen); 'cutout' makes "
                             "colors never overlap (plotters, screen printing). Default: stacked")
    parser.add_argument("--detail", choices=["low", "medium", "high"], default="medium",
                        help="'low' if edges look jagged, 'high' if thin lines or small shapes get lost. Default: medium")
    parser.add_argument("--outline", choices=["lines", "edges"], metavar="MODE",
                        help="keep only lines. 'lines' keeps the darkest color's own shapes, for artwork "
                             "that already has outlines; 'edges' draws a line wherever two colors meet, for flat "
                             "artwork with none. Default: off")
    parser.add_argument("--outline-width", type=float, metavar="PIXELS",
                        help="line width for --outline edges, in source pixels. Default: 2")
    parser.add_argument("--outline-color", metavar="#RRGGBB",
                        help="line color for --outline. Default: #000000")
    parser.add_argument("--engine", choices=["classic", "new"], default="classic",
                        help="'new' tries the prototype color and contour engine: it never refuses an image, and shares "
                             "one curve per wall. Default: classic")
    parser.add_argument("--preview-background", metavar="#RRGGBB",
                        help="color to show the result on in the preview and report, such as the surface it will "
                             "go on. It is not added to the SVG. Default: a color contrasting with the artwork")
    parser.add_argument("-o", "--output", type=Path, metavar="FILE.svg", help="output path. Default: next to the input")
    parser.add_argument("--force", action="store_true", help="overwrite existing output files")
    parser.add_argument("--no-report", action="store_true", help="write only the SVG, without report or preview")
    parser.add_argument("--open", action="store_true", help="open the preview in your default image viewer when done")
    parser.add_argument("--json", action="store_true", help="print a machine-readable result on stdout")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                        help="color in terminal output. 'auto' uses it on a terminal, unless NO_COLOR is set. Default: auto")
    parser.add_argument("--version", action="version", version=f"unpixel {__version__}")
    return parser


def _options(args, parser) -> Options:
    options = Options(detail=args.detail, layers=args.layers, outline=args.outline, engine=args.engine)
    if args.outline_width is not None:
        if args.outline != "edges":
            parser.error("--outline-width needs --outline edges")
        if args.outline_width <= 0:
            parser.error("--outline-width must be above 0")
        options.outline_width = args.outline_width
    if args.outline_color is not None and not args.outline:
        parser.error("--outline-color needs --outline")
    try:
        if args.outline_color is not None:
            options.outline_color = parse_hex(args.outline_color)
        if args.background not in ("auto", "keep"):
            options.background_rgb = parse_hex(args.background)
            options.background = "color"
        else:
            options.background = args.background
        options.also_transparent = [parse_hex(v) for v in args.also_transparent]
        if args.colors:
            if args.colors.strip().isdigit():
                options.color_count = int(args.colors)
                if options.color_count < 1:
                    parser.error("--colors must be at least 1")
            else:
                options.palette = [parse_hex(v) for v in args.colors.split(",")]
    except ValueError as error:
        parser.error(str(error))
    return options


def _fail(args, code: int, message: str) -> int:
    if args.json:
        print(json.dumps({"status": "error", "exit_code": code, "error": message}, indent=2))
    print_error(Style(sys.stderr, args.color), message)
    return code


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    parser = build_parser()
    args = parser.parse_args(argv)
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    options = _options(args, parser)
    if args.open and args.no_report:
        parser.error("--open needs the preview, which --no-report turns off")

    svg_path = args.output or args.input.with_suffix(".svg")
    stem = svg_path.with_suffix("")
    report_path = stem.parent / f"{stem.name}.report.html"
    preview_path = stem.parent / f"{stem.name}.preview.png"
    outputs = [svg_path] + ([] if args.no_report else [report_path, preview_path])
    existing = [str(p) for p in outputs if p.exists()]
    if existing and not args.force:
        return _fail(args, 2, f"output exists, pass --force to overwrite: {', '.join(existing)}")
    if svg_path.suffix.lower() != ".svg":
        return _fail(args, 2, f"output must end in .svg: {svg_path}")
    preview_color = None
    if args.preview_background:
        try:
            preview_color = parse_hex(args.preview_background)
        except ValueError as error:
            parser.error(str(error))
    try:
        with Image.open(args.input) as opened:
            rgba = opened.convert("RGBA")
    except (OSError, ValueError) as error:
        return _fail(args, 2, f"cannot read {args.input}: {error}")
    flattened = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flattened.alpha_composite(rgba)  # transparent input pixels act as a white background
    source = np.asarray(flattened.convert("RGB"))
    height, width = source.shape[:2]

    out, err = Style(sys.stdout, args.color), Style(sys.stderr, args.color)
    show_progress = not args.json and bool(getattr(sys.stderr, "isatty", lambda: False)())
    if not args.json:
        print_header(out, args.input.name, width, height, spaced=show_progress)
    try:
        with stage(err, "Finding colors and background", show_progress):
            context = None
            if options.engine == "new":
                from .engine.adapter import segment_new  # only then: the classic path stays as it was

                seg, context = segment_new(source, options)
            else:
                seg = segment(source, options)
    except UnsuitableImage as error:
        return _fail(args, 3, f"image not suitable for flat-color tracing: {error}")
    except InvalidRequest as error:
        return _fail(args, 2, str(error))

    if options.outline:
        seg = apply_outline(seg, options.outline, options.outline_width, options.outline_color)

    with stage(err, "Tracing shapes", show_progress):
        if context is not None:
            from .engine.adapter import trace_new

            svg, layers = trace_new(seg, context, width, height, options.layers, html.escape(args.input.stem),
                                    outlined=bool(options.outline))
        else:
            svg, layers = build_svg(seg.labels, seg.colors, width, height, options.layers, seg.speck_area,
                                    html.escape(args.input.stem))
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")

    with stage(err, "Checking the result", show_progress):
        metrics, rendered, hotspots = verify(svg, seg, width, height)
    background = preview_color or contrast_background(seg.colors)
    if not args.no_report:
        with stage(err, "Writing preview and report", show_progress):
            write_preview(svg, width, height, background, preview_path)
            write_report(source, svg, seg, metrics, hotspots, layers, background, args.input.name, report_path)
    if options.engine == "new":
        # Shapes share their walls, so a trace of see-through along one is antialiasing. Only a real hole counts.
        if metrics["opaque_pixels_in_background"] or metrics["holes_in_artwork"] >= VISIBLE_HOLE_PIXELS:
            seg.warnings.append("Transparency does not fully match the expected background; inspect the preview.")
        elif options.layers == "cutout" and metrics["transparent_pixels_in_artwork"]:
            seg.warnings.append(
                "Cutout layers meet edge to edge, so a faint seam can show where colors meet. Use the default, "
                "stacked, unless colors must not overlap."
            )
    elif metrics["opaque_pixels_in_background"] or metrics["transparent_pixels_in_artwork"]:
        if options.layers == "cutout" and not metrics["opaque_pixels_in_background"]:
            seg.warnings.append(
                f"Cutout layers leave tiny gaps where colors meet ({metrics['transparent_percent']}% of the image is "
                "see-through), because each shape is curved separately. Use the default, stacked, unless colors "
                "must not overlap."
            )
        else:
            seg.warnings.append("Transparency does not fully match the expected background; inspect the preview.")

    if args.open and not open_file(str(preview_path)):
        seg.warnings.append(f"Could not open the preview automatically. It is at {preview_path}.")

    result = {
        "status": "ok",
        "svg": str(svg_path),
        "report": None if args.no_report else str(report_path),
        "preview": None if args.no_report else str(preview_path),
        "input_size": [width, height],
        "background_removed": seg.background,
        "working_scale": round(seg.scale, 2),
        "layers_mode": options.layers,
        "outline": options.outline,
        "layers": layers,
        "metrics": metrics,
        "preview_background": to_hex(background),
        "warnings": seg.warnings,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_summary(out, result, rendered, time.monotonic() - started)
        print_warnings(err, seg.warnings, raw_arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
