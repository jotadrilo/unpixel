"""Terminal output: real color swatches, a miniature of the result, progress and copyable hints.

Color follows the usual conventions: on for a terminal, off when piped, off with NO_COLOR, on with
FORCE_COLOR, and --color overrides them all. --json never goes through here.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import time
from contextlib import contextmanager

import numpy as np
from PIL import Image

from .color import parse_hex

BAR_WIDTH = 16
MAX_THUMB_COLUMNS = 72
MAX_THUMB_ROWS = 24
CHECKER = ((150, 150, 150), (168, 168, 168))  # close mid-greys: black and white art both show, and it stays quiet
CHECKER_SQUARE = 6  # half-block pixels


def color_enabled(mode: str, stream) -> bool:
    if mode != "auto":
        return mode == "always"
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"


class Style:
    def __init__(self, stream, mode: str = "auto"):
        self.stream = stream
        self.enabled = color_enabled(mode, stream)
        self.truecolor = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        self.unicode = encoding.startswith("utf")

    def _sgr(self, code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._sgr("1", text)

    def dim(self, text: str) -> str:
        return self._sgr("2", text)

    def green(self, text: str) -> str:
        return self._sgr("32", text)

    def yellow(self, text: str) -> str:
        return self._sgr("33", text)

    def red(self, text: str) -> str:
        return self._sgr("1;31", text)

    def cyan(self, text: str) -> str:
        return self._sgr("36", text)

    def symbol(self, fancy: str, plain: str) -> str:
        return fancy if self.unicode else plain

    def _channel(self, rgb, layer: int) -> str:
        if self.truecolor:
            return f"{layer};2;{rgb[0]};{rgb[1]};{rgb[2]}"
        if max(rgb) - min(rgb) < 12:  # the grey ramp avoids false tints from the coarse color cube
            grey = sum(rgb) / 3
            if grey < 8:
                return f"{layer};5;16"
            if grey > 248:
                return f"{layer};5;231"
            return f"{layer};5;{232 + int(round((grey - 8) / 247 * 23))}"
        r, g, b = (int(round(v / 255 * 5)) for v in rgb)
        return f"{layer};5;{16 + 36 * r + 6 * g + b}"

    def swatch(self, hex_color: str) -> str:
        """The color's own name printed on the color, readable even when it matches the terminal."""
        if not self.enabled:
            return hex_color
        rgb = parse_hex(hex_color)
        luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        ink = (0, 0, 0) if luminance > 140 else (255, 255, 255)
        return f"\x1b[{self._channel(rgb, 48)};{self._channel(ink, 38)}m {hex_color} \x1b[0m"

    def strip(self, parts: list[tuple[str | None, float]], width: int = 48) -> str:
        """One line showing the image's color make-up. None is the transparent part."""
        if not self.enabled or not self.unicode:
            return ""
        total = sum(share for _, share in parts) or 1.0
        out = []
        for hex_color, share in parts:
            cells = max(1, round(share / total * width)) if share > 0 else 0
            if hex_color is None:
                out.append(self.dim("░" * cells))
            else:
                out.append(f"\x1b[{self._channel(parse_hex(hex_color), 38)}m{'█' * cells}\x1b[0m")
        return "".join(out)

    def thumbnail(self, rgba: np.ndarray) -> list[str]:
        """Draw the result with half-block characters, with transparency as a checkerboard."""
        if not self.enabled or not self.unicode:
            return []
        # Empty margins only waste the few cells available.
        ys, xs = np.nonzero(rgba[..., 3] > 0)
        if ys.size:
            pad = max(2, max(rgba.shape[:2]) // 100)
            rgba = rgba[
                max(0, ys.min() - pad) : ys.max() + pad + 1,
                max(0, xs.min() - pad) : xs.max() + pad + 1,
            ]
        terminal = shutil.get_terminal_size((80, 24)).columns
        columns = min(MAX_THUMB_COLUMNS, max(10, terminal - 4))
        height, width = rgba.shape[:2]
        ratio = min(columns / width, MAX_THUMB_ROWS * 2 / height)
        size = (max(1, round(width * ratio)), max(2, 2 * round(height * ratio / 2)))
        small = Image.fromarray(rgba).convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
        rows_index, columns_index = np.indices((size[1], size[0]))
        tile = rows_index // CHECKER_SQUARE + columns_index // CHECKER_SQUARE
        board = np.array(CHECKER, dtype=np.uint8)[tile % 2]
        pixels = np.asarray(small, dtype=np.float32)
        alpha = pixels[..., 3:] / 255.0
        shown = (pixels[..., :3] * alpha + board * (1 - alpha)).round().astype(np.uint8)
        lines = []
        for y in range(0, size[1] - 1, 2):
            cells = []
            for x in range(size[0]):
                top, bottom = shown[y, x].tolist(), shown[y + 1, x].tolist()
                cells.append(f"\x1b[{self._channel(top, 38)};{self._channel(bottom, 48)}m▀")
            lines.append("".join(cells) + "\x1b[0m")
        return lines


@contextmanager
def stage(style: Style, label: str, active: bool):
    """Show what a slow step is doing, and how long it took. Silent unless on a terminal."""
    if not active:
        yield
        return
    start = time.monotonic()
    style.stream.write(f"  {style.dim(style.symbol('…', '-'))} {label}")
    style.stream.flush()
    try:
        yield
    except BaseException:
        style.stream.write(f"\r\x1b[2K  {style.red(style.symbol('✗', 'x'))} {label}\n\n")
        style.stream.flush()
        raise
    took = time.monotonic() - start
    mark = style.green(style.symbol("✓", "ok"))
    style.stream.write(f"\r\x1b[2K  {mark} {label} {style.dim(f'{took:.1f}s')}\n")
    style.stream.flush()


def retry_command(warning: str, argv: list[str]) -> str | None:
    """If a warning names a flag to add, build the full command to run next."""
    found = re.search(r"add (--[\w-]+) '([^']+)'", warning)
    if not found:
        return None
    kept: list[str] = []
    skip = False
    for token in argv:
        if skip:
            skip = False
        elif token == "--color":
            skip = True
        elif token != "--json" and not token.startswith("--color="):
            kept.append(token)
    command = ["unpixel", *kept, found.group(1), found.group(2)]
    if "--force" not in command:
        command.append("--force")
    return shlex.join(command)


def print_header(style: Style, name: str, width: int, height: int, spaced: bool) -> None:
    title = style.bold(name)
    size = f"{width} {style.symbol(chr(215), 'x')} {height} px"
    print(f"\n  {style.cyan(style.bold('unpixel'))} {style.dim(style.symbol('·', '-'))} {title} {style.dim(size)}",
          file=style.stream)
    if spaced:
        print(file=style.stream)


def print_summary(style: Style, result: dict, rgba: np.ndarray, elapsed: float) -> None:
    write = lambda text="": print(text, file=style.stream)  # noqa: E731
    metrics = result["metrics"]
    layers = result["layers"]
    clear = metrics["transparent_percent"]

    thumbnail = style.thumbnail(rgba)
    if thumbnail:
        write()
        for line in thumbnail:
            write(f"  {line}")
    strip = style.strip([(l["color"], l["area_percent"]) for l in layers] + [(None, clear)])
    if strip:
        write()
        write(f"  {strip}")

    write()
    count = len(layers)
    write(f"  {style.bold(f'{count} color' + ('' if count == 1 else 's'))}")
    full, empty = style.symbol("█", "#"), style.symbol("░", ".")
    largest = max([l["area_percent"] for l in layers] + [0.1])
    for layer in layers:
        share = layer["area_percent"]
        filled = max(1, round(share / largest * BAR_WIDTH))
        bar = style.dim(full * filled + empty * (BAR_WIDTH - filled))
        shapes = f"{layer['shapes']} shape" + ("" if layer["shapes"] == 1 else "s")
        write(f"    {style.swatch(layer['color'])}  {bar} {share:>5.1f}%  {style.dim(shapes)}")

    write()
    if result["background_removed"]:
        write(f"  {style.bold('Background')}  {style.swatch(result['background_removed'])} removed, "
              f"{clear:.1f}% of the image is now transparent")
    else:
        write(f"  {style.bold('Background')}  kept")

    write()
    write(f"  {style.bold('Files')}")
    write(f"    SVG      {style.cyan(result['svg'])}")
    if result["preview"]:
        note = style.dim(f"on {result['preview_background']}, not part of the SVG")
        write(f"    Preview  {style.cyan(result['preview'])}  {note}")
        write(f"    Report   {style.cyan(result['report'])}  {style.dim('original next to result')}")
    write()
    write(f"  {style.green(style.symbol('✓', 'ok'))} {style.bold('Done')} {style.dim(f'in {elapsed:.1f}s')}")
    write()


def print_warnings(style: Style, warnings: list[str], argv: list[str]) -> None:
    for warning in warnings:
        print(f"  {style.yellow(style.bold('Warning:'))} {warning}", file=style.stream)
        command = retry_command(warning, argv)
        if command:
            print(f"    {style.dim('Run:')} {style.cyan(command)}", file=style.stream)
    if warnings:
        print(file=style.stream)


def print_error(style: Style, message: str) -> None:
    print(f"{style.dim('unpixel:')} {style.red('error:')} {message}", file=style.stream)


