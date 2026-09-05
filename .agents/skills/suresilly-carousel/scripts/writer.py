#!/usr/bin/env python3
"""
writer.py — layer 5. Turn one moment into nine slides that argue one thing.

Written in two calls, not one, and the order matters more than it looks.

  Call A returns a PLAN: one line per slide, what each slide hands to the next,
         and which earlier slide it needs. Code checks that chain as data,
         before a single sentence of copy exists.
  Call B expands the approved plan into slides.

A single call optimises each slide on its own, so slide 8 re-explains slide 3
and the argument gets discovered backwards. Planning first also means a repair
is safe: a slide that fails a gate is rewritten against the same plan, so fixing
one slide cannot quietly break the story.

Two things the model is not allowed to do.

It does not choose the angle. A planner draws that here, from a fixed set of
34,944 combinations, because a model left to pick its own approach converges on
the same few ideas no matter how the temperature is set. The angle arrives as
instructions about what to write, never as a request to be original.

It does not name a source. It returns a citation id and a claim index, and code
substitutes the verified strings. There is no field in which it can type an
author, a title or a year, so a fabricated study is not unlikely, it is
impossible.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bibliography  # noqa: E402
import coherence  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import outcomes  # noqa: E402
from outcomes import Refused  # noqa: E402
import readability  # noqa: E402
import safety  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CITATIONS_PATH = SKILL_DIR / "references" / "citations.json"
HASHTAGS_PATH = SKILL_DIR / "references" / "hashtags.json"

# ─────────────────────────── the angles ────────────────────────────
#
# Six axes that change what the deck SAYS, not how it is decorated. Combined
# they give 34,944 starting positions, and the planner draws one per run from the
# moment's own fingerprint so the same moment could never be written twice the
# same way. Each value is phrased as an instruction, because a constraint the
# model is told to satisfy changes the writing and a label it is merely shown
# does not.
#
# NOT ONE OF THEM SHOWS A LINE OF COPY. That is the whole reason this is an axis
# and not a library of examples. Invariant 20 was written after five of seven
# published decks were caught carrying a run of words lifted straight out of the
# prompt, including a sentence the prompt quoted in order to forbid it. An
# example is a template; a job is not. So the model is handed a job and code
# picks which job, and there is nothing here for it to converge on.

AXES = {
    "angle": {
        "curiosity-gap": "open on the behaviour and withhold the reason until slide 3",
        "mistake": "open on what the reader is doing that quietly costs them",
        "specificity": "open on one exact detail, the time or the count, and nothing else",
        "story": "open mid-scene, as though the reader walked in on it",
        "contrarian": "open by refusing the obvious explanation",
        "promise": "open on what changes tonight if they read to the end",
        "collective": "open on how many people are doing this at the same hour",
    },
    # The sixth axis, and the one that changes the cover.
    #
    # Measured on the reference account: 18 of its 42 covers, 43%, run a How-to
    # or a list shape, at 65k followers on 75 posts. None of them run it in the
    # headline. The h1 is a flat human claim and THE FORMULA SITS IN THE H2,
    # doing the benefit job. Our covers named a problem and never once said what
    # the reader gets, and that was the gap — not a missing hook library.
    #
    # Every value here is a job for the H2, which is what keeps this axis
    # orthogonal to `angle`: angle owns how slide 1 opens, formula owns what the
    # second line does about it. Each job either absolves or promises, and
    # nothing else is on offer.
    #
    # WHAT IS DELIBERATELY ABSENT, each for a reason and not for taste. No
    # quantified timeline, because "fixed in thirty days" is a health-outcome
    # claim and invariant 12 exists so this account never prints one. No
    # invented social proof, because two files under research/ already hold
    # invented numbers and AGENTS.md has to warn about them. No manufactured
    # deadline, because there are zero instances of one across those 42 covers
    # and the growth engine here is a DM-share, which a pressured reader does
    # not send to their sister. And no "one weird trick", which reads as 2013.
    "formula": {
        "exact-words": "the h2 promises the exact wording, and slide 8 has to print wording that matches",
        "without-the-cost": "the h2 promises the result and names the effort they do not have to spend on it",
        "smallest-version": "the h2 promises the smallest usable version, the one that fits in a spare minute",
        "one-of-these": "the h2 promises that one of the moves further in is the one that will sting, without saying which",
        "craft-name": "the h2 promises a small skill the reader can use in this situation",
        "who-this-is": "the h2 names who this is for by something they do, never by something they are",
        "what-it-costs": "the h2 names what it costs to carry on not knowing this, with no deadline attached",
        "refuse-their-reason": "the h2 refuses the explanation the reader has already been handed about themselves",
        "give-the-reason": "the h2 gives the reason the behaviour made sense, so it stops reading as a flaw",
        "who-else": "the h2 says who else does this, as a kind of person the reader can picture, never as a count",
        "what-stops": "the h2 promises what stops happening, not what starts",
        "the-part-left-out": "the h2 promises the piece missing from the advice they were already given, without claiming nobody said it",
        "how-it-breaks": "the h2 promises the ways this goes wrong, so the reader can check themselves against them",
    },
    "lens": {
        "body-first": "explain through what the body did before the thought arrived",
        "clock-first": "explain through the timing, why this hour and not another",
        "other-person": "explain through what the other person saw from outside",
        "cost-accounting": "explain by counting what it costs in units the reader can measure",
        "origin-story": "explain by where the habit was learned and what it earned back then",
        "equipment-and-place": "explain through the room and the objects that cue the behaviour",
    },
    "protocol": {
        "script-first": "lead the advice with words to say out loud",
        "if-then-first": "lead the advice with one trigger and one response",
        "habit-stack-first": "lead the advice by attaching the new move to something already done daily",
        "menu-first": "lead the advice with three small options, reader picks one",
    },
    "cheat_shape": {
        "script-card": "the saved card is three lines of copy-paste wording",
        "decision-tree": "the saved card is a short if this then that path",
        "two-column": "the saved card is what you say now against what you say instead",
        "timed-sequence": "the saved card is a sequence pinned to clock times",
    },
    "rehook": {
        "open-question": "end the middle slides on a question the next slide answers",
        "partial-reveal": "end the middle slides by naming what is coming without explaining it",
        "countdown": "end the middle slides by counting down what is left",
        "name-the-next": "end the middle slides by naming the next move plainly",
    },
}

ROLES = ("hook", "cost", "source", "name", "script", "action", "sustain", "cheat", "cta")

# What a deck built on a proved concept is told about it.
#
# The term does NOT become the pattern name, and it must not reach slide 1.
# Slide 1 is a filmable scene in plain words, not a required label, and the
# brand rule is that clinical vocabulary is translated, never printed raw. The
# playbook says the same thing in its own words: recognition first, no diagnosis
# before slide 3.
#
# So the reader recognises themselves first and learns the word afterwards,
# which is also the order that makes the word stick. Slide 4 already exists to
# explain what the finding means; a proved field term may be explained there.
TERM_BRIEF = """
THE FIELD'S NAME FOR THIS, which is why this deck exists.

  {term}

Slide 4 MUST print that word and say it is what this is called. One sentence, in
your own words, after the pattern has been explained. "This has a name:
{term}." is enough.

It must NOT appear on slide 1 or slide 2. Those are a scene in plain words, and
a reader who meets a term before they have recognised themselves stops reading.
Use the real scene on slide 1, not an invented label. No second name is
required. Do not claim that the field's term diagnoses the reader."""


# How many decks a formula stays taken for once it is used. Eight, matching
# SHAPE_WINDOW in compose.py, because the two are the same kind of memory and a
# reader scrolling a profile sees them in the same grid. Thirteen values minus
# eight leaves five free at the worst moment, so the window can never starve the
# draw.
FORMULA_WINDOW = 8


def draw_axes(seed: str, recent: list[str] | None = None) -> dict:
    """Pick one value per axis, deterministically from the moment.

    Deterministic on purpose: the same moment always plans the same way, so a
    rerun reproduces a deck exactly and a reported problem can be looked at
    rather than guessed at. Different moments land in different corners because
    the hash spreads them, not because anything is random.

    Each axis gets its own hash of its own name, rather than byte i of one
    digest. Byte-by-position meant adding an axis silently moved every axis
    after it in the dict, so a sixth axis would have changed what the other five
    drew for every moment that already existed. Now a new axis disturbs nothing.

    `recent` is the formulas the last few decks were built on, oldest first.
    Given one, the hash pick is walked forward in sorted order until it lands on
    a formula outside the window — deterministic, so a rerun with the same
    history still reproduces the deck. Only the formula axis gets this. The
    other five are old enough to have their variety measured elsewhere, and this
    is the axis that decides what the cover's second line does, so repeating it
    is what would make two decks sound alike.
    """
    chosen = {}
    for axis, options in AXES.items():
        keys = sorted(options)
        digest = hashlib.sha256(f"{axis}\x00{seed}".encode()).digest()
        chosen[axis] = keys[digest[0] % len(keys)]
    if recent:
        taken = set(recent[-FORMULA_WINDOW:])
        keys = sorted(AXES["formula"])
        start = keys.index(chosen["formula"])
        for step in range(len(keys)):
            candidate = keys[(start + step) % len(keys)]
            if candidate not in taken:
                chosen["formula"] = candidate
                break
    return chosen


def recent_formulas(history: list[str] | None = None) -> list[str]:
    """Which formula each past deck was built on, oldest last.

    Replayed rather than recorded. `state/used.jsonl` stores the moment text and
    not the axes, and invariant 16 says state is one thing in one place — so the
    choice is between adding a field to a ledger that already exists for another
    purpose, or deriving it from the ledger every run. Deriving it costs one
    hash per past deck and cannot fall out of step with `draw_axes`, because it
    IS `draw_axes`.

    Chained on purpose: each step is replayed with the list as it stood at that
    point, which is the only way the reconstruction matches the sequence that
    actually ran.

    Honest about what this is. Decks written before the formula axis existed did
    not use one, so their entry here is not a record of anything. It is a
    deterministic function of the history, which is all the window needs to
    spread the next thirteen.

    `history` is injectable because a test may not read `state/`.
    """
    if history is None:
        history = memory.used_texts()
    seen: list[str] = []
    for text in history:
        seen.append(draw_axes(text, seen)["formula"])
    return seen


def combinations() -> int:
    total = 1
    for options in AXES.values():
        total *= len(options)
    return total


# ─────────────────────────── citations ────────────────────────────

def load_citations() -> dict:
    data = json.loads(CITATIONS_PATH.read_text(encoding="utf-8"))
    for citation in data["citations"]:
        bibliography.validate_citation(citation)
    return {c["id"]: c for c in data["citations"]}


def citations_for(topic: str, avoid: list[str] | None = None) -> list[dict]:
    """The sources that fit this subject. The model only ever sees this list.

    Recently used books drop out. Books were the one rotating thing here with no
    memory — poses have one, palettes have one — and with four books fitting
    people-pleasing and nothing recording what yesterday used, the same author
    took three of the first seven decks.

    Dropping out never empties the shelf: if avoiding everything recent would
    leave nothing, the full set comes back. A repeat is a worse deck; no
    citation at all is no deck.
    """
    skip = set(avoid or ())
    everything = list(load_citations().values())
    pool = [c for c in everything if topic in c["pillars"] and bibliography.supported_indices(c)]
    return [c for c in pool if c["id"] not in skip] or pool


# ─────────────────────────── the plan ────────────────────────────

PLAN_SYSTEM = """You plan a nine-slide Instagram carousel for a page about ordinary
relational psychology. You are planning only. Do not write slide copy yet.

EVERY EXAMPLE BELOW IS ABOUT PARKING TICKETS, DENTISTS, LIBRARY BOOKS AND
BICYCLES. That is deliberate and it is not this page's subject. The examples
show you a SHAPE. Not one of their words, objects, rooms or hours may appear in
what you return, and this is checked by counting shared runs of words. Measured
on this engine's own output: every example set on the page's own ground was
copied into a deck within a week, and no off-subject example ever was.

The page sounds like a smart friend who reads the textbooks. Never a therapist,
never a guru, never a brand. Dry, warm, specific. A reader should want to send it
to one person rather than agree with it in public.

START WITH A REAL SCENE. Show a familiar action or tension involving another
person. Build useful words and a small action first; write the cover last.
The reader should recognise the moment and have something useful to send.
Do not claim that a label, emotion or format guarantees shares.

PATTERN NAMES ARE OPTIONAL. Set pattern_name to an empty string unless a short
plain label helps explain the scene. It is not the cover and not a diagnosis.
An invented label is our shorthand, never a medical fact or a term the source
proved. If used, explain it on slide 4 as shorthand, not on slides 1 or 2.

THE NINE BEATS, in order, each one earning the next:
  1 hook     a familiar action or tension in the moment, not a pattern name.
  2 cost     what it costs. This is served on its own to people who did not
             swipe, so it must work with no slide 1 in front of it.
  3 source   the citation, then ONE sentence connecting it to the moment.
             The citation line is written for you and you do not touch it.

             Say what the supported finding means for this situation. Do not
             attach an invented label to the researcher or add a new claim.
             Copying the claim under a second heading is the fastest way to
             look broken, and it is checked.
  4 name     explain the meaning for the reader. The field is called name for
             storage only; no label is required. If pattern_name is present,
             explain that one shorthand here. Never coin a second label.
  5 script   a condition, then the words. Two fields, two different jobs:

               When: The library book has been by the front door nine days.
               Say:  "The book goes in the [bag] before I sit down."

             WHEN is something the reader can check against themselves right
             now — am I doing that? It is not speech and it takes no quotation
             marks. Second person is right here: it is about them.

             SAY is a line they say out loud, in their own voice, with a
             [bracket] to fill in. Never narrate them in it, and never ask
             them a question. A question in SAY is the page coaching rather
             than a person speaking, and it is checked.

             These printed under WHAT YOU SAY and TRY THIS INSTEAD until a
             deck went out with a stage direction about the reader, in
             quotation marks, under a label claiming they had said it. The
             playbook had already called that out: it puts words in their
             mouth and loses everybody who does not say that exact sentence.

  6 action   one move, with a time and a place named
  7 sustain  what makes it survive tomorrow
  8 cheat    the card they save. It recaps slides 4 to 7 and adds nothing new.
  9 cta      ask them to send it to one specific kind of person

THE PROTOCOL, written FIRST, before any beat. Advice invented to fill slide 6 is
always worse than advice the deck was built around. Every part must be doable in
under two minutes, while anxious, with no app and no googling.

  script     under 20 words, said out loud or sent, and it MUST contain one
             [square bracket] the reader fills in.
  intention  ONE move, saying both WHEN it happens and WHERE. The when may be a
             clock time, or the thing that sets it off — the moment before some
             everyday act, or the moment after it. The second kind is better,
             because it fires on something the reader will notice instead of on a
             number they have to remember. The where is a room, or the piece of
             furniture they will be standing at. It does not have to begin "I
             will" and it is better when it does not: a filled-in template reads
             like a form rather than like a person. Shape only, never these
             words: <the small move>, <when or where>.
  if_then    MUST contain the words if and then, and name a time or a place.
             Shape only, never these words: If <trigger>, then <small move>.
  menu       three tiny options, each a physical move someone could film

  The examples above show SHAPE ONLY. Never reuse their words or their subject.
  Every part of the protocol must be about the moment you were given. A script
  about declining an invitation inside a deck about waking at night is wrong even
  though the shape is right.

RULES
  The scene token MUST be one of the words listed under THE THINGS IN THIS
  MOMENT below. Not a synonym, not a word from the same family, one of those
  exact words. Write it literally into the beat for slide 1 and into the hook.

  That list is not a suggestion. Slide 1 is checked for a thing a camera could
  point at, and it recognises those words and no others. A hook built on
  "doorway" when the list says "door" is refused, and so is a hook built on a
  feeling.
  HOOKS. Give at least 8. Each is used on slide 1 exactly as written, so every
  rule here is checked and a hook that breaks one is thrown away. Eight because
  most of them will break something and one usable hook is the whole deck.
    h1  at most 12 words. Exactly one [[accent]], wrapping the last stressed
        word. Never open with Why, The reason, What nobody, Most people, or
        Here is: each of those delays the noun, and the first three words are
        the ones that carry it.
    h2  at most 7 words. No [[accent]] at all. Add a useful promise or reframe,
        not a pattern name or a repeat of the headline.

        THE H2 EITHER ABSOLVES OR PROMISES. Those are the only two jobs, and
        HOW THIS DECK IS BUILT tells you which one this deck's h2 has.
          absolves   it takes the thing the h1 just caught the reader doing and
                     removes the shame from it. Not comfort: a reason.
          promises   it names what the reader gets, or gets to stop doing, if
                     they read on. A gain, in plain words, and no number and no
                     deadline attached to it.
        An h2 that agrees with the h1 is thrown away. A deck that posted put
        the name and the same image in both lines, which is the same sentence
        twice on the only slide most people see. It is a subtitle: it moves the
        reader on, it does not nod along. Say it flat, with the hedges cut:
        "maybe", "sort of", "a bit", "can sometimes" all cost it its job.

    BOTH LINES, SIMPLE WORDS. No word of four syllables or more in either one.
    This is a cover, read at a scroll, and a word that has to be decoded is a
    thumb that keeps moving. It is not permission to soften the idea — the idea
    stays as sharp as you can make it, the vocabulary gets easy. Give eight
    hooks and this is the rule that will disqualify most of them.
    h1 CONTAINS A FILMABLE ACTION OR TENSION and a thing from the moment.
    Do not print pattern_name in either cover line. The scene is the way in.
    A specific hour is allowed when it matters, not required decoration.
      Shape only: The parcel rides home again in the [[car]].
    Instructions later must work at the reader's own time and place.
    Do not promise a result, do not sell a trick, do not name a condition.
    No diagnosis word anywhere in a hook: nervous system, attachment,
    regulation, cortisol, polyvagal, somatic, trauma response, fawn response,
    hypervigilance, neuroception. Slide 1 is read by people who never asked
    for a diagnosis.
  exports is what a slide hands on. depends_on is which earlier slides it needs.
  Slide 8 exports nothing new: everything on it already exists in slides 1 to 7.
  Never export a word that names the card itself. "cheat", "sheet", "card",
  "list" and "summary" describe the slide, they are not ideas it carries.
  Never name an author, a book or a year. Return the citation id you were given.
  Never write a diagnosis. Never tell the reader they have a condition.
  Do not use an em dash anywhere. Do not use the shape "it is not X, it is Y".
  Each beat is under 400 characters. Give at least 4 hooks, and every field
  asked for must be present, dm_share_hypothesis included.

Return only a JSON object with exactly the fields you are asked for."""

PLAN_USER = """THE MOMENT
{moment}

SUBJECT
{topic}

HOW THIS DECK IS BUILT, decided already, not yours to change:
THE THINGS IN THIS MOMENT, and the only words that count as one:
  {things}

  hook angle        {angle}
  the subtitle      {formula}
  explain through   {lens}
  advice leads with {protocol}
  saved card is     {cheat_shape}
  middle slides     {rehook}

CITATIONS YOU MAY USE. Return one id and the index of the claim you want.
{citations}
{term}
Plan the deck and return the JSON object."""

# A cap here is a hard failure, so caps sit only where a length genuinely breaks
# something. The word limits that matter for a rendered slide are checked in
# validate_plan, where a complaint can be fed back and fixed. A character cap on
# a planning note only fails a good plan over a number nobody measures, and no
# model counts characters reliably.
PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scene_token", "pattern_name", "citation_id", "claim_index", "protocol", "beats",
                 "hooks", "dm_share_hypothesis"],
    "properties": {
        "scene_token": {"type": "string", "maxLength": 30},
        # Optional shorthand. Empty is valid; it must not replace the scene.
        # Two or three words, a noun phrase, never a sentence.
        "pattern_name": {"type": "string", "maxLength": 28,
                         "description": "Optional plain shorthand for slide 4. Empty string means no label. Never a diagnosis."},
        # Replaced per deck in plan_deck() with an enum of the ids that actually
        # cover this topic. A model cannot then return a citation we do not
        # have — and one did: pinned to Cloudflare it copied the label out of
        # the prompt listing and answered "id=tawwab-2021", which is not an id.
        "citation_id": {"type": "string", "maxLength": 40},
        "claim_index": {"type": "integer", "minimum": 0, "maximum": 1},
        "protocol": {
            "type": "object",
            "additionalProperties": False,
            "required": ["script", "intention", "if_then", "menu"],
            "properties": {
                "script": {"type": "string", "minLength": 10, "maxLength": 260},
                "intention": {"type": "string", "minLength": 10, "maxLength": 260},
                "if_then": {"type": "string", "minLength": 10, "maxLength": 280},
                "menu": {"type": "array", "minItems": 3, "maxItems": 3,
                         "items": {"type": "string", "maxLength": 240}},
            },
        },
        "beats": {
            "type": "array", "minItems": 9, "maxItems": 9,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["n", "role", "beat", "exports", "depends_on", "accent_word"],
                "properties": {
                    "n": {"type": "integer", "minimum": 1, "maximum": 9},
                    "role": {"type": "string", "enum": list(ROLES)},
                    "beat": {"type": "string", "minLength": 10, "maxLength": 400},
                    "exports": {"type": "array", "maxItems": 5,
                                "items": {"type": "string", "maxLength": 40}},
                    "depends_on": {"type": "array", "maxItems": 4,
                                   "items": {"type": "integer", "minimum": 1, "maximum": 9}},
                    "accent_word": {"type": "string", "maxLength": 30},
                },
            },
        },
        "hooks": {
            # Eight, not four. The playbook has said "generate 8, ship 1" since it
            # was written and this schema said four, so the floor and the brief
            # disagreed. It matters more now: the h2 has a job it can fail at, so
            # more of the candidates get thrown away, and a plan that offered the
            # minimum four could arrive with nothing left standing.
            "type": "array", "minItems": 8, "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["h1", "h2"],
                "properties": {
                    "h1": {"type": "string", "minLength": 10, "maxLength": 130},
                    "h2": {"type": "string", "minLength": 4, "maxLength": 140},
                },
            },
        },
        "dm_share_hypothesis": {"type": "string", "minLength": 20, "maxLength": 400},
    },
}

# "How to" was on this list and is now off it. Counted on the reference account
# the page is aiming at: eighteen of its forty-two covers — forty-three percent —
# are How-to or list shapes, at sixty-five thousand followers on seventy-five
# posts. The ban was written from taste, and the measurement disagreed with the
# taste. What was actually wrong with "How to" was never the opener: it was a
# headline that promises a result the deck cannot deliver, and that is refused
# by its own rules further down, not by banning two words.
#
# "Why", "The reason", "What nobody", "Most people" and "Here's" stay banned.
# Each delays the noun, which is the fault the list was built to catch.
BANNED_OPENERS = re.compile(r"^(why|the reason|what nobody|most people|here'?s)\b", re.I)
EARLY_JARGON = ("nervous system", "attachment", "regulation", "regulated", "cortisol",
                "polyvagal", "trauma response", "fawn response", "hypervigilance",
                "emotional flashback", "somatic", "neuroception")
SEESAW = re.compile(r"(?i)\b(it'?s|you'?re|you were|you weren'?t)\s+not\b.*\b(it'?s|you'?re|you were)\b")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", re.sub(r"\[\[|\]\]", " ", text))


# How many words of its own the subtitle has to bring. See hook_faults for the
# measurement behind the number.
H2_NEW_WORDS = 2

# Function words, so "adds something" cannot be satisfied with "and why the".
# Only closed-class words are here — pronouns, articles, prepositions, auxiliary
# verbs, the small numbers. Nothing that could carry a claim, because a list that
# grew to include ordinary verbs and nouns would start refusing real subtitles.
STOPWORDS = frozenset("""
a an the and or but so if then than that this these those of in on at to for from with
without into onto over under about after before while when where how why what who whom
whose which is are was were be been being am do does did doing done have has had having
will would can could shall should may might must not no nor never you your yours
yourself i me my mine we us our ours they them their theirs he him his she her hers it
its as by up down out off again once here there all any both each few more most other
some such only own same too very just now even still yet also because until unless
during through against between among one two three four five six seven eight nine ten
""".split())


def _content_words(text: str) -> set[str]:
    """The words in this line that carry the claim, lowercased.

    Accents and fill-in brackets stripped first: a [[word]] the renderer paints
    is still the writer's word, and a [blank] is the reader's, so it is not a
    contribution the subtitle gets credit for.
    """
    return {w.lower() for w in readability.words_in(text)
            if w.lower() not in STOPWORDS}


def pick_hashtags(topic: str, seed: str) -> list[str]:
    """The tags for one deck, chosen by code from a vetted list.

    A model wrote these until now, and it produced #transitionfreeze — a name we
    had coined an hour earlier, which nobody has ever searched for — alongside
    #psychology, which a page this size will never surface in. The same failure
    the citations had: asked for a label, a model makes something label-shaped.

    Three from the subject and one broad, so a deck is findable by people
    browsing its actual topic and not only by people browsing everything. The
    choice is deterministic on the deck, so two decks on one subject do not
    carry identical tags.
    """
    try:
        bank = json.loads(HASHTAGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    subject = bank.get(topic) or bank.get(topic.replace(" ", "_")) or []
    broad = bank.get("always", [])
    if not subject and not broad:
        return []
    roll = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    # Five, which is the cap Instagram set in December 2025. They cost nothing
    # and they are how a post is filed, so there is no reason to leave room
    # unused — four from the subject so it is findable by people browsing that,
    # one broad so it is findable by people browsing the category.
    chosen = [subject[(roll + i) % len(subject)] for i in range(min(4, len(subject)))]
    if broad:
        chosen.append(broad[roll % len(broad)])
    return list(dict.fromkeys(chosen))[:5]


def hook_faults(hook: dict, name: str = "") -> list[str]:
    """Why this hook cannot be used. Empty means it can.

    Named rather than counted, because "not one hook is usable" told a repair
    nothing and it produced four fresh hooks that broke the same rule.
    """
    h1, h2 = hook["h1"], hook["h2"]
    faults = []
    if BANNED_OPENERS.match(h1.strip()):
        faults.append("opens with a banned word")
    if len(_words(h1)) > 12:
        faults.append(f"h1 is {len(_words(h1))} words, cap 12")
    if len(_words(h2)) > 7:
        faults.append(f"h2 is {len(_words(h2))} words, cap 7")
    # assemble() writes the hook onto slide 1 unchanged, so an unaccented hook
    # is a slide that renders flat and fails the accent gate every time.
    accents = len(re.findall(r"\[\[.+?\]\]", h1))
    if accents != 1:
        faults.append(f"h1 has {accents} accents, needs exactly one")
    if "[[" in h2:
        faults.append("h2 has an accent and must have none")
    jargon = [t for t in EARLY_JARGON if t in h1.lower() or t in h2.lower()]
    if jargon:
        faults.append(f"diagnosis word in the hook: {', '.join(jargon)}")
    if "—" in h1 or "—" in h2:
        faults.append("em dash")
    if SEESAW.search(h1):
        faults.append('the "not X, it is Y" shape')

    # The subtitle has to say something the headline did not. A deck that
    # posted opened "Execution freeze. You remain anchored to the bed even when
    # awake." and put "Execution freeze. Anchored to the bed." underneath it —
    # the same words twice, on the only slide most people see.
    #
    # That used to be caught by asking whether h2's words were a subset of h1's,
    # which only fires when the overlap is total. The h2 now has a job — it
    # absolves or it promises, and the formula axis says which — and a line
    # doing either brings words the headline did not have. So the check counts
    # them, with function words removed because "and why the" is not a
    # contribution.
    #
    # Two, measured. Across the seven decks published so far the failing deck
    # above scores zero and every other h2 scores three or four, so two catches
    # the real failure with a word of headroom and refuses nothing that shipped.
    new_content = _content_words(h2) - _content_words(h1)
    if len(new_content) < H2_NEW_WORDS:
        faults.append(
            f"h2 adds {len(new_content)} new words to h1, needs {H2_NEW_WORDS}. It has "
            f"one job: absolve the reader or promise them something. Either one "
            f"brings words the headline did not have")
    if name and any(name.lower() in line.lower() for line in (h1, h2)):
        faults.append(f"cover prints pattern name {name!r}. Show the scene; explain optional shorthand on slide 4")
    # Plain words, checked here rather than only on the finished deck. Slide 1 is
    # this hook written on unchanged, so a hook carrying a four-syllable noun is
    # a cover that fails the readability gate after the draft has been paid for.
    # Caught here, the plan simply picks one of its other seven hooks.
    faults += readability.line_faults(h1, "h1")
    faults += readability.line_faults(h2, "h2")
    # Slide 1 is checked for a thing a camera could point at, and slide 1 IS
    # this hook, written on unchanged. Catching it here means the PLAN retries,
    # which can choose a different hook; catching it later meant the draft loop
    # was asked to repair a slide it does not write, and it plateaued at one
    # remaining fault for seven attempts running.
    if not coherence.anchors_in(h1):
        faults.append("h1 names nothing a camera could point at")
    return faults


def hook_ok(hook: dict, name: str = "") -> bool:
    """One definition of a usable hook, used by the validator and the chooser.

    They disagreed once, so the validator accepted a deck whose only usable hook
    was then passed over for one that broke the subtitle limit. One function now,
    two callers.
    """
    return not hook_faults(hook, name)


def validate_plan(plan: dict, moment: str, topic: str, term: str = "", *, require_support: bool = False) -> list[str]:
    """Check the chain before any copy is written.

    A bad plan expanded into nine slides is nine bad slides, so this is the
    cheapest place in the pipeline to say no.
    """
    problems: list[str] = []
    citations = load_citations()

    beats = plan["beats"]
    if [b["n"] for b in beats] != list(range(1, 10)):
        problems.append("the beats are not numbered 1 to 9 in order")
    if [b["role"] for b in beats] != list(ROLES):
        problems.append("the beats are not in the fixed role order")
    for number, beat in enumerate(beats, 1):
        links = beat["depends_on"]
        if len(set(links)) != len(links) or any(link >= number or link < 1 for link in links):
            problems.append(f"slide {number} must depend only on distinct earlier slides")

    citation = citations.get(plan["citation_id"])
    if not citation:
        problems.append(f"citation {plan['citation_id']!r} is not on the allowlist")
    elif plan["claim_index"] >= len(citation["claims"]):
        problems.append(f"claim {plan['claim_index']} does not exist for {plan['citation_id']}")
    elif topic not in citation["pillars"]:
        problems.append(f"{plan['citation_id']} does not cover {topic}")
    elif require_support:
        try:
            bibliography.require_claim_support(citation, plan["claim_index"])
        except bibliography.Unverified as why:
            problems.append(str(why))

    name = plan.get("pattern_name", "").strip()
    if name and not 1 <= len(name.split()) <= 4:
        problems.append(f"the pattern name is {len(name.split())} words. A handle a reader "
                        f"repeats is two or three: 'waiting mode', 'bowl washing'")
    elif readability.hard_words(name):
        # The handle is the one phrase meant to be repeated out loud and sent on,
        # so it is the last place a word a reader has to decode belongs. A deck
        # led with "Execution freeze"; the ones that worked were "waiting mode"
        # and "bowl washing", which is two plain words each.
        problems.append(
            f"the pattern name {name!r} is built on "
            f"{', '.join(repr(w) for w in readability.hard_words(name))}. A handle is "
            f"repeated out loud, so it is made of short words: 'waiting mode', "
            f"'bowl washing'")
    elif name.rstrip(".").endswith((" is", " are", " you", " it")) or "." in name.rstrip("."):
        problems.append(f"the pattern name {name!r} is a sentence. It has to be a thing "
                        f"with a name, not a claim")
    elif name.lower().strip(" .") in {t.replace("_", " ") for t in safety.TOPICS} | \
            {t.replace("_", "") for t in safety.TOPICS}:
        # The pillar is the shelf this deck sits on, not the thing it names.
        # A deck pinned to the weaker vendor came back with pattern_name
        # "Boundaries" and slide 4 reading "the name of this pattern is
        # boundaries", which teaches nobody anything and is not sendable.
        problems.append(f"the pattern name {name!r} is just the subject. Leave it empty "
                        f"or use plain shorthand for this specific scene")
    elif name:
        if any(term in name.lower() for term in EARLY_JARGON):
            problems.append("pattern name uses diagnosis language; use plain shorthand or leave it empty")
        # An optional label is explained once, not forced onto the cover.
        fourth = beats[3]["beat"] if len(beats) > 3 else ""
        exported = " ".join(beats[3].get("exports", [])) if len(beats) > 3 else ""
        if name.lower() not in f"{fourth} {exported}".lower():
            problems.append(f"slide 4 does not name {name!r}. It is the slide that explains "
                            f"the name, not the slide that invents a second one")

    token = plan["scene_token"].lower().strip()
    allowed = coherence.anchors_in(moment)
    if not token:
        problems.append("no scene token")
    elif allowed and token not in allowed:
        problems.append(f"the scene token {token!r} is not one of the things in this "
                        f"moment: {', '.join(sorted(allowed))}")
    elif token not in beats[0]["beat"].lower():
        # Name the word and show the sentence it has to go in.
        #
        # This said only "the scene token is missing from slide 1", which is the
        # counted-not-named failure the hook validator already learned: a repair
        # prompt that does not say WHICH word cannot fix the word. On 2026-09-01
        # a run spent all four attempts here, faults going 2, 2, 2, 1, and posted
        # nothing. Every other message in this function names its value.
        #
        # The allowed set is small — coherence knows about thirty concrete nouns,
        # so "I sat in the car at 9:15pm with the engine off" offers exactly two,
        # and "engine" is not one of them. Saying so turns an unguessable note
        # into a single edit.
        problems.append(
            f"slide 1 must contain the scene token {token!r}, and does not. "
            f"Slide 1 currently reads: {beats[0]['beat'][:120]!r}. "
            f"Put {token!r} in it, or change the scene token to one of: "
            f"{', '.join(sorted(allowed)) if allowed else token}")
    # The cheat sheet must carry the moment too, but a beat is a description of a
    # slide rather than its copy, and demanding the literal token inside a
    # description rejects perfectly good plans. The coherence gate enforces it on
    # the finished slide, which is where it can be enforced honestly.

    protocol = plan["protocol"]
    if "[" not in protocol["script"] or "]" not in protocol["script"]:
        problems.append("the script has no [bracket] to fill in")

    # When and where, measured as content rather than as grammar.
    #
    # This asked for the literal words "at" and "in", in either order, and it is
    # the check that stopped run local-1788236906: four attempts, faults going
    # 2, 1, 1, 1, and nothing posted. The same signature as the scene token
    # above, and the same two causes.
    #
    # It contradicted its own prompt. The spec says "a real time OR a real
    # place" and the gate demanded both, so a model that followed the
    # instruction exactly was faulted for it and had no way to see why. The
    # prompt now asks for both, which is what slide 6 is for.
    #
    # And it graded grammar. Measured over the eight intentions this engine has
    # published: ONE passed. That one — "move the cup to the sink at 11:45pm in
    # the hallway" — is the filled-in-template shape the prompt tells the model
    # not to write, while "I will start the first step at 6am by the [[bed]]"
    # names a real time and a real place and was refused for missing an "in".
    # A gate that rewards the one bad shape and refuses seven good ones is not
    # strict, it is measuring the wrong thing. Prepositions are not places.
    # On the same eight, when and where catch the two that deserve it: "I will
    # check my calendar and let you know" and "I will take a slow breath".
    missing = ([] if coherence.when_in(protocol["intention"]) else ["when it happens"]) + \
              ([] if coherence.place_in(protocol["intention"]) else ["where it happens"])
    if missing:
        problems.append(
            f"the intention does not say {' or '.join(missing)}. It reads: "
            f"{protocol['intention'][:120]!r}. Name a time the reader will notice "
            f"— a clock time, or before/after/when something happens — and the room "
            f"or thing they will be standing at")
    if not re.search(r"\bif\b.*\bthen\b", protocol["if_then"], re.I):
        problems.append("the if-then is not an if-then")
    for option in protocol["menu"]:
        if re.search(r"\b(figure out|decide|try to|work on)\b", option, re.I):
            problems.append(f"menu option is not a concrete move: {option[:50]}")

    # The advice has to be about THIS moment. Models lift the shape example from
    # the prompt and hand back a script for declining an invitation inside a deck
    # about waking at 2am: the format is right and the deck is nonsense. Sharing
    # a real word with the moment or the hook is a low bar that catches it.
    # The basis is the moment and the beats that set the scene, never the beats
    # that describe the advice itself. Including those would make the check
    # circular: advice about a birthday would match a beat about a birthday.
    basis = {w.lower() for w in _words(moment) if len(w) > 3}
    for beat in beats[:4]:
        basis |= {w.lower() for w in _words(beat["beat"]) if len(w) > 3}
    basis.add(token)
    advice = {w.lower() for w in _words(" ".join(
        [protocol["script"], protocol["intention"], protocol["if_then"], *protocol["menu"]]))}
    if not (advice & basis):
        problems.append("the advice is not about this moment, it reads as a borrowed example")

    # Slide 8 may only recap. A card that adds an idea is a new argument
    # arriving after the reader has stopped reading for one.
    # Every slide before the cheat sheet, not only the three just before it. A
    # recap that reaches back to the mechanism on slide 4 or the problem on
    # slide 2 is doing exactly what a recap is for, and counting that as a new
    # idea refused decks for being well made.
    earlier = set()
    for beat in beats[:7]:
        earlier |= {w.lower() for w in _words(beat["beat"])} | {e.lower() for e in beat["exports"]}
    new_on_cheat = {e.lower() for e in beats[7]["exports"]} - earlier
    if new_on_cheat:
        problems.append(f"the cheat sheet exports something new: {', '.join(sorted(new_on_cheat))}")

    early = f"{beats[0]['beat']} {beats[1]['beat']}".lower()
    for jargon in EARLY_JARGON:
        if jargon in early:
            problems.append(f"diagnosis word before slide 3: {jargon}")

    # The field's name, when this deck was built on a proved concept. Both
    # halves matter and they pull opposite ways: without the first the concept
    # channel produces the same deck the feed does, and without the second it
    # puts a clinical word on the only slide most people see.
    if term:
        wanted = term.lower()
        if len(beats) > 3 and wanted not in beats[3]["beat"].lower():
            problems.append(f"slide 4 does not print {term!r}. That word is the only "
                            f"thing this deck has that a harvested one does not, and "
                            f"slide 4 is where the name gets handed over")
        if wanted in early:
            problems.append(f"{term!r} appears before slide 3. The reader recognises "
                            f"themselves first and learns the word afterwards")

    if not any(hook_ok(h, name) for h in plan["hooks"]):
        why = "; ".join(f"hook {i}: {', '.join(hook_faults(h, name))}"
                        for i, h in enumerate(plan["hooks"], 1))
        problems.append(f"not one hook is usable — {why}")

    for beat in beats:
        if "—" in beat["beat"]:
            problems.append(f"slide {beat['n']} uses an em dash")
        if SEESAW.search(beat["beat"]):
            problems.append(f"slide {beat['n']} uses the 'not X, it is Y' shape")

    return problems


CONCRETE = re.compile(r"\d|\bclock|phone|inbox|bed|kitchen|desk|email|text|message|"
                      r"chest|heart|stomach|door|screen|laptop|car\b", re.I)


def best_hook(plan: dict, token: str = "", allow_review: bool = False) -> dict:
    """The best usable hook, which is not simply the shortest one.

    A cover has to be one breath, so length matters. But "The maths started" is
    short and says nothing a camera could point at. Naming something concrete
    comes first, then brevity.
    """
    def rank(hook: dict) -> tuple:
        h1 = hook["h1"]
        has_token = bool(token) and token.lower() in h1.lower()
        return (not has_token, not bool(CONCRETE.search(h1)), len(_words(h1)))

    usable = [h for h in plan["hooks"] if hook_ok(h, plan.get("pattern_name", "").strip())]
    if not usable and allow_review:
        # V1 shows the least-bad cover and every remaining fault to the owner.
        # This is only reached after plan_deck has proved that the outstanding
        # plan faults are reviewable writing/structure notes rather than source
        # or safety failures.
        usable = list(plan["hooks"])
    if not usable:
        raise Refused("No usable scene-first cover remains", retry=False)
    return sorted(usable, key=rank)[0]


def plan_deck(moment: str, topic: str, term: str = "", review_plan: bool = False):
    """Plan one deck. Returns (plan, axes, provider), or raises.

    `term` is the field's name for the idea, when the deck was built from a
    proved concept rather than from a harvested moment. It is the only thing a
    concept deck has that a feed deck does not, and without it the two produce
    the same deck: the concept picks the subject and is then thrown away.

    One outline and at most three bounded field repairs. Three unchanged fault
    signatures stop the loop. Clean work and the selected source remain fixed.
    """
    axes = draw_axes(moment, recent_formulas())

    # A book is looked up fresh for this deck, from any book of any year, and
    # put through the five gates in bibliography.py before it can be offered.
    # What survives is added to the pool, so tomorrow starts from a bigger
    # library than today did. Nothing here can fail the run: when no suggestion
    # survives — which is ordinary, the gates are strict — the deck is written
    # from a book proved on an earlier day.
    avoid = bibliography.recent()
    # V1 uses verified source material first. Source discovery is useful only
    # when this subject has no supported claim; it must not spend quota before
    # every otherwise-ready carousel.
    if os.environ.get("SS_REVIEW_WINDOW_V1") == "1" and citations_for(topic, avoid):
        found, refused = None, []
    else:
        found, refused = bibliography.discover(topic, moment, avoid)
    if found:
        bibliography.store(found)
        print(f"    citation      {found['line']} "
              f"(verified, {found['verified']['scanned_hits']} scanned hits, "
              f"checked by {found['verified']['checked_by']})")
    elif refused:
        print(f"    citation      no new book survived: {refused[0][:88]}")

    options = citations_for(topic, avoid)
    if not options:
        raise Refused("No source-supported claim is available for this subject. Saved claims need review.", retry=False)
    if found:
        options.sort(key=lambda c: c["id"] != found["id"])
    listing = "\n".join(
        f"  {c['id']}\n" + "\n".join(f"      claim {i}: {claim}"
                                     for i, claim in enumerate(c["claims"])
                                     if i in bibliography.supported_indices(c))
        for c in options
    )
    # The words the coherence gate will actually recognise, taken from the gate
    # itself rather than guessed. The plan used to invent a scene token from the
    # moment's wording — "doorway" for a moment about a door — and slide 1 was
    # then refused for naming nothing filmable, by a check reading a different
    # vocabulary. One list, taken from the checker, given to the writer.
    things = sorted(coherence.anchors_in(moment))
    user = PLAN_USER.format(
        term=TERM_BRIEF.format(term=term) if term else "",
        moment=moment, topic=topic.replace("_", " "),
        things=", ".join(things) if things else "(nothing recognised)",
        angle=AXES["angle"][axes["angle"]],
        formula=AXES["formula"][axes["formula"]],
        lens=AXES["lens"][axes["lens"]],
        protocol=AXES["protocol"][axes["protocol"]],
        cheat_shape=AXES["cheat_shape"][axes["cheat_shape"]],
        rehook=AXES["rehook"][axes["rehook"]],
        citations=listing,
    )

    # Repair from the BEST plan so far, the same as the draft loop. Starting
    # each attempt from whatever came back last lets a fixed fault come back.
    user += ("\nSOURCE LIMIT: The supplied claims are the full factual boundary. "
             "Do not invent a cause, brain effect or benefit for a suggested action. "
             "Offer actions as things to try, with no promised result. "
             "A shared word does not prove a mechanism. Keep scripts to words "
             "the reader can actually say, without directions inside the quotation.")
    attempt_user = user
    best_plan: dict | None = None
    best_problems: list[str] | None = None
    # A closed list, not free text. The ids are known before the call, so there
    # is no reason a model should be able to type one.
    plan_schema = json.loads(json.dumps(PLAN_SCHEMA))
    plan_schema["properties"]["citation_id"] = {
        "type": "string", "enum": [c["id"] for c in options],
        "description": "Exactly one of these, on its own. Not 'id=' and not the title."}
    # Books used to carry exactly two claims each because a person typed two. A
    # verified lookup arrives with one, and a book proved twice grows a third,
    # so the ceiling is whatever is actually on the shelf today. validate_plan
    # still checks the index against the ONE citation chosen.
    plan_schema["properties"]["claim_index"] = {
        "type": "integer", "minimum": 0,
        "maximum": max(len(c["claims"]) for c in options) - 1}

    history: list[int] = []
    signatures = []
    import plan_repair
    import draft_repair
    original_provider = None
    def checked_outline(value):
        return validate_plan(value, moment, topic, term=term, require_support=True)
    for attempt in range(4):
        if attempt == 0:
            plan, provider = llm.ask(PLAN_SYSTEM, attempt_user, plan_schema, temperature=1.0)
            original_provider = provider
            problems = checked_outline(plan)
        else:
            providers = tuple(p for p in llm.PROVIDERS if p[0] == original_provider)
            if not providers:
                raise llm.ModelRefused("The original outline writer is unavailable for field repair.")
            reply, provider = llm.ask(
                PLAN_SYSTEM + "\nREPAIR MODE: return field edits only, not a new outline. "
                "Use plain text for text fields and JSON text for number or array fields. "
                "The source and claim cannot change. Do not alter clean fields.",
                attempt_user, plan_repair.schema(best_plan, best_problems),
                temperature=0.4, providers=providers)
            plan, problems = plan_repair.apply(best_plan, best_problems, reply, plan_schema, checked_outline)
        if not problems:
            return (plan, axes, provider, []) if review_plan else (plan, axes, provider)
        history.append(len(problems))
        signatures.append(outcomes.fault_signature(problems))
        if best_problems is None or len(problems) < len(best_problems):
            best_plan, best_problems = plan, problems
        plan, problems = best_plan, best_problems
        if outcomes.unchanged_faults(signatures):
            break
        # The plan goes back with the complaints, and it is the BEST plan, not
        # the last one. Retrying blind asks the same model the same question and
        # gets the same answer; retrying from a worse plan loses ground already
        # won. Temperature drops too: this is no longer a search for an angle,
        # it is a correction to one.
        attempt_user = user + (
            "\n\nTHE BEST PLAN SO FAR, which is nearly right:\n"
            + json.dumps(plan, indent=2)
            + f"\n\nOnly these {len(problems)} things are wrong with it:\n  "
            + json.dumps(draft_repair.fault_map(problems), indent=2)
            + "\n\nEditable fields and value encoding:\n"
            + json.dumps(plan_repair.describe(plan), indent=2)
            + "\nReturn only edits to the listed field IDs using paths such as /field_1. "
              "No full outline. Leave every other field unchanged."
        )
    # Refused, not llm.ModelRefused. Both used to be the same type, so an
    # unreachable vendor and a plan the gates simply would not pass turned CI
    # red in exactly the same way. The vendor case still raises ModelRefused —
    # from inside llm.ask(), which propagates straight out of this loop — so the
    # two are told apart by where they originate. See outcomes.py.
    #
    # Same trajectory rule as the draft loop below: a fault count that stopped
    # falling is a gate no wording satisfies, and offering a retry into it wastes
    # a run. The trail rides on the exception so the alert can print it.
    reviewable = (best_problems and all(problem.startswith(
        ("the cheat sheet exports something new:", "not one hook is usable —"))
        for problem in best_problems))
    if review_plan and best_plan is not None and reviewable:
        return best_plan, axes, original_provider, list(dict.fromkeys(best_problems))
    shape, _ = outcomes.trajectory(history)
    raise Refused(
        f"{'; '.join(dict.fromkeys(best_problems or []))[:340]} "
        f"[faults per attempt: {', '.join(str(n) for n in history)}]",
        retry=not outcomes.unchanged_faults(signatures), history=history, signatures=signatures)


# ─────────────────────────── the draft ────────────────────────────
#
# The model returns JSON and the markdown is assembled here, rather than asking
# it for markdown directly. The renderer parses exact field labels, and a model
# that renames one field silently produces a deck with a missing slide. Field
# labels are not a creative decision, so they are not the model's to make.

DRAFT_SYSTEM = """You write the copy for a nine-slide Instagram carousel about
ordinary relational psychology. The plan is settled. Do not re-plan, do not add a
slide, do not change the moment, the citation or the protocol.

VOICE
A smart friend who reads the textbooks. Dry, warm, specific. Never a therapist,
never a guru, never a brand.

EVERY EXAMPLE IN THIS PROMPT IS ABOUT DENTISTS, PARKING TICKETS, LIBRARY BOOKS
AND BICYCLES. That is deliberate and it is not this page's subject. Copy the
rhythm, never the words. Not one object, room, hour or phrase from an example
below may appear in what you return, and this is checked by counting shared
runs of words. Measured on this engine's own output: every example that was set
on the page's own ground got copied into a published deck within a week, and no
off-subject example ever did.
  "You have had the dentist's number in your phone for nine days. You have opened
   the contact. You have not pressed call."
  "The parking ticket is on the windowsill. You walk past it. You have developed
   a small route around the windowsill."
  "The library book is four weeks late. Returning it now feels like a confession,
   so you keep it, which is worse, which you know."

EVERY SLIDE TURNS. This is the difference between a deck people finish and a
deck people leave on slide 3. Nine slides, nine things the reader did not have
a moment earlier. A slide that restates the slide before it in fresh words is
the slide they stop on, and it is the commonest way a finished deck is dead.

  A turn is small. A consequence they had not connected, a second meaning, a
  flat admission, the same fact seen from the other side. Never a joke, never
  a twist, never a bigger claim.

  NO LABEL IS REQUIRED. If pattern_name is empty, do not invent one. If it is
  present, explain it on slide 4 as our shorthand, not a medical fact. Slides
  1 and 2 show the scene. Do not credit an invented label to the source.

  SAY THE FINDING ONCE. Slide 3 puts it in plain words and that is the end of
  it. The researcher's surname appears on the citation line and nowhere else
  in the deck, caption included. Slides 4 to 7 carry the IDEA. They may reuse
  one word from slide 3. They may never reuse its sentence.

  NAME THE THING IN THE ROOM TWO OR THREE TIMES, not nine. The object anchors
  the deck; it does not run it. Once it has done its work on slides 1 and 2 it
  should mostly get out of the way.

MARKUP, the rule that gets broken most, so read it twice

  EVERY line of copy you write needs exactly one [[accent]] around its most
  important word. Not most lines. Every line. The renderer colours that word,
  and a line without one prints flat and grey.

  Right:  "The renewal has been open in a tab since [[Tuesday]]."
  Right:  "I am not renewing it again before [[Friday]]."
  Wrong:  "The renewal has been open in a tab since Tuesday."     no accent
  Wrong:  "The [[renewal]] has been open since [[Tuesday]]."      two accents

  The accent wraps a WHOLE word. "[[decide]]d" and "[[script]]ed" print as a
  word broken in half, and one of each has shipped.

  This applies to every h2, every body, every old and new line, every bullet,
  the CTA and the closing thought. Nine slides, every field but one: slide 8's
  callout prints as a solid pill in a single colour, so it takes no accent.

  [bracket] marks a blank the reader fills in, inside a script. Not the same
  thing, and a field can carry both.

HARD RULES, each one checked by code after you finish
  No em dash or en dash. Use a period or a comma.
  Never write "it is not X, it is Y" or "you are not X, you are Y". Say what it IS.
  No emoji. No hashtags inside slides. No slide numbers. No handle inside copy.
  Never open slide 1 with Why, The reason, What nobody, Most people, Here is.
  No diagnosis words on slides 1 or 2: nervous system, attachment, regulation,
  regulated, cortisol, polyvagal, trauma response, fawn response, hypervigilance,
  emotional flashback, somatic, neuroception.
  Never tell the reader they have a condition. A noun for a pattern is fine.
  Never name an author, a book, a study or a year. That line is added for you.
  Slide 2 must work alone as a cover, for someone who never saw slide 1.
  Slide 8 adds nothing new. It recaps slides 4 to 7 only.
  Bodies stay under 220 characters. The closing thought stays under 180.
  SIMPLE WORDS, SHARP IDEA. No word of four syllables or more, anywhere a reader
  can see it. Not in a body, not in a bullet, not in the caption. This is the
  rule most likely to send a draft back, and it is not a request to simplify the
  argument: keep the argument exactly as hard as it is and say it in words a
  nine-year-old already owns. Every long noun has a short one that means the
  same, and the long one is almost never the only word that would do. A word
  inside [square brackets] is the reader's, so it is not counted.

THE CTA, slide 9. This exact shape, and nothing longer than 11 words:
    Send this to the [kind of person] who [does the thing in the moment].
  e.g.  Send this to the friend who has never returned that [[book]].
  It must contain the word "send" or "share", and name who. Not "share if you
  relate", not "tag someone". A named kind of person.

  The closing thought on that same slide is NOT the CTA again. Two lines, two
  jobs: the CTA asks the reader to pass it on, the closing thought is the one
  sentence they keep. It is addressed to the reader and it does not mention
  sending. A deck once printed the identical sentence in both, so the last card
  a reader saw asked twice and gave nothing, and it is checked now.

SLIDES 1 AND 2 EACH NAME A THING. Not a feeling, not a pattern — a thing in the
room, or the hour on the clock. The moment hands you its own objects and its
own hour: put one of them on slide 1 and a DIFFERENT one on slide 2.

  Slide 1 without a thing is a caption, and it is checked.
  Slide 2 is served on its own to people who never saw slide 1, so it has to
  set its own scene rather than refer back to one.

  Weak, and refused:  "The form went unread before it was signed."
  Right:              "You signed it standing up, still holding the [[helmet]]."

THE PROTOCOL GOES ON THE SLIDES. The plan hands you an "intention" line and an
"if_then" line. One of slides 4 to 7 carries the intention, keeping its move
and keeping its time or its place. Another carries the if-then, and that one
keeps the words "if" and "then" because code looks for them.

The intention does NOT have to begin "I will", and it is better when it does
not. A filled-in template reads like a form somebody completed rather than
like a person deciding something. One shipped deck filled the shape in twice
over and produced an instruction naming a room the moment never contained.
Say the move, say when. That is the whole requirement.

The reader must be able to act on it tomorrow with nothing looked up.
Reword to fit the slide. Do not summarise the move away.

THE THREAD, slides 4 to 7. This is the rule drafts fail most often, and it is
never obvious from a single slide.

  Slide 3 names the mechanism. EVERY ONE of slides 4, 5, 6 and 7 has to use at
  least one word from THE THREAD WORDS listed below, or from your own slide 3
  wording. One word is enough. All four slides need one, not three of them.

  Carry the IDEA, never the sentence. Do not paste the claim into a slide and do
  not name the researcher again — they are credited on slide 3 and nowhere else,
  the caption included. A deck once printed a sentence beginning with the
  researcher's surname inside a line the reader was told to say out loud, which
  is not a thing any person says. Take the word. Leave the citation.

  Every field in the deck says something the deck has not said yet. The three
  lines on slide 3 are three different sentences: what the source says, what
  that means in plain words, and what it explains about this evening. Printing
  one sentence under two of those headings is the fastest way to look broken.

  Advice that never touches slide 3 is advice for a different deck. It reads
  fine on its own, which is exactly why nobody notices, and it is checked. This
  is the rule that fails more often than every other rule put together, and it
  fails on slides 6 and 7, because by then the advice has drifted into general
  good habits. Before you finish, read slides 6 and 7 back and check each one
  still says one of these words.

THE CAPTION is NOT the deck written out again underneath itself. That is what
it used to be and nobody reads it twice.

  Four short paragraphs, 60 to 120 words. The last one that shipped was two
  sentences and 151 characters, which reads like the post was abandoned.

  1  The familiar action, and what it costs. ONE sentence, and it has to work alone,
     because Instagram hides everything after about 125 characters.
  2  Two or three sentences saying something the slides did NOT say. Where
     this shows up in an ordinary week, or what it is usually mistaken for.
     This is the paragraph that earns the caption its space.
  3  Who is let off. One line naming the thing this was never a failure of.
  4  Ask them to save it, and say what they are saving it for. Name the next
     time this will happen to them. Use your own words for both.

  Never a summary of the slides. Somebody reading the caption has already seen
  them, or is deciding whether to.

You do not write hashtags. Code picks them from a vetted list, the same way it
picks the citation, because a model asked for a label produces something
label-shaped: a deck went out tagged with a name this engine had coined an
hour earlier, which nobody has ever searched for.

  Asking for a save moves saves by about 90 percent, and asking for a like
  slightly lowers likes, so ask for the save and never for the like. Slide 9
  already asks them to send it, and one post gets one action out of a person,
  so there are exactly two asks in the whole deck: send on the slide, save in
  the caption.

THE CHEAT SHEET, slide 8, must name the scene token from the plan. The reader
saves this slide on its own, so it has to say what moment it is for.

  Every [[accented]] word on slide 8 must already appear somewhere in slides 1
  to 7. The card is a recap, so an accent on it is a reminder and never a new
  idea. Do not accent the word "cheat", or any word describing the card itself.

INVENT NOTHING. Every object, room and time you write must come from the
moment or the plan. If the moment says a laptop and a remote, do not write
about keys. A detail the moment did not contain is a different person's
evening, and it is checked.

MASCOT BRIEFS
  Nine plain English descriptions of a small donkey, one per slide, each drawn
  from that slide's own beat so no two could be swapped. Posture and expression,
  one prop at most. Describe what the body is doing, never an emotion word.
  No text, letters, numbers, signs, screens or labels anywhere in the artwork.
  This is refused more often than any other rule, and always the same way: the
  moment involves a phone, so the brief describes it being looked at. A picture
  of a screen is a picture of writing. Put the device face down, or held
  against the body, or pushed away: the object, never its display. Same for a
  clock, which is turned to the wall and never shows a time.
  Nothing in quotation marks, ever. A brief that quotes a spoken line is asking
  for a speech bubble, and a speech bubble is lettering: not "saying 'not
  today'", but ears flat and one hoof already turning away. A named object is
  fine, the words on it never are — a parking ticket tucked under a wiper is a
  picture, a parking ticket with the fine written on it is not.
  Nine different things happening, not one thing in nine spots. Change the VERB
  first: standing nine times with the scenery moved around is one picture. And
  vary how the briefs begin — if all nine open on the same three words you have
  filled in a template, so start most of them on the action or the place.

Return only a JSON object with the fields you are asked for."""

DRAFT_USER = """THE PLAN, settled:
{plan}

THE HOOK, already chosen. Use these two lines as slide 1, unchanged:
  H1: {h1}
  H2: {h2}

THE SOURCE CLAIM for slide 3, use this wording, do not alter it:
  {claim}

THE THREAD WORDS. Each of slides 4, 5, 6 and 7 must contain at least one of
these, or a word you use in your own slide 3 lines:
  {thread}

HOW THIS DECK IS WRITTEN:
  explain through   {lens}
  middle slides     {rehook}
  saved card is     {cheat_shape}

WHAT THE H2 ABOVE PROMISED, which the deck now has to keep:
  {formula}

That subtitle is a debt. Whatever it said the reader would get, some slide has
to hand it over, and slide 8 is where a reader looks for it. A deck that made
the promise and never paid it is the one that gets unfollowed.

THE SCENE. These are the only concrete things in this person's evening:
  {scene}

Every slide, the advice included, stays inside that scene. Do not put them at a
desk, in a kitchen, on a sofa, or reaching for a phone unless the words above
say so. If the advice needs somewhere to happen, it happens here.

This is the rule most drafts break. A deck about waking at 2:17am once shipped
with "17 tabs open" in its advice, because the advice was written for a
different evening and dropped in. Advice you could paste into any deck is the
wrong advice for this one.

Write the copy and return the JSON object."""

# Same principle as the plan schema, and it matters more here because these
# caps sit next to editorial limits that look identical. They are not: a schema
# cap is a hard failure with no feedback, while audit_copy enforces the real
# editorial limits and its complaints are handed back for repair. So the schema
# is deliberately looser than the editorial rule, and the gate does the judging.
DRAFT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cost", "explains", "name", "script", "action",
                 "sustain", "cheat", "cta", "caption", "alt", "mascots"],
    "properties": {
        "cost": {"type": "object", "additionalProperties": False, "required": ["h2", "body"],
                 "properties": {"h2": {"type": "string", "maxLength": 140},
                                # 185, and it is measured. The editorial cap on
                                # slide 2 is 35 words, and this used to be 280
                                # so the model wrote to the schema and the gate
                                # refused it afterwards. Setting it to 200 was
                                # not enough either: a live publish run came
                                # back at 38 words in under 200 characters and
                                # stalled there for three attempts, one fault
                                # from a finished deck.
                                #
                                # A word on the decks we accept runs 5.5
                                # characters including its space, so 35 words is
                                # about 190. 185 leaves the gate a little room
                                # to be the thing that refuses rather than the
                                # schema, which gives a repair something to act
                                # on instead of a silent truncation.
                                "body": {"type": "string", "maxLength": 185}}},
        # The description is rewritten per deck in write_deck() with the real
        # name in it. A rule stated once in the system prompt was missed seven
        # attempts running: the model is filling in a field called "explains"
        # and the instruction was three hundred lines away talking about
        # "slide 3's last line".
        "explains": {"type": "string", "maxLength": 280,
                     "description": "Slide 3's last line. Says what the supported "
                                    "finding means for the person in this moment. Never restates "
                                    "the source claim."},
        "name": {"type": "object", "additionalProperties": False, "required": ["h2", "body"],
                 "properties": {"h2": {"type": "string", "maxLength": 60},
                                "body": {"type": "string", "maxLength": 220}}},
        "script": {"type": "object", "additionalProperties": False,
                   "required": ["h2", "old", "new"],
                   "properties": {"h2": {"type": "string", "maxLength": 60},
                                  "old": {"type": "string", "maxLength": 220},
                                  "new": {"type": "string", "maxLength": 220}}},
        "action": {"type": "object", "additionalProperties": False,
                   "required": ["h2", "old", "new", "body"],
                   "properties": {"h2": {"type": "string", "maxLength": 60},
                                  "old": {"type": "string", "maxLength": 240},
                                  "new": {"type": "string", "maxLength": 240},
                                  "body": {"type": "string", "maxLength": 220}}},
        "sustain": {"type": "object", "additionalProperties": False,
                    "required": ["h2", "bullets"],
                    "properties": {"h2": {"type": "string", "maxLength": 60},
                                   "bullets": {"type": "array", "minItems": 3, "maxItems": 3,
                                               "items": {"type": "string", "maxLength": 170}}}},
        "cheat": {"type": "object", "additionalProperties": False,
                  "required": ["h2", "callout", "bullets"],
                  "properties": {"h2": {"type": "string", "maxLength": 60},
                                 # Printed as a pill, in one colour. An accent
                                 # here renders as nothing, so it is stripped.
                                 "callout": {"type": "string", "maxLength": 140,
                                             "description": "Slide 8's bottom pill. "
                                                            "No [[accent]] — it prints in "
                                                            "one colour."},
                                 "bullets": {"type": "array", "minItems": 3, "maxItems": 4,
                                             "items": {"type": "string", "maxLength": 170}}}},
        "cta": {"type": "object", "additionalProperties": False, "required": ["cta1", "closing"],
                "properties": {"cta1": {"type": "string", "maxLength": 150},
                               "closing": {"type": "string", "maxLength": 240}}},
        # There used to be a 200 character FLOOR here, which is why the caption
        # was the whole deck retold as prose underneath itself. That is gone.
        #
        # It is NOT replaced with a hard short cap. The study behind "captions
        # under 30 words win" (Socialinsider, 9.1M posts) measures likes and
        # comments over followers and excludes saves and sends entirely — the
        # two behaviours this page is built for — and the biggest accounts in
        # this niche run captions of a couple of hundred words. So this is a
        # range wide enough for either, and the prompt asks for the shape.
        "caption": {"type": "string", "minLength": 300, "maxLength": 900,
                    "description": "60 to 120 words in four short paragraphs: the action and "
                                   "what it costs, then something the slides did not say, "
                                   "then one line letting the reader off, then ask them to "
                                   "save it. Never a summary of the slides."},
        "alt": {"type": "array", "minItems": 9, "maxItems": 9,
                "items": {"type": "string", "maxLength": 260}},
        # Nine briefs, one per slide, each drawn from that slide's own beat so no
        # two could be swapped. Never a letter or a number in the artwork: a
        # previous pipeline shipped slides with "2. Thinking" printed on the
        # donkey, which is why the renderer refuses text in a pose.
        "mascots": {"type": "array", "minItems": 9, "maxItems": 9,
                    "items": {"type": "string", "minLength": 15, "maxLength": 240}},
    },
}

# Some fields come back without their accent however plainly the prompt asks,
# and a deck should not die over markup we can add ourselves. This wraps the
# last substantial word, which is where the stress usually falls anyway. The
# critic still sees the result and can object if the choice is poor.
_TRAILING = re.compile(r"[\s\"'.,!?;:)\]]+$")


def ensure_accent(text: str) -> str:
    """Give a line exactly one accent: add one if missing, keep the first if many."""
    if not text or not text.strip():
        return text
    marks = re.findall(r"\[\[.+?\]\]", text)
    if len(marks) == 1:
        return text
    if len(marks) > 1:
        # Keep the first, unwrap the rest.
        seen = False
        def once(match):
            nonlocal seen
            if seen:
                return match.group(0)[2:-2]
            seen = True
            return match.group(0)
        return re.sub(r"\[\[.+?\]\]", once, text)

    body = text.rstrip()
    tail = text[len(body):]
    trailing = _TRAILING.search(body)
    punctuation = trailing.group(0) if trailing else ""
    core = body[: len(body) - len(punctuation)]
    words = core.split()
    if not words:
        return text
    # Walk back to the last word worth colouring, skipping small connectives.
    skip = {"the", "a", "an", "and", "or", "to", "in", "on", "at", "of", "it",
            "is", "was", "for", "you", "your", "my", "me", "i", "that", "this"}
    index = len(words) - 1
    while index > 0 and words[index].lower().strip(".,!?") in skip:
        index -= 1
    words[index] = f"[[{words[index]}]]"
    return " ".join(words) + punctuation + tail


def no_accent(text: str) -> str:
    """Strip accent markup from a line the renderer prints without colour.

    Slide 8's callout is a pill, and render.py writes it through plain(), so
    [[markup]] there never becomes colour — it is invisible in the PNG either
    way. It was still the one field of copy that went into the markdown raw
    while every other went through ensure_accent, and check_accents counted it.

    A live run died on it: "slide 8 has two accents in one field", seven
    attempts, faults 7, 3, 1, 1, 1, 1, 1. The model could not fix it because
    the complaint did not name the field and the JSON it was repairing looked
    fine; ensure_accent had quietly cleaned every other field on that slide.
    A whole deck, the plan, the judge and the composer, thrown away over markup
    that renders as nothing.

    Stripping here also keeps carousel.md honest: what the file says is on the
    card is what the card shows.
    """
    return re.sub(r"\[\[|\]\]", "", text)


LAYOUTS = {"hook": "Template A", "cost": "Template A", "source": "Template F",
           "name": "Template B", "script": "Template C", "action": "Template C",
           "sustain": "Template D", "cheat": "Template D", "cta": "Template E"}


def assemble(plan: dict, copy: dict, hook: dict, citation: dict, claim: str,
             mascots: list[str], title: str, pattern: str, pillar: str,
             tags: list[str] | None = None) -> str:
    """Build the markdown the renderer parses. Labels are fixed here, not asked for."""
    out = [
        f"# Carousel: {title}",
        "",
        f"**Pattern:** {pattern} · **Content Pillar:** {pillar} · "
        f"**Core Emotion:** Recognition",
        f"**DM-Share Hypothesis:** {plan['dm_share_hypothesis']}",
        "",
        "### Slide 1 · Hook",
        f"- **Layout:** {LAYOUTS['hook']}",
        f"- **H1:** {hook['h1']}",
        f"- **H2:** {hook['h2']}",
        f"- **Mascot:** {mascots[0]}",
        "",
        "### Slide 2 · Agitation",
        f"- **Layout:** {LAYOUTS['cost']}",
        f"- **H2:** {ensure_accent(copy['cost']['h2'])}",
        f"- **Body:** {ensure_accent(copy['cost']['body'])}",
        f"- **Mascot:** {mascots[1]}",
        "",
        "### Slide 3 · Source Anchor",
        f"- **Layout:** {LAYOUTS['source']}",
        f"- **Source:** {citation['line']}",
        f"- **Source Claim:** {claim}",
        f"- **What This Explains Here:** {ensure_accent(copy['explains'])}",
        f"- **Mascot:** {mascots[2]}",
        "",
        "### Slide 4 · Value Step 1",
        f"- **Layout:** {LAYOUTS['name']}",
        "- **Badge:** 01",
        f"- **H2:** {ensure_accent(copy['name']['h2'])}",
        f"- **Body:** {ensure_accent(copy['name']['body'])}",
        f"- **Mascot:** {mascots[3]}",
        "",
        "### Slide 5 · Value Step 2",
        f"- **Layout:** {LAYOUTS['script']}",
        f"- **H2:** {ensure_accent(copy['script']['h2'])}",
        f"- **When:** {ensure_accent(copy['script']['old'])}",
        f"- **Say:** \"{ensure_accent(copy['script']['new'])}\"",
        f"- **Mascot:** {mascots[4]}",
        "",
        "### Slide 6 · Value Step 3",
        f"- **Layout:** {LAYOUTS['action']}",
        f"- **H2:** {ensure_accent(copy['action']['h2'])}",
        f"- **When:** {ensure_accent(copy['action']['old'])}",
        f"- **Say:** \"{ensure_accent(copy['action']['new'])}\"",
        f"- **Body:** {ensure_accent(copy['action']['body'])}",
        f"- **Mascot:** {mascots[5]}",
        "",
        "### Slide 7 · Value Step 4",
        f"- **Layout:** {LAYOUTS['sustain']}",
        f"- **H2:** {ensure_accent(copy['sustain']['h2'])}",
    ]
    out += [f"  • {ensure_accent(b)}" for b in copy["sustain"]["bullets"]]
    out += [
        f"- **Mascot:** {mascots[6]}",
        "",
        "### Slide 8 · Cheat Sheet",
        f"- **Layout:** {LAYOUTS['cheat']}",
        f"- **H2:** {ensure_accent(copy['cheat']['h2'])}",
        f"- **Callout:** {no_accent(copy['cheat']['callout'])}",
        "- **Bullets:**",
    ]
    out += [f"  • {ensure_accent(b)}" for b in copy["cheat"]["bullets"]]
    out += [
        f"- **Mascot:** {mascots[7]}",
        "",
        "### Slide 9 · CTA",
        f"- **Layout:** {LAYOUTS['cta']}",
        f"- **Primary CTA:** {ensure_accent(copy['cta']['cta1'])}",
        f"- **Closing thought:** {ensure_accent(copy['cta']['closing'])}",
        "- **Handle:** @suresilly",
        f"- **Mascot:** {mascots[8]}",
        "",
        "## Caption",
        # The caption is READ, never rendered. Instagram prints the characters
        # it is given, so [[markup]] arrives as [[markup]] — 20260901's post
        # went out with twenty-one pairs of brackets in its first paragraph.
        #
        # This was the last line of copy still going into the file raw, which
        # is the same hole the slide 8 callout was in: the model is taught
        # [[accent]] as the house markup for every line it writes, so sooner or
        # later it uses it everywhere, and only the fields that pass through
        # ensure_accent or no_accent are normalised. Nothing downstream caught
        # it either — check_accents reads only ### Slide sections and
        # audit_copy wants an accent PER SLIDE, so a bracketed caption broke no
        # rule anyone had written down.
        no_accent(copy["caption"].strip()),
        "",
        # A heading, and a # on every tag.
        #
        # This wrote the tags as bare words under a horizontal rule, and
        # post_to_ig.py looks for a "## Hashtags" section. It never found one,
        # so every post went out with the caption and nothing else — no tags at
        # all, on every deck this engine has ever published. Two formats that
        # never agreed, in two files, and nothing compared them.
        "## Hashtags",
        " ".join(f"#{tag}" for tag in (tags or [])),
        "",
        "## Alt Text",
    ]
    out += [f"Slide {i}: {line}" for i, line in enumerate(copy["alt"], 1)]
    out += ["", f"**DM-Share Hypothesis:** {plan['dm_share_hypothesis']}", ""]
    return "\n".join(out)


SPOKEN = re.compile(r"(?m)^- \*\*(❌ Old Reaction|✅ Regulated Response|When|Say):\*\* (.+)$")
# A spoken line can ask another person a question. Matching every question
# containing 'you' refused "Could you tell me when my bike will be ready?".
# Only the measured coaching shape is mechanical evidence here; general
# conversational meaning belongs to the independent critic.
ASKS_THE_READER = re.compile(
    r"\bwhat(?:'s| is) (?:the |your )?(?:smallest|next) (?:action|step)\b[^.!?]*\?",
    re.I,
)


def check_spoken(markdown: str) -> list[str]:
    """Slide 5 and 6 print a condition and a line. Each has to be its own thing.

    These used to print under WHAT YOU SAY and TRY THIS INSTEAD, and a deck went
    out with "You stand up and walk to the hallway." under the first — a stage
    direction about the reader, in quotation marks, under a label claiming they
    said it. Four more like it are on disk.

    The content playbook had already deprecated that pair, in as many words: it
    "puts words in their mouth and leaks viewers who don't say that exact
    sentence", and it asked for a condition the reader can test instead. So the
    labels are "when" and "say" now, and this checks each against its own job.

    WHEN is a condition. "You stand up and walk to the hallway" is a fine one —
    the reader can ask whether they are doing that. It is not speech, so it
    carries no quotation marks.

    SAY is a line somebody says out loud. It may not begin by narrating the
    reader. A coaching prompt is not speech; a question addressed to the other
    person is valid speech and must not be refused merely for containing 'you'.
    """
    problems = []
    for label, line in SPOKEN.findall(markdown):
        plain = re.sub(r"\[\[|\]\]", "", line).strip()
        says = label in ("Say", "✅ Regulated Response")
        if says:
            spoken = plain.strip('"“”')
            if re.match(r"(?i)^you\b", spoken):
                problems.append(f"the Say line starts \"You...\", so it narrates the reader "
                                f"instead of giving them words: {spoken[:56]!r}")
            if ASKS_THE_READER.search(spoken):
                problems.append(f"the Say line asks the reader a question, which is coaching "
                                f"and not a thing anybody says: {spoken[:56]!r}")
        elif plain.startswith(('"', "\u201c")):
            problems.append(f"the When line is in quotation marks, so it reads as something "
                            f"the reader said. It is a condition they can test: {plain[:56]!r}")
    return problems


def check_repeats(markdown: str) -> list[str]:
    """No line of copy may be written twice, and no researcher may be quoted
    into the advice.

    Both shipped. On the kitchen deck, slide 1's hook and slide 2's body were
    the same sentence word for word, and slide 3 printed one sentence under
    both "SOURCE SAYS" and "THIS EXPLAINS" — a reader sees the same line twice
    on one card and stops trusting the page.

    `Primary CTA` was missing from the field list until 2026-09-02, when a deck
    posted with slide 9's two lines byte-identical: "Send this to the friend
    caught at the [[doorway]] past 6pm." twice, one above the other, on the last
    card a reader sees. `Closing thought` was already listed, so the pair was
    half-watched — the duplicate could only be seen from the side that was not
    being read. Both are listed now, and check_last_slide covers the near miss
    this exact-match test cannot.

    The second half is a fault this file caused. Slides 4 to 7 were told to
    reuse slide 3's words, and the cheapest way to satisfy that is to paste the
    citation, so the script slide told a reader to stand in their kitchen and
    say "Walker found that leaving is learned where it worked" out loud. The
    thread is supposed to carry the IDEA forward, never the sentence.
    """
    problems = []
    # Which SLIDE and which FIELD, both times. A run in CI went 6 faults, then
    # 2, then 1, then stalled at 1 for three attempts: the model was told a line
    # appeared twice and not where either copy was, so it had nowhere to look.
    slide = 0
    seen: dict[str, list[str]] = {}
    for line in markdown.splitlines():
        heading = re.match(r"^### Slide (\d+)", line)
        if heading:
            slide = int(heading.group(1))
            continue
        field = re.match(r"^- \*\*(H1|H2|Body|Source Claim|What This Explains Here|"
                         r"❌ Old Reaction|✅ Regulated Response|When|Say|Callout|Primary CTA|"
                         r"Closing thought)"
                         r":\*\* (.+)$", line)
        if not field:
            continue
        key = re.sub(r"[^a-z0-9 ]", "", field.group(2).lower()).strip()
        if len(key.split()) < 4:
            continue
        seen.setdefault(key, []).append(f"slide {slide}'s {field.group(1)}")
    for key, places in seen.items():
        if len(places) > 1:
            problems.append(f"{' and '.join(places)} are the same line: {key[:52]!r}. "
                            f"Keep one, and write the other from scratch")

    # Only the lines a reader is told to SAY. Naming the researcher elsewhere is
    # ordinary and every hand-written deck does it, in the alt text and in
    # passing. Putting them inside a spoken script is not: "say out loud, Walker
    # found that leaving is learned where it worked" is not a thing a person
    # says in their own kitchen.
    author = re.search(r"(?m)^- \*\*Source:\*\* — ([^,]+),", markdown)
    if author:
        surname = author.group(1).strip().split()[-1].lower()
        spoken = re.findall(r"(?m)^- \*\*(?:Say|❌ Old Reaction|✅ Regulated Response):\*\* (.+)$",
                            markdown)
        if any(surname in line.lower() for line in spoken):
            problems.append(f"a script tells the reader to say {surname.title()}'s name out "
                            f"loud. The researcher is credited on slide 3; the words a person "
                            f"says are their own")
    return problems


# Slide 9 is the last thing a reader sees and it has two lines with two jobs:
# the CTA asks for the share, the closing thought is what they take away. On
# 2026-09-02 they were the same sentence, so the card asked twice and gave
# nothing — and check_repeats could not see it, because `Primary CTA` was not in
# its field list. It is now, but exact matching only catches the exact case; a
# closing thought that rewords the CTA is the same empty card.
#
# Measured on all ten decks, word overlap between the two lines: the nine that
# read acceptably score 0.00, 0.00, 0.00, 0.04, 0.05, 0.05, 0.05, 0.11, 0.13.
# The 2026-09-02 deck scores 1.00. There is no data anywhere between 0.13 and
# 1.00, so the cap goes at the middle of that emptiness rather than just above
# the highest passing deck.
LAST_SLIDE_SAME = 0.5


def check_last_slide(markdown: str) -> list[str]:
    """The CTA and the closing thought may not be the same thought twice."""
    cta = re.search(r"(?m)^- \*\*Primary CTA:\*\* (.+)$", markdown)
    closing = re.search(r"(?m)^- \*\*Closing thought:\*\* (.+)$", markdown)
    if not (cta and closing):
        return []

    def bag(text: str) -> set[str]:
        # Accents are ours and a tag is a routing label, so the brackets and the
        # hash come off before the words are compared — otherwise "[[doorway]]"
        # and "doorway" would read as two different words and hide a repeat.
        return set(re.findall(r"[a-z']+", re.sub(r"[\[\]#]", " ", text.lower())))

    a, b = bag(cta.group(1)), bag(closing.group(1))
    if not (a and b):
        return []
    overlap = len(a & b) / len(a | b)
    if overlap <= LAST_SLIDE_SAME:
        return []
    return [f"slide 9's CTA and closing thought are the same thought "
            f"({overlap:.0%} of the words are shared). The CTA asks the reader to "
            f"send it to someone; the closing thought is what they keep. Write the "
            f"closing thought about the reader, not about sending"]

# Words a dictionary will not know and we use on purpose: the handle, British
# spellings, and the vocabulary of this particular subject. Grown by running the
# check against decks we already accept, never by relaxing it.
KNOWN_WORDS = {
    "suresilly", "silly",
    # British spellings. A US dictionary calls each of these a mistake.
    "pyjamas", "neighbour", "neighbours", "colour", "colours", "realise",
    "realised", "apologise", "apologised", "organise", "organised",
    "recognise", "recognised", "practising", "travelling", "cancelled",
    "favourite", "behaviour", "behaviours", "labelled", "modelling",
    # The subject.
    "overthinking", "overthink", "rehearsing", "reframe", "reframing",
    "self", "worth", "bandwidth", "doomscroll", "doomscrolling", "hypervigilance",
    "dysregulation", "co", "regulate", "regulating", "unspoken", "unfinished",
    "unanswered", "unread", "unsent", "unmade", "unopened", "outsized",
}
WORD = re.compile(r"[A-Za-z][A-Za-z']{2,}")


def check_spelling(markdown: str) -> list[str]:
    """Words that are not words.

    A deck that scored 82 and would have posted carried "you decid to open it"
    and "pick your line befor the neighbor knocks". Two letters missing, on a
    public account, and nothing in thirty-odd gates was looking.

    Deliberately quiet about anything it is unsure of. The dictionary does not
    know "pyjamas" either, and a speller that blocks a deck for British English
    is worse than no speller. It reports a word only when the dictionary has a
    correction one edit away, which is what a typo is.
    """
    try:
        from spellchecker import SpellChecker
    except ImportError:
        return []                       # not installed here, and not worth failing over

    text = "\n".join(re.findall(r"(?m)^- \*\*[^:]+:\*\* (.+)$", markdown))
    text += "\n" + "\n".join(re.findall(r"(?m)^\s+[•·]\s+(.+)$", markdown))
    text = re.sub(r"\[\[|\]\]|\[|\]", " ", text)

    # The citation line is written by code, from a verified allowlist. Every
    # word in it — Porges, Nolen-Hoeksema, the book title — is correct by
    # construction, and a dictionary calls each one a mistake.
    source = " ".join(re.findall(r"(?m)^- \*\*Source(?: Claim)?:\*\* (.+)$", markdown))
    from_source = {w.lower() for w in WORD.findall(source)}

    speller = SpellChecker()
    seen, problems = set(), []
    for word in WORD.findall(text):
        low = word.lower().strip("'")
        if low in KNOWN_WORDS or low in from_source or low in seen \
                or not speller.unknown([low]):
            continue
        seen.add(low)
        fix = speller.correction(low)
        # One edit away means somebody dropped a letter. Further than that and
        # it is a word this dictionary has not heard of, which is not our
        # problem to solve at eight in the evening.
        if fix and fix != low and _edits(low, fix) == 1:
            problems.append(f"{word!r} is not a word. Did you mean {fix!r}?")
    return problems


def _edits(a: str, b: str) -> int:
    """Levenshtein distance, capped where it stops mattering."""
    if abs(len(a) - len(b)) > 2:
        return 3
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def verify_draft(markdown: str, moment_anchors: set[str] | None = None,
                 pattern_name: str = "") -> list[str]:
    """Every complaint about an assembled deck, from every gate that applies.

    Run together rather than one at a time because a repair call costs the same
    whether it fixes one fault or six, and fixing them one per round lets an
    early repair break a later gate.
    """
    import tempfile

    import audit_copy
    import coherence
    import render

    problems = check_accents(markdown)
    problems += check_leak(markdown)
    problems += check_repeats(markdown)
    problems += check_last_slide(markdown)
    problems += check_spoken(markdown)
    problems += check_spelling(markdown)
    problems += check_mascots(re.findall(r"(?m)^- \*\*Mascot:\*\* (.+)$", markdown))

    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(markdown)
        path = Path(handle.name)
    try:
        problems += audit_copy.audit(path)
        slides = render.parse_markdown(path)
        keys = ("h1", "h2", "body", "source_claim", "source_translation", "source_explains",
                "old_reaction", "new_reaction", "closing", "cta1", "callout")
        problems += coherence.check(
            slides,
            lambda s: " ".join([str(s[k]) for k in keys if k in s] + s.get("bullets", [])),
            moment_anchors,
        )
    finally:
        path.unlink(missing_ok=True)
    return list(dict.fromkeys(problems))


def hard_faults(markdown: str) -> list[str]:
    """The faults in verify_draft that a human may not stand in for.

    The owner can override a copy-craft gate — a hard word, a subtitle that
    repeats the headline, a CTA aimed at nobody. Those are matters of taste that
    a person looking at the deck is better placed to judge than a regex.

    These two are not taste.

      check_leak      the draft copied the prompt (invariant 20). Five of seven
                      published decks carried a run of words lifted from their
                      own instructions, including a sentence the prompt quotes
                      in order to forbid it. A human saying "post it anyway"
                      cannot make that stop being plagiarised from ourselves.
      check_mascots   a brief asks for lettering in the artwork (invariants 3,
                      28). It is refused here, before any art is drawn, and
                      again at render by cutout.assert_no_text. Overriding this
                      one would put text on the mascot.

    Everything else genuinely dangerous is out of reach of an override already,
    because it runs somewhere else entirely: the citation is proved in
    bibliography before the draft loop starts, the safety screen runs at moment
    selection, novelty runs in compose, the two claim locks run before drafting,
    and the pixel gates run at render. So this list is short by construction —
    it is only the non-craft checks that happen to live INSIDE this loop.
    """
    return check_leak(markdown) + check_mascots(
        re.findall(r"(?m)^- \*\*Mascot:\*\* (.+)$", markdown))


def write_deck(moment: str, topic: str, title: str, pattern: str, pillar: str,
               moment_anchors: set[str] | None = None,
               term: str = "",
               allow_faults: bool = False, review_draft: bool = False) -> tuple[str, dict, dict, str, list[str]]:
    """Plan, draft, assemble. Returns (markdown, plan, axes, who wrote it, faults).

    The last element is the list of copy-craft faults the deck still carries. It
    is EMPTY on every ordinary run, because an ordinary run does not return a
    deck that has any. It is populated only under `allow_faults`, and then it is
    what the owner has to be shown before they approve the deck.

    `allow_faults` is the override the owner types as `force` in Telegram. It
    returns the best draft the loop reached instead of refusing — but only after
    hard_faults() comes back empty, so a draft that copied the prompt or asked
    for lettering in the artwork still refuses, exactly as it does without the
    flag. Read hard_faults for why those two and nothing else.

    An overridden deck is HELD, never posted by the run that built it. Invariant
    4 still holds for everything a gate protects on its own; what changed is that
    the owner may stand in for a matter of taste, once, by name, into a deck a
    second reply has to release.

    The provider is returned because the critic must not be the vendor that
    wrote the deck, and until now the caller assumed Gemini always did. When
    Gemini was exhausted and Groq wrote instead, the critic was told Gemini had
    written it, chose Groq as the independent reviewer, and Groq reviewed its
    own work. Silently, which is the worst way for that rule to fail.

    Two calls in the ordinary case. The plan is validated before the draft is
    paid for, and the citation line and claim are substituted here rather than
    written, so the one thing this page cannot afford to get wrong is not
    something a model is able to get wrong.
    """
    if review_draft:
        planned = plan_deck(moment, topic, term=term, review_plan=True)
        # Test and extension callers written before plan notes return the
        # original three values. Treat that as a clean outline.
        plan, axes, _ = planned[:3]
        plan_notes = planned[3] if len(planned) > 3 else []
    else:
        plan, axes, _ = plan_deck(moment, topic, term=term)
        plan_notes = []
    citation = load_citations()[plan["citation_id"]]
    # A second boundary protects against a changed pool and applies to force.
    bibliography.require_claim_support(citation, plan["claim_index"])
    claim = citation["claims"][plan["claim_index"]]
    hook = (best_hook(plan, plan["scene_token"], True) if plan_notes
            else best_hook(plan, plan["scene_token"]))

    # The scene is handed to the model because a gate has always enforced it and
    # nothing ever stated it. The draft was rejected for naming a kitchen by a
    # rule the model was never shown, then repaired one stray word at a time
    # across three attempts. Saying it once up front is cheaper and it works.
    scene = ", ".join(sorted(moment_anchors)) if moment_anchors else "(none recorded)"

    # The checker's own vocabulary, handed over rather than described. Telling a
    # model to "connect back to slide 3" failed in every run; telling it which
    # words count is the same fix that worked for the scene token.
    thread = ", ".join(sorted(coherence.content(claim))[:24])

    # Put the deck's actual name into the field description, so the rule is
    # sitting next to the box the model is filling in rather than in a wall of
    # prose above it.
    name = plan.get("pattern_name", "").strip()
    schema = json.loads(json.dumps(DRAFT_SCHEMA))

    # Same treatment for the other two rules that stall a draft. Both were
    # stated in the system prompt and both were missed for five attempts
    # running; put on the field, with this deck's own words in them, they are
    # sitting next to the box being filled in.
    if scene and moment_anchors:
        schema["properties"]["cost"]["properties"]["body"]["description"] = (
            f"Slide 2. Instagram re-serves a carousel starting HERE to anyone who did not "
            f"swipe, so it is a second cover and has to work with slide 1 unseen. It MUST "
            f"name one of these out loud: {scene}. A slide 2 with no thing in it is a "
            f"caption, and it is checked. Under 35 WORDS, and shorter is better: it is a "
            f"cover, not a paragraph.")
    if thread:
        for field, slide in (("name", 4), ("script", 5), ("action", 6), ("sustain", 7)):
            spec = schema["properties"].get(field, {})
            target = spec.get("properties", {}).get("body") or spec
            target["description"] = (
                f"Slide {slide}. MUST contain at least one of these words, which come from "
                f"the finding on slide 3: {thread}. One is enough. A slide that shares no "
                f"word with slide 3 is advice for a different deck, and it is checked.")
    user = DRAFT_USER.format(
        plan=json.dumps(plan, indent=2), scene=scene, thread=thread,
        h1=hook["h1"], h2=hook["h2"], claim=claim,
        lens=AXES["lens"][axes["lens"]],
        rehook=AXES["rehook"][axes["rehook"]],
        cheat_shape=AXES["cheat_shape"][axes["cheat_shape"]],
        formula=AXES["formula"][axes["formula"]],
    )
    # Repairs return field edits, never a replacement deck. Code checks the
    # assembled result and removes edits that were not needed to fix a fault.
    import draft_repair

    def assembled(value):
        return assemble(plan, value, hook, citation, claim, value["mascots"],
                        title, pattern, pillar,
                        pick_hashtags(topic, plan.get("pattern_name", "") + moment))

    def checked(value):
        return verify_draft(assembled(value), moment_anchors, plan.get("pattern_name", ""))
    # Repair from the BEST draft so far, never from the last one.
    #
    # A deck has to satisfy about thirty-five rules at once. A draft that breaks
    # three of them is close, and the next attempt used to start from whatever
    # came back last — so it fixed those three, broke two others, and the loop
    # wandered instead of closing. Three attempts did one attempt's work, and
    # from the outside it looked like bad luck.
    #
    # Keeping the best and always repairing from it makes the fault count go
    # down or stay flat. It cannot go up.
    user += ("\nSOURCE LIMIT: The supplied claims are the full factual boundary. "
             "Do not invent a cause, brain effect or benefit for a suggested action. "
             "Offer actions as things to try, with no promised result. "
             "A shared word does not prove a mechanism. Keep scripts to words "
             "the reader can actually say, without directions inside the quotation.")
    attempt_user = user
    best_copy: dict | None = None
    best_problems: list[str] | None = None
    # The assembled markdown of the best attempt, and who wrote it. Kept because
    # the override needs the deck itself, not just the copy dict — assemble() is
    # deterministic, so re-running it would give the same bytes, but keeping the
    # ones that were actually measured means the faults reported to the owner are
    # about the file they are approving.
    best_markdown: str | None = None
    best_wrote: str = ""
    # Seven, not five. With the best draft carried forward the fault count
    # falls steadily — a CI run went 6, 2, 1 and a local one 4, 4, 4, 2, 1 —
    # and both ran out of attempts one short of clean. Each attempt is one call
    # against a hundred a day, and a run that stops at one remaining fault has
    # already paid for the plan, the judge and the composer.
    history: list[int] = []
    signatures = []
    for attempt in range(3 if review_draft else 7):
        if attempt == 0:
            copy, wrote = llm.ask(DRAFT_SYSTEM, attempt_user, schema, temperature=0.6)
            problems = checked(copy)
        else:
            # A mixed-vendor draft would let the independent critic review
            # some of its own text. Repair with the original writer only.
            providers = tuple(p for p in llm.PROVIDERS if p[0] == best_wrote)
            if not providers:
                raise llm.ModelRefused("The original writer is unavailable for field repair.")
            reply, wrote = llm.ask(
                DRAFT_SYSTEM + "\nREPAIR MODE: return only the field edits in the supplied schema, "
                "not a full draft. Each edit must address a listed fault. Leave clean text alone.",
                attempt_user, draft_repair.schema(best_copy, best_problems),
                temperature=0.4, providers=providers)
            copy, problems = draft_repair.apply(best_copy, best_problems, reply, schema, checked)
        markdown = assembled(copy)
        if not problems:
            return markdown, plan, axes, wrote, plan_notes
        history.append(len(problems))
        signatures.append(outcomes.fault_signature(problems))
        if best_problems is None or len(problems) < len(best_problems):
            best_copy, best_problems = copy, problems
            best_markdown, best_wrote = markdown, wrote
        copy, problems = best_copy, best_problems
        if outcomes.unchanged_faults(signatures):
            break
        # The draft itself goes back with the complaints. It said "your previous
        # draft was rejected" and then did not include the draft, so the model
        # wrote a fresh deck every attempt and arrived with a fresh set of
        # faults. Three attempts fixed nothing and looked like bad luck.
        attempt_user = user + (
            "\n\nTHE BEST DRAFT SO FAR, which is nearly right:\n"
            + json.dumps(copy, indent=2)
            + f"\n\nOnly these {len(problems)} things are wrong with it:\n  "
            + json.dumps(draft_repair.fault_map(problems), indent=2)
            + "\n\nReturn only edits to existing text fields. Use the exact field path "
              "and fault from the schema. Every other line stays word for word. "
              "Do not change the plan, source claim, or cover. Fix up to "
            + str(draft_repair.MAX_EDITS) + " fields in this reply."
        )
    # Out of attempts. Two ways this ends.
    #
    # The owner asked for this deck anyway (`force` in Telegram, --force here).
    # Hand back the best draft with its remaining faults attached, so the message
    # they get lists exactly what they are approving. Only after hard_faults()
    # comes back empty: a draft that copied the prompt or asked for lettering in
    # the artwork is refused with or without the flag, because neither of those
    # is a matter of taste a person is better placed to judge.
    if (allow_faults or review_draft) and best_markdown is not None:
        blocking = hard_faults(best_markdown)
        if not blocking:
            return (best_markdown, plan, axes, best_wrote,
                    list(dict.fromkeys(plan_notes + (best_problems or []))))
        # Refused for a different reason than running out of attempts, and the
        # message has to say so — otherwise the owner types `force` again.
        raise Refused(
            "the override cannot apply to this deck: "
            + "; ".join(dict.fromkeys(blocking))[:300]
            + " [these two faults are never overridable]",
            retry=True, history=history)

    # Refused, not llm.ModelRefused — see the matching raise at the end of
    # plan_deck for why. The draft the gates would not pass is an amber ending.
    #
    # The trail is carried on the exception as well as printed in the reason.
    # `retry` is withheld when the count stopped falling, because a fresh moment
    # goes into the same unsatisfiable check — invariant 27's promise that a verb
    # is offered only when it could work, measured rather than assumed.
    shape, _ = outcomes.trajectory(history)
    raise Refused(
        f"{'; '.join(dict.fromkeys(best_problems or []))[:340]} "
        f"[faults per attempt: {', '.join(str(n) for n in history)}]",
        retry=not outcomes.unchanged_faults(signatures), history=history, signatures=signatures)


# ─────────────────────────── checking the draft ────────────────────────────

# A brief may not ask for text, and this is where that is refused — before any
# art is drawn, not after (invariant 3: the pixel gates in cutout.py are the
# second line, and they only see what the drawing actually contains).
#
# The old pattern read `\b(reads?|says?|…|word|letter|…)\b|\d` and let both of
# these through on 2026-09-02, into a published deck:
#
#     Slide 7: A small donkey stands at the doorway, saying 'I'm out'.
#     Slide 8: A small donkey holds a card with the words 'Exit Block' on it.
#
# `\bsays?\b` does not match "saying" and `\bword\b` does not match "words", so
# the two briefs that most plainly ask for lettering were the two it could not
# see. Both slides shipped with printed text on the mascot.
#
# Three signals were added, chosen because they are what an instruction to draw
# text actually looks like: a QUOTED STRING (the words to print, verbatim), the
# phrase THE WORD/WORDS/LETTER(S)/NUMBER(S)/PHRASE/MESSAGE (naming lettering as
# a thing the picture contains), and the -ING speech and writing verbs the old
# stem-anchored list missed. Measured over the 90 briefs in the ten decks on
# disk: it newly catches exactly those two and nothing else.
#
# What it deliberately does NOT match is the bare noun `card` or `list`. An
# earlier draft did, and flagged "a blank white paper card, offering it forward"
# and "holds up three fingers, arranged in an orderly list" — two briefs asking
# for no text at all. A gate that refuses a blank card is a fault nothing can
# answer (invariant 21), so the noun is allowed and only the lettering is not.
MASCOT_TEXT = re.compile(
    r"""
      ['"‘“][^'"’”]{2,}['"’”]
    | \bthe\s+(?:word|words|letter|letters|number|numbers|phrase|message)\b
    | \b(?:saying|reading|writing|labell?ing|spelling|scrawling|inscribing)\b
    | \b(?:reads?|says?|labell?ed|written|text|sign|signage|screen|display|
          caption|slogan|banner|headline|title)\b
    | \bclock\s+face\s+showing\b
    | \bshowing\s+\d
    | \d
    """, re.I | re.X)
MASCOT_FEELING = re.compile(
    r"\b(anxious|sad|happy|distressed|worried|calm|angry|upset|nervous|"
    r"depressed|excited|relaxed|frustrated|lonely|scared|ashamed|hopeful)\b", re.I)

# Words that carry no picture. Function words, plus the four that open literally
# every brief this engine has ever written ("a small donkey" and its "the"), which
# is why they have to come out before two briefs can be compared at all — see
# check_mascots for the measurement.
BRIEF_NOISE = frozenset("""
a an the of in on at to by for with from and or but so as into onto over under
up down out off about is are was were be been being it its his her their this
that these those there here while when then than very just also both each
small donkey donkeys
""".split())
# Where the cap sits, and why it is a named constant: it was measured, so a test
# imports the same number rather than restating it (invariant 25).
MASCOT_SAME = 0.27


def _brief_content(brief: str) -> set[str]:
    """The words in a brief that describe a picture. Nothing else."""
    words = re.findall(r"[a-z]+", brief.lower())
    return {w for w in words if w not in BRIEF_NOISE and len(w) > 2}


# ── Nothing from the prompt may appear in the deck ────────────────────────
#
# The engine's largest single defect, measured rather than suspected. Of the
# seven decks on disk, three carried "the hallway" — the filler in an example
# intention — including one set in a kitchen and one set on a bed. One carried
# "move the cup to the sink", the example script, verbatim. One carried a
# sentence the prompt quotes in full while forbidding it. One printed the
# researcher's surname inside a line the reader was told to say out loud, which
# is the exact failure the prompt describes two paragraphs earlier.
#
# The pattern in every case: an example set on the page's own ground. The three
# VOICE examples have always been about dentists, parking tickets and library
# books, and not one word of them has ever reached a deck. So the rule is not
# "use fewer examples". It is that an on-subject example IS a template, and the
# only reliable enforcement is to count.
#
# Four words, because three matches ordinary English constantly ("a piece of
# your") and five misses "am going in now". Anything the deck is ORDERED to
# reproduce is exempt: the CTA shape and the if-then words are dictated by the
# prompt and are supposed to come back.
LEAK_N = 4
#
# The exemptions are the CTA and nothing else, and each one is load-bearing:
# the prompt DICTATES "Send this to the [kind of person] who [does the thing]",
# so those words coming back is the rule working rather than a model borrowing.
# An exemption that matches no prompt n-gram is a hole with nothing behind it,
# so five speculative ones were deleted rather than left in place.
LEAK_ALLOWED = ("send this to", "this to the", "to the friend")
# A run made only of grammar words cannot identify a copied idea or example.
# "do not have to" caused three identical failed repairs in run 33896861923.
LEAK_GRAMMAR_WORDS = frozenset("a an the i you we they he she it do does did not no have has had to of in on at for and or but is are was were be been am can could will would should may might this that these those your our their its my his her".split())


def _ngrams(text: str, size: int) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def prompt_ngrams(size: int = LEAK_N) -> set[str]:
    """Every run of words the model was shown. Computed, never maintained.

    The four templates are joined RAW, with their placeholders unexpanded, which
    left a hole: the axis instructions arrive through {angle} and {lens} and the
    rest, so the one part of the prompt written to steer the wording was the one
    part the leak gate could not see. Every axis value is added here instead of
    only the drawn one, so the set does not depend on which deck is being
    checked. Measured against all seven published decks: 450 new runs of words,
    zero of them already in use, so nothing that shipped would have been refused.
    """
    shown = " ".join((PLAN_SYSTEM, PLAN_USER, DRAFT_SYSTEM, DRAFT_USER,
                      *(value for axis in AXES.values() for value in axis.values())))
    return _ngrams(shown, size)


def copy_lines(markdown: str) -> list[tuple[str, str]]:
    """Only what a reader sees. Layout names and the citation line are ours."""
    out = []
    for slide in re.split(r"(?m)^### Slide ", markdown)[1:]:
        number = slide.split("\u00b7")[0].strip()
        for label, text in re.findall(
                r"(?m)^-\s+\*\*(?!Layout|Mascot|Badge|Handle|Source:|Source Claim:)"
                r"([^:]+):\*\*\s*(.+)$", slide):
            out.append((f"slide {number} {label}", text))
        for bullet in re.findall(r"(?m)^\s*\u2022\s+(.+)$", slide):
            out.append((f"slide {number} bullet", bullet))
    caption = re.search(r"(?ms)^## Caption\n(.+?)(?=\n---|\n## |\Z)", markdown)
    if caption:
        out.append(("the caption", caption.group(1)))
    return out


def check_leak(markdown: str, shown: set[str] | None = None) -> list[str]:
    """Copy that was lifted out of the prompt instead of written.

    A model under thirty-five simultaneous constraints reaches for the nearest
    text in its context, and the nearest text is whatever the prompt spelled
    out. Counting has no opinion about whether the borrowing was deliberate.
    """
    if shown is None:
        shown = prompt_ngrams()
    problems = []
    for where, text in copy_lines(markdown):
        line = re.sub(r"\[\[|\]\]", "", text)
        for gram in sorted(_ngrams(line, LEAK_N) & shown):
            if any(ok in gram for ok in LEAK_ALLOWED) or set(gram.split()) <= LEAK_GRAMMAR_WORDS:
                continue
            problems.append(
                f"{where} copies {gram!r} straight out of this prompt. That is an example "
                f"showing you a shape, not words you may use. Write the line from the "
                f"moment you were given")
            break
    return problems


def check_mascots(briefs: list[str]) -> list[str]:
    """Mascot briefs are artwork instructions, and two rules are absolute.

    No text in the picture, not a letter and not a digit. A previous pipeline
    sliced a labelled sprite sheet and shipped nine slides with captions printed
    on the donkey, which is why the renderer refuses text in a pose and why this
    checks the brief rather than trusting the wording of a prompt.

    And no emotion words. "Looks anxious" gives the pose picker nothing to match
    on and gives an illustrator nothing to draw; "ears flat, head turned away"
    gives both something.

    Then: nine briefs have to be nine PICTURES. The duplicate check here used to
    compare raw word sets at 0.6, which cannot work, because every brief opens
    "A small donkey" — five words of boilerplate shared by all nine inflate every
    pair towards the threshold from below and the real overlap is invisible under
    it. Measured over the ten decks on disk, raw scores are 0.15–0.59 and the
    ceiling was never once reached, including by the deck whose nine briefs were
    the same donkey in the same doorway nine times.

    Content words only, then, function words and the boilerplate dropped. That
    separates: every deck that shipped acceptably scores 0.11–0.20 and the three
    slop decks score 0.33, 0.33 and 0.40. The cap sits at 0.27, in the middle of
    the widest gap the measurement offers, so it is not tuned to one deck.
    """
    problems = []
    for i, brief in enumerate(briefs, 1):
        found = MASCOT_TEXT.search(brief)
        if found:
            problems.append(f"mascot {i} puts text or a number in the artwork: "
                            f"{found.group(0)!r} in {brief[:60]!r}. Describe what the "
                            f"donkey DOES instead — no quoted words, no lettering")
        feeling = MASCOT_FEELING.search(brief)
        if feeling:
            problems.append(f"mascot {i} names a feeling instead of a posture: {feeling.group(0)!r}")

    content = [_brief_content(b) for b in briefs]
    same = []
    for i in range(len(content)):
        for j in range(i + 1, len(content)):
            a, b = content[i], content[j]
            if not (a and b):
                continue
            overlap = len(a & b) / len(a | b)
            if overlap > MASCOT_SAME:
                same.append((overlap, i + 1, j + 1, sorted(a & b)))
    # ONE fault, however many pairs there are. The bed deck has seven, and seven
    # separate lines all asking for the same thing is how a repair loop stalls:
    # the prompt caps at twelve problems, so seven of them crowd out the other
    # faults, and each attempt fixes one pair and re-reports the rest. Invariant
    # 21's lesson is that a fault has to be answerable, and "these two are the
    # same, and six other pairs are too" is answerable in one pass. The worst
    # pair is named concretely because a complaint with nowhere to look cannot
    # be repaired — the same lesson check_repeats and check_accents both learned.
    if same:
        same.sort(reverse=True)
        _, i, j, shared = same[0]
        crowd = ""
        if len(same) > 1:
            slides = sorted({n for _, x, y, _ in same for n in (x, y)})
            crowd = (f", and {len(same) - 1} other pair(s) among slides "
                     f"{', '.join(str(n) for n in slides)}")
        problems.append(
            f"mascots {i} and {j} describe the same picture — both are about "
            f"{', '.join(shared[:4])}{crowd}. Nine slides need nine different "
            f"things happening: change what the donkey is DOING, not just where "
            f"it is standing")

    # And they may not all begin the same way. Five of the ten decks on disk have
    # all nine briefs opening on the identical three words, which is the shape of
    # a set written by filling a template rather than by imagining nine pictures.
    # A fault has to be answerable (invariant 21) and this one is answerable by
    # rewriting one opening, so it names that as the fix.
    opens = {tuple(b.lower().split()[:3]) for b in briefs if b.split()}
    if len(briefs) > 2 and len(opens) == 1:
        problems.append(
            f"every mascot brief opens {' '.join(next(iter(opens)))!r}. Nine identical "
            f"openings is one picture written nine times — start most of them on the "
            f"donkey's action or on where it is, not all on the same three words")
    return problems


def check_accents(markdown: str) -> list[str]:
    """Every slide needs exactly one accent, and no field may carry two.

    The renderer colours [[the accent]], and a slide without one renders flat
    while a field with two renders as a mess. Neither is something a schema can
    express, so it is checked on the assembled text.

    Which field, and which words. "slide 8 has two accents in one field" ran a
    draft out of all seven attempts: the model was repairing its own JSON, where
    the fault was invisible, because assemble() had normalised every field on
    that slide except the one that actually broke. A complaint that does not say
    where to look cannot be repaired, which is the same lesson check_repeats
    learned.

    Both faults should now be unreachable from model output: assemble() puts
    every line of copy through ensure_accent or no_accent, and the hook gate
    settles slide 1. This stays as the backstop that says so.
    """
    problems = []
    slides = re.split(r"(?m)^### Slide ", markdown)[1:]
    for slide in slides:
        number = slide.split("·")[0].strip()
        fields = re.findall(
            r"(?m)^-\s+\*\*(?!Layout|Mascot|Badge|Handle|Source:)([^:]+):\*\*\s*(.+)$", slide)
        fields += [("bullet", b) for b in re.findall(r"(?m)^\s*•\s+(.+)$", slide)]
        total = sum(len(re.findall(r"\[\[.+?\]\]", text)) for _, text in fields)
        if total == 0:
            problems.append(f"slide {number} has no [[accent]]")
        for label, text in fields:
            for broken in re.findall(r"\w\[\[.+?\]\]|\[\[.+?\]\]\w", text):
                problems.append(
                    f"slide {number}'s {label} line accents half a word ({broken!r}). The "
                    f"renderer colours exactly what is inside the brackets, so this prints "
                    f"as one word broken in two. Wrap the whole word")
            marks = re.findall(r"\[\[.+?\]\]", text)
            if len(marks) > 1:
                problems.append(
                    f"slide {number}'s {label} line has {len(marks)} accents and needs "
                    f"exactly one. Keep one of {', '.join(marks)} and unwrap the rest: "
                    f"{text[:64]!r}")
    return problems
