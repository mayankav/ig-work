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

Everything it reports comes from one of four places:

  state/flux_neurons.json   what the image generator has spent today, written
                            by poses_flux.Ledger every time it books a call
  state/vendor_quotas.json  what a vendor said it had LEFT, written by
                            quotas.record from the vendor's own headers
  poses_flux constants      the free allowance, the share this repo may use,
                            and what one picture is booked at
  the clock                 when the allowance resets

Those two state files are opposites and are deliberately not merged. The ledger
accumulates what we spent and may never be lowered; the quota snapshot holds
what the vendor reports is left and is always replaced by the newest reading.

THREE VENDORS, THREE UNITS, THREE KINDS OF REFRESH

There is no common currency here and this file does not invent one. Cloudflare
bills neurons from one account-wide pot that returns whole at 00:00 UTC. Groq
counts requests, per model, shared across the organisation, and drips them back
continuously — there is no boundary to wait for. Gemini counts requests per
model per project against a limit it never reports, returning at midnight
Pacific. So each vendor is reported in its own unit, and the only numbers that
are added together are ones that answer the same question: how many more
pictures can today's deck have.

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

# Below this share of its own allowance, a vendor is worth a line of its own in
# the report. Above it, saying so every morning is noise that trains you to skip
# the section on the morning it matters.
LOW_WATER = 0.20


def _quotas() -> dict:
    """The vendor snapshot, or nothing. Never raises: this file is written by a
    best-effort recorder and a fresh checkout has never had one."""
    try:
        import quotas
        return quotas.read()
    except Exception:                                          # noqa: BLE001
        return {}


def vendors() -> list[dict]:
    """One record per text vendor, each in its OWN unit.

    `known` is the field that matters. Gemini reports no quota header at all —
    checked live on 2026-08-31, a successful call carries none — so its record
    says so instead of showing a bar that would be a guess drawn as a
    measurement. A vendor we cannot see is not a vendor with room.
    """
    import quotas as _q
    flux = _flux()
    ledger = flux.Ledger()
    snap = _quotas()
    out: list[dict] = []

    # Gemini — counted by nobody. Stated, not implied.
    out.append({"name": "gemini", "unit": "requests", "known": False,
                "note": "no quota reported by the vendor",
                "low": False})

    # Groq — the vendor's own remaining, and its age, because a reading from
    # yesterday is not a reading from today.
    groq = snap.get("groq") if isinstance(snap.get("groq"), dict) else None
    reqs = (groq or {}).get("requests") or {}
    limit, remaining = reqs.get("limit"), reqs.get("remaining")
    if limit and remaining is not None:
        share = remaining / limit
        out.append({"name": "groq", "unit": "requests", "known": True,
                    "limit": limit, "remaining": remaining, "share": share,
                    "model": groq.get("model"),
                    "refills_in_seconds": reqs.get("reset_seconds"),
                    "age_seconds": _q.age_seconds(groq),
                    "low": share < LOW_WATER})
    else:
        out.append({"name": "groq", "unit": "requests", "known": False,
                    "note": "no reading yet — it is written by the next call",
                    "low": False})

    # Cloudflare text — the only one of the three we have to keep the total for
    # ourselves, because its header reports a cost and not a remaining.
    share_for_text = flux.FREE_DAILY_NEURONS - ledger.budget
    used = ledger.text_spent()
    left = max(0.0, share_for_text - used)
    out.append({"name": "cloudflare", "unit": "neurons", "known": True,
                "limit": round(share_for_text), "remaining": round(left),
                "share": (left / share_for_text) if share_for_text else 0.0,
                "account_left": round(ledger.account_left()),
                # Never refused, only recorded: writing is what this repo exists
                # to do. So this flag is a warning and not a gate.
                "low": used > 0.85 * share_for_text})
    return out


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
        "text_spent": round(ledger.text_spent()),
        "account_spent": round(ledger.account_spent()),
        "account_left": round(ledger.account_left()),
        "reserved_for_text": round(flux.FREE_DAILY_NEURONS - ledger.budget),
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
        "vendors": vendors(),
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
        "",
        "WRITING",
        f"  {s['text_spent']} neurons used of the {s['reserved_for_text']} kept back for it",
        f"  {s['account_left']} left on the whole account today",
        f"  {_writing_verdict(s)}",
    ])


def _writing_verdict(s: dict) -> str:
    """Writing shares the allowance with pictures and is never refused to
    protect them, so the only thing worth saying is how much room is left."""
    if s["text_spent"] == 0:
        return "writing has not touched the allowance today"
    share = s["text_spent"] / max(1, s["reserved_for_text"])
    if share > 0.85:
        return "⚠ writing is near the end of what was kept back for it"
    return f"writing has used {share:.0%} of its share"


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
