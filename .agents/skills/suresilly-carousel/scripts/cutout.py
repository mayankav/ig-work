#!/usr/bin/env python3
"""
cutout.py — turning a generated sheet into clean transparent artwork.

This is the live, load-bearing half of the pipeline: background removal and the
quality gates that decide whether a pose is fit to ship. Used by
import_poses.py on every import.

Two things here are not obvious and were both learned the hard way:

  · The key colour is DETECTED, never hardcoded. Silly is green, so a green
    backdrop overlaps his own body and the key eats the character. Magenta is
    the documented backdrop for exactly that reason.
  · Every key-coloured pixel goes, not only the ones touching the border.
    Backdrop seen through a magnifying-glass lens or behind a held card is
    still backdrop; requiring border connectivity left magenta inside 36 of 60
    poses.
"""

from __future__ import annotations

import cv2
import numpy as np


class QAFailure(Exception):
    """A pose failed a quality gate. Nothing is written when this is raised."""


def detect_key_hue(bgr: np.ndarray) -> float:
    """Median hue of the frame border — the backdrop colour to key out."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    border = np.concatenate([hsv[0], hsv[-1], hsv[:, 0], hsv[:, -1]])
    return float(np.median(border, axis=0)[0])


def auto_chroma_matte(bgr: np.ndarray) -> np.ndarray:
    """Key out whatever saturated colour the border actually is. Returns BGRA.

    The key colour is detected, never hardcoded. That matters because Silly is
    green: a green backdrop overlaps his own body in hue, so the key would eat
    parts of the character. Magenta is the documented backdrop, but auto-detection
    means a stray green or blue sheet still mattes correctly instead of silently
    producing a mangled cutout.

    Shared by the generation path and by import_poses.py so there is one
    implementation to get right.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    border = np.concatenate([hsv[0], hsv[-1], hsv[:, 0], hsv[:, -1]])
    med = np.median(border, axis=0)
    hue = float(med[0])

    # Hue wraps at 180 in OpenCV, so a magenta key near 150 needs circular distance.
    dh = np.abs(hsv[:, :, 0].astype(np.int16) - hue)
    dh = np.minimum(dh, 180 - dh)
    mask = ((dh <= 22) & (hsv[:, :, 1] >= 70) & (hsv[:, :, 2] >= 40)).astype(np.uint8)

    # Remove EVERY key-coloured pixel, not only the border-connected ones. A
    # chroma backdrop is a colour the character never uses, so an enclosed patch
    # of it — seen through a magnifying-glass lens, behind a held card, between
    # an arm and the body — is still background. Requiring border connectivity
    # left magenta inside 36 of 60 poses. (The paper/white path in
    # import_poses.matte_flat DOES need connectivity, because there the "key"
    # colour is close to the character's own cream muzzle.)
    hard = np.where(mask.astype(bool), 0, 255).astype(np.uint8)
    hard = cv2.morphologyEx(hard, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # Choke 1px: the outermost ring of a generated edge is mostly backdrop.
    hard = cv2.erode(hard, np.ones((3, 3), np.uint8), iterations=1)

    # Colour-extend instead of un-premultiplying. Dividing by a clamped alpha
    # amplified whatever backdrop survived by up to 4x, which is why cutouts
    # carried a rim five times greener than the body. Growing the SUBJECT's own
    # colours outward under the feather means the rim can only ever be the
    # character's colour, and alpha alone does the blending.
    solid = hard > 127
    filled = bgr.copy()
    if solid.any():
        holes = (~solid).astype(np.uint8)
        # nearest opaque colour for every transparent pixel near the edge
        _, labels = cv2.distanceTransformWithLabels(
            holes, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.where(solid)
        order = np.zeros(labels.max() + 1, dtype=np.int64)
        lab_at_solid = labels[solid]
        order[lab_at_solid] = np.arange(len(ys))
        idx = order[labels]
        filled = bgr[ys[idx], xs[idx]]
        filled[solid] = bgr[solid]

    alpha = cv2.GaussianBlur(hard, (0, 0), 0.9)
    return np.dstack([filled, alpha])


def qa(rgba: np.ndarray, *, src_shape: tuple[int, int],
       allow_detached: bool = False, strict_framing: bool = True,
       key_hue: float | None = None) -> None:
    """Every gate raises QAFailure naming itself. Nothing is saved on failure."""
    alpha = rgba[:, :, 3]
    solid = (alpha > 128).astype(np.uint8)
    total = solid.size

    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, 8)
    areas = [(i, stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)]
    if not areas:
        raise QAFailure("single_subject: nothing left after matting")
    areas.sort(key=lambda x: -x[1])

    # 1 · exactly one substantial subject — leftover glyphs show up as extra blobs
    big = [i for i, a in areas if a >= 0.02 * total]
    if len(big) != 1 and not allow_detached:
        raise QAFailure(
            f"single_subject: expected 1 component >=2% of canvas, found {len(big)} "
            f"(likely text or a second figure in the artwork)")

    # 2 · a caption printed under the artwork. The signature is a RUN of small
    #     components of similar height sitting low in the frame — that is what
    #     glyphs look like. A lone detached hoof or foot is one component, not a
    #     run, so a jumping or caped pose is no longer rejected as text.
    main = areas[0][0]
    H = rgba.shape[0]
    low = [(i, a) for i, a in areas
           if i != main and a >= 0.0005 * total
           and stats[i, cv2.CC_STAT_TOP] > 0.80 * H]
    if len(low) >= 3:
        heights = sorted(stats[i, cv2.CC_STAT_HEIGHT] for i, _ in low)
        med = heights[len(heights) // 2]
        similar = [h for h in heights if med / 2.5 <= h <= med * 2.5]
        if len(similar) >= 3:
            raise QAFailure(
                f"no_bottom_strays: {len(similar)} similar-height components in a row "
                f"below 80% height — this is what baked-in caption text looks like")

    # 3 · leftover backdrop colour. Must be measured against the ACTUAL key,
    #     not hardcoded green: the character is green, so on a magenta backdrop
    #     a perfectly clean edge is strongly green-dominant. Callers that know
    #     the key pass its hue; the check is skipped when they do not.
    if key_hue is not None:
        hsv = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_BGR2HSV)
        dh = np.abs(hsv[:, :, 0].astype(np.int16) - key_hue)
        dh = np.minimum(dh, 180 - dh)
        residue = (dh <= 18) & (hsv[:, :, 1] > 90) & (alpha > 200)
        frac = residue.sum() / max(1, solid.sum())
        if frac > 0.004:
            raise QAFailure(
                f"key_residue: {residue.sum()} px of backdrop colour left on the "
                f"subject ({frac:.1%}) — the matte missed an enclosed region")

    # 4 · framing — the character must sit fully inside the frame. The bottom
    #     edge is tolerated because sheet cells crop tightly there; the other
    #     three edges being touched means a genuinely clipped figure.
    #     Only meaningful for GENERATED poses, where the model controls the
    #     composition and edge contact means a bad crop. Sheet extraction slices
    #     a deliberately tight grid, so ear tips legitimately reach the edge —
    #     there the caption and neighbour-bleed guards are what matter.
    ys, xs = np.where(solid > 0)
    sh, sw = src_shape
    scale_ok = rgba.shape[0] >= sh * 0.5
    touches = {
        "top": ys.min() <= 1,
        "left": xs.min() <= 1 and rgba.shape[1] >= sw * 0.9,
        "right": xs.max() >= rgba.shape[1] - 2 and rgba.shape[1] >= sw * 0.9,
    }
    bad = [k for k, v in touches.items() if v]
    if bad and scale_ok and strict_framing:
        raise QAFailure(
            f"framing: subject is clipped by the {'/'.join(bad)} edge — the whole "
            f"figure must sit inside the frame")

    # 5 · the subject actually fills its crop
    # Calibrated against the real library: fills run 34%-59% (median 53%). A
    # donkey bust has tall ears and empty shoulders, so the tight crop is never
    # dense. 22% still catches a subject lost in a large frame.
    fill = solid.sum() / total
    if fill < 0.22:
        raise QAFailure(f"subject_size: subject fills only {fill:.0%} of its bounding box (<22%)")
