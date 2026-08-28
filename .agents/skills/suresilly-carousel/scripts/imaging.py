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


