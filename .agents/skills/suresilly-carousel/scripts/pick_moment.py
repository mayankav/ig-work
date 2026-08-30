#!/usr/bin/env python3
"""
pick_moment.py — fetch live, screen, drop anything already used, rank.

This is the whole of "where does today's post come from", and it holds no stock.
Every run reaches out to the live feed and takes something written recently.

Why there is no queue of moments waiting to be used: an earlier design kept one,
because the topic bank held 24 fixed rows that had to be rationed. The live feed
returns thousands of usable moments a day against a need of two, so there is
nothing to ration. A stockpile would only add a second place for staleness to
hide, and a second thing to keep in sync between a scheduled run and a manual
one.

What we DO keep is the opposite list: every moment already used, forever. Public
feeds repeat themselves constantly, so without that memory we would re-tell the
same evening every few weeks.

The reserve is not a stockpile either. It is three spares for the single case
where the feed is unreachable at post time. It is topped up from moments this
run already fetched, so it costs nothing.

This module does not persist anything. Candidates still carry the author's own
words at this point, and those are never written to disk. Storing happens in the
run script, after the abstraction step has replaced them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import memory  # noqa: E402
import screen  # noqa: E402
import sources  # noqa: E402


def screen_all(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Run layers 1 and 2 over everything the feed returned.

    Returns the survivors, best first, plus a tally of why the rest went. The
    tally is the health signal for an unattended system: if the reject mix
    shifts, either the feed changed or a filter broke.
    """
    used = memory.used_ids()
    used_raw = memory.used_raw_hashes()
    kept: list[dict] = []
    tally: dict[str, int] = {}

    for item in candidates:
        if memory.moment_id(item["ref"]) in used:
            tally["already used"] = tally.get("already used", 0) + 1
            continue
        if memory.raw_hash(item["text"]) in used_raw:
            tally["repost of a used moment"] = tally.get("repost of a used moment", 0) + 1
            continue
        verdict = screen.screen(item["text"], item.get("query", ""))
        if not verdict["ok"]:
            key = verdict["reason"] if verdict["stage"] == "banned" else "shape"
            tally[key] = tally.get(key, 0) + 1
            continue
        # The extracted moment replaces the full post from here on. It is still
        # the author's wording, and the abstraction step replaces it before
        # anything reaches disk or a slide.
        kept.append({**item, "text": verdict["text"], "raw": item["text"],
                     "score": verdict["score"], "anchors": verdict["anchors"]})

    kept.sort(key=lambda c: c["score"], reverse=True)
    return kept, tally


def pick(per_query: int = 25, want: int = 5) -> dict:
    """Return the best candidates, or fall back to the reserve.

    Never raises on an empty feed — the caller needs to distinguish "nothing
    usable today" from "the feed is down", and both end the run the same way but
    read very differently in an alert.
    """
    try:
        harvested = sources.harvest(per_query=per_query)
        raw = harvested["items"]
    except sources.SourceUnavailable as exc:
        spare = memory.take_from_reserve()
        return {
            "ok": spare is not None,
            "route": "reserve",
            "note": str(exc),
            "candidates": [spare.__dict__] if spare else [],
            "tally": {},
            "fetched": 0,
        }

    kept, tally = screen_all(raw)
    failed = harvested["failed"]
    return {
        "ok": bool(kept),
        "route": "live",
        "note": f"{len(failed)}/{harvested['attempted']} phrases failed" if failed else None,
        "candidates": kept[:want],
        "tally": tally,
        "fetched": len(raw),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--per-query", type=int, default=25, help="posts to pull per search phrase")
    ap.add_argument("--want", type=int, default=5, help="how many survivors to return")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    result = pick(per_query=args.per_query, want=args.want)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        raise SystemExit(0 if result["ok"] else 1)

    print(f"route     {result['route']}")
    print(f"fetched   {result['fetched']}")
    if result["note"]:
        print(f"note      {result['note']}")
    if result["tally"]:
        print("dropped")
        for reason, count in sorted(result["tally"].items(), key=lambda kv: -kv[1]):
            print(f"  {str(count).rjust(4)}  {reason}")
    print(f"kept      {len(result['candidates'])}")
    for cand in result["candidates"]:
        anchors = ",".join(cand.get("anchors", {}))
        print(f"\n  score {cand['score']}  [{anchors}]")
        print(f"  {cand['text'][:150]}")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
