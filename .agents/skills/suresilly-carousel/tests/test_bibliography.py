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

    total = 6 + 2 + 1 + 2 + 2 + 2 + 3 + 2 + (0 if skipped else 7)
    if failures:
        print(f"bibliography: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"bibliography: {total}/{total} passed "
          f"(uncheckable claims, phrase linkage, accents, failing closed, line assembly, "
          f"pool growth, rotation{'' if skipped else ', live catalogue'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
