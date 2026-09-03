#!/usr/bin/env python3
"""
outcomes.py — how a run ends, and what colour that is.

A run has three endings, not two.

    green   a deck went out
    amber   nothing shipped and nothing broke — a gate did its job
    red     something is broken, and trying again probably will not help

The engine had only two. A coherence gate refusing every draft and a vendor
that could not be reached both raised llm.ModelRefused, both exited 1, and both
turned CI red. Run 33583495343 was the first kind and read as the second: the
Telegram message said "a gate refusing, which is the system working" while the
run sat red in the actions list. Two of those in a week and a red run stops
being read at all, which is precisely the state in which a real outage goes out
the door unnoticed.

WHY THIS FILE EXISTS AT ALL

The benign ending is raised in two places that cannot see each other. writer.py
runs out of attempts with gate faults still standing; run.py finds no moment
that survives, or a deck too close to one already published. run.py imports
writer, so writer cannot import run, so the exception cannot live in either of
them. Invariant 3 already settled this question for the artwork gates — they
belong in the module both paths import, not in whichever one needed them first —
and the same answer applies here.
"""

from __future__ import annotations


class Stop(Exception):
    """A layer said no. The reason is written for whoever reads the alert.

    RED. Reaching this means something needs a person: the renderer refused,
    Instagram refused, the state on disk could not be trusted. Exit 1, and the
    alert says so.
    """


class Refused(Exception):
    """A gate did its job and there is nothing to publish. AMBER.

    Not an error. Nothing broke, nothing was consumed, and the moment is still
    there to be drawn tomorrow. Exit 0, so the red in CI keeps meaning what it
    says.

    `retry` is whether asking again could plausibly end differently. Nearly
    always it can — the writer draws a different moment each attempt. It is
    False for the one case where the answer cannot change until something else
    runs first: an empty concept pool, which only the topup job refills. A
    message offering a retry that cannot work is worse than no offer.
    """

    def __init__(self, reason: str, retry: bool = True,
                 history: list[int] | None = None) -> None:
        super().__init__(reason)
        self.retry = retry
        # The fault count per attempt. Carried because it is the one number that
        # tells a stuck gate from an unlucky draft, and until now it existed only
        # inside the reason string, where nothing could read it.
        self.history = list(history or [])


# ───────────────────────── reading the fault trail ─────────────────────────

# Three identical counts in a row. Measured against the two real trails this
# engine has recorded: a CI run went 6, 2, 1 and a local one 4, 4, 4, 2, 1 —
# both were converging and both ended one attempt short of clean, so three
# repeats must NOT call either of those stuck. Run local-1788395662 went
# 13, 5, 4, 3, 3, 3, 3 and was: the same fault stood for four attempts because
# the gate could not be satisfied by any wording.
#
# Two would have called 4, 4, 4, 2, 1 stuck at its third attempt and withheld a
# retry from a run that was about to finish. Four never fires on a seven-attempt
# loop until the sixth, which is too late to be worth saying.
STUCK_AFTER = 3


def trajectory(history: list[int]) -> tuple[str, str]:
    """How the fault count moved, and one sentence about it for the owner.

    Returns one of `converging`, `stuck` or `one-shot`, and a plain line naming
    what that means for whoever is reading the alert at breakfast.

    This decides ONE thing: whether the message offers `retry`. Invariant 27
    already says a verb is offered only when trying again could work, and this is
    the measurement behind that promise for the writer loop — a fault count that
    stopped falling means a gate no wording will satisfy, and a fresh moment goes
    straight back into it.
    """
    counts = list(history or [])
    if len(counts) < 2:
        return "one-shot", ("There was only one try, so there is nothing to "
                            "compare it against.")
    tail = counts[-STUCK_AFTER:]
    if len(tail) >= STUCK_AFTER and len(set(tail)) == 1:
        return "stuck", (f"The count stopped falling at {tail[0]}. "
                         f"One check cannot be passed, so a new idea will stop "
                         f"in the same place.")
    return "converging", ("The count was still falling. It ran out of tries "
                          "rather than running out of ideas.")


def arrow(history: list[int]) -> str:
    """The trail as one scannable line: 13 → 5 → 4 → 3 → 3 → 3 → 3."""
    return " → ".join(str(n) for n in history) if history else "—"
