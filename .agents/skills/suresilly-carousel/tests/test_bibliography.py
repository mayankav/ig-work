#!/usr/bin/env python3
"""
Citation verification regression.

A citation is the only thing on a slide that names a real, living person and
puts words in their mouth. It is now looked up fresh for every deck rather than
drawn from a list somebody typed, which is a much better page and a much larger
blast radius, so the gates that make it safe are worth more tests than the
lookup itself.

The offline cases always run. The catalogue cases need openlibrary.org, and when
it cannot be reached they report INCONCLUSIVE and do not fail: a gate that goes
red because somebody's donated server is busy trains people to ignore red. What
must never happen is the opposite — an unreachable catalogue must never let a
candidate through — and that is checked offline, by pointing the module at a
host that cannot answer.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import bibliography as bib  # noqa: E402


def run() -> int:
    failures: list[str] = []
    skipped = 0

    # ── gate 2: claims shaped like evidence nobody can check ──
    #
    # The deck that shipped "studies show 94 percent of night waking is caused
    # by cortisol" is the reason this gate exists, so it is the first case.
    for claim in (
        "Studies show 94 percent of night waking is caused by cortisol.",
        "Research proves that people pleasing is learned in childhood.",
        "A meta-analysis found the fawn response in most adults.",
        "Walker found people are twice as likely to freeze.",
        "In 4,200 participants the effect held.",
        "This is scientifically proven.",
    ):
        try:
            bib.check_claim_is_falsifiable(claim)
            failures.append(f"GATE2 an uncheckable claim passed: {claim[:52]}")
        except bib.Unverified:
            pass

    for claim in (
        "Walker found that the fawn response turns keeping the peace into a reflex.",
        "Tawwab found that a porous boundary leaves resentment behind.",
    ):
        try:
            bib.check_claim_is_falsifiable(claim)
        except bib.Unverified as why:
            failures.append(f"GATE2 an honest claim was refused: {claim[:40]} ({why})")

    # ── the claim has to be built on the phrase we prove ──
    #
    # Otherwise gate 3 proves a real term of art and the sentence printed on the
    # slide is about something else entirely, which is the whole failure this
    # module exists to stop, arrived at by a longer route.
    try:
        bib.verify({"author": "Pete Walker", "title": "Complex PTSD", "year": 2013,
                    "phrase": "fawn response",
                    "claim": "Walker found that shame is stored in the body."},
                   proposed_by="gemini", pillars=["people_pleasing"])
        failures.append("LINK a claim that never mentions its own phrase was accepted")
    except bib.Unverified as why:
        if "does not contain the phrase" not in str(why):
            failures.append(f"LINK refused for the wrong reason: {why}")

    # ── accents ──
    #
    # Open Library stores accents DECOMPOSED, models send them PRECOMPOSED, and
    # comparing the two as raw strings refused Gabor Maté — real author, real
    # book, correct catalogue entry. A gate that wrongly rejects is invisible
    # from outside: it looks exactly like an author never being suggested, and
    # it narrows the shelf, which is the one thing this module exists to widen.
    import unicodedata
    spellings = ["Gabor Maté", unicodedata.normalize("NFD", "Gabor Maté"), "Gabor Mate"]
    if len({bib._surname(s) for s in spellings}) != 1:
        failures.append(f"ACCENT one name spelled three ways gave "
                        f"{ {bib._surname(s) for s in spellings} }")
    if bib._norm("Brené Brown") != bib._norm("Brene Brown"):
        failures.append("ACCENT an accented title would not match its plain spelling")

    # ── failing closed ──
    #
    # An unreachable catalogue must reject, never wave through. This is the one
    # that would be invisible in production: everything would keep working and
    # nothing would be verified.
    real_search, real_inside = bib.SEARCH_URL, bib.INSIDE_URL
    real_retries = bib.RETRIES
    bib.SEARCH_URL = "https://localhost:1/search.json"
    bib.INSIDE_URL = "https://localhost:1/inside.json"
    bib.RETRIES = 0
    try:
        bib.verify_book("Pete Walker", "Complex PTSD", 2013)
        failures.append("CLOSED an unreachable catalogue still verified a book")
    except bib.Unverified:
        pass
    try:
        bib.verify_phrase("fawn response")
        failures.append("CLOSED an unreachable catalogue still verified a phrase")
    except bib.Unverified:
        pass
    bib.SEARCH_URL, bib.INSIDE_URL, bib.RETRIES = real_search, real_inside, real_retries

    # ── gate 1b: the book is shelved in this field ──
    #
    # The failure this catches is the one recorded in discovery.py's docstring:
    # a fantasy novel accepted as the proof of "bed rotting" because a scanned
    # sentence contained the word "bed". Every other gate passes that book. The
    # author is real, the title is real, the phrase is real, the citation is
    # nonsense. Only the librarians' own subject classes tell it apart.
    #
    # Every doc below is a real Open Library response shape, taken from live
    # lookups on 2026-08-31. None of these cases touch the network.
    for label, doc in (
        ("van der Kolk", {"title": "The Body Keeps the Score", "ddc": ["616.85"],
                          "lcc": ["RC-0552.00000000.P67 V358 2014eb"]}),
        ("Tawwab, no Dewey at all", {"title": "Set Boundaries, Find Peace", "ddc": None,
                                     "lcc": ["BF-0637.00000000.P3 T38 2021"]}),
        # Greene is HQ and Dewey 649.153 — neither BF nor 150-158. Measured, and
        # the reason the whitelist is wider than the obvious two classes.
        ("Greene, parenting", {"title": "The Explosive Child", "ddc": ["649.153"],
                               "lcc": ["HQ-0755.85000000.G7365 2014"]}),
        # QP is physiology. Porges and Walker on sleep carry QP AND NOTHING
        # ELSE, so dropping it would delete the whole body-and-nervous-system
        # shelf this page leans on.
        ("Porges, QP only", {"title": "The Polyvagal Theory", "ddc": None,
                             "lcc": ["QP-0368.00000000.D36 2018"]}),
        ("Lerner, Dewey only", {"title": "The Dance of Anger", "ddc": ["152.47082"], "lcc": []}),
        # Frankl's work record merges thirty-nine call numbers, most of them D
        # (the Second World War). One in-discipline code is enough on purpose:
        # demanding a majority would refuse Frankl.
        ("Frankl, merged record", {"title": "Man's Search for Meaning",
                                   "ddc": ["940.5318092 B", "616.8917"],
                                   "lcc": ["D--0810.00000000.J4 F72713 1985",
                                           "D--0805.00000000.G3 F7233 1963",
                                           "RC-0489.00000000.E93"]}),
    ):
        try:
            bib.check_discipline(doc)
        except bib.Unverified as why:
            failures.append(f"FIELD a psychology book was refused as off-field: {label} ({why})")

    for label, doc in (
        ("the fantasy novel", {"title": "The Name of the Wind", "ddc": ["813.6"],
                               "lcc": ["PS-3618.00000000.O8685 N36 2007"]}),
        ("a literary novel", {"title": "Normal People", "ddc": ["823.92"],
                              "lcc": ["PR-6118.00000000.O59 N67 2018"]}),
        ("a memoir", {"title": "Becoming", "ddc": ["973.932092"],
                      "lcc": ["E--0909.00000000.O24 A3 2018"]}),
        # HV is social pathology and criminology. It was in the candidate
        # whitelist and measurement threw it out: not one of twenty-eight
        # psychology titles needed it, and it waves through true crime.
        ("true crime", {"title": "In Cold Blood", "ddc": ["364.15230978144"],
                        "lcc": ["HV-6533.00000000.K3 C3 1965"]}),
        ("a business book", {"title": "Good to Great", "ddc": ["658"],
                             "lcc": ["HD-0057.70000000.C645 2001"]}),
    ):
        try:
            bib.check_discipline(doc)
            failures.append(f"FIELD an off-field book was accepted: {label}")
        except bib.Unverified:
            pass

    # ── no classification is a rejection, not a shrug ──
    #
    # Invariant 12 read literally: an unclassified record is "we could not
    # check", and that must never come out the same as "we checked". Some Open
    # Library records are stubs carrying neither number. They are refused, and
    # the caller's answer is to read the next record for the same book rather
    # than to guess.
    for label, doc in (
        ("nothing at all", {"title": "Why Zebras Don't Get Ulcers"}),
        ("both fields null", {"title": "x", "ddc": None, "lcc": None}),
        ("both fields empty", {"title": "x", "ddc": [], "lcc": []}),
    ):
        try:
            bib.check_discipline(doc)
            failures.append(f"FIELD an unclassified record passed ({label}) — "
                            "'we could not check' came out as 'we checked'")
        except bib.Unverified as why:
            if "no library classification" not in str(why):
                failures.append(f"FIELD unclassified refused for the wrong reason: {why}")

    # ── a cataloguing quirk must not take the run down ──
    #
    # These fields are typed by hand across thousands of libraries and they hold
    # whatever ended up in them. A shape nobody expected has to REJECT, which is
    # what an unreadable code is worth as evidence, and never raise.
    for label, doc in (
        ("lcc as a bare string", {"title": "x", "lcc": "PS-3618.00000000.O8685"}),
        ("numbers in the list", {"title": "x", "lcc": [552, None, {"a": 1}], "ddc": [616.85]}),
        ("Dewey that is not a number", {"title": "x", "ddc": ["[Fic]"], "lcc": []}),
        ("a single-letter class", {"title": "x", "lcc": ["R--0726.50000000.M375 2003"]}),
        ("the fields missing entirely", {}),
    ):
        try:
            bib.check_discipline(doc)
            failures.append(f"FIELD a malformed record was accepted: {label}")
        except bib.Unverified:
            pass
        except Exception as boom:                                  # noqa: BLE001
            failures.append(f"FIELD a malformed record crashed the gate ({label}): "
                            f"{type(boom).__name__}: {boom}")

    # ── the classes ride along on the request gate 1 already makes ──
    #
    # One request, not two. If this ever becomes a second lookup the module has
    # doubled its load on somebody's donated server for information it was
    # already being sent.
    real_get, seen = bib._get, []

    def _stub(url, params):
        seen.append((url, params))
        return {"docs": [
            # The first record for Sapolsky really is a bare stub. The second
            # carries QP 82.2, Stress. Refusing on the first would lose the book.
            {"title": "Why Zebras Don't Get Ulcers", "author_name": ["Robert M. Sapolsky"],
             "first_publish_year": 1994},
            {"title": "Why Zebras Don't Get Ulcers", "author_name": ["Robert M. Sapolsky"],
             "first_publish_year": 1994, "ddc": ["616.0019"],
             "lcc": ["QP-0082.20000000.S8 S266 1998"]},
        ]}

    bib._get = _stub
    try:
        book = bib.verify_book("Robert M. Sapolsky", "Why Zebras Don't Get Ulcers", 1994)
        if book["year"] != 1994:
            failures.append(f"FIELD the rescued record came back wrong: {book}")
    except bib.Unverified as why:
        failures.append(f"FIELD an unclassified first record lost a classified book: {why}")
    if len(seen) != 1:
        failures.append(f"FIELD gate 1 now makes {len(seen)} requests instead of one")
    elif not {"ddc", "lcc"} <= set(seen[0][1].get("fields", "").split(",")):
        failures.append(f"FIELD ddc and lcc were not asked for: {seen[0][1].get('fields')}")

    bib._get = lambda url, params: {"docs": [
        {"title": "The Name of the Wind", "author_name": ["Patrick Rothfuss"],
         "first_publish_year": 2007, "ddc": ["813.6"],
         "lcc": ["PS-3618.00000000.O8685 N36 2007"]}]}
    try:
        bib.verify_book("Patrick Rothfuss", "The Name of the Wind", 2007)
        failures.append("FIELD the fantasy novel verified as a source")
    except bib.Unverified as why:
        if "not psychology" not in str(why):
            failures.append(f"FIELD the novel was refused for the wrong reason: {why}")
    bib._get = real_get

    # ── the contact we send, and the one we do not ──
    #
    # Open Library wants to know who is calling. It gets the name and the public
    # account, and deliberately not a personal email: the 3 req/s tier the email
    # would buy is for applications making multiple calls per minute, and this
    # one makes about ten a day. See the note above AGENT in bibliography.py.
    #
    # This asserts the absence on purpose. An address is easy to add back in
    # good faith by somebody reading the policy and not the volume, and it would
    # then be in the history for good.
    if "suresilly" not in bib.AGENT or "openlibrary" in bib.AGENT.lower():
        failures.append(f"AGENT does not identify the application: {bib.AGENT}")
    if "@" in bib.AGENT:
        failures.append(f"AGENT carries a personal address we chose not to send: {bib.AGENT}")

    # ── the line is built by code, from verified fields ──
    line = bib.citation_line({"author": "Pete Walker",
                              "title": "complex PTSD: from surviving to thriving",
                              "year": 2013})
    if line != "— Pete Walker, *Complex PTSD: From Surviving to Thriving* (2013)":
        failures.append(f"LINE assembled wrongly: {line}")
    if bib.titlecase("the nice girl syndrome") != "The Nice Girl Syndrome":
        failures.append("LINE a sentence-case catalogue title reached the slide uncorrected")

    # ── the pool grows rather than duplicating ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        bib.CITATIONS_PATH = tmp / "citations.json"
        bib.HISTORY_PATH = tmp / "history.json"
        bib.CITATIONS_PATH.write_text('{"citations": []}', encoding="utf-8")

        entry = {"id": "engel-2008", "line": "— Beverly Engel, *The Nice Girl Syndrome* (2008)",
                 "pillars": ["people_pleasing"], "claims": ["A claim about people pleasing."],
                 "phrase": "people pleasing", "verified": {"at": "x"}}
        bib.store(entry)
        bib.store({**entry, "pillars": ["self_worth"], "claims": ["A different claim entirely."]})
        pool = bib.load_pool()
        if len(pool) != 1:
            failures.append(f"POOL the same book was stored {len(pool)} times")
        elif sorted(pool[0]["pillars"]) != ["people_pleasing", "self_worth"]:
            failures.append("POOL a second proof did not widen the subjects the book covers")
        elif len(pool[0]["claims"]) != 2:
            failures.append("POOL a second proof did not add its claim")

        # ── the memory that stops one author owning the page ──
        for i, cid in enumerate(["a-1", "b-2", "c-3", "b-2"]):
            bib.remember(f"deck{i}", cid)
        if bib.recent() != ["a-1", "c-3", "b-2"]:
            failures.append(f"RECENT wrong order or duplicates kept: {bib.recent()}")
        if len(bib.recent(window=2)) != 2:
            failures.append("RECENT the window is not honoured")

    # ── the catalogue itself, when it will talk to us ──
    try:
        real = bib.verify_book("Nedra Glover Tawwab", "Set Boundaries, Find Peace", 2019)
        if real["year"] != 2021:
            failures.append(f"GATE1 a wrong year was not corrected from the catalogue: {real}")
        for author, title in (("Marcus Zelnick", "The Mindful Hippopotamus Cure"),
                              ("Brene Brown", "The Fawn Response Handbook")):
            try:
                bib.verify_book(author, title, 2019)
                failures.append(f"GATE1 an invented book verified: {title}")
            except bib.Unverified:
                pass
        # Punctuation in a title. Open Library's search returns NOTHING for a
        # query containing an apostrophe, so every book with a contraction or a
        # possessive in its title was refused as non-existent. Two real books,
        # one with an apostrophe and one with an accented author, because both
        # were found the same way: a rejection that looked like strictness and
        # was a bug.
        for author, title, year in (
            ("Judith L. Rapoport", "The Boy Who Couldn't Stop Washing", 1989),
            ("Gabor Maté", "When the Body Says No", 2003),
        ):
            try:
                bib.verify_book(author, title, year)
            except bib.Unverified as why:
                failures.append(f"GATE1 a real book was refused: {title} ({why})")

        # The classes, live. The novel has to be refused by a real response and
        # not only by a fixture, and Sapolsky has to survive a real response
        # whose FIRST record is an unclassified stub.
        try:
            bib.verify_book("Patrick Rothfuss", "The Name of the Wind", 2007)
            failures.append("FIELD live: the fantasy novel verified as a source")
        except bib.Unverified:
            pass
        try:
            bib.verify_book("Robert M. Sapolsky", "Why Zebras Don't Get Ulcers", 1994)
        except bib.Unverified as why:
            failures.append(f"FIELD live: a real psychology book was refused ({why})")

        if bib.verify_phrase("emotional flashback") < bib.MIN_INSIDE_HITS:
            failures.append("GATE3 a real term of art was not found in scanned books")
        for fake in ("hippocampal shame spiral", "the vibe collapse effect"):
            try:
                bib.verify_phrase(fake)
                failures.append(f"GATE3 an invented term verified: {fake}")
            except bib.Unverified:
                pass
    except bib.Unverified as why:
        skipped = 1
        print(f"  (catalogue unreachable, its cases skipped: {str(why)[:70]})")

    total = (6 + 2 + 1 + 2 + 2 + 2 + 3 + 2          # claims, linkage, accents, closed, line…
             + 6 + 5 + 3 + 5 + 4 + 1                # …the subject classes, and the address
             + (0 if skipped else 9))
    if failures:
        print(f"bibliography: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"bibliography: {total}/{total} passed "
          f"(uncheckable claims, phrase linkage, accents, failing closed, line assembly, "
          f"pool growth, rotation, subject classification, one request, user agent"
          f"{'' if skipped else ', live catalogue'})")
    return 0


def test_bibliography():
    """So `pytest tests/test_bibliography.py` runs the same suite CI runs.

    CI executes each file with `python test_x.py`, which is what `run()` and the
    block below are for. This wrapper adds nothing except a name pytest will
    collect, so both ways of asking produce the same answer.
    """
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
