#!/usr/bin/env python3
"""
trace_svg.py — turn a flat raster pose into clean vector paths.

The library art is flat colour with hard edges, which is the ideal case for
tracing. This keeps the exact character while removing every raster failure
mode at once: no matte to compute, so no coloured rim; no resampling, so no
streaks; no fixed resolution, so no soft edge at any size. About 25x smaller
than the PNG, and each colour region becomes a path you can recolour.

    trace_svg.py deadpan                 # one pose
    trace_svg.py --all --out mascot/vector
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

SKILL_DIR = Path(__file__).resolve().parent.parent
LIBRARY = SKILL_DIR / "mascot" / "library"


def trace(png: Path, n_colors: int = 7, simplify: float = 1.2) -> str:
    im = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if im is None or im.shape[2] != 4:
        raise SystemExit(f"ERROR: {png} is not an RGBA cutout")
    bgr, alpha = im[:, :, :3], im[:, :, 3]
    solid = alpha > 128
    h, w = bgr.shape[:2]

    # cluster to the art's real palette — it only ever uses a handful of flats
    px = bgr[solid].reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 0.8)
    _, lab, cen = cv2.kmeans(px, n_colors, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    cen = cen.astype(np.uint8)
    full = np.full((h, w), -1, np.int32)
    full[solid] = lab.ravel()

    parts = []
    # largest first, so base shapes are painted underneath the details
    for i in sorted(range(n_colors), key=lambda k: -(full == k).sum()):
        mask = (full == i).astype(np.uint8)
        if mask.sum() < 40:
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        # Grow only the BASE regions by 1px so neighbours overlap rather than
        # butt up — tiled regions leave a hairline of background between them.
        # Details sit on top and must keep their true size; fattening those
        # haloed the eye whites.
        if mask.sum() > 0.03 * solid.sum():
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        cnts, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        d = []
        for c in cnts:
            if cv2.contourArea(c) < 24:
                continue
            ap = cv2.approxPolyDP(c, simplify, True).reshape(-1, 2)
            if len(ap) >= 3:
                d.append("M" + " ".join(f"{x},{y}" for x, y in ap) + "Z")
        if d:
            b, g, r = cen[i]
            parts.append(f'<path fill="#{r:02X}{g:02X}{b:02X}" '
                         f'fill-rule="evenodd" d="{"".join(d)}"/>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" shape-rendering="geometricPrecision">'
            + "".join(parts) + "</svg>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pose", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=str(SKILL_DIR / "mascot" / "vector"))
    ap.add_argument("--colors", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    srcs = (sorted(p for p in LIBRARY.glob("*.png") if not p.stem.startswith("_"))
            if a.all else [LIBRARY / f"{a.pose}.png"])
    if not a.all and not srcs[0].is_file():
        raise SystemExit(f"ERROR: no such pose: {a.pose}")

    tot_svg = tot_png = 0
    for src in srcs:
        svg = trace(src, a.colors)
        (out / f"{src.stem}.svg").write_text(svg)
        tot_svg += len(svg)
        tot_png += src.stat().st_size
        if not a.all:
            print(f"  {src.stem}: {len(svg)/1024:.1f} KB svg "
                  f"(png was {src.stat().st_size/1024:.1f} KB)")
    if a.all:
        print(f"{len(srcs)} poses -> {out}")
        print(f"  {tot_svg/1024/1024:.2f} MB of svg vs {tot_png/1024/1024:.2f} MB of png")


if __name__ == "__main__":
    main()
