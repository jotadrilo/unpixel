"""Draw each color layer of an SVG as its own plate, as a cutter or screen printer would see it.

Usage: python plates.py INPUT.svg OUTPUT.png
"""

import re
import sys

from PIL import Image

from unpixel.render import render_svg


def main(svg_path, out_path):
    svg = open(svg_path, encoding="utf-8").read()
    width, height = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
    groups = re.findall(r"<g id=.*?</g>\n", svg, flags=re.S)
    head = svg[: svg.index("<g id=")]
    scale = 500 / width
    gap = 16
    tile_h = round(height * scale)
    sheet = Image.new("RGB", ((500 + gap) * len(groups) - gap, tile_h), (255, 255, 255))
    for index, group in enumerate(groups):
        plate = Image.fromarray(render_svg(head + group + "</svg>", width, height, scale * 2))
        tile = Image.new("RGBA", plate.size, (232, 232, 232, 255))
        tile.alpha_composite(plate)
        sheet.paste(tile.convert("RGB").resize((500, tile_h), Image.LANCZOS), (index * (500 + gap), 0))
    sheet.save(out_path, optimize=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
