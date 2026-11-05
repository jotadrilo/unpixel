"""Show the same enlarged crop of an image and of several SVGs, side by side.

Usage: python compare.py OUTPUT.png LEFT,TOP,RIGHT,BOTTOM INPUT_IMAGE A.svg [B.svg ...]
"""

import re
import sys

from PIL import Image

from unpixel.render import composite, render_svg

ZOOM = 3


def main(out_path, box_text, source, *svgs):
    box = tuple(int(v) for v in box_text.split(","))
    tiles = [Image.open(source).convert("RGB").crop(box).resize(
        ((box[2] - box[0]) * ZOOM, (box[3] - box[1]) * ZOOM), Image.LANCZOS)]
    for path in svgs:
        svg = open(path, encoding="utf-8").read()
        width, height = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
        big = composite(render_svg(svg, width, height, ZOOM * 2), (255, 255, 255))
        crop = big.crop(tuple(v * ZOOM * 2 for v in box))
        tiles.append(crop.resize(tiles[0].size, Image.LANCZOS))
    gap = 16
    sheet = Image.new("RGB", (sum(t.width for t in tiles) + gap * (len(tiles) - 1), tiles[0].height), (200, 200, 200))
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index * (tile.width + gap), 0))
    sheet.save(out_path, optimize=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
