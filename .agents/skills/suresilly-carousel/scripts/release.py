#!/usr/bin/env python3
"""
release.py — what happens to a deck the reviewer held back.

A held deck is finished. It was written, checked, rendered, and it scored below
the bar, so instead of being thrown away it waits for somebody to say what
happens to it. That somebody is the owner of the page, and this is the only
thing in the pipeline they are asked to decide.

    release.py --list                 what is waiting
    release.py --publish <slug>       post it as it is
    release.py --drop <slug>          throw it away

Both decisions are final and neither can be reversed here. A dropped deck is
gone: its moment was already retired when it was built, exactly as if it had
posted, so nothing can come round twice.

Two ways in, one script. A reply in Telegram and a button in GitHub Actions both
land here, because two code paths that post to Instagram is how you get two
different ideas of what has already gone out.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
PENDING = REPO_ROOT / "state" / "pending"
MEDIA_BASE = "https://media.suresilly.com/slides"


def held() -> list[dict]:
    """Every deck waiting on a decision, oldest first."""
    if not PENDING.is_dir():
        return []
    out = []
    for path in sorted(PENDING.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(out, key=lambda r: r.get("held_at", ""))


def find(slug: str) -> dict | None:
    """Match a slug, or the short id a person is likely to type.

    The slugs are long and end in six hex characters. Nobody types
    "20260830_door-walked-to_79262b" correctly from a phone, so the last part on
    its own is enough as long as it matches exactly one held deck.
    """
    records = held()
    exact = [r for r in records if r["slug"] == slug]
    if exact:
        return exact[0]
    partial = [r for r in records if slug and slug in r["slug"]]
    return partial[0] if len(partial) == 1 else None


def publish(record: dict) -> int:
    """Post a held deck, then stop holding it."""
    deck = REPO_ROOT / record["deck"]
    if not deck.is_file():
        print(f"the deck is gone from disk: {record['deck']}", file=sys.stderr)
        return 1
    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "post_to_ig.py"),
         "--carousel", str(deck),
         "--base-url", f"{MEDIA_BASE}/{record['slug']}/slides"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        tail = (done.stdout + done.stderr).strip().splitlines()[-4:]
        print("Instagram refused the post: " + " | ".join(tail), file=sys.stderr)
        return 1
    (PENDING / f"{record['slug']}.json").unlink(missing_ok=True)
    print(f"posted {record['slug']} (held at {record['score']}/100)")
    return 0


def drop(record: dict) -> int:
    """Throw a held deck away.

    The markdown and the slides stay on disk. They are a record of what was
    built, they cost nothing to keep, and the moment behind them is retired
    either way — so leaving them cannot cause a repeat, and deleting them would
    only lose the evidence of why something was refused.
    """
    (PENDING / f"{record['slug']}.json").unlink(missing_ok=True)
    print(f"dropped {record['slug']} (held at {record['score']}/100). "
          f"The next scheduled run builds a fresh deck.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Decide what happens to a held deck.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="what is waiting")
    group.add_argument("--publish", metavar="SLUG", help="post it as it is")
    group.add_argument("--drop", metavar="SLUG", help="throw it away")
    args = ap.parse_args()

    if args.list:
        records = held()
        if not records:
            print("nothing held")
            return 0
        for record in records:
            print(f"{record['slug']}  {record['score']}/100  held {record.get('held_at', '?')}")
            for note in record.get("notes", [])[:4]:
                print(f"    {note}")
        return 0

    slug = args.publish or args.drop
    record = find(slug)
    if record is None:
        print(f"nothing held matching {slug!r}. Try --list", file=sys.stderr)
        return 1
    return publish(record) if args.publish else drop(record)


if __name__ == "__main__":
    raise SystemExit(main())
