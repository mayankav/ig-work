#!/usr/bin/env python3
"""
Used-memory and claim regression.

The used list is the only thing standing between us and re-telling the same
evening every few weeks, so the cases here are about the ways a moment could
sneak back in: the same post fetched twice, a repost from another account, a
spare that went stale in the reserve, and a run that died holding a claim.

Every case runs against a temporary state directory. Nothing here touches the
real one.
"""
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import memory  # noqa: E402


def fresh_state(tmp: pathlib.Path) -> None:
    """Point the module at a throwaway directory."""
    memory.STATE_DIR = tmp
    memory.USED_PATH = tmp / "used.jsonl"
    memory.RESERVE_PATH = tmp / "reserve.json"
    memory.CLAIM_PATH = tmp / "claim.json"


def make(text: str, ref: str) -> memory.Moment:
    return memory.Moment.make(text, source="test", source_ref=ref, anchors={}, score=5)


def run() -> int:
    failures = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        fresh_state(tmp)

        wake = make("I woke at 2:17am with my heart pounding.", "at://post/one")

        # A moment nobody has used is not used.
        if memory.is_used(wake.id):
            failures.append("a fresh moment reported as used")

        memory.mark_used(wake, deck_slug="20260830_test", mode="no-post")

        # Built but never posted still counts. This is the rule that stops a
        # manual build being repeated later.
        if not memory.is_used(wake.id):
            failures.append("a built-but-unposted moment was not retired")

        # The same source post fetched again is the same moment.
        again = make("I woke at 2:17am with my heart pounding.", "at://post/one")
        if again.id != wake.id:
            failures.append("the same source post produced two different ids")

        # A repost from a different account is caught by the wording hash.
        repost = make("I woke at 2:17am with my heart pounding!", "at://post/other")
        if repost.id in memory.used_ids():
            failures.append("a repost matched on id, which it should not")
        if repost.raw_hash not in memory.used_raw_hashes():
            failures.append("a repost of a used moment was not recognised")

        # A genuinely different moment is untouched by either check.
        other = make("I stood in the kitchen at 11pm holding the fridge open.", "at://post/two")
        if other.id in memory.used_ids() or other.raw_hash in memory.used_raw_hashes():
            failures.append("a different moment was treated as used")

        # ── reserve ──
        memory.save_reserve([wake, other])
        spare = memory.take_from_reserve()
        if spare is None or spare.id != other.id:
            failures.append("the reserve handed back a moment that was already used")
        if memory.take_from_reserve() is not None:
            failures.append("the reserve did not empty")

        # ── claim ──
        memory.CLAIM_PATH.unlink(missing_ok=True)
        memory.claim(other, run_id="run-a")
        try:
            memory.claim(other, run_id="run-b")
            failures.append("a second run took a moment that was already claimed")
        except memory.ClaimHeld:
            pass

        # A run only releases its own claim.
        if memory.release_claim("run-b"):
            failures.append("a run released someone else's claim")
        if not memory.release_claim("run-a"):
            failures.append("a run could not release its own claim")

        # An expired claim is not a blocker. A crashed run must not wedge the
        # next scheduled one.
        memory.claim(other, run_id="run-c")
        held = memory.read_claim()
        held["expires_at"] = time.time() - 1
        memory.CLAIM_PATH.write_text(__import__("json").dumps(held))
        try:
            memory.claim(other, run_id="run-d")
        except memory.ClaimHeld:
            failures.append("an expired claim still blocked a later run")

    if failures:
        print(f"memory: {len(failures)} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print("memory: 12/12 passed (used list, reposts, reserve, claims)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
