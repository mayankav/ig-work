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
2,688 combinations, because a model left to pick its own approach converges on
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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import coherence  # noqa: E402
import llm  # noqa: E402
import safety  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CITATIONS_PATH = SKILL_DIR / "references" / "citations.json"
HASHTAGS_PATH = SKILL_DIR / "references" / "hashtags.json"

# ─────────────────────────── the angles ────────────────────────────
#
# Five axes that change what the deck SAYS, not how it is decorated. Combined
# they give 2,688 starting positions, and the planner draws one per run from the
# moment's own fingerprint so the same moment could never be written twice the
# same way. Each value is phrased as an instruction, because a constraint the
# model is told to satisfy changes the writing and a label it is merely shown
# does not.

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


def draw_axes(seed: str) -> dict:
    """Pick one value per axis, deterministically from the moment.

    Deterministic on purpose: the same moment always plans the same way, so a
    rerun reproduces a deck exactly and a reported problem can be looked at
    rather than guessed at. Different moments land in different corners because
    the hash spreads them, not because anything is random.
    """
    digest = hashlib.sha256(seed.encode()).digest()
    chosen = {}
    for i, (axis, options) in enumerate(AXES.items()):
        keys = sorted(options)
        chosen[axis] = keys[digest[i] % len(keys)]
    return chosen


def combinations() -> int:
    total = 1
    for options in AXES.values():
        total *= len(options)
    return total


# ─────────────────────────── citations ────────────────────────────

def load_citations() -> dict:
    data = json.loads(CITATIONS_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["citations"]}


def citations_for(topic: str) -> list[dict]:
    """The sources that fit this subject. The model only ever sees this list."""
    everything = load_citations().values()
    fitting = [c for c in everything if topic in c["pillars"]]
    return fitting or list(everything)


# ─────────────────────────── the plan ────────────────────────────

PLAN_SYSTEM = """You plan a nine-slide Instagram carousel for a page about ordinary
relational psychology. You are planning only. Do not write slide copy yet.

The page sounds like a smart friend who reads the textbooks. Never a therapist,
never a guru, never a brand. Dry, warm, specific. A reader should want to send it
to one person rather than agree with it in public.

WHAT THE READER FEELS, and it is not relief. Relief is calm, and calm does not
travel: the emotions that get a post sent are the ones with a jolt in them —
recognition ("there is a NAME for that?"), being caught out, mild indignation.
Relief is where the deck ENDS, on slide 9. It is not what the deck is built on.

THE NAME IS THE POST. Before the beats, decide what this pattern is CALLED:
a short noun phrase a reader can repeat, search for, and send to somebody with
"this is you". Two or three words. "Waiting mode". "The bird test". "Bowl
washing". Not a sentence, not a feeling, not a diagnosis.

  This is the single biggest thing that decides whether a post travels. A name
  can be looked up, argued with, and used as an accusation, a confession or a
  diagnosis of somebody else. A scene cannot: nobody forwards a stranger's
  evening. The named ideas that spread — waiting mode, the orange peel theory,
  weaponised incompetence — are all somebody putting a handle on a thing
  everybody already did.

THE NINE BEATS, in order, each one earning the next:
  1 hook     the NAME, then one line saying what it is. Not a staged scene.
  2 cost     what it costs. This is served on its own to people who did not
             swipe, so it must work with no slide 1 in front of it.
  3 source   the citation, then ONE sentence connecting it to the name.
             The citation line is written for you and you do not touch it.

             YOUR SENTENCE BEGINS WITH THE NAME. Literally the first words.
             Then say what the finding explains about it, in your own words.
             This is the single fault that stalls more drafts than any other,
             and it is the easiest to avoid: start typing the name.
               claim    "Walker found that keeping the peace becomes automatic."
               yours    "Peace keeping is why the sink still has you at 11pm."
             Copying the claim under a second heading is the fastest way to
             look broken, and it is checked.
  4 name     EXPLAIN the name slide 1 gave. Never coin a second one. A deck
             that posted led with "Execution freeze" and then invented "the
             traction gap" here, so a reader was handed two names and carried
             away neither. One deck, one name; this is where it is unpacked.
  5 script   the words to say, copy-paste, with a [bracket] to fill in.

             These two lines print under WHAT YOU SAY and TRY THIS INSTEAD, so
             they have to be things a person says. Two shapes work: a quoted
             line in the reader's own voice — "Yes of course! So excited!" — or
             an unquoted behaviour — "Sending three rapid follow-up messages to
             fix the vibe." Neither begins by telling the reader what they are
             doing. A deck that posted put "You stand up and walk to the
             hallway." under WHAT YOU SAY, which nobody said.

             And the response is one thing somebody says. Do not append a
             question to it: "I will move the cup to the sink at 11:45pm. What
             is the smallest action you can take?" is a script with a coach
             stapled to the end.
  6 action   one move, with a time and a place named
  7 sustain  what makes it survive tomorrow
  8 cheat    the card they save. It recaps slides 4 to 7 and adds nothing new.
  9 cta      ask them to send it to one specific kind of person

THE PROTOCOL, written FIRST, before any beat. Advice invented to fill slide 6 is
always worse than advice the deck was built around. Every part must be doable in
under two minutes, while anxious, with no app and no googling.

  script     under 20 words, said out loud or sent, and it MUST contain one
             [square bracket] the reader fills in.
             e.g.  The shape only: The [thing] is done. I am going in now.
  intention  MUST be exactly this shape, with a real time and a real place:
             I will [do the thing] at [time] in [place]
             e.g.  The shape only: I will [do it] at [8pm] in [the hallway]
  if_then    MUST contain the words if and then, and name a time or a place
             e.g.  The shape only: If [the trigger], then [the two minute move]
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
  HOOKS. Give at least 4. Each is used on slide 1 exactly as written, so every
  rule here is checked and a hook that breaks one is thrown away.
    h1  at most 12 words. Exactly one [[accent]], wrapping the last stressed
        word. Never open with Why, How to, The reason, What nobody, Most
        people, or Here is.
    h2  at most 7 words. No [[accent]] at all. It says something the h1 did
        NOT, and it never repeats the name — the headline already gave it. A
        deck that posted opened "Execution freeze. You remain anchored to the
        bed even when awake." and put "Execution freeze. Anchored to the bed."
        underneath, which is the same words twice on the only slide most
        people see. "The morning goes while you stand" is a subtitle.
    h1 CONTAINS THE NAME, and one thing a camera could point at. Both. The
    name is what gets sent on; the thing is what makes it a picture rather
    than a slogan. "Peace keeping. You cannot leave the [[sink]] until every
    cup is done" has the name and has the sink.
    Write about what always happens, not about one evening that happened.
    "You" means anybody, in the present. It does not mean one person doing one
    thing at one hour.
      Right:  Bowl washing. You cannot sit down until the counter is [[clear]].
              (11 words. Count them before you return it — every hook in one
               rejected plan ran to 14 and 15, and the cap is 12.)
      Right:  Waiting mode. The whole day gets held for one [[appointment]].
              (11 words.)
      Wrong:  You stood in the kitchen at 11pm washing bowls that were [[clean]].
    The wrong one reads as somebody else's Tuesday. The reader has their own
    kitchen and their own hour, and an invented one competes with the real
    memory and loses. Say the thing that is always true and let them supply
    the evening.
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
  explain through   {lens}
  advice leads with {protocol}
  saved card is     {cheat_shape}
  middle slides     {rehook}

CITATIONS YOU MAY USE. Return one id and the index of the claim you want.
{citations}

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
        # The handle a reader repeats, searches for, and sends to somebody.
        # Two or three words, a noun phrase, never a sentence.
        "pattern_name": {"type": "string", "minLength": 3, "maxLength": 28},
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
            "type": "array", "minItems": 4, "maxItems": 8,
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

BANNED_OPENERS = re.compile(r"^(why|how to|the reason|what nobody|most people|here'?s)\b", re.I)
EARLY_JARGON = ("nervous system", "attachment", "regulation", "regulated", "cortisol",
                "polyvagal", "trauma response", "fawn response", "hypervigilance",
                "emotional flashback", "somatic", "neuroception")
SEESAW = re.compile(r"(?i)\b(it'?s|you'?re|you were|you weren'?t)\s+not\b.*\b(it'?s|you'?re|you were)\b")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", re.sub(r"\[\[|\]\]", " ", text))


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
    if {w.lower() for w in _words(h2)} and \
            {w.lower() for w in _words(h2)} <= {w.lower() for w in _words(h1)}:
        faults.append("h2 only repeats h1. It has to add something")
    if name and name.lower() in h2.lower():
        faults.append(f"h2 says {name!r} again. The headline already named it")
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


def validate_plan(plan: dict, moment: str, topic: str) -> list[str]:
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

    citation = citations.get(plan["citation_id"])
    if not citation:
        problems.append(f"citation {plan['citation_id']!r} is not on the allowlist")
    elif plan["claim_index"] >= len(citation["claims"]):
        problems.append(f"claim {plan['claim_index']} does not exist for {plan['citation_id']}")
    elif topic not in citation["pillars"]:
        problems.append(f"{plan['citation_id']} does not cover {topic}")

    name = plan.get("pattern_name", "").strip()
    if not 1 <= len(name.split()) <= 4:
        problems.append(f"the pattern name is {len(name.split())} words. A handle a reader "
                        f"repeats is two or three: 'waiting mode', 'bowl washing'")
    elif name.rstrip(".").endswith((" is", " are", " you", " it")) or "." in name.rstrip("."):
        problems.append(f"the pattern name {name!r} is a sentence. It has to be a thing "
                        f"with a name, not a claim")
    elif name.lower().strip(" .") in {t.replace("_", " ") for t in safety.TOPICS} | \
            {t.replace("_", "") for t in safety.TOPICS}:
        # The pillar is the shelf this deck sits on, not the thing it names.
        # A deck pinned to the weaker vendor came back with pattern_name
        # "Boundaries" and slide 4 reading "the name of this pattern is
        # boundaries", which teaches nobody anything and is not sendable.
        problems.append(f"the pattern name {name!r} is just the subject. Coin a handle for "
                        f"this particular pattern — 'peace keeping', 'bowl washing', "
                        f"'waiting mode' — not the shelf it sits on")
    else:
        # It has to be on slide 1. A name introduced later is a name nobody
        # carries away, and slide 1 is the only slide most people see.
        first = f"{beats[0]['beat']} {' '.join(h['h1'] for h in plan['hooks'])}".lower()
        if name.lower() not in first:
            problems.append(f"the pattern name {name!r} is missing from slide 1. Lead with "
                            f"it: it is the thing a reader repeats and sends on")

        # Slide 4's whole job is to explain the name slide 1 gave. A deck that
        # posted led with "Execution freeze" and then coined "the traction gap"
        # four slides later, so a reader was handed two handles and carried
        # away neither. One deck, one name.
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
        problems.append("the scene token is missing from slide 1")
    # The cheat sheet must carry the moment too, but a beat is a description of a
    # slide rather than its copy, and demanding the literal token inside a
    # description rejects perfectly good plans. The coherence gate enforces it on
    # the finished slide, which is where it can be enforced honestly.

    protocol = plan["protocol"]
    if "[" not in protocol["script"] or "]" not in protocol["script"]:
        problems.append("the script has no [bracket] to fill in")
    if not re.search(r"\bat\b.*\bin\b|\bin\b.*\bat\b", protocol["intention"], re.I):
        problems.append("the intention names no time and place")
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
    for term in EARLY_JARGON:
        if term in early:
            problems.append(f"diagnosis word before slide 3: {term}")

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


def best_hook(plan: dict, token: str = "") -> dict:
    """The best usable hook, which is not simply the shortest one.

    A cover has to be one breath, so length matters. But "The maths started" is
    short and says nothing a camera could point at. Naming something concrete
    comes first, then brevity.
    """
    def rank(hook: dict) -> tuple:
        h1 = hook["h1"]
        has_token = bool(token) and token.lower() in h1.lower()
        return (not has_token, not bool(CONCRETE.search(h1)), len(_words(h1)))

    usable = [h for h in plan["hooks"] if hook_ok(h)]
    return sorted(usable or plan["hooks"], key=rank)[0]


def plan_deck(moment: str, topic: str) -> tuple[dict, dict, str]:
    """Plan one deck. Returns (plan, axes, provider), or raises.

    Two attempts. A plan that fails its own chain check twice is a signal about
    the moment, not about the model, and the feed has thousands more moments.
    """
    axes = draw_axes(moment)
    options = citations_for(topic)
    listing = "\n".join(
        f"  {c['id']}\n      claim 0: {c['claims'][0]}\n      claim 1: {c['claims'][1]}"
        for c in options
    )
    # The words the coherence gate will actually recognise, taken from the gate
    # itself rather than guessed. The plan used to invent a scene token from the
    # moment's wording — "doorway" for a moment about a door — and slide 1 was
    # then refused for naming nothing filmable, by a check reading a different
    # vocabulary. One list, taken from the checker, given to the writer.
    things = sorted(coherence.anchors_in(moment))
    user = PLAN_USER.format(
        moment=moment, topic=topic.replace("_", " "),
        things=", ".join(things) if things else "(nothing recognised)",
        angle=AXES["angle"][axes["angle"]],
        lens=AXES["lens"][axes["lens"]],
        protocol=AXES["protocol"][axes["protocol"]],
        cheat_shape=AXES["cheat_shape"][axes["cheat_shape"]],
        rehook=AXES["rehook"][axes["rehook"]],
        citations=listing,
    )

    # Repair from the BEST plan so far, the same as the draft loop. Starting
    # each attempt from whatever came back last lets a fixed fault come back.
    attempt_user = user
    best_plan: dict | None = None
    best_problems: list[str] | None = None
    # A closed list, not free text. The ids are known before the call, so there
    # is no reason a model should be able to type one.
    plan_schema = json.loads(json.dumps(PLAN_SCHEMA))
    plan_schema["properties"]["citation_id"] = {
        "type": "string", "enum": [c["id"] for c in options],
        "description": "Exactly one of these, on its own. Not 'id=' and not the title."}

    history: list[int] = []
    for attempt in range(4):
        plan, provider = llm.ask(PLAN_SYSTEM, attempt_user, plan_schema,
                                 temperature=1.0 if attempt == 0 else 0.7)
        problems = validate_plan(plan, moment, topic)
        if not problems:
            return plan, axes, provider
        history.append(len(problems))
        if best_problems is None or len(problems) < len(best_problems):
            best_plan, best_problems = plan, problems
        plan, problems = best_plan, best_problems
        # The plan goes back with the complaints, and it is the BEST plan, not
        # the last one. Retrying blind asks the same model the same question and
        # gets the same answer; retrying from a worse plan loses ground already
        # won. Temperature drops too: this is no longer a search for an angle,
        # it is a correction to one.
        attempt_user = user + (
            "\n\nTHE BEST PLAN SO FAR, which is nearly right:\n"
            + json.dumps(plan, indent=2)
            + f"\n\nOnly these {len(problems)} things are wrong with it:\n  "
            + "\n  ".join(dict.fromkeys(problems))
            + "\n\nReturn that plan again with exactly those fixed and everything else "
              "left as it is."
        )
    raise llm.ModelRefused(
        f"{'; '.join(dict.fromkeys(best_problems or []))[:340]} "
        f"[faults per attempt: {', '.join(str(n) for n in history)}]")


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

These examples are deliberately about subjects this page never covers. Copy the
rhythm. Never copy the subject.
  "You have had the dentist's number in your phone for nine days. You have opened
   the contact. You have not pressed call."
  "The parking ticket is on the counter. You walk past it. You have developed a
   small route around the counter."
  "The library book is four weeks late. Returning it now feels like a confession,
   so you keep it, which is worse, which you know."

MARKUP, the rule that gets broken most, so read it twice

  EVERY line of copy you write needs exactly one [[accent]] around its most
  important word. Not most lines. Every line. The renderer colours that word,
  and a line without one prints flat and grey.

  Right:  "You searched for it for [[thirty]] minutes."
  Right:  "I am not looking again until [[morning]]."
  Wrong:  "You searched for it for thirty minutes."      no accent
  Wrong:  "You [[searched]] for it for [[thirty]] minutes."   two accents

  This applies to every h2, every body, every old and new line, every bullet,
  every callout, the CTA and the closing thought. Nine slides, every field.

  [bracket] marks a blank the reader fills in, inside a script. Not the same
  thing, and a field can carry both.

HARD RULES, each one checked by code after you finish
  No em dash or en dash. Use a period or a comma.
  Never write "it is not X, it is Y" or "you are not X, you are Y". Say what it IS.
  No emoji. No hashtags inside slides. No slide numbers. No handle inside copy.
  Never open slide 1 with Why, How to, The reason, What nobody, Most people, Here is.
  No diagnosis words on slides 1 or 2: nervous system, attachment, regulation,
  regulated, cortisol, polyvagal, trauma response, fawn response, hypervigilance,
  emotional flashback, somatic, neuroception.
  Never tell the reader they have a condition. A noun for a pattern is fine.
  Never name an author, a book, a study or a year. That line is added for you.
  Slide 2 must work alone as a cover, for someone who never saw slide 1.
  Slide 8 adds nothing new. It recaps slides 4 to 7 only.
  Bodies stay under 220 characters. The closing thought stays under 180.

THE CTA, slide 9. This exact shape, and nothing longer than 11 words:
    Send this to the [kind of person] who [does the thing in the moment].
  e.g.  Send this to the friend who loses their [[keys]] every morning.
  It must contain the word "send" or "share", and name who. Not "share if you
  relate", not "tag someone". A named kind of person.

SLIDES 1 AND 2 EACH NAME A THING. Not a feeling, not a pattern — a thing in the
room, or the hour on the clock. The moment hands you a door, a coat, a kettle,
11pm: put one of them on slide 1 and one on slide 2.

  Slide 1 without a thing is a caption, and it is checked.
  Slide 2 is served on its own to people who never saw slide 1, so it has to
  set its own scene rather than refer back to one.

  Weak, and refused:  "You said yes when you meant no."
  Right:              "You said it at the [[door]], still in your coat."

THE PROTOCOL GOES ON THE SLIDES. The plan hands you an "intention" line and an
"if_then" line, already written. One of slides 4 to 7 must carry the intention
almost word for word, keeping its time and its place, and another must carry the
if-then. A reader has to be able to do the thing tomorrow without looking
anything up, and code checks that one of those two shapes survived:

    I will [do the thing] at [time] in [place]
    If [the trigger], then [the response]

Reword them only enough to fit the slide. Do not summarise them away.

THE THREAD, slides 4 to 7. This is the rule drafts fail most often, and it is
never obvious from a single slide.

  Slide 3 names the mechanism. EVERY ONE of slides 4, 5, 6 and 7 has to use at
  least one word from THE THREAD WORDS listed below, or from your own slide 3
  wording. One word is enough. All four slides need one, not three of them.

  Carry the IDEA, never the sentence. Do not paste the claim into a slide and do
  not name the researcher again — they are credited on slide 3 and nowhere else.
  A deck once told its reader to stand in the kitchen and say "Walker found that
  leaving is learned where it worked" out loud, which is not a thing a person
  says. Take the word. Leave the citation.

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

  1  The name, and what it costs. ONE sentence, and it has to work alone,
     because Instagram hides everything after about 125 characters.
  2  Two or three sentences saying something the slides did NOT say. Where
     this shows up in an ordinary week, or what it is usually mistaken for.
     This is the paragraph that earns the caption its space.
  3  Who this is not about. One line that lets somebody off: "This is not a
     discipline problem and it was never laziness."
  4  Ask them to save it. "Save this for the next 6am you spend standing by
     the bed."

  Never a summary of the slides. Somebody reading the caption has already seen
  them, or is deciding whether to.

  Asking for a save moves saves by about 90 percent, and asking for a like
  slightly lowers likes, so ask for the save and never for the like. Slide 9
  already asks them to send it, and one post gets one action out of a person,
  so there are exactly two asks in the whole deck: send on the slide, save in
  the caption.

You do not write hashtags. Code picks them from a vetted list, the same way it
picks the citation, because a model asked for a label produces something
label-shaped: a deck went out tagged #transitionfreeze, a name we had coined an
hour earlier that nobody has ever searched for.

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
  moment involves a phone, so the brief says "looking at the screen". A picture
  of a screen is a picture of writing. Show the phone face down on the duvet, or
  held against the chest, or being pushed away — the object, never its display.
  Same for a clock: the donkey turns it to the wall, it never shows a time.

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
                     "description": "Slide 3's last line. MUST BEGIN with the pattern name "
                                    "from the plan, word for word, then say what the finding "
                                    "explains about it. Never restate the source claim."},
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
                                 "callout": {"type": "string", "maxLength": 140},
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
                    "description": "60 to 120 words in four short paragraphs: the name and "
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
        f"- **❌ Old Reaction:** \"{ensure_accent(copy['script']['old'])}\"",
        f"- **✅ Regulated Response:** \"{ensure_accent(copy['script']['new'])}\"",
        f"- **Mascot:** {mascots[4]}",
        "",
        "### Slide 6 · Value Step 3",
        f"- **Layout:** {LAYOUTS['action']}",
        f"- **H2:** {ensure_accent(copy['action']['h2'])}",
        f"- **❌ Old Reaction:** \"{ensure_accent(copy['action']['old'])}\"",
        f"- **✅ Regulated Response:** \"{ensure_accent(copy['action']['new'])}\"",
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
        f"- **Callout:** {copy['cheat']['callout']}",
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
        copy["caption"].strip(),
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


SPOKEN = re.compile(r"(?m)^- \*\*(❌ Old Reaction|✅ Regulated Response):\*\* (.+)$")
ASKS_THE_READER = re.compile(r"[^.!?]*\byou(?:r|rself)?\b[^.!?]*\?")


def check_spoken(markdown: str) -> list[str]:
    """Slides 5 and 6 print these under "WHAT YOU SAY" and "TRY THIS INSTEAD".

    So they have to be things a person says. A deck that posted put
    "You stand up and walk to the hallway." under WHAT YOU SAY, which is not
    something the reader said — it is a stage direction about them, in quotes.
    Another said "You stare at the ceiling and wait for a feeling that will not
    come."

    The hand-written decks show the two shapes that work: a quoted line in the
    reader's own voice ("Yes of course! So excited!") or an unquoted behaviour
    ("Sending three rapid follow-up messages to fix the vibe."). Neither starts
    by telling the reader what they are doing.
    """
    problems = []
    for label, line in SPOKEN.findall(markdown):
        plain = re.sub(r"\[\[|\]\]", "", line).strip().strip('"“”')
        if re.match(r"(?i)^you\b", plain):
            problems.append(f"{label} starts \"You...\", so it is a description of the "
                            f"reader and not a thing they say: {plain[:56]!r}")
        # Only the response. An old reaction may well ask somebody a question —
        # "Did I do something to upset you?" is exactly the reflex being named.
        if "Regulated" in label and ASKS_THE_READER.search(plain):
            problems.append(f"the response asks the reader a question, so it is coaching "
                            f"and not a line anybody says out loud: {plain[:56]!r}")
    return problems


def check_repeats(markdown: str) -> list[str]:
    """No line of copy may be written twice, and no researcher may be quoted
    into the advice.

    Both shipped. On the kitchen deck, slide 1's hook and slide 2's body were
    the same sentence word for word, and slide 3 printed one sentence under
    both "SOURCE SAYS" and "THIS EXPLAINS" — a reader sees the same line twice
    on one card and stops trusting the page.

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
                         r"❌ Old Reaction|✅ Regulated Response|Callout|Closing thought)"
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
        spoken = re.findall(r"(?m)^- \*\*(?:❌ Old Reaction|✅ Regulated Response):\*\* (.+)$",
                            markdown)
        if any(surname in line.lower() for line in spoken):
            problems.append(f"a script tells the reader to say {surname.title()}'s name out "
                            f"loud. The researcher is credited on slide 3; the words a person "
                            f"says are their own")
    return problems


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
    problems += check_repeats(markdown)
    problems += check_spoken(markdown)
    problems += check_spelling(markdown)
    explains = re.search(r"(?m)^- \*\*What This Explains Here:\*\* (.+)$", markdown)
    if explains and pattern_name and pattern_name.lower() not in explains.group(1).lower():
        problems.append(f"slide 3's last line does not mention {pattern_name!r}. Its whole "
                        f"job is to connect the finding to the name, and without the name "
                        f"it can only repeat the finding")
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


def write_deck(moment: str, topic: str, title: str, pattern: str, pillar: str,
               moment_anchors: set[str] | None = None) -> tuple[str, dict, dict, str]:
    """Plan, draft, assemble. Returns (markdown, plan, axes, who wrote it).

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
    plan, axes, _ = plan_deck(moment, topic)
    citation = load_citations()[plan["citation_id"]]
    claim = citation["claims"][plan["claim_index"]]
    hook = best_hook(plan, plan["scene_token"])

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
    if name:
        schema["properties"]["explains"]["description"] = (
            f'Slide 3\'s last line. MUST BEGIN with the exact words "{name}", then say what '
            f'the finding explains about {name}. Never restate the source claim.')

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
    )
    # The whole draft is rewritten on a repair rather than the failing slides
    # being spliced back in. Splicing saves a few thousand tokens and costs the
    # guarantee that the deck still reads as one piece; at two posts a day the
    # tokens are not worth the risk. The plan does not change, so the argument
    # cannot drift between attempts.
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
    attempt_user = user
    best_copy: dict | None = None
    best_problems: list[str] | None = None
    # Seven, not five. With the best draft carried forward the fault count
    # falls steadily — a CI run went 6, 2, 1 and a local one 4, 4, 4, 2, 1 —
    # and both ran out of attempts one short of clean. Each attempt is one call
    # against a hundred a day, and a run that stops at one remaining fault has
    # already paid for the plan, the judge and the composer.
    history: list[int] = []
    for attempt in range(7):
        copy, wrote = llm.ask(DRAFT_SYSTEM, attempt_user, schema,
                              temperature=0.6 if attempt == 0 else 0.4)
        markdown = assemble(plan, copy, hook, citation, claim, copy["mascots"],
                            title, pattern, pillar,
                            pick_hashtags(topic, plan.get("pattern_name", "") + moment))
        problems = verify_draft(markdown, moment_anchors, plan.get("pattern_name", ""))
        if not problems:
            return markdown, plan, axes, wrote
        history.append(len(problems))
        if best_problems is None or len(problems) < len(best_problems):
            best_copy, best_problems = copy, problems
        copy, problems = best_copy, best_problems
        # The draft itself goes back with the complaints. It said "your previous
        # draft was rejected" and then did not include the draft, so the model
        # wrote a fresh deck every attempt and arrived with a fresh set of
        # faults. Three attempts fixed nothing and looked like bad luck.
        attempt_user = user + (
            "\n\nTHE BEST DRAFT SO FAR, which is nearly right:\n"
            + json.dumps(copy, indent=2)
            + f"\n\nOnly these {len(problems)} things are wrong with it:\n  "
            + "\n  ".join(list(dict.fromkeys(problems))[:12])
            + "\n\nReturn that draft again with exactly those fixed. Every other line "
              "stays word for word as it is above. Do not improve anything you were not "
              "asked about — a line you rewrite unasked is a new fault."
        )
    raise llm.ModelRefused(
        f"{'; '.join(dict.fromkeys(best_problems or []))[:340]} "
        f"[faults per attempt: {', '.join(str(n) for n in history)}]")


# ─────────────────────────── checking the draft ────────────────────────────

MASCOT_TEXT = re.compile(
    r"\b(reads?|says?|labell?ed|written|text|sign|screen|display|caption|number|"
    r"word|letter|clock face showing|showing \d)\b|\d", re.I)
MASCOT_FEELING = re.compile(
    r"\b(anxious|sad|happy|distressed|worried|calm|angry|upset|nervous|"
    r"depressed|excited|relaxed|frustrated|lonely|scared|ashamed|hopeful)\b", re.I)


def check_mascots(briefs: list[str]) -> list[str]:
    """Mascot briefs are artwork instructions, and two rules are absolute.

    No text in the picture, not a letter and not a digit. A previous pipeline
    sliced a labelled sprite sheet and shipped nine slides with captions printed
    on the donkey, which is why the renderer refuses text in a pose and why this
    checks the brief rather than trusting the wording of a prompt.

    And no emotion words. "Looks anxious" gives the pose picker nothing to match
    on and gives an illustrator nothing to draw; "ears flat, head turned away"
    gives both something.
    """
    problems = []
    for i, brief in enumerate(briefs, 1):
        found = MASCOT_TEXT.search(brief)
        if found:
            problems.append(f"mascot {i} puts text or a number in the artwork: "
                            f"{found.group(0)!r} in {brief[:60]!r}")
        feeling = MASCOT_FEELING.search(brief)
        if feeling:
            problems.append(f"mascot {i} names a feeling instead of a posture: {feeling.group(0)!r}")

    lowered = [re.sub(r"[^a-z ]", " ", b.lower()) for b in briefs]
    for i in range(len(lowered)):
        for j in range(i + 1, len(lowered)):
            a, b = set(lowered[i].split()), set(lowered[j].split())
            if a and b and len(a & b) / len(a | b) > 0.6:
                problems.append(f"mascots {i + 1} and {j + 1} describe the same picture")
    return problems


def check_accents(markdown: str) -> list[str]:
    """Every slide needs exactly one accent, and no field may carry two.

    The renderer colours [[the accent]], and a slide without one renders flat
    while a field with two renders as a mess. Neither is something a schema can
    express, so it is checked on the assembled text.
    """
    problems = []
    slides = re.split(r"(?m)^### Slide ", markdown)[1:]
    for slide in slides:
        number = slide.split("·")[0].strip()
        fields = re.findall(r"(?m)^-\s+\*\*(?!Layout|Mascot|Badge|Handle|Source:)[^:]+:\*\*\s*(.+)$", slide)
        fields += re.findall(r"(?m)^\s*•\s+(.+)$", slide)
        total = sum(len(re.findall(r"\[\[.+?\]\]", f)) for f in fields)
        if total == 0:
            problems.append(f"slide {number} has no [[accent]]")
        for field in fields:
            if len(re.findall(r"\[\[.+?\]\]", field)) > 1:
                problems.append(f"slide {number} has two accents in one field")
                break
    return problems
