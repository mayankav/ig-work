#!/usr/bin/env python3
"""
Slide 9 has to say who to send it to. No network.

This gate had no test at all, and it stopped the engine. `has_specific_recipient`
accepted exactly fifteen nouns and nothing else, while DRAFT_SYSTEM dictates the
shape as an open slot:

    Send this to the [kind of person] who [does the thing in the moment].

So a moment set in an office — "I walked into the office at 6pm and took my
manager's extra shift" — asks for `manager`, `boss`, `colleague` or `teammate`,
and the gate refused all four. Its whole message was "CTA must ask for a DM/share
to a specific recipient", which names none of the fifteen, so the model rewrote
the line differently wrong every time. Run local-1788395662 went 13, 5, 4, 3, 3,
3, 3 — four attempts with no movement — and posted nothing. `coworker` was on the
list the entire time, one synonym away.

That is invariant 24 (a gate may not contradict its own prompt) and invariant 21
(a fault nothing can answer is a stopped engine, not a strict gate).

The fix measured against the corpus first, which is invariant 28: all ten
published decks pass on the noun route unchanged, so nothing that shipped is
re-judged. What is new is the DESCRIBED route — any kind of person, provided the
deck says which one — because the clause is where the specificity actually lives.
The nouns still standing alone matters too: "send this to your partner" is a real
CTA and needs no clause.

The negatives are the reason the gate exists. A vague pronoun with a clause
attached — "send this to anyone who relates" — is the generic CTA in disguise,
and it must stay refused on both routes or widening the nouns would have quietly
opened the door this gate was built to hold shut.
"""
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import audit_copy  # noqa: E402

DECKS = pathlib.Path(__file__).resolve().parents[3].parent / "carousels"

# Written for the office moment that deadlocked. Not one of these nouns was
# reachable before, and every one is what a person would actually type.
DESCRIBED = [
    "Send this to the manager who books your evening.",
    "Send this to the colleague who never says no.",
    "Send this to the boss who adds one more shift.",
    "Send this to the teammate who covers every gap.",
    "Send this to your neighbor who always waves you in.",
    "Share this with the flatmate who never leaves the kitchen.",
]

# The noun route, which the published decks used. These carry no clause at all,
# so they prove the two routes are independent and not one accidental regex.
NAMED = [
    "Send this to your partner.",
    "Send this to the friend caught at the doorway past 6pm.",
    "Send this to a sibling who also time-travels at family dinners.",
]

# Every one of these must be refused. The first three are the dangerous shape:
# a clause makes them look described, and they address nobody.
REFUSED = [
    "Send this to anyone who relates.",
    "Send this to everyone who needs to hear this.",
    "Share this with whoever is still awake.",
    "Send this to somebody who always does this.",
    "Send this to someone.",
    "Tag someone below.",
    "Save this for later.",
    "Drop a comment if this is you.",
    "Send this.",
    "Share if you relate.",
]


def published_ctas() -> list[tuple[str, str]]:
    """Slide 9's call to action out of every deck on disk."""
    out = []
    for deck in sorted(DECKS.glob("*/carousel.md")):
        text = deck.read_text(encoding="utf-8")
        slide = re.search(r"(?ms)^### Slide 9.*?(?=\n### |\Z)", text)
        if not slide:
            continue
        call = re.search(r"(?m)^-\s+\*\*(?:Primary CTA|CTA|H1)[^:]*:\*\*\s*(.+)$",
                         slide.group(0))
        if call:
            out.append((deck.parent.name, call.group(1)))
    return out


def run() -> int:
    failures = []
    decks = published_ctas()

    # Nothing that shipped may be re-judged by a widened gate.
    for name, call in decks:
        if not audit_copy.has_specific_recipient(call):
            failures.append(f"PUBLISHED {name} now refused: {call[:60]!r}")

    for call in DESCRIBED:
        if not audit_copy.has_specific_recipient(call):
            failures.append(f"DESCRIBED refused {call!r} — the prompt asks for "
                            "'[kind of person] who [does the thing]', so any noun "
                            "with a clause is the shape being requested")

    for call in NAMED:
        if not audit_copy.has_specific_recipient(call):
            failures.append(f"NAMED refused {call!r} — a word on PERSON_WORDS "
                            "stands alone and needs no clause")

    for call in REFUSED:
        if audit_copy.has_specific_recipient(call):
            failures.append(f"LEAKED {call!r} — widening the nouns must not open "
                            "the door this gate exists to hold shut")

    # The message is half the gate, and the reason this suite exists: the old
    # one said "a specific recipient" and named nothing, so seven attempts
    # rewrote the same line differently wrong. Run the real audit over a real
    # deck with its CTA swapped, and read what comes back.
    if decks:
        source = sorted(DECKS.glob("*/carousel.md"))[0]
        broken = source.read_text(encoding="utf-8").replace(
            decks[0][1], "Send this to anyone who relates.")
        scratch = pathlib.Path(tempfile.mkdtemp()) / "carousel.md"
        scratch.write_text(broken, encoding="utf-8")
        try:
            said = [i for i in audit_copy.audit(scratch) if "send it to" in i]
        finally:
            shutil.rmtree(scratch.parent, ignore_errors=True)
        if not said:
            failures.append("MESSAGE a CTA addressed to 'anyone' raised no CTA fault")
        else:
            if "kind of person" not in said[0]:
                failures.append(f"MESSAGE names no shape to write instead: {said[0]!r}")
            if "anyone who relates" not in said[0]:
                failures.append("MESSAGE does not quote the line it refused, so the "
                                f"model cannot see what was wrong: {said[0]!r}")

    if not decks:
        failures.append("CORPUS no decks found on disk — this suite proved nothing")

    total = len(decks) + len(DESCRIBED) + len(NAMED) + len(REFUSED) + 1
    if failures:
        print(f"cta-recipient: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"cta-recipient: {total}/{total} passed "
          f"({len(decks)} published decks unchanged, {len(DESCRIBED)} described, "
          f"{len(NAMED)} named, {len(REFUSED)} refused)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
