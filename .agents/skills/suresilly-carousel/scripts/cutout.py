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


# Below this brightness a pixel's hue and saturation carry no information:
# saturation is (max-min)/max, so a near-black BGR (5,0,3) reports as fully
# saturated with an arbitrary hue. Both the key mask and the residue gate use
# this floor, so they agree about what the backdrop colour is.
KEY_MIN_VALUE = 40


class QAFailure(Exception):
    """A pose failed a quality gate. Nothing is written when this is raised."""


def detect_key_hue(bgr: np.ndarray) -> float:
    """Median hue of the frame border — the backdrop colour to key out."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    border = np.concatenate([hsv[0], hsv[-1], hsv[:, 0], hsv[:, -1]])
    return float(np.median(border, axis=0)[0])


def detect_key_colour(bgr: np.ndarray) -> np.ndarray:
    """Median BGR of the frame border — the backdrop colour itself.

    The hue alone is not enough to identify a backdrop, and detect_key_hue()
    below is kept only for callers that genuinely want the hue. A flat chroma
    backdrop is ONE colour, and knowing which one is what lets a lilac tissue
    box survive on a magenta key: same hue family, 113-154 units away in BGR,
    where the backdrop's own pixels sit within 15 of their median.
    """
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
    return np.median(border.astype(np.float32), axis=0)


KEY_TOL = 60.0      # BGR distance that still counts as the backdrop itself
KEY_REACH = 3       # px from the backdrop within which a blend is its edge


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
    # Two tiers, and the split is what stops the key eating the artwork.
    #
    # CORE is the backdrop itself: pixels within KEY_TOL of the measured border
    # colour. A flat chroma backdrop is one colour and stays within 15 units of
    # its own median, so this is a generous match with room for JPEG noise.
    #
    # EDGE is the antialiased blend between the backdrop and the subject. Those
    # pixels are genuinely part-backdrop and have to go, but they are far from
    # the key colour by construction — a 50% blend of magenta and green sits
    # ~118 units away — so a colour match alone leaves a fringe. They are caught
    # by hue, and ONLY within KEY_REACH pixels of the core, which is the whole
    # point: an antialiased edge is by definition next to the backdrop.
    #
    # The previous version had only the hue tier, applied everywhere. That is
    # why a lilac tissue box vanished out of a scene: at 113-154 units from the
    # key it is obviously not the backdrop, but it shares the hue family, and
    # nothing was asking about anything but hue. Sitting on a rug in the middle
    # of the picture, it is nowhere near the backdrop and now survives.
    key = detect_key_colour(bgr)
    core = np.linalg.norm(bgr.astype(np.float32) - key, axis=2) <= KEY_TOL

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue = float(cv2.cvtColor(np.uint8([[key]]), cv2.COLOR_BGR2HSV)[0, 0, 0])
    # Hue wraps at 180 in OpenCV, so a magenta key near 150 needs circular distance.
    dh = np.abs(hsv[:, :, 0].astype(np.int16) - hue)
    dh = np.minimum(dh, 180 - dh)
    hue_band = ((dh <= 22) & (hsv[:, :, 1] >= 70) & (hsv[:, :, 2] >= KEY_MIN_VALUE))

    reach = np.ones((2 * KEY_REACH + 1,) * 2, np.uint8)
    near_core = cv2.dilate(core.astype(np.uint8), reach, 1).astype(bool)
    mask = (core | (hue_band & near_core)).astype(np.uint8)

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
       key_bgr: np.ndarray | tuple[int, int, int] | None = None) -> None:
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

    # 3 · leftover backdrop colour. Measured as distance from the ACTUAL key
    #     COLOUR, which is the same question auto_chroma_matte's core tier asks,
    #     so the matte and the gate cannot disagree about what the backdrop was.
    #
    #     It used to ask about HUE, and that was wrong twice over. It called a
    #     lilac tissue box "backdrop" because lilac is magenta-family, and it
    #     called black outlines "backdrop" because saturation is a ratio and
    #     BGR (5,0,3) reports as fully saturated magenta — two outlined poses
    #     measured 1.0% and 0.9% residue whose pixels had a median brightness of
    #     3 out of 255, and showed no fringe whatever on a real slide ground.
    #
    #     Measured over all 18 library sheet cells and the six scene imports,
    #     the colour-distance definition reports 0.000% residue everywhere,
    #     because there genuinely is none.
    if key_bgr is not None:
        key = np.asarray(key_bgr, dtype=np.float32)
        dist = np.linalg.norm(rgba[:, :, :3].astype(np.float32) - key, axis=2)
        residue = (dist <= KEY_TOL) & (alpha > 200)
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


# ═════════════════════════════════════════════════════════════════════════════
# Shared character gates
# ═════════════════════════════════════════════════════════════════════════════
#
# These four gates — no text, on-palette colour, a correct pair of eyes, and the
# palette correction that feeds them — were written for the generation path in
# poses_flux.py and lived there alone. That was a mistake with a measurable
# cost, and moving them here is the fix.
#
# The import path is where artwork ACTUALLY enters this project. Every one of
# the 180 poses in the library arrived through import_poses.py, and not one of
# them was ever checked for text, for eyes, or for colour, because those checks
# sat in a module import_poses.py does not import. The evidence is in the
# library: sage.png is 24.9 dE76 off the brand green at saturation 81 against a
# library median of 145 — the washed-out drift AGENTS.md warns about, shipped,
# because nothing on the way in measured it.
#
# So they live here now, in the module both paths already depend on, and
# poses_flux.py imports them back. One implementation, both ends — the same
# argument auto_chroma_matte is shared under.
#
# Nothing here is loosened in the move. assert_no_text is a strict SUPERSET of
# qa()'s bottom-strays heuristic: qa() only looks below 80% of the frame, since
# that is where a sheet cell's caption sits and looking higher would reject
# legitimate detached artwork; this one reads the whole frame, which is what
# catches a corner watermark or a signature across the chest.
def backdrop_mask(bgr: np.ndarray, tolerance: int = 44) -> np.ndarray:
    """Pixels close to the frame's border colour — the flat backdrop.

    Border median, the same trick cutout.py and import_poses.py both use, so it
    works on the magenta key we ask for, on the cream of the old style sheets,
    and on whatever a model hands back instead.
    """
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
    med = np.median(border, axis=0)
    return (np.abs(bgr.astype(np.int16) - med).max(2) <= tolerance)


# A pad is a large light region — a speech bubble, a held card, a sign. Marks
# inside one are lettering if they are appreciably darker than the pad itself.
# All three measured against the whole 194-pose library at both scales; see
# enclosed_runs for the numbers.
PAD_LIGHT = 200
PAD_MIN_FRACTION = 0.002
INK_DROP = 40


def _letter_shaped(area: float, w: int, h: int,
                   total: float, W: int, H: int) -> bool:
    """The size and proportion a mark must have to be letter-like.

    One band, used by both detectors below, so "the same test" is a fact about
    the code and not a claim in a docstring.
    """
    if not (0.00002 * total <= area <= 0.006 * total):
        return False
    if not (0.008 * H <= h <= 0.12 * H):
        return False
    return not (w > 0.25 * W or w > 6 * h)


def _baseline_runs(marks: list) -> list[list[tuple[int, int, int, int]]]:
    """Marks grouped into runs: >=3 of similar height on a shared baseline,
    spread across x rather than stacked.

    Each mark arrives as (baseline, height, left, box). Shared, for the same
    reason the size band is.
    """
    runs = []
    used: set[tuple[int, int, int, int]] = set()
    for base, h, _, box in sorted(marks):
        if box in used:
            continue
        row = [g for g in marks if abs(g[0] - base) <= max(3, 0.5 * h)]
        if len(row) < 3:
            continue
        heights = sorted(g[1] for g in row)
        med = heights[len(heights) // 2]
        similar = [g for g in row if med / 2.0 <= g[1] <= med * 2.0]
        xs = sorted(g[2] for g in similar)          # spread across x, not a stack
        if len(similar) >= 3 and (xs[-1] - xs[0]) >= 2 * med:
            runs.append([g[3] for g in similar])
            used.update(g[3] for g in similar)
    return runs


def glyph_runs(bgr: np.ndarray) -> list[list[tuple[int, int, int, int]]]:
    """Runs of small, similar-height marks sitting on one baseline, detached
    from the figure: the shape of text. Each run is a list of bounding boxes.

    Two conditions, and the second one is what makes this usable.

    Size and alignment alone are not enough. Silly's mane is dense black
    corkscrew curls, his hooves are four small black shapes and his ear insides
    are two more — small dark blobs of near-identical height, and the hooves
    genuinely do line up along the bottom of the frame. A detector that looks
    only at shape calls 82 of the 181 poses in the library "text".

    So a mark counts only if it is a SEPARATE PIECE OF PICTURE: its own
    connected region of non-backdrop, not part of the main figure. A caption is
    printed on the background with clear space round every letter. A hoof is
    attached to a leg, and a mane curl to a head. That condition takes the
    false-positive rate on the real 180-pose library to zero while still
    catching every caption on the four old style sheets.

    Working on non-backdrop regions rather than on dark pixels also means the
    colour of the lettering does not matter. A pale watermark is as detectable
    as a black caption.

    cutout.qa() has a cousin of this that only looks BELOW 80% of the frame,
    because that is where a sheet cell's caption lives and looking higher would
    reject legitimate detached artwork in imported poses. Here the composition
    came from a model we prompted, so the whole frame is fair game: a watermark
    across the middle or a signature in a corner is just as fatal and cutout's
    version would not see either. Superset, never a relaxation.

    What "separate piece of picture" cannot see is lettering INSIDE the figure —
    words in a speech bubble, a card held at the chest — because those are holes
    in one component, not components of their own. That is enclosed_runs below,
    and assert_no_text runs both.
    """
    H, W = bgr.shape[:2]
    total = float(H * W)
    subject = (~backdrop_mask(bgr)).astype(np.uint8)
    subject = cv2.morphologyEx(subject, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(subject, 8)
    if n <= 2:
        return []
    main = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])

    glyphs = []
    for i in range(1, n):
        if i == main:
            continue
        area = stats[i, cv2.CC_STAT_AREA]
        h, w = stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_WIDTH]
        top, left = stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_LEFT]
        if not _letter_shaped(area, w, h, total, W, H):
            continue
        glyphs.append((top + h, h, left, (left, top, w, h)))

    return _baseline_runs(glyphs)


def _holes_of(mask: np.ndarray) -> np.ndarray:
    """Every enclosed hole in a binary mask, painted solid.

    A hole is a topological fact, so ask the contour hierarchy: a contour with a
    parent is inside something. The obvious shortcut — close the mask and
    subtract it — instead calls 126 of the 194 library poses text, because
    closing a rounded bubble fills its own convexity and the antialiased rim
    comes back as a row of marks.
    """
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP,
                                           cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros_like(mask)
    if hierarchy is None:
        return out
    for i, node in enumerate(hierarchy[0]):
        if node[3] != -1:                       # has a parent, so it is a hole
            cv2.drawContours(out, contours, i, 1, -1)
    return out


def enclosed_runs(bgr: np.ndarray) -> list[list[tuple[int, int, int, int]]]:
    """The same runs, but INSIDE the figure rather than detached from it.

    Deck 20260902_6pm-picked-up_068b42 published a mascot saying "I'm out" in a
    speech bubble and another holding a card reading "Exit Block". glyph_runs
    scored both frames zero: their subjects are single components filling 89.7%
    and 92.2% of the frame, so the letters were holes in the figure, not pieces
    of picture beside it. Invariant 3 says not a letter, and the gate could not
    see these.

    Find the pads first — light regions that are part of the main component —
    take their topological holes, and hand those to the same size band and the
    same run test glyph_runs uses.

    The one condition that is new is INK_DROP: a mark must be at least 40 grey
    levels darker than the pad it sits in. That number is doing all the work
    here, and it is measured. Against 720 positives — six poses x four phrases x
    three text sizes x bubble and card x five ink tones from near-black to a
    pale 175-on-white — and all 194 library poses at both the scale they are
    stored at and the 1024px scale a generator hands back:

        drop      0    25    30    40    45    50    60
        caught  720   720   720   720   720   701   694
        false     2     1     0     0     0     0     0

    The false side clears at 30 (a shadow inside lantern_bearer's lamp glow, 26
    levels down) and the true side is whole through 45 (pale grey lettering
    starts being missed at 50). 40 is the middle of that window, with 14 levels
    of margin below and 10 above.

    Word-splitting on wide gaps, and dropping the x-spread condition, were both
    tried: with INK_DROP in place all four combinations score exactly
    720/720 and zero, so neither earns its complexity and the run test stays
    literally the one above.
    """
    H, W = bgr.shape[:2]
    total = float(H * W)
    subject = (~backdrop_mask(bgr)).astype(np.uint8)
    subject = cv2.morphologyEx(subject, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(subject, 8)
    if n <= 1:
        return []
    main = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    body = (labels == main).astype(np.uint8)

    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    pads = ((grey >= PAD_LIGHT).astype(np.uint8) & body)
    pn, plabels, pstats, _ = cv2.connectedComponentsWithStats(pads, 8)

    runs = []
    for p in range(1, pn):
        if pstats[p, cv2.CC_STAT_AREA] < PAD_MIN_FRACTION * total:
            continue
        x, y = pstats[p, cv2.CC_STAT_LEFT], pstats[p, cv2.CC_STAT_TOP]
        w, h = pstats[p, cv2.CC_STAT_WIDTH], pstats[p, cv2.CC_STAT_HEIGHT]
        pad = (plabels[y:y + h, x:x + w] == p).astype(np.uint8)
        holes = _holes_of(pad)
        if not holes.any():
            continue
        region = grey[y:y + h, x:x + w]
        tone = float(np.median(region[pad > 0]))
        hn, hlabels, hstats, _ = cv2.connectedComponentsWithStats(holes, 8)
        marks = []
        for k in range(1, hn):
            area = hstats[k, cv2.CC_STAT_AREA]
            mh, mw = hstats[k, cv2.CC_STAT_HEIGHT], hstats[k, cv2.CC_STAT_WIDTH]
            top, left = hstats[k, cv2.CC_STAT_TOP], hstats[k, cv2.CC_STAT_LEFT]
            if not _letter_shaped(area, mw, mh, total, W, H):
                continue
            # A letter is small against the thing it is written on. Without
            # this an eye is a mark inside a face.
            if mh > 0.6 * h or mw > 0.6 * w:
                continue
            if tone - float(np.median(region[hlabels == k])) < INK_DROP:
                continue
            marks.append((y + top + mh, mh, x + left, (x + left, y + top, mw, mh)))
        runs.extend(_baseline_runs(marks))
    return runs


def assert_no_text(bgr: np.ndarray, what: str) -> None:
    """Invariant 3. Raises QAFailure — it never warns.

    Runs on the frame BEFORE matting, because matting a captioned image throws
    the caption away and then the artwork looks clean. cutout.qa()'s component
    gates are the net that catches text after matting. Both have to hold.

    Two detectors, because lettering arrives two ways: printed on the backdrop
    beside the figure, or written on something the figure is holding or saying.
    """
    runs = glyph_runs(bgr)
    if runs:
        raise QAFailure(
            f"no_text: {what} contains {len(runs)} run(s) of "
            f"{sum(len(r) for r in runs)} detached, similar-height marks on a "
            f"shared baseline — this is what lettering looks like, and no "
            f"mascot artwork may carry any")
    inside = enclosed_runs(bgr)
    if inside:
        raise QAFailure(
            f"no_text: {what} contains {len(inside)} run(s) of "
            f"{sum(len(r) for r in inside)} similar-height marks written ON the "
            f"figure — a speech bubble or a held sign. No mascot artwork may "
            f"carry a letter, and a bubble is the way it usually arrives")

# ── palette correction ───────────────────────────────────────────────────────
#
# Measured, not guessed. Across the first four generated poses, against the four
# library poses used as references:
#
#     body green     library saturation 49-52   generated 30-41
#     muzzle/belly   library hue 38-40 deg      generated 22-28 deg
#
# So the model holds the SHAPES from the references and drifts the COLOUR: a
# sage body instead of the brand green, and a blush muzzle instead of a buttery
# one. Consistent in one direction, which is what makes it correctable.
#
# This is a colour correction and nothing more. It moves saturation and hue of
# pixels already in the right family; it cannot repair a wrong shape and must
# never be asked to. It runs BEFORE the gates, so what is judged and what is
# written are the same picture.
LIBRARY_GREEN_SAT = 0.51        # median of the library reference poses
LIBRARY_CREAM_HUE = 39.0        # degrees, ditto
GREEN_HUE_RANGE = (35, 95)      # OpenCV H is 0-179, so this is 70-190 deg
CREAM_MIN_V, CREAM_MAX_S = 180, 120
EYE_MAX_SAT = 45          # an eye white is white; the cream muzzle is 73-94


def correct_palette(bgr: np.ndarray) -> np.ndarray:
    """Pull the body green and the cream back onto the brand palette.

    Returns a new frame. The magenta key is untouched on purpose — everything
    downstream mattes against it and shifting it would break the one thing that
    is already right.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    green = (h > GREEN_HUE_RANGE[0]) & (h < GREEN_HUE_RANGE[1]) & (sat > 25)
    if green.sum() <= 500:
        green = np.zeros_like(green)
    else:
        current = float(np.median(sat[green])) / 255.0
        if current > 0.01:
            sat[green] = np.clip(sat[green] * (LIBRARY_GREEN_SAT / current), 0, 255)

    # The cream is pale and barely saturated, which is what separates it from
    # both the green and the magenta without needing a mask from anywhere else.
    cream = (val > CREAM_MIN_V) & (sat < CREAM_MAX_S) & (sat > 12) & (h < 45)
    if cream.sum() <= 500:
        cream = np.zeros_like(cream)
    else:
        h[cream] += (LIBRARY_CREAM_HUE / 2.0) - float(np.median(h[cream]))
        h[cream] = np.clip(h[cream], 0, 179)

    fixed = cv2.cvtColor(np.stack([h, sat, val], -1).astype(np.uint8),
                         cv2.COLOR_HSV2BGR)

    # Write back ONLY the pixels we meant to change. A BGR->HSV->BGR round trip
    # is not lossless — it moved the magenta key from 255 to 254 — and while one
    # level is nothing to the eye, cutout.py's key_residue gate measures exactly
    # that kind of thing. Compositing on the masks keeps every untouched pixel
    # byte-identical, so the correction cannot cost us an import rejection.
    touched = (green | cream)[..., None]
    return np.where(touched, fixed, bgr).astype(np.uint8)

def _eye_candidates(rgba: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """White blobs that could be an eye. Returns (x, y, w, h, area), largest first."""
    solid = rgba[..., 3] > 200
    bgr = rgba[..., :3]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1]
    height, _ = grey.shape
    upper = np.zeros_like(solid)
    upper[: int(height * 0.62)] = True

    whites = ((grey > 200) & (sat < EYE_MAX_SAT) & solid & upper).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(whites, 8)
    figure_area = max(int(solid.sum()), 1)

    out = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        if not (0.0008 * figure_area < area < 0.06 * figure_area):
            continue
        if w < 5 or h < 5 or not (0.45 < w / h < 2.2):
            continue
        out.append((x, y, w, h, area))
    return sorted(out, key=lambda b: -b[4])


def _pupil_centre(grey: np.ndarray, box: tuple[int, int, int, int, int]):
    """Centre of the dark core inside one eye white, or None if there isn't one."""
    x, y, w, h, _ = box
    patch = grey[y:y + h, x:x + w]
    inset_y, inset_x = max(1, h // 7), max(1, w // 7)
    inner = patch[inset_y:h - inset_y, inset_x:w - inset_x]
    if inner.size == 0:
        return None
    dark = (inner < 110).astype(np.uint8)
    if dark.sum() < max(6, int(0.05 * inner.size)):
        return None
    ys, xs = np.nonzero(dark)
    return (x + inset_x + float(xs.mean()), y + inset_y + float(ys.mean()))


def _matched_size(a: tuple[int, int, int, int, int],
                  b: tuple[int, int, int, int, int]) -> bool:
    """Are these two whites the same size, the way a pair of eyes is?"""
    _, _, aw, ah, _ = a
    _, _, bw, bh, _ = b
    return (abs(ah - bh) <= 0.40 * max(ah, bh)
            and abs(aw - bw) <= 0.40 * max(aw, bw))


def _side_by_side(a: tuple[int, int, int, int, int],
                  b: tuple[int, int, int, int, int]) -> bool:
    """Do these two whites sit at the same height, next to each other?

    Stacked, far apart, or one above the other is not a face.
    """
    ax, ay, aw, ah, _ = a
    bx, by, bw, bh, _ = b
    if abs(ay - by) > 0.60 * max(ah, bh):
        return False
    gap = max(ax, bx) - min(ax + aw, bx + bw)
    return -0.20 * max(aw, bw) < gap < 2.6 * max(aw, bw)


def _assert_not_lopsided(grey: np.ndarray, boxes: list, what: str) -> None:
    """The defect that used to hide inside "no pair found".

    Draft three. Found while investigating the blank eye published on
    2026-09-01, though it is NOT what let that deck out — that was
    fresh_poses.py never calling this gate at all, and those two eyes were the
    same size, so draft two would have caught them. This is the neighbouring
    hole the investigation walked into.

    The hole: the defect DISABLES the detector. Two whites of unequal size are
    not a matched pair, no matched pair is found, and "no pair found" is the
    branch that returns clean for winks and profiles. So the wronger the eye
    is, the more certainly it passed. Measured by blanking one eye and growing
    it 1.6x on the 100 library poses that carry a plain two-eye face, draft two
    missed 32 and this catches 99.

    So a lopsided pair is judged here rather than skipped. The position tests
    still have to hold — same height, side by side, both eye-shaped and
    eye-sized against the figure — and on top of that exactly one of the two
    must carry a pupil. That last condition is what keeps a prop out: it
    anchors one blob as a real eye and asks what is sitting beside it. Two
    blank whites stay unjudged, because that is the train-window case from
    draft two and a pair of props is exactly what it looks like.

    Measured against all 188 library poses, this check refuses none of them.
    The three the gate does refuse — `guarded`, `chasing`, `lab_coat` — are
    draft two's known cost and are unchanged by this.
    """
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if _matched_size(a, b) or not _side_by_side(a, b):
                continue
            pa, pb = _pupil_centre(grey, a), _pupil_centre(grey, b)
            if (pa is None) == (pb is None):
                continue                       # both blank, or both fine
            blank, seeing = (a, b) if pa is None else (b, a)
            raise QAFailure(
                f"pupils: {what} has two eye whites side by side at the same "
                f"height, {blank[2]}x{blank[3]} and {seeing[2]}x{seeing[3]}, and "
                f"the {blank[2]}x{blank[3]} one is blank. A face with one eye "
                f"drawn wrong is still a face with one eye drawn wrong. "
                f"Re-roll with another seed.")


def assert_has_pupils(rgba: np.ndarray, what: str) -> None:
    """Refuse a pose whose eyes came back blank, mismatched or crooked.

    Written twice, and the first version is why this docstring is long.

    Draft one asked "is there a bright blob, and does one of them contain
    something dark". It refused five real library poses, because the cream
    muzzle is bright. Measured, the library cream sits at saturation 73-94 and
    an eye white is near zero, so the mask now demands that white be white.

    Draft two still passed a train-window scene with two blank eyes. The reason
    is the useful one: the picture contained a WINDOW, 135x279 of pale glass,
    which is blob-shaped, white, and in the upper half of the frame. It was
    counted as an eye, something dark inside it satisfied "at least one has a
    pupil", and a prop rescued a face that had none. A fridge, a sink, a plate
    and a laptop screen do the same thing.

    So the unit here is the PAIR, not the blob. Two whites of similar size,
    sitting side by side at the same height, is a shape a prop does not
    accidentally make, and it is what a face actually looks like. Both must
    carry a pupil, and the two pupils must sit at roughly the same height —
    crooked pupils are the other way a generated face reads as wrong, and
    draft two could not see them at all.

    Draft three is _assert_not_lopsided below, and it closes the hole draft two
    left: "no matched pair" was treated as "nothing to judge", so an eye drawn
    the wrong SIZE disabled the very check that would have caught it.

    When no pair of any kind is found the gate still passes. That is deliberate
    and it is the limit of what this can honestly claim: a closed-eye pose, a
    wink and a profile all legitimately show no pair, and refusing them would
    refuse good art to catch bad art. The gate's promise is narrow and complete
    — IF two eye whites are visible side by side, THEN both are correct.
    """
    if rgba.shape[2] < 4:
        return
    grey = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2GRAY)
    boxes = _eye_candidates(rgba)

    pair = None
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if not _matched_size(a, b):
                continue                       # eyes are a matched pair
            if not _side_by_side(a, b):
                continue                       # at the same height, not stacked or far apart
            pair = (a, b) if a[0] < b[0] else (b, a)
            break
        if pair:
            break

    if pair is None:
        # Not "clean" — only "no matched pair". An eye drawn the wrong SIZE
        # lands here too, and it used to leave unjudged.
        _assert_not_lopsided(grey, boxes, what)
        return                                  # closed, winking or in profile

    left, right = pair
    pupils = [_pupil_centre(grey, box) for box in pair]
    blank = [side for side, p in zip(("left", "right"), pupils) if p is None]
    if blank:
        raise QAFailure(
            f"pupils: {what} has a pair of eye whites and the {' and '.join(blank)} "
            f"one is blank. Both eyes must carry a pupil. Re-roll with another seed.")

    # Crookedness is measured INSIDE each eye, not against the horizon.
    #
    # The first attempt compared the two pupils' absolute heights and refused 11
    # real library poses: jumping, leaping, falling, chasing, on_back — every
    # pose where the head is tilted. A tilted head has its eyes at different
    # heights and its pupils with them, and that is correct drawing, not a
    # defect. What is a defect is one pupil sitting high in its own white while
    # the other sits low, which is what a model produces and an illustrator does
    # not. So each pupil is expressed as a fraction of its own eye box, and the
    # two fractions are compared.
    offsets = []
    for (px, py), (bx, by, bw, bh, _) in zip(pupils, (left, right)):
        offsets.append(((px - bx) / bw, (py - by) / bh))
    (lu, lv), (ru, rv) = offsets
    if abs(lv - rv) > 0.30:
        raise QAFailure(
            f"pupils: {what} has one pupil high in its eye and the other low "
            f"({lv:.0%} against {rv:.0%} of the way down). A crooked stare is the "
            f"other way a generated face reads as wrong. Re-roll with another seed.")



# ── brand palette conformance ────────────────────────────────────────────────
#
# BRAND_GREEN_BGR is #3C965A, the body fill named in CHARACTER.md's identity
# invariants, in CIE L*a*b* so distance is perceptual rather than a raw BGR
# difference.
BRAND_GREEN_BGR = (0x5A, 0x96, 0x3C)
MAX_BODY_DELTA = 25.0     # dE76 between the body green and the brand green
MIN_REGION = 0.01         # a green region must be this much of the figure to count


def body_green_delta(rgba: np.ndarray) -> tuple[float, tuple[int, int, int]] | None:
    """How far Silly's own green is from the brand green, and what it measures.

    Returns (dE76, median BGR) for the LARGE green region nearest #3C965A, or
    None if the picture has no substantial green in it at all.

    Two earlier versions of this got it wrong in opposite directions, and both
    failures are the same mistake: measuring the wrong pixels.

    Version one took the MEDIAN of every green pixel. That rejected sage and
    knees_hugged, who are wearing a sage robe and bright green trousers — the
    median was measuring the GARMENT and reporting the character as off-model.
    Wardrobe is a variable slot in CHARACTER.md; a gate that punishes him for
    getting dressed is measuring the wrong thing.

    Version two asked what SHARE of the figure was brand green. That works for a
    cut-out character on an empty backdrop and falls apart the moment the
    artwork is a scene — a donkey reading in bed with a blanket, a lamp and a
    stack of books is mostly not donkey, so the share collapses however good the
    donkey is. It would have refused good artwork for containing furniture.

    What survives both is a question about COLOUR rather than about quantity:
    of the substantial green regions in this picture, how close to #3C965A does
    the nearest one get? A blanket, a houseplant or a hillside adds green
    regions; none of them takes the body away. If the body is on-brand the
    nearest region is the body and the answer is small. If the body has drifted
    then nothing in the picture is Silly's green and the answer is large.

    Calibration, measured over all 180 library poses: median 6.0, p90 13.5,
    p99 14.1, max 24.1. The maximum is knees_hugged, and he is the honest limit
    of this approach — his green trousers TOUCH his green body, so the two merge
    into one connected region whose median sits between them. Regions are found
    by connectivity, so anything the body touches in its own hue is averaged
    into it.

    The limit worth stating plainly: a large prop that happens to be close to
    brand green will satisfy this gate on the body's behalf. It proves the
    picture contains Silly's green, not that the donkey is the thing wearing it.
    """
    if rgba.shape[2] == 4:
        opaque = rgba[..., 3] > 200
        bgr = rgba[..., :3]
    else:
        opaque = np.ones(rgba.shape[:2], bool)
        bgr = rgba
    if opaque.sum() < 500:
        return None
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (((h > 30) & (h < 95) & (s > 60) & (v > 40)) & opaque).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(green, 8)
    if count < 2:
        return None
    spec = cv2.cvtColor(np.uint8([[BRAND_GREEN_BGR]]), cv2.COLOR_BGR2LAB)[0, 0].astype(float)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(float)
    floor = max(200, int(MIN_REGION * opaque.sum()))
    best = None
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < floor:
            continue
        m = labels == i
        delta = float(np.linalg.norm(np.median(lab[m], 0) - spec))
        if best is None or delta < best[0]:
            best = (delta, tuple(int(c) for c in np.median(bgr[m], 0)))
    return best


def assert_on_palette(rgba: np.ndarray, what: str) -> None:
    """Refuse a figure whose green is not Silly's green.

    The floor is 25, and every real library pose clears it — the highest is
    knees_hugged at 24.1. See body_green_delta() for what is measured and for
    the two earlier versions of this gate that measured the wrong pixels.
    """
    found = body_green_delta(rgba)
    if found is None:
        raise QAFailure(
            f"palette: {what} contains no substantial green region at all — "
            f"whatever this is, it is not Silly")
    delta, bgr = found
    if delta > MAX_BODY_DELTA:
        hexcode = f"#{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X}"
        raise QAFailure(
            f"palette: the nearest large green in {what} is {hexcode}, {delta:.0f} "
            f"dE from the brand green #3C965A (limit {MAX_BODY_DELTA:.0f}). Every "
            f"real library pose clears this, the worst at 24.1. Re-generate on "
            f"the brand colour; do not raise the limit")
