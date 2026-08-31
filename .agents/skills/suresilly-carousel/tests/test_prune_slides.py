#!/usr/bin/env python3
"""
Retention regression for the public slide host.

prune_slides.py deletes folders off gh-pages. Every other gate in this repo
refuses to publish something; this one is the only one that removes something
that is already live, so the cases worth locking are the refusals, not the
deletions.

Two failures it must never have. It must not delete a deck that a person can
still ask us to publish — the one this run just put up, or one of the newest few
when posting has paused. And it must not report a calm "nothing to do" when the
truth is that it could not tell: a missing host, an empty host, or a naming
scheme it does not recognise are all non-zero exits, because a prune that
silently does nothing looks exactly like a prune that worked right up until the
day the site hits its limit.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "scripts"))
import prune_slides as prune  # noqa: E402


def host(root: pathlib.Path, *names: str) -> pathlib.Path:
    """A pretend gh-pages `slides/` directory with one folder per deck."""
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        slides = root / name / "slides"
        slides.mkdir(parents=True)
        (slides / "01_slide_1_hook.png").write_bytes(b"\x89PNG" + b"0" * 64)
    return root


def planned(root: pathlib.Path, today: str, days: int = 14, keep_min: int = 8,
            protect: set[str] | None = None,
            held: set[str] | None = None) -> set[str]:
    removed, _ = prune.plan(root, prune.read_date(today + "_"), days, keep_min,
                            protect or set(), held or set())
    return {p.name for p in removed}


def spoken(root: pathlib.Path, today: str = "20260901", **kw) -> str:
    _, lines = prune.plan(root, prune.read_date(today + "_"), kw.get("days", 14),
                          kw.get("keep_min", 0), kw.get("protect", set()),
                          kw.get("held", set()))
    return "\n".join(lines)


def refuses(root: pathlib.Path, today: str = "20260901", **kw) -> bool:
    try:
        prune.plan(root, prune.read_date(today + "_"), kw.get("days", 14),
                   kw.get("keep_min", 0), kw.get("protect", set()),
                   kw.get("held", set()))
    except prune.Abort:
        return True
    return False


def run() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # ── the window ──
        root = host(base / "a",
                    "20260801_old-one_aaaaaa", "20260810_old-two_bbbbbb",
                    "20260825_recent_cccccc", "20260901_today_dddddd")
        got = planned(root, "20260901", days=14, keep_min=0)
        if got != {"20260801_old-one_aaaaaa", "20260810_old-two_bbbbbb"}:
            failures.append(f"the 14 day window removed the wrong set: {sorted(got)}")

        # A deck built exactly at the edge of the window is inside it. Fourteen
        # days means fourteen, and off-by-one here is a live URL going dark.
        edge = host(base / "edge", "20260818_edge_eeeeee")
        if planned(edge, "20260901", days=14, keep_min=0):
            failures.append("a deck exactly 14 days old was removed")

        # ── the deck this run just published ──
        #
        # Dated old on purpose: a protected slug outranks the window, because
        # Instagram may not have fetched it yet.
        root = host(base / "b", "20260101_stale-but-live_ffffff",
                    "20260102_stale_gggggg")
        got = planned(root, "20260901", days=14, keep_min=0,
                      protect={"20260101_stale-but-live_ffffff"})
        if "20260101_stale-but-live_ffffff" in got:
            failures.append("the protected deck was scheduled for removal")
        if got != {"20260102_stale_gggggg"}:
            failures.append(f"protection spread past the named slug: {sorted(got)}")

        # ── the floor under the window ──
        #
        # Posting stops for a month, every folder ages out, and a held deck is
        # still waiting on a reply. The newest few survive anyway.
        names = [f"202601{day:02d}_paused_{day:06d}" for day in range(1, 13)]
        root = host(base / "c", *names)
        got = planned(root, "20260901", days=14, keep_min=8)
        if len(got) != 4 or set(names[-8:]) & got:
            failures.append(f"the keep-min floor did not hold: removed {len(got)}")

        # ── a folder we cannot read is a folder we cannot delete ──
        root = host(base / "d", "20260101_old_aaaaaa", "assets", "not-a-deck")
        got = planned(root, "20260901", days=14, keep_min=0)
        if got != {"20260101_old_aaaaaa"}:
            failures.append(f"an unparseable folder was touched: {sorted(got)}")

        # ── the refusals ──
        if not refuses(base / "does-not-exist"):
            failures.append("a missing host did not abort")

        empty = base / "empty"
        empty.mkdir()
        if not refuses(empty):
            failures.append("an empty host did not abort — it means the publish never landed")

        root = host(base / "e", "20260825_here_aaaaaa")
        if not refuses(root, protect={"20260825_somewhere-else_bbbbbb"}):
            failures.append("a protected deck missing from the host did not abort")

        root = host(base / "f", "assets", "css")
        if not refuses(root):
            failures.append("a host where no folder is date-named did not abort")

        # ── dry run deletes nothing ──
        root = host(base / "g", "20260101_old_aaaaaa", "20260901_new_bbbbbb")
        argv = sys.argv[:]
        sys.argv = ["prune_slides.py", "--root", str(root), "--today", "20260901",
                    "--keep-min", "0", "--dry-run"]
        try:
            code = prune.main()
        finally:
            sys.argv = argv
        if code != 0:
            failures.append(f"a clean dry run exited {code}")
        if not (root / "20260101_old_aaaaaa").is_dir():
            failures.append("--dry-run deleted a folder")

        # ── and a real run does delete, and only what it said ──
        sys.argv = ["prune_slides.py", "--root", str(root), "--today", "20260901",
                    "--keep-min", "0"]
        try:
            code = prune.main()
        finally:
            sys.argv = argv
        if code != 0:
            failures.append(f"a clean run exited {code}")
        if (root / "20260101_old_aaaaaa").is_dir():
            failures.append("the old folder survived a real run")
        if not (root / "20260901_new_bbbbbb" / "slides" / "01_slide_1_hook.png").is_file():
            failures.append("a slide inside the kept deck was lost")

        # ── an unreadable host exits non-zero from main(), not just plan() ──
        sys.argv = ["prune_slides.py", "--root", str(base / "does-not-exist")]
        try:
            code = prune.main()
        finally:
            sys.argv = argv
        if code == 0:
            failures.append("main() reported success on a missing host")

        # ── decks held for review outlive the window ──
        # A deck in state/pending is posted by release.py from this host days
        # after it was built. Prune it and the owner's "publish" reply fetches
        # nine 404s, and the deck can never go out.
        held = host(base / "held", "20260101_held_aaaaaa",
                    "20260101_plain_bbbbbb", "20260830_new_cccccc")
        if planned(held, "20260901", keep_min=0,
                   held={"20260101_held_aaaaaa"}) != {"20260101_plain_bbbbbb"}:
            failures.append("a deck awaiting review was pruned on the window")
        if planned(held, "20260901", keep_min=0) != {
                "20260101_held_aaaaaa", "20260101_plain_bbbbbb"}:
            failures.append("an unheld deck of the same age was spared")

        # An already-pruned held slug must NOT abort. Aborting would wedge every
        # future run on one mistake and the host would fill up behind it.
        gone = host(base / "gone", "20260830_new_cccccc")
        if refuses(gone, held={"20260101_vanished_ffffff"}):
            failures.append("a held deck already off the host aborted the prune")
        if "vanished" not in spoken(gone, held={"20260101_vanished_ffffff"}):
            failures.append("a held deck that vanished was not named in the log")

        # The deck this run published keeps its hard check.
        if not refuses(gone, protect={"20260830_notthere_dddddd"}):
            failures.append("a missing --protect deck no longer aborts")

    total = 17
    if failures:
        print(f"prune_slides: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"prune_slides: {total}/{total} passed "
          f"(window, edge day, protected deck, keep-min floor, unreadable names, "
          f"missing host, empty host, absent protected slug, unknown layout, dry run, held decks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
