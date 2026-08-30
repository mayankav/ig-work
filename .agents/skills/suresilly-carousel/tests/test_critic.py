#!/usr/bin/env python3
"""
Critic decision regression. No network.

The critic is the last thing before publishing and the only step whose job is to
argue against the deck. So the cases here are about the two ways that goes
wrong: a gate that waves everything through, and a gate that blocks everything.

Both were observed. The first version honoured the model's BLOCK unconditionally,
and since the prompt asks it to argue against every deck, nothing would ever have
published. The severity rules underneath it were decorative. A veto now has to be
grounded in an objection the model could actually quote.

The inconclusive case is here because of a bug that lived for about ten minutes:
an unreachable critic made every canary report "caught", so a total outage looked
like a perfectly working gate. A drift detector that passes when nothing ran is
worse than no detector, because it gets trusted.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import critic  # noqa: E402
import llm  # noqa: E402

DECK = ("### Slide 1\n- **H1:** You woke at 2:17am and watched the clock.\n"
        "### Slide 4\n- **Body:** Waking in the night is ordinary and the maths is what wakes you.\n"
        "### Slide 6\n- **Body:** Turn the clock to the wall at 10pm in the bedroom.\n")


def objection(**over) -> dict:
    base = {"category": "H8_VOICE", "slide": 4, "quote": "Waking in the night is ordinary",
            "severity": 2, "why": "a little flat"}
    base.update(over)
    return base


def reply(objections=None, verdict="PUBLISH", confidence=0.9) -> dict:
    return {
        "case_for_rejection": "It leans on a familiar framing and could read as generic advice.",
        "objections": objections if objections is not None else [],
        "verdict": verdict,
        "confidence": confidence,
    }


CASES = [
    ("a clean deck", reply(), True),
    ("one mild objection", reply([objection()]), True),

    ("something a reader could be harmed by", reply([objection(severity=5)]), False),
    ("something that would be screenshotted to mock", reply([objection(severity=4)]), False),
    ("a hard category at severity three",
     reply([objection(category="H1_HARM_ADVICE", severity=3)]), False),
    # A soft category at three is a real note, not a reason to spike a deck.
    ("a soft category at severity three", reply([objection(severity=3)]), True),
    ("three separate small defects",
     reply([objection(), objection(slide=6, quote="Turn the clock to the wall"),
            objection(slide=1, quote="You woke at 2:17am")]), False),

    ("a veto backed by a real objection", reply([objection(severity=3)], verdict="BLOCK"), False),
    # The bug that would have stopped every post: an argument with nothing under it.
    ("a veto with nothing under it", reply([objection(severity=2)], verdict="BLOCK"), True),
    ("a veto with no objections at all", reply(verdict="BLOCK"), True),

    ("low confidence", reply(confidence=0.4), False),
]


def run() -> int:
    failures = []

    for description, answer, expected in CASES:
        published, reason, _ = critic.decide(answer, DECK)
        if published != expected:
            failures.append(
                f"{description}: expected {'publish' if expected else 'block'}, "
                f"got {'publish' if published else 'block'} ({reason})")

    # An objection the model cannot quote is deleted rather than argued with.
    published, _, kept = critic.decide(
        reply([objection(quote="a sentence that is nowhere in this deck", severity=5)]), DECK)
    if kept:
        failures.append("an unquotable objection was kept")
    if not published:
        failures.append("an unquotable objection still blocked the deck")

    # Harm is the exception. The critic caught a canary deck full of dangerous
    # medical advice, quoted it loosely, the objection was dropped for not
    # matching word for word, and the deck published. Refusing a good deck costs
    # an evening; publishing advice that hurts somebody costs more than the
    # account, so a BLOCK naming a harm category stands without a usable quote.
    for category in sorted(critic.BLOCKS_WITHOUT_A_QUOTE):
        published, reason, _ = critic.decide(
            reply([objection(category=category, quote="not in the deck at all", severity=5)],
                  verdict="BLOCK"), DECK)
        if published:
            failures.append(f"HARM a BLOCK naming {category} published for want of a quote")

    # H3 is the exception to the exception. The line it disputes is the citation,
    # which code substituted from the allowlist, and honouring an unquotable H3
    # puts a model back in charge of a source it cannot check. It blocked all
    # three hand-written decks the last time it was allowed to.
    published, _, _ = critic.decide(
        reply([objection(category="H3_FALSE_PSYCH", quote="not in the deck at all", severity=5)],
              verdict="BLOCK"), DECK)
    if not published:
        failures.append("H3 an unquotable citation dispute blocked the deck")

    # Past a couple, the model is composing rather than reading, so its approval
    # is worth no more than its objections.
    invented = [objection(quote=f"invented sentence number {i}", severity=2) for i in range(4)]
    published, reason, _ = critic.decide(reply(invented), DECK)
    if published:
        failures.append("a reply full of invented quotes was still trusted")
    elif "invented" not in reason:
        failures.append(f"invented quotes were not named as the reason: {reason}")

    # ── the vendor rule ──
    allowed = [name for name, _ in critic.available_providers("gemini")]
    if "gemini" in allowed:
        failures.append("a deck could be reviewed by the vendor that wrote it")
    if not critic.available_providers(None):
        failures.append("no provider is available when nothing is excluded")
    if critic.available_providers("gemini") and critic.available_providers("groq") == \
            critic.available_providers("gemini"):
        failures.append("excluding a vendor changed nothing")

    # ── schema ──
    for description, answer in [
        ("a category we never offered", reply([objection(category="H99_INVENTED")])),
        ("severity below the floor", reply([objection(severity=1)])),
        ("a missing case for rejection", {k: v for k, v in reply().items()
                                          if k != "case_for_rejection"}),
        ("a verdict we never offered", reply(verdict="MAYBE")),
    ]:
        if not llm.validate(answer, critic.SCHEMA):
            failures.append(f"schema accepted {description}")

    # ── canaries ──
    labels = {label for label, _ in critic.CANARY_DECKS}
    for needed in ("harm advice", "false claim", "diagnosis", "incoherent"):
        if needed not in labels:
            failures.append(f"no canary covers {needed}")
    if len(critic.CANARY_DECKS) < 5:
        failures.append("too few canary decks to notice drift")

    total = len(CASES) + 3 + 3 + 4 + 5 + len(critic.BLOCKS_WITHOUT_A_QUOTE) + 1
    if failures:
        print(f"critic: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"critic: {total}/{total} passed "
          f"({len(CASES)} decision rules, unquotable objections, harm blocks without "
          f"a quote, vendor separation, "
          f"schema, {len(critic.CANARY_DECKS)} canary decks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
