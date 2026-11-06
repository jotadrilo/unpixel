"""Color helpers. All perceptual distances are CIE76 delta-E in Lab space."""

from __future__ import annotations

import numpy as np

_M = np.array(
    [[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]],
    dtype=np.float32,
)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)


import os as _os
_THREADS = int(_os.environ.get("UNPIXEL_THREADS", "1"))


def _pmap(fn, jobs):
    if _THREADS <= 1:
        return [fn(j) for j in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(_THREADS) as ex:
        return list(ex.map(fn, jobs))


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB values in 0..255, shape (..., 3), to float32 Lab."""
    arr = np.asarray(rgb)
    if arr.ndim == 3 and arr.shape[0] > 256:
        out = np.empty(arr.shape, dtype=np.float32)

        def work(y):
            out[y:y + 256] = srgb_to_lab(arr[y:y + 256])

        _pmap(work, range(0, arr.shape[0], 256))
        return out
    c = np.asarray(rgb, dtype=np.float32) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    t = (c @ _M.T) / _WHITE
    f = np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16.0 / 116.0)
    return np.stack(
        [116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]), 200.0 * (f[..., 1] - f[..., 2])],
        axis=-1,
    ).astype(np.float32)


def delta_e(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = np.asarray(a) - np.asarray(b)
    return np.sqrt(d[..., 0] * d[..., 0] + d[..., 1] * d[..., 1] + d[..., 2] * d[..., 2])


def parse_hex(value: str) -> tuple[int, int, int]:
    """Parse '#RRGGBB' or 'RRGGBB'. Raises ValueError on anything else."""
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a #RRGGBB color: {value!r}")
    return int(text[:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def to_hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"
