"""Synthetic artwork, built soft on purpose to imitate real upscaled or anti-aliased sources."""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

WHITE, CREAM, NAVY, RED = (255, 255, 255), (253, 243, 226), (4, 22, 46), (187, 16, 15)


def soften(image, seed=0):
    """Downscale-free softening plus mild noise, like a JPEG or an AI upscale."""
    soft = image.filter(ImageFilter.GaussianBlur(1.2))
    noise = np.random.default_rng(seed).normal(0, 1.5, (soft.height, soft.width, 3))
    return Image.fromarray(np.clip(np.asarray(soft, dtype=np.float32) + noise, 0, 255).astype(np.uint8))


@pytest.fixture
def save(tmp_path):
    def _save(image, name="art.png"):
        path = tmp_path / name
        image.save(path)
        return path

    return _save


@pytest.fixture
def ticket():
    """Cream card with a navy outline on white, a red banner, and a thin cream line inside it."""
    image = Image.new("RGB", (1000, 500), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 40, 960, 460), 40, fill=CREAM, outline=NAVY, width=12)
    draw.rectangle((200, 180, 800, 320), fill=RED)
    draw.line((500, 180, 500, 320), fill=CREAM, width=5)
    draw.ellipse((90, 90, 170, 170), fill=NAVY)
    return soften(image)


@pytest.fixture
def stamp():
    """Black ring on white: the hole in the ring matches the background but is enclosed."""
    image = Image.new("RGB", (800, 800), WHITE)
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 150, 650, 650), fill=(0, 0, 0))
    draw.ellipse((300, 300, 500, 500), fill=WHITE)
    return soften(image)


@pytest.fixture
def no_outline():
    """Cream directly on white with no line between them."""
    image = Image.new("RGB", (800, 600), WHITE)
    ImageDraw.Draw(image).rectangle((150, 150, 650, 450), fill=CREAM)
    return soften(image)


@pytest.fixture
def photo():
    """Smooth gradients with noise: nothing here is flat color."""
    y, x = np.mgrid[0:600, 0:800]
    arr = np.stack([x / 800 * 255, y / 600 * 255, (x + y) / 1400 * 255], -1)
    arr += np.random.default_rng(1).normal(0, 12, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
