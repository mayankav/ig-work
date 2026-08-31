#!/usr/bin/env python3
"""
neurons.py — the one ledger for the one free allowance.

Cloudflare gives 10,000 neurons a day, per ACCOUNT. Two different parts of this
repo spend them: poses_flux.py draws mascot poses, and llm.py calls a Llama
model as its third text vendor. Until this file existed only the pictures were
recorded, so the split everyone quoted — 6,000 for pictures, the rest for
writing — was an assumption nobody could check. If the writer had quietly eaten
half the allowance, the picture budget would still have reported itself full.

So both record here now, under separate kinds, against one shared total. That
is the only way to answer the question that matters before a run: is the writer
about to run out.

Extracted from poses_flux.py rather than imported from it. llm.py may not
import poses_flux — poses_flux imports llm for its credentials, so that would
be a cycle — and neither of them should own a number the other depends on.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[4]   # scripts -> skill -> skills -> .agents -> repo


class BudgetExceeded(Exception):
    """Refusing to spend past the daily neuron budget."""


# ── neuron budget ────────────────────────────────────────────────────────────
#
# Workers AI gives 10,000 neurons/day free, per ACCOUNT — the same account
# llm.py bills its third text vendor against. So this tool may not spend the
# lot: whatever it takes, the writer and the critic no longer have.
#
# Two numbers disagree about what a call costs, by a factor of ten, and this
# module believes the expensive one.
#
#   PUBLISHED   ~104 neurons for a 1024x1024 frame, ~21 for references.
#   MEASURED    every response carries a cf-ai-neurons header. Five calls on
#               2026-08-31 at 1024x1024 reported 5.37 neurons per reference
#               image and nothing at all for the output frame:
#                   1 ref -> 5.37    2 refs -> 10.74    4 refs -> 21.48
#               Exactly linear, three independent confirmations.
#
# One of those is wrong and there is no way from here to tell which. If the
# header is right, believing the published rate costs some throughput. If the
# header undercounts — it plainly does not bill the output frame, so something
# is missing from it — then believing the header runs ten times over the free
# allowance and starts spending the user's money.
#
# So: RESERVE at the published rate, which is the pessimistic one and does not
# depend on the header being complete. Reconcile against the header only when
# the header is HIGHER than the reservation. Reconciliation can raise the
# recorded spend and can never lower it, which means a surprise expensive call
# is caught and a suspiciously cheap one buys nothing. Same rule as everywhere
# else here: "we could not check" must never come out the same as "we checked".
NEURONS_PER_MEGAPIXEL = 104.0     # published, per 1024x1024-equivalent output
NEURONS_PER_REFERENCE = 21.0      # published, per reference image
FREE_DAILY_NEURONS = 10_000
DEFAULT_BUDGET = 6_000            # 60%: the text vendors draw on the same pot

LEDGER_PATH = Path(os.environ.get(
    "SS_FLUX_LEDGER", REPO_DIR / "state" / "flux_neurons.json"))

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Ledger:
    """What this tool has spent today, on disk, so two runs cannot both think
    they have the whole allowance.

    Keyed on the UTC date because that is when Cloudflare's allowance rolls
    over. Spend is recorded BEFORE the call and never refunded on failure: a
    refused image is an image you were still billed for, and a ledger that only
    counts successes will walk you straight into a 429 in the middle of a batch.
    """

    def __init__(self, path: Path | str | None = None,
                 budget: float = DEFAULT_BUDGET):
        # Resolved here rather than defaulted in the signature, which binds the
        # module constant once at import and then ignores every attempt to
        # point it somewhere else. A test suite that cannot redirect this file
        # writes its arithmetic into the repo's real ledger, and the next run
        # believes it has already spent the afternoon.
        self.path = Path(path) if path is not None else LEDGER_PATH
        self.budget = float(budget)
        if self.budget > FREE_DAILY_NEURONS:
            raise BudgetExceeded(
                f"budget {self.budget:.0f} exceeds the free daily allowance of "
                f"{FREE_DAILY_NEURONS} neurons — this tool does not spend money")

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def spent(self) -> float:
        day = self._read().get(_today())
        return float(day.get("neurons", 0.0)) if isinstance(day, dict) else 0.0

    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent())

    def check(self, cost: float) -> None:
        if cost > self.remaining():
            raise BudgetExceeded(
                f"this call is booked at {cost:.0f} neurons and only "
                f"{self.remaining():.0f} of today's {self.budget:.0f} budget are left "
                f"(the account's free allowance is {FREE_DAILY_NEURONS}/day and the "
                f"text vendors draw on it too). Try again tomorrow.")

    def spend_text(self, cost: float, note: str = "") -> None:
        """Record what the text vendor took out of the SAME allowance.

        No check() and no refusal. Writing is the thing this repo exists to do
        and a deck that cannot be written is a day with no post, so text is
        never turned away to protect a picture budget. It is only recorded, so
        that the picture side can see the true remaining total and so a person
        can see whether writing is close to the edge.
        """
        self._write(0.0, 0, note=note, text_neurons=cost, text_calls=1)

    def text_spent(self) -> float:
        day = self._read().get(_today())
        return float(day.get("text_neurons", 0.0)) if isinstance(day, dict) else 0.0

    def account_spent(self) -> float:
        """Everything this repo has put against the account today."""
        return self.spent() + self.text_spent()

    def account_left(self) -> float:
        return max(0.0, FREE_DAILY_NEURONS - self.account_spent())

    def _write(self, neurons_delta: float, calls_delta: int, note: str = "",
               text_neurons: float = 0.0, text_calls: int = 0) -> None:
        data = self._read()
        day = data.get(_today())
        day = day if isinstance(day, dict) else {"neurons": 0.0, "calls": 0}
        day["neurons"] = max(0.0, round(float(day.get("neurons", 0.0)) + neurons_delta, 2))
        day["calls"] = int(day.get("calls", 0)) + calls_delta
        # Text is a separate line against the same day, so "how much did the
        # pictures take" and "how much did the writing take" are both
        # answerable from one file.
        day["text_neurons"] = round(float(day.get("text_neurons", 0.0)) + text_neurons, 2)
        day["text_calls"] = int(day.get("text_calls", 0)) + text_calls
        if note:
            day["last"] = note
        data[_today()] = day
        # Keep a fortnight; the file is a rate limiter, not an archive.
        for stale in sorted(data)[:-14]:
            data.pop(stale, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    def spend(self, cost: float, note: str = "") -> None:
        self._write(cost, 1, note)

    def reconcile(self, reserved: float, actual: float | None, note: str = "") -> None:
        """Top the reservation up if Cloudflare billed MORE than we booked.

        One-directional on purpose. The cf-ai-neurons header reports about a
        tenth of the published rate and visibly does not bill the output frame,
        so it is trustworthy as a floor and not as a total: a call that comes
        back dearer than expected is news worth acting on, and one that comes
        back cheap buys no extra throughput.

        actual is None when the response carried no header at all. Then the
        reservation stands, because "we could not check" must never come out
        the same as "we checked".
        """
        if actual is None or actual <= reserved:
            return
        self._write(actual - reserved, 0, note)


# ─────────────────────────── the call ────────────────────────────────────────
