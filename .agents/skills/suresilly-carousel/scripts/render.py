#!/usr/bin/env python3
"""
render.py — turns a @suresilly carousel markdown script into 1080x1350 PNG slides.

Design system lives in references/design-system.md; this file is its executable
form. The layout alternates two modes across a deck so the grid has rhythm:

  BLEED  a saturated ground with the character huge and cropped by the frame,
         the headline sitting on colour. Loud. Short copy only.
  TYPE   a light ground where the headline IS the graphic at 130px+, with the
         character overlapping it and a rotated badge anchoring the corner.

Both carry a generated colour field — a rounded, wedged or orbed block of the
second colour — picked deterministically per slide. Fields are plain CSS
shapes, so a deck never repeats a composition and nothing is stored as an asset.
"""

from __future__ import annotations

import argparse
import base64
import html as html_mod
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_DIR = Path(__file__).resolve().parent.parent
FONT_DIR = SKILL_DIR / "assets" / "fonts"

W, H = 1080, 1350
MARGIN = 92
FOOTER_H = 132
RULE_Y = 96
BANNER_MAX_H = 380
# Minimum internal breathing room — guarantees the type block never kisses
# the viewport edge, even when FIT_FIGURE centers short copy. Applied as
# padding inside .canvas so getBoundingClientRect() measurements stay true.
CANVAS_PAD_TOP = 36
CANVAS_PAD_BOTTOM = 36
# Source slides carry a dense 3-block stack (kicker + line ×3 + credit) and
# need a touch more headroom than a regular value slide. This is the *total*
# top padding for source (not additive to CANVAS_PAD_TOP).
SOURCE_PAD_TOP = 56
# ── The type scale. Fixed, and identical on every slide of every carousel.
#
# It used to auto-fit: each slide shrank its own text until the copy fitted, so
# the SAME level rendered at 62, 70, 72, 74 and 108px across one deck and
# bullets fell to 24px. That is why nothing looked consistent and why short
# slides looked lost in the frame. A level now has exactly one size, and copy
# that will not fit is reported as a writing problem rather than silently
# shrunk. (size, line-height, letter-spacing)
TYPE = {
    "h1":     (112, 0.94, "-.042em"),   # the hook, once per deck
    "h2":     (86,  0.99, "-.034em"),   # every other slide title
    "lead":   (46,  1.30, "-.008em"),   # the line under a hook
    "body":   (44,  1.38, "-.006em"),
    "bullet": (44,  1.28, "-.006em"),
    "quote":  (54,  1.28, "-.012em"),   # the source slide's hero
    "credit": (27,  1.40, "0"),
    "label":  (23,  1.00, ".22em"),
    "footer": (20,  1.00, ".22em"),
}

# Text first. The copy is laid out at full size and takes whatever room it
# needs; the figure is added only if enough is genuinely left over. Below
# MASCOT_MIN a mascot is not "small", it is an apology — the slide is better
# as pure type.
COPY_MAX_H = 940
MASCOT_MIN, MASCOT_MAX = 470, 900

DISPLAY = "ArchivoBlk"
BODY = "Familjen"

# ───────────────────────── design tokens ─────────────────────────
# `ground` is the slide colour, `field` the generated block laid over it,
# `ink`/`soft` the type, `accent` the pivot word and badges.

THEMES = {
    # saturated grounds — the BLEED mode lives here
    "terracotta": dict(ground="#D0522A", field="#B03F1B", ink="#FFF7EE",
                       soft="rgba(255,247,238,.80)", accent="#FFD9A0",
                       cardink="#3A1A0E", card="#FFF7EE", grid="rgba(255,247,238,.10)",
                       badge_ink="#B8441F"),
    "forest":     dict(ground="#2F6B4F", field="#20503A", ink="#F4F1E6",
                       soft="rgba(244,241,230,.80)", accent="#F0C64B",
                       cardink="#14291E", card="#F4F1E6", grid="rgba(244,241,230,.10)",
                       badge_ink="#255840"),
    "charcoal":   dict(ground="#1E1E1E", field="#333330", ink="#F2EFE8",
                       soft="rgba(242,239,232,.72)", accent="#E58A5C",
                       cardink="#23201C", card="#F2EFE8", grid="rgba(242,239,232,.07)",
                       badge_ink="#1E1E1E"),
    "ochre":      dict(ground="#C6892B", field="#A56C17", ink="#221703",
                       soft="rgba(34,23,3,.72)", accent="#FFF7EE",
                       cardink="#221703", card="#FFF7EE", grid="rgba(34,23,3,.10)",
                       badge_ink="#AE7420"),
    "indigo":     dict(ground="#3B5C7E", field="#2A4460", ink="#F1F4F7",
                       soft="rgba(241,244,247,.78)", accent="#F0C64B",
                       cardink="#16232F", card="#F1F4F7", grid="rgba(241,244,247,.10)",
                       badge_ink="#2F4B69"),
    # papers — the TYPE mode lives here
    "oatmeal":    dict(ground="#E9E4D6", field="#CFC5A6", ink="#1B2A1E",
                       soft="rgba(27,42,30,.74)", accent="#C2481F",
                       cardink="#1B2A1E", card="#FFFFFF", grid="rgba(27,42,30,.07)",
                       badge_ink="#FFF7EE"),
    "sagetint":   dict(ground="#E4E9DC", field="#C2D0AF", ink="#1B2A1E",
                       soft="rgba(27,42,30,.74)", accent="#C2481F",
                       cardink="#1B2A1E", card="#FFFFFF", grid="rgba(27,42,30,.07)",
                       badge_ink="#FFF7EE"),
    "cream":      dict(ground="#F2EFE6", field="#DBD2B9", ink="#1B2A1E",
                       soft="rgba(27,42,30,.74)", accent="#C2481F",
                       cardink="#1B2A1E", card="#FFFFFF", grid="rgba(27,42,30,.07)",
                       badge_ink="#FFF7EE"),
    "clay":       dict(ground="#EBD9C6", field="#D9BF9F", ink="#2A1B12",
                       soft="rgba(42,27,18,.74)", accent="#B8441F",
                       cardink="#2A1B12", card="#FFF7EE", grid="rgba(42,27,18,.08)",
                       badge_ink="#FFF7EE"),
    # Added because four saturated grounds was too narrow a rotation: a run of
    # decks kept landing on the same colour, and whole hue families (blue that
    # actually reads as blue, purple, wine, teal) had no theme at all, so a
    # request for them silently resolved to something else. Every one of these
    # clears the same bars the originals do — see tests/test_layout.py.
    "cobalt":     dict(ground="#2C5AA0", field="#1F4480", ink="#F2F6FC",
                       soft="rgba(242,246,252,.78)", accent="#F5C542",
                       cardink="#13243F", card="#F2F6FC", grid="rgba(242,246,252,.10)",
                       badge_ink="#24497F"),
    "midnight":   dict(ground="#233047", field="#182234", ink="#EEF1F6",
                       soft="rgba(238,241,246,.76)", accent="#E8A05C",
                       cardink="#141C29", card="#EEF1F6", grid="rgba(238,241,246,.09)",
                       badge_ink="#233047"),
    "teal":       dict(ground="#17575A", field="#0F4144", ink="#EFF7F5",
                       soft="rgba(239,247,245,.78)", accent="#F2B95C",
                       cardink="#0B2B2D", card="#EFF7F5", grid="rgba(239,247,245,.10)",
                       badge_ink="#124749"),
    "plum":       dict(ground="#6B3560", field="#522847", ink="#FBF0F6",
                       soft="rgba(251,240,246,.78)", accent="#F3B7A0",
                       cardink="#2E1629", card="#FBF0F6", grid="rgba(251,240,246,.10)",
                       badge_ink="#5A2C51"),
    "wine":       dict(ground="#8C2F39", field="#6E222B", ink="#FDF0EC",
                       soft="rgba(253,240,236,.80)", accent="#F0C64B",
                       cardink="#3A1216", card="#FDF0EC", grid="rgba(253,240,236,.10)",
                       badge_ink="#75262F"),
    "blush":      dict(ground="#F2E2DE", field="#E0C6C0", ink="#3A1F22",
                       soft="rgba(58,31,34,.74)", accent="#B8441F",
                       cardink="#3A1F22", card="#FFFFFF", grid="rgba(58,31,34,.08)",
                       badge_ink="#FFF7EE"),
    "mist":       dict(ground="#E4EAF1", field="#C6D3E2", ink="#1D2833",
                       soft="rgba(29,40,51,.74)", accent="#B8441F",
                       cardink="#1D2833", card="#FFFFFF", grid="rgba(29,40,51,.08)",
                       badge_ink="#FFF7EE"),
}

# No green ground. Silly is green (#3C965A) and the forest ground sat at almost
# the same hue — the character vanished into the slide. A ground must be a
# different hue family from the character, not merely a different colour.
# `forest` is kept in THEMES only so old decks that name it still parse; it is
# not selectable, and the colour words that used to reach it resolve to `teal`.
BLEED_THEMES = ["terracotta", "charcoal", "indigo", "ochre",
                "cobalt", "midnight", "teal", "plum", "wine"]
PAPER_THEMES = ["oatmeal", "cream", "clay", "blush", "mist"]
# sagetint stays out of the rotation — it is the one paper close enough to the
# character's hue to be a judgement call, so it ships only when asked for.

# Roles that always shout, and roles that always need room for copy.
ALWAYS_BLEED = {"hook", "cta"}
ALWAYS_TYPE = {"source", "script"}

# ─────────────────── plain-English colour requests ────────────────
# A brief or a `**Palette:**` line may name a colour in ordinary words
# ("red", "reddish", "pinkish") instead of a theme token. Every alias below
# resolves to one of the THEMES keys above — never a bespoke hex — because
# every theme in THEMES already ships with an `ink` chosen for contrast on
# its `ground`. Routing loose colour words through this fixed vetted set is
# what keeps "reddish" from ever landing on a background too harsh, too
# saturated, or too close to the character's own green for the type (or
# Silly himself) to read.
#
# Each alias also carries which *slot* it fills: "bleed" (a saturated,
# full-bleed ground) or "paper" (a light ground with room for type). A
# colour word only ever fills the slot it was designed for — asking for
# "pink" fills the paper slot with `clay`, it does not force a saturated
# pink bleed that does not exist in the system.
COLOR_ALIASES: dict[str, tuple[str, str]] = {
    # warm red / orange / rust family -> terracotta (bleed)
    "red": ("bleed", "terracotta"), "reddish": ("bleed", "terracotta"),
    "orange": ("bleed", "terracotta"), "orangey": ("bleed", "terracotta"),
    "rust": ("bleed", "terracotta"), "rusty": ("bleed", "terracotta"),
    "terracotta": ("bleed", "terracotta"), "coral": ("bleed", "terracotta"),
    "brick": ("bleed", "terracotta"), "burnt orange": ("bleed", "terracotta"),
    # deep red / wine family -> wine (bleed)
    "wine": ("bleed", "wine"), "maroon": ("bleed", "wine"),
    "burgundy": ("bleed", "wine"), "crimson": ("bleed", "wine"),
    "deep red": ("bleed", "wine"), "dark red": ("bleed", "wine"),
    "berry": ("bleed", "wine"), "cherry": ("bleed", "wine"),
    "oxblood": ("bleed", "wine"),
    # pink / blush family -> blush (paper). No saturated pink bleed exists;
    # a hot pink ground would be the "too harsh for the type" case.
    "pink": ("paper", "blush"), "pinkish": ("paper", "blush"),
    "blush": ("paper", "blush"), "rose": ("paper", "blush"),
    "salmon": ("paper", "blush"), "peach": ("paper", "blush"),
    "peachy": ("paper", "blush"), "hot pink": ("paper", "blush"),
    "light pink": ("paper", "blush"), "dusty rose": ("paper", "blush"),
    # purple family -> plum (bleed)
    "purple": ("bleed", "plum"), "purplish": ("bleed", "plum"),
    "plum": ("bleed", "plum"), "violet": ("bleed", "plum"),
    "lilac": ("bleed", "plum"), "mauve": ("bleed", "plum"),
    "aubergine": ("bleed", "plum"), "eggplant": ("bleed", "plum"),
    "magenta": ("bleed", "plum"),
    # blue family. "blue" means a blue that reads as blue -> cobalt.
    # The muted slate stays reachable as indigo, the near-black as midnight.
    "blue": ("bleed", "cobalt"), "bluish": ("bleed", "cobalt"),
    "cobalt": ("bleed", "cobalt"), "royal blue": ("bleed", "cobalt"),
    "bright blue": ("bleed", "cobalt"), "true blue": ("bleed", "cobalt"),
    "sapphire": ("bleed", "cobalt"), "azure": ("bleed", "cobalt"),
    "indigo": ("bleed", "indigo"), "slate blue": ("bleed", "indigo"),
    "steel blue": ("bleed", "indigo"), "denim": ("bleed", "indigo"),
    "dusty blue": ("bleed", "indigo"), "slate": ("bleed", "indigo"),
    "navy": ("bleed", "midnight"), "midnight": ("bleed", "midnight"),
    "deep blue": ("bleed", "midnight"), "dark blue": ("bleed", "midnight"),
    "navy blue": ("bleed", "midnight"), "ink blue": ("bleed", "midnight"),
    "light blue": ("paper", "mist"), "pale blue": ("paper", "mist"),
    "sky blue": ("paper", "mist"), "powder blue": ("paper", "mist"),
    "sky": ("paper", "mist"), "mist": ("paper", "mist"),
    "ice blue": ("paper", "mist"), "cool grey": ("paper", "mist"),
    # teal / aqua family -> teal (bleed). Deliberately darker than a true
    # teal so it never closes on the character's green.
    "teal": ("bleed", "teal"), "aqua": ("bleed", "teal"),
    "turquoise": ("bleed", "teal"), "cyan": ("bleed", "teal"),
    "petrol": ("bleed", "teal"), "deep teal": ("bleed", "teal"),
    "dark green": ("bleed", "teal"), "emerald": ("bleed", "teal"),
    "forest": ("bleed", "teal"),   # the retired green ground's nearest safe home
    # yellow / gold / mustard family -> ochre (bleed)
    "yellow": ("bleed", "ochre"), "yellowish": ("bleed", "ochre"),
    "gold": ("bleed", "ochre"), "golden": ("bleed", "ochre"),
    "mustard": ("bleed", "ochre"), "amber": ("bleed", "ochre"),
    "ochre": ("bleed", "ochre"), "honey": ("bleed", "ochre"),
    "turmeric": ("bleed", "ochre"),
    # green / sage family -> sagetint (paper: light, so the character never
    # vanishes into it the way the retired `forest` bleed did)
    "green": ("paper", "sagetint"), "greenish": ("paper", "sagetint"),
    "sage": ("paper", "sagetint"), "sagey": ("paper", "sagetint"),
    "mint": ("paper", "sagetint"), "minty": ("paper", "sagetint"),
    "olive": ("paper", "sagetint"), "moss": ("paper", "sagetint"),
    "light green": ("paper", "sagetint"), "pale green": ("paper", "sagetint"),
    "sagetint": ("paper", "sagetint"),
    # black / charcoal / dark family -> charcoal (bleed)
    "black": ("bleed", "charcoal"), "dark": ("bleed", "charcoal"),
    "charcoal": ("bleed", "charcoal"), "night": ("bleed", "charcoal"),
    "grey": ("bleed", "charcoal"), "gray": ("bleed", "charcoal"),
    "graphite": ("bleed", "charcoal"), "ink": ("bleed", "charcoal"),
    # cream / ivory / off-white family -> cream (paper)
    "cream": ("paper", "cream"), "creamy": ("paper", "cream"),
    "ivory": ("paper", "cream"), "off-white": ("paper", "cream"),
    "off white": ("paper", "cream"), "vanilla": ("paper", "cream"),
    "white": ("paper", "cream"), "whitish": ("paper", "cream"),
    "bone": ("paper", "cream"), "eggshell": ("paper", "cream"),
    # tan / oatmeal / neutral family -> oatmeal (paper)
    "tan": ("paper", "oatmeal"), "beige": ("paper", "oatmeal"),
    "oatmeal": ("paper", "oatmeal"), "sand": ("paper", "oatmeal"),
    "sandy": ("paper", "oatmeal"), "wheat": ("paper", "oatmeal"),
    "khaki": ("paper", "oatmeal"), "warm neutral": ("paper", "oatmeal"),
    "neutral": ("paper", "oatmeal"), "greige": ("paper", "oatmeal"),
    # brown -> clay (paper)
    "brown": ("paper", "clay"), "brownish": ("paper", "clay"),
    "clay": ("paper", "clay"), "tan pink": ("paper", "clay"),
    "camel": ("paper", "clay"), "caramel": ("paper", "clay"),
}

# Intensity words that carry no hue of their own. When a phrase like
# "deep blue" is not itself in the table, these are stripped and the bare
# colour retried — so an unlisted modifier degrades to the right hue family
# instead of failing. Phrases where the modifier genuinely changes the answer
# ("deep blue" -> midnight, "light blue" -> mist) are listed above and win,
# because the full phrase is always tried first.
COLOR_MODIFIERS = {
    "deep", "dark", "darker", "light", "lighter", "pale", "soft", "softer",
    "bright", "brighter", "muted", "rich", "warm", "cool", "dusty", "dull",
    "vivid", "strong", "gentle", "subtle", "faded", "washed", "very",
    "really", "super", "quite", "a", "an", "the", "some", "ish", "toned",
}


def resolve_color_word(word: str) -> tuple[str, str] | None:
    """Map a loose colour word to a (slot, theme) pair, or None if it names
    no colour we know.

    Handles, in order: the phrase as written, the phrase with any hex code
    and punctuation stripped ("Oatmeal #F5F4F0"), and the phrase with
    intensity words removed ("deep blue" -> "blue"). A trailing "-ish" is
    also trimmed, so "greenish" and "green-ish" both land.
    """
    w = word.strip().lower()
    if w in COLOR_ALIASES:
        return COLOR_ALIASES[w]

    # Strip hex codes and stray punctuation — older scripts wrote the palette
    # as "Oatmeal #F5F4F0 / Charcoal #2B2B2B" and every token missed.
    w = re.sub(r"#[0-9a-f]{3,8}\b", " ", w)
    w = re.sub(r"[^a-z\s-]", " ", w)
    w = re.sub(r"\s+", " ", w).strip()
    if w in COLOR_ALIASES:
        return COLOR_ALIASES[w]

    words = [x for x in w.replace("-", " ").split() if x]

    # Longest contiguous phrase wins, so a modifier that genuinely changes
    # the answer is never thrown away by accident: "a really dark red"
    # finds "dark red" (wine) rather than stripping down to "red"
    # (terracotta) and landing two hue families away.
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n])
            if phrase in COLOR_ALIASES:
                return COLOR_ALIASES[phrase]
            if phrase.endswith("ish") and phrase[:-3] in COLOR_ALIASES:
                return COLOR_ALIASES[phrase[:-3]]

    # Nothing matched as written. Drop pure intensity words and retry the
    # bare colour, so an unlisted modifier still lands in the right family.
    for word_ in words:
        if word_ in COLOR_MODIFIERS:
            continue
        if word_ in COLOR_ALIASES:
            return COLOR_ALIASES[word_]
    return None


def layout_for(role: str, seq: int) -> str:
    """BLEED or TYPE. Alternates across the middle of the deck so the grid has
    rhythm instead of nine identical frames."""
    for k in ALWAYS_BLEED:
        if k in role:
            return "bleed"
    for k in ALWAYS_TYPE:
        if k in role:
            return "type"
    return "bleed" if seq % 2 else "type"


PALETTE_HISTORY_PATH = SKILL_DIR / "palette_history.json"


def load_palette_history() -> dict[str, list[str]]:
    """Which [bleed, paper] pair each past deck used, keyed by carousel slug.

    Mirrors mascot/usage_history.json's pattern so "I'm feeling lucky" can
    round-robin through the palette instead of repeating recent decks.
    """
    if not PALETTE_HISTORY_PATH.is_file():
        return {}
    return json.loads(PALETTE_HISTORY_PATH.read_text())


def record_palette(slug: str, bleed: str, paper: str) -> None:
    """Record this deck's palette, replacing any prior record for the same
    slug so rebuilding a deck updates its entry instead of piling up."""
    history = load_palette_history()
    history[slug] = [bleed, paper]
    PALETTE_HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")


def _least_recent(options: list[str], used: list[str]) -> str:
    """The least recently used option. `used` is every past choice in order,
    oldest first.

    This is a true LRU over the whole history rather than a fixed-size
    window. A window is the obvious implementation and it is wrong: with a
    4-deck window and nine themes, the fifth deck sees the first theme drop
    out of the window and picks it again, so the rotation never reaches
    themes 5-9. Ranking by how long ago each option was last used cycles
    through every option before any repeats.
    """
    def last_used(opt: str) -> int:
        for i in range(len(used) - 1, -1, -1):
            if used[i] == opt:
                return i
        return -1   # never used — always wins
    return min(options, key=lambda o: (last_used(o), options.index(o)))


def _random_palette(exclude_slug: str | None = None) -> tuple[str, str]:
    """Random bleed/paper pair, avoiding immediate repeat of the last deck."""
    import random
    history = load_palette_history()
    slugs = sorted(s for s in history if s != exclude_slug)
    last_bleed = history[slugs[-1]][0] if slugs and history[slugs[-1]][0] in BLEED_THEMES else None
    last_paper = history[slugs[-1]][1] if slugs and history[slugs[-1]][1] in PAPER_THEMES else None
    bleeds = [b for b in BLEED_THEMES if b != last_bleed] or BLEED_THEMES
    papers = [p for p in PAPER_THEMES if p != last_paper] or PAPER_THEMES
    return random.choice(bleeds), random.choice(papers)


def _round_robin_palette(exclude_slug: str | None) -> tuple[str, str]:
    """The bleed/paper pair least recently used across past decks, so a run
    of "I'm feeling lucky" decks visibly cycles instead of clumping on one
    colour or repeating the deck before it."""
    history = load_palette_history()
    slugs = sorted(s for s in history if s != exclude_slug)
    used_bleeds = [history[s][0] for s in slugs if history[s][0] in BLEED_THEMES]
    used_papers = [history[s][1] for s in slugs if history[s][1] in PAPER_THEMES]
    return (_least_recent(BLEED_THEMES, used_bleeds),
            _least_recent(PAPER_THEMES, used_papers))


def deck_palette(md_path, exclude_slug: str | None = None, randomize: bool = False) -> tuple[str, str]:
    """ONE saturated colour and ONE paper for the whole carousel.

    Nine colours across nine slides read as noise, not as a brand. A deck now
    commits to a pair and alternates between them.

    Resolution order:
    1. An explicit `**Palette:**`/`**Theme:**` header naming theme tokens
       (`forest / cream`) or plain colour words (`reddish / pinkish`) —
       colour words are routed through COLOR_ALIASES so a casual request
       always lands on a theme already vetted for text contrast, never a
       one-off hex value.
    2. Whatever half of the pair isn't named is filled by round-robin —
       the option least recently used across past decks (see
       palette_history.json), so an unnamed colour never repeats a few
       decks in a row the way the old name-hash fallback could.
    """
    bleed = paper = None
    if isinstance(md_path, (str, Path)):
        p = Path(md_path)
        if p.is_file():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"\*\*(?:Theme|Palette):\*\*\s*(.+)", txt)
            if m:
                # Scan every token, not just the first two: legacy scripts
                # wrote four ("Oatmeal #F5F4F0 / Charcoal #2B2B2B / Terracotta
                # accent … / Sage green …") and the ground was not always
                # first. First bleed and first paper found win.
                tokens = [t for t in re.split(r"\s*[/,]\s*", m.group(1).strip()) if t]
                unresolved = []
                for tok in tokens:
                    tok_l = tok.strip().lower()
                    # Only a *selectable* theme name is taken as-is. A name
                    # that exists in THEMES but was retired from the rotation
                    # (`forest`) has to go through the alias table like any
                    # other word, or an old script naming it would put the
                    # green ground — and the invisible character — straight
                    # back on the slide.
                    if tok_l in BLEED_THEMES or tok_l in PAPER_THEMES:
                        slot = "paper" if tok_l in PAPER_THEMES else "bleed"
                        theme = tok_l
                    else:
                        resolved = resolve_color_word(tok_l)
                        if not resolved:
                            unresolved.append(tok.strip())
                            continue
                        slot, theme = resolved
                    if slot == "bleed" and bleed is None:
                        bleed = theme
                    elif slot == "paper" and paper is None:
                        paper = theme

                # A palette line that resolved to NOTHING is the defect this
                # guard exists for: `**Palette:** deep blue` used to fall
                # through to the round robin and ship a terracotta deck, with
                # no sign anything had gone wrong. Asking for a colour and
                # silently getting a different one is worse than a failed
                # build, so this aborts.
                if unresolved and bleed is None and paper is None:
                    known = ", ".join(sorted(COLOR_ALIASES))
                    sys.exit(
                        f"ERROR: **Palette:** names no colour this system knows: "
                        f"{', '.join(unresolved)}\n"
                        f"  in {p}\n"
                        f"  Use a theme name ({', '.join(BLEED_THEMES + PAPER_THEMES)})\n"
                        f"  or a plain colour word. Known words:\n    {known}\n"
                        f"  Or delete the **Palette:** line to let the build "
                        f"pick by round robin.")
                # A partially-understood line still builds — the half that
                # resolved is honoured — but never silently.
                if unresolved:
                    print(f"  ! palette: ignoring unknown colour "
                          f"{', '.join(unresolved)}", file=sys.stderr)
            if exclude_slug is None:
                exclude_slug = p.parent.name

    if bleed and paper:
        return bleed, paper
    if randomize:
        r_bleed, r_paper = _random_palette(exclude_slug)
        return bleed or r_bleed, paper or r_paper
    rb_bleed, rb_paper = _round_robin_palette(exclude_slug)
    return bleed or rb_bleed, paper or rb_paper


def theme_for(mode: str, palette: tuple[str, str]) -> str:
    return palette[0] if mode == "bleed" else palette[1]


# ───────────────────── generated colour fields ───────────────────
# Each returns the inline style for one absolutely-positioned block. They are
# CSS shapes, not assets: a deck gets a different composition per slide and
# nothing has to be stored or downloaded.

def _f(css: str, colour: str) -> str:
    return f"position:absolute;background:{colour};z-index:1;{css}"


# Four shapes, all ANCHORED. The previous set had ten picked by index, and
# several floated in the middle of the slide with no relationship to anything —
# a rounded band across the waist read as an accident rather than a decision.
# Each of these either grounds the figure or supports the copy block, and each
# is positioned from the figure's own width so it never lands arbitrarily.

def _ground_sweep(c: str, fig_w: int) -> str:
    """A field along the bottom with one swept corner. The figure stands on it."""
    return _f(f"left:0;right:0;bottom:0;height:560px;"
              f"border-radius:{min(340, 120 + fig_w // 2)}px 70px 0 0;", c)


def _ground_arch(c: str, fig_w: int) -> str:
    """A wide arch. Symmetrical, calmer than the sweep."""
    return _f("left:-60px;right:-60px;bottom:0;height:620px;"
              "border-radius:50% 50% 0 0 / 34% 34% 0 0;", c)


def _halo(c: str, fig_w: int) -> str:
    """A disc centred behind the figure's mass, so it reads as a backdrop to
    the character rather than a shape of its own."""
    d = int(fig_w * 2.0)
    return _f(f"right:{-d // 5}px;bottom:{-d // 6}px;width:{d}px;height:{d}px;"
              f"border-radius:50%;", c)


def _corner_wedge(c: str, fig_w: int) -> str:
    """A diagonal rising from the bottom-left, under the copy."""
    return _f("left:0;right:0;bottom:0;height:700px;"
              "clip-path:polygon(0 42%,100% 0,100% 100%,0 100%);", c)


FIELDS = [_ground_sweep, _ground_arch, _halo, _corner_wedge]
def field_style(seq: int, theme: dict, fig_w: int = 340) -> str:
    return FIELDS[seq % len(FIELDS)](theme["field"], fig_w)


# ───────────────────────── assets ────────────────────────────────

def font_face(family: str, filename: str, weights: str) -> str:
    path = FONT_DIR / filename
    if not path.is_file():
        sys.exit(f"ERROR: missing font {path}\nExpected {filename} in assets/fonts/.")
    b64 = base64.b64encode(path.read_bytes()).decode()
    # These are TrueType (sfnt). Declaring them as woff2 is what silently sent
    # every slide to a system fallback in an earlier version.
    return (f"@font-face{{font-family:'{family}';"
            f"src:url(data:font/ttf;base64,{b64}) format('truetype');"
            f"font-weight:{weights};font-style:normal;font-display:block;}}")


def grain_tile(seed: int = 7, size: int = 128) -> str:
    """A real raster noise tile, generated locally. No SVG filters."""
    rng = np.random.default_rng(seed)
    n = rng.integers(0, 256, (size, size), dtype=np.uint8)
    rgba = np.dstack([n, n, n, np.full_like(n, 22)])
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


# ───────────────────────── markdown ──────────────────────────────

FIELDS_MD = {
    "- **Layout:**": "layout", "- **H1:**": "h1", "- **H2:**": "h2",
    "- **Body:**": "body", "- **Mascot:**": "mascot",
    "- **Visual / Mascot:**": "mascot", "- **Cue:**": "cue", "- **Badge:**": "badge",
    "- **Source:**": "source", "- **Closing thought:**": "closing",
    "- **Handle:**": "handle", "- **Callout:**": "callout",
    "- **Primary CTA:**": "cta1", "- **Secondary CTA:**": "cta2",
    "- **Source Claim:**": "source_claim",
    "- **Plain-English Translation:**": "source_translation",
    "- **What This Explains Here:**": "source_explains",
    "- **Myth:**": "myth", "- **Reality:**": "reality",
    # The playbook deprecated "WHAT YOU SAY" and asked for "When" and "Say".
    # The old spellings stay so the decks already on disk still parse.
    "- **When:**": "old_reaction", "- **Say:**": "new_reaction",
}


def parse_markdown(path: Path) -> list[dict]:
    slides: list[dict] = []
    cur: dict | None = None
    for raw in path.read_text(encoding="utf-8").split("\n"):
        line = raw.strip()
        if line.startswith("### Slide"):
            if cur:
                slides.append(cur)
            title = line.replace("### ", "").strip()
            role = title.split("·")[-1].strip().lower() if "·" in title else ""
            cur = {"title": title, "role": role}
            continue
        if cur is None:
            continue
        if line.startswith("## "):
            slides.append(cur); cur = None; continue
        for prefix, key in FIELDS_MD.items():
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                # The renderer draws its own quotation marks around a spoken
                # line, so a pair in the markdown becomes two pairs on the
                # slide. The ❌/✅ branch below always stripped them; When and
                # Say came in through this loop and did not, and printed
                # ""You whisper: ..."" on a rendered slide.
                if key in ("old_reaction", "new_reaction"):
                    value = value.strip('"\u201c\u201d')
                cur[key] = value
                break
        else:
            if line.startswith("- **❌") or line.startswith("- **✗"):
                cur["old_reaction"] = line.split(":**", 1)[-1].strip().strip('"“”')
            elif line.startswith("- **✅") or line.startswith("- **✓"):
                cur["new_reaction"] = line.split(":**", 1)[-1].strip().strip('"“”')
            elif re.match(r"^-?\s*•\s+", line):
                cur.setdefault("bullets", []).append(re.sub(r"^-?\s*•\s+", "", line))
    if cur:
        slides.append(cur)
    keep = ("h1", "h2", "body", "cta1", "old_reaction", "new_reaction", "bullets",
            "closing", "source_claim", "source_translation", "source_explains",
            "myth", "reality")
    return [s for s in slides if any(k in s for k in keep)]


EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF️‍]+")


def strip_emoji(text: str) -> str:
    """The design system is type-and-shape only; emoji render as tofu boxes."""
    return EMOJI.sub("", text).strip()


def fmt(text: str) -> str:
    """Escape, then render [[accent]], **bold** and *italic*."""
    text = strip_emoji(text)
    out, parts = [], re.split(r"\[\[|\]\]", text)
    for i, chunk in enumerate(parts):
        piece = html_mod.escape(chunk)
        piece = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", piece)
        piece = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", piece)
        out.append(f'<span class="hl">{piece}</span>' if i % 2 else piece)
    return "".join(out)


def plain(text: str) -> str:
    text = strip_emoji(text)
    text = re.sub(r"\[\[|\]\]", "", text)
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    return html_mod.escape(text)


# ───────────────────────── CSS ───────────────────────────────────

def build_css(t: dict, mode: str) -> str:
    T = TYPE
    disp = TYPE["h1"] if mode == "bleed" else TYPE["h2"]
    return f"""
{font_face(DISPLAY, 'ArchivoBlack.ttf', '400 900')}
{font_face(BODY, 'FamiljenGrotesk-Variable.ttf', '400 700')}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px}}
body{{background:{t['ground']};color:{t['ink']};position:relative;overflow:hidden;
  font-family:'{BODY}',system-ui,sans-serif;-webkit-font-smoothing:antialiased}}

.grid{{position:absolute;inset:0;z-index:2;pointer-events:none;
  background-image:repeating-linear-gradient(0deg,{t['grid']} 0 2px,transparent 2px 58px),
                   repeating-linear-gradient(90deg,{t['grid']} 0 2px,transparent 2px 58px)}}
.grain{{position:absolute;inset:0;z-index:60;pointer-events:none;opacity:.5;
  background-image:url({{GRAIN}});background-size:128px 128px;mix-blend-mode:overlay}}

.canvas{{position:absolute;left:{MARGIN}px;right:{MARGIN}px;top:{MARGIN}px;bottom:{FOOTER_H+12}px;
  z-index:5;display:flex;flex-direction:column;justify-content:center;gap:28px;align-items:center;
  padding-top:{CANVAS_PAD_TOP}px;padding-bottom:{CANVAS_PAD_BOTTOM}px;}}
.canvas.source-pad{{padding-top:{SOURCE_PAD_TOP}px;justify-content:flex-start}}
/* With no figure the copy owns the slide and is centred in it. Spreading the
   blocks apart with space-between only moved the void into the middle, which
   looks broken rather than composed. */
.canvas.solo{{justify-content:center}}
.canvas.center{{text-align:center;align-items:center}}
.canvas.sparse{{gap:32px}}
.canvas.sparse h1{{font-size:128px;line-height:0.92}}
.canvas.sparse h2{{font-size:96px;line-height:0.96}}
.canvas.sparse .lead{{font-size:52px;line-height:1.25}}
.canvas.sparse .body-text{{font-size:48px;line-height:1.35}}
.canvas.sparse .script .line{{font-size:52px;line-height:1.28}}
.canvas.sparse .quote{{font-size:62px;line-height:1.22}}
.canvas.sparse .bullets li{{font-size:48px;line-height:1.28}}

h1{{font-family:'{DISPLAY}',system-ui,sans-serif;font-weight:400;
  font-size:{T['h1'][0]}px;line-height:{T['h1'][1]};letter-spacing:{T['h1'][2]};
  margin-bottom:24px;text-wrap:balance}}
h2{{font-family:'{DISPLAY}',system-ui,sans-serif;font-weight:400;
  font-size:{T['h2'][0]}px;line-height:{T['h2'][1]};letter-spacing:{T['h2'][2]};
  margin-bottom:24px;text-wrap:balance}}

/* The hook slide's second line is a SUPPORTING line, not a second headline.
   At h2's 86px display weight it competed with the 112px hook above it and the
   whole slide read as a wall of black type — the reason hooks stopped landing
   in 1.5 seconds. Body face, soft ink, roughly a third the size: it now reads
   as the aside it always was. Only fires when an h1 is present, so every other
   slide's h2 is untouched. */
h1 + h2{{font-family:'{BODY}',system-ui,sans-serif;font-weight:500;
  font-size:{T['lead'][0]}px;line-height:{T['lead'][1]};
  letter-spacing:{T['lead'][2]};color:{t['soft']};
  margin-top:-6px;margin-bottom:24px;max-width:840px}}
.hl{{color:{t['accent']}}}
.lead{{font-size:{T['lead'][0]}px;line-height:{T['lead'][1]};
  letter-spacing:{T['lead'][2]};color:{t['soft']};font-weight:500;max-width:840px}}
.body-text{{font-size:{T['body'][0]}px;line-height:{T['body'][1]};
  letter-spacing:{T['body'][2]};font-weight:450;max-width:820px}}

/* A numbered list. Short left rules per item read as broken bars; a counter
   in the accent gives the same structure and actually looks deliberate. */
.bullets{{list-style:none;max-width:900px;counter-reset:b}}
.bullets li{{font-size:{T['bullet'][0]}px;line-height:{T['bullet'][1]};
  letter-spacing:{T['bullet'][2]};font-weight:500;margin-bottom:26px;
  padding-left:76px;position:relative}}
.bullets li::before{{counter-increment:b;content:counter(b,decimal-leading-zero);
  position:absolute;left:0;top:.06em;font-family:'{DISPLAY}',sans-serif;
  font-size:{T['bullet'][0]}px;line-height:{T['bullet'][1]};color:{t['accent']}}}

/* The source slide. A card shrank the quote and walled it off; an oversized
   quote mark and a rule do the same job at full size. */
.quotemark{{font-family:'{DISPLAY}',serif;font-size:140px;line-height:.58;
  color:{t['accent']};margin-bottom:6px}}
.quote{{font-size:{T['quote'][0]}px;line-height:{T['quote'][1]};
  letter-spacing:{T['quote'][2]};font-weight:500;max-width:880px}}
.credit{{margin-top:30px;padding-top:20px;font-size:{T['credit'][0]}px;
  line-height:{T['credit'][1]};color:{t['soft']};font-weight:500;
  border-top:3px solid {t['accent']};display:inline-block}}
.source-stack{{display:grid;gap:26px;max-width:900px}}
.source-kicker{{font-size:{T['label'][0]}px;letter-spacing:{T['label'][2]};
  text-transform:uppercase;color:{t['accent']};font-weight:700;margin-bottom:10px}}
.source-line{{font-size:{T['body'][0]}px;line-height:{T['body'][1]};
  letter-spacing:{T['body'][2]};font-weight:500}}

/* Before and after, unboxed. Weight and colour carry the contrast. */
.script{{max-width:860px}}
.script + .script{{margin-top:56px}}
.script .tag{{font-size:{T['label'][0]}px;letter-spacing:{T['label'][2]};
  text-transform:uppercase;font-weight:700;display:block;margin-bottom:14px}}
.script .line{{font-size:{T['body'][0]}px;line-height:{T['body'][1]};font-weight:450}}
.was .tag,.was .line{{color:{t['soft']}}}
.now .tag{{color:{t['accent']}}}
.now .line{{font-weight:600}}
.dm-thread{{display:flex;flex-direction:column;gap:30px;max-width:900px}}
.bubble{{font-size:{T['body'][0]}px;line-height:{T['body'][1]};
  letter-spacing:{T['body'][2]};font-weight:500;padding:28px 34px;
  border-radius:36px;max-width:780px}}
.bubble.was{{align-self:flex-start;background:{t['card']};color:{t['cardink']}}}
.bubble.now{{align-self:flex-end;background:{t['accent']};color:{t['ground']};
  font-weight:650}}
.quad-grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px;max-width:900px;
  margin-top:14px}}
.quad{{background:{t['card']};color:{t['cardink']};padding:26px 28px;
  border-radius:28px;font-size:34px;line-height:1.25;font-weight:550}}
.chain{{display:flex;flex-direction:column;gap:20px;max-width:900px;margin-top:8px;
  counter-reset:chain}}
.chain-step{{position:relative;padding:24px 32px 24px 96px;background:{t['card']};
  color:{t['cardink']};border-radius:28px;font-size:36px;line-height:1.22;font-weight:550}}
.chain-step::before{{counter-increment:chain;content:counter(chain,decimal-leading-zero);
  position:absolute;left:28px;top:24px;font-family:'{DISPLAY}',sans-serif;
  color:{t['accent']};font-size:35px;line-height:1}}
.mythgrid{{display:grid;grid-template-columns:1fr 1fr;gap:26px;max-width:900px;margin-top:8px}}
.mythbox{{background:{t['card']};color:{t['cardink']};padding:28px;border-radius:30px}}
.mythbox .tag{{font-size:{T['label'][0]}px;letter-spacing:{T['label'][2]};
  text-transform:uppercase;font-weight:800;margin-bottom:16px;color:{t['accent']}}}
.mythbox .line{{font-size:36px;line-height:1.24;font-weight:550}}

.pill{{display:inline-flex;align-self:flex-start;margin-top:28px;
  background:{t['accent']};color:{t['ground']};font-size:24px;font-weight:700;
  letter-spacing:.04em;padding:17px 32px;border-radius:999px}}

.swipe{{position:absolute;left:{MARGIN}px;bottom:{FOOTER_H + 4}px;z-index:8;
  display:inline-flex;align-items:center;gap:12px;background:{t['ink']};
  color:{t['ground']};font-size:22px;letter-spacing:.16em;text-transform:uppercase;
  padding:18px 34px;border-radius:999px;font-weight:700}}

.mascot{{position:absolute;z-index:6;pointer-events:none;left:50%;transform:translateX(-50%);bottom:{FOOTER_H+12}px;width:calc(100% - {MARGIN*2}px);max-width:900px;max-height:calc(100% - {MARGIN+FOOTER_H+40}px);display:flex;justify-content:center;align-items:flex-end;overflow:visible}}
.mascot img{{display:block;width:auto;height:auto;max-width:100%;max-height:100%;object-fit:contain;object-position:center bottom;}}
.mascot.wide{{justify-content:center;}}
.mascot.wide img{{object-position:center bottom;}}
.mascot.mascot-inline{{position:static !important;left:auto;right:auto;bottom:auto;transform:none;width:100%;max-width:900px;height:460px;flex:0 0 auto;margin-top:0;align-self:center;justify-content:center;align-items:flex-end;overflow:visible}}
.mascot.mascot-inline img{{width:auto;height:auto;max-width:100%;max-height:100%;object-fit:contain;object-position:center bottom;}}
/* flex-centred, never shrink-wrapped: align-items:center on the column was
   sizing this to content and clipping a raised hoof off the edge. */
.mascot-cta{{position:static;margin:0 auto 26px;z-index:6;flex:0 0 auto;
  display:flex;justify-content:center;align-self:stretch}}
.mascot-cta img{{display:block;width:auto;height:100%;max-width:100%;
  object-fit:contain}}

.cta-closing{{font-size:{T['lead'][0]}px;line-height:{T['lead'][1]};
  color:{t['soft']};margin-bottom:22px;max-width:820px;font-weight:500}}
.cta1{{font-family:'{DISPLAY}',sans-serif;font-weight:400;font-size:74px;
  line-height:0.96;letter-spacing:-.03em;max-width:860px;text-wrap:balance}}
.cta-handle{{font-family:'{DISPLAY}',sans-serif;font-size:36px;margin:18px 0 8px;
  color:{t['accent']};letter-spacing:-.02em}}
.cta-sub{{font-size:26px;color:{t['soft']};font-weight:500}}

.footer{{position:absolute;left:{MARGIN}px;right:{MARGIN}px;bottom:58px;z-index:8;
  display:flex;align-items:center;justify-content:space-between;
  border-top:2px solid {t['grid']};padding-top:20px}}
.handle{{font-size:{T['footer'][0]}px;letter-spacing:{T['footer'][2]};
  text-transform:uppercase;color:{t['soft']};font-weight:700}}
.num{{font-size:{T['footer'][0]}px;letter-spacing:{T['footer'][2]};
  color:{t['soft']};font-weight:700}}
""".replace("{GRAIN}", grain_tile())


def slide_html(s: dict, idx: int, total: int, mascot: Path | None,
               seq: int, palette: tuple[str, str]) -> str:
    role = s.get("role", "")
    lay = s.get("layout", "")
    is_cta = "cta" in role or lay.startswith("Template E")
    is_source = "source" in role or lay.startswith("Template F")
    is_script = lay.startswith("Template C") or "old_reaction" in s
    is_dm = lay.startswith("Template G")
    is_grid = lay.startswith("Template H")
    is_chain = lay.startswith("Template I")
    is_myth = lay.startswith("Template J")
    is_cheat = "cheat" in role or lay.startswith("Template D")

    mode = "type" if (is_source or is_script or is_dm or is_grid or is_myth) else layout_for(role, seq)
    t = THEMES[theme_for(mode, palette)]
    has_m = mascot is not None and mascot.is_file()
    wide = False
    if has_m:
        with Image.open(mascot) as im:
            wide = im.size[0] / im.size[1] > 1.0

    body: list[str] = []
    body.append(f'<div id="field" style="{field_style(seq, t, 340)}"></div>')
    body.append('<div class="grid"></div>')

    if is_cta:
        body.append('<div class="canvas center">')
        if has_m:
            body.append(f'<div class="mascot-cta" id="fig" style="height:500px">'
                        f'<img src="{data_uri(mascot)}"></div>')
        closing = s.get("closing", s.get("body", ""))
        cta_main = s.get("cta1", s.get("h1", ""))
        if closing:
            body.append(f'<p class="cta-closing">{fmt(closing)}</p>')
        if cta_main:
            body.append(f'<div class="cta1">{fmt(cta_main)}</div>')
        body.append(f'<div class="cta-handle">{plain(s.get("handle", "@suresilly"))}</div>')
        if "cta2" in s:
            body.append(f'<div class="cta-sub">{plain(s["cta2"])}</div>')
        body.append("</div>")
    else:
        # No eyebrow label anywhere. It was a dot and a caption that pushed the
        # real headline down and added nothing a reader needed.
        if is_source:
            body.append('<div class="canvas source-pad" id="copy">')
        else:
            body.append('<div class="canvas" id="copy">')
        if is_source:
            if any(k in s for k in ("source_claim", "source_translation", "source_explains")):
                body.append('<div class="source-stack">')
                if "source_claim" in s:
                    body.append('<section><div class="source-kicker">source says</div>'
                                f'<p class="source-line">{fmt(s["source_claim"])}</p></section>')
                if "source_translation" in s:
                    body.append('<section><div class="source-kicker">translation</div>'
                                f'<p class="source-line">{fmt(s["source_translation"])}</p></section>')
                if "source_explains" in s:
                    body.append('<section><div class="source-kicker">this explains</div>'
                                f'<p class="source-line">{fmt(s["source_explains"])}</p></section>')
                body.append("</div>")
            else:
                body.append('<div class="quotemark">&ldquo;</div>')
                body.append(f'<p class="quote">{fmt(s.get("body", ""))}</p>')
            if "source" in s:
                body.append(f'<p class="credit">{plain(s["source"].lstrip("— ").strip())}</p>')
        elif is_dm:
            body.append('<div class="dm-thread">')
            if "old_reaction" in s:
                body.append(f'<p class="bubble was">{fmt(s["old_reaction"])}</p>')
            if "new_reaction" in s:
                body.append(f'<p class="bubble now">{fmt(s["new_reaction"])}</p>')
            body.append("</div>")
        elif is_grid:
            if "h2" in s:
                body.append(f'<h2>{fmt(s["h2"])}</h2>')
            if "body" in s:
                body.append(f'<p class="body-text">{fmt(s["body"])}</p>')
            body.append('<div class="quad-grid">'
                        + "".join(f'<div class="quad">{fmt(b)}</div>'
                                  for b in s.get("bullets", [])[:4])
                        + "</div>")
        elif is_chain:
            if "h2" in s:
                body.append(f'<h2>{fmt(s["h2"])}</h2>')
            if "body" in s:
                body.append(f'<p class="body-text">{fmt(s["body"])}</p>')
            body.append('<div class="chain">'
                        + "".join(f'<div class="chain-step">{fmt(b)}</div>'
                                  for b in s.get("bullets", [])[:5])
                        + "</div>")
        elif is_myth:
            if "h2" in s:
                body.append(f'<h2>{fmt(s["h2"])}</h2>')
            body.append('<div class="mythgrid">')
            if "myth" in s:
                body.append('<section class="mythbox"><div class="tag">myth</div>'
                            f'<p class="line">{fmt(s["myth"])}</p></section>')
            if "reality" in s:
                body.append('<section class="mythbox"><div class="tag">reality</div>'
                            f'<p class="line">{fmt(s["reality"])}</p></section>')
            body.append("</div>")
        elif is_script:
            # "when" and "say", not "what you say" and "try this instead".
            #
            # A deck went out with "You stand up and walk to the hallway."
            # printed under WHAT YOU SAY, which is a stage direction about the
            # reader in quotation marks under a label claiming they said it.
            # Four more like it are on disk. The content playbook deprecated
            # this pair years before I got here, in as many words: it "puts
            # words in their mouth and leaks viewers who don't say that exact
            # sentence", and it asked for a condition the reader can test
            # instead. The code never followed.
            #
            # "When" takes quotation marks off too. A condition is not speech.
            if "old_reaction" in s:
                body.append('<div class="script was"><span class="tag">when</span>'
                            f'<p class="line">{plain(s["old_reaction"])}</p></div>')
            if "new_reaction" in s:
                body.append('<div class="script now"><span class="tag">say</span>'
                            f'<p class="line">&ldquo;{plain(s["new_reaction"])}&rdquo;</p></div>')
        else:
            if "h1" in s:
                body.append(f'<h1>{fmt(s["h1"].strip().strip(chr(34)))}</h1>')
            if "h2" in s:
                body.append(f'<h2>{fmt(s["h2"])}</h2>')
            if "body" in s:
                body.append(f'<p class="{"lead" if "h1" in s else "body-text"}">'
                            f'{fmt(s["body"])}</p>')
            if "bullets" in s:
                body.append('<ul class="bullets">'
                            + "".join(f"<li>{fmt(b)}</li>" for b in s["bullets"]) + "</ul>")
            if "callout" in s and idx == total:
                body.append(f'<span class="pill">{plain(s["callout"])}</span>')
        # Mascot inside canvas as flex child — prevents absolute gap/cut and keeps text+donkey as one centered group
        if has_m:
            # Use a fixed reasonable height (450px) inside flex flow, not dynamic remaining — avoids huge donkey on sparse slides
            body.append(f'<div class="mascot mascot-inline{" wide" if wide else ""}" id="fig" '
                        f'style="height:460px;flex:0 0 auto;margin-top:28px;"><img src="{data_uri(mascot)}"></div>')
        body.append("</div>")

        if idx == 1:
            body.append('<div class="swipe">swipe'
                        '<svg width="21" height="13" viewBox="0 0 22 14" fill="none">'
                        '<path d="M1 7h19M14.5 1.5 20.5 7l-6 5.5" stroke="currentColor" '
                        'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
                        '</svg></div>')

    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'<style>{build_css(t, mode)}</style></head><body>'
            + "".join(body)
            + f'<div class="footer"><span class="handle">@suresilly</span>'
              f'<span class="num">{idx:02d} / {total:02d}</span></div>'
              f'<div class="grain"></div></body></html>')


FONT_GUARD = """async () => {
  const need = [['400 104px ArchivoBlk','ArchivoBlk'], ['450 38px Familjen','Familjen']];
  await Promise.all(need.map(([spec]) => document.fonts.load(spec).catch(() => {})));
  return need.filter(([spec]) => !document.fonts.check(spec)).map(([,n]) => n);
}"""

# Type never shrinks. Instead the figure GROWS into whatever the copy leaves —
# which is what actually fills a slide, and does it the same way every time.
FIT_FIGURE = """(cfg) => {
  const copy = document.getElementById('copy');
  const fig = document.getElementById('fig');
  const field = document.getElementById('field');
  const out = {overflow: 0, figure: 0, field: 'kept'};

  // Where the copy actually ends, measured — exclude inline mascot so text height is correct
  let copyBottom = cfg.top;
  if (copy) {
    const kids = [...copy.children].filter(k => k.id !== 'fig');
    copyBottom = kids.length
      ? Math.max(...kids.map(k => k.getBoundingClientRect().bottom))
      : copy.getBoundingClientRect().bottom;
    out.overflow = Math.max(0, Math.round(copyBottom - cfg.copyMaxY));
    // Sparse text — bump size so it doesn't look lost at the top while mascot is huge below
    if ((copyBottom - cfg.top) < 380 && kids.length <= 3) {
      copy.classList.add('sparse');
      const kids2 = [...copy.children].filter(k => k.id !== 'fig');
      copyBottom = kids2.length
        ? Math.max(...kids2.map(k => k.getBoundingClientRect().bottom))
        : copy.getBoundingClientRect().bottom;
    }
  }

  // The colour field must never run through type. Positioned by slide index it
  // sliced a paragraph in half on the call-to-action slide.
  if (field) {
    const fr = field.getBoundingClientRect();
    if (fr.top < copyBottom + cfg.clear && fr.bottom > copyBottom) {
      const room = cfg.pageH - (copyBottom + cfg.clear);
      if (room < 180) { field.style.display = 'none'; out.field = 'dropped'; }
      else {
        field.style.top = Math.round(copyBottom + cfg.clear) + 'px';
        field.style.bottom = '0px';
        field.style.height = 'auto';
        out.field = 'moved';
      }
    }
  }

  // CTA is centered, not top-anchored — handle overflow by shrinking the figure
  if (fig && fig.classList.contains('mascot-cta')) {
    const canvas = fig.closest('.canvas');
    if (canvas) {
      const cb = canvas.getBoundingClientRect().bottom;
      const limit = cfg.pageH - cfg.footerH - 12;
      if (cb > limit) {
        const over = Math.round(cb - limit);
        const curH = fig.getBoundingClientRect().height;
        const newH = Math.max(320, Math.round(curH - over - 24));
        fig.style.height = newH + 'px';
        out.figure = newH;
        out.field = 'cta-shrunk';
        return out;
      }
    }
    out.figure = -1; return out;
  }
  // Inline mascot (flex child inside canvas) — fixed 460px, no dynamic room calc
  if (fig && fig.classList.contains('mascot-inline')) {
    const limit = cfg.pageH - cfg.footerH - 8;
    let fb = fig.getBoundingClientRect().bottom;
    if (fb > limit) {
      const over = Math.round(fb - limit);
      const curH = fig.getBoundingClientRect().height;
      let newH = Math.max(240, Math.round(curH - over - 16));
      fig.style.height = newH + 'px';
      fb = fig.getBoundingClientRect().bottom;
      if (fb > limit) {
        const over2 = Math.round(fb - limit);
        newH = Math.max(180, Math.round(newH - over2 - 8));
        fig.style.height = newH + 'px';
      }
      out.figure = parseInt(fig.style.height, 10);
      out.field = 'inline-shrunk';
      return out;
    }
    out.figure = fig.getBoundingClientRect().height;
    return out;
  }
  // Text first: a figure is added only if real room is left over. Below the
  // minimum a mascot is not small, it is an apology — the slide reads better
  // as pure type.
  if (!fig) return out;
  const room = cfg.pageH - cfg.footerH - copyBottom - cfg.gap;
  if (room < cfg.min) {
    fig.remove();
    // No figure means the copy owns the slide: spread it down the frame
    // instead of leaving it huddled at the top above a void.
    if (copy) {
      copy.classList.add('solo');
      if (field) {
        const fb = Math.max(...[...copy.children].map(k => k.getBoundingClientRect().bottom));
        const fr = field.getBoundingClientRect();
        if (fr.top < fb + cfg.clear) {
          const room2 = cfg.pageH - (fb + cfg.clear);
          if (room2 < 180) field.style.display = 'none';
          else { field.style.top = Math.round(fb + cfg.clear) + 'px';
                 field.style.bottom = '0px'; field.style.height = 'auto'; }
        }
      }
    }
    out.figure = 0; return out;
  }
  let h = Math.min(cfg.max, Math.round(room));
  // Horizontal cut guard: wide mascots would overflow the 1080px canvas
  // and get clipped. Cap by available width so the image scales down
  // proportionally instead of being cut. object-fit:contain in CSS keeps
  // aspect locked; this just chooses the smaller of the two constraints.
  const availW = (cfg.pageW || 1080) - (cfg.margin || 92)*2;
  const imgEl = fig.querySelector('img');
  if (imgEl && imgEl.naturalWidth && imgEl.naturalHeight) {
    const maxHbyW = Math.round(availW * imgEl.naturalHeight / imgEl.naturalWidth);
    if (h > maxHbyW) h = Math.max(cfg.min, Math.min(h, maxHbyW));
  }
  fig.style.height = h + 'px';
  fig.style.maxWidth = availW + 'px';
  out.figure = h;
  return out;
}"""
def render(md_path: Path, mascots: dict[int, Path], out_dir: Path,
           verbose: bool = True) -> list[Path]:
    from playwright.sync_api import sync_playwright

    slides = parse_markdown(md_path)
    if not slides:
        sys.exit(f"ERROR: no slides parsed from {md_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    palette = deck_palette(md_path)

    written: list[Path] = []
    long_slides: list[tuple[int, str, int]] = []
    textonly: list[int] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=1)
        for i, s in enumerate(slides, 1):
            html = slide_html(s, i, len(slides), mascots.get(i), i - 1, palette)
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            missing = page.evaluate(FONT_GUARD)
            if missing:
                browser.close()
                sys.exit(f"ERROR: font(s) failed to load: {', '.join(missing)}.\n"
                         f"Slides would silently render in a fallback face — aborting.\n"
                         f"Check assets/fonts/ contains valid TrueType files.")
            # Per-slide effective top accounts for the minimum canvas padding
            # (SOURCE_PAD_TOP vs CANVAS_PAD_TOP). Bottom is factored via an
            # effective footer that includes the canvas bottom inset + inner pad.
            _is_src = "source" in s.get("role", "") or s.get("layout", "").startswith("Template F")
            _top_eff = MARGIN + (SOURCE_PAD_TOP if _is_src else CANVAS_PAD_TOP)
            _footer_eff = FOOTER_H + 12 + CANVAS_PAD_BOTTOM
            fit = page.evaluate(FIT_FIGURE, {
                "pageH": H, "pageW": W, "margin": MARGIN,
                "footerH": _footer_eff, "gap": 22, "top": _top_eff,
                "clear": 40, "copyMaxY": _top_eff + COPY_MAX_H,
                "min": MASCOT_MIN, "max": MASCOT_MAX})
            if verbose and fit["figure"] == 0:
                textonly.append(i)
            if fit["overflow"] > 0:
                long_slides.append((i, s.get("title", ""), fit["overflow"]))
            page.wait_for_timeout(60)
            safe = re.sub(r"[^a-z0-9]+", "_", s.get("title", f"slide{i}").lower()).strip("_")
            dest = out_dir / f"{i:02d}_{safe}.png"
            page.screenshot(path=str(dest))
            written.append(dest)
            if verbose:
                print(f"  ✓ {dest.name}")
        browser.close()

    if textonly:
        print(f"\n  text-only (no room for a figure): "
              + ", ".join(f"slide {i:02d}" for i in textonly))
    if long_slides:
        # Type no longer shrinks to rescue long copy, so say so plainly. Each of
        # these is a sentence to cut, not a size to reduce.
        print("\n  copy runs past the text zone — trim these, do not resize:")
        for i, title, over in long_slides:
            print(f"    slide {i:02d}  {title[:42]:44s} {over}px too long")
    return written


def contact_sheet(paths: list[Path], dest: Path, cols: int = 3) -> Path:
    """3-wide grid, so the deck can be judged the way a real feed is."""
    thumbs = [Image.open(p).convert("RGB").resize((360, 450), Image.LANCZOS) for p in paths]
    rows = (len(thumbs) + cols - 1) // cols
    gap = 12
    sheet = Image.new("RGB", (cols * 360 + (cols + 1) * gap,
                              rows * 450 + (rows + 1) * gap), (18, 18, 18))
    for i, th in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(th, (gap + c * (360 + gap), gap + r * (450 + gap)))
    sheet.save(dest)
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--mascot-dir")
    a = ap.parse_args()
    md = Path(a.script)
    mascots: dict[int, Path] = {}
    if a.mascot_dir:
        for f in sorted(Path(a.mascot_dir).glob("*.png")):
            m = re.match(r"(\d+)", f.stem)
            if m:
                mascots[int(m.group(1))] = f
    out = render(md, mascots, md.parent / "slides")
    contact_sheet(out, md.parent / "contact_sheet.png")
    print(f"\n{len(out)} slides -> {md.parent / 'slides'}")


if __name__ == "__main__":
    main()
