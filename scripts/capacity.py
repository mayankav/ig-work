#!/usr/bin/env python3
"""
capacity.py — how many more pictures can we make today, and how much text is left.

    scripts/capacity.py                 print it
    scripts/capacity.py --notify        print it and send it to Telegram
    scripts/capacity.py --json          machine-readable, for another script

Reads only local state. It makes no API call, so it costs nothing and it cannot
fail because a vendor is down. That also sets its honest limit: it reports what
THIS repo has spent through its own ledger. A call made by hand outside the
pipeline is invisible to it, and so is anything the account spent elsewhere.

Everything it reports comes from one of three places:

  state/flux_neurons.json   what the image generator has spent today, written
                            by poses_flux.Ledger every time it books a call
  poses_flux constants      the free allowance, the share this repo may use,
                            and what one picture is booked at
  the clock                 when the allowance resets

WHY A SCRIPT AND NOT A NOTE SOMEWHERE

The numbers move every day and a note goes stale. The one question worth
answering before a run is "will today's deck get fresh pictures or fall back to
the library", and that is arithmetic on a file, not something to remember.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "suresilly-carousel"
sys.path.insert(0, str(SKILL / "scripts"))

SLIDES_PER_DECK = 9


def _flux():
    """poses_flux's numbers without its network code running. Imported lazily so
    capacity.py still answers when the generator cannot even be imported."""
    import poses_flux as flux
    return flux


def snapshot() -> dict:
    flux = _flux()
    ledger = flux.Ledger()
    per_picture = flux.estimate_neurons(1024, 1024, flux.MAX_REFS)
    remaining = ledger.remaining()
    now = datetime.now(timezone.utc)
    reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return {
        "date_utc": now.strftime("%Y-%m-%d"),
        "resets_in_hours": round((reset - now).total_seconds() / 3600, 1),
        "free_per_day": flux.FREE_DAILY_NEURONS,
        "our_ceiling": ledger.budget,
        "spent": round(ledger.spent()),
        "left": round(remaining),
        "per_picture": round(per_picture),
        "pictures_left": int(remaining // per_picture),
        "decks_left": int(remaining // (per_picture * SLIDES_PER_DECK)),
        "pictures_per_full_day": int(ledger.budget // per_picture),
        "library_poses": len(list((SKILL / "mascot" / "library").glob("*.png"))) - 1,
    }


def as_text(s: dict) -> str:
    bar_len = 20
    used = int(bar_len * s["spent"] / max(1, s["our_ceiling"]))
    bar = "█" * min(used, bar_len) + "░" * max(0, bar_len - used)
    verdict = ("enough for a full deck" if s["pictures_left"] >= SLIDES_PER_DECK
               else f"only {s['pictures_left']} picture(s) — the rest of a deck "
                    f"falls back to the library")
    return "\n".join([
        f"PICTURE BUDGET  {s['date_utc']} UTC",
        f"  {bar}  {s['spent']} / {s['our_ceiling']} used",
        f"  {s['pictures_left']} more pictures  ({s['decks_left']} full decks)",
        f"  {verdict}",
        f"  resets in {s['resets_in_hours']}h",
        f"  library holds {s['library_poses']} poses to fall back on",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--notify", action="store_true", help="also send to Telegram")
    a = ap.parse_args(argv)

    try:
        s = snapshot()
    except Exception as exc:                                   # noqa: BLE001
        print(f"could not read the budget: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(s, indent=2) if a.json else as_text(s))

    if a.notify:
        # notify.py is the one place that knows the channels, so it is called
        # rather than reimplemented. It never fails a caller by design.
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "notify.py"),
             "--subject", f"Picture budget: {s['pictures_left']} left today",
             "--body", as_text(s)],
            check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
