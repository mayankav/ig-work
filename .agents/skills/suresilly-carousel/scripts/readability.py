#!/usr/bin/env python3
"""
readability.py - is this line written in words a reader does not have to decode.

The axis nothing measured. Seventy-eight checks asked whether a line had exactly
one accent, whether it named a thing a camera could see, whether it repeated a
word from slide 3. Not one asked whether it was written in plain words, so a
line could satisfy every gate in the engine and still read like a textbook.

WHY SYLLABLES AND NOT A READING SCORE. Flesch-Kincaid mixes two things:
sentence length and word length. This deck already caps sentence length hard —
twelve words on a hook, seven on a subtitle, two hundred and twenty characters
in a body. So the only part of a reading score still free to move is vocabulary,
and measuring it directly says which word to change. `grade_level` is here
because it is the number people recognise, and it is reported; the caps that
abort are the syllable ones, because they name the offending word.

WHAT GRADE 5 MEANS HERE. Not simple ideas. Simple words carrying a sharp idea:
grade-3 vocabulary can hold a real argument, and a four-syllable noun is almost
never the only word that would do. The brand dial says intellectual sharpness
9/10 and clinical jargon 1/10, and those two only coexist if the thinking stays
hard while the vocabulary gets easy.
"""

from __future__ import annotations

import re

# ──────────────────────────── the caps ────────────────────────────
#
# Calibrated against the seven decks this engine has published. Every one of
# them fails the four-syllable cap, between one and five lines each, and every
# single offending word has a plain replacement: automatically, environment,
# ambiguity, enthusiastic, hesitation, execution, repetition, alternative,
# overthinking, impossible. Those are the words that made a deck read like a
# textbook, so a cap that let them through would measure nothing.
#
# "appeasement" was on that list until the counts were checked: the -ment rule
# below makes it three beats and it passes. Left named here because a comment
# claiming a catch the code does not make is worse than no comment.
#
# THREE-SYLLABLE WORDS ARE MEASURED AND NOT ENFORCED. Rationing them was tried
# first and refused: it added between twenty and thirty-two faults across the
# same seven decks, and the words it objected to were "tomorrow", "remember",
# "another", "yesterday", "everywhere". Refusing those simplifies the THINKING,
# which is the one thing the brand dial says never to do. `long_words` stays
# because the count is worth reporting; it does not produce a fault.

HARD_SYLLABLES = 4      # no reader-visible word may reach this
LONG_SYLLABLES = 3      # counted and reported, never a fault
GRADE_CAP = 6.0         # Flesch-Kincaid ceiling for a whole deck's copy

VOWELS = "aeiouy"

# Words the syllable heuristic gets wrong. Kept short on purpose: every entry is
# a hole in the gate, so one goes in only to correct a count, never to excuse a
# word from the cap.
#
# It was twice this size. Seventeen entries — everyone, another, people, little,
# simple, favourite and the rest — turned out to be compensating for a
# double-counted "-le" ending rather than for anything about English, and they
# went when that was fixed. An allowlist that grows to cover a bug stops being
# readable as a list of exceptions.
#
# Two of these are worth naming. "everywhere" is three beats and came back as
# four, so correcting it lets an ordinary word through. "everybody" really is
# four and stays refused, which is the cap working: "everyone" is three, means
# the same, and is sitting right there.
KNOWN = {
    "every": 2, "everything": 3, "everywhere": 3, "everybody": 4, "evening": 2,
    "somebody": 3, "anybody": 3, "comfortable": 3, "business": 2,
    "quiet": 2, "quietly": 3, "science": 2, "being": 2, "doing": 2, "going": 2,
}

# Contractions and possessives are one word, and the apostrophe is not a vowel
# boundary. "you'd" counted as two before this, which made a five-word subtitle
# read as though it were carrying textbook vocabulary.
WORD = re.compile(r"[A-Za-z][A-Za-z']*")
SENTENCE = re.compile(r"[.!?]+")


def strip_markup(text: str) -> str:
    """Reader-visible words only: accents, bold, fill-in brackets and tags removed.

    A [[double bracket]] is an accent the renderer paints and a [single bracket]
    is a blank the reader fills in. Neither changes how hard the line is to
    read, and counting the bracket words as ours would fail a script for a word
    the reader supplies.

    A #hashtag is not prose. It is a routing label, compound by construction, and
    the caption is required to carry a block of them — so counting them found
    "anxiousattachment", "attachmentstyle", "burnoutrecovery" and
    "relationalpsychology" in four of the seven published decks and asked for a
    rewrite that does not exist. Gates abort, so a fault nothing can answer is
    not a strict gate, it is a stopped engine. Measured: with tags removed, no
    published caption loses a genuine fault.
    """
    text = re.sub(r"\[\[|\]\]", "", text)
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"#\w+", " ", text)
    return text


def syllables(word: str) -> int:
    """How many beats this word takes to say. A heuristic, and it says so.

    Vowel groups, minus the silent e, plus the one back for a consonant-le
    ending. Wrong on loan words and on some names, which is why KNOWN exists
    and why the caps have a notch of headroom rather than being exact.
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if w in KNOWN:
        return KNOWN[w]
    count = 0
    previous_was_vowel = False
    for ch in w:
        is_vowel = ch in VOWELS
        if is_vowel and not previous_was_vowel:
            count += 1
        previous_was_vowel = is_vowel
    # A trailing e is usually silent ("time", "made"), except where it is the
    # only vowel sound in the word ("the", "he"), where it carries a
    # consonant-l, or where it is the second half of a "ue" that is spoken
    # ("residue", "argue"). The "ue" exemption is here because without it a
    # three-beat word came back as two.
    #
    # The consonant-le case is an exemption from the subtraction and nothing
    # more. It briefly also ADDED a beat, which double-counted every word ending
    # that way: "table", "candle", "cycle" and "gentle" all came back one too
    # high, and "impossible" came back as five. Four entries in KNOWN existed
    # only to paper over it, which is how a heuristic quietly stops being one.
    if w.endswith("e") and not w.endswith(("le", "ee", "ye", "ue")) and count > 1:
        count -= 1
    # -ment after a silent e: "movement" is two beats, not three, and
    # "arrangement" is three, not four. Both came back one too high, which
    # would have refused a word on a rule the word does not break.
    if w.endswith("ment") and len(w) > 6 and w[-5] == "e" and w[-6] not in VOWELS:
        count -= 1
    return max(1, count)


def words_in(text: str) -> list[str]:
    return WORD.findall(strip_markup(text))


def hard_words(text: str) -> list[str]:
    """The words that put this line out of reach, longest first."""
    seen: dict[str, int] = {}
    for word in words_in(text):
        n = syllables(word)
        if n >= HARD_SYLLABLES:
            seen[word.lower()] = n
    return [w for w, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def long_words(text: str) -> list[str]:
    """Three-syllable words. Counted for the report, never a fault. See the caps."""
    return sorted({w.lower() for w in words_in(text) if syllables(w) == LONG_SYLLABLES})


def grade_level(text: str) -> float:
    """Flesch-Kincaid, for a whole deck rather than a line.

    Meaningless on a seven-word subtitle — one long word swings it four grades —
    so it is only ever asked about a whole deck's copy, where the sentence count
    is large enough to mean something.
    """
    words = words_in(text)
    if not words:
        return 0.0
    sentences = max(1, len([s for s in SENTENCE.split(strip_markup(text)) if s.strip()]))
    beats = sum(syllables(w) for w in words)
    return 0.39 * (len(words) / sentences) + 11.8 * (beats / len(words)) - 15.59


def line_faults(text: str, where: str = "this line") -> list[str]:
    """Why this line is not written in plain words. Empty means it is.

    Names the word. A gate that says "too hard to read" gets a rewrite that is
    differently hard; a gate that says "appeasement" gets the word changed.
    """
    hard = hard_words(text)
    if not hard:
        return []
    return [f"{where} uses {', '.join(repr(w) for w in hard[:3])}, which is "
            f"{HARD_SYLLABLES} syllables or more. Say it in shorter words. The idea "
            f"stays sharp, the vocabulary gets easy"]


def deck_faults(lines: list[tuple[str, str]]) -> list[str]:
    """Every readability complaint about one assembled deck.

    `lines` is what writer.copy_lines returns: only what a reader sees, so the
    citation line and the layout names — which are ours, not the model's — are
    already gone before anything is counted.
    """
    problems: list[str] = []
    for where, text in lines:
        problems += line_faults(text, where)
    joined = " ".join(text for _, text in lines)
    grade = grade_level(joined)
    if grade > GRADE_CAP:
        # Name the words, like every other fault in this module. "Shorten the
        # words, not the argument" is the one message here that did not say WHICH
        # word, which is the guess-and-retry failure the docstring warns about.
        # The four-syllable ones are already named line by line above, so the
        # ones left driving the number are the three-syllable ones — reported
        # here and nowhere else, because on their own they are never a fault.
        #
        # Measured on the seven published decks: five pass this outright and the
        # two that do not are also carrying named hard words, so the cap has
        # never been the only thing standing between a run and a deck.
        driving = [w for w in long_words(joined)][:6]
        problems.append(
            f"the deck reads at grade {grade:.1f}, cap is {GRADE_CAP}. Shorten the "
            f"words, not the argument"
            + (f". The three-syllable words carrying it: "
               f"{', '.join(repr(w) for w in driving)}" if driving else ""))
    return problems
