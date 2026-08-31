#!/usr/bin/env python3
"""
imaging.py — shared cutout helpers used by the import pipeline.

These were extracted from the old sprite-sheet slicer. That slicer is gone: the
whole library is generated art now, and leaving it in place was a hazard —
running it would have written 24 obsolete bust poses over the live library,
including a `deadpan` that would have replaced the good one.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def drop_neighbour_bleed(rgba: np.ndarray) -> np.ndarray:
    """Delete small blobs sliced in from an adjacent grid cell.

    A fragment is neighbour bleed when it is small, touches a side edge, and
    does not overlap the main subject's horizontal span. Detached artwork that
    belongs to the pose — sweat drops, hearts, a held trophy — sits within that
    span and survives.
    """
    alpha = (rgba[:, :, 3] > 128).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
    if n <= 2:
        return rgba
    areas = [(i, stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)]
    main = max(areas, key=lambda t: t[1])[0]
    mx, mw = stats[main, cv2.CC_STAT_LEFT], stats[main, cv2.CC_STAT_WIDTH]
    W = rgba.shape[1]

    keep = np.ones(n, bool)
    for i, area in areas:
        if i == main or area >= 0.06 * stats[main, cv2.CC_STAT_AREA]:
            continue
        x, w = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_WIDTH]
        touches_side = x <= 1 or x + w >= W - 1
        outside_main = x + w < mx or x > mx + mw
        if touches_side and outside_main:
            keep[i] = False
    if keep.all():
        return rgba
    out = rgba.copy()
    out[:, :, 3] = np.where(keep[labels], rgba[:, :, 3], 0)
    return out



def tight_crop(rgba: np.ndarray, pad: int = 4) -> np.ndarray:
    ys, xs = np.where(rgba[:, :, 3] > 20)
    if len(ys) == 0:
        return rgba
    t, b = max(0, ys.min() - pad), min(rgba.shape[0], ys.max() + 1 + pad)
    l, r = max(0, xs.min() - pad), min(rgba.shape[1], xs.max() + 1 + pad)
    return rgba[t:b, l:r]



def contact_sheet(out: Path, cols: int = 6) -> Path:
    """Every pose on a checkerboard, so alpha quality is inspectable at a glance."""
    files = sorted(f for f in out.glob("*.png") if not f.stem.startswith("_"))
    TW, TH = 220, 240
    tiles = []
    for f in files:
        im = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        a = im[:, :, 3:4].astype(np.float32) / 255.0
        ck = np.indices(im.shape[:2]).sum(0) // 12 % 2
        bgc = np.where(ck[..., None] == 0, 235, 205).astype(np.uint8).repeat(3, axis=2)
        comp = (im[:, :, :3] * a + bgc * (1 - a)).astype(np.uint8)
        h, w = comp.shape[:2]
        sc = min((TW - 14) / w, (TH - 34) / h)
        comp = cv2.resize(comp, (int(w * sc), int(h * sc)))
        tile = np.full((TH, TW, 3), 250, np.uint8)
        y0 = (TH - 24 - comp.shape[0]) // 2 + 18
        x0 = (TW - comp.shape[1]) // 2
        tile[y0:y0 + comp.shape[0], x0:x0 + comp.shape[1]] = comp
        cv2.putText(tile, f.stem, (6, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (40, 40, 40), 1, cv2.LINE_AA)
        tiles.append(cv2.copyMakeBorder(tile, 1, 1, 1, 1, cv2.BORDER_CONSTANT,
                                        value=(200, 200, 200)))
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 250))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    dest = out / "_contact_sheet.png"
    cv2.imwrite(str(dest), np.vstack(rows))
    return dest




# ── the judging sheet ────────────────────────────────────────────────────────
#
# contact_sheet() above answers "is the alpha clean" — it composites on a
# checkerboard, which is the right ground for seeing a halo and the wrong one
# for every other question. It also globs a whole directory and writes its
# result back into it, so the only way to look at a new pose was to add it to
# the library first.
#
# This one answers the question that actually decides an import: does this pose
# belong beside the ones already there, on the grounds it will really be
# printed on. Nothing here writes to the library.
#
# The grounds are lifted from render.py's THEMES. `forest` is in the list on
# purpose and is the hard case: it is #2F6B4F, and Silly's body is #3C965A — a
# green character on a green ground, which is where a drifted or muddy cutout
# stops reading as a silhouette at feed size.
JUDGING_GROUNDS = [
    ("terracotta", "#D0522A"),
    ("forest", "#2F6B4F"),
    ("charcoal", "#1E1E1E"),
]

# Fixed, so two runs of the same sheet are comparable. These are the poses
# poses.json names as role defaults — the closest thing the library has to a
# statement of what "on-model" looks like.
STYLE_ANCHORS = ["deadpan", "explaining", "welcoming"]


def _hex_bgr(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def _on(rgba: np.ndarray, bgr: tuple[int, int, int], box: tuple[int, int]) -> np.ndarray:
    """Composite a pose onto a solid ground, letterboxed into box (w, h)."""
    bw, bh = box
    tile = np.zeros((bh, bw, 3), np.uint8)
    tile[:, :] = bgr
    if rgba is None or rgba.size == 0:
        return tile
    s = min((bw - 12) / rgba.shape[1], (bh - 12) / rgba.shape[0])
    w, h = max(1, int(rgba.shape[1] * s)), max(1, int(rgba.shape[0] * s))
    r = cv2.resize(rgba, (w, h), interpolation=cv2.INTER_AREA)
    a = r[:, :, 3:4].astype(np.float32) / 255.0
    y, x = (bh - h) // 2, (bw - w) // 2
    tile[y:y + h, x:x + w] = (r[:, :, :3] * a + tile[y:y + h, x:x + w] * (1 - a)).astype(np.uint8)
    return tile


def _label(w: int, text: str, h: int = 26, ink=(40, 40, 40), paper=250) -> np.ndarray:
    strip = np.full((h, w, 3), paper, np.uint8)
    cv2.putText(strip, text[:120], (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                ink, 1, cv2.LINE_AA)
    return strip


def judging_sheet(entries: list[dict], library: Path, dest: Path) -> Path:
    """One row per candidate: the pose on three real slide grounds, then the
    style anchors on the same grounds for comparison, then the gate verdicts.

    `entries` is a list of {name, rgba, verdicts: list[str], ok: bool}.
    """
    CW, CH = 240, 300
    anchors = []
    for a in STYLE_ANCHORS:
        p = library / f"{a}.png"
        if p.is_file():
            anchors.append((a, cv2.imread(str(p), cv2.IMREAD_UNCHANGED)))

    grounds = [(n, _hex_bgr(h)) for n, h in JUDGING_GROUNDS]
    rows = []

    # A library with no anchors in it is a real case — a fresh checkout, or a
    # test with a tmp library — and a zero-width tile crashes cv2. The sheet is
    # still worth writing without the comparison column.
    header = [_label(CW * len(grounds), "NEW  —  " + " · ".join(n for n, _ in grounds), 30)]
    if anchors:
        header.append(np.full((30, 16, 3), 250, np.uint8))
        header.append(_label(CW * len(anchors),
                             "LIBRARY  —  " + " · ".join(n for n, _ in anchors), 30))
    rows.append(np.hstack(header))

    for e in entries:
        cells = [_on(e["rgba"], g, (CW, CH)) for _, g in grounds]
        if anchors:
            gap = np.full((CH, 16, 3), 250, np.uint8)
            # anchors are shown on the FIRST ground only, at the same box, so
            # the comparison is like for like: same scale, same background,
            # same crop.
            cells += [gap] + [_on(img, grounds[0][1], (CW, CH)) for _, img in anchors]
        rows.append(np.hstack(cells))
        width = sum(c.shape[1] for c in cells)
        verdict = ("PASS  " if e["ok"] else "REJECT  ") + e["name"]
        ink = (30, 120, 30) if e["ok"] else (30, 30, 200)
        rows.append(_label(width, verdict, 26, ink))
        for line in e["verdicts"]:
            rows.append(_label(width, "    " + line, 22, (90, 90, 90)))
        rows.append(np.full((10, width, 3), 250, np.uint8))

    width = max(r.shape[1] for r in rows)
    rows = [r if r.shape[1] == width else
            np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)), constant_values=250)
            for r in rows]
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), np.vstack(rows))
    return dest
