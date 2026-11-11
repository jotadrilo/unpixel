import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from unpixel.quality import assess, warning


def artwork(size=(1200, 800)):
    """Flat shapes with crisp edges and fine lines, drawn at their own size."""
    im = Image.new("RGB", size, (250, 250, 248))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(3)
    for _ in range(120):
        x, y = rng.integers(0, size[0]), rng.integers(0, size[1])
        r = int(rng.integers(6, 60))
        color = tuple(int(c) for c in rng.integers(0, 255, 3))
        d.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(20, 20, 20), width=2)
    for i in range(0, size[0], 37):
        d.line([i, 0, i + 200, size[1]], fill=(30, 30, 30), width=1)
    return im


def rgb(im):
    return np.asarray(im.convert("RGB"))


def test_artwork_at_its_own_size_is_ok():
    assert assess(rgb(artwork()), "hard")["verdict"] == "ok"


def test_jpeg_grid_is_not_an_enlargement(tmp_path):
    path = tmp_path / "art.jpg"
    artwork().save(path, quality=15)
    assert assess(rgb(Image.open(path)), "hard")["verdict"] == "ok"


def test_a_small_image_is_low_resolution():
    small = artwork().resize((300, 200), Image.LANCZOS)
    q = assess(rgb(small), "hard")
    assert q["verdict"] == "low_resolution"
    assert "300×200" in warning(q, 300, 200)


def test_an_image_enlarged_with_smoothing_is_upscaled():
    soft = artwork().resize((300, 200), Image.BILINEAR).resize((1200, 800), Image.BICUBIC)
    assert assess(rgb(soft), "soft")["verdict"] == "upscaled"


def test_an_image_enlarged_into_soft_blocks_and_sharpened_gives_its_factor():
    """Like a small logo enlarged 6 times, then smoothed, sharpened and saved as JPEG."""
    enlarged = artwork().resize((200, 133), Image.LANCZOS).resize((1200, 798), Image.NEAREST)
    enlarged = enlarged.filter(ImageFilter.GaussianBlur(1.5)).filter(ImageFilter.UnsharpMask(radius=2, percent=200))
    q = assess(rgb(enlarged), "soft")
    assert q["verdict"] == "upscaled" and abs(q["factor"] - 6) < 0.3
    assert abs(q["source_size"][0] - 200) <= 2 and abs(q["source_size"][1] - 133) <= 2
    assert "enlarged from a smaller one (about " in warning(q, 1200, 798)


def test_pixel_blocks_are_pixelated_whatever_the_measure():
    q = assess(rgb(artwork()), "pixel", block=8)
    assert q == {"verdict": "pixelated", "block": 8}
    assert "8-pixel blocks" in warning(q, 1200, 800)


def test_a_flat_or_tiny_image_is_not_judged():
    assert assess(np.full((600, 900, 3), 200, np.uint8), "soft") == {"verdict": "ok"}
    assert assess(np.full((1, 1, 3), 200, np.uint8), "soft")["verdict"] == "low_resolution"
