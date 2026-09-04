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
import hashlib
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


def promote_checked_candidates(candidates: list[tuple[Path, str]]) -> None:
    """Import frozen checked PNGs only after every candidate hash matches."""
    import tempfile
    import shutil
    import import_poses
    with tempfile.TemporaryDirectory(prefix="suresilly-import-") as temporary:
        for candidate, expected_hash in candidates:
            raw = candidate.read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_hash:
                raise ValueError(f"Checked artwork changed before import: {candidate.name}")
            (Path(temporary) / candidate.name).write_bytes(raw)
            brief = candidate.with_suffix(".brief.txt")
            if brief.is_file():
                shutil.copy2(brief, Path(temporary) / brief.name)
        import_poses.main_argv([temporary, "--tags", "generated", "--exact"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?")
    ap.add_argument("--no-mascot", action="store_true")
    ap.add_argument("--generate", action="store_true",
                    help="removed unsafe path; use --fresh for checked free generation")
    ap.add_argument("--model", choices=["pro", "flash", "empero"], default=None,
                    help="removed with --generate; cannot choose an unchecked image model")
    ap.add_argument("--random-palette", action="store_true",
                    help="Pick a random bleed/paper pair (avoids immediate repeat), "
                         "instead of LRU round-robin. Use in CI for every-run variety.")
    ap.add_argument("--fresh", action="store_true",
                    help="generate a pose per slide from that slide's own brief. "
                         "Every failure falls back to the library pose, so a build "
                         "with no key or no network produces the same deck as always.")
    ap.add_argument("--fresh-budget", type=float,
                    help="neuron ceiling for this deck's generation (see poses_flux)")
    ap.add_argument("--bootstrap", action="store_true")
    a = ap.parse_args()

    if a.generate or a.model is not None:
        ap.error("--generate and --model were removed. Use --fresh for checked free art, "
                 "or omit it to use the library. No request was sent.")

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
    candidates: list[tuple[Path, str]] = []

    if not a.no_mascot:
        import library
        have = library.available()
        if not have:
            sys.exit("ERROR: no library artwork has current pixel, body and eye checks. "
                     "Complete the image audit before building. No image request was sent.")
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

        if a.fresh:
            # Imported HERE, not at module scope. build.py must keep working on a
            # machine with no key and no network, so the generator is reached only
            # when it is asked for, and every way it can fail returns the library
            # pose that was just chosen above. See fresh_poses for the invariant
            # this changes and why the guarantee it protected still holds.
            import fresh_poses
            print(f"\nGenerating fresh poses from the slide briefs "
                  f"(library poses are the fallback)…")
            keep = mdir / "_library_candidates"
            mascots, stats = fresh_poses.generate_for_deck(
                slides, mascots, mdir, budget=a.fresh_budget, keep_dir=keep)
            print(f"  {stats['generated']} generated, {stats['fell_back']} fell back, "
                  f"{stats['seconds']:.0f}s, ~{stats['neurons']:.0f} neurons")
            for reason in stats["reasons"][:4]:
                print(f"    {reason[:110]}")

            # Every generated pose is offered to the library, through
            # import_poses.py and its gates — never written straight in. A pose
            # that earned a slide today is a pose the next deck can reach, and
            # it arrives tagged with the BODY its brief described, which is the
            # vocabulary selection has never had.
            #
            # Wrapped, because growing the library is a bonus and a deck that
            # already rendered must not fail over it.
            if stats["kept"]:
                candidates = [(keep / f"{name}.png", stats["kept_hashes"][name])
                              for name in stats["kept"]]


    out = render.render(md, mascots, md.parent / "slides")
    sheet = render.contact_sheet(out, md.parent / "contact_sheet.png")
    print(f"\n{len(out)} slides -> {md.parent / 'slides'}")
    print(f"contact sheet -> {sheet}")

    # Promotion is after the complete render, and includes only this attempt's
    # surviving candidates. Old files in _library_candidates are not eligible.
    if candidates:
        promote_checked_candidates(candidates)

    if chosen:
        library.record_usage(md.parent.name, chosen)

    bleed, paper = render.deck_palette(md, exclude_slug=md.parent.name, randomize=a.random_palette)
    render.record_palette(md.parent.name, bleed, paper)
    print(f"palette -> {bleed} / {paper}{' (random)' if a.random_palette else ''}")


if __name__ == "__main__":
    main()
