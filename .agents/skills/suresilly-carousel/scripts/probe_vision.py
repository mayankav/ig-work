#!/usr/bin/env python3
"""
probe_vision.py — measure which models can actually look at a picture.

Two model ids in llm.py were written from documentation and nothing else:
GROQ_VISION_MODEL and CLOUDFLARE_VISION_MODEL. Gemini needs no id of its own —
every model in GEMINI_MODELS is multimodal, so a picture rides the same five
daily buckets as the writing. This script is how those stop being assumptions.

    probe_vision.py                 every vendor, the ids llm.py names
    probe_vision.py --gemini-all    every Gemini bucket, one at a time
    probe_vision.py --groq meta-llama/llama-4-maverick-17b-128e-instruct

WHY ACCEPTANCE IS THE EASY HALF

A model that takes an image and answers politely has proved almost nothing. The
job here is to see a donkey with six legs and say so, and a model that reports
"faults: []" for everything passes an acceptance test perfectly while vetoing
nothing forever — which is the failure that looks green.

So two pictures go out, not one. A control donkey with four legs, and the same
donkey with six. The column that matters is the last one:

    sees six    faulted the six-legged donkey       ← the whole point
    quiet on 4  left the four-legged one alone      ← not trigger-happy

A model that fails either column is not usable as a veto: one waves everything
through, the other throws every generated pose away and turns the feature into
an expensive way to use the library.

This is offline tooling. Nothing in the pipeline imports it, it spends real
quota, and it is run by hand when a model id needs proving.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fresh_poses  # noqa: E402
import llm  # noqa: E402

BODY = (90, 150, 60)        # BGR, roughly the mascot green
INK = (30, 30, 30)


def donkey(legs: int, size: int = 512) -> np.ndarray:
    """A crude donkey with however many legs you ask for, on flat grey.

    Deliberately crude. If a model needs a beautiful drawing to count legs it
    cannot do this job on our artwork either, which is generated and often
    rough. Drawn as BGRA so it can go through contact_grid, which is the
    composition the real check uses — probing a differently-built picture would
    measure a code path nothing runs.
    """
    art = np.zeros((size, size, 4), np.uint8)
    cx, cy = size // 2, int(size * 0.5)
    cv2.ellipse(art, (cx, cy), (int(size * 0.24), int(size * 0.15)), 0, 0, 360,
                (*BODY, 255), -1)
    cv2.circle(art, (cx - int(size * 0.24), cy - int(size * 0.16)),
               int(size * 0.11), (*BODY, 255), -1)        # head
    for side in (-1, 1):                                   # ears
        cv2.ellipse(art, (cx - int(size * 0.26) + side * 14, cy - int(size * 0.27)),
                    (9, 26), side * 12, 0, 360, (*BODY, 255), -1)
    for dx in (-0.29, -0.20):                              # eyes, with pupils
        ex = cx + int(size * dx)
        ey = cy - int(size * 0.18)
        cv2.circle(art, (ex, ey), 13, (255, 255, 255, 255), -1)
        cv2.circle(art, (ex, ey), 5, (*INK, 255), -1)

    span = int(size * 0.40)
    left = cx - span // 2
    step = span // max(1, legs - 1)
    top = cy + int(size * 0.10)
    for index in range(legs):
        x = left + index * step
        cv2.rectangle(art, (x - 9, top), (x + 9, top + int(size * 0.22)),
                      (*BODY, 255), -1)
    return art


def one(name: str, model: str | None = None) -> dict:
    """Send both pictures to one vendor and report what it did with them."""
    providers = tuple(p for p in llm.PROVIDERS if p[0] == name)
    if not providers:
        return {"error": f"no provider called {name}"}
    if not llm.configured(name):
        return {"error": "no credentials on this machine"}

    saved = {}
    if model:
        # Pinned one model at a time, because "Gemini works" is not the answer
        # anyone needs — the buckets empty separately and a run reaches the
        # smaller ids only once the good ones are gone.
        if name == "gemini":
            saved["GEMINI_MODELS"] = llm.GEMINI_MODELS
            llm.GEMINI_MODELS = (model,)
            llm._SPENT.clear()
        elif name == "groq":
            saved["GROQ_VISION_MODEL"] = llm.GROQ_VISION_MODEL
            llm.GROQ_VISION_MODEL = model
        elif name == "cloudflare":
            saved["CLOUDFLARE_VISION_MODEL"] = llm.CLOUDFLARE_VISION_MODEL
            llm.CLOUDFLARE_VISION_MODEL = model

    result = {"vendor": name, "model": model or "(as configured)"}
    try:
        for legs, key in ((4, "quiet_on_four"), (6, "sees_six")):
            grid = fresh_poses.contact_grid({1: donkey(legs)})
            answer, _ = llm.look(
                fresh_poses.VISION_SYSTEM,
                "The sheet holds 1 numbered panel: 1. Check it and list the "
                "faults you can point at.",
                fresh_poses.VISION_SCHEMA, grid, providers=providers)
            faults = answer.get("faults") or []
            result[key] = (not faults) if legs == 4 else bool(faults)
            result[f"said_{legs}"] = "; ".join(
                str(f.get("fault", ""))[:60] for f in faults) or "nothing"
        result["accepted"] = True
    except Exception as exc:                                  # noqa: BLE001
        result["accepted"] = False
        result["error"] = f"{type(exc).__name__}: {str(exc)[:150]}"
    finally:
        for attr, value in saved.items():
            setattr(llm, attr, value)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--gemini-all", action="store_true",
                    help="probe every Gemini bucket separately")
    ap.add_argument("--groq", action="append", default=[], metavar="MODEL",
                    help="an extra Groq model id to try")
    ap.add_argument("--cloudflare", action="append", default=[], metavar="MODEL",
                    help="an extra Cloudflare model id to try")
    args = ap.parse_args(argv)

    jobs: list[tuple[str, str | None]] = []
    if args.gemini_all:
        jobs += [("gemini", m) for m in llm.GEMINI_MODELS]
    else:
        jobs.append(("gemini", None))
    jobs.append(("groq", llm.GROQ_VISION_MODEL))
    jobs += [("groq", m) for m in args.groq]
    jobs.append(("cloudflare", llm.CLOUDFLARE_VISION_MODEL))
    jobs += [("cloudflare", m) for m in args.cloudflare]

    print(f"{'vendor':11} {'model':46} {'took it':>8} {'sees 6':>7} {'quiet on 4':>11}")
    print("-" * 88)
    usable = 0
    detail = []
    for name, model in jobs:
        r = one(name, model)
        if not r.get("accepted"):
            print(f"{name:11} {str(r['model'])[:46]:46} "
                  f"{'no':>8}   {r.get('error', '')[:40]}")
            continue
        good = r["sees_six"] and r["quiet_on_four"]
        usable += good
        print(f"{name:11} {str(r['model'])[:46]:46} {'yes':>8} "
              f"{('yes' if r['sees_six'] else 'NO'):>7} "
              f"{('yes' if r['quiet_on_four'] else 'NO'):>11}"
              f"{'' if good else '   x'}")
        detail.append(r)

    print(f"\n{usable} of {len(jobs)} usable as a veto")
    for r in detail:
        print(f"\n  {r['vendor']} {r['model']}")
        print(f"    on the six-legged donkey: {r['said_6']}")
        print(f"    on the four-legged one:   {r['said_4']}")
    if not usable:
        print("\nNo model both saw the fault and left the good one alone. Until one "
              "does,\nfresh_poses vetoes every generated pose and the deck uses the "
              "library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
