#!/usr/bin/env python3
"""
discovery.py — layer 0b. Where IDEAS come from.

`sources.py` answers "what is somebody doing tonight". It cannot answer "what is
that called", because it reads a public feed and a public feed is people, not
literature. The search phrases decide the whole subject range of the account,
and no number of them answers a different question: they find what somebody DID,
never what it is called.

This module is the other end. It holds a vocabulary of named ideas, each proved
to be a real term of art, each with a measured demand behind it. A deck built
from one starts with a NAME for the thing, which is what a harvested moment
never has.

WHAT THIS DELIBERATELY DOES NOT DO, and this is the important part.

It does not quote a book. An earlier version did: it fetched a sentence out of
Open Library's scanned text and stored it to print on a slide. That single
decision was most of this module's size and every one of its defects. Scanned
text is filthy, and making one sentence safe to print took rules for contents
pages, running heads, dotted leaders, index entries, catalogue subject headings,
soft hyphens, corporate authors filed where a person goes, and fragments ending
in "i.e." — and it still shipped a fantasy novel as the proof of "bed rotting",
because the sentence contained the word "bed".

The engine already has a citation it can trust. `bibliography.discover()` finds
and proves a book for every deck, from the moment, through five gates. Nothing
here needs to duplicate that or improve on it. A concept supplies the IDEA; the
book is found the way it has always been found.

What is kept from that work is the one cheap part that earns its place:
`bibliography.verify_phrase` proves a term appears in at least two scanned
books. That is enough to know a term is real. It does not require naming which
book, so none of the machinery above comes back with it.

WHERE THE TERMS COME FROM. Wikipedia keeps curated, human-maintained category
listings of named psychological concepts. Free, keyless, and a list somebody
else maintains — which is the point, because a list this repo maintained would
go stale the same way topic-bank.md did.

It does not hardwire a condition. There is no OCD topic and no ADHD topic and
there never will be. What there is, is a route by which such a term can arrive
on its own, be proved, and be ranked against everything else on demand. Nobody
types a diagnosis anywhere for that to happen. The harm families reject a
concept exactly as they reject a moment, with one deliberate exception noted
below.

It does not let a model choose. Invariant 11 holds: the category listing is
data, the gates are code, and the ranking is arithmetic over one measured
number. A model may VETO a concept as unusable. It is never asked which is best.

Everything fails closed. An unreachable API or a term no book uses drops the
candidate. There are fourteen hundred more.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bibliography  # noqa: E402
import safety  # noqa: E402
import screen  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
CONCEPTS_PATH = SKILL_DIR / "references" / "concepts.json"
HISTORY_PATH = SKILL_DIR / "concept_history.json"
DEMAND_CACHE = SKILL_DIR / "concept_demand.json"

AGENT = "suresilly-carousel/3.0 (+https://instagram.com/suresilly)"
TIMEOUT = 30

WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
             "/en.wikipedia/all-access/user")

# Wikipedia throttles hard and early. A probe at 0.35s between calls got nine
# categories in and then took 429 on every remaining one, which looks exactly
# like those categories being empty. 1.5s ran clean.
PAUSE = 1.5
RETRY_PAUSE = 5.0
RETRIES = 2

# How many decks a concept stays out of the running once used. Longer than the
# citation window because there are hundreds of concepts and twenty books, so
# the pressure to circle back is much lower and the cost of circling is higher:
# a repeated book is a footnote, a repeated concept is the same post.
RECENT_WINDOW = 40


class Unavailable(Exception):
    """A source could not be read. The caller drops the candidate."""


def _get(url: str, params: dict | None = None) -> dict:
    target = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    request = urllib.request.Request(target, headers={"User-Agent": AGENT})
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(RETRY_PAUSE)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as handle:
                return json.loads(handle.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, OSError) as problem:
            last = problem
    raise Unavailable(f"{url.split('/')[2]}: {type(last).__name__}")


# ─────────────────────── the concept list ───────────────────────
#
# Measured, not guessed, the same way sources.py chose its search phrases. Each
# was queried and the count below is what came back. Two candidates were dropped
# for returning nothing at all — Category:Habit and Category:Procrastination are
# both empty, whatever they sound like.

CATEGORIES = (
    ("Cognitive_biases", 271),
    ("Interpersonal_relationships", 272),
    ("Human_communication", 166),
    ("Emotions", 149),
    ("Psychological_concepts", 137),
    ("Symptoms_and_signs_of_mental_disorders", 131),
    ("Motivation", 130),
    ("Sleep", 113),
    ("Behavioral_concepts", 79),
    ("Psychological_stress", 67),
    ("Emotional_issues", 64),
    ("Anxiety", 58),
    ("Defence_mechanisms", 48),
    ("Attachment_theory", 40),
    ("Self-care", 36),
    ("Interpersonal_conflict", 29),
)


def category_members(category: str) -> list[str]:
    """Every article title filed under one category."""
    answer = _get(WIKI_API, {
        "action": "query", "list": "categorymembers",
        "cmtitle": f"Category:{category}", "cmlimit": "500",
        "cmtype": "page", "format": "json",
    })
    return [m["title"] for m in answer.get("query", {}).get("categorymembers", [])]


# ─────────────────────── the shape filter ───────────────────────

# An article that is a directory rather than an idea.
LIST_ARTICLE = re.compile(r"^(list|outline|index|glossary|timeline|history|"
                          r"comparison) of\b", re.I)

# A parenthetical that says this is not a psychological concept at all. The
# listings carry paintings and films: Category:Anxiety contains "Anxiety
# (Munch)" and Category:Psychological_stress contains "At Eternity's Gate".
NOT_A_CONCEPT = re.compile(
    r"\((film|album|band|song|book|novel|painting|tv series|magazine|opera|"
    r"play|sculpture|journal|company|newspaper|disambiguation|artwork)\)", re.I)

# A parenthetical that only disambiguates, and comes off. "Agency (psychology)"
# is searched and printed as "agency".
QUALIFIER = re.compile(
    r"\s*\((psychology|psychiatry|psychoanalysis|biology|emotion|philosophy|"
    r"sociology|social science|coping mechanism|behaviour|behavior)\)\s*$", re.I)

# The banned families that still apply to a CONCEPT, and the one that does not.
#
# screen.BANNED rejects a MOMENT, and there a clinical label is always wrong: a
# moment is one person's evening, and "my OCD meant I checked the door" is a
# diagnosis standing in for what happened. A CONCEPT is the opposite case. The
# reason this module exists is that a term of art out of the literature can
# become the idea a deck is built on, so "clinical" is the one family that must
# NOT apply here — with it, the vocabulary could never hold what it was built to
# find.
#
# Every other family still holds, and holds harder than upstream.
CONCEPT_BANNED = tuple(f for f in screen.BANNED if f != "clinical")

# What dropping the clinical family would otherwise let in.
#
# "clinical" is a broad net. It catches "ocd" and "adhd", which this module has
# to hold, and in the same expression it catches "schizo", "bipolar" and
# "mania", which it must not. So the family comes off and this goes on in its
# place: the severe conditions safety.py already refuses to build a post on at
# B4_CLINICAL.
SEVERE = re.compile(
    r"\b(schizo\w*|psychosis|psychotic|bipolar|mania|manic|"
    r"dissociat\w+|depersonal\w+|dereal\w+|catatoni\w+|delusion\w*|"
    r"hallucinat\w+|personality disorder|munchausen|"
    r"self[- ]?harm|self[- ]?injur\w*|self[- ]?mutilat\w*|"
    r"auto[- ]?enucleation|enucleation|autophagia|"
    r"suicid\w*)\b", re.I)

# Things that happen TO a life, rather than patterns inside one.
#
# safety.py refuses these in a moment at B6_ACUTE_GRIEF, and nothing was
# refusing them in a concept: "divorce" (12,466 views a month) and "broken
# heart" both proved cleanly and would have outranked every real mechanism.
LIFE_EVENT = re.compile(
    r"\b(divorce|separation|bereavement|widow\w*|funeral|grief|mourning|"
    r"broken heart|breakup|break-up|marriage|wedding|childbirth|miscarriage|"
    r"stillbirth|infertility|redundancy|unemployment|retirement|"
    r"terminal illness|eviction|bankruptcy|immigration)\b", re.I)

# An experience scoped to a demographic identity, rather than a pattern anybody
# can have.
#
# "Black fatigue" proved cleanly at 7,833 views a month. It is real, named and
# well documented, and it is not this page's to write about: the page speaks in
# a universal "you", nobody reviews a deck before it posts, and safety.py
# already puts politics out of scope at B7.
#
# The line is between a COGNITIVE OR EMOTIONAL pattern, which anybody might
# recognise in themselves, and a SOCIAL POSITION, which they might not. That is
# why neurodivergence is deliberately absent: it names how a mind works, it is
# the clinical family this module exists to hold, and the tests require it.
IDENTITY_SPECIFIC = re.compile(
    r"\b(black|white|brown|racial|racism|race[- ]|ethnic\w*|minority|"
    r"indigenous|aboriginal|latin[ox]|latina|hispanic|asian|african|"
    r"immigrant|migrant|colonial\w*|slavery|"
    r"queer|gay|lesbian|bisexual|transgender|lgbt\w*|homophob\w+|"
    r"sexism|misogyn\w+|patriarch\w+|feminis\w+|"
    r"muslim|islam\w*|jewish|christian|hindu|religio\w+|caste|"
    r"disabilit\w+|disabled|deaf|blind)\b", re.I)

# A population this page does not write for. The reader is an ordinary adult at
# home. "Combat stress reaction" is real, documented, and about soldiers.
# Parenting is named out of scope at B7; "attachment theory" and "inner child"
# must both survive, so this names parenting only and never the bare word child.
NOT_OUR_READER = re.compile(
    r"\b(combat|military|veteran|soldier|war|refugee|prisoner|inmate|"
    r"postpartum|prenatal|perinatal|neonatal|p(a)?ediatric|geriatric|"
    r"adolescen\w+|infant|toddler|student|academic|occupational|patient|"
    r"parenting|parenthood|motherhood|fatherhood|maternal|paternal|"
    r"child[- ]?rearing|caregiver)\b", re.I)


def banned_concept(term: str) -> str | None:
    """The family that rejects this concept, or None."""
    defanged = screen.defang(term)
    for family in CONCEPT_BANNED:
        if screen.BANNED[family].search(defanged):
            return family
    if SEVERE.search(defanged):
        return "severe"
    if LIFE_EVENT.search(defanged):
        return "life_event"
    if IDENTITY_SPECIFIC.search(defanged):
        return "identity_specific"
    if NOT_OUR_READER.search(defanged):
        return "not_our_reader"
    return None


def usable_term(title: str) -> str | None:
    """Turn an article title into a term of art, or refuse it.

    The rules are deliberately the same ones bibliography.verify_phrase applies
    at gate 3, because a term this lets through and that gate then rejects is a
    wasted network call and a confusing log. One to five words, seven letters or
    more: "codependency" and "fawn response" qualify, "self" and "guilt" do not.
    """
    if LIST_ARTICLE.match(title) or NOT_A_CONCEPT.search(title):
        return None
    if ":" in title or "," in title:          # "Freud, Sigmund", "Portal:Mind"
        return None
    # Wikipedia sets compound terms with an en dash — "Obsessive–compulsive
    # disorder" — and a plain hyphen is what the catalogue uses. Without this
    # the word count below disagreed with itself and rejected every en-dashed
    # concept, a whole class of real terms lost to a typographic detail.
    term = QUALIFIER.sub("", title.replace("–", "-").replace("—", "-")).strip()
    if "(" in term or ")" in term:            # a qualifier we do not recognise
        return None
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", term)
    if len(words) != len(term.split()):       # digits, symbols, "3C-model"
        return None
    if not 1 <= len(words) <= 5:
        return None
    # LETTERS, not characters. Counting the string let "3C-model" through on a
    # hyphen: "C-model" is seven characters and six letters.
    if sum(1 for c in term if c.isalpha()) < 7:
        return None
    if banned_concept(term):
        return None
    # A term that IS one of the eight subjects is the shelf, not the thing on
    # it. "Anxiety" reached the pool at 26,884 views a month and would have
    # outranked every real concept, for a deck whose whole idea was "anxiety".
    # writer.py already refuses a pattern name for exactly this.
    if term.lower() in {t.replace("_", " ") for t in safety.TOPICS}:
        return None
    return term.lower()


# ─────────────────────── what a concept means ───────────────────────

# How much of the article to keep. Enough for a composer to understand the idea,
# short enough that the file stays readable.
SUMMARY_MAX = 600


def summary(title: str) -> str:
    """The opening of the Wikipedia article, as plain text.

    This is what tells the composer what the idea IS, and it replaces the book
    passage the earlier version fetched from scanned text. Two things make it a
    better answer to the same question:

      it is clean. Wikipedia serves plain prose, so none of the scan-cleaning
      rules are needed, and none of the defects they were written for exist.
      it is never printed. It informs the moment and stops there, so it does not
      have to survive being set on a slide under somebody's name.

    compose.verify already refuses any moment sharing seven consecutive words
    with what it was given, so this is held to the same standard as a harvested
    post: read it, then write something of our own.
    """
    answer = _get(WIKI_API, {
        "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
        "redirects": 1, "format": "json", "titles": title,
    })
    pages = (answer.get("query") or {}).get("pages") or {}
    if not pages:
        return ""
    text = (next(iter(pages.values())) or {}).get("extract", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:SUMMARY_MAX]


# ─────────────────────── the demand signal ───────────────────────

def demand(title: str, start: str, end: str) -> int:
    """Average monthly Wikipedia views for this article. 0 when unknown.

    This measures LOOKING UP, which is real and not the same as SAVING.
    "Apeirophobia" draws 3,314 views a month and nobody will ever save a
    carousel about the fear of eternity. So this ranks, it does not gate, and
    the floor below only drops articles nobody reads at all.

    The window is passed in rather than read off the clock, so a scheduled run
    and a rerun of it ask the same question.
    """
    path = urllib.parse.quote(title.replace(" ", "_"), safe="")
    try:
        answer = _get(f"{PAGEVIEWS}/{path}/monthly/{start}/{end}")
    except Unavailable:
        return 0
    months = answer.get("items") or []
    if not months:
        return 0
    return sum(m.get("views", 0) for m in months) // len(months)


MIN_DEMAND = 200

# How many scanned books a term may appear in before it stops being a term of
# art and starts being an ordinary word.
#
# bibliography.verify_phrase proves a term is REAL by requiring at least two
# hits. That says nothing about whether it is DISTINCTIVE, and once the book
# gates came out nothing else was asking. A sweep then proved 70 of 70,
# including "attention", "acceptance" and "behavior".
#
# The measured split is unusually clean, with nothing at all in the gap:
#
#   terms of art     amygdala hijack 220 · apophenia 457 · anchoring effect 1,911
#                    akrasia 3,183 · anhedonia 14,514 · compartmentalization 54,407
#                    hypochondria 67,708
#   ordinary words   altruism 243,445 · boredom 737,084 · aggression 860,760
#                    fantasy 1,185,015 · behavior 2,054,395 · attention 4,594,739
#
# So the ceiling sits in the empty middle. This is the same judgement gate 3
# makes at the bottom end — "a short common word proves nothing by appearing in
# scanned books" — applied at the top.
MAX_INSIDE_HITS = 100_000


# ─────────────────────── the veto ───────────────────────
#
# The one judgement no rule above can make.
#
# Every mechanical filter asks about SHAPE — is it one to five words, is it in a
# harm family. None can tell "amygdala hijack" from "alarm clock", and both
# arrive from Category:Sleep looking identical.
#
# So a model is asked, in the only shape invariant 11 permits: it may REMOVE a
# concept and it may not add, rank or choose one. A term it says nothing about
# survives. There is no field in which it can say "use this one", and the
# ranking that follows is arithmetic over a number it never sees.

VETO_SYSTEM = """You sort a list of psychology terms into two kinds. You name only
the ones that belong to the second kind, so that somebody else can drop them.

You are not judging whether a term is interesting, popular or worth writing
about. Something else measures that, with numbers, after you. You are answering
one narrow question about each term: is this a thing that HAPPENS TO A PERSON,
or is it something else?

KEEP anything that names an experience, a feeling, a habit, or a way people
treat each other. Keep it even when it sounds technical, dull or obscure. Keep
it when you are unsure. Keep it when you have never heard of it.
  amygdala hijack · fawn response · just-right feeling · learned helplessness
  rejection sensitivity · emotional labor · sunk cost fallacy · akrasia
  affect labeling · acting out · affect regulation · revenge bedtime procrastination

REMOVE a term ONLY when it clearly belongs to one of these kinds:

  an object or a device                 alarm clock, weighted blanket
  a bare body part or a chemical        amygdala, adrenaline, cortisol, ageusia
      Only the bare noun. A named thing that HAPPENS to a person stays, even
      with a body part in its name: "amygdala hijack" is an experience somebody
      has, and it is kept.
  a research method, measure or scale   actigraphy, questionnaire, factor analysis
  a theory ABOUT the field itself       4E cognition, appraisal theory
  a term about groups or society        boycott, deviancy amplification spiral
  a term about animals or infants rather than adults
  a whole field, or the name of the category itself
                                        cognitive bias, human communication

If a term does not clearly sit in one of those kinds, keep it. Most lists are
mixed, and naming more than about half of a list means you have started judging
how interesting the terms are, which is not your job.

For every term you remove, give the term exactly as it was given to you and one
short reason. Do not list terms you are keeping. Return only JSON."""

VETO_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["remove"],
    "properties": {
        "remove": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["term", "why"],
                "properties": {
                    "term": {"type": "string", "maxLength": 60},
                    "why": {"type": "string", "maxLength": 120},
                },
            },
        },
    },
}

# Terms per call. The schema caps a reply at 60 removals, and a batch larger
# than that could not say no to all of them even when all deserve it.
VETO_BATCH = 50


def veto(terms: list[str]) -> tuple[set[str], str]:
    """Terms a model says could never carry a post. Returns (removed, provider).

    Fails OPEN, unlike every other gate in this repo, and deliberately: this one
    is about taste rather than harm. Every harm filter ran before it and none
    depend on this answering. An unreachable model means a slightly weaker
    vocabulary, not an unsafe one.
    """
    import llm

    removed: set[str] = set()
    provider = "none"
    for start in range(0, len(terms), VETO_BATCH):
        chunk = terms[start:start + VETO_BATCH]
        listing = "\n".join(f"  {t}" for t in chunk)
        try:
            answer, provider = llm.ask(
                VETO_SYSTEM, f"TERMS\n{listing}\n\nReturn the JSON.",
                VETO_SCHEMA, temperature=0.0)
        except llm.ModelRefused:
            continue
        wanted = {t.lower() for t in chunk}
        # Only terms that were actually on the list. A model that invents one to
        # remove is answering about something we never asked.
        removed |= {r["term"].lower() for r in answer["remove"]
                    if r["term"].lower() in wanted}
    return removed, provider


# ─────────────────────── proving one concept ───────────────────────

def prove(term: str, title: str, start: str, end: str) -> dict:
    """Put one concept through every gate. Raises when it does not survive.

    Three questions, cheapest first, and no model call anywhere in this path.

      is it allowed        the harm and scope families above
      is it real           it appears in at least two scanned books
      does anyone want it  measured Wikipedia views

    What it does NOT do is name a book. bibliography.discover() already finds
    and proves one per deck, from the moment, through five gates. Duplicating
    that here is what made the earlier version large and fragile.
    """
    family = banned_concept(term)
    if family:
        raise Unavailable(f"{term!r} is in the {family} family")

    # The term is a real term of art. Reusing the module that already decides
    # this, and only the part of it that needs no specific book. An unreachable
    # catalogue raises Unverified and the candidate drops, which is the
    # fail-closed behaviour: "we could not check" must never come out the same
    # as "we checked".
    hits = bibliography.verify_phrase(term)
    if hits > MAX_INSIDE_HITS:
        raise Unavailable(f"{term!r} appears in {hits:,} scanned books, which makes "
                          f"it an ordinary word rather than a term of art")

    meaning = summary(title)
    if len(meaning) < 80:
        raise Unavailable(f"no usable summary for {term!r}")

    views = demand(title, start, end)
    if views < MIN_DEMAND:
        raise Unavailable(f"{views} views a month, floor is {MIN_DEMAND}")

    return {
        "id": re.sub(r"[^a-z0-9]+", "-", term).strip("-"),
        "term": term,
        "article": title,
        "demand": views,
        "scanned_hits": hits,
        "summary": meaning,
        "verified": {
            "terms_from": "wikipedia",
            "phrase_checked_against": "openlibrary",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }


# ─────────────────────── the pool ───────────────────────

def _read(path: Path, fallback):
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


NOTE = ("A record of what has been proved, not a list anybody maintains. Every "
        "concept here came from a Wikipedia category listing, appears in at "
        "least two scanned books, and has measured demand behind it. The "
        "summary is read to tell the composer what the idea means and is never "
        "printed. No book is named here on purpose: bibliography.py finds and "
        "proves the citation for every deck. Run discovery.py --refresh to grow "
        "this; never edit it by hand.")


# Every field a stored concept carries, and the contract the rest of the
# pipeline reads it by.
#
# run.py prints three of these and hands two to the composer. When the book
# fields came out, run.py was still reading "passage" and "citation_line", and
# every one of the nineteen suites passed while `--source concept` died on a
# KeyError the moment it was run. Nothing was checking that what prove() writes
# is what anybody reads.
CONCEPT_FIELDS = ("id", "term", "article", "demand", "scanned_hits",
                  "summary", "verified")


def load_pool() -> list[dict]:
    return _read(CONCEPTS_PATH, {"concepts": []}).get("concepts", [])


def store(concepts: list[dict]) -> int:
    """Add proved concepts. Returns how many were new."""
    data = _read(CONCEPTS_PATH, {"_note": NOTE, "concepts": []})
    data["_note"] = NOTE
    pool = data.setdefault("concepts", [])
    have = {c["id"] for c in pool}
    added = 0
    for concept in concepts:
        missing = [f for f in CONCEPT_FIELDS if f not in concept]
        if missing:
            raise ValueError(f"concept {concept.get('term', '?')!r} is missing "
                             f"{', '.join(missing)}; CONCEPT_FIELDS is the contract "
                             f"run.py and compose.py read a concept by")
        if concept["id"] in have:
            continue
        pool.append(concept)
        have.add(concept["id"])
        added += 1
    pool.sort(key=lambda c: -c["demand"])
    CONCEPTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return added


def prune() -> list[tuple[str, str]]:
    """Re-check the stored pool against today's rules. Returns what was dropped.

    The scope rules move every time a sweep shows something they missed — a
    divorce ranked above every real mechanism, an experience belonging to one
    group written in a universal "you". Each fix protects the NEXT sweep and
    does nothing about what is already stored.

    So this re-runs the cheap rules over what is already there. No network and
    no model: what can stop being true is not whether a term is real, but
    whether we should be writing about it. Run it after any filter change.
    """
    pool = load_pool()
    kept, dropped = [], []
    for concept in pool:
        family = banned_concept(concept["term"])
        if family:
            dropped.append((concept["term"], family))
            continue
        if usable_term(concept["term"]) is None:
            dropped.append((concept["term"], "no longer a usable term"))
            continue
        if concept.get("scanned_hits", 0) > MAX_INSIDE_HITS:
            dropped.append((concept["term"],
                            f"{concept['scanned_hits']:,} books, an ordinary word"))
            continue
        kept.append(concept)
    if dropped:
        data = _read(CONCEPTS_PATH, {"_note": NOTE, "concepts": []})
        data["concepts"] = kept
        CONCEPTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    return dropped


def remember(slug: str, concept_id: str) -> None:
    history = _read(HISTORY_PATH, {})
    history[slug] = concept_id
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def recent(window: int = RECENT_WINDOW) -> list[str]:
    return list(_read(HISTORY_PATH, {}).values())[-window:]


def pick(avoid: list[str] | None = None) -> dict | None:
    """The concept this run should build on, or None when the pool is dry.

    Highest demand that has not been used lately. Deliberately not random: an
    unattended system that picks the same way every time can be reasoned about
    after the fact.
    """
    skip = set(avoid if avoid is not None else recent())
    for concept in load_pool():
        if concept["id"] not in skip:
            return concept
    return None


# ─────────────────────── the whole sweep ───────────────────────

def titles(categories=CATEGORIES) -> list[tuple[str, str]]:
    """Every (article title, term) pair the categories yield, deduplicated.

    Interleaved across categories, one from each in turn. Read category by
    category, the list comes back alphabetically inside the largest category
    first, so the first refresh tried twelve cognitive biases beginning with A
    and the veto correctly removed all twelve. Interleaving means any limit
    samples the whole space instead of the top of one shelf.
    """
    per_category: list[list[tuple[str, str]]] = []
    seen: set[str] = set()
    for index, (category, _) in enumerate(categories):
        if index:
            time.sleep(PAUSE)
        try:
            members = category_members(category)
        except Unavailable:
            continue
        found: list[tuple[str, str]] = []
        for title in members:
            term = usable_term(title)
            if term and term not in seen:
                seen.add(term)
                found.append((title, term))
        per_category.append(found)

    out: list[tuple[str, str]] = []
    for row in range(max((len(c) for c in per_category), default=0)):
        for column in per_category:
            if row < len(column):
                out.append(column[row])
    return out


def measure(candidates: list[tuple[str, str]], start: str, end: str,
            verbose: bool = True) -> list[tuple[int, str, str]]:
    """Attach a demand figure to every candidate, cheapest signal first.

    This is the ordering step. The first real sweep proved concepts in the order
    the categories listed them — alphabetical inside the largest — and spent its
    whole budget on "acceptance" and "academic buoyancy" while "sunk cost
    fallacy" sat two hundred rows down and was never reached.

    Cached, because the answer barely moves month to month.
    """
    cache = _read(DEMAND_CACHE, {})
    out: list[tuple[int, str, str]] = []
    fresh = 0
    for title, term in candidates:
        key = f"{title}|{start}|{end}"
        if key in cache:
            views = cache[key]
        else:
            views = demand(title, start, end)
            cache[key] = views
            fresh += 1
            if fresh % 25 == 0:
                DEMAND_CACHE.write_text(json.dumps(cache, indent=0) + "\n",
                                        encoding="utf-8")
                if verbose:
                    print(f"  measured {fresh}...")
        out.append((views, title, term))
    DEMAND_CACHE.write_text(json.dumps(cache, indent=0) + "\n", encoding="utf-8")
    out.sort(key=lambda row: (-row[0], row[2]))
    return out


def refresh(start: str, end: str, limit: int = 40, scan: int = 250,
            categories=CATEGORIES, verbose: bool = True,
            use_veto: bool = True) -> dict:
    """Sweep the categories, prove the most-wanted, and store as we go.

    Two numbers, because the stages cost differently.
      scan   how many candidates to veto and measure. One model call per fifty,
             then one fast call each.
      limit  how many of the best to prove. Two network calls each.

    Every proved concept is stored the moment it lands. An early sweep was
    interrupted after eight minutes and lost all of it, because storing happened
    once after the loop. A sweep is now resumable: stop it whenever and run it
    again, and what is already proved is skipped on the way in.
    """
    known = {c["id"] for c in load_pool()}
    candidates = [(t, term) for t, term in titles(categories)
                  if re.sub(r"[^a-z0-9]+", "-", term).strip("-") not in known]

    batch = candidates[:scan]
    vetoed: set[str] = set()
    if use_veto and batch:
        vetoed, by = veto([term for _, term in batch])
        if verbose:
            print(f"  veto  {len(vetoed)} of {len(batch)} removed by {by}")
    batch = [(t, term) for t, term in batch if term not in vetoed]

    ranked = measure(batch, start, end, verbose)
    if verbose:
        print(f"  rank  {len(ranked)} measured, proving the top {limit}\n")

    proved = added = 0
    refused: dict[str, int] = {"vetoed as unusable": len(vetoed)} if vetoed else {}
    for views, title, term in ranked[:limit]:
        try:
            concept = prove(term, title, start, end)
        except (Unavailable, bibliography.Unverified) as why:
            key = str(why).split("(")[0][:44]
            refused[key] = refused.get(key, 0) + 1
            if verbose:
                print(f"  no    {term}: {str(why)[:74]}")
            continue
        proved += 1
        added += store([concept])
        if verbose:
            print(f"  ok    {term}  ({views}/mo, {concept['scanned_hits']} books)")
    return {"looked_at": len(candidates), "tried": min(limit, len(ranked)),
            "proved": proved, "added": added, "refused": refused}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--refresh", action="store_true", help="sweep and prove new concepts")
    ap.add_argument("--list", action="store_true", help="show the pool")
    ap.add_argument("--pick", action="store_true", help="show the concept a run would use")
    ap.add_argument("--prune", action="store_true",
                    help="re-check the stored pool against today's rules. No network")
    ap.add_argument("--limit", type=int, default=40,
                    help="how many of the best to prove")
    ap.add_argument("--scan", type=int, default=250,
                    help="how many candidates to veto and measure")
    ap.add_argument("--no-veto", action="store_true",
                    help="skip the model veto, for an offline or keyless run")
    # Passed in rather than read off the clock, so a rerun asks the same
    # question and gets the same answer.
    ap.add_argument("--from", dest="start", default="20250801", help="pageview window start")
    ap.add_argument("--to", dest="end", default="20260731", help="pageview window end")
    args = ap.parse_args()

    if args.refresh:
        report = refresh(args.start, args.end, limit=args.limit, scan=args.scan,
                         use_veto=not args.no_veto)
        print(f"\nlooked at {report['looked_at']} unproved concepts, "
              f"tried {report['tried']}, proved {report['proved']}, "
              f"added {report['added']}")
        if report["refused"]:
            print("refused")
            for reason, count in sorted(report["refused"].items(), key=lambda kv: -kv[1]):
                print(f"  {str(count).rjust(4)}  {reason}")
        raise SystemExit(0 if report["added"] else 1)

    if args.prune:
        dropped = prune()
        if not dropped:
            print(f"{len(load_pool())} concepts, all still pass today's rules")
            raise SystemExit(0)
        print(f"dropped {len(dropped)}, kept {len(load_pool())}\n")
        for term, why in dropped:
            print(f"  {term:<34} {why}")
        raise SystemExit(0)

    if args.list:
        pool = load_pool()
        print(f"{len(pool)} proved concepts\n")
        for concept in pool:
            print(f"  {str(concept['demand']).rjust(7)}/mo  {concept['term']}"
                  f"  ({concept['scanned_hits']} books)")
            print(f"           {concept['summary'][:104]}\n")
        raise SystemExit(0 if pool else 1)

    if args.pick:
        chosen = pick()
        if not chosen:
            print("the pool is dry, or everything in it was used recently")
            raise SystemExit(1)
        print(f"term      {chosen['term']}")
        print(f"demand    {chosen['demand']}/month, {chosen['scanned_hits']} scanned books")
        print(f"means     {chosen['summary'][:200]}")
        raise SystemExit(0)

    ap.print_help()


if __name__ == "__main__":
    main()
