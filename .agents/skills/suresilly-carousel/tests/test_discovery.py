#!/usr/bin/env python3
"""
Concept discovery regression.

This module decides what the page is ALLOWED to be about, which makes it the
first thing in the repo that can widen the subject range and the first thing
that can widen it in a direction nobody wanted. Two failure modes matter and
they pull opposite ways:

  too narrow   the harm families leak into the concept filter and the
               vocabulary can never hold a clinical term of art, which is the
               single thing this module was built to make possible. That
               failure is invisible: it looks exactly like the concept never
               having existed.
  too wide     a concept out of a harm or scope family reaches the pool, and a
               deck gets built on it with nobody in the loop.

So the harm cases and the clinical cases are both release blockers, in opposite
directions, and they are the first two blocks below.

Everything here is offline except one live check at the end. There is no
scanned-text handling to test any more: an earlier version fetched a sentence
out of Open Library and stored it to print, and that one decision was most of
this module's size and every one of its defects. The book is found by
bibliography.py, the way it always was.
"""
import inspect
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import bibliography  # noqa: E402
import discovery as d  # noqa: E402
import screen  # noqa: E402
import writer  # noqa: E402

# Terms that must NEVER reach the pool, and the family that has to catch each.
# Every one is a subject the page does not touch, and a concept is not a safer
# place to put one than a moment is.
MUST_REJECT = [
    ("Suicidal ideation", "crisis"),
    ("Self-harm", "self_harm"),
    ("Anorexia nervosa", "eating"),
    ("Bulimia nervosa", "eating"),
    ("Alcohol withdrawal syndrome", "substances"),
    ("Sexual abuse", "abuse"),
    ("Psychosis", "psychosis"),
    ("Benzodiazepine dependence", "medication"),
    # Severe conditions the page does not touch. These used to be stopped by
    # screen's clinical family, which this module deliberately switches off in
    # order to hold "ocd" and "adhd". SEVERE is what replaced it, and without
    # these cases the switch-off would go unnoticed.
    ("Schizophrenia", "severe"),
    ("Bipolar disorder", "severe"),
    ("Dissociation", "psychosis"),
    ("Mania", "severe"),
    ("Borderline personality disorder", "severe"),
    # Things that happen TO a life rather than patterns inside one. safety.py
    # refuses these in a moment at B6_ACUTE_GRIEF; nothing was refusing them in
    # a concept, and "divorce" proved cleanly at 12,466 views a month, where it
    # would have outranked every real mechanism in the pool.
    ("Divorce", "life_event"),
    ("Broken heart", "life_event"),
    ("Bereavement", "life_event"),
    # Experiences scoped to a demographic identity. Real, named, documented —
    # and not this page's to write about, because it speaks in a universal
    # "you" and nobody reviews a deck before it posts. "Black fatigue" proved
    # cleanly at 7,833 views a month during a real sweep.
    ("Black fatigue", "identity_specific"),
    ("Minority stress", "identity_specific"),
    ("Internalized racism", "identity_specific"),
    ("Religious trauma syndrome", "identity_specific"),
    # Readers this page does not write for. Parenting is out of scope at B7.
    ("Combat stress reaction", "not_our_reader"),
    ("Postpartum depression", "not_our_reader"),
    ("Attachment parenting", "not_our_reader"),
    ("Motherhood", "not_our_reader"),
    # Self-injury. "Autoenucleation" proved cleanly at 1,647 views a month.
    ("Autoenucleation", "severe"),
    ("Self-mutilation", "severe"),
]

# Terms that MUST survive the concept filter. Every one is blocked upstream by
# screen.banned_subject as a MOMENT, and that is correct there and wrong here:
# a moment is one person's evening and a clinical label has no business in it,
# while a concept is the name of an idea and the literature is where it lives.
# If this block ever fails, the vocabulary has quietly lost the ability to hold
# the terms this module exists to find.
MUST_KEEP_CLINICAL = [
    "Obsessive–compulsive disorder",
    "Attention deficit hyperactivity disorder",
    "Rejection sensitivity",
    "Hypervigilance",
    "Neurodivergent",
    "Impostor syndrome",
]

# Ordinary shape failures. Not harms, just things that are not terms of art.
MUST_DROP_SHAPE = [
    "List of cognitive biases",
    "Outline of psychology",
    "Anxiety (Munch)",
    "At Eternity's Gate (film)",
    "3C-model",
    "Self",
    "Guilt",
    "Freud, Sigmund",
    # A subject, not a concept. These are the shelves a deck is filed on, and
    # "anxiety" reached the pool at 26,884 views a month, where it would have
    # outranked every real concept for a deck whose only idea was "anxiety".
    "Anxiety",
    "Burnout",
    "Boundaries",
    # A clinical term can still be a shelf. "Executive dysfunction" is a real
    # term of art AND one of the eight subjects.
    "Executive dysfunction",
]


def run() -> int:
    failures: list[str] = []
    skipped = 0

    # ── the harm and scope families hold ──
    for title, family in MUST_REJECT:
        term = d.usable_term(title)
        if term is not None:
            failures.append(f"HARM {title!r} reached the pool as {term!r}, "
                            f"expected the {family} family to stop it")
        caught = d.banned_concept(title)
        if caught != family:
            failures.append(f"HARM banned_concept({title!r}) said {caught!r}, "
                            f"expected {family!r}")

    # ── and the clinical family does NOT ──
    for title in MUST_KEEP_CLINICAL:
        if d.usable_term(title) is None:
            failures.append(f"NARROW {title!r} was refused. A clinical term of art "
                            f"is exactly what this module exists to find")
        if d.banned_concept(title) is not None:
            failures.append(f"NARROW banned_concept({title!r}) fired. The clinical "
                            f"family must not apply to a concept")

    # The identity rule must not reach the clinical terms. Neurodivergence names
    # how a mind works rather than a social position, and it is the whole reason
    # the clinical family was switched off in the first place.
    for keep in ("neurodivergent", "obsessive-compulsive disorder", "hypervigilance"):
        if d.IDENTITY_SPECIFIC.search(keep):
            failures.append(f"NARROW the identity rule swallowed {keep!r}")

    # The parenting rule must not reach these. "Attachment theory" is a core
    # subject and "inner child" is in the account's own hashtag list, so a rule
    # written around the bare word "child" would have taken both.
    for keep in ("attachment theory", "inner child", "childhood emotional neglect"):
        if d.banned_concept(keep):
            failures.append(f"NARROW {keep!r} was caught by {d.banned_concept(keep)}")

    # The guard above is only meaningful if the family it excludes still exists
    # upstream. If screen ever renames it, CONCEPT_BANNED silently becomes every
    # family and the two blocks above start disagreeing for no visible reason.
    if "clinical" not in screen.BANNED:
        failures.append("WIRING screen.BANNED has no 'clinical' family any more, so "
                        "CONCEPT_BANNED is excluding nothing")
    if "clinical" in d.CONCEPT_BANNED:
        failures.append("WIRING the clinical family is being applied to concepts")
    if set(d.CONCEPT_BANNED) != set(screen.BANNED) - {"clinical"}:
        failures.append("WIRING CONCEPT_BANNED is not screen.BANNED minus clinical")
    # Switching the clinical family off is only safe while SEVERE is on.
    for word in ("schizophrenia", "bipolar", "mania", "psychosis"):
        if not d.SEVERE.search(word):
            failures.append(f"WIRING SEVERE no longer covers {word!r}, which the "
                            f"clinical family used to stop")

    # ── shape ──
    for title in MUST_DROP_SHAPE:
        term = d.usable_term(title)
        if term is not None:
            failures.append(f"SHAPE {title!r} passed as {term!r}")

    # A term this lets through must be one bibliography.verify_phrase would also
    # accept, or every refresh spends a network call proving something the next
    # gate was always going to refuse.
    for title in MUST_KEEP_CLINICAL + ["Amygdala hijack", "Fawn response"]:
        term = d.usable_term(title)
        if not term:
            continue
        words = term.split()
        if not 1 <= len(words) <= 5 or sum(1 for c in term if c.isalpha()) < 7:
            failures.append(f"GATE3 {term!r} would be refused by verify_phrase, "
                            f"so it should not have passed usable_term")

    # ── this module does not name a book ──
    #
    # The one rule that keeps it small. An earlier version fetched a sentence out
    # of scanned text and stored the book it came from; that decision was most of
    # the module's size and every one of its defects, and it shipped a fantasy
    # novel as the proof of "bed rotting" because the sentence contained the word
    # "bed". bibliography.py finds the citation, from the moment, through five
    # gates. If any of these come back, the quoting path has been rebuilt and the
    # tests for it have not.
    for gone in ("passages", "clean_passage", "best_passage", "as_citation",
                 "is_a_person", "author_of", "mentions"):
        if hasattr(d, gone):
            failures.append(f"SCOPE discovery.{gone} exists again. This module "
                            f"must not fetch or store book text")
    for func in (writer.plan_deck, writer.write_deck):
        if "prefer" in inspect.signature(func).parameters:
            failures.append(f"SCOPE writer.{func.__name__} still takes prefer, "
                            f"which only the removed quoting path used")

    # ── fail closed ──
    #
    # An unreachable source must drop the candidate, never pass it. Checked by
    # pointing the module at a host that cannot answer, which is the only way to
    # test this without waiting for a real outage.
    real_wiki, real_views = d.WIKI_API, d.PAGEVIEWS
    original_retries, original_pause = d.RETRIES, d.RETRY_PAUSE
    d.RETRIES, d.RETRY_PAUSE = 0, 0
    try:
        d.WIKI_API = d.PAGEVIEWS = "http://127.0.0.1:9/nothing"
        try:
            got = d.prove("fawn response", "Fawn response", "20250801", "20260731")
            failures.append(f"CLOSED an unreachable source still proved: {got['id']}")
        except (d.Unavailable, bibliography.Unverified):
            pass
        # demand() is the one call allowed to fail soft, because it only ranks.
        # It must return 0 rather than raise, or an outage stops a refresh.
        if d.demand("Fawn response", "20250801", "20260731") != 0:
            failures.append("CLOSED demand() invented a number from a dead host")
    finally:
        d.WIKI_API, d.PAGEVIEWS = real_wiki, real_views
        d.RETRIES, d.RETRY_PAUSE = original_retries, original_pause

    # ── the pool ──
    #
    # Written to a temporary file. A test that appends to the real vocabulary
    # would grow it every CI run with whatever the fixtures happened to say.
    real_concepts, real_history = d.CONCEPTS_PATH, d.HISTORY_PATH
    with tempfile.TemporaryDirectory() as tmp:
        d.CONCEPTS_PATH = pathlib.Path(tmp) / "concepts.json"
        d.HISTORY_PATH = pathlib.Path(tmp) / "history.json"
        try:
            full = {"article": "A", "verified": {}}
            sample = [
                {"id": "low", "term": "fawn response", "demand": 100,
                 "summary": "x", "scanned_hits": 2, **full},
                {"id": "high", "term": "amygdala hijack", "demand": 9000,
                 "summary": "x", "scanned_hits": 2, **full},
            ]
            # The contract between what prove() writes and what the pipeline
            # reads. When the book fields came out, run.py was still reading
            # "passage" and every suite passed while `--source concept` died on
            # a KeyError the first time anybody ran it.
            try:
                d.store([{"id": "x", "term": "x", "demand": 1}])
                failures.append("CONTRACT store accepted a concept missing fields")
            except ValueError:
                pass
            for field in ("term", "summary"):
                if field not in d.CONCEPT_FIELDS:
                    failures.append(f"CONTRACT {field!r} is read by the pipeline but "
                                    f"is not in CONCEPT_FIELDS")
            if d.store(sample) != 2:
                failures.append("POOL store did not report two new concepts")
            if d.store(sample) != 0:
                failures.append("POOL storing the same concepts twice added them again")
            if [c["id"] for c in d.load_pool()] != ["high", "low"]:
                failures.append("POOL is not ordered by demand")
            if (d.pick() or {}).get("id") != "high":
                failures.append("POOL pick did not take the highest demand")
            if (d.pick(avoid=["high"]) or {}).get("id") != "low":
                failures.append("POOL pick ignored the avoid list")
            if d.pick(avoid=["high", "low"]) is not None:
                failures.append("POOL pick invented a concept when everything was avoided")

            d.remember("20260901_deck", "high")
            if d.recent() != ["high"]:
                failures.append("POOL remember did not record the concept used")
            if (d.pick() or {}).get("id") != "low":
                failures.append("POOL pick reused a concept from the recent window")

            # prune re-applies today's rules to what is already stored. A stored
            # concept that a newly written rule now rejects must go, and nothing
            # is re-proved to make that happen.
            d.store([{"id": "divorce", "term": "divorce", "demand": 12466,
                      "summary": "x", "scanned_hits": 9, **full},
                     # An ordinary word. "attention" appears in 4,594,739 scanned
                     # books and proved cleanly once the book gates came out.
                     {"id": "attention", "term": "attention", "demand": 8322,
                      "summary": "x", "scanned_hits": 4_594_739, **full}])
            dropped = dict(d.prune())
            if dropped.get("divorce") != "life_event":
                failures.append(f"PRUNE did not drop a life event: {dropped}")
            if "ordinary word" not in dropped.get("attention", ""):
                failures.append(f"PRUNE kept an ordinary word: {dropped}")
            if {c["id"] for c in d.load_pool()} != {"high", "low"}:
                failures.append("PRUNE removed something it should have kept")
        finally:
            d.CONCEPTS_PATH, d.HISTORY_PATH = real_concepts, real_history

    # ── a decision made by hand sticks ──
    #
    # Deleting a row is not enough. refresh() treats "not in the pool" as "new",
    # so a deleted concept comes back on the very next sweep. Eighteen of the
    # first fifty were rejected by a person, and every one of them would have
    # returned.
    real_concepts2, real_history2 = d.CONCEPTS_PATH, d.HISTORY_PATH
    with tempfile.TemporaryDirectory() as tmp:
        d.CONCEPTS_PATH = pathlib.Path(tmp) / "concepts.json"
        d.HISTORY_PATH = pathlib.Path(tmp) / "history.json"
        try:
            full = {"article": "A", "verified": {}}
            d.store([{"id": "catfight", "term": "catfight", "demand": 5126,
                      "summary": "x", "scanned_hits": 9479, **full}])
            if d.reject({"catfight": "wrong for this page"}) != 1:
                failures.append("REJECT did not record a new decision")
            if d.load_rejected().get("catfight") != "wrong for this page":
                failures.append("REJECT did not keep the reason")
            if any(c["term"] == "catfight" for c in d.load_pool()):
                failures.append("REJECT left the concept in the pool")
            # And it must not come back. refresh() filters candidates against
            # the list, so a rejected term is never a candidate again.
            if "catfight" not in d.load_rejected():
                failures.append("REJECT the decision did not persist")
            # prune drops a stored concept that has since been rejected.
            d.store([{"id": "catfight", "term": "catfight", "demand": 5126,
                      "summary": "x", "scanned_hits": 9479, **full}])
            if dict(d.prune()).get("catfight") != "rejected by hand":
                failures.append("PRUNE ignored a term rejected by hand")
        finally:
            d.CONCEPTS_PATH, d.HISTORY_PATH = real_concepts2, real_history2

    # ── how common a term is, at both ends ──
    #
    # bibliography proves a term EXISTS with two hits. It says nothing about
    # whether the term is distinctive, and once the book gates came out nothing
    # else was asking: a sweep proved 70 of 70, including "attention".
    if not d.MIN_INSIDE_HITS < 57:
        failures.append(f"FLOOR MIN_INSIDE_HITS is {d.MIN_INSIDE_HITS}, which would "
                        f"reject 'anxious-preoccupied attachment' at 57 books. A new "
                        f"term has few books BECAUSE it is new, and those are the "
                        f"most valuable concepts here")
    if not 12 < d.MIN_INSIDE_HITS:
        failures.append("FLOOR MIN_INSIDE_HITS would still admit 'bad boy archetype' "
                        "at 12 books")
    if not 67_708 < d.MAX_INSIDE_HITS < 243_445:
        failures.append(f"CEILING MAX_INSIDE_HITS is {d.MAX_INSIDE_HITS}, outside the "
                        f"measured gap between 'hypochondria' at 67,708 and "
                        f"'altruism' at 243,445")

    # ── the article says what it is ──
    for meaning, caught in (
        ("Attachment therapy is a pseudoscientific mental health intervention.", True),
        ("Homo homini lupus is a Latin proverb meaning a man is a wolf.", True),
        ("Send to Coventry is an idiom used in England meaning to ostracise.", True),
        ("In the philosophy of Baruch Spinoza, conatus is an innate inclination.", True),
        # And it must not reach the clinical terms it sits next to.
        ("Alexithymia is a neuropsychological phenomenon characterized by "
         "difficulties processing emotion.", False),
        ("An amygdala hijack is an immediate and overwhelming emotional response.", False),
    ):
        if bool(d.NOT_PSYCHOLOGY.search(meaning)) != caught:
            failures.append(f"TELL {'missed' if caught else 'wrongly caught'}: "
                            f"{meaning[:56]!r}")

    # ── the veto may only ever remove ──
    #
    # A reply naming a term nobody asked about is answering a different question,
    # and honouring it would drop a concept by coincidence of spelling.
    import llm
    real_ask = llm.ask
    try:
        llm.ask = lambda *a, **k: ({"remove": [
            {"term": "alarm clock", "why": "an object"},
            {"term": "fawn response", "why": "invented, was never on the list"},
        ]}, "stub")
        removed, _ = d.veto(["alarm clock", "amygdala hijack"])
        if removed != {"alarm clock"}:
            failures.append(f"VETO honoured a term that was not on the list: {removed}")

        # An unreachable model must not empty the list. This gate fails OPEN on
        # purpose, and getting that backwards is a refresh that silently proves
        # nothing.
        def refuse(*a, **k):
            raise llm.ModelRefused("no vendor")
        llm.ask = refuse
        removed, who = d.veto(["alarm clock", "amygdala hijack"])
        if removed or who != "none":
            failures.append("VETO an unreachable model removed something anyway")
    finally:
        llm.ask = real_ask

    # ── the summary, when Wikipedia is reachable ──
    try:
        meaning = d.summary("Amygdala hijack")
        if not meaning:
            skipped += 1
        elif "amygdala" not in meaning.lower():
            failures.append(f"LIVE the summary is not about the term: {meaning[:60]!r}")
        elif len(meaning) > d.SUMMARY_MAX:
            failures.append(f"LIVE the summary is {len(meaning)} chars, "
                            f"cap {d.SUMMARY_MAX}")
    except Exception:                                   # noqa: BLE001 - offline
        skipped += 1

    if failures:
        print(f"discovery: {len(failures)} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    note = f", {skipped} inconclusive (source unreachable)" if skipped else ""
    print(f"discovery: passed ({len(MUST_REJECT)} harm and scope families held, "
          f"{len(MUST_KEEP_CLINICAL)} clinical terms allowed through, "
          f"pool, prune and veto checked, no book path{note})")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
