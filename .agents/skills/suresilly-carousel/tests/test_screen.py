#!/usr/bin/env python3
"""
Layer 1 and layer 2 regression.

These two filters run on every candidate from a public feed, thousands a day,
and they are the only part of the pipeline whose recall has to be perfect. A
moment that should have been rejected and was not becomes a published post with
nobody in the loop.

The cases below are split on purpose.

  MUST_REJECT   getting one of these wrong is a harm, not a miss. Any failure
                here is a release blocker.
  MUST_KEEP     good moments the filter must not throw away. Failures here cost
                supply, which we have plenty of, so they are bugs but not
                emergencies.
  EXTRACTION    long chatty posts with one filmable moment inside. Roughly half
                of everything the feed returns looks like this, so the extractor
                is worth as much yield as every other tuning combined.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import screen  # noqa: E402

# (text, family we expect to catch it)
MUST_REJECT = [
    ("I woke up at 3am and thought about killing myself again.", "crisis"),
    ("Stood in the kitchen at 2am and wanted to die honestly.", "crisis"),
    ("I want to k1ll myself, I stood in the kitchen at 2am.", "crisis"),
    ("Checked my phone at 4am, thought about how everyone is better off without me.", "crisis"),
    ("I cut myself again last night at 11pm in the bathroom.", "self_harm"),
    ("Sat on the bathroom floor at 1am counting calories, 900 today.", "eating"),
    ("I took 50mg at 11pm in the kitchen and stared at the ceiling.", "medication"),
    ("Upped my dose last week and woke at 3am with my heart pounding.", "medication"),
    ("He hit me in the kitchen at 9pm and I just stood there.", "abuse"),
    ("I am 16 and my mum shouted at me in the kitchen this morning.", "minor"),
    ("Woke at 2am hearing voices again, sat on the couch until six.", "psychosis"),
    ("Drinking alone at 11pm in the kitchen again, third night running.", "substances"),
    ("My ADHD meant I stared at the screen at 4pm and did nothing.", "clinical"),
]

MUST_KEEP = [
    "I woke at 2:17am with my heart pounding and could not get back to sleep.",
    "I reread their one word reply four times and checked the time twice.",
    "I stood in the kitchen at 11pm and could not decide what to eat.",
    "I closed my laptop at 8:30pm and refreshed my inbox from the sofa.",
    "I typed and deleted the same message six times before I sent it.",
    "I sat in the car outside my own house for twenty minutes.",
]

# Shape problems. These are not harmful, they just cannot carry a deck.
MUST_DROP_SHAPE = [
    "I have been feeling a lot of anxiety about my healing journey lately.",
    "You should try setting a boundary with your family this week.",
    "5 things I learned about my anxiety at 3am in the kitchen.",
    "Anyone else stare at the ceiling at 3am? dm me, link in bio",
    "Every day I sit at my desk at 9am and stare at the screen.",
    "I would leave my desk at 5pm if my manager ever let me.",
]

# (whole post, a phrase the extracted moment must contain)
EXTRACTION = [
    ("todays been rough honestly. I woke up at 3:40am with my heart pounding and "
     "could not get back to sleep. anyway hope everyone else had a better one.",
     "3:40am"),
    ("ok so. long day. I stood in the kitchen at 11pm holding the fridge door open "
     "for a full minute. going to bed now, night all",
     "kitchen"),
    ("Reposting this because it matters!! Anyway I reread her message four times "
     "before I answered. Sleep well everyone",
     "reread"),
]


def run() -> int:
    failures = []

    for text, expected in MUST_REJECT:
        got = screen.banned_subject(text)
        if got != expected:
            failures.append(f"HARM  expected {expected}, got {got!r}: {text[:60]}")

    for text in MUST_KEEP:
        verdict = screen.screen(text)
        if not verdict["ok"]:
            failures.append(f"LOST  {verdict['reason']}: {text[:60]}")

    for text in MUST_DROP_SHAPE:
        verdict = screen.screen(text)
        if verdict["ok"]:
            failures.append(f"SHAPE should have dropped: {text[:60]}")

    for post, needle in EXTRACTION:
        verdict = screen.screen(post)
        if not verdict["ok"]:
            failures.append(f"EXTRACT dropped a usable post: {verdict['reason']}")
        elif needle not in verdict["text"]:
            failures.append(f"EXTRACT missed {needle!r}, got: {verdict['text'][:70]}")

    total = len(MUST_REJECT) + len(MUST_KEEP) + len(MUST_DROP_SHAPE) + len(EXTRACTION)
    if failures:
        print(f"screen: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"screen: {total}/{total} passed "
          f"({len(MUST_REJECT)} harm, {len(MUST_KEEP)} keep, "
          f"{len(MUST_DROP_SHAPE)} shape, {len(EXTRACTION)} extraction)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
