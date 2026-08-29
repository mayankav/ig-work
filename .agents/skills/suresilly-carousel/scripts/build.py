#!/usr/bin/env python3
"""
build.py — one command: carousel markdown in, finished slide PNGs out.

    build.py carousels/20260822_topic/carousel.md

Runs identically under Claude Code, Antigravity, a bare shell or CI: it is a
plain CLI that talks to the Gemini REST API directly and never depends on an
MCP server being wired up.

Poses come from mascot/library/ by default. Nothing to remember, no key, no
network.

Flags:
    --no-mascot     text-only pass, for fast copy and layout iteration
    --generate      OBSOLETE paid path — see mascot.py. Needs billing.
    --model pro     only meaningful alongside --generate
    --bootstrap     create the venv from requirements.txt and install Chromium
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))


def bootstrap() -> None:
    venv = SKILL_DIR / ".venv"
    if not venv.is_dir():
        print(f"Creating venv at {venv}…")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    pip = venv / "bin" / "pip"
    subprocess.check_call([str(pip), "install", "-q", "-r",
                           str(SKILL_DIR / "requirements.txt")])
    subprocess.check_call([str(venv / "bin" / "playwright"), "install", "chromium"])
    print("Bootstrap complete.")


def role_key(role: str, slide: dict | None = None) -> str:
    """What the slide is FOR.

    The before/after template is detected by its content, not by its title —
    a slide called "Value Step 2" can still be a script slide, and it was
    getting the generic `value` treatment (and an arms-folded scowl) because
    of it.
    """
    if slide is not None:
        if "old_reaction" in slide or "new_reaction" in slide:
            return "script"
        if slide.get("layout", "").startswith("Template C"):
            return "script"
    for k in ("hook", "agitation", "source", "cheat", "cta"):
        if k in role:
            return k
    return "value"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?")
    ap.add_argument("--no-mascot", action="store_true")
    ap.add_argument("--generate", action="store_true",
                    help="OBSOLETE paid path — generate poses instead of using the "
                         "library. Needs a billed Gemini project; fails otherwise.")
    ap.add_argument("--model", choices=["pro", "flash", "empero"], default="flash")
    ap.add_argument("--random-palette", action="store_true",
                    help="Pick a random bleed/paper pair (avoids immediate repeat), "
                         "instead of LRU round-robin. Use in CI for every-run variety.")
    ap.add_argument("--bootstrap", action="store_true")
    a = ap.parse_args()

    if a.bootstrap:
        bootstrap()
        if not a.script:
            return
    if not a.script:
        ap.error("a carousel markdown path is required")

    md = Path(a.script).resolve()
    if not md.is_file():
        sys.exit(f"ERROR: no such script: {md}")

    import render
    slides = render.parse_markdown(md)
    if not slides:
        sys.exit(f"ERROR: no slides parsed from {md}")
    print(f"Parsed {len(slides)} slides from {md.name}")

    mascots: dict[int, Path] = {}
    mdir = md.parent / "mascot"
    chosen: dict[int, str] = {}

    if not a.generate and not a.no_mascot:
        import library
        have = library.available()
        if not have:
            sys.exit("ERROR: pose library is empty. Import sheets with\n                 scripts/import_poses.py — see mascot/GENERATION_PROMPTS.md")
        # Assign the whole deck at once — see library.assign_deck.
        specs = []
        for s in slides:
            specs.append(dict(
                brief=s.get("mascot", ""),
                headline=" ".join(filter(None, [s.get("h1", ""), s.get("h2", ""),
                                                s.get("closing", ""), s.get("cta1", "")])),
                body=" ".join(filter(None, [
                    s.get("body", ""), s.get("old_reaction", ""), s.get("new_reaction", ""),
                    " ".join(s.get("bullets", []))])),
                role=role_key(s.get("role", ""), s)))
        # A pose used across recent decks loses ground to a comparable fresh
        # one — see library.record_usage. A deck never penalises its own past
        # choices when rebuilt, hence exclude_slug.
        chosen = library.assign_deck(specs, have, usage=library.load_usage(),
                                     exclude_slug=md.parent.name)
        for i, s in enumerate(slides, 1):
            pose = chosen.get(i - 1)
            if pose:
                mascots[i] = library.path_for(pose)
                print(f"  [{i}] {role_key(s.get('role',''), s):9s} -> {pose}")
        print(f"Using {len(mascots)} library poses ({len(set(chosen.values()))} distinct)")


    elif a.generate:
        print("WARNING: --generate is the obsolete paid path. Gemini image "
              "generation\n         has no free tier, so this fails unless "
              "billing is enabled.\n         Drop the flag to use the pose library.\n"
              "         Use --model empero to try Empero community models instead.")
        import mascot as mascot_mod
        defaults = mascot_mod.default_briefs()
        api_key = mascot_mod.resolve_api_key()
        model = mascot_mod.MODEL_PRO if a.model == "pro" else \
                mascot_mod.MODEL_FLASH if a.model == "flash" else \
                mascot_mod.MODEL_EMPERO_FLASH if a.model == "empero" else mascot_mod.MODEL_FLASH
        mdir.mkdir(parents=True, exist_ok=True)
        print(f"Generating {len(slides)} mascot poses with {model}…")
        for i, s in enumerate(slides, 1):
            rk = role_key(s.get("role", ""))
            brief = s.get("mascot", "").strip()
            # legacy S1.2-style pose codes carry no posture information
            if not brief or re.fullmatch(r"S\d\.\d.*", brief, re.I):
                brief = defaults.get(rk, defaults["value"])
            dest = mdir / f"{i:02d}_{rk}.png"
            print(f"  [{i}/{len(slides)}] {rk}: {brief[:64]}…")
            mascot_mod.render_pose(brief, dest, model=model, seed=1000 + i * 37,
                                   api_key=api_key)
            mascots[i] = dest

    out = render.render(md, mascots, md.parent / "slides")
    sheet = render.contact_sheet(out, md.parent / "contact_sheet.png")
    print(f"\n{len(out)} slides -> {md.parent / 'slides'}")
    print(f"contact sheet -> {sheet}")

    if chosen:
        library.record_usage(md.parent.name, chosen)

    bleed, paper = render.deck_palette(md, exclude_slug=md.parent.name, randomize=a.random_palette)
    render.record_palette(md.parent.name, bleed, paper)
    print(f"palette -> {bleed} / {paper}{' (random)' if a.random_palette else ''}")


if __name__ == "__main__":
    main()
