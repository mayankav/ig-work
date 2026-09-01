#!/usr/bin/env python3
"""
Plain words, and the axis that decides what the subtitle does.

Two changes are covered here, and they arrived together because they answer the
same complaint: the decks were accurate and nobody sent them on.

  READABILITY   the axis nothing measured. Seventy-eight checks asked whether a
                line had one accent or named a visible thing; not one asked
                whether it was written in words a reader has to decode. All
                seven decks published before this fail it, one to five lines
                each, and every offending word has a plain replacement.

  FORMULA       what the h2 does. Measured on the reference account: 18 of its
                42 covers run a How-to or a list shape at 65k followers, and
                none of them run it in the headline — the h1 is a flat human
                claim and the formula sits in the subtitle. Ours named a problem
                and never once said what the reader gets.

The point of the formula axis is that it holds no copy. Invariant 20 exists
because five of seven published decks were caught carrying a run of words lifted
out of the prompt, including a sentence the prompt quoted in order to forbid it.
So the model is handed a JOB and code picks which job, and CODE_NOT_COPY below is
the test that keeps it that way when somebody is tempted to add an example.

Nothing here reads state/. `recent_formulas` takes its history as an argument
for exactly that reason.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import readability  # noqa: E402
import writer  # noqa: E402

MOMENT = "I woke at 2:17am with my heart pounding and watched the clock until six."

# word -> beats, checked by saying it out loud. The last four are here because
# the heuristic got them wrong: "arrangement" and "residue" came back one too
# high, which would have refused a word on a rule the word does not break.
SYLLABLES = {
    "the": 1, "bed": 1, "true": 1, "clock": 1, "phone": 1,
    "waiting": 2, "movement": 2, "cement": 2, "argue": 2, "value": 2,
    "quiet": 2, "people": 2, "simple": 2,
    "tomorrow": 3, "remember": 3, "another": 3, "continue": 3,
    "arrangement": 3, "residue": 3,
    "impossible": 4, "execution": 4, "appeasement": 3, "hesitation": 4,
    "automatically": 6, "communication": 5, "everywhere": 3, "everybody": 4,
    "table": 2, "candle": 2, "gentle": 2, "possible": 3,
    # A past tense "-ed" is a beat only after t or d. Both halves are pinned
    # here, because a rule that only ever subtracts is as wrong as one that
    # never does: "unfinished" came back as four and there is no shorter word
    # for it, and "wanted" must stay at two.
    "unfinished": 3, "finished": 2, "walked": 1, "closed": 1, "missed": 1,
    "published": 2, "unnoticed": 3, "remembered": 3, "considered": 3,
    "overwhelmed": 3, "determined": 3, "answered": 2,
    "wanted": 2, "needed": 2, "started": 2, "decided": 3, "exhausted": 3,
    "agreed": 2, "worried": 2, "studied": 2, "tried": 1,
    # Still four, so still refused. The fix must not buy an easy pass for a
    # word that is genuinely out of reach.
    "complicated": 4, "disappointed": 4, "interrupted": 4, "automated": 4,
}

# Words pulled out of the seven published decks. Each one shipped, and each one
# is why the cap is set where it is.
SHIPPED_OFFENDERS = ("automatically", "environment", "ambiguity", "enthusiastic",
                     "invitation", "impossible", "hesitation", "evaporates",
                     "execution", "repetition", "alternative", "overthinking")

# Words a nine-year-old owns that must never be refused. Three beats each, and
# rationing them was tried and thrown out: it added twenty to thirty-two faults
# across the same seven decks and every one of them asked for the thinking to be
# simplified, which is the one thing the brand dial forbids.
#
# "everybody" is deliberately NOT here. It really is four beats, so the cap
# refuses it, and that is the cap working rather than failing: "everyone" is
# three, means the same thing, and is sitting right there. A word only belongs on
# this list if refusing it would cost the voice something.
MUST_PASS = ("tomorrow", "remember", "another", "yesterday", "everywhere",
             "family", "different", "probably", "comfortable", "everyone",
             "table", "candle", "people", "simple", "trouble",
             # Run local-1788240340 was told seven times to find a shorter word
             # than "unfinished". There is not one. These five are the -ed class
             # that the phantom beat put over the cap.
             "unfinished", "remembered", "considered", "overwhelmed", "unnoticed")


def run() -> int:
    failures: list[str] = []
    total = 0

    # ── the syllable count ──
    total += 1
    wrong = {w: (readability.syllables(w), n) for w, n in SYLLABLES.items()
             if readability.syllables(w) != n}
    if wrong:
        failures.append(f"SYLLABLES counted wrong, got vs expected: {wrong}")

    # ── what the gate refuses, and what it must not ──
    total += 1
    missed = [w for w in SHIPPED_OFFENDERS if not readability.hard_words(w)]
    if missed:
        failures.append(f"HARD these shipped and the cap let them through: {missed}")

    total += 1
    refused = [w for w in MUST_PASS if readability.hard_words(w)]
    if refused:
        failures.append(f"PLAIN ordinary words were refused, the cap is too tight: {refused}")

    # ── the reader's words are not ours ──
    #
    # A [[double bracket]] is an accent the renderer paints, so the word is still
    # the writer's. A [single bracket] is a blank the reader fills in, and
    # failing a script for a word the reader supplies would be refusing our own
    # best format.
    total += 1
    if readability.hard_words("Say it to [whoever is unavailable] tonight."):
        failures.append("BRACKET a fill-in blank was counted against the line")
    if not readability.hard_words("Say it to your [[unavailable]] friend."):
        failures.append("ACCENT an accented word escaped the count")

    # ── a tag is a label, not prose ──
    #
    # Counting hashtags found "anxiousattachment", "attachmentstyle" and
    # "burnoutrecovery" in four of the seven published decks and asked for a
    # shorter word that does not exist — the tag block is required and compound by
    # construction. Gates abort, so a fault nothing can answer is a stopped
    # engine, not a strict gate. The markdown heading must survive the strip.
    total += 1
    if readability.hard_words("Real talk tonight. #anxiousattachment #burnoutrecovery"):
        failures.append("TAG a hashtag was counted as a word the reader has to decode")
    if "Caption" not in readability.strip_markup("## Caption"):
        failures.append("TAG stripping tags ate a markdown heading")

    # ── the grade fault names words too ──
    #
    # It was the one message here that did not say WHICH word, which is the
    # guess-and-retry failure this module exists to avoid. The four-syllable words
    # are named line by line, so what is left driving the number is the
    # three-syllable ones.
    total += 1
    textbook = [(f"slide {i}", "Remembering yesterday continues another difficult morning "
                               "regardless of whatever family arrangement.") for i in range(1, 5)]
    graded = [f for f in readability.deck_faults(textbook) if "grade" in f]
    if not graded:
        failures.append("GRADE a deck of three-syllable words did not trip the cap")
    elif "'" not in graded[0]:
        failures.append(f"GRADE the grade fault named no word to change: {graded[0]}")

    # ── the deck-level number ──
    total += 1
    easy = [("slide 1 h1", "You sat on the bed and stared at the door."),
            ("slide 2 body", "It felt heavy. You did not move for an hour.")]
    if readability.deck_faults(easy):
        failures.append(f"GRADE plain copy was graded too hard: {readability.deck_faults(easy)}")
    hard = [("slide 1 h1", "Environmental ambiguity generates automatic hesitation."),
            ("slide 2 body", "Repetition of the alternative accelerates communication.")]
    faults = readability.deck_faults(hard)
    if len(faults) < 3 or not any("grade" in f for f in faults):
        failures.append(f"GRADE textbook copy passed with only {faults}")

    # ── every fault names the word ──
    #
    # A gate that says "too hard to read" gets a rewrite that is differently
    # hard. The word has to be in the message or the repair loop is guessing.
    total += 1
    message = readability.line_faults("Movement feels impossible to start.", "h2")
    if not message or "impossible" not in message[0]:
        failures.append(f"NAMED the fault did not name the offending word: {message}")

    # ── the formula axis ──
    total += 1
    if len(writer.AXES["formula"]) != 13:
        failures.append(f"expected 13 formulas, got {len(writer.AXES['formula'])}")

    # CODE_NOT_COPY. Every value is an instruction about what the subtitle DOES,
    # never a subtitle. The day one of these becomes a line of sample copy, the
    # model has a template and invariant 20 has been undone quietly.
    total += 1
    not_a_job = [k for k, v in writer.AXES["formula"].items() if "the h2 " not in v]
    if not_a_job:
        failures.append(f"CODE_NOT_COPY these formulas are not phrased as a job for the h2, "
                        f"which is how an example gets in: {not_a_job}")
    total += 1
    with_copy = [k for axis in writer.AXES.values() for k, v in axis.items()
                 if "[[" in v or '"' in v]
    if with_copy:
        failures.append(f"CODE_NOT_COPY an axis value contains quoted copy: {with_copy}")

    # ── the draw is reproducible, and adding an axis disturbs nothing ──
    total += 1
    if writer.draw_axes(MOMENT) != writer.draw_axes(MOMENT):
        failures.append("the same moment drew two different formulas")

    total += 1
    before = writer.draw_axes(MOMENT)
    original = writer.AXES
    try:
        writer.AXES = {"aaa_new_axis": {"one": "do one thing", "two": "do another"}, **original}
        after = writer.draw_axes(MOMENT)
    finally:
        writer.AXES = original
    moved = {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    if moved:
        failures.append(f"INDEPENDENT inserting an axis moved the others: {moved}. Each axis "
                        f"must hash its own name, or a seventh axis silently replans every "
                        f"moment that already exists")

    # ── no repeat inside the window ──
    total += 1
    history = [f"a moment on evening {i} with a hallway and a phone" for i in range(40)]
    sequence = writer.recent_formulas(history)
    clashes = [(j, i, sequence[i]) for i in range(len(sequence))
               for j in range(max(0, i - writer.FORMULA_WINDOW), i)
               if sequence[j] == sequence[i]]
    if clashes:
        failures.append(f"WINDOW a formula repeated inside {writer.FORMULA_WINDOW} decks: "
                        f"{clashes[:3]}")

    total += 1
    if len(set(sequence)) != 13:
        failures.append(f"WINDOW 40 decks used only {len(set(sequence))} of 13 formulas")

    # Replay is the memory, so replay has to be stable. If this drifts, two runs
    # of the same history disagree about what is still available.
    total += 1
    if writer.recent_formulas(history) != sequence:
        failures.append("REPLAY the same history reconstructed two different sequences")
    total += 1
    if writer.recent_formulas([]) != []:
        failures.append("REPLAY an empty history did not produce an empty window")

    # The window may never starve the draw: thirteen values, eight taken.
    total += 1
    nxt = writer.draw_axes("a moment nobody has written about yet", sequence)["formula"]
    if nxt in sequence[-writer.FORMULA_WINDOW:]:
        failures.append(f"WINDOW the next draw took {nxt!r}, which is still inside the window")

    # ── the subtitle has a job, and code checks the part it can ──
    #
    # This exact pair posted: the name and the same image on both lines, on the
    # only slide most people see. It scores zero new words and it is the reason
    # the check counts them instead of asking about a subset.
    total += 1
    shipped_twice = {"h1": "Execution freeze. You remain anchored to the [[bed]] even when awake.",
                     "h2": "Execution freeze. Anchored to the bed."}
    faults = writer.hook_faults(shipped_twice)
    if not any("new words" in f for f in faults):
        failures.append(f"H2 the h2 that repeated h1 was not caught: {faults}")
    if not any("execution" in f for f in faults):
        failures.append(f"H2 a four-syllable word on the cover was not caught: {faults}")

    total += 1
    working = {"h1": "You sat on the edge of the [[bed]] and stared.",
               "h2": "Old rooms reload old roles."}
    faults = writer.hook_faults(working)
    if faults:
        failures.append(f"H2 a hook that does its job was refused: {faults}")

    # Function words are not a contribution. "and why the" is three words and
    # says nothing, which is how a subset check gets satisfied without a subtitle.
    total += 1
    padded = {"h1": "You sat on the edge of the [[bed]] and stared.",
              "h2": "And why you are still there."}
    if not any("new words" in f for f in writer.hook_faults(padded)):
        failures.append("H2 a subtitle padded out with function words was accepted")

    # ── the axis text is inside the leak gate ──
    #
    # The four templates are joined raw, so for a long time the one part of the
    # prompt written to steer the wording was the one part the leak gate could
    # not see. Measured across the seven published decks when this was widened:
    # zero of them would have been refused.
    total += 1
    shown = writer.prompt_ngrams()
    uncovered = [k for k, v in writer.AXES["formula"].items()
                 if not (writer._ngrams(v, writer.LEAK_N) & shown)]
    if uncovered:
        failures.append(f"LEAK the leak gate cannot see these axis instructions, so the model "
                        f"could copy them into a slide: {uncovered}")

    total += 1
    for deck in sorted((pathlib.Path(__file__).resolve().parents[3] / "carousels")
                       .glob("*/carousel.md")):
        leaks = writer.check_leak(deck.read_text(encoding="utf-8"), shown)
        if leaks:
            failures.append(f"LEAK {deck.parent.name} is now refused by the widened gate: "
                            f"{leaks[0]}")

    # ── the handle is said out loud ──
    total += 1
    plan = {"pattern_name": "execution freeze"}
    if not readability.hard_words(plan["pattern_name"]):
        failures.append("HANDLE 'execution freeze' passed as a handle a reader repeats")
    if readability.hard_words("waiting mode") or readability.hard_words("bowl washing"):
        failures.append("HANDLE the two handles that worked were refused")

    if failures:
        print(f"readability: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"readability: {total}/{total} passed "
          f"(syllables, the cap, 13 formulas, a window of {writer.FORMULA_WINDOW}, "
          f"the h2's job, the leak gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
