#!/usr/bin/env python3
"""
Held-deck regression. No network is touched.

A deck the reviewer scored below the bar is not thrown away and not posted. It
waits for the owner of the page to say which. This is the only decision a person
is asked to make in the whole pipeline, and there are two ways to make it — a
reply in Telegram and a button in GitHub Actions — that both call one script,
because two code paths that post to Instagram is how you end up with two
different ideas of what has already gone out.

The thing worth testing here is the matching. The slugs are long and end in six
hex characters, and nobody types "20260830_door-walked-to_79262b" correctly from
a phone at nine at night. A short id has to work, and it has to refuse rather
than guess when it matches more than one.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import release  # noqa: E402


def hold(tmp: pathlib.Path, slug: str, score: int = 74) -> None:
    (tmp / f"{slug}.json").write_text(json.dumps({
        "slug": slug, "deck": f"carousels/{slug}/carousel.md", "score": score,
        "reason": "thin", "notes": [], "held_at": "2026-08-30T20:00:00Z"}), encoding="utf-8")


def run() -> int:
    import tempfile
    failures = []
    real = release.PENDING
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="held-"))
    release.PENDING = tmp
    try:
        if release.held():
            failures.append("EMPTY an empty store reported something held")
        if release.find("anything") is not None:
            failures.append("EMPTY matched a deck in an empty store")

        hold(tmp, "20260830_door-walked-to_79262b")
        hold(tmp, "20260829_kettle-again_aa1234", score=68)

        if len(release.held()) != 2:
            failures.append(f"LIST expected two held, got {len(release.held())}")
        # Oldest first, because the one that has waited longest is the one a
        # person most needs to see.
        if release.held()[0]["slug"] != "20260829_kettle-again_aa1234":
            failures.append("LIST held decks were not oldest first")

        if (release.find("20260830_door-walked-to_79262b") or {}).get("score") != 74:
            failures.append("MATCH the full slug did not match")
        if (release.find("79262b") or {}).get("score") != 74:
            failures.append("MATCH the short id did not match")
        if (release.find("kettle") or {}).get("score") != 68:
            failures.append("MATCH a word from the middle did not match")
        if release.find("2026") is not None:
            failures.append("MATCH an id matching two decks was guessed at rather than refused")
        if release.find("nothing-like-this") is not None:
            failures.append("MATCH an id matching nothing returned something")

        # Dropping stops the holding and nothing else. The deck and its slides
        # stay on disk: they are the record of what was built, and the moment
        # behind them was retired when it was built, so keeping them cannot
        # cause a repeat.
        release.drop(release.find("79262b"))
        if release.find("79262b") is not None:
            failures.append("DROP a dropped deck is still held")
        if len(release.held()) != 1:
            failures.append("DROP dropping one removed more than one")

        # A store with something unreadable in it still works. A run that dies
        # halfway through writing a record must not take the whole review queue
        # down with it.
        (tmp / "broken.json").write_text("{not json", encoding="utf-8")
        if len(release.held()) != 1:
            failures.append("BROKEN one unreadable record hid the readable ones")
    finally:
        release.PENDING = real

    total = 12
    if failures:
        print(f"release: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"release: {total}/{total} passed (empty store, oldest first, full slug, short id, "
          f"ambiguous refused, drop, unreadable record survived)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
