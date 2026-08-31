#!/usr/bin/env python3
"""
upscale.py — enlarging flat-vector mascot artwork without turning it to soup.

The library is 180 matted RGBA PNGs in `mascot/library/`, median 302x416 px.
`render.py` sizes a mascot between MASCOT_MIN and MASCOT_MAX — 470 and 900 CSS
px — at `device_scale_factor=1`, so every pose on every slide is enlarged by the
browser before it is printed: median 1.13x, and 4.04x for the smallest pose in
the library. Nothing chose that resampler and nothing can configure it. It is a
photo filter, and this is not a photograph.

Two specific defects come out of that, and this module exists to prevent both.

  · THE HALO. `cutout.auto_chroma_matte` finishes with `GaussianBlur(sigma=0.9)`
    on a hard mask, which is a deliberate ~1px feather so the silhouette is not
    stair-stepped. Measured across all 180 poses, that feather is 2.00 px wide
    (p10 1.99, p90 2.02, max 2.06; the metric is partial-alpha pixels divided by
    the length of the 0.5 contour). A smooth resampler multiplies it by the
    scale factor, so at 2.2x it is a 4-5 px soft rim. On a checkerboard nobody
    notices. On the saturated grounds render.py actually uses — terracotta
    #D0522A, forest #2F6B4F — a 5 px ramp of half-transparent green reads as a
    glow, and the character looks pasted onto the slide rather than drawn on it.

  · THE MUSH. The fills are not as flat as CHARACTER.md says they are. Sampling
    `deadpan`'s opaque pixels, the body green arrives from the generator spread
    across roughly ten units — (92,148,70) through (97,155,66) in BGR — and the
    interior of a naively enlarged pose carries a median of 35,097 distinct
    colours. A smooth filter then widens every interior boundary too, so the
    black brow bar bleeds into the green forehead and the cream muzzle bleeds
    into both.

So we enlarge deliberately: resample, re-steepen the alpha ramp back to about
one pixel AT THE NEW SCALE, and snap the interior back onto the artwork's own
colours so the resampler's gradients are removed. The browser then has less to
do — usually it is scaling our output DOWN, which is the operation its filter is
good at, and the anti-aliasing it puts back is correct for the display size.

Measured over the whole library at factor 3 (`upscale_flat(pose, 3)`):

    interior 5x5 local std      0.490  ->  0.000     (median over 180 poses)
    distinct interior colours  35,097  ->  6         (median)
    alpha ramp, output px        6.00  ->  0.62      (2.00 src px x 3)
    solid area vs factor^2     0.9999 - 1.0005       (min - max, 180 poses)

against the same poses resampled once with INTER_LANCZOS4 and nothing else.

WHAT IS DELIBERATELY NOT HERE

  · k-means. The obvious way to flatten fills is `cv2.kmeans`, and the obvious
    way is wrong here: without an explicit seed it initialises randomly, so the
    same pose flattens to slightly different colours on every run and no two
    builds of the same deck are byte-identical. Seeding it would fix the
    symptom. Instead the palette is derived by a fixed-order histogram pass —
    bin the opaque pixels on a 32^3 grid, walk the bins in descending count with
    ties broken by bin index, and keep a bin only if its mean colour is at least
    MIN_SEPARATION away from every colour already kept. Every step is a
    deterministic numpy operation, so the output is reproducible by
    construction rather than by remembering to pass a seed.

  · A fixed k. `k=8` is a guess, and the library does not have one k: plain
    Silly is green, darker green, cream, black, white and a hoof shade, while
    `lab_coat` adds a coat, a collar and a prop. k is not a parameter here — it
    falls out of the separation rule. Measured over the 180 real poses it lands
    at median 6, minimum 4, maximum 13. MAX_COLOURS is 16 and is a guard against
    a pathological input, not a design choice; it does not bind on any pose in
    the library.

    MIN_SEPARATION = 18 was chosen against the same 180. A single fill's own
    spread is about 10 units, so 18 merges the resampler's noise. Two genuinely
    different colours sit much further apart — in `rebel` the black jacket
    (19,20,21) and the grey (46,46,46) are 45 apart. Sweeping the threshold, the
    first value at which any pose loses its second green (the darker ear inner,
    which is what stops an ear reading as a flat paddle) is 30, and by 40 that
    is 16 poses. 18 is below the failure and above the noise, and it costs
    almost nothing: mean per-pixel snap error is 5.5 at 18 against an
    irreducible 4.35 at 8, where the residual is anti-aliasing between regions
    and is not removable by any palette.

  · A hardcoded steepening gain. The gain is computed from the ramp this
    particular image actually has, not from a constant, for two reasons. The
    library's feather is uniform today but is a consequence of one sigma in
    cutout.py, and a constant here would silently stop matching if that sigma
    ever moved. And measuring makes the function idempotent-safe: run it on its
    own output and it sees an already-steep 0.62 px ramp, asks for a gain of
    about 1.9 instead of 6, and converges instead of eating the silhouette.

    That safety matters most for the thin bits. The map is linear about a=0.5,
    which pins the half-alpha contour exactly where it was, so the tail and the
    pointed ear tips keep their area rather than being choked: across all 180
    poses the solid area of the output is between 0.9999 and 1.0005 of factor^2
    times the input's. A steepening that pivoted anywhere else would erode every
    thin feature in the library and it would only be visible on the tail.

KNOWN COST

  Flattening posterises. The generator did not obey CHARACTER.md's "completely
  flat colour fills with no gradients" everywhere: several poses carry a soft
  vertical gradient down the ear inner, and `reading` has an eye white that
  shades from (251,251,251) to a warm (206,240,252) across 970 px. A smooth
  resampler hides that as a blur; this module resolves it into two hard-edged
  regions, which is closer to the brand and more obvious. Measured over the 180
  poses, a median of 7.0% of interior pixels move more than 12 units when they
  are snapped (p90 9.3%, worst 12.4% on `hero_fumbling`) — that share is where
  banding can appear, and on the ear inners it does. Where it looks wrong the
  fix is a better pose, not a softer palette — and it is why
  `_enforce_separation` exists at all: `detective` first shipped a two-tone eye
  because Lloyd refinement walked two whites to within 16.4 of each other,
  under a floor of 18 that the seeding had respected.
"""

from __future__ import annotations

import cv2
import numpy as np

# The alpha ramp we want on the OUTPUT, in output pixels, measured with
# _alpha_ramp_px below. The library's matte measures 2.00 by the same metric.
TARGET_RAMP_PX = 1.0

# Two palette colours closer than this in BGR are the same fill seen through the
# generator's noise. See the module docstring for the sweep this came from.
MIN_SEPARATION = 18.0

# A histogram bin has to hold this share of the opaque pixels to seed a palette
# entry. 0.15% of a median pose is about 90 px — small enough to keep a pupil
# highlight, large enough to ignore the anti-aliased fringe between two fills.
MIN_SHARE = 0.0015

# Guard against a pathological input, not a design choice: no library pose
# reaches it. See the docstring.
MAX_COLOURS = 16

# Alpha above which a pixel counts as "inside a fill" when the palette is built.
_SOLID = 200

# Alpha above which an output pixel is re-coloured. Below this the pixel is
# mostly ground anyway, and the outermost sub-pixel blend is left as the
# resampler made it so the silhouette does not speckle.
_SNAP_ALPHA = 128

# 3 -> 32 levels per channel, a 32^3 histogram. Coarse enough that one fill
# lands in a handful of bins, fine enough to keep 18 units of separation
# meaningful.
_BIN_SHIFT = 3


def upscale_flat(rgba: np.ndarray, factor: int = 3) -> np.ndarray:
    """Enlarge matted flat-vector artwork by `factor`, keeping the edges hard.

    `rgba` is an HxWx4 BGRA image as `cv2.imread(..., IMREAD_UNCHANGED)` returns
    it. A 3-channel BGR image is accepted and comes back 3-channel: the fills
    are flattened and the alpha work is skipped, because there is no alpha.

    The result is `factor` times the input in both dimensions, always. Every
    step is deterministic, so the same input gives a byte-identical output.
    """
    if factor < 1:
        raise ValueError(f"factor must be >= 1, got {factor}")
    factor = int(factor)
    if rgba.ndim != 3 or rgba.shape[2] not in (3, 4):
        raise ValueError(f"expected an HxWx3 or HxWx4 image, got shape {rgba.shape}")
    H, W = rgba.shape[:2]
    if H == 0 or W == 0:
        return rgba.copy()

    has_alpha = rgba.shape[2] == 4
    bgr_src = rgba[:, :, :3]
    solid = rgba[:, :, 3] > _SOLID if has_alpha else np.ones((H, W), bool)

    # The palette comes from the SOURCE, before any resampling. The source is
    # the ground truth for what colours the artwork uses; the enlarged copy has
    # the resampler's inventions in it and would seed the palette with them.
    pal = _palette(bgr_src, solid)

    # Measure the feather before it is stretched, so the gain suits this image.
    ramp = _alpha_ramp_px(rgba[:, :, 3]) if has_alpha else 0.0

    big = cv2.resize(rgba, (W * factor, H * factor),
                     interpolation=cv2.INTER_LANCZOS4)
    if big.ndim == 2:  # cv2 drops the axis for a single-column/row input
        big = big[:, :, None]
    out_bgr = big[:, :, :3]

    if has_alpha:
        # Linear about 0.5: the half-alpha contour, which is the silhouette,
        # does not move. Everything either side of it is pulled to 0 or 1.
        gain = 1.0
        if ramp > 0:
            gain = float(np.clip(ramp * factor / TARGET_RAMP_PX, 1.0, 24.0))
        a = big[:, :, 3].astype(np.float32) / 255.0
        a = np.clip((a - 0.5) * gain + 0.5, 0.0, 1.0)
        out_a = np.round(a * 255.0).astype(np.uint8)
        snap_mask = out_a >= _SNAP_ALPHA
    else:
        out_a = None
        snap_mask = np.ones(out_bgr.shape[:2], bool)

    if pal is not None and snap_mask.any():
        out_bgr = _snap(out_bgr, pal, snap_mask)

    if out_a is None:
        return np.ascontiguousarray(out_bgr)
    return np.ascontiguousarray(np.dstack([out_bgr, out_a]))


# ─────────────────────────── measurement ─────────────────────────────────────

def _alpha_ramp_px(alpha: np.ndarray) -> float:
    """Width of the anti-aliased alpha edge, in pixels.

    Partial-alpha pixels divided by the length of the 0.5 contour. It is a
    proxy, not a geometric width — it saturates once the ramp is inside a single
    pixel, which is exactly the regime we are steering out of. The library's
    matte measures 2.00 by it; a hard-edged mask measures 0.
    """
    solid = (alpha > 128).astype(np.uint8)
    if not solid.any():
        return 0.0
    edge = solid - cv2.erode(solid, np.ones((3, 3), np.uint8))
    perimeter = int(edge.sum())
    if perimeter == 0:
        return 0.0
    partial = int(((alpha > 20) & (alpha < 235)).sum())
    return partial / perimeter


# ─────────────────────────── palette ─────────────────────────────────────────

def _palette(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    """The artwork's own fill colours, as a (k, 3) float32 array of BGR.

    Deterministic by construction: a histogram on a fixed grid, walked in a
    fixed order, refined by two fixed passes. No randomness, no seed to forget.
    Returns None when there is not enough opaque artwork to measure, in which
    case the caller leaves the colours alone.
    """
    px = bgr[mask]
    if px.size == 0 or len(px) < 500:
        return None
    px = px.astype(np.int32)

    q = px >> _BIN_SHIFT
    key = (q[:, 0].astype(np.int64) << 10) | (q[:, 1].astype(np.int64) << 5) | q[:, 2]
    keys, inverse, counts = np.unique(key, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    means = np.stack(
        [np.bincount(inverse, weights=px[:, c], minlength=len(keys)) / counts
         for c in range(3)], axis=1).astype(np.float32)

    total = int(counts.sum())
    floor = max(1.0, MIN_SHARE * total)

    # Descending count, ties broken by bin index ascending. lexsort is stable
    # and the keys are unique, so this order is a function of the pixels alone.
    order = np.lexsort((keys, -counts))

    seeds: list[np.ndarray] = []
    for j in order:
        if counts[j] < floor:
            break
        c = means[j]
        if seeds and min(float(np.linalg.norm(c - s)) for s in seeds) < MIN_SEPARATION:
            continue
        seeds.append(c)
        if len(seeds) == MAX_COLOURS:
            break
    if not seeds:
        seeds = [means[order[0]]]
    pal = np.asarray(seeds, np.float32)

    # Two weighted Lloyd passes over the SIGNIFICANT bins only. A seed is one
    # bin's mean, which is a corner of the fill rather than its centre; this
    # recentres it. Restricting to bins above the floor keeps the thousands of
    # tiny anti-aliasing bins from dragging a fill colour off its own value.
    sig = counts >= floor
    bin_mean, bin_count = means[sig], counts[sig].astype(np.float32)
    weight = np.zeros(len(pal), np.float32)
    if len(bin_mean) > len(pal):
        for _ in range(2):
            d = ((bin_mean[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
            assign = d.argmin(axis=1)
            for k in range(len(pal)):
                m = assign == k
                if m.any():
                    w = bin_count[m]
                    weight[k] = w.sum()
                    pal[k] = (bin_mean[m] * w[:, None]).sum(axis=0) / w.sum()
    return _enforce_separation(pal, weight)


def _enforce_separation(pal: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Merge any pair the refinement pulled back under MIN_SEPARATION.

    Seeding respects the separation rule; Lloyd does not know about it and can
    walk two entries together again. `detective` finished with two whites 16.4
    apart, and a palette holding two colours that close bands a fill it should
    have flattened — the eye whites came out two-tone. Merging by weight is
    deterministic: the closest pair is found by argmin over the upper triangle,
    which resolves ties to the lowest index pair.
    """
    while len(pal) > 1:
        d = np.sqrt(((pal[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2))
        iu = np.triu_indices(len(pal), 1)
        j = int(np.argmin(d[iu]))
        if d[iu][j] >= MIN_SEPARATION:
            break
        a, b = int(iu[0][j]), int(iu[1][j])
        wa, wb = float(weight[a]), float(weight[b])
        if wa + wb <= 0:
            wa = wb = 1.0
        pal[a] = (pal[a] * wa + pal[b] * wb) / (wa + wb)
        weight[a] = wa + wb
        pal = np.delete(pal, b, axis=0)
        weight = np.delete(weight, b, axis=0)
    return pal


def _snap(bgr: np.ndarray, pal: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Replace every masked pixel with the nearest palette colour.

    One pass per palette entry rather than a (N, k, 3) tensor: k is at most 16
    but N is factor^2 times a pose, so the tensor would be hundreds of MB for
    no gain.
    """
    px = bgr[mask].astype(np.float32)
    best = np.full(len(px), np.inf, np.float32)
    idx = np.zeros(len(px), np.int32)
    for k in range(len(pal)):
        d = ((px - pal[k]) ** 2).sum(axis=1)
        closer = d < best
        best[closer] = d[closer]
        idx[closer] = k
    out = bgr.copy()
    out[mask] = np.round(pal[idx]).astype(np.uint8)
    return out
