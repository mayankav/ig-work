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
reference images books about 126 neurons against a 6,000/day ceiling, so a
nine-slide deck costs about 1,130 and the ceiling covers five decks a day.
A single call took 15 seconds wall-clock on 2026-08-31. PER_POSE_TIMEOUT is far
below poses_flux's own 180s ceiling because a slow generation must not hold up
a deck that has a perfectly good library pose waiting for it.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402
from cutout import (  # noqa: E402
    QAFailure, assert_has_pupils, auto_chroma_matte, detect_key_colour, qa,
)
from imaging import drop_neighbour_bleed, tight_crop  # noqa: E402

PER_POSE_TIMEOUT = 60          # seconds; the library pose is waiting, so do not wait long
MIN_BRIEF = 15                 # a brief shorter than this describes nothing to draw
NAME_WORDS = 4                 # how much of the brief becomes the pose name

# Words that describe nothing, so they never reach a pose name.
_SKIP = {"the", "and", "with", "his", "her", "its", "a", "an", "of", "in", "on",
         "at", "to", "small", "donkey", "silly", "both", "one", "two"}

VISION_TILE = 512              # pixels per panel; nine of them make a 1536px sheet
GRID_QUALITY = 82              # JPEG quality — about 200KB for the whole sheet
GRID_BG = (128, 128, 128)      # flat mid grey: not the mascot green, not a bubble white

VISION_SCHEMA = {
    "type": "object",
    "required": ["faults"],
    "properties": {
        "faults": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["panel", "fault"],
                "properties": {
                    # Ranged, because a schema that accepts panel 47 turns a
                    # confused reply into a silent no-op instead of a complaint.
                    "panel": {"type": "integer", "minimum": 1, "maximum": 9},
                    "fault": {"type": "string", "minLength": 4, "maxLength": 120},
                },
            },
        },
    },
}

# Written to be a VETO and nothing else — invariant 11: a model may write and may
# veto, it may never approve. There is no field here for "this one is fine",
# because the deterministic gates above have already decided that. The only
# thing this reply can do is take a pose away.
#
# The fault list is mechanical on purpose. "Does this look right" is a taste
# question and taste is what the rules own; counting limbs is a perception
# question, which is the one thing a model can do here that no gate can.
VISION_SYSTEM = """\
You are checking drawings of a cartoon donkey for anatomy that is impossible.

Report a panel ONLY when you can point at one of these:
  - one animal with more than four legs
  - one figure with more than two arms, or more than two hands
  - a limb, hoof or hand that connects to nothing
  - a second head, or more than two eyes on one face
  - two bodies melted into each other

These are NOT faults, and reporting them is wrong:
  - two or three SEPARATE complete donkeys in one panel — often asked for
  - a limb hidden behind a prop, a wall or the animal's own body
  - a tail, ears, a held object, a shadow
  - anything about colour, style, framing, or how well it is drawn

If you are not sure, leave it out. Return {"faults": []} when nothing is wrong.
"""


def contact_grid(tiles: dict[int, "cv2.typing.MatLike"], tile: int = VISION_TILE) -> bytes:
    """The generated poses as one numbered JPEG sheet.

    One picture instead of nine, because nine calls a run would not fit. Measured
    from state/vendor_quotas.json: 2026-09-01 emptied gemini-2.5-flash at 28
    calls and gemini-2.5-flash-lite at 18, in a day that made two decks. Adding
    eighteen vision calls to that would push the WRITER out of quota, which
    turns green days amber to protect against a fault that has never stopped a
    deck.

    Each panel carries its own SLIDE number, drawn on. That is the whole reason
    the number is there: the reply says "panel 3" and slide 3 is what loses its
    pose, with no table in between to get out of step. Panels with no pose are
    left blank and unnumbered.

    The digits are not a violation of invariant 3. That rule governs ARTWORK —
    what goes into the library and onto a slide. This sheet is an inspection
    copy: it is built in memory, sent, and dropped, and no path writes it
    anywhere. The mattes it is made from have already passed assert_no_text.
    """
    numbers = sorted(tiles)
    cols = max(1, math.ceil(math.sqrt(len(numbers))))
    rows = max(1, math.ceil(len(numbers) / cols))
    sheet = np.full((rows * tile, cols * tile, 3), GRID_BG, dtype=np.uint8)

    for index, number in enumerate(numbers):
        rgba = tiles[number]
        h, w = rgba.shape[:2]
        # 24px of air on every side, so a figure that touches its own edge is
        # still visibly touching an edge and not mistaken for a cropped limb.
        scale = min((tile - 48) / max(w, 1), (tile - 48) / max(h, 1))
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        small = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_AREA)

        top = (index // cols) * tile + (tile - nh) // 2
        left = (index % cols) * tile + (tile - nw) // 2
        patch = sheet[top:top + nh, left:left + nw]
        alpha = (small[:, :, 3:4].astype(np.float32) / 255.0)
        sheet[top:top + nh, left:left + nw] = (
            small[:, :, :3].astype(np.float32) * alpha
            + patch.astype(np.float32) * (1 - alpha)).astype(np.uint8)

        # Hershey is compiled into OpenCV, so unlike invariant 7's typefaces it
        # cannot fail to load and there is nothing to verify.
        cv2.putText(sheet, str(number),
                    ((index % cols) * tile + 14, (index // cols) * tile + 46),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, (0, 0, 220), 3, cv2.LINE_AA)

    ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, GRID_QUALITY])
    if not ok:
        raise QAFailure("could not encode the inspection sheet")
    return buf.tobytes()


def anatomy_faults(tiles: dict[int, "cv2.typing.MatLike"], log=print) -> dict[int, str]:
    """Which generated poses have anatomy no donkey has. Fails CLOSED.

    A limb count cannot be written as a gate, and this was measured rather than
    assumed: profiling silhouette runs across the leg band of all 194 library
    poses, 25 of them have a median count of three or more, because hugging,
    high_five, far_apart2, laughing_together, shoulder_hold, mirroring and
    pursue_withdraw are TWO-donkey poses where four legs is correct, and
    gardener, hero_landing and clinging hold props. No threshold separates a
    malformed donkey from two correct ones, and a fault nothing can answer is a
    stopped engine rather than a strict gate — invariant 21.

    So this is the one place a model is allowed to look at the artwork, and it
    is allowed to do exactly one thing with it: take a pose away.

    Every failure — no vendor, a refusal, a timeout, a reply that will not
    parse — vetoes EVERY tile. That is the uncomfortable direction on purpose.
    The alternative is publishing unchecked art whenever a vendor has a bad
    afternoon, which is the exact failure this was built for, and the cost of
    being wrong is nine library poses and a deck that still goes out.
    """
    if not tiles:
        return {}
    numbers = sorted(tiles)
    try:
        grid = contact_grid(tiles)
        answer, vendor = llm.look(
            VISION_SYSTEM,
            f"The sheet holds {len(numbers)} numbered panels: "
            + ", ".join(str(n) for n in numbers)
            + ". Check each one and list the faults you can point at.",
            VISION_SCHEMA, grid)
    except Exception as exc:                                  # noqa: BLE001
        log(f"  anatomy check unavailable ({type(exc).__name__}), "
            f"keeping the library poses")
        return {n: f"anatomy unchecked: {type(exc).__name__}" for n in numbers}

    faults: dict[int, str] = {}
    for item in answer.get("faults") or []:
        panel = item.get("panel")
        if panel in tiles:
            faults[panel] = str(item.get("fault", "anatomy"))[:100]
    log(f"  anatomy checked by {vendor}: {len(faults)} of {len(numbers)} vetoed")
    return faults


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
             "reasons": [], "kept": [], "vetoed": []}
    out = dict(fallback)

    # Asked BEFORE a single neuron is spent. The anatomy check is a veto, so
    # with no vendor to run it every generated pose would be thrown away — and
    # thrown away after roughly 1,130 neurons had drawn it. Nine library poses
    # are the same deck for nothing.
    if not llm.vision_ready():
        stats["reasons"].append("no vendor can check anatomy, so nothing was drawn")
        stats["fell_back"] = len(fallback)
        return out, stats

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
        # Probed once so a missing library or an unreadable reference fails here
        # rather than nine times inside the loop. The real set is chosen per
        # slide, because the brief decides half of it.
        flux.pick_references()
        ledger = flux.Ledger(budget=budget) if budget else flux.Ledger()
    except Exception as exc:                                  # noqa: BLE001
        stats["reasons"].append(f"no generator credentials: {exc}")
        stats["fell_back"] = len(fallback)
        return out, stats

    out_dir.mkdir(parents=True, exist_ok=True)
    # What each slide produced, kept so a veto can undo it completely: the
    # matte goes to the inspection sheet, the two paths get deleted, and the
    # library name comes back out of stats["kept"] before build.py offers it.
    made: dict[int, dict] = {}
    for number, _pose_path in sorted(fallback.items()):
        slide = slides[number - 1] if number - 1 < len(slides) else {}
        brief = (slide.get("mascot") or "").strip()
        if len(brief) < MIN_BRIEF:
            stats["fell_back"] += 1
            stats["reasons"].append(f"slide {number}: no usable brief")
            continue

        started = time.time()
        kept_name: str | None = None
        try:
            # Half anchors, half chosen for the posture this brief describes.
            # References decide the body: measured twice, a brief asking for a
            # lowered head came back alert and a brief asking to tumble came
            # back mid-jump, both times against four upright references.
            refs = flux.pick_references(brief=brief)
            reserved = flux.estimate_neurons(1024, 1024, len(refs))
            ledger.check(reserved)
            ledger.spend(reserved, note=f"deck-slide-{number}")
            blob, billed = flux.generate(
                flux.build_prompt(brief), refs, width=1024, height=1024,
                account=account, token=token, timeout=PER_POSE_TIMEOUT)
            ledger.reconcile(reserved, billed, note=f"deck-slide-{number}")
            stats["neurons"] += reserved

            arr = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
            if arr is None:
                raise QAFailure("model returned something that is not an image")
            # Invariant 3 first, on the frame BEFORE matting, exactly as
            # everywhere else: matting throws a caption away and then the
            # artwork looks clean.
            flux.assert_no_text(arr, f"slide {number}")
            arr = flux.correct_palette(arr)
            rgba = _matte(arr)
            # Invariant 3's other gate on the artwork, and the one this path
            # shipped without. poses_flux.check() has always called it; this
            # function does not go through check() — a scene has several pieces
            # and check() is tuned for one standing figure — and in taking its
            # own route it took only one of the three gates with it. That is
            # how 20260901_door-pushed-the_572b21 went out with a blank white
            # oval for slide 3's left eye: not a gate that failed, a gate that
            # was never called. Measured on that slide, the two eye whites are
            # 38x37 and 41x40 and the left one has no pupil — assert_has_pupils
            # refuses that frame outright, and the slide would have fallen back
            # to its library pose. It runs on the MATTED figure because it
            # reads alpha to know what is artwork.
            assert_has_pupils(rgba, f"slide {number}")
            # The structural gates, and the second one this path shipped
            # without. Same reasoning as the line above: check() calls qa() and
            # this function does not go through check(), so it inherited none of
            # it. The configuration is import_poses.py's, not check()'s, for the
            # reason _matte already gives — a deck scene has several pieces and
            # a wide silhouette, and _matte tight-crops, after which the subject
            # touches every edge by definition. allow_detached and loose framing
            # are what is left, and they still catch a magenta fringe the matte
            # missed, a caption baked under the artwork, and a subject lost in
            # its own frame.
            qa(rgba, src_shape=arr.shape[:2], allow_detached=True,
               strict_framing=False, key_bgr=detect_key_colour(arr))

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
                    kept_name = name
            out[number] = dest
            made[number] = {"rgba": rgba, "dest": dest, "kept": kept_name}
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

    # One look at all of it, after the drawing and before the deck. Everything
    # above this line is deterministic and everything below it is a model, which
    # is the order that matters: the gates decide what is admissible and the
    # model may only take more away.
    for number, fault in anatomy_faults({n: m["rgba"] for n, m in made.items()},
                                        log=log).items():
        entry = made[number]
        # Undone completely, not just unlinked from the deck. A vetoed pose left
        # in out_dir is a file the next thing to read that folder will find, and
        # one left in keep_dir is a malformed donkey offered to the library —
        # where it would be selectable by every deck after this one.
        entry["dest"].unlink(missing_ok=True)
        if entry["kept"]:
            if keep_dir is not None:
                (keep_dir / f"{entry['kept']}.png").unlink(missing_ok=True)
                (keep_dir / f"{entry['kept']}.brief.txt").unlink(missing_ok=True)
            if entry["kept"] in stats["kept"]:
                stats["kept"].remove(entry["kept"])
        out[number] = fallback[number]
        stats["generated"] -= 1
        stats["fell_back"] += 1
        stats["vetoed"].append(number)
        stats["reasons"].append(f"slide {number}: {fault}")
        log(f"  [{number}] vetoed, fell back to {fallback[number].stem}: {fault}")

    return out, stats
