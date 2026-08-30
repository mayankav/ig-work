#!/usr/bin/env python3
"""
probe_phrases.py — measure a search phrase before trusting it.

The phrases in sources.py decide the entire topical range of the account: every
post we ever write comes from something one of them found. They were written by
me, from taste, which is a bad way to decide the range of anything.

This makes a phrase testable. Give it candidates, it searches each one, runs
every result through the same screen a real run uses, and reports the share that
survives. A phrase that yields nothing is dropped whatever it sounded like.

The measurement matters because intuition here is unreliable. The obvious idea
was to stop guessing phrases entirely and stream everything Bluesky publishes,
letting the filters do the work. Measured: 1,767 posts over four minutes
produced ZERO usable moments, against roughly 1.7% for phrase search. Bluesky's
search index is doing the work, not the filters, and an unbiased sample of the
internet is almost entirely bots, sport and links.

So candidates can come from anywhere. What they cannot do is skip the number.

  probe_phrases.py "sat in the car" "still at my desk at" "cancelled on me"
  probe_phrases.py --current

One caution about reading the output. The screen measures SHAPE, not subject: a
post can be first person, filmable and about a browser tab. So a rate is a
filter, not a verdict, and the examples printed underneath are the part that
tells you whether a phrase found the right kind of evening. Read them.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import screen  # noqa: E402
import sources  # noqa: E402

# Bluesky's search returns at most 100 per call, and we take all of them. A
# smaller sample cannot support a verdict: at 25 posts a single hit reads as 4%
# and zero hits only means "fewer than one in twenty five", which is not evidence
# that a phrase is bad. At 100 the resolution is 1% and a zero starts to mean
# something.
SAMPLE = 100
# Below this, a phrase is finding the wrong kind of post. Judge it against the
# whole harvest, which runs at roughly 1.7%.
KEEP_THRESHOLD = 0.02
# Searches back to back get throttled, and a throttled phrase reports as an
# error rather than as a bad phrase, which is a different thing.
PAUSE = 2.5


def probe(phrase: str, sample: int = SAMPLE) -> dict:
    """Search one phrase and report what survives the screen."""
    try:
        results = sources.search(phrase, limit=sample)
    except sources.SourceUnavailable as exc:
        return {"phrase": phrase, "error": str(exc)[:60], "found": 0, "kept": 0,
                "rate": 0.0, "examples": []}

    kept = []
    for item in results:
        verdict = screen.screen(item["text"])
        if verdict["ok"]:
            kept.append(verdict["text"])

    return {
        "phrase": phrase,
        "error": None,
        "found": len(results),
        "kept": len(kept),
        "rate": len(kept) / len(results) if results else 0.0,
        "examples": kept[:2],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure search phrases before trusting them.")
    ap.add_argument("phrases", nargs="*", help="candidate phrases to test")
    ap.add_argument("--current", action="store_true", help="test the phrases in use today")
    ap.add_argument("--sample", type=int, default=SAMPLE)
    args = ap.parse_args()

    phrases = list(sources.QUERIES) if args.current else args.phrases
    if not phrases:
        ap.error("give some phrases, or --current")

    print(f"{'phrase':34} {'found':>6} {'kept':>5} {'rate':>7}")
    print("-" * 56)
    results = []
    for index, phrase in enumerate(phrases):
        if index:
            time.sleep(PAUSE)
        result = probe(phrase, args.sample)
        results.append(result)
        if result["error"]:
            print(f"{phrase[:34]:34} {'':>6} {'':>5} {result['error']}")
        else:
            mark = " " if result["rate"] >= KEEP_THRESHOLD else "x"
            print(f"{phrase[:34]:34} {result['found']:>6} {result['kept']:>5} "
                  f"{result['rate']:>6.0%} {mark}")

    good = [r for r in results if r["rate"] >= KEEP_THRESHOLD]
    print(f"\n{len(good)} of {len(results)} phrases clear {KEEP_THRESHOLD:.0%}")
    for result in good[:6]:
        if result["examples"]:
            print(f"\n  {result['phrase']!r}")
            for example in result["examples"]:
                print(f"    {example[:96]}")


if __name__ == "__main__":
    main()
