"""Shared pixel checks for saved artwork. Passing is necessary, not sufficient.

Body-review evidence and model qualification remain separate requirements.
The cache is keyed by actual image bytes and check code, never by a filename.
"""
import hashlib
from pathlib import Path

import cv2
import numpy as np

import cutout

_CACHE = {}


def pixel_faults(path: Path) -> tuple[str, ...]:
    try:
        raw = path.read_bytes()
    except OSError:
        return ("artwork cannot be read",)
    return pixel_faults_bytes(raw)


def pixel_faults_bytes(raw: bytes) -> tuple[str, ...]:
    """Check the exact encoded file, including before it is first written."""
    try:
        version = hashlib.sha256(Path(cutout.__file__).read_bytes()
                                 + Path(__file__).read_bytes()
                                 + cv2.__version__.encode() + np.__version__.encode()).hexdigest()
    except OSError:
        return ("check code cannot be read",)
    key = (hashlib.sha256(raw).hexdigest(), version)
    if key in _CACHE:
        return _CACHE[key]
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("artwork must be a PNG",)
    try:
        art = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    except (ValueError, cv2.error):
        return ("artwork cannot be decoded",)
    if art is None or art.ndim != 3 or art.shape[2] != 4:
        return ("artwork must be a readable RGBA image",)
    alpha = art[:, :, 3:4].astype(np.float32) / 255
    flat = (art[:, :, :3] * alpha + np.array([255, 0, 255]) * (1-alpha)).astype(np.uint8)
    faults = []
    for check in (
        lambda: cutout.assert_no_text(flat, "artwork"),
        lambda: cutout.assert_on_palette(art, "artwork"),
        lambda: cutout.assert_has_pupils(art, "artwork"),
        lambda: cutout.qa(art, src_shape=art.shape[:2], allow_detached=True, strict_framing=False),
    ):
        try:
            check()
        except (cutout.QAFailure, ValueError, cv2.error) as exc:
            faults.append(str(exc))
    _CACHE[key] = tuple(faults)
    return _CACHE[key]
