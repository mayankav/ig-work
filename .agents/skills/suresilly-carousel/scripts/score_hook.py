#!/usr/bin/env python3
"""
score_hook.py — 5-dimension hook rubric for @suresilly.

Adversarial, deterministic starter. Not an LLM judge — scores what can be
measured so the author cannot hand-wave a weak hook to a pass. Use before
committing a hook; the ledger is the memory.

Dimensions (10 each, 50 total). Ship only ≥32. Below 32 → find a sharper scene.

Usage:
  .venv/bin/python scripts/score_hook.py "You reread their two-word reply four times."
  .venv/bin/python scripts/score_hook.py --ledger  # scores every hook in carousels/HOOK_LEDGER.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EARLY_JARGON = (
    "nervous system", "attachment", "regulation", "cortisol",
    "polyvagal", "trauma response", "fawn response", "hypervigilance",
    "emotional flashback", "somatic", "neuroception", "identity trap",
)

BANNED_OPENERS = re.compile(r"(?i)^\s*(why|how to|the reason|what nobody|most people|here'?s)\b")


def clean(text: str) -> str:
    text = re.sub(r"\[\[|\]\]", "", text)
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    return text.strip()


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", clean(text))


def score_hook(h1: str, h2: str = "") -> dict:
    c = clean(h1)
    wc = len(words(c))
    lc = c.lower()

    # 1 Gap — does it leave something open?
    gap = 5
    # two-sentence hooks explain themselves → kill gap
    if c.count(".") >= 1 and len(c.split(".")) > 2 or "you're not" in lc and ". you" in lc:
        gap = 3
    elif wc <= 8 and not re.search(r"\bbecause\b|\bso\b|\bwhich means\b", lc):
        gap = 8
    else:
        gap = 5
    # open-loop markers: unfinished, "never about", ellipses, specific noun without explanation
    if re.search(r"never about|before they did|four times|shoes on|the key", lc):
        gap = min(10, gap + 2)
    if BANNED_OPENERS.search(c):
        gap = min(gap, 4)  # banned opener caps gap — scene never lands in first 3 words
        # further penalty applied in clarity below

    # 2 Specificity — odd concrete detail vs generic
    spec = 5
    if re.search(r"\b\d+\b|face-down|two-word|shoes on|the key|dishes|four times|typing\b", lc):
        spec = 9
    elif re.search(r"you (typed|reread|heard|staring|feel|knew)", lc):
        spec = 7
    elif wc <= 6 and "you" in lc:
        spec = 6
    elif len(c) < 20:
        spec = 4

    # 3 Relevance — says "you"
    rel = 10 if re.search(r"\byou\b|\byour\b|\byou're\b", lc) else 3

    # 4 Clarity — ≤8 words, no jargon, no comma splice
    clar = 10
    if wc > 8:
        clar -= 3 + (wc - 8)
    if any(t in lc for t in EARLY_JARGON):
        clar -= 4
    if h2 and len(words(h2)) > 7:
        clar -= 2
    if BANNED_OPENERS.search(c):
        clar -= 4
    clar = max(1, min(10, clar))

    # 5 Trust — promises only what slide 2 can pay; no bait, no timeframe scam
    trust = 8
    if re.search(r"\b30 days\b|\bfix.*in\b|\btransform\b.*\b(days|weeks)\b", lc):
        trust = 3
    if wc > 8 and "." in c:
        trust -= 2  # two-sentence gap-killer hurts trust too
    trust = max(1, min(10, trust))

    total = gap + spec + rel + clar + trust
    # hard cap: banned opener can never ship on score alone — matches audit_copy gate
    if BANNED_OPENERS.search(c):
        total = min(total, 31)
    return {"gap": gap, "specificity": spec, "relevance": rel, "clarity": clar, "trust": trust, "total": total, "words": wc}


def main() -> None:
    ap = argparse.ArgumentParser(description="Score a hook on the 5-dimension rubric (50).")
    ap.add_argument("hook", nargs="?", help="Hook text (H1)")
    ap.add_argument("--h2", default="", help="Subtitle (H2)")
    args = ap.parse_args()

    if not args.hook:
        ap.print_help()
        raise SystemExit(1)

    s = score_hook(args.hook, args.h2)
    print(f"Hook: \"{clean(args.hook)}\"  ({s['words']}w)")
    if args.h2:
        print(f"H2:   \"{clean(args.h2)}\"")
    print(f"  Gap:         {s['gap']:>2}/10")
    print(f"  Specificity: {s['specificity']:>2}/10")
    print(f"  Relevance:   {s['relevance']:>2}/10")
    print(f"  Clarity:     {s['clarity']:>2}/10")
    print(f"  Trust:       {s['trust']:>2}/10")
    print(f"  TOTAL:       {s['total']:>2}/50  {'SHIP' if s['total'] >= 32 else 'REWRITE — below 32'}")
    if s["total"] < 32:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
