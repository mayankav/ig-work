#!/usr/bin/env python3
"""
mascot_svg.py — Silly as a parametric vector rig.

An experiment against the raster library. Raster cutouts inherit whatever the
generator drew: a soft rim that has to be matted, streaks inside the ears, marks
in the eyes. A rig has none of those failure modes — the edges are exact by
construction, transparency is real, and a pose is a set of numbers rather than
a new image to matte and check.

Colours come from CHARACTER.md. Geometry is on a 520x900 viewBox.
"""

from __future__ import annotations

import argparse
from pathlib import Path

GREEN = "#3C965A"
GREEN_DK = "#31804A"
CREAM = "#FAD2AA"
BLACK = "#141414"
WHITE = "#FFFFFF"
EAR_IN = "#2E7A47"

W, H = 520, 900


def _mane_crown(cx: float, cy: float, r: float, n: int = 9) -> str:
    """The signature: overlapping dark discs, not a solid cap."""
    import math
    out = []
    for i in range(n):
        t = math.pi * (0.06 + 0.88 * i / (n - 1))
        x = cx - math.cos(t) * r * 0.98
        y = cy - math.sin(t) * r * 0.52
        rr = r * (0.30 if i % 2 else 0.34)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}"/>')
    return "".join(out)


def _mane_neck(x: float, y0: float, y1: float, r: float, n: int = 7) -> str:
    out = []
    for i in range(n):
        y = y0 + (y1 - y0) * i / (n - 1)
        rr = r * (1.0 - 0.30 * i / (n - 1))
        out.append(f'<circle cx="{x + i * 1.4:.1f}" cy="{y:.1f}" r="{rr:.1f}"/>')
    return "".join(out)


def build(pose: dict) -> str:
    arm_l = pose.get("arm_l", -14)
    arm_r = pose.get("arm_r", 14)
    eye = pose.get("eye", "open")
    mouth = pose.get("mouth", "flat")
    brow = pose.get("brow", 0)
    head_tilt = pose.get("head", 0)
    body = pose.get("body", GREEN)

    if eye == "closed":
        eyes = (f'<path d="M188 336 q22 16 44 0" stroke="{BLACK}" stroke-width="9" '
                f'fill="none" stroke-linecap="round"/>'
                f'<path d="M292 336 q22 16 44 0" stroke="{BLACK}" stroke-width="9" '
                f'fill="none" stroke-linecap="round"/>')
    else:
        px = {"left": -13, "right": 13, "up": 0}.get(pose.get("look", ""), 0)
        py = -10 if pose.get("look") == "up" else 0
        eyes = (f'<ellipse cx="210" cy="332" rx="34" ry="38" fill="{WHITE}"/>'
                f'<ellipse cx="314" cy="332" rx="34" ry="38" fill="{WHITE}"/>'
                f'<circle cx="{210+px}" cy="{338+py}" r="14" fill="{BLACK}"/>'
                f'<circle cx="{314+px}" cy="{338+py}" r="14" fill="{BLACK}"/>')

    if mouth == "smile":
        m = f'<path d="M226 470 q30 26 60 0" stroke="{BLACK}" stroke-width="8" fill="none" stroke-linecap="round"/>'
    elif mouth == "open":
        m = f'<ellipse cx="256" cy="474" rx="26" ry="19" fill="{BLACK}"/>'
    elif mouth == "frown":
        m = f'<path d="M226 480 q30 -24 60 0" stroke="{BLACK}" stroke-width="8" fill="none" stroke-linecap="round"/>'
    else:
        m = f'<rect x="228" y="468" width="58" height="8" rx="4" fill="{BLACK}"/>'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<g fill="{body}">
  <path d="M150 210 C138 120 150 60 172 48 C196 36 214 92 220 176 Z"/>
  <path d="M370 210 C382 120 370 60 348 48 C324 36 306 92 300 176 Z"/>
</g>
<g fill="{EAR_IN}">
  <path d="M166 196 C158 126 166 82 178 74 C192 66 202 112 206 178 Z"/>
  <path d="M354 196 C362 126 354 82 342 74 C328 66 318 112 314 178 Z"/>
</g>
<g transform="rotate({head_tilt} 260 340)">
  <rect x="470" y="560" width="0" height="0"/>
  <path d="M132 300 C132 196 186 150 260 150 C334 150 388 196 388 300
           L388 430 C388 512 334 556 260 556 C186 556 132 512 132 430 Z" fill="{body}"/>
  <ellipse cx="256" cy="452" rx="104" ry="82" fill="{CREAM}"/>
  <ellipse cx="222" cy="424" rx="9" ry="15" fill="{BLACK}"/>
  <ellipse cx="290" cy="424" rx="9" ry="15" fill="{BLACK}"/>
  {m}
  {eyes}
  <rect x="176" y="{272 + brow}" width="172" height="19" rx="9" fill="{BLACK}"/>
  <g fill="{BLACK}">{_mane_crown(262, 232, 96)}</g>
  <g fill="{BLACK}">{_mane_neck(372, 268, 470, 27)}</g>
</g>
<path d="M196 560 L324 560 C356 560 372 588 372 626 L372 742
         C372 782 348 800 314 800 L206 800 C172 800 148 782 148 742
         L148 626 C148 588 164 560 196 560 Z" fill="{body}"/>
<ellipse cx="260" cy="700" rx="66" ry="60" fill="{CREAM}"/>
<g fill="{body}">
  <g transform="rotate({arm_l} 176 606)">
    <rect x="118" y="592" width="66" height="150" rx="33"/>
    <circle cx="151" cy="742" r="33" fill="{BLACK}"/>
  </g>
  <g transform="rotate({arm_r} 344 606)">
    <rect x="336" y="592" width="66" height="150" rx="33"/>
    <circle cx="369" cy="742" r="33" fill="{BLACK}"/>
  </g>
</g>
<g fill="{body}">
  <rect x="188" y="778" width="60" height="104" rx="28"/>
  <rect x="272" y="778" width="60" height="104" rx="28"/>
</g>
<g fill="{BLACK}">
  <ellipse cx="218" cy="874" rx="36" ry="22"/>
  <ellipse cx="302" cy="874" rx="36" ry="22"/>
</g>
<path d="M372 700 q60 20 62 66" stroke="{body}" stroke-width="15" fill="none" stroke-linecap="round"/>
<circle cx="436" cy="772" r="20" fill="{BLACK}"/>
</svg>'''


POSES = {
    "deadpan":   dict(eye="open", mouth="flat", brow=0, arm_l=-8, arm_r=8),
    "welcoming": dict(eye="open", mouth="open", brow=-6, arm_l=-72, arm_r=72),
    "serene":    dict(eye="closed", mouth="smile", brow=-4, arm_l=-6, arm_r=6),
    "watchful":  dict(eye="open", look="left", mouth="flat", brow=4, arm_l=-4, arm_r=4),
    "realising": dict(eye="open", look="up", mouth="open", brow=-8, arm_l=-96, arm_r=10),
    "clutching": dict(eye="open", mouth="frown", brow=6, arm_l=-34, arm_r=34, head=-3),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pose", nargs="?", default="deadpan", choices=sorted(POSES))
    ap.add_argument("-o", "--out")
    ap.add_argument("--grey", action="store_true", help="the partner colourway")
    a = ap.parse_args()
    p = dict(POSES[a.pose])
    if a.grey:
        p["body"] = "#757A77"
    svg = build(p)
    dest = Path(a.out) if a.out else Path(f"{a.pose}.svg")
    dest.write_text(svg)
    print(f"{dest}  {len(svg)} bytes")


if __name__ == "__main__":
    main()
