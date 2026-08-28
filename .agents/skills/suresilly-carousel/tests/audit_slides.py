#!/usr/bin/env python3
"""
audit_slides.py — adversarial check of RENDERED slides.

Everything else in tests/ inspects inputs. This inspects the actual PNGs a
reader would see, because every defect that has shipped so far was invisible to
the input checks: a clipped hoof, a colour field slicing a paragraph, a figure
overlapping type, dead space that reads as unfinished.

    audit_slides.py carousels/<slug>/slides
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import cv2
import numpy as np

W, H = 1080, 1350
MARGIN, FOOTER_H = 92, 132


# Measured on real slides: ground and grid sit under 15 from the background,
# the colour field around 32, and type and figure above 90. A threshold of 70
# sees content and ignores decoration — at 26 the audit flagged every slide,
# because the field is full-bleed by design.
CONTENT_DELTA = 70


def ink_mask(img: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """Type and figure only, not the background decoration."""
    return (np.abs(img.astype(np.int16) - bg).max(2) > CONTENT_DELTA).astype(np.uint8)


def audit(path: pathlib.Path) -> list[str]:
    img = cv2.imread(str(path))
    if img is None:
        return [f"unreadable"]
    out: list[str] = []
    h, w = img.shape[:2]
    if (w, h) != (W, H):
        out.append(f"wrong size {w}x{h}")

    bg = np.median(img[4:12, 4:12].reshape(-1, 3), axis=0)
    ink = ink_mask(img, bg)

    # 1 · content running off the canvas
    for name, run, span in (("top", ink[2], w), ("bottom", ink[-3], w),
                            ("left", ink[:, 2], h), ("right", ink[:, -3], h)):
        n = int(run.sum())
        if n > 0.02 * span:
            out.append(f"content bleeds off the {name} edge ({100*n/span:.0f}%)")

    # 2 · dead space: the largest band of rows with almost nothing in them
    rows = ink.sum(1)
    live = rows > 0.012 * w
    best = run = 0
    start = beststart = 0
    for y in range(MARGIN, H - FOOTER_H):
        if not live[y]:
            if run == 0:
                start = y
            run += 1
            if run > best:
                best, beststart = run, start
        else:
            run = 0
    if best > 300:
        out.append(f"dead band of {best}px from y={beststart}")

    # 3 · how much of the usable frame carries anything at all
    usable = ink[MARGIN:H - FOOTER_H, MARGIN:W - MARGIN]
    fill = usable.mean()
    if fill < 0.14:
        out.append(f"only {fill:.0%} of the frame is used")

    # 4 · type crowding the footer rule
    if ink[H - FOOTER_H - 10:H - FOOTER_H, MARGIN:W - MARGIN].mean() > 0.30:
        out.append("content crowds the footer rule")

    # 5 · a figure whose limb is cut by the frame. Bottom contact is the ground
    #     line and expected; the sides and top are not.
    # The figure is whatever differs strongly from THIS slide's own ground —
    # an absolute green test caught the ground itself and called every edge of
    # the call-to-action slide clipped.
    green = ink
    for name, run, span in (("left", green[:, 1], h), ("right", green[:, -2], h),
                            ("top", green[1], w)):
        n = int(run.sum())
        if n > 0.02 * span:
            out.append(f"figure clipped by the {name} edge ({n}px)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    a = ap.parse_args()
    slides = sorted(pathlib.Path(a.folder).glob("*.png"))
    if not slides:
        sys.exit(f"no slides in {a.folder}")
    bad = 0
    for s in slides:
        issues = audit(s)
        if issues:
            bad += 1
            print(f"  {s.name}")
            for i in issues:
                print(f"      - {i}")
    print(f"\n{len(slides) - bad}/{len(slides)} slides clean")


if __name__ == "__main__":
    main()
