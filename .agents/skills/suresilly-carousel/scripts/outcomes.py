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

    def __init__(self, reason: str, retry: bool = True) -> None:
        super().__init__(reason)
        self.retry = retry
