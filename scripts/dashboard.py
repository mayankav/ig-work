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
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".agents" / "skills" / "suresilly-carousel"
STATE = REPO / "state"

# One direction only. This script reads the engine — outcomes.py for what a fault
# trail means, capacity.py for what is left — and NOTHING in the engine imports
# this. That is the same rule invariant 17 states for insights.py, for the same
# reason: a report that can change a decision is not a report.
sys.path.insert(0, str(SKILL / "scripts"))

# India has no daylight saving, so the offset is a constant and no timezone
# database is needed. Every schedule in this repo is stated in IST — the cron
# comments, the workflow, these messages — while the runner's clock is UTC, and a
# message that prints UTC and then says "the next run is 20:00" makes the reader
# do arithmetic they will get wrong at least once.
IST = timezone(timedelta(hours=5, minutes=30))

# Three colours, and the icons carry them. `stopped` was 🛑, which is a red
# octagon — the wrong signal for the one outcome that means a gate did its job
# and nothing is wrong. Amber now, so the phone can be read at a glance:
# ✅ posted · ⏸ waiting for you · ⚠️ nothing today, nothing broken · ❌ broken.
ICON = {"ok": "✅", "held": "⏸", "stopped": "⚠️", "error": "❌"}

# THE COLOUR KEY.
#
# Telegram's HTML has bold, italic and <code>. It has no coloured text. So the
# colour in these messages is emoji, and an emoji only works as colour if it
# means the same thing every time — a stray one makes the whole key mean less.
# test_message.py asserts every emoji a message prints comes from here or from
# REPLIES, because a key that is only a convention is one edit from being wrong.
MARK = {
    "ok": "🟢", "held": "🟠", "stopped": "🔴", "error": "🔴",
    "pass": "✔", "fail": "✘", "look": "⚠️", "no": "🚫", "problem": "❌",
    "what": "📝", "self": "🔁", "you": "💬", "idle": "⏰",
    "logs": "🔗", "note": "ℹ️", "eye": "👆",
    "pictures": "🖼", "writing": "✍️", "library": "📚",
    "deck": "🎨", "queue": "📦", "review": "📥", "measured": "📈",
}

# The headline of each message. Says what happened, in words that need no
# knowledge of how the engine works. "A gate refused" is not here on purpose:
# the owner does not have to know what a gate is.
TITLE = {
    "ok": "POSTED",
    "held": "READY — WAITING FOR YOU",
    "stopped": "NOTHING WAS POSTED",
    "error": "SOMETHING IS BROKEN",
}

# Every reply the owner may send, per outcome, with what it does. One list, one
# order, every message — so the options are in the same place on the screen every
# morning and can be found without reading.
#
# `{id}` is filled with the short deck id. A verb that cannot work keeps its line
# and loses its emoji to 🚫: hiding the word would make the owner think it does
# not exist, and they would go looking for it.
REPLIES = {
    "ok": [("📋", "list", "Show what waits for your answer.")],
    "held": [("✅", "publish {id}", "Post it now, as it is."),
             ("🗑", "rerun {id}", "Throw it away. Tonight builds another."),
             ("📋", "list", "Show what else waits.")],
    "stopped": [("🔨", "force", "Build it anyway. I send you the picture. "
                                "Nothing goes out until you reply publish."),
                ("📋", "list", "Show what waits for your answer."),
                ("🔄", "retry", "Start again with a new idea.")],
    "error": [("🔄", "retry", "Try the whole run again now."),
              ("📋", "list", "Show what waits for your answer.")],
}

# What happens if the message is ignored. Asked on every alert this engine has
# ever sent, and answered on none of them.
IDLE = {
    "ok": "Nothing to do. The next run is {next}.",
    "held": "Nothing happens until you reply. It will not post on its own.",
    "stopped": "The next run starts {next}. Nothing is lost.",
    "error": "The next run starts {next} anyway. This one still needs a look.",
}

# A fault, said the way a person would say it.
#
# The fault strings are written for the model, because they are fed straight back
# into the repair prompt — they name field labels and quote rules. That is right
# for the model and wrong for a phone at breakfast.
#
# This table starts nearly empty ON PURPOSE and falls back to the raw fault text
# when there is no entry. An entry is added only when state/gate_faults.jsonl
# shows a check is actually blocking runs, so nothing here is written on a guess.
# The match is a substring of the fault, lowercased.
#
# Each entry is (what the check wants, a good line, a bad line, why). The BAD line
# is the one place in this file where a long word is allowed — quoting the word
# the gate refused is how the owner learns which word, and test_message.py knows
# that position is a quotation and skips it.
PLAIN = {
    "kind of person": (
        "The last slide must name a kind of person to send it to.",
        "Send this to the friend who always says yes.",
        "Send this to anyone who relates.",
        '"Anyone" is not a person.'),
    "syllables or more": (
        "One line uses a word that is too long to read fast.",
        "the weight you carry",
        "the emotional load you carry",
        "Say it in short words. The idea stays sharp."),
}


def say_plainly(fault: str) -> list[str]:
    """One fault, as lines a person can read. Falls back to the raw text.

    The fallback is the important half. A gate added next month has no entry
    here, and its fault must still reach the owner — badly worded beats missing.

    Every line comes out already wrapped to phone width, including the fallback.
    A gate writes its fault for a repair prompt, so it is one long line, and one
    long line on a phone is the shape the eye skips.
    """
    low = fault.lower()
    for needle, (what, good, bad, why) in PLAIN.items():
        if needle in low:
            return (_wrap(what)
                    + _hang(f'{MARK["pass"]} "{good}"')
                    + _hang(f'{MARK["fail"]} "{bad}"')
                    + _wrap(why))
    return _wrap(fault)


def _hang(text: str, width: int = 36) -> list[str]:
    """An example, indented, with its wrapped tail lined up under its first word
    rather than under its ✔ — so the mark stays a column the eye can run down."""
    return [f"   {part}" if i == 0 else f"     {part}"
            for i, part in enumerate(_wrap(text, width))]


RULE = "━━━━━━━━━━━━━━━━━━━━━━━"

# What a held message must fit inside, and the only hard number in this file.
#
# A held deck carries the contact sheet, so its text is a CAPTION, and Telegram
# caps a caption at 1024 and rejects an over-long one outright rather than
# trimming it. notify.CAPTION_LIMIT is 1000 and spills the remainder into a
# follow-up message, so nothing is ever lost — but the cut lands at a line
# boundary near the end, which is exactly where the reply list is, and the reply
# list is the only part of a held message that has to be read.
#
# Measured, not chosen. With a two-line reviewer note the message is 922
# characters before a single objection, and each objection costs 30 to 55 more:
# two of them reach 1005 and the cut fires. A fixed count of six could never have
# been right, because what fits depends on how long each one is — so the count is
# not fixed. `_fit_held` renders, measures, and drops the tail until it fits,
# saying how many it dropped. test_message.py imports this number.
CAPTION_BUDGET = 1000

# The longest reviewer note a held caption will print.
#
# Measured on the rendered message, not estimated. A held message is 818
# characters with no note and no objections; the note costs about one character
# each and so does everything else. Holding the objections at the one summary
# line — the shortest a held message can be while still saying something was
# dropped — the floor fits up to a 145-character note and goes over at 153. So
# 140, plus the one-character ellipsis, is the longest note that can never on its
# own push the reply list into a second message.
#
# This is the lever the objection fitter does not have. Dropping every objection
# still leaves the note, so a long note overflows alone: a realistic critic
# paragraph rendered at 1101 characters and no amount of dropping brought it
# back. Trimmed rather than dropped, because half a reason beats none, and the
# message already ends with a link to the full log.
NOTE_BUDGET = 140

# The shape writer.write_deck puts on the end of a refusal reason:
#
#   slide 9 names nobody; slide 4 uses 'emotional' … [faults per attempt: 13, 5, 4]
#
# One string, because an exception carries one. It is split back apart here rather
# than being carried as two fields, because the string is what survives the trip
# out of the run and through $GITHUB_OUTPUT into the workflow — and the workflow
# is where the message used to be a constant that could see none of it.
TRAIL = re.compile(r"\[faults per attempt:\s*([\d,\s]+)\]")


def read_trail(reason: str) -> list[int]:
    """The fault count per attempt, out of a refusal reason. Empty if absent."""
    match = TRAIL.search(reason or "")
    if not match:
        return []
    return [int(n) for n in re.findall(r"\d+", match.group(1))]


def split_faults(reason: str) -> list[str]:
    """The individual faults out of a refusal reason.

    Semicolons, because that is what write_deck joins them with. The trail is cut
    off first so it does not arrive as a fourth fault, and a reason with no
    semicolon is one fault, not zero — a single blocking check is the common case
    and it was the one shape a naive split would have dropped.
    """
    body = TRAIL.sub("", reason or "").strip()
    if not body:
        return []
    return [part.strip() for part in body.split(";") if part.strip()]


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


def blocked_runs(fault: str) -> int:
    """How many runs this fault has already stopped, from the fault ledger.

    Read-only, and it changes nothing. Invariant 17's rule applied to gates: the
    count is reported so the owner knows which check to fix next, and no part of
    the pipeline may read it or act on it. A missing ledger is 0 runs recorded,
    which is not the same as a claim that the fault is new — it means nobody has
    counted yet, and the caller only prints the line when the count is above 1.
    """
    def read():
        path = STATE / "gate_faults.jsonl"
        if not path.is_file():
            return 0
        key = fault.lower()[:60]
        seen = 0
        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            if any(key in str(f).lower() for f in row.get("faults", [])):
                seen += 1
        return seen
    return _safe(read, default=0)


def next_slot(now: datetime | None = None) -> str:
    """Which run comes next, in the owner's own clock. See IST above for why."""
    ist = (now or datetime.now(timezone.utc)).astimezone(IST)
    return "at 20:00 tonight" if ist.hour < 20 else "at 08:00 tomorrow"


def stamp(now: datetime | None = None) -> str:
    """Wednesday 3 September · 08:34 IST."""
    ist = (now or datetime.now(timezone.utc)).astimezone(IST)
    return f"{ist:%A %-d %B · %H:%M} IST"


def build(status: str, slug: str | None, note: str, score: str | None,
          run_url: str | None, fmt: str = "text", *,
          history: list[int] | None = None, retry: bool = True,
          objections: list[str] | None = None,
          reply_id: str | None = None) -> str:
    """The report, as text (email, logs) or Telegram HTML.

    ONE template, four outcomes. Every message answers the same five questions,
    in the same order, in the same place on the screen:

        what happened · what went wrong · can I fix it myself ·
        what can you reply · what happens if you ignore this

    Every message used to answer a different subset of those. The posted one was
    a dashboard with no reply list; the held one was a decision with no dashboard;
    the stopped one was a hardcoded sentence in a workflow file that could not see
    the actual reason. So the owner had to learn three shapes and still could not
    tell a stuck check from an unlucky draft.

    HTML mode bolds the head and the section labels and links the logs line, and
    escapes every dynamic value with html.escape. The tags it uses — <b> and a
    single-line <a> — never span a newline, which is the rule notify.py relies on
    to split a long caption safely: cut at a newline and both halves are still
    valid HTML.

    `history` is the fault count per attempt. `retry` is False when the count
    stopped falling, and then the retry line is marked 🚫 with the reason rather
    than removed — a verb hidden is a verb the owner goes looking for.
    """
    notes = list(objections or [])
    if status == "held":
        # Fit the objections to the caption budget before anything is sent. See
        # CAPTION_BUDGET: a held message that overflows loses its reply list to a
        # second message, and the reply list is the only part that has to be read.
        #
        # The note is trimmed first, because the fitter's only other lever is
        # dropping objections and a long note overflows on its own — measured at
        # 1101 characters on a realistic critic paragraph, which no number of
        # dropped objections can bring back under the cap.
        note = _clip(note, NOTE_BUDGET)
    render = lambda keep: _assemble(                          # noqa: E731
        status, slug, note, score, run_url, fmt, history=history,
        retry=retry, objections=keep, reply_id=reply_id)
    if status == "held":
        notes = _fit_held(notes, render)
    return render(notes)


def _clip(text: str, limit: int) -> str:
    """Cut at a word and mark the cut. Empty stays empty.

    The marker is a word, not a bare ellipsis: `…` alone reads as a sentence
    trailing off, which is what a critic's note does anyway, so nothing would
    tell the owner there is more to read.
    """
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[:limit].rsplit(" ", 1)[0] + "…"


def _fit_held(notes: list[str], render) -> list[str]:
    """Drop objections from the end until the message fits the caption budget.

    Rendering to measure, rather than counting characters, because the length
    depends on wrapping, on HTML escaping and on how long the reviewer's note
    was — three things a fixed cap cannot see. That is why the old `[:6]` could
    never have been right: six short objections fit and two long ones do not.

    The last line always says how many were dropped, so the message never quietly
    shows three of five. Nothing is lost either way — the full list is in the run
    log, and the link to it is in the message.

    It can go all the way down to that one summary line, and it has to be able
    to: a single objection long enough to blow the budget on its own is not
    hypothetical, and a floor of "always show one" would put the reply list into
    a second message to protect a line the owner cannot read anyway. The floor
    that matters is the reply list, not the objections.
    """
    def summarised(shown: int) -> list[str]:
        if shown >= len(notes):
            return list(notes)
        dropped = len(notes) - shown
        return notes[:shown] + [f"and {dropped} more — see the full log"]

    for shown in range(len(notes), -1, -1):
        if len(render(summarised(shown))) <= CAPTION_BUDGET:
            return summarised(shown)
    # Even the bare summary line does not fit, which means the reviewer's own
    # note is the thing over budget. Send the shortest form there is and let
    # notify.py spill; it cuts at a line boundary, so the reply list survives
    # whole in the follow-up rather than being cut through the middle.
    return summarised(0)


def _assemble(status: str, slug: str | None, note: str, score: str | None,
              run_url: str | None, fmt: str = "text", *,
              history: list[int] | None = None, retry: bool = True,
              objections: list[str] | None = None,
              reply_id: str | None = None) -> str:
    """The template itself. build() is the door; this is the room.

    Split out so a held message can be rendered, measured and rendered again with
    fewer objections — see _fit_held. Nothing else calls this directly.
    """
    is_html = fmt == "html"
    esc = html.escape if is_html else (lambda s: s)
    bold = (lambda s: f"<b>{s}</b>") if is_html else (lambda s: s)
    code = (lambda s: f"<code>{s}</code>") if is_html else (lambda s: s)

    short = reply_id or (slug.rsplit("_", 1)[-1] if slug and "_" in slug else slug) or ""

    lines: list[str] = []

    def rule() -> None:
        """A divider, with exactly one blank line under it and none above it.

        Every block ends with a spacer so the blocks inside it breathe, which used
        to leave a gap above each divider and made the message look like it had
        holes in it. The trim lives here, once, instead of in every block.
        """
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend([RULE, ""])

    lines += [bold(f"{MARK.get(status, 'ℹ️')} {TITLE.get(status, status.upper())}"),
              stamp()]
    rule()

    if status == "ok":
        lines += _body_ok(slug, esc, bold)
    elif status == "held":
        lines += _body_held(note, score, objections or [], esc, bold)
    else:
        lines += _body_refused(status, note, history or [], retry, esc, bold)

    rule()
    lines += _replies(status, short, retry, esc, bold, code)
    rule()
    lines += [f"{bold(MARK['idle'] + ' IF YOU DO NOTHING')}"]
    lines += _wrap(IDLE.get(status, "").format(next=next_slot()))
    lines += [""]

    # The one message that carries an attachment and a single reply does not need
    # the footer twice. Everything else does: "ok" and "yes" arrive in this chat
    # by accident, and one of them would publish, so they are excluded on purpose
    # and the owner has to be told that or they will try one.
    if status != "ok":
        lines += [f"{MARK['note']} Only the words above work.",
                  '   "ok", "yes" and "no" do nothing.', ""]

    if run_url:
        lines += [f'{MARK["logs"]} <a href="{esc(run_url)}">See the full log</a>'
                  if is_html else f'{MARK["logs"]} See the full log: {run_url}']
    return "\n".join(lines).rstrip() + "\n"


def _body_ok(slug: str | None, esc, bold) -> list[str]:
    """A deck went out. The dashboard, because this is the one message where
    nothing needs deciding and there is room to say how the engine is holding up.

    Kept to short rows: this message carries the contact sheet, so it is a caption
    and Telegram caps a caption at 1024 and REJECTS an over-long one outright.
    """
    head_writing, rows_writing = writing()
    out = [f"{MARK['pass']} {esc(slug or 'a deck')} is live.", ""]
    out += [
        f"{MARK['pictures']} {bold('Pictures')}  {esc(pictures())}",
        f"{MARK['writing']} {bold('Writing')}   {esc(head_writing)}",
        *[f"   {esc(row.strip())}" for row in rows_writing],
        f"{MARK['library']} {bold('Library')}   {esc(library())}",
        f"{MARK['deck']} {bold('This deck')} {esc(poses_used(slug))}",
        f"{MARK['queue']} {bold('Queue')}     {esc(queue())}",
        f"{MARK['review']} {bold('Waiting')}   {esc(waiting())}",
        f"{MARK['measured']} {bold('Measured')}  {esc(measured())}",
        "",
    ]
    return out


def _body_held(note: str, score: str | None, objections: list[str],
               esc, bold) -> list[str]:
    """A finished deck, waiting for a person. The green block and the orange
    block ARE the decision.

    Green is what the owner cannot check by looking — whether the source is real,
    whether the artwork is clean, whether the idea has been posted before. Orange
    is what they can. Splitting them means the message says "the parts you have to
    trust me on are fine; here is the part you are better at" in two glances.

    `note` is the reviewer's one-line reason and it is printed. It used to be
    accepted and dropped: `--note` is the flag that carries the real reason on
    every other status, and a held deck that silently discarded it was the same
    defect this whole change exists to fix, one status along.

    Under 1000 characters, because the contact sheet is attached and the caption
    limit is real. How many objections fit is not a number in this function —
    build() measures the rendered message and hands over the ones that fit, plus
    a line saying how many it dropped. See CAPTION_BUDGET and _fit_held.
    """
    out = ["I built this for you to judge.",
           "It will NOT post on its own.", ""]
    if score:
        out += [esc(_score_line(score))]
    if note:
        out += [esc(part) for part in _wrap(note)]
    if score or note:
        out += [""]
    out += [bold(f"{MARK['ok']} SAFETY CHECKS — all passed"),
            f"   {MARK['pass']} The source is proved",
            f"   {MARK['pass']} No text in the pictures",
            f"   {MARK['pass']} This idea is new",
            ""]
    if objections:
        out += [bold(f"{MARK['held']} STYLE CHECKS — {len(objections)} objection"
                     f"{'s' if len(objections) != 1 else ''}")]
        for note in objections:
            out += [esc(part) for part in _hang(f"{MARK['fail']} {note}")]
    else:
        out += [bold(f"{MARK['held']} STYLE CHECKS — nothing to report")]
    out += ["", f"{MARK['eye']} Look at the picture, then reply.", ""]
    return out


def _score_line(score: str) -> str:
    """The critic's score, said once.

    `run.py` passes the bare number it got from `critic.review`, but a person
    typing `--score` on the command line writes `7.5/10`. Appending " of 100" to
    either produced "Score 7.5/10 of 100", which is two scales in one sentence and
    the reader has to work out which one is real. A value that already carries its
    own denominator keeps it.
    """
    text = str(score).strip()
    return f"Score {text}." if "/" in text or "%" in text else f"Score {text} of 100."


def _body_refused(status: str, note: str, history: list[int], retry: bool,
                  esc, bold) -> list[str]:
    """Nothing was posted, or something is broken. Three blocks.

    WHAT HAPPENED and CAN I FIX IT MYSELF the engine writes on its own, from the
    attempt count and the fault trail. Only THE PROBLEM comes from a gate, and a
    gate's fault is written for the model that has to repair it — so it goes
    through say_plainly, which rewrites the ones we have measured as blockers and
    passes the rest through unchanged rather than dropping them.
    """
    import outcomes

    faults = split_faults(note)
    trail = read_trail(note) or list(history)
    out = [bold(f"{MARK['what']} WHAT HAPPENED")]
    if status == "error":
        # An error reason is raw vendor text — long, and with no newline in it. It
        # gets wrapped like everything else, or it arrives as one unreadable slab
        # on the one message that most needs reading.
        out += [esc(part) for part in _wrap(note or "The run did not finish.")]
        out += ["", bold(f"{MARK['self']} CAN I FIX IT MYSELF?")]
        out += _wrap("A new try may help after a short outage." if retry else
                     "No. This fault needs a fix before a new try.")
        out += [""]
        return out

    tries = len(trail) if trail else 1
    out += [f"I wrote the carousel {tries} time{'s' if tries != 1 else ''}.",
            f"A quality check refused {'all ' + str(tries) if tries > 1 else 'it'}.",
            ""]
    if faults:
        out += [bold(f"{MARK['problem']} THE PROBLEM")]
        # Three at most. The fourth is the one nobody reads, and the reply list
        # below it is the only part of this message that has to be read.
        for fault in faults[:3]:
            out += [esc(line) for line in say_plainly(fault)]
            seen = blocked_runs(fault)
            if seen > 1:
                out += [f"   {MARK['look']} This check has blocked {seen} runs."]
            out += [""]
    out += [bold(f"{MARK['self']} CAN I FIX IT MYSELF?")]
    shape, why = outcomes.trajectory(trail)
    out += ["Not this time." if retry else "No. A new try is not advised."]
    if trail:
        out += [f"   {outcomes.arrow(trail)}"]
    out += [f"   {esc(part)}" for part in _wrap(why, 40)]
    return out


def _replies(status: str, short: str, retry: bool, esc, bold, code) -> list[str]:
    """Every reply the owner may send, and what each one does.

    In the same place, in the same order, on every message. A verb that cannot
    work keeps its line and loses its emoji to 🚫 — hiding it would make the owner
    think the word does not exist and go looking for it. Only `retry` is ever
    withheld, and only when the fault count stopped falling, which means a fresh
    idea walks into the same check.
    """
    out = [bold(f"{MARK['you']} REPLY WITH ONE WORD"), ""]
    for emoji, verb, what in REPLIES.get(status, []):
        word = verb.format(id=short) if "{id}" in verb else verb
        if verb == "retry" and not retry:
            out += [f"{MARK['no']} {code(esc(word))}",
                    "   Starts a new idea. Not advised —",
                    "   the same check will stop it.", ""]
            continue
        out += [f"{emoji} {code(esc(word))}"]
        out += [f"   {esc(part)}" for part in _wrap(what)]
        out += [""]
    return out


def _wrap(text: str, width: int = 38) -> list[str]:
    """Short lines. A phone is about 38 characters wide at a readable size, and a
    line that wraps in the middle of a phrase is the difference between scanning
    a message and reading it."""
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="ok",
                    choices=["ok", "held", "stopped", "error"])
    ap.add_argument("--slug")
    ap.add_argument("--note", default="",
                    help="the real reason, as run.py printed it. For a refusal "
                         "this is the fault list and the per-attempt trail, and "
                         "both are read back out of it")
    ap.add_argument("--score")
    ap.add_argument("--run-url")
    ap.add_argument("--reply-id",
                    help="the short deck id a reply names. Defaults to the last "
                         "segment of the slug, which is what release.find matches")
    ap.add_argument("--objection", action="append", default=[],
                    help="one style objection on a held deck. Repeatable")
    ap.add_argument("--no-retry", action="store_true",
                    help="the fault count stopped falling, so a fresh idea walks "
                         "into the same check. The retry line is marked 🚫 with "
                         "the reason rather than removed")
    ap.add_argument("--format", default="text", choices=["text", "html"],
                    help="html is Telegram-flavoured (bold labels, tap-to-copy "
                         "verbs, linked logs); text is for email and the run log")
    a = ap.parse_args(argv)
    print(build(a.status, a.slug, a.note, a.score, a.run_url, a.format,
                retry=not a.no_retry, objections=a.objection,
                reply_id=a.reply_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
