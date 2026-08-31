#!/usr/bin/env python3
"""
fresh_poses.py — generate a pose for a slide from that slide's own brief.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  OPTIONAL. build.py calls this only under --fresh, and every failure  │
    │  here is answered by the pose the library already chose. A build      │
    │  with no key, no network, or an empty neuron budget produces exactly  │
    │  the deck it produced before this file existed.                       │
    └──────────────────────────────────────────────────────────────────────┘

Why this exists, and why the answer used to be no.

The library is finite and the brief is not. Measured over the 63 slides in
carousels/, 50 of them name a physical object and the whole pose library knows
only seven of those words: blanket, card, floor, list, mug, scarf, wall. A bed
appears in 17 briefs and no pose has ever had a bed. On those slides selection
was never choosing the right pose, it was choosing the least wrong one, and no
amount of scoring fixes a set that contains nothing right.

Pre-generating the gaps does not fix it either. The brief is written fresh from
that morning's moment, and three different briefs asked for a bed and wanted
three different things on it — sitting on the edge staring down, lying face
down, standing beside it. One pre-made bed pose serves one of them.

THE INVARIANT THIS CHANGES, AND WHY IT IS STILL TRUE

AGENTS.md invariant 2 said the render path must never reach the network,
because "a build that needs a network is a build that can fail at 8am with
nobody watching". That reasoning is right and the conclusion was too strong:
what must never fail is the DECK, not the call. So the network is allowed here
and the deck is guaranteed by the fallback instead of by abstinence.

Every path out of generate_for_deck() that is not a finished image returns the
library's pose for that slide. Missing key, refused credentials, HTTP error,
timeout, exhausted neuron budget, a frame that fails a QA gate, a matte that
comes out empty — all of them land in the same place, and the caller cannot
tell the difference except from the count this prints.

Cost and time, measured rather than assumed. One 1024x1024 pose with four
reference images books 188 neurons against a 6,000/day ceiling, so a nine-slide
deck costs about 1,700 and the free allowance covers roughly three decks a day.
A single call took 15 seconds wall-clock on 2026-08-31. PER_POSE_TIMEOUT is far
below poses_flux's own 180s ceiling because a slow generation must not hold up
a deck that has a perfectly good library pose waiting for it.
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutout import QAFailure, auto_chroma_matte  # noqa: E402
from imaging import drop_neighbour_bleed, tight_crop  # noqa: E402

PER_POSE_TIMEOUT = 60          # seconds; the library pose is waiting, so do not wait long
MIN_BRIEF = 15                 # a brief shorter than this describes nothing to draw
NAME_WORDS = 4                 # how much of the brief becomes the pose name

# Words that describe nothing, so they never reach a pose name.
_SKIP = {"the", "and", "with", "his", "her", "its", "a", "an", "of", "in", "on",
         "at", "to", "small", "donkey", "silly", "both", "one", "two"}


def pose_name(brief: str) -> str:
    """A library name for a generated pose: a few words of the brief, plus a
    short digest of the whole thing.

    The digest is what makes re-running a deck safe. Two different briefs can
    open with the same four words, and a name collision would have one pose
    overwrite another in mascot/library/ with nobody told. Hashing the FULL
    brief means the same brief always lands on the same name — so regenerating
    a deck refreshes its poses rather than growing a pile of near-identical
    ones — and any different brief lands somewhere else.
    """
    words = [w for w in re.findall(r"[a-z]+", brief.lower()) if w not in _SKIP]
    stem = "_".join(words[:NAME_WORDS]) or "pose"
    digest = hashlib.sha1(brief.strip().lower().encode()).hexdigest()[:4]
    return f"{stem}_{digest}"


def _matte(raw_bgr) -> "cv2.typing.MatLike":
    """The generated frame as transparent artwork, the same way an import does.

    Deliberately the import path's treatment and not the generation path's:
    a scene has several pieces and a wide silhouette, and poses_flux.check() is
    tuned for one standing figure.

    This matte is for THIS DECK only. The same frame also goes to the library,
    and it goes there raw, through import_poses.py, so that the library's own
    gates and the library's own matte decide. Two writers into mascot/library/
    is how two subtly different libraries happen, so there is still exactly one.
    """
    rgba = auto_chroma_matte(raw_bgr)
    rgba = tight_crop(drop_neighbour_bleed(rgba))
    if rgba.size == 0 or (rgba[:, :, 3] > 128).sum() < 5000:
        raise QAFailure("matte came out empty")
    return rgba


def generate_for_deck(slides: list[dict], fallback: dict[int, Path], out_dir: Path,
                      budget: float | None = None, keep_dir: Path | None = None,
                      log=print) -> tuple[dict[int, Path], dict]:
    """A pose per slide, generated where possible and borrowed where not.

    `fallback` is what library selection already decided, keyed by 1-based slide
    number. The returned mapping has an entry for every key `fallback` had:
    generation never removes a pose, it only replaces one.
    """
    stats = {"generated": 0, "fell_back": 0, "seconds": 0.0, "neurons": 0.0,
             "reasons": [], "kept": []}
    out = dict(fallback)

    # Imported here, not at module scope, so that merely importing this file
    # costs nothing and a broken or absent poses_flux cannot stop a build.
    try:
        import poses_flux as flux
    except Exception as exc:                                  # noqa: BLE001
        stats["reasons"].append(f"generator unavailable: {exc}")
        stats["fell_back"] = len(fallback)
        return out, stats

    try:
        account, token = flux.credentials()
        refs = flux.pick_references()
        ledger = flux.Ledger(budget=budget) if budget else flux.Ledger()
    except Exception as exc:                                  # noqa: BLE001
        stats["reasons"].append(f"no generator credentials: {exc}")
        stats["fell_back"] = len(fallback)
        return out, stats

    out_dir.mkdir(parents=True, exist_ok=True)
    for number, _pose_path in sorted(fallback.items()):
        slide = slides[number - 1] if number - 1 < len(slides) else {}
        brief = (slide.get("mascot") or "").strip()
        if len(brief) < MIN_BRIEF:
            stats["fell_back"] += 1
            stats["reasons"].append(f"slide {number}: no usable brief")
            continue

        started = time.time()
        try:
            reserved = flux.estimate_neurons(1024, 1024, len(refs))
            ledger.check(reserved)
            ledger.spend(reserved, note=f"deck-slide-{number}")
            blob, billed = flux.generate(
                flux.build_prompt(brief), refs, width=1024, height=1024,
                account=account, token=token, timeout=PER_POSE_TIMEOUT)
            ledger.reconcile(reserved, billed, note=f"deck-slide-{number}")
            stats["neurons"] += reserved

            arr = cv2.imdecode(flux.np.frombuffer(blob, flux.np.uint8), cv2.IMREAD_COLOR)
            if arr is None:
                raise QAFailure("model returned something that is not an image")
            # Invariant 3 first, on the frame BEFORE matting, exactly as
            # everywhere else: matting throws a caption away and then the
            # artwork looks clean.
            flux.assert_no_text(arr, f"slide {number}")
            arr = flux.correct_palette(arr)
            rgba = _matte(arr)

            dest = out_dir / f"{number:02d}_fresh.png"
            ok, buf = cv2.imencode(".png", rgba)
            if not ok:
                raise QAFailure("could not encode the matted pose")
            dest.write_bytes(buf.tobytes())

            # Keep the RAW magenta frame for the library, never the matte. The
            # library is grown by import_poses.py and by nothing else, and it
            # wants the frame before matting so its own gates and its own matte
            # decide. The brief travels with it as a sidecar so the pose enters
            # the library tagged with the BODY it was drawn from, which is the
            # vocabulary selection has never had.
            if keep_dir is not None:
                keep_dir.mkdir(parents=True, exist_ok=True)
                name = pose_name(brief)
                ok_raw, raw_buf = cv2.imencode(".png", arr)
                if ok_raw:
                    (keep_dir / f"{name}.png").write_bytes(raw_buf.tobytes())
                    (keep_dir / f"{name}.brief.txt").write_text(brief, encoding="utf-8")
                    stats["kept"].append(name)
            out[number] = dest
            stats["generated"] += 1
            log(f"  [{number}] generated in {time.time() - started:.0f}s")
        except Exception as exc:                              # noqa: BLE001
            # EVERY failure is the same failure: the slide keeps its library
            # pose. Nothing here is allowed to end a build.
            stats["fell_back"] += 1
            stats["reasons"].append(f"slide {number}: {type(exc).__name__}: {exc}")
            log(f"  [{number}] fell back to {fallback[number].stem} "
                f"({type(exc).__name__})")
        finally:
            stats["seconds"] += time.time() - started

    return out, stats
