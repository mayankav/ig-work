#!/usr/bin/env python3
"""
Composer regression. No network is touched.

The harvested post is a SEED. We read it to learn what kind of evening somebody
had, then invent our own. Nothing of theirs is republished because nothing of
theirs is used, and the check that guarantees it is the word count: no run of
seven words may survive. A model asked whether it was original enough will say
yes. Counting words has no opinion.

Reading their names is fine. The post is public and we are only looking at it.
The rule is about what we WRITE, so the moment we publish carries no name at
all, whether copied or invented. That is one rule instead of two, and it is
stronger than either.

This file replaces the abstraction-firewall tests. Two of those cases have been
deleted rather than rewritten: inventing a clock and inventing a room used to be
faults, because the moment was supposed to stay faithful to a real evening. It
is now supposed to be a different evening, so those are the job.
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import compose  # noqa: E402

SEED = ("todays been rough honestly. I woke up at 3:40am with my heart pounding "
        "and could not get back to sleep. hope everyone else had a better one @friend")

# (moment, the phrase we expect the complaint to contain)
MUST_REJECT = [
    # Copied word for word, which is the whole reason this check exists.
    ("I woke up at 3:40am with my heart pounding and could not get back to sleep.",
     "words in a row"),
    # Reworded at the edges, identical in the middle.
    ("At 3:40am I woke up with my heart pounding and could not get back to sleep again.",
     "words in a row"),
    ("At 2:40 I opened my eyes, chest thumping, and stayed awake. @friend",
     "handle"),
    # Drifted into something we may never publish.
    ("At 2:40 I opened my eyes and thought about killing myself until six.",
     "reads as crisis"),
    # Nothing felt in it, so the judge would refuse it and be right.
    ("At 2:40 I opened my eyes and stayed awake until six, then got up for work.",
     "nothing about how it felt"),
    # A label is not a feeling, and this brand never uses one.
    ("At 2:40 I woke burnt out, stayed awake until six, then got up for work.",
     "nothing about how it felt"),
    # Too vague to build nine slides on.
    ("I had a difficult night and felt a lot of anxiety about everything.", ""),
]

MUST_ACCEPT = [
    # A different hour and a different room from the seed. That is the job.
    "At 1:20am I gave up, sat on the kitchen floor, and felt too tired to cry.",
    "I lay in bed until 4am with a thumping chest, dreading the alarm at seven.",
]

# A clock and a feeling, but nothing in the room. It clears the shape filter on
# its hour alone, and then nine slides have nothing to be about — the writer
# fills the vacuum with therapy jargon and the critic refuses it, two expensive
# calls later. A composed moment can be asked for a thing in shot, so it is.
MUST_REJECT_EMPTY = [
    "At 11pm I answered my manager because I felt guilty about it all evening.",
]

# One rule, about the output. It does not matter whether a name was copied from
# the seed or invented: an invented moment needs no name at all.
NAMED_SEED = ("god im tired. Sarah rang me at 11pm from Canberra and I sat in the car "
              "outside the Aldi car park until midnight")

MUST_REJECT_NAMED = [
    "I answered Sarah at 11pm, too tired to drive off, and sat there until midnight.",
    "A call came at 11pm from Canberra and I sat tired in the car until midnight.",
    "I sat in the car until midnight, too tired to answer Priya at 11pm.",
]
MUST_ACCEPT_NAMED = [
    "A call came at 11pm and I sat tired in the car outside a shop until midnight.",
    "My sister rang at 11pm and I sat too tired to answer, in the car, until midnight.",
]

# When the seed's problem is between two people, ours has to be as well. Told to
# name nobody, a model reaches past the name and deletes the person: "she was
# locked out, I let her in" comes back as "someone was locked out, I let them
# in", and the judge then refuses it for having no relational content, which is
# the correct reading of what is left.
PEOPLED_SEED = ("so tired. she messaged at 11pm saying she was locked out again "
                "so I let her in and went to bed")

MUST_REJECT_PERSON = [
    "Tired at 11pm, I let someone in at the front door, then went back to bed and slept.",
]
MUST_ACCEPT_PERSON = [
    "Tired at 11pm, I let her in at the front door, then went back to bed and slept.",
    "Tired at 11pm, my sister was shut out again, I let her in and went back to bed.",
]


def run() -> int:
    failures = []

    # The measure itself, before anything depends on it.
    if compose.shared_run("one two three four", "one two three four") != 4:
        failures.append("RUN identical text did not report its full length")
    if compose.shared_run("one two three", "four five six") != 0:
        failures.append("RUN unrelated text reported a shared run")
    if compose.shared_run("the cat sat on the mat", "a cat sat on a bench") != 3:
        failures.append("RUN a partial overlap was measured wrongly")

    for moment, expected in MUST_REJECT:
        problems = compose.verify(SEED, moment)
        if not problems:
            failures.append(f"ACCEPTED a moment that should have been refused: {moment[:58]}")
        elif expected and not any(expected in p for p in problems):
            failures.append(f"WRONG REASON for {moment[:44]!r}: got {problems}")

    for moment in MUST_ACCEPT:
        problems = compose.verify(SEED, moment)
        if problems:
            failures.append(f"REFUSED a good moment: {problems} | {moment[:58]}")

    for moment in MUST_REJECT_EMPTY:
        if not any("nothing in the room" in p for p in compose.verify(SEED, moment)):
            failures.append(f"EMPTY a moment with nothing in shot was accepted: {moment[:56]}")

    for moment in MUST_REJECT_NAMED:
        if not any("names somebody" in p for p in compose.verify(NAMED_SEED, moment)):
            failures.append(f"NAMES a moment naming a person was accepted: {moment[:58]}")
    for moment in MUST_ACCEPT_NAMED:
        problems = compose.verify(NAMED_SEED, moment)
        if problems:
            failures.append(f"NAMES refused a moment that named nobody: {problems}")

    for moment in MUST_REJECT_PERSON:
        if not any("about nobody" in p for p in compose.verify(PEOPLED_SEED, moment)):
            failures.append(f"PERSON a moment about nobody was accepted: {moment[:58]}")
    for moment in MUST_ACCEPT_PERSON:
        problems = compose.verify(PEOPLED_SEED, moment)
        if problems:
            failures.append(f"PERSON refused a moment that kept the person: {problems}")

    # A moment spent alone must never be asked to produce a companion.
    if compose.verify(SEED, "At 2:40am my eyes opened, chest thumping, and I stayed awake until six."):
        failures.append("PERSON asked for another person in a moment spent alone")

    # A weekday is not a name, and neither is the first word of a sentence.
    if compose.proper_nouns("I woke on Tuesday. Nothing helped in March.") != set():
        failures.append("NAMES a weekday, a month or a sentence opener read as a name")
    if compose.proper_nouns("I sat with Deepa in Leeds") != {"Deepa", "Leeds"}:
        failures.append("NAMES missed a person or a town")
    # A known limit, written down rather than left to be discovered. A name that
    # opens a sentence cannot be told from an ordinary capitalised opener
    # without a dictionary, so this does not try. The safety judge's
    # B5_IDENTIFIABLE stands behind it. If this ever fails, somebody has made
    # the check cleverer and this note is stale.
    if compose.proper_nouns("Sarah rang me") != set():
        failures.append("NAMES the sentence-opener limit has changed, update the note")

    # ── Not the same moment, and not the same sentence, twice ──
    #
    # Two failures, two detectors, and each is blind to the other's case. The
    # numbers here are the measured ones from this repo's own four real moments.
    BED = ("I sat on the edge of the bed at 11:45pm and stared at the dark hallway, "
           "too tired to stand up and get ready for the morning.")
    NEAR_COPY = ("I sat on the edge of the bed at 11:45pm and stared at the dark hallway, "
                 "dreading the morning that was coming.")
    SAME_SHAPE = ("I sat in the car at 9:15pm with the engine off, too cold to stay "
                  "and too tired to go inside.")
    DIFFERENT = ("My phone buzzed during dinner and I answered my manager "
                 "before the plate was down.")

    real = compose.memory.used_texts
    try:
        compose.memory.used_texts = lambda limit=None: [BED]

        # Same words. This is the pair that actually shipped twice.
        if not any("word for word" in p for p in compose.repetition_faults(NEAR_COPY)):
            failures.append("REPEAT a near-copy of a published moment was accepted")

        # Different words, same sentence. Word overlap scores this at 0.000 to
        # 0.050 and cannot see it; the shape signature is what catches it.
        if not any("same sentence shape" in p for p in compose.repetition_faults(SAME_SHAPE)):
            failures.append("REPEAT the fourth copy of one template was accepted")

        # And the gate must not swallow everything. A genuinely different
        # moment has to survive both checks.
        if compose.repetition_faults(DIFFERENT):
            failures.append(f"REPEAT a new moment was refused: {compose.repetition_faults(DIFFERENT)}")

        # The push, not just the refusal. It must name the posture to avoid and
        # must never quote the moment it learned that from — invariant 10.
        brief = compose.variety_brief([BED], 3)
        if "sat" not in brief:
            failures.append("VARIETY the brief did not ban the verb just used")
        if "bed" in brief or "11:45pm" in brief:
            failures.append("VARIETY the brief leaked a past moment into the prompt")
    finally:
        compose.memory.used_texts = real

    # The example in SYSTEM taught the template it was meant to prevent: three
    # of the first four moments copied "too ___ to ___ and too ___ to ___"
    # straight out of it.
    if "too awake to stay there" in compose.SYSTEM:
        failures.append("SYSTEM the worked example still demonstrates the banned construction")

    total = (12 + len(MUST_REJECT_EMPTY) + len(MUST_REJECT) + len(MUST_ACCEPT) + len(MUST_REJECT_NAMED)
             + len(MUST_ACCEPT_NAMED) + len(MUST_REJECT_PERSON) + len(MUST_ACCEPT_PERSON))
    if failures:
        print(f"compose: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"compose: {total}/{total} passed (copied words, handles, drift, lost feeling, "
          f"names whatever their origin, the other person kept, alone left alone)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
