#!/usr/bin/env python3
"""
upscale regression. No network, no key, no model — this is cv2 and numpy only.

Four things are worth locking here, in order of what they would cost:

  1 · DETERMINISM. The whole reason this module hand-rolls a quantiser instead
      of calling cv2.kmeans is that kmeans initialises randomly, so the same
      pose would flatten to slightly different colours on every run and no two
      builds of the same deck would be byte-identical. That property is invisible
      until somebody diffs two builds, so it is a test.

  2 · THE THIN BITS. Silly's tail is a thin green line with a black tuft and his
      ears are pointed. Re-steepening alpha is exactly the operation that eats
      those, and it eats them quietly — the contact sheet still looks fine at
      220 px a tile. The area check is the guard.

  3 · THAT IT IS ACTUALLY AN IMPROVEMENT. The module claims two things over a
      plain resize: a narrower alpha ramp and flatter interiors. Both are
      measurable, so both are asserted against a naive INTER_LANCZOS4 resize of
      the same input rather than against a remembered number.

  4 · THAT THE REAL LIBRARY SURVIVES. Synthetic fixtures agree with whatever the
      author was thinking. The 180 poses on disk do not.
"""
import pathlib
import sys

import cv2
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import upscale as U  # noqa: E402

LIBRARY = ROOT / "mascot" / "library"


# ─────────────────────────── helpers ─────────────────────────────────────────

# Silly's identity colours, in BGR, from CHARACTER.md.
GREEN = (90, 150, 60)
DARK_GREEN = (55, 105, 35)
CREAM = (170, 210, 250)
BLACK = (20, 20, 20)
WHITE = (250, 250, 250)


def donkey(size: int = 120) -> np.ndarray:
    """A stand-in with the features the real poses have and the module must keep:
    several distinct fills, a thin tail, a pointed ear, and a matted alpha edge
    with the same ~1px Gaussian feather cutout.py leaves behind."""
    bgr = np.zeros((size, size, 3), np.uint8)
    mask = np.zeros((size, size), np.uint8)

    def blob(pts_or_centre, colour, *, ellipse=None, poly=None, line=None):
        if ellipse is not None:
            cv2.ellipse(bgr, pts_or_centre, ellipse, 0, 0, 360, colour, -1)
            cv2.ellipse(mask, pts_or_centre, ellipse, 0, 0, 360, 255, -1)
        elif poly is not None:
            cv2.fillPoly(bgr, [poly], colour)
            cv2.fillPoly(mask, [poly], 255)
        elif line is not None:
            cv2.line(bgr, line[0], line[1], colour, line[2])
            cv2.line(mask, line[0], line[1], 255, line[2])

    c = size // 2
    # head + body
    blob((c, int(size * 0.36)), GREEN, ellipse=(int(size * 0.20), int(size * 0.24)))
    blob((c, int(size * 0.68)), GREEN, ellipse=(int(size * 0.16), int(size * 0.22)))
    # a pointed ear
    ear = np.array([[c - 16, int(size * 0.22)], [c - 6, int(size * 0.22)],
                    [c - 12, int(size * 0.05)]], np.int32)
    blob(None, GREEN, poly=ear)
    inner = np.array([[c - 14, int(size * 0.20)], [c - 8, int(size * 0.20)],
                      [c - 12, int(size * 0.09)]], np.int32)
    blob(None, DARK_GREEN, poly=inner)
    # a THIN tail — two px wide, which is what the alpha steepening can eat
    blob(None, GREEN, line=((c + 18, int(size * 0.66)), (c + 30, int(size * 0.80)), 2))
    blob(None, BLACK, line=((c + 29, int(size * 0.79)), (c + 33, int(size * 0.84)), 3))
    # brow bar, eyes, pupils, muzzle
    blob(None, BLACK, line=((c - 12, int(size * 0.30)), (c + 12, int(size * 0.30)), 4))
    for dx in (-7, 7):
        blob((c + dx, int(size * 0.37)), WHITE, ellipse=(6, 5))
        blob((c + dx, int(size * 0.37)), BLACK, ellipse=(2, 2))
    blob((c, int(size * 0.47)), CREAM, ellipse=(9, 6))

    # the same feather cutout.auto_chroma_matte leaves: blur a hard mask
    alpha = cv2.GaussianBlur(mask, (0, 0), 0.9)
    return np.dstack([bgr, alpha])


def naive(rgba: np.ndarray, factor: int) -> np.ndarray:
    """What a smooth photo filter does — the thing we are claiming to beat."""
    h, w = rgba.shape[:2]
    return cv2.resize(rgba, (w * factor, h * factor),
                      interpolation=cv2.INTER_LANCZOS4)


def interior(rgba: np.ndarray, erode: int = 9) -> np.ndarray:
    """Well inside the subject, so the measurement is about fills, not edges."""
    solid = (rgba[:, :, 3] > 200).astype(np.uint8)
    return cv2.erode(solid, np.ones((erode, erode), np.uint8)).astype(bool)


def local_std(rgba: np.ndarray, mask: np.ndarray) -> float:
    """Median 5x5 luma standard deviation inside `mask`.

    A flat fill scores 0. A resampled fill carries the resampler's gradients and
    scores above 0. The MEDIAN is what makes this a fill measurement: windows
    that straddle a boundary between two fills score high in both images and
    would swamp a mean.
    """
    g = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu = cv2.blur(g, (5, 5))
    mu2 = cv2.blur(g * g, (5, 5))
    return float(np.median(np.sqrt(np.maximum(mu2 - mu * mu, 0.0))[mask]))


def solid_area(rgba: np.ndarray) -> int:
    return int((rgba[:, :, 3] > 128).sum())


def library_poses(limit: int | None = None) -> list[pathlib.Path]:
    files = sorted(p for p in LIBRARY.glob("*.png") if not p.stem.startswith("_"))
    return files if limit is None else files[::max(1, len(files) // limit)][:limit]


# ─────────────────────────── 1 · determinism ─────────────────────────────────

def test_two_runs_are_byte_identical():
    src = donkey()
    a = U.upscale_flat(src, 3)
    b = U.upscale_flat(src, 3)
    assert a.tobytes() == b.tobytes()


def test_determinism_holds_on_real_poses():
    for p in library_poses(6):
        src = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        assert U.upscale_flat(src, 2).tobytes() == U.upscale_flat(src, 2).tobytes(), p.name


def test_input_is_not_mutated():
    src = donkey()
    before = src.copy()
    U.upscale_flat(src, 3)
    assert np.array_equal(src, before)


def test_no_kmeans_anywhere():
    """The determinism above is a property of the algorithm, not of luck. An
    unseeded cv2.kmeans would pass a single-process comparison often enough to
    look fine and still differ between builds."""
    text = (ROOT / "scripts" / "upscale.py").read_text()
    body = text.split('"""', 2)[-1]  # the module docstring may discuss it
    assert "kmeans" not in body


# ─────────────────────────── 2 · shape and geometry ──────────────────────────

@pytest.mark.parametrize("factor", [1, 2, 3, 4])
def test_output_is_factor_times_the_input(factor):
    src = donkey(80)
    out = U.upscale_flat(src, factor)
    assert out.shape == (80 * factor, 80 * factor, 4)
    assert out.dtype == np.uint8


def test_rejects_a_factor_below_one():
    with pytest.raises(ValueError):
        U.upscale_flat(donkey(40), 0)


# ─────────────────────────── 3 · the two claims ──────────────────────────────

def test_alpha_ramp_is_narrower_than_a_naive_resize():
    """Relative to the image, the halo has to shrink. The naive resize widens the
    2px matte feather in proportion to the scale; this must not."""
    src = donkey()
    factor = 3
    ours = U.upscale_flat(src, factor)
    theirs = naive(src, factor)
    assert U._alpha_ramp_px(ours[:, :, 3]) < U._alpha_ramp_px(theirs[:, :, 3]) / 2


def test_alpha_ramp_lands_near_one_output_pixel():
    src = donkey()
    ramp = U._alpha_ramp_px(U.upscale_flat(src, 3)[:, :, 3])
    # The metric saturates below a pixel (see _alpha_ramp_px), so the assertion
    # is that we are in the sub-pixel regime, not that we hit 1.00 exactly.
    assert 0.2 < ramp < 1.4


def test_interior_fills_are_flatter_than_a_naive_resize():
    src = donkey()
    factor = 3
    ours = U.upscale_flat(src, factor)
    theirs = naive(src, factor)
    mask = interior(ours)
    assert mask.sum() > 500
    assert local_std(theirs, mask) > 0.05, "the fixture has no gradient to remove"
    assert local_std(ours, mask) < local_std(theirs, mask) / 4


def test_interior_holds_only_a_handful_of_colours():
    src = donkey()
    ours = U.upscale_flat(src, 3)
    mask = interior(ours)
    colours = np.unique(ours[:, :, :3][mask].reshape(-1, 3), axis=0)
    assert len(colours) <= U.MAX_COLOURS


def test_palette_entries_stay_separated():
    """Seeding respects MIN_SEPARATION and Lloyd refinement does not, which is
    how `detective` ended up with a two-tone eye white. _enforce_separation is
    the fix and this is the lock."""
    for p in library_poses(8):
        src = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        pal = U._palette(src[:, :, :3], src[:, :, 3] > 200)
        assert pal is not None and len(pal) >= 2, p.name
        d = np.sqrt(((pal[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2))
        iu = np.triu_indices(len(pal), 1)
        assert d[iu].min() >= U.MIN_SEPARATION - 1e-3, p.name


def test_identity_colours_survive_on_the_hard_poses():
    """Wardrobe and props are the cases where a palette runs out of room. The
    brow bar, the hooves, the eye whites, the cream muzzle and the darker ear
    inner all have to still be in the palette afterwards, or Silly stops being
    Silly."""
    landmarks = {
        "eye white": (252, 253, 253),
        "cream muzzle/belly": (178, 224, 252),
        "black brow/mane/hooves": (16, 20, 14),
        "body green": (94, 152, 70),
    }
    hard = ["lab_coat", "bathrobe", "cardigan_mug", "detective", "rebel", "sleepless"]
    for name in hard:
        f = LIBRARY / f"{name}.png"
        if not f.is_file():
            pytest.skip(f"{name}.png is not in the library")
        src = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        pal = U._palette(src[:, :, :3], src[:, :, 3] > 200)
        for label, colour in landmarks.items():
            d = np.linalg.norm(pal - np.array(colour, np.float32), axis=1).min()
            assert d < 40, f"{name}: {label} has no palette entry within 40 (got {d:.0f})"
        greens = [c for c in pal if c[1] > c[0] + 20 and c[1] > c[2] + 20]
        assert len(greens) >= 2, f"{name}: body green and darker ear inner collapsed to one"


# ─────────────────────────── 4 · the thin bits ───────────────────────────────

def test_thin_features_are_not_eaten():
    """The alpha map is linear about a=0.5, so the half-alpha contour does not
    move and the area at that threshold is preserved. 1% is the tolerance:
    measured over all 180 library poses the real spread is 0.9999-1.0005, so 1%
    is two orders of magnitude of headroom and still catches a choked tail,
    which costs several percent."""
    for factor in (2, 3):
        src = donkey()
        out = U.upscale_flat(src, factor)
        ratio = solid_area(out) / (solid_area(src) * factor * factor)
        assert 0.99 < ratio < 1.01, f"factor {factor}: solid area ratio {ratio:.4f}"


def test_the_tail_tuft_is_still_there():
    """Area over the whole figure can hold while a thin appendage disappears, so
    check the tail's own bounding box separately."""
    src = donkey()
    h, w = src.shape[:2]
    box = (slice(int(h * 0.62), h), slice(int(w * 0.55), w))
    before = int((src[box][:, :, 3] > 128).sum())
    assert before > 20, "the fixture has no tail to lose"
    out = U.upscale_flat(src, 3)
    box3 = (slice(int(h * 0.62) * 3, h * 3), slice(int(w * 0.55) * 3, w * 3))
    after = int((out[box3][:, :, 3] > 128).sum())
    assert after / (before * 9) > 0.9, f"tail area {after / (before * 9):.2f} of expected"


# ─────────────────────────── 5 · the real library ────────────────────────────

def test_every_library_pose_upscales_without_loss():
    files = library_poses()
    assert len(files) > 100, "the library did not load; the rest of this is vacuous"
    for p in files:
        src = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        assert src is not None and src.shape[2] == 4, p.name
        out = U.upscale_flat(src, 2)
        assert out.shape[:2] == (src.shape[0] * 2, src.shape[1] * 2), p.name
        ratio = solid_area(out) / (solid_area(src) * 4)
        assert 0.98 < ratio < 1.02, f"{p.name}: solid area ratio {ratio:.4f}"


def test_library_palettes_stay_inside_the_cap():
    for p in library_poses(30):
        src = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        pal = U._palette(src[:, :, :3], src[:, :, 3] > 200)
        assert 2 <= len(pal) <= U.MAX_COLOURS, f"{p.name}: k={len(pal)}"


# ─────────────────────────── 6 · edge cases ──────────────────────────────────

def test_fully_transparent_image():
    out = U.upscale_flat(np.zeros((40, 40, 4), np.uint8), 3)
    assert out.shape == (120, 120, 4)
    assert out[:, :, 3].max() == 0


def test_fully_opaque_single_colour():
    src = np.zeros((40, 40, 4), np.uint8)
    src[:, :, :3] = GREEN
    src[:, :, 3] = 255
    out = U.upscale_flat(src, 3)
    assert out[:, :, 3].min() == 255
    assert len(np.unique(out[:, :, :3].reshape(-1, 3), axis=0)) == 1


def test_tiny_images():
    for h, w in ((1, 1), (2, 3), (4, 4), (7, 2)):
        src = np.zeros((h, w, 4), np.uint8)
        src[:, :, :3] = GREEN
        src[:, :, 3] = 255
        out = U.upscale_flat(src, 3)
        assert out.shape == (h * 3, w * 3, 4), (h, w)


def test_three_channel_input_keeps_three_channels():
    src = np.zeros((30, 30, 3), np.uint8)
    src[:, :] = GREEN
    src[10:20, 10:20] = CREAM
    out = U.upscale_flat(src, 3)
    assert out.shape == (90, 90, 3)
    assert len(np.unique(out.reshape(-1, 3), axis=0)) == 2


def test_rejects_a_two_dimensional_image():
    with pytest.raises(ValueError):
        U.upscale_flat(np.zeros((8, 8), np.uint8), 3)


def test_running_it_twice_does_not_erode_the_subject():
    """Nothing calls it twice today, but the gain is measured rather than fixed
    precisely so that a second pass converges instead of choking the silhouette.
    A fixed gain would steepen an already-hard edge again and lose the tail."""
    src = donkey()
    once = U.upscale_flat(src, 2)
    twice = U.upscale_flat(once, 2)
    ratio = solid_area(twice) / (solid_area(once) * 4)
    assert 0.98 < ratio < 1.02, f"second pass changed solid area by {ratio:.4f}"
