#!/usr/bin/env python3
"""
bibliography.py — proving a citation before it can reach a slide.

The page used to cite from a hand-written list of eighteen books. That list was
safe and it was boring: for a subject like people-pleasing only four books
fitted, nothing remembered which had been used last, and one author appeared on
three of the first seven decks. A reader notices that faster than we do, and
what they conclude is that the psychology is being bent to fit the shelf.

So a citation is now looked up fresh for every deck, from any book of any year.
What has NOT changed is that a model may not type an author, a title or a year
onto a slide. It proposes; this file proves; code writes the line. The failure
that makes this necessary is not the invented book, which is easy to catch — it
is the REAL book with a claim that is not in it, attributed to a living author
who never said it. That is unfalsifiable by reading the slide, and this repo has
already shipped its cousin: a deck went out carrying "studies show 94 percent of
night waking is caused by cortisol".

Five gates, in cost order, cheapest first. A candidate that fails any gate is
discarded and the next one is tried. There is no shortage of books.

  1  the book exists          Open Library, matched on author and title,
                             and shelved in a psychology-adjacent subject
  2  the claim is falsifiable no percentages, no counts, no "studies show"
  3  the term is real         Open Library full-text search over scanned books
  4  nobody can refute it     a model that did NOT propose it tries to
  5  code writes the line     from the verified fields, never from model prose

Gates 1 and 3 are free, keyless and need no account. Gate 4 costs one model
call. Everything here fails CLOSED: an unreachable API rejects the candidate
rather than waving it through, because "we could not check" and "we checked"
must never produce the same outcome.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import readability  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent

SEARCH_URL = "https://openlibrary.org/search.json"
INSIDE_URL = "https://openlibrary.org/search/inside.json"
# Open Library asks for a name and a contact so they can reach us "when we
# notice high request volume", and gives 3 req/s to a User-Agent carrying an
# email against 1 req/s without one. We deliberately take the 1 req/s.
#
# The faster tier is for applications making "multiple calls per minute". This
# module tries at most VERIFY_MAX candidate books per deck, once or twice a
# day — about ten requests, nowhere near one a second, let alone three. The
# speed buys nothing, and a personal address on every request, in every log at
# the other end and in this file's git history forever, is a real cost paid for
# it. The public account is a contact a librarian can actually use.
#
# Do not add an address here to "follow the policy". Volume is what the policy
# is about, and if this module's volume ever grows to where the limit bites,
# that is the moment to revisit it — with an address chosen on purpose.
AGENT = "suresilly-carousel/3.0 (+https://instagram.com/suresilly)"
TIMEOUT = 20

# Open Library is free and unmetered but it is somebody's donated infrastructure,
# and a burst of lookups from one address gets throttled. One retry, then give up
# and let the caller fall back to a book already proved.
RETRIES = 1
RETRY_PAUSE = 3.0


class Unverified(Exception):
    """This candidate cannot be used, and the reason is written for a log."""


# ─────────────────────────── the wire ────────────────────────────

def _get(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": AGENT})
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
    raise Unverified(f"the catalogue could not be reached ({type(last).__name__})")


# ─────────────────────────── gate 1 ────────────────────────────

def _plain(text: str) -> str:
    """Strip accents so two spellings of one name compare equal.

    This rejected Gabor Maté, who is real, whose book is real, and whose entry
    in the catalogue is correct. Open Library stores the accent DECOMPOSED — an
    "e" followed by a combining acute — while a model sends the precomposed "é".
    They are the same letter and they were not the same string, so "Maté"
    reduced to "mate" on one side and "mat" on the other, and a well-known book
    was refused as though it did not exist.

    That is the failure mode worth guarding hardest against: not a gate that
    lets something bad through, but a gate that silently narrows the shelf and
    looks from the outside exactly like an author simply never being suggested.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def _norm(text: str) -> str:
    """Compare titles the way a person would: letters and digits, nothing else.

    "Complex PTSD: From Surviving to Thriving" and "Complex P.T.S.D. — from
    surviving to thriving" are the same book, and an exact-string match would
    reject the second and lose a real citation over punctuation.
    """
    return re.sub(r"[^a-z0-9]+", " ", _plain(text).lower()).strip()


def _surname(author: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z'-]+", _plain(author)) if len(p) > 1]
    return parts[-1].lower() if parts else ""


# ── gate 1b: the book is shelved in this field ──
#
# A real book by a real author can still be the wrong book entirely. The sister
# module's docstring records how that looks in production: a fantasy novel was
# accepted as the proof of "bed rotting" because a scanned sentence contained
# the word "bed". Nothing above catches that. The author exists, the title
# exists, the phrase exists, and the citation is nonsense.
#
# Librarians have already done this work. Open Library returns a book's Dewey
# and Library of Congress classes on the SAME search request gate 1 already
# makes — same round trip, no extra call, and the code used to throw them away.
# "The Body Keeps the Score" is RC 552 (psychiatry); "The Name of the Wind" is
# PS 3618 (American literature). That is the whole gate.
#
# The whitelist below is measured, not guessed. 47 books were looked up live on
# 2026-08-31: 28 psychology titles this page would actually cite, and a control
# set of novels, memoirs, self-help, business, cookery, popular science, true
# crime and religion. Two changes came out of that measurement:
#
#   QP ADDED. Physiology. Not an obvious psychology class, but "Why We Sleep",
#   Porges' "The Polyvagal Theory" and "Why Zebras Don't Get Ulcers" (QP 82.2,
#   Stress) carry QP AND NOTHING ELSE. Without it the gate silently deletes the
#   body-and-nervous-system shelf, which is a third of what this page talks
#   about.
#
#   HV DROPPED. Social pathology and criminology. Not one of the 28 psychology
#   titles needed it, and it admits "In Cold Blood" (HV 6533) and "The New Jim
#   Crow" — exactly the wrong-book class this gate exists to stop.
#
# BF psychology · RC internal medicine, which is where psychiatry (RC 435–576)
# lives · RJ paediatrics, which holds child psychiatry · HQ family, marriage
# and sexuality · HM sociology and social psychology · QP physiology.
PSYCH_LCC = frozenset({"BF", "RC", "RJ", "HQ", "HM", "QP"})

# Dewey, for the records that carry no LC class. 150–158 is psychology through
# applied psychology and is checked numerically. The rest are prefixes, each one
# earned by a measured book that would otherwise have been refused: 302 social
# interaction (Lerner), 612.8 neurophysiology (Walker on sleep), 616.0
# psychosomatic and medical psychology (Maté 616.08, Sapolsky 616.0019), 616.8
# psychiatry (van der Kolk, Herman, Fisher, Levine), 649.1 child rearing
# (Greene, Siegel).
PSYCH_DDC = ("302", "612.8", "616.0", "616.8", "649.1")


def _codes(value) -> list[str]:
    """Whatever the catalogue put in a classification field, as clean strings.

    Open Library returns a list, but a field can be absent, null, a bare string,
    or a list with something odd in it. None of that may raise: a crash here
    would take out the whole run over a cataloguing quirk, and an entry that
    cannot be read is simply not evidence.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [c for c in value if isinstance(c, str) and c.strip()]
    return []


def _lcc_class(code: str) -> str:
    """The alphabetic class at the front of an LC call number.

    Open Library stores these in a sortable form with the numbers zero-padded
    and single-letter classes padded with dashes: "RC-0552.00000000.P67 V358
    2014eb", "R--0726.50000000.M375 2003". So the letters cannot be taken as a
    fixed-width slice — they are read up to the first thing that is not a
    letter, which also copes with a plain "PS3618" from an older record.
    """
    match = re.match(r"[^A-Za-z]*([A-Za-z]{1,3})", code)
    return match.group(1).upper() if match else ""


def _ddc_is_psych(code: str) -> bool:
    """True if a Dewey number sits in a psychology-adjacent range."""
    # Dewey fields carry things that are not numbers at all — "[Fic]", "j004",
    # "616.8914092 B" — so the number is found rather than parsed from the start.
    match = re.search(r"\d{1,3}(?:\.\d+)?", code)
    if not match:
        return False
    head = match.group(0)
    if 150 <= float(head) < 159:            # psychology → applied psychology
        return True
    return head.startswith(PSYCH_DDC)


def check_discipline(doc: dict) -> None:
    """Gate 1b. The catalogue shelves this book somewhere near psychology.

    ANY in-discipline code passes, rather than most of them. That is deliberate
    and it is the one judgement call in here worth arguing about. An Open
    Library work record merges every edition, translation and re-issue, so a
    single book routinely carries codes from several shelves: Frankl's "Man's
    Search for Meaning" has thirty-nine LC numbers of which most are D (the
    Second World War) and only a handful are RC. Requiring a majority would
    refuse Frankl, and refusing Frankl is a worse failure for this module than
    admitting a memoir — a gate that wrongly rejects is invisible from outside
    and narrows the shelf, which is the thing this file exists to widen.

    What "any" costs: a book with one stray self-help edition gets through.
    "Eat, Pray, Love" carries a BF 637 alongside its travel-writing G class, so
    it passes here. That is accepted. This gate proves SUBJECT, not quality, and
    a book that is merely off-key still has to survive gates 3 and 4.

    NO classification at all is REJECTED. This is the fail-closed rule of
    invariant 12 applied literally: an unclassified record is "we could not
    check", and that must not come out the same as "we checked". A handful of
    Open Library records are stubs with nothing on them — the first result for
    "Why Zebras Don't Get Ulcers" is one — which is why the caller keeps reading
    the rest of the SAME response instead of giving up on the first match. The
    second Sapolsky record carries QP 82.2 and the book is cited. Nothing here
    costs another request.
    """
    title = doc.get("title") or "this book"
    lcc = [_lcc_class(c) for c in _codes(doc.get("lcc"))]
    ddc = _codes(doc.get("ddc"))
    if not any(c for c in lcc) and not ddc:
        raise Unverified(f"{title!r} carries no library classification at all, so there is "
                         "no way to tell what field it is in")
    if any(c in PSYCH_LCC for c in lcc) or any(_ddc_is_psych(c) for c in ddc):
        return
    shelved = ", ".join(dict.fromkeys(lcc + [c.strip() for c in ddc]))
    raise Unverified(f"{title!r} is catalogued under {shelved}, which is not psychology. "
                     "A real book on the wrong shelf is still the wrong book")


def verify_book(author: str, title: str, year: int) -> dict:
    """Gate 1. The book exists, by that author, at roughly that date.

    Returns the CATALOGUE's spelling of all three, not the model's. A model that
    is right about the book and wrong about the year should not put the wrong
    year on a slide, and it is cheaper to take the catalogue's answer than to
    argue about whose is better.
    """
    # The query is stripped to letters and digits before it is sent. Open
    # Library's search returns NOTHING for a title containing an apostrophe:
    # "The Boy Who Couldn't Stop Washing Rapoport" finds nothing, the same
    # words without the apostrophe find the book. That silently refused every
    # book with a possessive or a contraction in its title, and the refusal is
    # indistinguishable from the book not existing — the failure mode this
    # module has to be most careful about, because it narrows the shelf
    # invisibly and looks like an author simply never coming up.
    # ddc and lcc ride along on the request that was already being made. They
    # are what gate 1b reads, and asking for them costs nothing: same URL, same
    # round trip, two more field names.
    found = _get(SEARCH_URL, {
        "q": f"{_norm(title)} {_norm(author)}", "limit": 8,
        "fields": "title,author_name,first_publish_year,ddc,lcc",
    })
    docs = found.get("docs") or []
    if not docs:
        raise Unverified(f"no book called {title!r} by {author} exists in the catalogue")

    want_title, want_author = _norm(title), _surname(author)
    wrong_shelf: list[str] = []
    for doc in docs:
        got_title = _norm(doc.get("title") or "")
        names = doc.get("author_name") or []
        # Containment, not equality: catalogues carry subtitles the cover drops.
        title_ok = want_title in got_title or got_title in want_title
        author_ok = any(_surname(n) == want_author for n in names)
        if title_ok and author_ok:
            try:
                check_discipline(doc)
            except Unverified as off_field:
                # Keep reading. Several records for one book is the normal case,
                # and an unclassified stub coming first says nothing about the
                # classified record two rows below it.
                wrong_shelf.append(str(off_field))
                continue
            published = doc.get("first_publish_year")
            return {
                "author": names[0] if names else author,
                "title": doc.get("title") or title,
                "year": int(published) if published else int(year),
            }
    if wrong_shelf:
        raise Unverified(wrong_shelf[0])
    shown = f"{docs[0].get('title')!r} by {(docs[0].get('author_name') or ['?'])[0]}"
    raise Unverified(f"{title!r} by {author} does not match the catalogue (closest: {shown})")


# ─────────────────────────── gate 2 ────────────────────────────

# A claim shaped like evidence but impossible to check. Every one of these was
# in the deck that shipped "studies show 94 percent of night waking is caused by
# cortisol" — a real-sounding number, attached to nothing, that no reader can
# look up and no gate below this one would have caught, because the sentence is
# perfectly grammatical and the book it named is perfectly real.
FABRICATION_TELLS = (
    r"\b\d+\s*(?:%|percent|per cent)",          # 94 percent of people
    r"\b(?:studies|research|science|data)\s+(?:show|shows|prove|proves|say|says)",
    r"\b\d[\d,]*\s+(?:participants|subjects|people|adults|women|men|patients)\b",
    r"\b(?:twice|three times|four times|\d+x)\s+(?:as|more|less|likely)",
    r"\bmeta[- ]analys",
    r"\b(?:proven|scientifically proven|clinically proven)\b",
)


def check_claim_is_falsifiable(claim: str) -> None:
    """Gate 2. Refuse the claim shapes that cannot be checked at all.

    This is a blunt rule and it is meant to be. The page's voice is "a smart
    friend who reads the textbooks", and a smart friend says "Walker found that
    keeping the peace becomes automatic", not "studies show 94 percent". The
    second is not a stronger version of the first, it is a different and worse
    kind of sentence, and it is the only kind that has ever got us in trouble.
    """
    for pattern in FABRICATION_TELLS:
        hit = re.search(pattern, claim, re.I)
        if hit:
            raise Unverified(
                f"the claim leans on {hit.group(0)!r}, a statistic no reader can check. "
                "Say what the book found, not what a study allegedly measured")

    # And it has to be sayable. Slide 3 is the one card a reader must understand
    # on the first read, and code puts this sentence there, so nothing downstream
    # can soften it. Syllables do not catch these words — "schema" is two beats —
    # which is why the list is separate from the caps.
    #
    # This was only ever checked by a test, so it fired after the claim was in
    # the file rather than before. A run on 2026-09-01 saved "Trauma survivors
    # use the fawn response to appease others and avoid conflict" and the suite
    # went red on data a gate should have refused.
    jargon = readability.jargon_words(claim)
    if jargon:
        raise Unverified(
            f"the claim says {', '.join(repr(w) for w in jargon)}, which is out of a paper "
            f"rather than out of a conversation. Say the same thing the way you would say "
            f"it to a friend. The claim reads: {claim[:100]!r}")


# ─────────────────────────── gate 3 ────────────────────────────

MIN_INSIDE_HITS = 2


def verify_phrase(phrase: str) -> int:
    """Gate 3. The term of art actually appears in scanned books.

    Not the claim sentence — a sentence never appears verbatim, and demanding it
    would reject every honest citation. What is checked is the PHRASE the claim
    is built on: "fawn response", "emotional flashback", "implementation
    intention". A model that has invented a concept cannot produce a phrase that
    appears in the scanned literature, and a model quoting a real idea always
    can.

    Two hits, not one, because a single hit is as likely to be a coincidence of
    ordinary words as a term of art.
    """
    # One to five words, not two to five. The first version of this gate threw
    # away four perfectly good books in one run — Lerner on "overfunctioning",
    # Beattie on "codependency", van der Kolk on "numbing", Brown on "fitting
    # in" — because it demanded two words and then discarded any word of three
    # letters or fewer, which quietly turned "fitting in" into one word too.
    # Some of the most established terms in this field are a single word, and
    # refusing them narrowed the shelf in exactly the way this module exists to
    # widen it.
    #
    # What still has to hold is that the phrase is DISTINCTIVE. A short common
    # word proves nothing by appearing in scanned books, so the test is length
    # rather than word count: "numbing" and "codependency" qualify, "the" and
    # "shame" do not.
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", phrase)
    letters = sum(len(w) for w in words)
    if not 1 <= len(words) <= 5:
        raise Unverified(f"{phrase!r} is not a term of art. Up to five words, "
                         "the phrase the idea is known by")
    if letters < 7:
        raise Unverified(f"{phrase!r} is too ordinary a word to prove anything. "
                         "A term of art, not a common noun")
    found = _get(INSIDE_URL, {"q": f'"{" ".join(words)}"'})
    hits = found.get("hits") or {}
    total = hits.get("total", 0) if isinstance(hits, dict) else 0
    if total < MIN_INSIDE_HITS:
        raise Unverified(f"the phrase {phrase!r} appears in {total} scanned book(s). "
                         "A real term of art appears in many")
    return int(total)


# ─────────────────────────── gate 4 ────────────────────────────

REFUTE_SYSTEM = """You are checking whether a book actually supports a claim
somebody wants to print under its name, on a public page, with the author named.

Your job is to REFUTE. Assume the claim is wrong until you cannot argue it.
A claim is refuted if the book does not make it, if it is a different author's
idea, if it overstates what the book says, or if you are simply not confident
the book contains it. Being unsure IS refusing: the cost of a wrong refusal is
one book out of millions, and the cost of a wrong approval is a real person
publicly credited with something they never wrote.

Return JSON only."""

REFUTE_USER = """Book:   {author}, "{title}" ({year})
Phrase: {phrase}
Claim:  {claim}

Does this book genuinely support this claim?"""

REFUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["refuted", "why"],
    "properties": {
        "refuted": {"type": "boolean"},
        "why": {"type": "string", "minLength": 10, "maxLength": 300},
    },
}


def check_not_refuted(book: dict, phrase: str, claim: str, proposed_by: str) -> str:
    """Gate 4. A model that did not propose this tries to knock it down.

    The vendor separation is the whole point and it is the same rule the critic
    runs on: a model recognises its own output and defends it. Asking the
    proposer to check its own citation is asking it to agree with itself.
    """
    import critic  # local import: critic imports llm, and llm must load first
    import llm

    providers = critic.available_providers(proposed_by)
    if not providers:
        raise Unverified(f"no second opinion available that did not propose this "
                         f"({proposed_by} proposed it)")
    try:
        answer, who = llm.ask(
            REFUTE_SYSTEM,
            REFUTE_USER.format(phrase=phrase, claim=claim, **book),
            REFUTE_SCHEMA, temperature=0.0, providers=providers)
    except llm.ModelRefused as refused:
        raise Unverified(f"no second opinion could be reached ({refused})") from refused
    if answer["refuted"]:
        raise Unverified(f"{who} refuted it: {answer['why']}")
    return who


# ─────────────────────────── gate 5 ────────────────────────────

# Words a title keeps lowercase unless they open or close it.
SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "is",
               "nor", "of", "on", "or", "the", "to", "up", "with", "your"}


def titlecase(title: str) -> str:
    """Set a catalogue title the way a cover sets it.

    Open Library stores what a cataloguer typed, and cataloguers type sentence
    case: "The nice girl syndrome". That goes straight onto a slide under the
    source rule, next to a hand-set title in proper case, and it looks like a
    mistake because it is one. Acronyms are left exactly as found — PTSD and
    ADHD are not Ptsd and Adhd — which also means a title already in title case
    survives this untouched.
    """
    words = title.split()
    out = []
    for i, word in enumerate(words):
        bare = word.strip("(),.:;\u2014-")
        if bare.isupper() and len(bare) > 1:
            out.append(word)                                  # PTSD, ADHD, DSM
        elif (i not in (0, len(words) - 1) and word.lower() in SMALL_WORDS
              # ...but a subtitle starts a new title. "Complex PTSD: From
              # Surviving to Thriving", never ": from Surviving".
              and not (i and words[i - 1].endswith((":", "?", "!", "—")))):
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def citation_line(book: dict) -> str:
    """The string that reaches the slide, assembled from verified fields only.

    This is the whole reason the model returns structured fields instead of a
    sentence. Every character of what a reader sees under the source rule comes
    from the catalogue or from this format string, and none of it from prose a
    model wrote.
    """
    return f"— {book['author']}, *{titlecase(book['title'])}* ({book['year']})"


def citation_id(book: dict) -> str:
    return f"{_surname(book['author'])}-{book['year']}"


# ─────────────────────────── the whole run ────────────────────────────

def verify(candidate: dict, proposed_by: str, pillars: list[str]) -> dict:
    """Every gate, in order. Returns a citation ready to store, or raises.

    The returned shape is the one citations.json already uses, so a verified
    lookup and a book proved months ago are indistinguishable downstream.
    """
    claim = candidate["claim"].strip()
    phrase = candidate["phrase"].strip()

    check_claim_is_falsifiable(claim)
    # The claim has to be built ON the phrase, or gate 3 proves a term of art
    # that has nothing to do with the sentence we are about to print.
    if _norm(phrase) not in _norm(claim):
        raise Unverified(f"the claim does not contain the phrase {phrase!r}, so proving "
                         "the phrase proves nothing about the claim")

    book = verify_book(candidate["author"], candidate["title"], candidate["year"])
    hits = verify_phrase(phrase)
    checked_by = check_not_refuted(book, phrase, claim, proposed_by)

    return {
        "id": citation_id(book),
        "line": citation_line(book),
        "pillars": list(pillars),
        "claims": [claim],
        "phrase": phrase,
        "verified": {
            "catalogue": "openlibrary",
            "scanned_hits": hits,
            "proposed_by": proposed_by,
            "checked_by": checked_by,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }


# ─────────────────────────── proposing ────────────────────────────

PROPOSE_SYSTEM = """You suggest published books a psychology page could cite.

The page explains ordinary relational psychology to ordinary people. It sounds
like a smart friend who reads the textbooks, never like a therapist.

Suggest real books you are confident exist. Range widely: recent popular
psychology, older clinical texts, memoirs by clinicians, anything genuinely
published. Do not suggest journal articles.

For each book give a PHRASE — the term of art the idea is known by, one to five
words, as it is actually printed in the literature ("fawn response", "emotional
flashback", "codependency", "overfunctioning"). It must be distinctive: a term
this field would recognise, never an ordinary word like "shame" or "boundaries". Then give a CLAIM: one sentence, under
sixteen words, saying what that book found, and it MUST contain the phrase.

Never a statistic. No percentages, no counts, no "studies show". Say what the
book found. Every suggestion is checked against a library catalogue and against
the scanned text of the book, and a second model will try to refute it, so a
book you are unsure about costs you the slot for nothing.

Return JSON only."""

PROPOSE_USER = """Subject: {topic}
The moment the deck is about: {moment}

Suggest {n} different books, best fit first, by different authors.
{avoid}
Return the JSON object."""

PROPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array", "minItems": 1, "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["author", "title", "year", "phrase", "claim"],
                "properties": {
                    "author": {"type": "string", "minLength": 3, "maxLength": 80},
                    "title": {"type": "string", "minLength": 3, "maxLength": 120},
                    "year": {"type": "integer", "minimum": 1890, "maximum": 2030},
                    "phrase": {"type": "string", "minLength": 4, "maxLength": 60},
                    "claim": {"type": "string", "minLength": 20, "maxLength": 160},
                },
            },
        },
    },
}

# How many suggestions to ask for, and how many to actually put through the
# gates. Asking for more than we check costs nothing — they arrive in one call —
# and the gates reject often enough that a single candidate would usually mean
# falling back to the pool.
PROPOSE_N = 5
VERIFY_MAX = 3


def propose(topic: str, moment: str, avoid: list[str], n: int = PROPOSE_N) -> tuple[list[dict], str]:
    """Ask for candidate books. Returns the candidates and who suggested them.

    Who suggested them matters: gate 4 must be a different vendor, and guessing
    at the proposer is how a model ends up marking its own homework.
    """
    import llm

    lines = ("Do not suggest these, they have been used recently: "
             + ", ".join(avoid[:20])) if avoid else ""
    answer, who = llm.ask(PROPOSE_SYSTEM,
                          PROPOSE_USER.format(topic=topic.replace("_", " "), moment=moment,
                                              n=n, avoid=lines),
                          PROPOSE_SCHEMA, temperature=0.9)
    return answer["candidates"], who


def discover(topic: str, moment: str, avoid: list[str]) -> tuple[dict | None, list[str]]:
    """Look a citation up on the fly. Returns the first one that survives.

    Returns (None, reasons) rather than raising when nothing survives. Nothing
    surviving is an ordinary outcome — the gates are strict on purpose — and the
    caller answers it by using a book that was proved on an earlier day, not by
    failing the run.
    """
    import llm

    try:
        candidates, proposed_by = propose(topic, moment, avoid)
    except llm.ModelRefused as refused:
        return None, [f"nobody could suggest a book ({refused})"]

    reasons: list[str] = []
    for candidate in candidates[:VERIFY_MAX]:
        try:
            verified = verify(candidate, proposed_by, [topic])
        except Unverified as why:
            reasons.append(f"{candidate.get('author', '?')}: {why}")
            continue
        except (KeyError, TypeError, ValueError) as why:
            reasons.append(f"malformed suggestion ({why})")
            continue
        if verified["id"] in avoid:
            reasons.append(f"{verified['id']}: verified, but used recently")
            continue
        return verified, reasons
    return None, reasons


# ─────────────────────────── the pool ────────────────────────────
#
# citations.json is no longer a list somebody wrote. It is the record of what
# has already been proved: every book in it passed all five gates on some
# earlier day, so nothing has to be proved twice and the daily run has something
# to fall back on when Open Library is down or every suggestion is rejected.
# It grows on its own and it never needs editing by hand.

CITATIONS_PATH = SKILL_DIR / "references" / "citations.json"
HISTORY_PATH = SKILL_DIR / "citation_history.json"

# How many decks back a book stays out of the running. The pool grows by roughly
# one book a run, so a window this size keeps the page from circling a small
# core the way it circled Pete Walker for three decks in seven.
RECENT_WINDOW = 12


def _read(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def load_pool() -> list[dict]:
    return _read(CITATIONS_PATH, {"citations": []}).get("citations", [])


def store(citation: dict) -> None:
    """Add a proved book to the pool, or widen the entry already there.

    A book proved twice is one book. The second proof usually arrives with a
    different claim and a different subject, and both are worth keeping: that is
    how one book comes to serve several pillars, which is what makes the pool
    stop being a lookup table and start being a library.
    """
    data = _read(CITATIONS_PATH, {"citations": []})
    pool = data.setdefault("citations", [])
    for existing in pool:
        if existing["id"] != citation["id"]:
            continue
        for claim in citation["claims"]:
            if claim not in existing["claims"]:
                existing["claims"].append(claim)
        for pillar in citation["pillars"]:
            if pillar not in existing["pillars"]:
                existing["pillars"].append(pillar)
        existing["verified"] = citation["verified"]
        break
    else:
        pool.append(citation)
    CITATIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")


def remember(slug: str, citation_id: str) -> None:
    """Record which book a deck used, so the next deck can avoid it.

    Books were the only rotating thing in this repo with no memory. Poses have
    one, palettes have one, topics have one; a citation was drawn fresh from the
    same short list every time and the same author kept winning.
    """
    history = _read(HISTORY_PATH, {})
    history[slug] = citation_id
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


def recent(window: int = RECENT_WINDOW) -> list[str]:
    """The books used most recently, newest last.

    Deduplicated from the NEWEST end, not the oldest. A book used again today
    has to count as used today: keeping the first sighting instead would let a
    book that appeared twelve decks ago and again this morning fall straight out
    of the window, which is precisely the repeat this exists to prevent.
    """
    used = list(_read(HISTORY_PATH, {}).values())
    newest_first = dict.fromkeys(reversed(used))
    return list(reversed(newest_first))[-window:]
