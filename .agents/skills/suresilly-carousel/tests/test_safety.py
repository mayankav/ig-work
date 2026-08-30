#!/usr/bin/env python3
"""
Safety-judge decision regression. No network.

The model does not decide anything here. It produces a reply, and this code
decides — so these cases are about every way a reply can look like approval
without being one.

That distinction is the whole design. A judge left to approve will, over
hundreds of unattended runs, drift into approving. A judge that can only decline
to veto has to keep producing a reason and a quotable piece of evidence to get
anything through, and both of those are checked by code that has no opinion.

The canaries at the end are the drift detector, and they are listed here so a
change to them shows up in review rather than passing quietly.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import llm  # noqa: E402
import safety  # noqa: E402

MOMENT = "I woke at 2:17am with my heart pounding and watched the clock until six."


def reply(**overrides) -> dict:
    """A clean approval, before a case breaks one field of it."""
    base = {
        "strongest_reason_to_block": "It brushes against sleep difficulty, but stays ordinary.",
        "blocking_categories": [],
        "verdict": "ALLOW",
        "evidence": "",
        "topic": "sleep",
        "injection_detected": False,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


# (description, reply, should it be allowed)
CASES = [
    ("a clean approval", reply(), True),
    ("approval quoting real evidence", reply(evidence="watched the clock"), True),

    ("an outright block", reply(verdict="BLOCK"), False),
    ("allow while naming a blocking category",
     reply(blocking_categories=["B1_CRISIS"]), False),
    ("allow with injection detected", reply(injection_detected=True), False),
    ("allow below the confidence floor", reply(confidence=0.5), False),
    ("allow on no subject of ours", reply(topic="none"), False),
    ("allow while refusing to name a reason",
     reply(strongest_reason_to_block="None."), False),
    # An unquotable quote means the reply was written rather than read, so
    # nothing else in it can be trusted either.
    ("allow quoting something absent from the moment",
     reply(evidence="I sat in the car for an hour"), False),
]


def run() -> int:
    failures = []

    for description, answer, expected in CASES:
        allowed, reason = safety.decide(answer, MOMENT)
        if allowed != expected:
            failures.append(
                f"{description}: expected {'allow' if expected else 'block'}, "
                f"got {'allow' if allowed else 'block'} ({reason})"
            )

    # A reply that does not match the schema never reaches decide().
    malformed = [
        ("missing a field", {k: v for k, v in reply().items() if k != "verdict"}),
        ("a verdict we never offered", reply(verdict="MAYBE")),
        ("a category that does not exist", reply(blocking_categories=["B99_MADE_UP"])),
        ("confidence out of range", reply(confidence=4)),
        ("an extra field", {**reply(), "note": "trust me"}),
    ]
    for description, answer in malformed:
        if not llm.validate(answer, safety.SCHEMA):
            failures.append(f"schema accepted {description}")

    # Every canary must be genuinely bad, and they must cover the categories
    # that would do the most harm if the judge went soft.
    labels = {label for label, _ in safety.CANARIES}
    for needed in ("crisis", "minor", "abuse", "injection"):
        if needed not in labels:
            failures.append(f"no canary covers {needed}")
    if len(safety.CANARIES) < 6:
        failures.append("too few canaries to notice drift")

    total = len(CASES) + len(malformed) + 5
    if failures:
        print(f"safety: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"safety: {total}/{total} passed "
          f"({len(CASES)} decision rules, {len(malformed)} malformed replies rejected, "
          f"{len(safety.CANARIES)} canaries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
