#!/usr/bin/env python3
"""
Abstraction-firewall regression.

The rewrite step is what lets this pipeline read a public feed and publish for a
brand: the observable fact is free to use, the author's sentence is not. So the
tests here are about the checks, not the model. No network is touched.

The verbatim check is the one that carries the weight. A model asked whether it
paraphrased enough will say yes; counting shared words does not have an opinion.
Everything else in this file exists because a plausible-looking rewrite can still
be unusable: it can invent a room the person never mentioned, keep a handle, or
quietly turn into something we may never publish.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import abstracter as abstract  # noqa: E402

ORIGINAL = ("todays been rough honestly. I woke up at 3:40am with my heart pounding "
            "and could not get back to sleep. hope everyone else had a better one @friend")

# (rewrite, the phrase we expect the complaint to contain)
MUST_REJECT = [
    # Word-for-word, which is the whole reason this check exists.
    ("I woke up at 3:40am with my heart pounding and could not get back to sleep.",
     "words in a row"),
    # Reworded at the edges, identical in the middle.
    ("At 3:40am I woke up with my heart pounding and could not get back to sleep again.",
     "words in a row"),
    ("At 3:40 I opened my eyes, chest thumping, and stayed awake. @friend",
     "handle"),
    # A room the original never mentioned. An invented detail becomes fact for
    # every slide after it.
    ("At 3:40 I woke in the kitchen, chest thumping, and stayed awake until six.",
     "invented a place"),
    # A clock time that was not in the original.
    ("At 5:15 I opened my eyes, chest thumping, and stayed awake until morning.",
     "invented a clock"),
    # Drifted into something we may never publish.
    ("At 3:40 I opened my eyes and thought about killing myself until six.",
     "reads as crisis"),
    # Lost the moment entirely.
    ("I had a difficult night and felt a lot of anxiety about everything.",
     ""),
]

MUST_ACCEPT = [
    "At 3:40 I opened my eyes, chest thumping, and stayed awake until six.",
    "My eyes opened at 3:40. I lay there with a loud chest and never dropped off.",
]


def run() -> int:
    failures = []

    # The measure itself, before anything depends on it.
    if abstract.shared_run("one two three four", "one two three four") != 4:
        failures.append("RUN identical text did not report its full length")
    if abstract.shared_run("one two three", "four five six") != 0:
        failures.append("RUN unrelated text reported a shared run")
    if abstract.shared_run("the cat sat on the mat", "a cat sat on a bench") != 3:
        failures.append("RUN a partial overlap was measured wrongly")

    for rewrite, expected in MUST_REJECT:
        problems = abstract.verify(ORIGINAL, rewrite)
        if not problems:
            failures.append(f"ACCEPTED a rewrite that should have been refused: {rewrite[:60]}")
        elif expected and not any(expected in p for p in problems):
            failures.append(f"WRONG REASON for {rewrite[:44]!r}: got {problems}")

    for rewrite in MUST_ACCEPT:
        problems = abstract.verify(ORIGINAL, rewrite)
        if problems:
            failures.append(f"REFUSED a good rewrite: {problems} | {rewrite[:60]}")

    total = 3 + len(MUST_REJECT) + len(MUST_ACCEPT)
    if failures:
        print(f"abstract: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"abstract: {total}/{total} passed "
          f"(verbatim reuse, handles, invented place and clock, drift, lost moment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
