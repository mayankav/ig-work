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


def reply(objections=None, verdict="PUBLISH", confidence=0.9, score=90) -> dict:
    return {
        "score": score,
        "summary": "It leans on a familiar framing and could read as generic advice.",
        "objections": objections if objections is not None else [],
        "verdict": verdict,
        "confidence": confidence,
    }


# (description, reply, expected outcome)
#
# Three outcomes now, and the middle one is the point of the rewrite. "review"
# is not a refusal: the deck is finished and held, and a person decides. Only
# harm and an invented claim reach "block", where there is no approval path,
# because that decision would otherwise arrive on a phone at 8pm as one line
# among many with approve one tap away.
CASES = [
    ("a clean deck", reply(), "publish"),
    ("one mild note", reply([objection()]), "publish"),

    # Harm and invented claims stop the deck. Nobody is asked.
    ("a fabricated claim", reply([objection(category="H3_FALSE_PSYCH", severity=3)]), "block"),
    ("a diagnosis handed to the reader",
     reply([objection(category="H4_DIAGNOSIS", severity=3)]), "block"),
    ("a real person named", reply([objection(category="H9_IDENTIFIES", severity=4)]), "block"),

    # H1 below a 5 does not stop a deck on one reviewer's word. It was the most
    # abused category by a distance — a hallway light, a reply left until
    # morning, a deadbolt — and review() puts it to a second company instead.
    ("harm advice at three, the stretch", reply([objection(category="H1_HARM_ADVICE",
                                                           severity=3)]), "publish"),
    ("harm advice at four, still corroborated", reply([objection(category="H1_HARM_ADVICE",
                                                                 severity=4)]), "publish"),
    ("harm advice at five, which stops on its own",
     reply([objection(category="H1_HARM_ADVICE", severity=5)]), "block"),

    # Everything else is a number, and a person reads it.
    ("a soft category at severity three", reply([objection(severity=3)]), "publish"),
    ("a deck that is simply not good enough", reply(score=64), "review"),
    ("a deck on the wrong side of the bar by one", reply(score=79), "review"),
    ("a deck exactly on the bar", reply(score=80), "publish"),

    # A veto for something that is not harm is no longer a veto. It is a note.
    ("a veto over an editorial objection",
     reply([objection(severity=3)], verdict="BLOCK"), "publish"),
    ("a veto with nothing under it", reply(verdict="BLOCK"), "publish"),

    # A reviewer unsure of its own answer is not evidence either way.
    ("low confidence", reply(confidence=0.4), "review"),
]


def run() -> int:
    failures = []

    for description, answer, expected in CASES:
        outcome, score, reason, _ = critic.decide(answer, DECK)
        if outcome != expected:
            failures.append(f"{description}: expected {expected}, got {outcome} "
                            f"(score {score}: {reason[:70]})")

    # An objection the model cannot quote is deleted rather than argued with.
    outcome, _, _, kept = critic.decide(
        reply([objection(quote="a sentence that is nowhere in this deck", severity=5)]), DECK)
    if kept:
        failures.append("an unquotable objection was kept")
    if outcome != "publish":
        failures.append("an unquotable objection still stopped the deck")

    # Harm is the exception. The critic caught a canary deck full of dangerous
    # medical advice, quoted it loosely, the objection was dropped for not
    # matching word for word, and the deck published. Refusing a good deck costs
    # an evening; publishing advice that hurts somebody costs more than the
    # account, so a BLOCK naming a harm category stands without a usable quote.
    for category in sorted(critic.BLOCKS_WITHOUT_A_QUOTE - {"H1_HARM_ADVICE"}):
        outcome, _, reason, _ = critic.decide(
            reply([objection(category=category, quote="not in the deck at all", severity=5)],
                  verdict="BLOCK"), DECK)
        if outcome != "block":
            failures.append(f"HARM a BLOCK naming {category} was not honoured without a quote")

    # H3 was exempted from this for a while, so the critic could not dispute the
    # citation — the one line code writes, from a verified allowlist, which a
    # model cannot check against the book it names. Live canaries showed that
    # exemption cost more than it saved: a deck carrying "studies show 94
    # percent of night waking is caused by cortisol" walked through, because
    # this critic quotes loosely and its objection was dropped for not matching
    # word for word. A fabricated statistic is a real harm. A citation dispute
    # costs a run.
    outcome, _, _, _ = critic.decide(
        reply([objection(category="H3_FALSE_PSYCH", quote="not in the deck at all", severity=5)],
              verdict="BLOCK"), DECK)
    if outcome != "block":
        failures.append("H3 an unquotable false-claim block was ignored")

    # The citation is protected one level down instead, which is where the
    # disputes actually appeared: an H3 objection quoting the Source Claim line
    # is dropped before any decision is made about it.
    cited = DECK + "\n- **Source Claim:** Espie found that checking the clock turns a waking into a sum.\n"
    _, _, _, kept = critic.decide(
        reply([objection(category="H3_FALSE_PSYCH", severity=5,
                         quote="Espie found that checking the clock turns a waking into a sum")],
              verdict="BLOCK"), cited)
    if any(o["category"] == "H3_FALSE_PSYCH" for o in kept):
        failures.append("H3 an objection to the vetted citation line was kept")

    # Past a couple, the model is composing rather than reading, so its approval
    # is worth no more than its objections.
    invented = [objection(quote=f"invented sentence number {i}", severity=2) for i in range(4)]
    outcome, _, reason, _ = critic.decide(reply(invented), DECK)
    if outcome == "publish":
        failures.append("a reply full of invented quotes was still trusted")
    elif "not in the deck" not in reason:
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
        ("a missing summary", {k: v for k, v in reply().items() if k != "summary"}),
        ("a missing score", {k: v for k, v in reply().items() if k != "score"}),
        ("a score outside the scale", reply(score=140)),
        ("a verdict we never offered", reply(verdict="MAYBE")),
    ]:
        if not llm.validate(answer, critic.SCHEMA):
            failures.append(f"schema accepted {description}")

    # ── who reviews ──
    #
    # Order, not just membership. Gemini writes nearly every deck, so gemini is
    # nearly always excluded, so whoever REVIEW_ORDER puts first is in practice
    # the only critic this engine has. Against the canary set cloudflare caught
    # the shame deck 4 times out of 4 and groq about half the time, so the order
    # is a finding rather than a preference and it should not drift back.
    if critic.REVIEW_ORDER.index("cloudflare") > critic.REVIEW_ORDER.index("groq"):
        failures.append("REVIEW the weaker reviewer is preferred over the stronger one")
    ranked = [name for name, _ in critic.available_providers("gemini")]
    if "cloudflare" in ranked and "groq" in ranked and \
            ranked.index("cloudflare") > ranked.index("groq"):
        failures.append("REVIEW available_providers did not honour REVIEW_ORDER")

    # ── canaries ──
    labels = {label for label, _ in critic.CANARY_DECKS}
    for needed in ("harm advice", "false claim", "diagnosis", "shame", "promise"):
        if needed not in labels:
            failures.append(f"no canary covers {needed}")
    if len(critic.CANARY_DECKS) < 5:
        failures.append("too few canary decks to notice drift")

    # Every canary must aim at something the critic BLOCKS for, or it is not a
    # drift detector — it is a scheduled outage. "incoherent" aimed at nothing
    # blockable, so both vendors passed it correctly, six times out of six, and
    # run_canary read that as the gate failing and halted the pipeline. Since
    # the canary index is used_count(), that was a guaranteed stop every sixth
    # run. The deck now lives in test_coherence.py as test 3, caught by a rule.
    if "incoherent" in labels:
        failures.append("the incoherent canary is back; the critic does not block for that")

    total = len(CASES) + 3 + 3 + 4 + 9 + len(critic.BLOCKS_WITHOUT_A_QUOTE) + 1
    if failures:
        print(f"critic: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"critic: {total}/{total} passed "
          f"({len(CASES)} decision rules, unquotable objections, harm blocks without "
          f"a quote, vendor separation and review order, "
          f"schema, {len(critic.CANARY_DECKS)} canary decks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
