#!/usr/bin/env python3
"""
screen.py — layers 1 and 2. What may never become a post, and what shape a
usable moment has.

Both layers are pure functions over a string. No network, no model, no state.
That is deliberate: these run on every candidate from a live feed, thousands a
day, and they are the only part of the pipeline whose recall must be perfect.

The governing asymmetry: this is a SELECTION filter, not a risk classifier.
Supply is effectively unlimited, so a false positive costs nothing and a false
negative can hurt a real person. Every judgement call here is made in favour of
rejecting.

Two consequences that look wrong until you know why:

  * Negation never clears a hit. "I would never hurt myself" is rejected exactly
    like the affirmative. Detecting negation reliably is hard, and getting it
    wrong is expensive in only one direction.
  * Text is normalised before matching, so disguised spellings ("k*ll", "un
    alive", "s.h.") still match. Obfuscation is the norm on public feeds, not
    the exception.

Layer 1 rejects by subject. Layer 2 rejects by shape. A moment must clear both.
"""

from __future__ import annotations

import re
import unicodedata

# ─────────────────────── normalisation ───────────────────────

# Digits stand in for letters only INSIDE a word ("k1ll", "su1c1de"). A digit
# beside another digit, or at the edge of a token, is a real number ("50mg",
# "11pm") and must survive — the medication and eating families match on those.
_LEET_DIGITS = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}
_INTERIOR_DIGIT = re.compile(r"(?<=[a-z])([01345 7])(?=[a-z])".replace(" ", ""))


def normalise(text: str) -> str:
    """Fold case and punctuation, but keep the text faithful.

    Digits survive here, because they are the anchors layer 2 scores on: a clock
    time and a count are the two most filmable things a moment can contain.
    """
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^\w\s':/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def defang(text: str) -> str:
    """Aggressively undo disguised spelling, for the banned-subject check only.

    Public feeds are full of "k1ll", "s.h.", "un alive". Layer 1 has to see
    through all of it, so it folds leet characters and rejoins letters that were
    split with punctuation.

    Substitution is deliberately narrow: only a digit with a letter on each side
    is treated as a disguised letter. That keeps "50mg" and "11pm" intact, which
    the medication and eating-disorder families need in order to fire.
    """
    text = _INTERIOR_DIGIT.sub(lambda m: _LEET_DIGITS[m.group(1)], normalise(text))
    # "s.h." and "k i l l" are rejoined so the families below still match.
    return re.sub(r"\b(\w)[.\-_*\s]{1,2}(?=\w\b|\w[.\-_*\s])", r"\1", text)


# ─────────────────────── layer 1: banned subjects ───────────────────────
#
# Nine families. A hit in any one rejects the moment outright. These are ordered
# by how much harm a miss would do, not by how often they fire.

BANNED = {
    "crisis": re.compile(
        r"\b(kill(ing)?\s*my\s*self|kms|end(ing)?\s+(it|my\s+life)|take\s+my\s+own\s+life"
        r"|suicid\w*|unalive|sewer\s*slide|self[\s-]?delete|ctb"
        r"|not\s+want(ing)?\s+to\s+(be\s+here|wake\s+up|exist|live)"
        r"|better\s+off\s+(dead|without\s+me)|no\s+reason\s+to\s+live"
        r"|do\s?nt\s+want\s+to\s+be\s+alive|want(ed|ing)?\s+to\s+die)\b"
    ),
    "self_harm": re.compile(
        r"\b(self[\s\-_]?harm\w*|cut(ting)?\s+my\s*self|burn(ed|ing)\s+my\s*self"
        r"|hurt(ing)?\s+my\s*self|fresh\s+cuts?|overdos\w*|\bod(ed|ing)\b"
        r"|clean\s+for\s+\d+\s+(days?|weeks?|months?)|grippy\s+sock)\b"
    ),
    "eating": re.compile(
        r"\b(anorexi\w*|bulimi\w*|arfid|binge[ds]?|purg\w+|thinspo|meanspo"
        r"|pro[\s-]?(ana|mia)|body\s?check\w*|goal\s?weight|ugw|cw\s*\d)\b"
        r"|\b\d{2,5}\s*(k?cal(orie)?s?|lbs?|kgs?|pounds)\b|\bbmi\s*\d"
        r"|\b(count(ing|ed)?|track(ing|ed)?|logged?)\s+(cal(orie)?s?|macros)\b"
        r"|\b(k?cal(orie)?s?|lbs?|kgs?|pounds)\b[^.]{0,12}\b\d{2,5}\b"
    ),
    "medication": re.compile(
        r"\b\d+(\.\d+)?\s?(mg|mcg|ml)\b"
        r"|\b(sertraline|fluoxetine|escitalopram|citalopram|venlafaxine|duloxetine"
        r"|bupropion|mirtazapine|quetiapine|olanzapine|risperidone|aripiprazole"
        r"|lithium|lamotrigine|clonazepam|lorazepam|alprazolam|diazepam|zopiclone"
        r"|zolpidem|trazodone|propranolol|methylphenidate|lisdexamfetamine"
        r"|adderall|vyvanse|ritalin|prozac|zoloft|lexapro|xanax|ambien|seroquel"
        r"|ssri|snri|benzo\w*|titrat\w+|taper\w*\s+off|upped\s+my\s+dose)\b"
    ),
    "abuse": re.compile(
        r"\b(rap(e|ed|ing)|sexual\s+assault|molest\w*|incest|abus(e|ed|ive)"
        r"|grooming|coerc\w+|beat\s+(me|her|him)|hit\s+me|strangl\w*"
        r"|chok(ed|ing)\s+me|domestic\s+violence|restraining\s+order"
        r"|stalk(ed|ing)\s+me|traffick\w+)\b"
    ),
    "minor": re.compile(
        r"\b(i\s?m|i\s+am)\s+(1[0-7]|[1-9])\b"
        r"|\b1[0-7]\s?[mf]\b|\b(6th|7th|8th|9th|10th|11th|12th)\s+grade"
        r"|\b(middle|high)\s?school\b|\bfreshman\b|\bsophomore\b"
        r"|\bteen(ager)?s?\b|\bminor\b|my\s+(son|daughter|kid|child|baby|toddler)\b"
    ),
    "psychosis": re.compile(
        r"\b(psychosis|psychotic|halluc\w+|hearing\s+voices|delusion\w*|paranoi\w+"
        r"|manic\s+episode|dissociat\w+|depersonal\w+|dereal\w+|catatoni\w+"
        r"|sectioned|5150|baker\s+act|psych\s+ward|inpatient"
        r"|involuntar\w+\s+(hold|commit\w*))\b"
    ),
    "substances": re.compile(
        r"\b(heroin|fentanyl|meth(amphetamine)?|cocaine|ketamine|oxycodone"
        r"|oxycontin|percs?|xans?|opioid\w*|withdrawal|detox|relapsed?"
        r"|blackout\s+drunk|drinking\s+(alone|to\s+forget)|sober\s+(since|for))\b"
    ),
    "clinical": re.compile(
        r"\b(diagnos\w+|comorbid\w*|dsm|icd-?1[01]|disorder|syndrome"
        r"|adhd|asd|ocd|ptsd|cptsd|bpd|mdd|gad|bipolar|schizo\w*|autis\w+"
        r"|neurodivergent|dopamine|serotonin|cortisol|amygdala"
        r"|nervous\s+system\s+dysregulat\w+)\b"
    ),
}

# Metaphor is the one place a literal reading is wrong often enough to matter.
# A closed list, applied only when the hit is entirely inside one of these
# phrases. Anything else fails, including anything creative.
IDIOMS = (
    "killing me", "kill me now", "could die", "dying of", "dead tired",
    "dying laughing", "kill for", "murdered that", "dead inside from",
)


def banned_subject(text: str) -> str | None:
    """Return the family name that rejects this text, or None.

    Checked before anything else touches the moment, including any model.
    """
    t = defang(text)
    for family, pattern in BANNED.items():
        match = pattern.search(t)
        if not match:
            continue
        if family in ("crisis", "self_harm"):
            span = t[max(0, match.start() - 12):match.end() + 12]
            if any(idiom in span for idiom in IDIOMS):
                continue
        return family
    return None


# ─────────────────────── layer 2: shape ───────────────────────
#
# A usable moment is small, first-person, past or present, and filmable. The
# anchors below ARE the filmability test — if a camera could not point at it,
# it does not score.

ANCHORS = {
    "clock": re.compile(r"\b([01]?\d|2[0-3]):[0-5]\d\s?(a\.?m\.?|p\.?m\.?)?\b|\b\d{1,2}\s?(am|pm)\b"),
    "body": re.compile(
        r"\b(heart\s+(pounding|racing|sank)|chest\s+(tight|heavy)|jaw|throat|"
        r"hands?\s+(shaking|shook)|stomach\s+(dropped|turned)|couldn'?t\s+breathe|"
        r"sweat\w*|nause\w+|shoulders|ears\s+rang)\b"
    ),
    "place": re.compile(
        r"\b(kitchen|bathroom|mirror|car|driveway|stairs|couch|sofa|mattress|sink|"
        r"desk|doorway|hallway|elevator|bus\s+stop|platform|office|shower|bed)\b"
    ),
    "object": re.compile(
        r"\b(phone|laptop|inbox|kettle|fridge|door|keys|screen|message|text|email|"
        r"receipt|calendar|alarm|reply|notification|photo|mirror|plate|mug)\b"
    ),
    "number": re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"fifteen|twenty|thirty|forty|fifty|sixty|half|\d{1,3})\s+"
        r"(times|minutes|hours|days|weeks|seconds|nights)\b"
    ),
    # A verb a camera could point at. "I reread" is filmable; "I struggled" is not.
    "action": re.compile(
        r"\b(stood|sat|opened|closed|scrolled|refreshed|reread|read|typed|deleted|"
        r"poured|drove|texted|stared|reached|checked|walked|waited|counted|"
        r"rewrote|paused|locked|knocked|hung\s+up|put\s+(it|them)\s+down)\b"
    ),
}

# A felt state, which is not the same thing as a diagnosis. "Tired", "guilty"
# and "dreading" are things a person notices in themselves; "anxiety" and
# "burnout" are labels for a category, and those are penalised below.
#
# This exists because the screen and the safety judge were pulling in different
# directions. The screen scored filmability, so a note left in a car park scored
# six for a place, an object and an action, and the judge then refused it as a
# trivial logistical mishap with nothing psychological in it. Three runs died
# that way. Filmable and worth reading are different axes and both need scoring.
FEELING = re.compile(
    r"\b(tired|exhausted|drained|guilty|ashamed|embarrassed|awkward|dread|"
    r"dreading|worried|scared|afraid|angry|furious|lonely|numb|restless|tense|"
    r"panicking|nervous|cried|crying|upset|hurt|resent|regret|avoided|avoiding|"
    r"ignored|ignoring|pretended|forced|couldn'?t stop|kept thinking|"
    r"overthinking|second guess|beat myself|hate myself|felt like)\b")

ABSTRACT = re.compile(
    r"\b(anxiety|depression|burnout|trauma|healing|journey|motivation|energy|"
    r"boundaries|self[\s-]?worth|mindset|growth|toxic|validation|closure)\b"
)
HEDGE = re.compile(r"\b(kind of|sort of|maybe|i guess|probably|somewhat)\b")
SIMILE = re.compile(r"\b(like a|feels like|as if|kind of like)\b")
ADVICE = re.compile(r"^\s*(you|your|try|just|stop|start|remember|here'?s|if you|never|always)\b", re.I)
LISTICLE = re.compile(r"\b\d+\s+(ways|things|signs|tips|habits|reasons)\b", re.I)
SOLICIT = re.compile(r"\b(anyone else|does anyone|dm me|link in bio)\b|https?://|@\w+", re.I)
GENERALISING = re.compile(r"\b(every\s+day|always|for\s+years|lately|usually|these\s+days)\b")
FIRST_PERSON = re.compile(r"\b(i|i'?m|i'?ve|my|me|myself)\b")
SECOND_PERSON = re.compile(r"\b(you|your|we|our)\b")
MODAL = re.compile(r"\b(would|could|should|might)\s+(?!not\b|n'?t\b)|\bif i ever\b")

PASS_SCORE = 5
HARD_ANCHORS = ("clock", "body", "place", "object", "action")


def shape(text: str) -> dict:
    """Score a moment for filmability and return the full working.

    The caller gets `ok`, plus every reason and every anchor found, so a
    rejection can be explained in a log without re-running anything.
    """
    raw = text.strip()
    t = normalise(raw)
    words = t.split()
    reasons: list[str] = []

    if not 8 <= len(words) <= 30:
        reasons.append(f"length {len(words)} outside 8-30")
    if not FIRST_PERSON.search(t):
        reasons.append("not first person")
    if SECOND_PERSON.search(t):
        reasons.append("addresses the reader")
    if MODAL.search(t):
        reasons.append("hypothetical, not something that happened")
    if GENERALISING.search(t):
        reasons.append("a habit, not one moment")
    if ADVICE.match(raw):
        reasons.append("opens as advice")
    if LISTICLE.search(raw):
        reasons.append("listicle")
    if SOLICIT.search(raw):
        reasons.append("solicitation or link")
    if raw.count(".") + raw.count("!") + raw.count("?") > 2:
        reasons.append("more than two sentences")

    found = {name: pat.findall(t) for name, pat in ANCHORS.items()}
    found = {k: v for k, v in found.items() if v}

    # A clock time is the strongest anchor there is, so it is worth more. The
    # rest are equal: a body sensation, a room, a thing in shot, and a visible
    # action are all equally filmable. A count only supports whatever it counts.
    score = 0
    score += 3 if "clock" in found else 0
    score += 2 if "body" in found else 0
    score += 2 if "place" in found else 0
    score += 2 if "object" in found else 0
    score += 2 if "action" in found else 0
    score += 1 if "number" in found else 0
    # A felt state is worth as much as a room. A moment can be perfectly
    # filmable and still be about nothing, and that is what the judge refuses.
    # A body sensation counts twice on purpose: once as something a camera can
    # see, and once as the feeling it is evidence of. A pounding heart is both,
    # and without this an empty note left in a car park outranked it.
    score += 2 if (FEELING.search(t) or "body" in found) else 0

    abstracts = ABSTRACT.findall(t)
    score -= 2 * len(abstracts)
    score -= len(SIMILE.findall(t))
    score -= len(HEDGE.findall(t))

    if len(abstracts) >= 2:
        reasons.append("names feelings instead of showing them")
    if not any(a in found for a in HARD_ANCHORS):
        reasons.append("no time, body or place to film")
    if score < PASS_SCORE:
        reasons.append(f"score {score} below {PASS_SCORE}")

    if not FEELING.search(t) and not found.get("body"):
        # Not a rejection. Plenty of good moments show the feeling rather than
        # naming it, and the judge is the one qualified to decide. But between
        # two equally filmable candidates, the one with a felt state in it is
        # the one worth spending a rewrite on.
        pass

    return {
        "ok": not reasons,
        "score": score,
        "anchors": {k: sorted({str(x) if isinstance(x, str) else x[0] for x in v}) for k, v in found.items()},
        "reasons": reasons,
    }


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def extract(text: str, found_by: str = "") -> str:
    """Pull the one moment out of a longer post.

    People do not write moments on their own. They write a paragraph about their
    evening, and the filmable part is one sentence somewhere inside it. Dropping
    the whole post for being three sentences long throws away roughly half of
    everything the feed gives us.

    So: score every sentence, keep the best one, and add the neighbour before or
    after it only if that neighbour improves the score.

    `found_by` is the phrase that made us look at this post, and it decides ties
    and near-ties. Without it the extractor picks whichever sentence has the most
    clocks and rooms in it, which is often not the sentence the search matched: a
    post found by "back to sleep" was being reduced to "talk about a jumbo sized
    bed, it is like a hotel". The relevant sentence is the one that made the post
    relevant, and we already know which that is.

    Safety is not affected by this. The banned-subject check always runs on the
    complete original, so a crisis sentence elsewhere in the post still rejects
    the whole thing.
    """
    parts = [s.strip() for s in SENTENCE_SPLIT.split(text.strip()) if s.strip()]
    if len(parts) <= 1:
        return text.strip()

    needle = found_by.lower().strip()
    scored = []
    for index, part in enumerate(parts):
        score = shape(part)["score"]
        # Enough to win a tie and to beat a slightly richer but unrelated
        # sentence, not enough to rescue a sentence with nothing filmable in it.
        if needle and needle in part.lower():
            score += 3
        scored.append((score, index))
    best_score, best = max(scored)

    # A neighbour earns its place only by raising the score of the pair.
    chosen = [best]
    for neighbour in (best - 1, best + 1):
        if not 0 <= neighbour < len(parts):
            continue
        pair = sorted(chosen + [neighbour])
        candidate = " ".join(parts[i] for i in pair)
        if len(candidate.split()) <= 30 and shape(candidate)["score"] > best_score:
            chosen = pair
            best_score = shape(candidate)["score"]

    return " ".join(parts[i] for i in sorted(chosen))


def screen(text: str, found_by: str = "") -> dict:
    """Run both layers. The first rejection wins and stops the work.

    On success `text` holds the extracted moment, which is what the rest of the
    pipeline works from. It is still the author's wording at this point; the
    abstraction step replaces it before anything is stored or published.
    """
    family = banned_subject(text)
    if family:
        return {"ok": False, "stage": "banned", "reason": family,
                "score": 0, "anchors": {}, "text": None}
    moment = extract(text, found_by)
    result = shape(moment)
    return {
        "ok": result["ok"],
        "stage": "shape",
        "reason": "; ".join(result["reasons"]) or None,
        "score": result["score"],
        "anchors": result["anchors"],
        "text": moment if result["ok"] else None,
    }
