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

Kept short on purpose. Telegram caps a media caption at 1024 characters and
rejects an over-long one outright rather than trimming it, so notify.py cuts at
1000 and spills the rest into a follow-up message. Nothing is lost either way,
but a report split across two messages is a report half of which gets skimmed —
so this aims well under the cap, puts the line that changes decisions at the
top, and expands the per-vendor rows only when one of them is near an edge.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "suresilly-carousel"
STATE = REPO / "state"

# Three colours, and the icons carry them. `stopped` was 🛑, which is a red
# octagon — the wrong signal for the one outcome that means a gate did its job
# and nothing is wrong. Amber now, so the phone can be read at a glance:
# ✅ posted · ⏸ waiting for you · ⚠️ nothing today, nothing broken · ❌ broken.
ICON = {"ok": "✅", "held": "⏸", "stopped": "⚠️", "error": "❌"}


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


def _bar(share: float, width: int = 10) -> str:
    full = max(0, min(width, round(share * width)))
    return "▓" * full + "░" * (width - full)


def _age(seconds) -> str:
    """A reading has to carry its own age. Groq's allowance drips back all day,
    so a figure from yesterday evening is not a figure about this morning, and
    printing it bare would be the most confident wrong number in the report."""
    if seconds is None:
        return ""
    if seconds < 2 * 3600:
        return ""
    if seconds < 48 * 3600:
        return f"  (seen {seconds / 3600:.0f}h ago)"
    return f"  (seen {seconds / 86400:.0f}d ago)"


def _refill(seconds) -> str:
    if seconds is None:
        return "drips back continuously"
    if seconds < 90:
        return f"full again in {seconds:.0f}s"
    if seconds < 5400:
        return f"full again in {seconds / 60:.0f}m"
    return f"full again in {seconds / 3600:.1f}h"


def _vendor_row(v: dict) -> str:
    """One vendor, in its own unit. No conversion, because there is no exchange
    rate between a neuron and a request and inventing one would put a number in
    the report that no vendor could account for."""
    name = f"  {v['name']:<11}"
    if not v.get("known"):
        # The unknown is spelled out rather than drawn. A bar here would be a
        # guess with the shape of a measurement, and how many requests we MADE
        # is not how many are LEFT.
        made = v.get("made")
        figure = f"{made} made today" if made is not None else "not counted"
        tail = v.get("note", "")
        out, total = v.get("models_out"), v.get("models_total")
        if out:
            tail = f"{out} of {total} models out of quota" if total else \
                   f"{out} model(s) out of quota"
        return f"{name}{figure:<20}?   {tail}"
    figure = f"{v['remaining']}/{v['limit']} {v['unit']}"
    if v["name"] == "groq":
        tail = _refill(v.get("refills_in_seconds")) + _age(v.get("age_seconds"))
    else:
        tail = "of the writing share, resets 00:00 UTC"
    return f"{name}{figure:<20}{_bar(v.get('share', 0.0))}  {tail}"


def writing() -> tuple[str, list[str]]:
    """Writing shares the one daily allowance with pictures, and it is the half
    that must never run out — a deck that cannot be written is a day with no
    post. It is recorded and never refused, so this line is the warning.

    Returns a headline and, only when something is actually near an edge, a row
    per vendor. Three vendors printed every morning is three lines you learn to
    skip, and Telegram truncates a caption at 1000 characters — a held deck is
    771 of them before any of this, so the rows have to earn their place.
    """
    def read():
        sys.path.insert(0, str(REPO / "scripts"))
        import capacity
        vendors = capacity.snapshot()["vendors"]
        low = [v for v in vendors if v.get("low")]
        if not low:
            return "all vendors have room", []
        # Each vendor states its OWN reason. One shared phrase would have to be
        # vague enough to fit all three, and "near the end of its share" is not
        # what happened when two of Gemini's five models went out of quota.
        why = " · ".join(f"{v['name']}: {v['low_because']}" if v.get("low_because")
                         else v["name"] for v in low)
        return f"⚠ {why}", [_vendor_row(v) for v in vendors]
    return _safe(read, default=("unknown", []))


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
          run_url: str | None, fmt: str = "text") -> str:
    """The report, as text (email, logs) or Telegram HTML.

    HTML mode bolds the head and the section labels and links the logs line, and
    escapes every dynamic value with html.escape. The tags it uses — <b> and a
    single-line <a> — never span a newline, which is the rule notify.py relies on
    to split a long caption safely: cut at a newline and both halves are still
    valid HTML. The text mode is byte-for-byte what it always was.
    """
    is_html = fmt == "html"
    esc = html.escape if is_html else (lambda s: s)

    def label(name: str) -> str:
        # Text keeps the original column: every value begins at column 11, so the
        # longest label ("THIS DECK", 9 chars) sets the pad and the rest align to
        # it. HTML can't hold a column without <pre> (which would span newlines
        # and break the caption split), so there the bold carries the separation.
        return f"<b>{name}</b>  " if is_html else f"{name:<9}  "

    head = f"{ICON.get(status, 'ℹ')} {status.upper()}"
    if slug:
        head += f"  {esc(slug)}"
    if score:
        head += f"  ({esc(score)}/100)"
    if is_html:
        head = f"<b>{head}</b>"

    lines = [head, f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    if note:
        lines += [esc(note), ""]
    head_writing, rows_writing = writing()
    lines += [
        f"{label('PICTURES')}{esc(pictures())}",
        f"{label('WRITING')}{esc(head_writing)}",
        *[esc(row) for row in rows_writing],
        f"{label('LIBRARY')}{esc(library())}",
        f"{label('THIS DECK')}{esc(poses_used(slug))}",
        f"{label('QUEUE')}{esc(queue())}",
        f"{label('REVIEW')}{esc(waiting())}",
        f"{label('MEASURED')}{esc(measured())}",
    ]
    if run_url:
        logs = (f'logs: <a href="{esc(run_url)}">{esc(run_url)}</a>' if is_html
                else f"logs: {run_url}")
        lines += ["", logs]
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
    ap.add_argument("--format", default="text", choices=["text", "html"],
                    help="html is Telegram-flavoured (bold labels, linked logs); "
                         "text is for email and the run log")
    a = ap.parse_args(argv)
    print(build(a.status, a.slug, a.note, a.score, a.run_url, a.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
