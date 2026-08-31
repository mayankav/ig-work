#!/usr/bin/env python3
"""
dashboard.py — the whole state of the engine, as one message.

    scripts/dashboard.py --status ok --slug 20260901_kitchen
    scripts/dashboard.py --status stopped --note "safety gate refused the moment"
    scripts/dashboard.py --status held --slug 20260901_kitchen --score 62

Used by the workflows to build the body of the Telegram and email report. It
reads local state only: no API call, no network, no cost, and it cannot fail
because a vendor is down.

WHY THIS EXISTS

The report used to be one line assembled in bash — "Built <slug> in mode <mode>.
See the contact sheet attached." That tells you a deck happened. It does not
tell you the picture budget is nearly gone, that six slides fell back to library
poses, that the queue is empty, or that a deck from Tuesday is still waiting for
an answer. Every one of those is something you would want to know BEFORE opening
Instagram, and every one of them was already sitting in a file nobody read.

NOTHING HERE MAY FAIL THE RUN

The post has already happened by the time this is called. Each section is read
inside its own try, and a section that cannot be read prints as "unknown" rather
than taking the message down with it. A missing state file is normal on a fresh
checkout, not an error.

Kept short on purpose. Telegram truncates a caption at 1000 characters and a
truncated dashboard is worse than a brief one, so this aims well under that and
puts the line that changes decisions at the top.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "suresilly-carousel"
STATE = REPO / "state"

ICON = {"ok": "✅", "held": "⏸", "stopped": "🛑", "error": "❌"}


def _safe(fn, default="unknown"):
    """Every reader goes through this. One unreadable file must not cost the
    whole message — the run is already over and the report is all there is."""
    try:
        return fn()
    except Exception:                                          # noqa: BLE001
        return default


def pictures() -> str:
    def read():
        sys.path.insert(0, str(REPO / "scripts"))
        import capacity
        s = capacity.snapshot()
        flag = "" if s["pictures_left"] >= 9 else "  ⚠ short for a full deck"
        return (f"{s['pictures_left']} pictures left "
                f"({s['spent']}/{int(s['our_ceiling'])} used, resets in "
                f"{s['resets_in_hours']}h){flag}")
    return _safe(read)


def library() -> str:
    def read():
        poses = [p for p in (SKILL / "mascot" / "library").glob("*.png")
                 if not p.stem.startswith("_")]
        return f"{len(poses)} poses"
    return _safe(read)


def queue() -> str:
    def read():
        reserve = json.loads((STATE / "reserve.json").read_text())
        used = sum(1 for _ in (STATE / "used.jsonl").open())
        return f"{len(reserve)} moments held back, {used} used so far"
    return _safe(read)


def waiting() -> str:
    def read():
        pending = sorted((STATE / "pending").glob("*.json"))
        if not pending:
            return "nothing waiting"
        names = ", ".join(p.stem for p in pending[:3])
        extra = f" (+{len(pending) - 3})" if len(pending) > 3 else ""
        return f"⚠ {len(pending)} deck(s) waiting for your answer: {names}{extra}"
    return _safe(read)


def poses_used(slug: str | None) -> str:
    def read():
        if not slug:
            return "no deck"
        mascot = REPO / "carousels" / slug / "mascot"
        fresh = len(list(mascot.glob("*_fresh.png")))
        kept = len(list((mascot / "_library_candidates").glob("*.png")))
        if not fresh:
            return "all from the library"
        return f"{fresh} generated, {kept} added to the library"
    return _safe(read)


def measured() -> str:
    """The last three days of reach, if the insights ledger has been written.

    Read-only and reported only. Invariant 17: a number here must never reach
    the pipeline, so this prints it and nothing else consumes it.
    """
    def read():
        path = STATE / "insights.jsonl"
        if not path.is_file():
            return "no measurements yet"
        rows = [json.loads(line) for line in path.open() if line.strip()][-3:]
        if not rows:
            return "no measurements yet"
        parts = []
        for r in rows:
            reach = r.get("reach")
            saves = r.get("saves")
            parts.append(f"{r.get('slug', '?')[:18]} "
                         f"reach {reach if reach is not None else '—'} "
                         f"saves {saves if saves is not None else '—'}")
        return " · ".join(parts)
    return _safe(read)


def build(status: str, slug: str | None, note: str, score: str | None,
          run_url: str | None) -> str:
    head = f"{ICON.get(status, 'ℹ')} {status.upper()}"
    if slug:
        head += f"  {slug}"
    if score:
        head += f"  ({score}/100)"

    lines = [head, f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    if note:
        lines += [note, ""]
    lines += [
        f"PICTURES   {pictures()}",
        f"LIBRARY    {library()}",
        f"THIS DECK  {poses_used(slug)}",
        f"QUEUE      {queue()}",
        f"REVIEW     {waiting()}",
        f"MEASURED   {measured()}",
    ]
    if run_url:
        lines += ["", f"logs: {run_url}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="ok",
                    choices=["ok", "held", "stopped", "error"])
    ap.add_argument("--slug")
    ap.add_argument("--note", default="")
    ap.add_argument("--score")
    ap.add_argument("--run-url")
    a = ap.parse_args(argv)
    print(build(a.status, a.slug, a.note, a.score, a.run_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
