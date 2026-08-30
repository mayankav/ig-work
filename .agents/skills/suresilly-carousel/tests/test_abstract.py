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
    # Kept every fact and threw away the feeling. This shipped for three runs:
    # the prompt said to strip feeling words, then the judge blocked the result
    # for having no feeling in it, and the shape score fell two points short.
    ("At 3:40 I opened my eyes and stayed awake until six, then got up for work.",
     "dropped how it felt"),
    # A label is not a feeling. "Burnt out" is the thing this brand never says.
    ("At 3:40 I woke burnt out, stayed awake until six, then got up for work.",
     "dropped how it felt"),
]

# Names are checked against the original that carried them, so these need their
# own source text. The model is told to drop towns and employers; until this
# check existed, nothing confirmed that it had, and one model call stood between
# a stranger's home town and a published slide.
NAMED = ("god im tired. Sarah rang me at 11pm from Canberra and I sat in the car "
         "outside the Aldi car park until midnight")

MUST_REJECT_NAMED = [
    # Flagged as invented rather than kept, because "Sarah" opens a sentence in
    # the source and so is invisible there. Either complaint blocks the rewrite.
    ("I answered Sarah at 11pm and stayed in the car, too tired to drive off.", "a name"),
    # Lowercased, because a model hiding a name will not capitalise it.
    ("A call came at 11pm from canberra and I sat tired in the car until midnight.",
     "kept a name"),
    ("I sat in the car until midnight, too tired to answer Priya at 11pm.",
     "invented a name"),
]

MUST_ACCEPT_NAMED = [
    "A call came at 11pm and I sat tired in the car outside a shop until midnight.",
]

# The other person is the moment. Told to remove anything identifying, a model
# reaches past the name and deletes the person too: "she was locked out, I let
# her in" comes back as "someone was locked out, I let them in". The judge then
# refuses it for having no relational content, which is the correct reading of
# what is left. A pronoun identifies nobody; only a name does.
WITH_PERSON = ("so tired. she messaged at 11pm saying she was locked out again "
               "so I let her in and went to bed")

MUST_REJECT_PERSON = [
    "Tired at 11pm, I read a note about someone shut out again, let them inside, then slept.",
]
MUST_ACCEPT_PERSON = [
    "Tired at 11pm, I read a note about her being shut out again, let her inside, then slept.",
    "Tired at 11pm, I read a note about my sister being shut out again, let her inside, then slept.",
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

    for rewrite, expected in MUST_REJECT_NAMED:
        problems = abstract.verify(NAMED, rewrite)
        if not problems:
            failures.append(f"ACCEPTED a rewrite carrying a name: {rewrite[:60]}")
        elif not any(expected in p for p in problems):
            failures.append(f"WRONG REASON for {rewrite[:44]!r}: got {problems}")

    for rewrite in MUST_ACCEPT_NAMED:
        problems = abstract.verify(NAMED, rewrite)
        if problems:
            failures.append(f"REFUSED a good rewrite: {problems} | {rewrite[:60]}")

    for rewrite in MUST_REJECT_PERSON:
        if not any("wrote the other person out" in p
                   for p in abstract.verify(WITH_PERSON, rewrite)):
            failures.append(f"PERSON an anonymised rewrite was accepted: {rewrite[:56]}")
    for rewrite in MUST_ACCEPT_PERSON:
        problems = abstract.verify(WITH_PERSON, rewrite)
        if problems:
            failures.append(f"PERSON refused a rewrite that kept the person: {problems}")

    # A moment with nobody else in it must never be asked for a person.
    alone = "I woke at 2:17am with my heart pounding and watched the clock until six."
    if abstract.verify(alone, "At 2:17am my eyes opened, chest thumping, and I stayed awake until six."):
        failures.append("PERSON asked for another person in a moment spent alone")

    # A weekday is not somebody's name, and neither is the first word of a
    # sentence. Both would otherwise be refused on every run.
    if abstract.proper_nouns("I woke on Tuesday. Nothing helped in March.") != set():
        failures.append("NAMES a weekday, a month or a sentence opener read as a name")
    if abstract.proper_nouns("I sat with Deepa in Leeds") != {"Deepa", "Leeds"}:
        failures.append("NAMES missed a person or a town")

    # A known limit, written down rather than left to be discovered. A name that
    # opens a sentence cannot be told apart from an ordinary capitalised opener
    # without a dictionary, so this check does not try. Towns and employers
    # almost always arrive mid-sentence ("in Canberra", "at Aldi") and those are
    # caught; a bare "Sarah rang me" is not, and the safety judge's
    # B5_IDENTIFIABLE is what stands behind it. If this assertion ever fails,
    # somebody has made the check cleverer and this note is stale.
    if abstract.proper_nouns("Sarah rang me") != set():
        failures.append("NAMES the sentence-opener limit has changed, update the note")

    total = 7 + len(MUST_REJECT_PERSON) + len(MUST_ACCEPT_PERSON) + len(MUST_REJECT) + len(MUST_ACCEPT) + len(MUST_REJECT_NAMED) + len(MUST_ACCEPT_NAMED)
    if failures:
        print(f"abstract: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"abstract: {total}/{total} passed "
          f"(verbatim reuse, handles, invented place and clock, drift, lost moment, "
          "lost feeling, names kept and invented, the other person kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
