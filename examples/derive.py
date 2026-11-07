"""Make the example inputs that are damaged on purpose, from the battery's images.

The battery holds clean artwork, but some use cases need a small, grainy, pixelated or watermarked source. These are
built here, so that build.sh can remake them and CREDITS.md can say exactly what they are.

Usage: python derive.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

CHEF = Image.open("../battery/chef.png").convert("RGB")
AXOLOTL = Image.open("axolotl/input.png").convert("RGB")


def scaled(image, width, resample=Image.LANCZOS):
    return image.resize((width, round(image.height * width / image.width)), resample)


def small():
    """A logo saved small, as JPEG, like one taken from an old website."""
    Path("small").mkdir(exist_ok=True)
    scaled(CHEF, 480, Image.BICUBIC).save("small/chef-480.jpg", quality=45)
    scaled(CHEF, 220, Image.BICUBIC).save("small/chef-220.jpg", quality=35)


def grain():
    """Strong noise over the whole image, past the point where unpixel smooths it first."""
    Path("grain").mkdir(exist_ok=True)
    base = scaled(CHEF, 700)
    noise = np.random.default_rng(7).normal(0, 30, (base.height, base.width, 3))
    Image.fromarray((np.asarray(base, float) + noise).clip(0, 255).astype("uint8")).save("grain/input.png", optimize=True)


def pixel_art():
    """The mascot on a grid of 176 blocks across, each 6 px wide, in its own ten colors."""
    Path("pixel-art").mkdir(exist_ok=True)
    palette = np.array(
        [
            (0xFD, 0xFD, 0xFD), (0xFF, 0xFF, 0xFF), (0x1C, 0x15, 0x2B), (0x0E, 0xBC, 0xAD), (0x0A, 0x9F, 0x93),
            (0xFB, 0xBD, 0x28), (0xF9, 0x9D, 0x19), (0xFC, 0xBB, 0xCE), (0xF7, 0x4C, 0x82), (0x87, 0x5C, 0xEF),
        ],
        float,
    )
    blocks = np.asarray(scaled(AXOLOTL.crop((340, 20, 1080, 750)), 176, Image.NEAREST), float)
    nearest = ((blocks[..., None, :] - palette) ** 2).sum(-1).argmin(-1)
    image = Image.fromarray(palette[nearest].astype("uint8"))
    image.resize((image.width * 6, image.height * 6), Image.NEAREST).save("pixel-art/input.png", optimize=True)


def watermark():
    """A repeated diagonal SAMPLE at three strengths, added for this project."""
    Path("watermark").mkdir(exist_ok=True)
    base = scaled(CHEF, 1000).convert("RGBA")
    font = ImageFont.load_default(size=64)
    for name, alpha in (("faint", 10), ("medium", 40), ("strong", 110)):
        layer = Image.new("RGBA", (base.width * 2, base.height * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for row, y in enumerate(range(0, layer.height, 190)):
            for x in range(-200 + row % 2 * 170, layer.width, 340):
                draw.text((x, y), "SAMPLE", font=font, fill=(60, 60, 60, alpha))
        left, top = base.width // 2, base.height // 2
        layer = layer.rotate(24, resample=Image.BICUBIC).crop((left, top, left + base.width, top + base.height))
        Image.alpha_composite(base, layer).convert("RGB").save(f"watermark/{name}.png", optimize=True)


if __name__ == "__main__":
    small()
    grain()
    pixel_art()
    watermark()
