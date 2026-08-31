#!/usr/bin/env python3
"""
quotas.py — what a vendor says it has left, recorded the moment it says it.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  A SNAPSHOT, NOT A LEDGER. neurons.py accumulates what we spent and  │
    │  may never be lowered. This records what the vendor reports is LEFT  │
    │  and is always replaced by the newest reading. The two rules are     │
    │  opposites, which is why they are not the same class.                │
    └──────────────────────────────────────────────────────────────────────┘

WHY THIS EXISTS

CREDITS.md said, for months, that Groq "does not report a cost per call, so it
cannot be counted". That was never true. Every successful Groq response carries
its own remaining allowance, and `_post` was already capturing response headers
for the Cloudflare call and throwing Groq's away. Measured 2026-08-31 against
`openai/gpt-oss-120b`:

    x-ratelimit-limit-requests: 1000        x-ratelimit-remaining-requests: 999
    x-ratelimit-limit-tokens:   8000        x-ratelimit-remaining-tokens:   7922
    x-ratelimit-reset-requests: 1m26.4s     x-ratelimit-reset-tokens:       585ms

This is better than the Cloudflare header, which reports what one call cost and
leaves the running total to us to reconstruct. Groq reports the total. There is
nothing to estimate and nothing to reconcile, so nothing here estimates.

WHAT THE NUMBERS MEAN, AND WHAT THEY DO NOT

`-requests` is per DAY and `-tokens` is per MINUTE, on Groq's own say-so and on
the arithmetic: one request bought back 86.4 seconds of refill, and
86.4 x 1000 is 86,400, which is a day exactly. So the daily allowance drips
back continuously — there is no midnight boundary to key a counter on, and no
moment when it is full again unless nothing has been spent. `reset_seconds` is
time until FULL, not time until a boundary.

Limits are per model and enforced across the whole organisation, so a second
API key buys nothing and a reading taken against one model says nothing about
another. The model is stored beside every reading, and a reading for a
different model REPLACES rather than merges: two models' numbers averaged
together would be a figure neither vendor nor code could account for.

NOTHING HERE MAY FAIL A CALL

`record()` swallows everything. A quota file that cannot be written is a
report that is missing a line, and that must never cost a deck. The reader's
side of the same rule: a value the vendor did not send is stored as absent and
never as a zero, because a zero is a measurement and an absence is not — and
these two are the difference between "Groq is out" and "we did not look".

TWO KINDS OF RECORD IN ONE FILE, AND HOW THEY ARE KEPT APART

Every record carries a `source`, and the two obey different rules:

  reported   the vendor said what is LEFT. Written by record(). Always
             replaced by the newest reading, never accumulated.
  counted    the vendor says nothing, so we count our own calls. Written by
             count(). Only ever incremented, and cleared when the vendor's own
             day rolls over.

They share a file because they answer one question — how much room has each
vendor got — but never a function, because treating a tally as a remaining is
how a vendor with nothing left comes to look full. `source` is what a reader
checks first.

GEMINI'S DAY IS NOT OUR DAY

Gemini's requests-per-day returns at midnight PACIFIC, per model, per project.
`neurons.py` keys its ledger on the UTC date because that is when Cloudflare's
pot returns, and reusing that key here would zero the tally at 17:00 Pacific —
seven hours early, every day, right in the middle of an allowance. So the zone
belongs to the vendor and is stored beside the day it produced.

What is counted is what THIS repo asked for. A call made by hand against the
same project is invisible here, the same blind spot capacity.py already owns.
So this reports how much we have used and never claims how much is left: the
ceiling is a number Gemini only ever names in the text of a 429.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_DIR = Path(__file__).resolve().parents[4]   # scripts -> skill -> skills -> .agents -> repo

QUOTAS_PATH = Path(os.environ.get(
    "SS_QUOTAS", REPO_DIR / "state" / "vendor_quotas.json"))

# Groq reports durations as Go-style strings: "1m26.4s", "585ms", "7.66s".
# ms/us/ns come first in the alternation so that "585ms" is not read as 585
# minutes followed by a stray second.
_DURATION = re.compile(r"([\d.]+)\s*(ms|us|ns|[dhms])")
_UNIT_SECONDS = {"ns": 1e-9, "us": 1e-6, "ms": 1e-3,
                 "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def parse_duration(text: str | None) -> float | None:
    """"1m26.4s" -> 86.4. None when there is nothing to read.

    Returns None rather than 0.0 for an unparseable string. Zero means "it is
    full right now", which is the opposite of "we could not tell".
    """
    if not text:
        return None
    parts = _DURATION.findall(text.strip().lower())
    if not parts:
        return None
    total = 0.0
    for value, unit in parts:
        try:
            total += float(value) * _UNIT_SECONDS[unit]
        except (ValueError, KeyError):
            return None
    return round(total, 3)


def _number(text: str | None) -> float | int | None:
    """Counts come back as integers so the state file reads like what it is —
    999 requests, not 999.0 of them."""
    if text is None:
        return None
    try:
        value = float(str(text).strip())
    except ValueError:
        return None
    return int(value) if value.is_integer() else value


def _dimension(headers: dict, kind: str) -> dict | None:
    """One quota dimension — requests or tokens — as the vendor reported it.

    A dimension with no limit and no remaining is dropped entirely, so that a
    reader iterating the file never has to tell an empty record from a real
    reading of zero.
    """
    limit = _number(headers.get(f"x-ratelimit-limit-{kind}"))
    remaining = _number(headers.get(f"x-ratelimit-remaining-{kind}"))
    reset = parse_duration(headers.get(f"x-ratelimit-reset-{kind}"))
    if limit is None and remaining is None:
        return None
    out = {"limit": limit, "remaining": remaining, "reset_seconds": reset}
    return {k: v for k, v in out.items() if v is not None}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read(path: Path | str | None = None) -> dict:
    try:
        data = json.loads(Path(path or QUOTAS_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def record(vendor: str, model: str, headers: dict,
           path: Path | str | None = None) -> dict | None:
    """Store what this response said was left. Never raises.

    `headers` is the lower-cased header map `llm._post` already captures.
    Returns the stored record, or None when the response carried no quota
    headers at all — which is the honest answer for Gemini, and is recorded as
    nothing rather than as a full tank.
    """
    try:
        requests_dim = _dimension(headers, "requests")
        tokens_dim = _dimension(headers, "tokens")
        if requests_dim is None and tokens_dim is None:
            return None
        record_ = {"source": "reported", "model": model, "observed_at": _now()}
        if requests_dim:
            record_["requests"] = requests_dim
        if tokens_dim:
            record_["tokens"] = tokens_dim

        target = Path(path or QUOTAS_PATH)
        data = read(target)
        # Wholesale replacement, not a merge. Limits are per model, so an old
        # reading for a different model is not a partial truth to be topped up
        # — it is a number about something else.
        data[vendor] = record_
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        return record_
    except Exception:                                          # noqa: BLE001
        return None       # a quota file that cannot be written never costs a deck


def age_seconds(record_: dict | None) -> float | None:
    """How long ago this reading was taken, so a reader can refuse to print a
    stale number as if it were current. None when there is nothing to date."""
    if not isinstance(record_, dict):
        return None
    try:
        seen = datetime.strptime(record_["observed_at"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, (datetime.now(timezone.utc)
                     - seen.replace(tzinfo=timezone.utc)).total_seconds())


# ── counted vendors: the ones that report nothing ────────────────────────────
#
# Gemini's allowance returns at midnight Pacific. Nothing else here uses that
# zone, which is precisely why it is written down rather than assumed.
VENDOR_ZONE = {"gemini": "America/Los_Angeles"}


def vendor_day(vendor: str) -> str:
    """Today's date in the vendor's OWN zone, which is the only date its
    allowance cares about. Falls back to UTC for a vendor with no zone on
    file, because a wrong-but-stated key beats a crash in a recorder that is
    not allowed to fail."""
    zone = VENDOR_ZONE.get(vendor)
    try:
        now = datetime.now(ZoneInfo(zone)) if zone else datetime.now(timezone.utc)
    except Exception:                                          # noqa: BLE001
        now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d")


def counted(vendor: str, path: Path | str | None = None) -> dict:
    """This vendor's tally for TODAY, in its own zone.

    A stored tally from an earlier day is not a smaller tally, it is last
    night's, so it is dropped rather than shown. Returns an empty record
    rather than None: "we have made no calls yet" is a true statement and a
    reader should not have to special-case it.
    """
    day = vendor_day(vendor)
    stored = read(path).get(vendor)
    if not isinstance(stored, dict) or stored.get("source") != "counted":
        return {"source": "counted", "day": day, "models": {}}
    if stored.get("day") != day:
        return {"source": "counted", "day": day, "models": {}}
    stored.setdefault("models", {})
    return stored


def count(vendor: str, model: str, path: Path | str | None = None) -> None:
    """One more request made against this vendor's model today. Never raises.

    Counted at the point the request is ATTEMPTED, not where it succeeded. A
    refused call has still been asked for, and a tally that only counts the
    answers we liked walks into a daily cap believing it has room.
    """
    try:
        target = Path(path or QUOTAS_PATH)
        data = read(target)
        record_ = counted(vendor, target)
        entry = record_["models"].setdefault(model, {"made": 0})
        entry["made"] = int(entry.get("made", 0)) + 1
        record_["observed_at"] = _now()
        record_["zone"] = VENDOR_ZONE.get(vendor, "UTC")
        data[vendor] = record_
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass          # a tally that cannot be written must never cost a deck


def mark_exhausted(vendor: str, model: str, path: Path | str | None = None) -> None:
    """This model said it is out of its daily allowance.

    Recorded as a fact with a time on it, and deliberately NOT turned into a
    learned ceiling. The tally counts only what this repo asked for, so
    "we made 14 and the fifteenth was refused" does not establish that the
    limit is 14 — anything else on the same project spends the same quota. A
    figure that would be wrong whenever we are not the only caller is worse
    than no figure.
    """
    try:
        target = Path(path or QUOTAS_PATH)
        data = read(target)
        record_ = counted(vendor, target)
        entry = record_["models"].setdefault(model, {"made": 0})
        entry["out_of_quota_at"] = _now()
        record_["observed_at"] = _now()
        record_["zone"] = VENDOR_ZONE.get(vendor, "UTC")
        data[vendor] = record_
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    except Exception:                                          # noqa: BLE001
        pass
