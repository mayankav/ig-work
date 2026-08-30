#!/usr/bin/env python3
"""
Story-gate regression.

A deck can pass every per-slide check and still be nine unrelated slides. These
gates ask whether it holds together, and they are tuned against both populations
we have: the three hand-written decks, which must always pass, and synthetic
versions of the failure that shipped, which must always be caught.

The gate that matters most is FOREIGN. A deck about waking at 2:17am once went
out carrying "17 tabs", "2:47pm" and a waiting-mode cheat sheet, because the
generator stitched a fixed template onto whatever hook it drew. Every slide was
individually well-formed, so nothing else noticed.

Tuning note, because these limits were wrong twice before they were right:
a good cheat sheet rewords heavily — our own decks introduce 56% new vocabulary
when they compress four slides onto one card — so the gate counts new IDEAS, a
concrete detail or a named pattern, never new words. And a hook that opens on a
dropping stomach is properly paid off by a tightening chest, so every body
sensation folds to one anchor.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import coherence  # noqa: E402
import screen  # noqa: E402
import render  # noqa: E402

CAROUSELS = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent / "carousels"

TEXT_KEYS = ("h1", "h2", "body", "source_claim", "source_translation", "source_explains",
             "old_reaction", "new_reaction", "myth", "reality", "closing", "cta1", "callout")


def text_of(slide: dict) -> str:
    return " ".join([str(slide[k]) for k in TEXT_KEYS if k in slide] + slide.get("bullets", []))


def fake(n: int, **fields) -> dict:
    return {"role": f"slide{n}", **fields}


def coherent_deck() -> list[dict]:
    """The shape a deck should have: one moment, carried the whole way."""
    return [
        fake(1, h1="You woke at 2:17am with your heart [[pounding]]."),
        fake(2, body="If you have ever woken at 2:17am and watched the clock until six, this is for [[you]]."),
        fake(3, source_claim="Brief wakings between sleep cycles are ordinary. Learning the time starts a [[countdown]]."),
        fake(4, h2="Name the [[countdown]].", body="Waking is ordinary. Knowing it is 2:17am is what finishes waking you up."),
        fake(5, old_reaction="I have ruined tomorrow.", new_reaction="Waking is ordinary. I do not need the [[time]]."),
        fake(6, body="If you wake and reach for the clock, then leave it turned away and breathe out [[slowly]]."),
        fake(7, body="Rest counts as rest. Lying still with your eyes closed restores more than the [[countdown]] allows."),
        fake(8, h2="Your 2:17am [[card]].", bullets=["Turn the clock to the wall before bed",
                                                     "Say it: waking is ordinary, no [[countdown]]",
                                                     "If you are awake past twenty minutes, then sit in low light"]),
        fake(9, cta1="Send this to the friend who does maths at [[2:17am]].",
             closing="The wakings were ordinary. The countdown is what took the [[night]]."),
    ]


def run() -> int:
    failures = []

    # 1. Real decks must never be blocked.
    decks = sorted(CAROUSELS.glob("*/carousel.md"))
    for path in decks:
        problems = coherence.check(render.parse_markdown(path), text_of)
        if problems:
            failures.append(f"REAL {path.parent.name} blocked: {problems[0]}")

    # 2. A well-formed synthetic deck passes.
    good = coherent_deck()
    problems = coherence.check(good, text_of, moment_anchors={"clock", "2:17am", "bed"})
    if problems:
        failures.append(f"SYNTHETIC coherent deck blocked: {problems[0]}")

    # 3. The original bug: another moment's details inside this deck.
    contaminated = coherent_deck()
    contaminated[5] = fake(6, body="If you are hovering at your desk with 17 tabs open, then set a 10 minute [[timer]].")
    problems = coherence.check(contaminated, text_of, moment_anchors={"clock", "2:17am", "bed"})
    # Caught by the thread check, not by counting nouns. Advice about tabs stops
    # explaining a slide about sleep cycles, and that is the real complaint —
    # "desk" is not, because good decks say "desk" too.
    if not any("does not connect back to the explanation" in p for p in problems):
        failures.append("FOREIGN a waiting-mode slide inside a 2:17am deck was not caught")

    # A different evening, which is what the foreign-scene gate is now for. The
    # deck that shipped broken opened at 2:17am and gave its advice at 2:47pm.
    wrong_time = coherent_deck()
    wrong_time[5] = fake(6, body="If you wake and reach for the clock at 2:47pm, then leave it turned [[away]].")
    if not any("not when this moment happened" in p
               for p in coherence.check(wrong_time, text_of, moment_anchors={"2:17am"})):
        failures.append("FOREIGN a deck giving 2:17am advice at 2:47pm was not caught")

    # The test whose absence let all of this ship. Every gate above was checked
    # against decks that must FAIL and never against one that must PASS, so the
    # foreign-scene gate ran for months rejecting all four decks we know to be
    # good — a deck about watching the clock was refused for saying "clock".
    # Any gate keyed on moment_anchors must clear the real decks first.
    for path in sorted(CAROUSELS.glob("*/carousel.md")):
        slides = render.parse_markdown(path)
        hook_words = {w.lower() for values in
                      screen.screen(text_of(slides[0]))["anchors"].values() for w in values}
        blocked = coherence.check(slides, text_of, moment_anchors=hook_words)
        if blocked:
            failures.append(f"REAL {path.parent.name} blocked by a moment-anchor gate: {blocked[0]}")

    # 4. A cheat sheet that abandons the moment.
    drifted = coherent_deck()
    drifted[7] = fake(8, h2="Your evening [[card]].", bullets=["Put the phone in another room",
                                                               "Drink water before bed"])
    if not any("cheat sheet never comes back" in p for p in coherence.check(drifted, text_of)):
        failures.append("MOMENT a cheat sheet that dropped the moment was not caught")

    # 5. Advice that has stopped explaining what slide 3 named.
    unthreaded = coherent_deck()
    unthreaded[4] = fake(5, old_reaction="Mornings are hard.", new_reaction="I will buy better [[curtains]].")
    if not any("does not connect back to the explanation" in p for p in coherence.check(unthreaded, text_of)):
        failures.append("THREAD an advice slide that abandoned slide 3 was not caught")

    # 6. Slide 2 must stand alone, because it is served cold as a second cover.
    dangling = coherent_deck()
    dangling[1] = fake(2, body="That is what happens every night in the [[bed]] and it never stops.")
    if not any("stand alone" in p for p in coherence.check(dangling, text_of)):
        failures.append("COVER a slide 2 opening on a back-reference was not caught")

    # 7. A cheat sheet inventing a new named pattern.
    invented = coherent_deck()
    invented[7] = fake(8, h2="Your 2:17am [[card]].", bullets=["Turn the clock to the wall before bed",
                                                               "Run the [[sleep restriction]] protocol nightly"])
    if not any("introduces" in p for p in coherence.check(invented, text_of)):
        failures.append("NEW-IDEA a cheat sheet inventing a new named pattern was not caught")

    checks = len(decks) * 2 + 7
    if failures:
        print(f"coherence: {len(failures)}/{checks} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"coherence: {checks}/{checks} passed "
          f"({len(decks)} real decks clean, and clean again against their own "
          f"anchors, wrong time, foreign scene, drifted cheat, broken thread, "
          f"weak second cover and invented idea all caught)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
