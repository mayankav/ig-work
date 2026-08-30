#!/usr/bin/env python3
"""
Writer regression. No network.

The writer is two model calls with deterministic checks on both sides, and the
checks are the part worth testing: they are what stands between a plausible
plan and nine slides built on it.

Three of these cases exist because the live model actually did the thing.

  BORROWED   the prompt shows the required shape of a script, and the model
             handed back a script about declining an invitation inside a deck
             about waking at 2am. Right shape, wrong deck.
  MASCOT     it wrote "a glowing alarm clock that reads 2:17am". Text in the
             artwork is banned outright: an earlier pipeline shipped nine slides
             with captions printed on the donkey.
  ACCENT     it returned a complete, well-formed deck with no [[accent]] on any
             slide. Nothing in a JSON schema can express "exactly one of these
             per slide", so it is checked on the assembled markdown.
"""
import copy as copymod
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import render  # noqa: E402
import writer  # noqa: E402

MOMENT = "I woke at 2:17am with my heart pounding and watched the clock until six."


def good_plan() -> dict:
    beats = [
        (1, "hook", "Clock maths. You wake at 2:17am and start working out what is left."),
        (2, "cost", "What the watching costs the next morning."),
        (3, "source", "Checking the time turns a waking into a maths problem."),
        (4, "name", "Name the pattern: clock maths."),
        (5, "script", "The words to say instead of doing the maths."),
        (6, "action", "Turn the clock away, at a named time, in the bedroom."),
        (7, "sustain", "Three small moves that keep it going tomorrow."),
        (8, "cheat", "Recap the clock turn, the words and the breathing."),
        (9, "cta", "Send it to whoever does maths in the dark."),
    ]
    return {
        "scene_token": "2:17am",
        "pattern_name": "clock maths",
        "citation_id": "espie-2006",
        "claim_index": 0,
        "protocol": {
            "script": "The [waking] is here. I am not checking the clock.",
            "intention": "I will turn the clock to the wall at 10pm in the bedroom",
            "if_then": "If I wake and reach for the clock, then I leave it turned away",
            "menu": ["Turn the clock to the wall", "Breathe out slowly for one minute",
                     "Sit in low light until heavy"],
        },
        "beats": [{"n": n, "role": r, "beat": b, "exports": [], "depends_on": [],
                   "accent_word": "clock"} for n, r, b in beats],
        "hooks": [{"h1": "You woke at 2:17am and watched the [[clock]].", "h2": "(the maths in the dark)"},
                  {"h1": "The maths [[started]].", "h2": "In the dark."}],
        "dm_share_hypothesis": "They will send this to whoever else is awake at that hour.",
    }


def broken(**changes) -> dict:
    plan = good_plan()
    for path, value in changes.items():
        if "." in path:
            head, tail = path.split(".", 1)
            plan[head][tail] = value
        else:
            plan[path] = value
    return plan


SHIPPED_BROKEN = """### Slide 1 · Hook
- **H1:** Cleaning up the kitchen while everyone else is [[asleep]].
### Slide 2 · Agitation
- **Body:** Cleaning up the kitchen while everyone else is [[asleep]].
### Slide 3 · Source Anchor
- **Source:** — Pete Walker, *Complex PTSD: From Surviving to Thriving* (2013)
- **Source Claim:** Walker found that appeasing is learned where it worked, which is why it arrives.
- **What This Explains Here:** Walker found that appeasing is learned where it worked, which is why it arrives.
### Slide 5 · Value Step 2
- **✅ Regulated Response:** "Say out loud: The bowl is [[done]]. Walker found that leaving is learned."
"""


# Words that belong in a paper and not on a slide. The deck that shipped told a
# reader that "appeasing is learned where it worked, which is why it arrives
# before you have decided anything", and that sentence came from our own
# citations file, not from a model. Half the claims in that file were over
# twenty words with a clause hung off a clause.
PAPER_WORDS = ("appeas", "residue", "rehearsal", "standby", "circuit", "salience",
               "arousal", "latency", "schema", "mechanism", "attunement", "dysregulat",
               "modality", "construct", "cognitive", "affective", "survival style")
CLAIM_WORD_CAP = 18


TYPOS = """### Slide 5 · Value Step 2
- **\u274c Old Reaction:** "You hear the sound and you [[decid]] to open it immediately."
- **\u2705 Regulated Response:** "I will keep the [[peac]] until morning."
### Slide 8 · Cheat Sheet
- **Body:** Pick your line [[befor]] the neighbour knocks.
"""

CLEAN = """### Slide 3 \u00b7 Source Anchor
- **Source:** \u2014 Stephen Porges, *The Polyvagal Theory* (2011)
- **Source Claim:** Porges found the body decides a room is safe before you have thought.
### Slide 5 · Value Step 2
- **\u2705 Regulated Response:** "I am in my pyjamas and I am not answering tonight."
"""


def run() -> int:
    failures = []

    # A deck that scored 82 and would have posted carried "you decid to open
    # it", "keep the peac" and "your line befor the neighbour knocks". Two
    # letters missing each, on a public account, and nothing in thirty-odd gates
    # was looking at spelling at all.
    found = writer.check_spelling(TYPOS)
    for typo in ("decid", "peac", "befor"):
        if not any(typo in f for f in found):
            failures.append(f"SPELL {typo!r} was not caught: {found}")

    # And it has to stay quiet about the things that are not mistakes. A speller
    # that blocks a deck for British English, or for the surname of the
    # researcher the citation names, is worse than no speller — the citation
    # line is written by code from a verified allowlist and is correct by
    # construction.
    for note in writer.check_spelling(CLEAN):
        failures.append(f"SPELL a correct deck was flagged: {note}")

    # Both loops must be able to REACH their own failure. plan_deck raised a
    # NameError on the line that reports a refusal, because a variable was
    # removed when the loop learned to keep its best attempt and one reference
    # to it survived. Every test passed; the fault only appears on the path
    # where a plan cannot be fixed, which is the path CI takes on a bad night.
    import llm as _llm
    for name, fn in (("plan_deck", lambda: writer.plan_deck("a moment", "sleep")),
                     ("write_deck", lambda: writer.write_deck(
                         "a moment", "sleep", title="t", pattern="p", pillar="P"))):
        real = _llm.ask
        _llm.ask = lambda *a, **k: (_ for _ in ()).throw(_llm.ModelRefused("no vendor"))
        try:
            fn()
            failures.append(f"REFUSAL {name} returned instead of refusing")
        except _llm.ModelRefused:
            pass
        except Exception as other:                          # noqa: BLE001
            failures.append(f"REFUSAL {name} raised {type(other).__name__}: {other}")
        finally:
            _llm.ask = real

    # Slide 3 is the one card a reader has to understand on the first read. It
    # is code that puts these words there, so nothing downstream can fix them.
    for citation in writer.load_citations().values():
        for claim in citation.get("claims", []):
            words = len(claim.split())
            if words > CLAIM_WORD_CAP:
                failures.append(f"CLAIM {words} words, cap {CLAIM_WORD_CAP}: {claim[:56]}")
            found = [w for w in PAPER_WORDS if w in claim.lower()]
            if found:
                failures.append(f"CLAIM uses {', '.join(found)}, which nobody says: {claim[:48]}")

    # The three faults a reader could see on the deck that shipped. Slide 1 and
    # slide 2 printed one sentence twice, slide 3 printed another under two
    # different headings, and the script told the reader to say a citation out
    # loud in their own kitchen — which this file caused, by telling slides 4 to
    # 7 to reuse slide 3's words without saying to leave the sentence behind.
    repeats = writer.check_repeats(SHIPPED_BROKEN)
    if sum("are the same line" in p for p in repeats) != 2:
        failures.append(f"REPEAT duplicated lines were not both caught: {repeats}")
    if not any("out loud" in p for p in repeats):
        failures.append("REPEAT a script quoting the researcher was accepted")

    # And it must not fire on decks that name the researcher in the ordinary
    # way, in the alt text or in passing. All three hand-written decks do.
    import pathlib as _p
    decks = sorted((_p.Path(__file__).resolve().parents[3] / "carousels").glob("*/carousel.md"))
    for deck in decks:
        text = deck.read_text(encoding="utf-8")
        if "Slide 5" not in text:
            continue
        for fault in writer.check_repeats(text):
            if "out loud" in fault:
                failures.append(f"REPEAT {deck.parent.name} blocked for crediting a source: {fault}")

    # ── the angles ──
    if writer.combinations() != 2688:
        failures.append(f"expected 2688 structural combinations, got {writer.combinations()}")
    if writer.draw_axes(MOMENT) != writer.draw_axes(MOMENT):
        failures.append("the same moment planned two different ways, so a rerun is not reproducible")
    spread = {tuple(writer.draw_axes(f"moment number {i}").values()) for i in range(60)}
    if len(spread) < 40:
        failures.append(f"60 moments landed in only {len(spread)} corners, the draw is clumping")

    # ── a good plan passes ──
    problems = writer.validate_plan(good_plan(), MOMENT, "sleep")
    if problems:
        failures.append(f"a good plan was rejected: {problems}")

    # ── each way a plan goes wrong ──
    beats_wrong_order = good_plan()["beats"]
    beats_wrong_order[3], beats_wrong_order[4] = beats_wrong_order[4], beats_wrong_order[3]
    cases = [
        ("a citation that is not on the allowlist", broken(citation_id="freud-1899"), "allowlist"),
        ("a citation that does not cover the subject", broken(citation_id="tawwab-2021"), "does not cover"),
        ("beats out of their fixed order", broken(beats=beats_wrong_order), "role order"),
        # A token this moment really does contain, which never reaches slide 1.
        ("a scene token missing from slide 1", broken(scene_token="body"), "missing from slide 1"),
        # The name is the thing a reader repeats and sends on, so it has to be
        # on the only slide most people see.
        ("a pattern name that never reaches slide 1",
         broken(pattern_name="the quiet tax"), "missing from slide 1"),
        ("a pattern name that is a sentence, not a handle",
         broken(pattern_name="you cannot sit down until it is clear"), "two or three"),
        # The pillar is the shelf, not the thing. A deck written by the weakest
        # vendor came back naming its pattern "Boundaries", with slide 4 reading
        # "the name of this pattern is boundaries".
        ("a pattern name that is just the subject",
         broken(pattern_name="boundaries"), "just the subject"),
        # A token invented from the moment's wording rather than taken from the
        # list. This is what the plan actually did: "doorway" for a moment about
        # a door, and slide 1 was then refused by a checker reading a different
        # vocabulary.
        ("a scene token that is not one of the moment's things",
         broken(scene_token="doorway"), "not one of the things in this moment"),
        ("a script with no bracket to fill in",
         broken(**{"protocol.script": "The waking is here. I am not checking."}), "bracket"),
        ("an intention with no time or place",
         broken(**{"protocol.intention": "I will turn the clock away"}), "time and place"),
        ("an if-then that is not one",
         broken(**{"protocol.if_then": "Leave the clock turned away when you wake"}), "if-then"),
        ("a menu option that is not a move",
         broken(**{"protocol.menu": ["Figure out why you woke", "Breathe out", "Sit up"]}), "concrete move"),
        # The live failure: right shape, wrong deck.
        ("advice borrowed from the prompt's example", broken(**{
            "protocol.script": "I cannot make it to [your birthday]. Hope you have a good one.",
            "protocol.intention": "I will send the message at 9am in the hallway",
            "protocol.if_then": "If the invitation arrives, then I reply within ten minutes",
            "protocol.menu": ["Send one line", "Delete the reasons", "Put the phone down"],
        }), "borrowed example"),
    ]
    for description, plan, expected in cases:
        found = writer.validate_plan(plan, MOMENT, "sleep")
        if not found:
            failures.append(f"PLAN accepted {description}")
        elif expected and not any(expected in f for f in found):
            failures.append(f"PLAN wrong reason for {description}: {found}")

    # A claim index of 1 is valid for espie-2006, so that case should pass.
    if writer.validate_plan(broken(claim_index=1), MOMENT, "sleep"):
        failures.append("PLAN rejected a valid second claim")

    # ── hooks ──
    if not writer.hook_ok({"h1": "You woke at 2:17am and watched the [[clock]].", "h2": "(the maths)"}):
        failures.append("HOOK a good hook was refused")
    for h1, h2, why in [
        ("Why you wake at 2:17am every [[night]]", "(the maths)", "banned opener"),
        ("You woke at [[2:17am]]", "Your heart was a drum solo in the dark tonight", "long subtitle"),
        ("You woke at 2:17am with your nervous system on [[alert]]", "(the maths)", "jargon"),
        ("You woke at 2:17am and watched the clock.", "(the maths)", "missing accent"),
    ]:
        if writer.hook_ok({"h1": h1, "h2": h2}):
            failures.append(f"HOOK accepted a hook with a {why}")

    chosen = writer.best_hook(good_plan(), "2:17am")
    if "2:17am" not in chosen["h1"]:
        failures.append("HOOK picked the vague hook over the one naming the moment")

    # The subtitle on the only slide most people see. A deck that posted said
    # "Execution freeze. You remain anchored to the bed even when awake." and
    # then "Execution freeze. Anchored to the bed." underneath it.
    repeated = {"h1": "Execution freeze. You remain anchored to the [[bed]] even when awake.",
                "h2": "Execution freeze. Anchored to the bed."}
    faults = writer.hook_faults(repeated, "Execution freeze")
    if not any("only repeats h1" in f for f in faults):
        failures.append(f"HOOK a subtitle repeating the headline was accepted: {faults}")
    if not any("again" in f for f in faults):
        failures.append(f"HOOK a subtitle repeating the name was accepted: {faults}")
    adds = dict(repeated, h2="The morning goes while you stand.")
    if writer.hook_faults(adds, "Execution freeze"):
        failures.append(f"HOOK a subtitle that adds something was refused: "
                        f"{writer.hook_faults(adds, 'Execution freeze')}")

    # One deck, one name. The same deck led with "Execution freeze" and coined
    # "the traction gap" on slide 4, so a reader had two handles and kept none.
    two_names = broken(pattern_name="clock maths")
    two_names["beats"][3]["beat"] = "Name the pattern: the traction gap."
    two_names["beats"][3]["exports"] = ["the traction gap"]
    if not any("invents a second one" in problem for problem in
               writer.validate_plan(two_names, MOMENT, "sleep")):
        failures.append("NAME slide 4 coining a second name was accepted")

    # Tags are picked by code from a vetted list, the same as the citation. A
    # deck went out tagged #transitionfreeze — a name we had coined an hour
    # earlier that nobody has ever searched for — beside #psychology, which a
    # page this size will never surface in.
    tags = writer.pick_hashtags("people_pleasing", "some-deck")
    if not 3 <= len(tags) <= 5:
        failures.append(f"TAGS wrong number for a deck: {tags}")
    if any("#" in t or " " in t or t != t.lower() for t in tags):
        failures.append(f"TAGS malformed: {tags}")
    if len(set(tags)) != len(tags):
        failures.append(f"TAGS repeated: {tags}")
    # Findable by people browsing the subject, not only by people browsing
    # everything: most of them come from the subject's own list.
    import json as _json
    bank = _json.loads((pathlib.Path(__file__).resolve().parent.parent
                        / "references" / "hashtags.json").read_text(encoding="utf-8"))
    if sum(1 for t in tags if t in bank["people_pleasing"]) < 2:
        failures.append(f"TAGS too few from the subject itself: {tags}")
    # Two decks on one subject must not carry identical tags.
    if len({tuple(writer.pick_hashtags("sleep", f"d{i}")) for i in range(12)}) < 4:
        failures.append("TAGS every deck on a subject gets the same tags")
    # A subject with no list is silence, not a crash.
    if writer.pick_hashtags("not_a_subject_we_have", "x") != [bank["always"][0]] and \
            len(writer.pick_hashtags("not_a_subject_we_have", "x")) > 1:
        failures.append("TAGS an unknown subject produced subject tags")

    # Slides 5 and 6 print a condition and a line, under "when" and "say".
    #
    # They used to print under WHAT YOU SAY and TRY THIS INSTEAD, and a deck
    # went out with "You stand up and walk to the hallway." under the first — a
    # stage direction about the reader, in quotes, under a label saying they
    # said it. The content playbook had already deprecated that pair in as many
    # words. The code never followed.
    wrong = """### Slide 5 · Value Step 2
- **When:** "You stand up and walk to the [[hallway]]."
- **Say:** "You whisper: the task is [[done]]. What is the smallest action you can take?"
"""
    faults = writer.check_spoken(wrong)
    if not any("quotation marks" in f for f in faults):
        failures.append(f"SPOKEN a quoted condition was accepted: {faults}")
    if not any("narrates the reader" in f for f in faults):
        failures.append(f"SPOKEN a Say line narrating the reader was accepted: {faults}")
    if not any("coaching" in f for f in faults):
        failures.append(f"SPOKEN a coaching question inside a script was accepted: {faults}")

    # And the shape the playbook asked for has to stay clean. Second person is
    # right in a condition — it is about them, and they can check it.
    right = """### Slide 5 · Value Step 2
- **When:** You are standing in the hallway with the cup still in your [[hand]].
- **Say:** "I will move the cup to the [[sink]] before I sit down."
### Slide 6 · Value Step 3
- **When:** The reply has been typed and not [[sent]] for ten minutes.
- **Say:** "Hey, my brain is inventing a story. Are we [[good]]?"
"""
    if writer.check_spoken(right):
        failures.append(f"SPOKEN the shape the playbook asked for was refused: "
                        f"{writer.check_spoken(right)}")

    # ── mascots ──
    for briefs, why in [
        (["a donkey looking at a clock that reads 2:17am"] + ["a donkey sitting"] * 8, "text in the artwork"),
        (["a donkey standing, ears back"] + ["a donkey that looks anxious"] + ["x"] * 7, "a feeling"),
    ]:
        if not writer.check_mascots(briefs):
            failures.append(f"MASCOT accepted {why}")
    same = ["a donkey stands in a dark room beside a bed with ears lowered"] * 9
    if not any("same picture" in p for p in writer.check_mascots(same)):
        failures.append("MASCOT accepted nine identical briefs")

    # ── accents ──
    if not writer.check_accents("### Slide 1 · Hook\n- **H1:** You woke at 2:17am.\n"):
        failures.append("ACCENT accepted a slide with none")
    if not writer.check_accents("### Slide 1 · Hook\n- **H1:** You [[woke]] at [[2:17am]].\n"):
        failures.append("ACCENT accepted two in one field")
    if writer.check_accents("### Slide 1 · Hook\n- **H1:** You woke at [[2:17am]].\n"):
        failures.append("ACCENT refused a correct slide")

    # ── the markdown the renderer has to read back ──
    plan = good_plan()
    citation = writer.load_citations()["espie-2006"]
    copy = {
        "cost": {"h2": "The [[maths]] begins.", "body": "You watched the clock until six and paid for it all [[day]]."},
        "translation": "Knowing the time starts a [[countdown]] you cannot stop.",
        "explains": "That is why the waking itself was never the [[problem]].",
        "name": {"h2": "Call it clock [[maths]].", "body": "Waking is ordinary. Doing the sums is what finishes [[waking]] you."},
        "script": {"h2": "The [[words]] for 2:17am.", "old": "I have ruined [[tomorrow]].",
                   "new": "Waking is ordinary. I do not need the [[time]]."},
        "action": {"h2": "Turn it [[away]].", "old": "I check how long is [[left]].",
                   "new": "I will turn the clock to the wall at 10pm in the [[bedroom]].",
                   "body": "If you wake and reach for the clock, then leave it turned [[away]]."},
        "sustain": {"h2": "Three small [[moves]].", "bullets": ["Clock to the [[wall]] before bed",
                                                                "One warm [[lamp]], no ceiling light",
                                                                "Out of bed after twenty [[minutes]]"]},
        "cheat": {"h2": "Your 2:17am [[card]].", "callout": "Save this for tonight",
                  "bullets": ["Say it: waking is [[ordinary]]", "Clock to the [[wall]] before bed",
                              "If awake past twenty minutes, then sit in low [[light]]"]},
        "cta": {"cta1": "Send this to the friend who does maths at [[2:17am]].",
                "closing": "The waking was ordinary. The [[countdown]] is what took the night."},
        "caption": "You woke at 2:17am again. " * 12,
        "hashtags": ["#insomnia", "#sleep", "#nightwaking", "#anxiety"],
        "alt": [f"description of slide {i}" for i in range(1, 10)],
        "mascots": [f"a donkey doing distinct thing number {i} with a different prop" for i in range(1, 10)],
    }
    markdown = writer.assemble(plan, copy, plan["hooks"][0], citation,
                               citation["claims"][0], copy["mascots"],
                               "Waking At The Same Hour", "Hidden Mechanism", "Sleep")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(markdown)
        path = pathlib.Path(handle.name)
    try:
        slides = render.parse_markdown(path)
        if len(slides) != 9:
            failures.append(f"ASSEMBLE the renderer read back {len(slides)} slides, not 9")
        else:
            if slides[0].get("h1") != plan["hooks"][0]["h1"]:
                failures.append("ASSEMBLE the hook did not survive the round trip")
            if "source" not in slides[2]:
                failures.append("ASSEMBLE the citation line did not survive")
            if len(slides[7].get("bullets", [])) != 3:
                failures.append("ASSEMBLE the cheat sheet bullets did not survive")
            if slides[4].get("old_reaction") is None:
                failures.append("ASSEMBLE the old and new script lines did not survive")
        if writer.check_accents(markdown):
            failures.append(f"ASSEMBLE accents broke in assembly: {writer.check_accents(markdown)}")
    finally:
        path.unlink(missing_ok=True)

    total = 22 + 3 + 1 + len(cases) + 1 + 5 + 3 + 3 + 5
    # ── the field's name, on a concept deck ──
    #
    # A deck built from a proved concept carries a second name: the plain handle
    # the writer coins for slide 1, and the word the field actually uses. That
    # second word is the ONLY thing a concept deck has that a harvested one does
    # not — without it the concept picks the subject and is then discarded, and
    # the two channels produce identical decks.
    #
    # Both halves are checked, because they pull opposite ways. It has to be
    # printed on slide 4, and it must not appear before slide 3: slide 1 is a
    # scene in plain words, and a reader who meets a clinical term before they
    # have recognised themselves stops reading.
    plan = good_plan()
    plan["beats"][3]["beat"] = "Name the pattern: clock maths. This has a name: akrasia."
    if any("akrasia" in p for p in writer.validate_plan(plan, MOMENT, "sleep", term="akrasia")):
        failures.append("TERM a plan that prints the term on slide 4 was refused")

    # Missing from slide 4 — the concept was thrown away.
    if not any("slide 4 does not print" in p
               for p in writer.validate_plan(good_plan(), MOMENT, "sleep", term="akrasia")):
        failures.append("TERM a plan that never prints the term was allowed")

    # On slide 1, where the brand rule says plain words only.
    early = good_plan()
    early["beats"][3]["beat"] = "Name the pattern: clock maths. This has a name: akrasia."
    early["beats"][0]["beat"] = "Akrasia. You wake at 2:17am and start working out what is left."
    if not any("before slide 3" in p
               for p in writer.validate_plan(early, MOMENT, "sleep", term="akrasia")):
        failures.append("TERM the term reached slide 1 and was allowed")

    # A feed deck passes no term, and nothing about it changes.
    if writer.validate_plan(good_plan(), MOMENT, "sleep") != writer.validate_plan(
            good_plan(), MOMENT, "sleep", term=""):
        failures.append("TERM an empty term changed the verdict on a feed deck")

    if failures:
        print(f"writer: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"writer: {total}/{total} passed "
          f"(2688 angles, {len(cases)} plan faults, hooks, mascots, accents, round trip)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
