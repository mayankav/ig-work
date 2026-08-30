#!/usr/bin/env python3
"""
Layout regression tests.

Every case covers a fault that shipped and was caught only by eye:
  · a wide pose sized for a side column overlapped the copy
  · a banner reserved 273px for a figure that rendered 614px tall
  · the corner badge landed on the eyebrow
  · a green character on a green ground, invisible
The QA gates cannot see any of these — they only inspect cutouts.
"""
import pathlib
import sys

from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402

LIB = pathlib.Path(__file__).resolve().parent.parent / "mascot" / "library"
FAIL = []


def check(name, ok, detail):
    print(f"  {'✓' if ok else '✗✗'} {name:38s} {detail}")
    if not ok:
        FAIL.append(name)


def lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def contrast(a, b):
    l1, l2 = sorted([lum(a), lum(b)], reverse=True)
    return (l1 + .05) / (l2 + .05)


def hue(h):
    import colorsys
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


poses = sorted(p for p in LIB.glob("*.png") if not p.stem.startswith("_"))
print(f"=== the figure never eats the copy zone ({len(poses)} poses) ===")
least = ("", 10_000)
for mode, h in (("bleed", 760), ("type", 650)):
    for p in poses:
        with Image.open(p) as im:
            iw, ih = im.size
        wide = iw / ih > 1.0
        mh = min(int(h * 1.2), render.BANNER_MAX_H) if wide else h
        copy_h = render.H - render.MARGIN - render.FOOTER_H - mh - 22
        if copy_h < least[1]:
            least = (f"{mode}/{p.stem}", copy_h)
check("copy always has room", least[1] >= 300, f"least {least[1]}px at {least[0]}")
check("banner height capped", render.BANNER_MAX_H <= 400, f"{render.BANNER_MAX_H}px")

print("\n=== the character is never lost in the ground ===")
CHAR = "#3C965A"
bad = []
for n in render.BLEED_THEMES + render.PAPER_THEMES:
    g = render.THEMES[n]["ground"]
    dh = abs(hue(g) - hue(CHAR))
    dh = min(dh, 360 - dh)
    if dh < 40 and contrast(g, CHAR) < 1.7:
        bad.append(f"{n} (hue {dh:.0f}deg, {contrast(g, CHAR):.2f}x)")
check("no ground shares the character's hue", not bad, bad or "all clear")

print("\n=== every selectable theme is legible ===")
# The bar is what already ships: terracotta is the weakest original at 4.02
# ink-on-ground and ochre the weakest accent at 2.82. A new theme may not be
# worse than the worst thing already in the rotation.
dim, faint = [], []
for n in render.BLEED_THEMES + render.PAPER_THEMES:
    t = render.THEMES[n]
    if contrast(t["ink"], t["ground"]) < 4.0:
        dim.append(f'{n} ({contrast(t["ink"], t["ground"]):.2f}x)')
    if contrast(t["accent"], t["ground"]) < 2.8:
        faint.append(f'{n} ({contrast(t["accent"], t["ground"]):.2f}x)')
check("body ink survives its ground", not dim, dim or "all >=4.0x")
check("accent survives its ground", not faint, faint or "all >=2.8x")
missing = [n for n in render.BLEED_THEMES + render.PAPER_THEMES
           if n not in render.THEMES]
check("every rotation entry exists", not missing, missing or "all defined")
TOKENS = {"ground", "field", "ink", "soft", "accent", "cardink", "card",
          "grid", "badge_ink"}
short = [n for n, t in render.THEMES.items() if TOKENS - set(t)]
check("every theme is a complete token set", not short, short or "all complete")

print("\n=== plain-English colour requests ===")
# Each of these silently resolved to the wrong colour, or to nothing, before
# COLOR_ALIASES existed. "deep blue" shipping a terracotta deck is the one
# that was actually caught by eye.
CASES = {"blue": "cobalt", "deep blue": "midnight", "navy": "midnight",
         "slate blue": "indigo", "light blue": "mist", "reddish": "terracotta",
         "dark red": "wine", "pinkish": "blush", "purple": "plum",
         "teal": "teal", "greenish": "sagetint", "black": "charcoal",
         "Oatmeal #F5F4F0": "oatmeal", "a really dark red": "wine"}
wrong = [f"{w!r}->{(render.resolve_color_word(w) or (None, None))[1]} want {want}"
         for w, want in CASES.items()
         if (render.resolve_color_word(w) or (None, None))[1] != want]
check("colour words land on the right theme", not wrong, wrong or f"{len(CASES)} cases")
unknown = [w for w in ("banana", "", "Accent #FFD9A0")
           if render.resolve_color_word(w) is not None]
check("a non-colour resolves to nothing", not unknown, unknown or "None, as expected")
bad_slot = [f"{w}->{t}" for w, (slot, t) in render.COLOR_ALIASES.items()
            if (t not in render.BLEED_THEMES if slot == "bleed"
                else t not in render.PAPER_THEMES and t != "sagetint")]
check("every alias points into its own slot", not bad_slot, bad_slot or "all valid")

print("\n=== unnamed colours rotate instead of repeating ===")
import tempfile  # noqa: E402

_orig = render.PALETTE_HISTORY_PATH
render.PALETTE_HISTORY_PATH = pathlib.Path(tempfile.mkdtemp()) / "ph.json"
seq = []
for i in range(len(render.BLEED_THEMES) + 2):
    b, p = render._round_robin_palette(exclude_slug=None)
    seq.append(b)
    render.record_palette(f"deck{i:02d}", b, p)
render.PALETTE_HISTORY_PATH = _orig
n_bleed = len(render.BLEED_THEMES)
check("a full cycle before any repeat", len(set(seq[:n_bleed])) == n_bleed,
      f"{len(set(seq[:n_bleed]))}/{n_bleed} distinct")
check("never twice in a row", all(a != b for a, b in zip(seq, seq[1:])),
      " ".join(seq[:5]) + " …")

print("\n=== the deck holds to two colours ===")
roles = ["hook", "agitation", "source", "value", "script", "value", "value", "cheat", "cta"]
pal = render.deck_palette("carousels/x/carousel.md")
themes = [render.theme_for(render.layout_for(r, i), pal) for i, r in enumerate(roles)]
check("at most two", len(set(themes)) <= 2, f"{len(set(themes))}: {', '.join(sorted(set(themes)))}")

print("\n=== one type scale, no per-slide resizing ===")
check("scale is a fixed table", isinstance(render.TYPE, dict) and len(render.TYPE) >= 8,
      f"{len(render.TYPE)} levels")
check("auto-fit is gone", not hasattr(render, "AUTOFIT"), "figure absorbs variation, not type")

print("\n=== no template silently drops written copy ===")
# Template C printed neither the H2 nor the Body. The writer produced both, the
# critic reviewed a deck containing both, and they never reached the PNG — so a
# script slide arrived with no headline while every other slide in the set had
# one. Nothing could see it: the QA gates inspect cutouts, and the copy gates
# read the markdown, which was correct. Only the render threw it away.
#
# Checked for every template rather than for C, because the next one added will
# be written the same way, by copying a branch.
import re as _re

_TEMPLATES = {
    "Template A": {},
    "Template C": {"old_reaction": "You are asked at 4pm.", "new_reaction": "Let me check."},
    "Template D": {"bullets": ["one", "two"]},
    "Template G": {"old_reaction": "I said yes.", "new_reaction": "I said maybe."},
    "Template H": {"bullets": ["a", "b", "c", "d"]},
    "Template I": {"bullets": ["first", "second"]},
    "Template J": {"myth": "Rest is earned.", "reality": "Rest is not earned."},
}
for _name, _extra in sorted(_TEMPLATES.items()):
    _slide = {"role": "value", "layout": _name,
              "h2": "The zebra heading.", "body": "A walrus explains the whole thing.", **_extra}
    _html = render.slide_html(_slide, 5, 9, None, 5, ("indigo", "oatmeal"))
    _text = " ".join(_re.sub(r"<[^>]+>", " ", _html).split())
    _lost = [k for k in ("h2", "body") if " ".join(_slide[k].split()[:3]) not in _text]
    check(f"{_name} keeps its h2 and body", not _lost,
          "both printed" if not _lost else f"DROPPED {', '.join(_lost)}")

# The cheat sheet's callout. Required by the writer's schema, asked for by name
# in the playbook, and unreachable in the renderer for the life of the repo —
# its guard was `idx == total`, and the last slide is always the CTA, which
# never reaches that line. Seven decks wrote one and none of them printed it.
_cheat = {"role": "cheat sheet", "layout": "Template D", "h2": "Your card.",
          "bullets": ["one", "two"], "callout": "Screenshot this for later."}
_cheat_html = render.slide_html(_cheat, 8, 9, None, 8, ("indigo", "oatmeal"))
check("the cheat sheet prints its callout", "Screenshot this for later." in _cheat_html,
      "pill rendered" if "Screenshot this for later." in _cheat_html else "DROPPED")

print()
if FAIL:
    raise SystemExit(f"FAILED: {', '.join(FAIL)}")
print("all layout cases passed")
