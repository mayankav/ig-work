#!/usr/bin/env python3
"""
coherence.py — does the deck hold together as one argument?

Nine slides that each pass their own checks can still be nine unrelated slides.
This module asks whether slide 2 follows from slide 1, whether the advice still
belongs to the mechanism named on slide 3, and whether the card at the end is a
summary of the deck rather than a new idea arriving late.

None of it needs a model. The checks are lexical: shared anchors, shared terms,
and set differences. That has a real ceiling — see the honesty note at the
bottom — but it catches the failures we have actually shipped.

The one that matters most is FOREIGN. A deck about waking at 2:17am once went
out carrying "17 tabs" and a waiting-mode cheat sheet, because the generator
stitched a fixed template onto whatever hook it drew. Nothing in the old audit
noticed, because every slide was individually well-formed.
"""

from __future__ import annotations

import re
from collections import Counter

# Concrete things a camera could point at. A deck's own anchors come from the
# moment it was built on; anything here that is NOT one of them is a detail that
# wandered in from somewhere else.
CONCRETE = re.compile(
    r"\b(\d{1,2}:\d{2}\s?[ap]m|\d{1,2}\s?[ap]m|\d{1,3}|tabs?|phones?|inboxe?s?|beds?|"
    r"kitchens?|desks?|clocks?|emails?|texts?|messages?|appointments?|laptops?|"
    r"sofas?|couch(es)?|cars?|mirrors?|fridges?|doors?|keys?|screens?|mugs?|"
    r"chests?|stomachs?|hearts?|jaws?|throats?|shoulders?|hands?|palms?)\b"
)

# A bare number is a weak anchor. "becoming 15" is a real hook, but a deck is
# not incoherent for failing to repeat the digit on every later slide, and the
# advice slides are full of counts that mean nothing about the scene.
def _wordy(anchors: set[str]) -> set[str]:
    return {a for a in anchors if not a.replace(":", "").isdigit()}

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "with", "by", "is",
    "it", "you", "your", "for", "that", "this", "was", "as", "but", "not", "be",
    "are", "from", "have", "has", "had", "i", "my", "me", "so", "if", "will",
    "can", "do", "does", "did", "what", "when", "then", "they", "them", "their",
    "there", "here", "one", "still", "just", "like", "get", "got", "out", "up",
}

# Slide 2 is served cold to people who did not swipe, so it has to work with no
# slide 1 in front of it. A pronoun with nothing to refer back to breaks that.
DANGLING = re.compile(r"^\s*(this|that|it|they|these|those|which|and|but|so)\b", re.I)

MIN_SLIDES = 8
# A named pattern, always written in [[accent]] on a slide. These are the ideas
# a deck teaches, so a new one appearing on the cheat sheet is a new idea.
LABEL = re.compile(r"\[\[([a-z][a-z \-]{2,28})\]\]")

# Accent words that carry emphasis rather than an idea. "Your 17 tab [[reset]]"
# is a title, not a new concept, and the deck should not be blocked for it.
# A time of day, not a count. "90 seconds" and "three times" are useful in a
# step; "2:50pm" is somebody else's afternoon.
CLOCK_TIME = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\s?(?:a\.?m\.?|p\.?m\.?)?\b|\b\d{1,2}\s?(?:am|pm)\b")

DECORATIVE = {
    "kit", "card", "sheet", "reset", "now", "this", "next", "you", "yours",
    "here", "stop", "one", "two", "three", "again", "yet", "good", "enough",
    "later", "tonight", "today", "start", "first", "last", "back", "out",
    # Words that name the artefact rather than an idea it carries. A card
    # headed "your [[cheat]] sheet" is not teaching anybody a concept called
    # cheat, and asking the model not to accent them never worked.
    "cheat", "script", "list", "summary", "recap", "steps", "step", "plan",
    "menu", "checklist", "notes", "note", "guide",
    # Generic nouns. A label is a pattern the deck TEACHES — "waiting mode",
    # "the countdown" — and accenting "fact" or "case" teaches nobody anything.
    # They were being counted as new ideas arriving on the card.
    "fact", "case", "reason", "reasons", "point", "answer", "way", "ways",
    "thing", "things", "part", "line", "lines", "paragraph", "low", "path",
    "body", "moment", "rule", "sequence", "order", "choice", "option",
}


def _words(text: str) -> list[str]:
    text = re.sub(r"\[\[|\]\]", " ", text.lower())
    return re.findall(r"[a-z0-9:']+", text)


def _stem(word: str) -> str:
    """Crude suffix stripping, enough to see that "wake", "waking" and "woke"
    are the same idea.

    A slide that says "when you wake" is plainly still explaining slide 3's
    "brief wakings", and an exact-match thread check calls that a broken
    argument. No stemming library: this needs to run in CI for years, and the
    handful of suffixes below cover everything the check actually depends on.
    """
    for suffix in ("ings", "ing", "edly", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    # A trailing "e" goes too, so that "wake" and "wakings" land on the same
    # stem. Without this the suffix stripping alone leaves "wake" and "wak".
    return word[:-1] if len(word) > 3 and word.endswith("e") else word


def content(text: str) -> set[str]:
    """Meaning-bearing words, stemmed, for the thread check."""
    return {_stem(w) for w in _words(text) if w not in STOP and len(w) > 2}


def _labels(text: str) -> set[str]:
    """Named patterns a deck teaches, e.g. [[waiting mode]].

    Decorative accents and anything already counted as a concrete anchor are
    dropped, so this only ever reports an actual idea.
    """
    out = set()
    for label in LABEL.findall(text.lower()):
        label = label.strip()
        if label in DECORATIVE or CONCRETE.fullmatch(label):
            continue
        out.add(label)
    return out


BODY = {"chest", "stomach", "heart", "jaw", "throat", "shoulder", "hand", "palm"}


def anchors_in(text: str) -> set[str]:
    """The concrete details a slide names, normalised so they compare sensibly.

    Plurals fold to the singular. Every body sensation folds to one token,
    because a hook that opens on a dropping stomach is properly paid off by a
    tightening chest — it is the same body, and a writer who repeats the exact
    noun on every slide is writing worse, not better.
    """
    found = set()
    for match in CONCRETE.finditer(text.lower()):
        token = match.group(0).strip()
        if token.endswith("s") and not token[-2:].isdigit():
            token = token[:-1]
        found.add("body" if token in BODY else token)
    return found


def check(slides: list[dict], text_of, moment_anchors: set[str] | None = None) -> list[str]:
    """Return every reason the deck does not hold together. Empty means it does.

    `moment_anchors` is what the deck was built from. When it is given, FOREIGN
    can name exactly which detail does not belong.
    """
    problems: list[str] = []
    if len(slides) < MIN_SLIDES:
        return [f"deck has {len(slides)} slides, expected at least {MIN_SLIDES}"]

    texts = [text_of(s) for s in slides]
    hook, cost, source = texts[0], texts[1], texts[2]
    cheat, cta = texts[7], texts[-1]
    hook_anchors = anchors_in(hook)

    # ── the moment survives the whole deck ──
    if not hook_anchors:
        problems.append("slide 1 names nothing a camera could film")
    elif _wordy(hook_anchors):
        # The cheat sheet is the slide people save, so it must be about the same
        # thing as the hook. Slide 2 and the CTA carry it too, but requiring all
        # three means repeating a noun for its own sake — a real deck can pay
        # off "stomach drops" without printing the word again.
        #
        # WHAT IT MAY NOT CARRY is the invented hour. A card saying "at 11pm,
        # in the kitchen" is a card that works for one imaginary person and
        # nobody else, and the card is the whole reason anybody saves a
        # carousel. The name ties it to this deck; the clock ties it to a
        # stranger's Tuesday. That check is below.
        wanted = _wordy(hook_anchors)
        named = ", ".join(sorted(wanted))
        if not (wanted & anchors_in(cheat)):
            problems.append(f"the cheat sheet never comes back to the moment on slide 1 ({named})")
        elsewhere = (wanted & anchors_in(cost)) or (wanted & anchors_in(cta))
        if not elsewhere:
            problems.append(
                f"neither the cost slide nor the CTA comes back to the moment on slide 1 ({named})"
            )

    # ── nothing from another deck's evening wandered in ──
    #
    # This once refused any noun the moment did not literally contain, which
    # sounds right and is not. Measured against the only decks known to be good
    # — the three hand-written ones and the fixture above — it refused all four:
    # a deck about watching the clock may not say "clock", a deck about being
    # let in may not say "door". A moment is one sentence and a deck is nine
    # slides, so the deck will always name more of the evening than the sentence
    # did. What it must not do is move to a DIFFERENT evening.
    #
    # A second clock time is that, and nothing else is. The deck that shipped
    # broken opened at 2:17am and gave advice at 2:47pm; the wrong time is what
    # a reader would notice, and it is the one detail that cannot be explained
    # by a deck simply saying more than its source. Advice that belongs to
    # somebody else's evening is caught below, by the thread check, on the
    # stronger ground that it stopped explaining what slide 3 named.
    if moment_anchors is not None:
        clocks = {a for a in {x.lower() for x in moment_anchors} if ":" in a or a.isdigit()}
        if clocks:
            for i, text in enumerate(texts, 1):
                other = {a for a in anchors_in(text) if ":" in a} - clocks
                if other:
                    problems.append(
                        f"slide {i} is set at {', '.join(sorted(other))}, "
                        f"which is not when this moment happened"
                    )

    # ── the saved card has to work for somebody else ──
    #
    # The one artefact a reader keeps. It carries the name so they remember
    # which deck it came from, and no invented clock time, because "turn the
    # light off at 11pm" is an instruction for a person who does not exist.
    # A deck that put "start the 10 minute starter at 2:50pm in the kitchen" on
    # its cheat sheet has thrown away the only slide with a second life.
    # Only the instructions. The card's title may name the moment — "your 2:17am
    # card" is what tells a reader which deck they saved — but a step that says
    # "at 2:50pm, in the kitchen" is a step for a person who does not exist.
    # Counts are fine and useful: "90 seconds", "three times". Times of day are
    # not, so this looks for an hour and not for a number.
    steps = " ".join(slides[7].get("bullets", []) + [str(slides[7].get("body", ""))])
    hours = set(CLOCK_TIME.findall(steps))
    if hours:
        problems.append(
            f"a step on the cheat sheet happens at {', '.join(sorted(hours))}. This is the "
            f"slide people save, and a step tied to one invented hour is a step nobody else "
            f"can follow. Name the moment in the title, never inside the instruction")

    # ── the advice still belongs to the mechanism ──
    source_terms = content(source)
    if not source_terms:
        problems.append("slide 3 explains nothing")
    else:
        for i in range(3, min(7, len(texts))):
            if not (content(texts[i]) & source_terms):
                problems.append(f"slide {i + 1} does not connect back to the explanation on slide 3")

    # ── the card is a recap, not a new idea ──
    # A good cheat sheet rewords heavily — that is what compressing four slides
    # onto one card looks like, and our own decks land at 56% new vocabulary.
    # So this counts new IDEAS, not new words: a concrete detail or a named
    # label that appears nowhere in the advice it claims to summarise.
    earlier_anchors, earlier_labels = set(), set()
    for i in range(0, 7):
        if i < len(texts):
            earlier_anchors |= anchors_in(texts[i])
            earlier_labels |= _labels(texts[i])
    # Slides 1 and 2 establish the scene, so a detail from either is not a new
    # idea when it reappears on the card people save.
    scene_anchors = anchors_in(hook) | anchors_in(cost)
    if moment_anchors:
        # A detail from the deck's own moment is part of the scene, even when
        # only the card happens to name it.
        scene_anchors |= {a.lower() for a in moment_anchors}
    cheat_anchors = anchors_in(cheat) - scene_anchors
    cheat_labels = _labels(cheat)

    # A label is only new if the deck has not said it before IN ANY FORM. The
    # [[brackets]] are a typographic accent, so the same idea is routinely
    # plain on slide 5 and accented on the card, and comparing accent to accent
    # called that a new idea. Compare against the words instead.
    earlier_words = set()
    for i in range(0, 7):
        if i < len(texts):
            earlier_words |= {w.lower() for w in _words(texts[i])}
    stray_anchors = {a for a in cheat_anchors - earlier_anchors if not a.replace(":", "").isdigit()}
    stray_labels = {label for label in cheat_labels - earlier_labels
                    if not {w.lower() for w in _words(label)} <= earlier_words}
    if stray_anchors or stray_labels:
        introduced = ", ".join(sorted(stray_anchors | stray_labels))
        problems.append(
            f"the cheat sheet introduces {introduced}, which slides 4 to 7 never mention"
        )

    # ── slide 2 has to work as a cover on its own ──
    first_sentence = re.split(r"(?<=[.!?])\s", cost.strip())[0] if cost.strip() else ""
    if DANGLING.match(first_sentence):
        problems.append("slide 2 opens with a word that refers back to slide 1, so it cannot stand alone")
    if len(_words(cost)) < 6:
        problems.append("slide 2 is too thin to work as a second cover")
    if not anchors_in(cost):
        problems.append("slide 2 names nothing concrete, so it reads as a caption rather than a cover")

    # ── the CTA closes the loop ──
    if not re.search(r"\b(send|share|forward|dm)\b", cta.lower()):
        problems.append("the CTA does not ask anyone to pass it on")

    return problems
