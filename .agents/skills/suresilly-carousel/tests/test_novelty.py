#!/usr/bin/env python3
"""
Novelty gate regression.

This gate exists because of a specific incident: four decks shipped in two days
carrying the same slides 3 to 9 under different hooks. So the test is built from
both populations we have actually observed.

  REAL      the three hand-written decks in carousels/. These are what "new"
            looks like, and the gate must never block them. Measured against
            each other they sit at 0.000 to 0.004 word overlap.
  RECYCLED  a deck assembled by copying slides out of a real one, which is what
            the broken generator was doing. The real thing measured 0.756 to
            0.837, so a synthetic copy is a fair stand-in and does not require
            keeping the bad decks in the repo.

Two orders of magnitude separate the populations, which is why the limits can
sit at 0.15 without being delicate.
"""
import itertools
import json
import pathlib
import sys
import tempfile
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import novelty  # noqa: E402
import render  # noqa: E402

CAROUSELS = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent / "carousels"

TEXT_KEYS = ("h1", "h2", "body", "source_claim", "source_translation", "source_explains",
             "old_reaction", "new_reaction", "myth", "reality", "closing", "cta1", "callout")


def text_of(slide: dict) -> str:
    return " ".join([str(slide[k]) for k in TEXT_KEYS if k in slide] + slide.get("bullets", []))


def use_temp_state(tmp: pathlib.Path) -> None:
    novelty.STATE_DIR = tmp
    novelty.FP_DIR = tmp / "fp"
    novelty.INDEX_PATH = tmp / "fp_index.json"
    novelty.PHRASES_PATH = tmp / "phrases.json"


def run() -> int:
    failures = []
    decks = sorted(CAROUSELS.glob("*/carousel.md"))
    if len(decks) < 2:
        print("novelty: skipped, needs at least two decks in carousels/")
        return 0

    prints = {
        d.parent.name: novelty.fingerprint(d.parent.name, render.parse_markdown(d),
                                           anchors=["kitchen"], text_of=text_of)
        for d in decks
    }

    # Real decks must sit well clear of every limit.
    for a, b in itertools.combinations(prints, 2):
        overlap = novelty.jaccard(set(prints[a]["deck_shingles"]), set(prints[b]["deck_shingles"]))
        vocab = novelty.cosine(Counter(prints[a]["terms"]), Counter(prints[b]["terms"]))
        runs = set(prints[a]["runs"]) & set(prints[b]["runs"])
        if overlap >= novelty.DECK_JACCARD_MAX:
            failures.append(f"REAL {a} vs {b}: overlap {overlap:.3f} would be blocked")
        if vocab >= novelty.COSINE_MAX:
            failures.append(f"REAL {a} vs {b}: vocabulary {vocab:.3f} would be blocked")
        if runs:
            failures.append(f"REAL {a} vs {b}: {len(runs)} shared run(s), probably an unmasked brand phrase")

    # The gate must pass a real deck against the others, and block a recycled one.
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        use_temp_state(tmp)

        names = list(prints)
        for name in names[:-1]:
            novelty.record(prints[name])

        fresh = novelty.check(prints[names[-1]])
        if fresh:
            failures.append(f"REAL {names[-1]} was blocked: {fresh[0]}")

        # Recycle: take a published deck's slides and call it a new deck.
        source = prints[names[0]]
        recycled = json.loads(json.dumps(source))
        recycled["slug"] = "20260830_recycled"
        blocked = novelty.check(recycled)
        if not blocked:
            failures.append("RECYCLED a copied deck passed the gate")
        else:
            kinds = " ".join(blocked)
            if "word-for-word" not in kinds:
                failures.append("RECYCLED slide reuse was not named in the reasons")
            if "run(s) of" not in kinds:
                failures.append("RECYCLED copied runs were not named in the reasons")

        # Half a copy must still fail. A deck that keeps the value slides and
        # swaps the hook is exactly what the broken generator produced.
        half = json.loads(json.dumps(prints[names[-1]]))
        half["slug"] = "20260830_half"
        half["slides"][3:] = json.loads(json.dumps(source["slides"][3:]))
        half["runs"] = sorted(set(half["runs"]) | set(source["runs"][:40]))
        if not novelty.check(half):
            failures.append("HALF a deck reusing only its value slides passed the gate")

    if failures:
        print(f"novelty: {len(failures)} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    pairs = len(list(itertools.combinations(prints, 2)))
    print(f"novelty: passed ({len(prints)} real decks, {pairs} pairs clear of the limits, "
          f"recycled and half-recycled decks both blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
