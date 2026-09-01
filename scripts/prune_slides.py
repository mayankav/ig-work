#!/usr/bin/env python3
"""
prune_slides.py — keep the public slide host inside a retention window.

The slides are published to gh-pages so that Instagram can fetch them, and
Instagram fetches each image exactly once, at container creation. After that the
post is served from Instagram's own CDN and the copy on our host is archive.
Nothing removed the archive, so `slides/` grew by about 11 MB a day forever
against a GitHub Pages site limit of 1 GB.

This deletes deck folders older than the window and nothing else.

    prune_slides.py --root gh-pages/slides --days 14 --protect <slug>

Three things it will not do, because each one would be a worse failure than the
disk filling up:

  * it never removes a slug named by --protect, which is the deck this run just
    published, nor one named by --protect-if-present, which is a deck still
    waiting in state/pending for the owner to answer. release.py posts a held
    deck from this host days after it was built, so pruning it is what turns a
    late "publish" reply into nine 404s;
  * it never removes the newest --keep-min folders, whatever their age, so a
    pause in posting cannot empty the host;
  * it never removes a folder whose name it cannot read as a date. A folder we
    do not understand is not a folder we are allowed to delete.

And it aborts rather than reporting a tidy nothing: an unreadable root, a
protected slug that is not on the host, a layout where no name parses, or a
delete that fails are all non-zero exits. "We could not check" must never come
out looking the same as "there was nothing to do".
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Slugs are built as `%Y%m%d` + "_" + scene token, by deck_slug() in run.py. The
# name is the only date we can trust: a git checkout stamps every file with the
# time of the checkout, so mtime on the host says "today" for all of them.
SLUG_DATE = re.compile(r"^(\d{8})_")

# Fourteen days. The window is not set by what Instagram needs — that is minutes
# — but by the one path that reaches back for an old URL: a deck held for review.
# It waits in state/pending with no expiry until the owner replies on Telegram —
# the reply pushes to the Cloudflare Worker, which dispatches review.yml, and
# release.py then posts it from
# https://media.suresilly.com/slides/<slug>/slides. That latency is a person's,
# not a machine's. Two weeks covers a holiday; at two decks a day it leaves about
# 28 decks live, roughly 160 MB, a sixth of the 1 GB Pages limit.
DEFAULT_DAYS = 14

# A floor under the window, for the case the window cannot cover: if posting
# stops for a month, every folder ages out and a deck still waiting on a reply
# would go with them. Eight is four days of posting at two a day.
DEFAULT_KEEP_MIN = 8


class Abort(Exception):
    """A gate said no. Nothing is deleted after one of these."""


def read_date(name: str) -> datetime | None:
    """The build date encoded in a deck folder name, or None if it is not one."""
    match = SLUG_DATE.match(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def folder_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def plan(root: Path, today: datetime, days: int, keep_min: int,
         protect: set[str], held: set[str] | None = None
         ) -> tuple[list[Path], list[str]]:
    """Decide what goes. Returns (to remove, lines to print).

    Two kinds of protection, and the difference matters.

    `protect` is the deck this run just published. It MUST be on the host, and
    its absence aborts, because pruning around a deck that is not there would
    hide a publish that did not land.

    `held` is the decks still waiting in state/pending for the owner to answer.
    They must survive the window — release.py posts them from this host days
    later, and a pruned folder means nine 404s and a deck that can never go out.
    But a held slug that is ALREADY gone must not abort: that would wedge every
    future prune on a mistake made once. Protect it if it is there, say so if it
    is not, and carry on.
    """
    if not root.is_dir():
        raise Abort(f"nothing to prune at {root}: it is not a directory")

    folders = sorted(p for p in root.iterdir() if p.is_dir())
    if not folders:
        raise Abort(f"{root} holds no deck folders. The publish step should have "
                    f"just put one there, so this is a broken layout, not an empty host")

    held = held or set()
    gone = sorted(slug for slug in held if not (root / slug).is_dir())
    protect = protect | (held - set(gone))

    missing = sorted(slug for slug in protect if not (root / slug).is_dir())
    if missing:
        raise Abort("the deck this run published is not on the host: "
                    + ", ".join(missing) + ". The publish did not land, and "
                    "pruning around a deck that is not there would hide that")

    dated = [(read_date(p.name), p) for p in folders]
    unknown = [p.name for when, p in dated if when is None]
    known = sorted(((when, p) for when, p in dated if when is not None),
                   key=lambda pair: (pair[0], pair[1].name))
    if not known:
        raise Abort(f"none of the {len(folders)} folders under {root} is named "
                    f"<YYYYMMDD>_<slug>. The naming changed and this script would "
                    f"be guessing")

    cutoff = today - timedelta(days=days)
    floor = {p.name for _, p in known[-keep_min:]} if keep_min > 0 else set()

    remove: list[Path] = []
    for when, path in known:
        if path.name in protect or path.name in floor or when >= cutoff:
            continue
        remove.append(path)

    lines = [f"host {root}: {len(folders)} deck folder(s), "
             f"window {days} day(s) back to {cutoff:%Y-%m-%d}, "
             f"floor {keep_min} newest kept"]
    if unknown:
        # Kept, and said out loud. Silence here is how a stray folder becomes a
        # permanent 7 MB nobody remembers agreeing to.
        lines.append(f"  not date-named, kept untouched: {', '.join(sorted(unknown))}")
    if protect:
        lines.append(f"  protected: {', '.join(sorted(protect))}")
    if gone:
        # Loud, but not fatal. See the docstring: a held deck already off the
        # host cannot be posted, and the owner needs to know that before they
        # reply to a review that can no longer be honoured.
        lines.append(f"  ::warning::held deck(s) no longer on the host, "
                     f"release.py cannot post them: {', '.join(gone)}")
    return remove, lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True,
                    help="the directory holding one folder per published deck, "
                         "e.g. gh-pages/slides")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"keep decks built within this many days (default {DEFAULT_DAYS})")
    ap.add_argument("--keep-min", type=int, default=DEFAULT_KEEP_MIN,
                    help=f"always keep this many newest decks (default {DEFAULT_KEEP_MIN})")
    ap.add_argument("--protect", action="append", default=[], metavar="SLUG",
                    help="a deck that must survive and must be present. Repeatable")
    ap.add_argument("--protect-if-present", action="append", default=[], metavar="SLUG",
                    help="a deck awaiting review: kept when present, warned about "
                         "when not, never fatal. Repeatable")
    ap.add_argument("--today", metavar="YYYYMMDD",
                    help="pretend today is this date. For the tests")
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would go, delete nothing")
    args = ap.parse_args()

    if args.days < 1 or args.keep_min < 0:
        print("::error::--days must be at least 1 and --keep-min cannot be negative",
              file=sys.stderr)
        return 2

    today = datetime.now(timezone.utc)
    if args.today:
        parsed = read_date(args.today + "_")
        if parsed is None:
            print(f"::error::--today {args.today!r} is not YYYYMMDD", file=sys.stderr)
            return 2
        today = parsed

    try:
        remove, lines = plan(Path(args.root), today, args.days, args.keep_min,
                             set(args.protect), set(args.protect_if_present))
    except Abort as why:
        print(f"::error::prune refused: {why}", file=sys.stderr)
        return 1

    for line in lines:
        print(line)

    if not remove:
        print("  nothing is old enough to remove")
        return 0

    freed = 0
    failed: list[str] = []
    for path in remove:
        size = folder_size(path)
        if args.dry_run:
            print(f"  would remove {path.name} ({size / 1e6:.1f} MB)")
            freed += size
            continue
        try:
            shutil.rmtree(path)
        except OSError as exc:
            failed.append(f"{path.name}: {exc}")
            continue
        freed += size
        print(f"  removed {path.name} ({size / 1e6:.1f} MB)")

    verb = "would free" if args.dry_run else "freed"
    print(f"  {len(remove) - len(failed)} folder(s) {verb} {freed / 1e6:.1f} MB")

    if failed:
        # Loud. A prune that half worked is a host that keeps growing while the
        # log says it is being looked after.
        for line in failed:
            print(f"::error::could not remove {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
