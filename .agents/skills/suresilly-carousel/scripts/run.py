#!/usr/bin/env python3
"""
run.py — the only way to make a post.

The scheduled job and a person at a laptop run this same script against the same
state. There is deliberately no second path, because a second path is how two
runs end up with two different ideas of what has already been used.

    run.py --publish     build and post          (scheduled, and manual live)
    run.py --no-post     build, do not post      (still uses up the moment)
    run.py --dry-run     look only, write nothing

Two rules make manual and scheduled runs safe to mix:

  * Any run that produces a deck consumes its moment, posted or not. A build you
    keep on your laptop is still a build, and if it did not retire its moment the
    same evening would come round again weeks later with nobody the wiser.
  * A run whose state is behind the shared copy refuses to start. That is the
    one remaining way a duplicate could escape: a laptop dealing from an old
    list. It is cheaper to skip a post than to explain a repeat.

Nothing here decides anything about content. Every judgement lives in the layer
that owns it, and this script only sequences them and stops on the first no.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import abstracter  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import pick_moment  # noqa: E402
import safety  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
HALT_FILE = REPO_ROOT / "state" / "HALT"

# How many moments to try before giving up on the run. Small on purpose: past
# three, the problem is not the moment.
MAX_ATTEMPTS = 3


class Stop(Exception):
    """A layer said no. The reason is written for whoever reads the alert."""


class Skip(Exception):
    """This moment did not work out. There are thousands more, so the run moves
    on rather than ending the day with nothing."""


class NotWired(Stop):
    """A layer that has not been built yet. Separate from Stop so a run that
    reaches the end of what exists reads as progress, not as a failure."""


def say(step: str, detail: str = "") -> None:
    print(f"  {step:<22} {detail}")


def git(*args: str) -> tuple[int, str]:
    result = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


# ─────────────────────────── step 1 ────────────────────────────

def check_halt() -> None:
    """The kill switch. A file in the repo, or an environment variable set on
    the workflow, so it can be thrown from a phone or from a laptop."""
    if os.environ.get("SS_HALT", "").strip() in ("1", "true", "yes"):
        raise Stop("posting is halted by SS_HALT")
    if HALT_FILE.is_file():
        reason = HALT_FILE.read_text(encoding="utf-8").strip() or "no reason given"
        raise Stop(f"posting is halted by state/HALT: {reason}")


def check_state_is_current(strict: bool) -> str:
    """Refuse to run from a stale or dirty copy of the shared state.

    Only state/ matters. Uncommitted work elsewhere in the repo is somebody's
    business and none of this script's.
    """
    code, dirty = git("status", "--porcelain", "--untracked-files=all", "--", "state")
    if code == 0 and dirty:
        # HALT is excluded on purpose. It is a control file, and it is
        # uncommitted exactly when somebody has just used it.
        # Porcelain v1 is two status characters, a space, then the path. Slice
        # at 2 and strip, so a staged entry (" M", "A ", "??") parses the same.
        changed = [line[2:].strip() for line in dirty.splitlines()
                   if not line[2:].strip().endswith("state/HALT")]
        if changed:
            shown = ", ".join(changed[:4]) + (" ..." if len(changed) > 4 else "")
            raise Stop(
                f"state/ has uncommitted changes ({shown}). Commit them so this run and "
                "the scheduled one share the same memory of what has been used"
            )

    code, _ = git("rev-parse", "--abbrev-ref", "@{u}")
    if code != 0:
        return "no upstream branch, cannot check for staleness"

    code, _ = git("fetch", "--quiet")
    if code != 0:
        if strict:
            raise Stop("could not reach the remote, so staleness cannot be ruled out")
        return "remote unreachable, staleness unchecked"

    code, behind = git("rev-list", "--count", "HEAD..@{u}", "--", "state")
    if code == 0 and behind.isdigit() and int(behind) > 0:
        raise Stop(
            f"state/ is {behind} commit(s) behind the remote. Pull before running, "
            "or this run may reuse a moment another run already took"
        )
    return "current"


# ─────────────────────────── step 2 ────────────────────────────

def draw() -> dict:
    """Fetch live, screen, drop what we have used, and take the best."""
    result = pick_moment.pick()
    if not result["ok"]:
        if result["route"] == "reserve":
            raise Stop(f"the feed is unreachable and the reserve is empty ({result['note']})")
        raise Stop(f"nothing usable in {result['fetched']} posts fetched")
    return result


# ─────────────────────────── steps 3 to 9 ────────────────────────────

def abstract(candidate: dict) -> memory.Moment:
    """Rewrite the moment so nobody's words are republished, then drop the original.

    Load-bearing for more than tidiness: the observable fact is free to use, the
    author's sentence is theirs, and this is the step that separates the two. The
    original is not carried past this point and is never written to disk.
    """
    try:
        result = abstracter.rewrite(candidate["text"])
    except llm.ModelRefused as refused:
        raise Skip(str(refused))
    return memory.Moment.make(
        text=result["moment"],
        source="bluesky",
        source_ref=candidate["ref"],
        anchors=candidate.get("anchors", {}),
        score=candidate.get("score", 0),
    )


def check_canary() -> None:
    """Send one known-bad moment past the judge, every run.

    This is how an unattended system notices that its judge has gone soft. A
    judge that has drifted into agreeing with everything stops failing the
    canary, and the only way anyone would otherwise find out is by reading a
    published post.

    A canary that gets through halts publishing on the spot. That is a heavy
    response to one call, and it is the right one: the alternative is carrying on
    with a gate we have just watched fail.
    """
    index = memory.used_count()
    caught, note = safety.run_canary(index)
    if caught:
        say("canary", note[:88])
        return
    HALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HALT_FILE.write_text(
        f"The safety judge let a known-bad moment through: {note}\n"
        "Publishing is halted. Delete this file once the judge has been checked.\n",
        encoding="utf-8",
    )
    raise Stop(f"{note}. Publishing halted, see state/HALT")


# ─────────────────────────── the run ────────────────────────────

def run(mode: str) -> int:
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{int(time.time())}"
    print(f"\nrun {run_id}  mode {mode}\n")

    claimed: memory.Moment | None = None
    try:
        check_halt()
        say("kill switch", "clear")

        if mode == "dry-run":
            say("state check", "skipped, this run writes nothing")
        else:
            say("state check", check_state_is_current(strict=(mode == "publish")))

        result = draw()
        candidates = result["candidates"]
        say("moment source", result["route"])
        say("fetched", str(result["fetched"]))
        say("usable", str(len(candidates)))

        best = candidates[0]
        print(f"\n  moment  {best['text'][:150]}")
        print(f"  anchors {', '.join(best.get('anchors', {}))}  score {best.get('score')}\n")

        if mode == "dry-run":
            say("done", "looked only, nothing written or used")
            return 0

        # A moment that will not rewrite cleanly is not a failed run. The
        # firewall refuses often and on purpose — a rewrite that keeps eight of
        # the author's words in a row is the thing it exists to stop — and the
        # feed has thousands more. Three refusals in a row is a different story:
        # that is the model or the source having a bad day, and it should show
        # up as an alert rather than as a quietly worse post.
        moment = None
        for attempt, candidate in enumerate(candidates[:MAX_ATTEMPTS], 1):
            try:
                moment = abstract(candidate)
                say("rewritten", f"on attempt {attempt}, original discarded")
                break
            except Skip as reason:
                say(f"attempt {attempt}", f"refused: {reason}")
        if moment is None:
            raise Stop(f"no usable rewrite in {min(MAX_ATTEMPTS, len(candidates))} attempts")

        print(f"\n  moment  {moment.text}\n")

        allowed, reason, judge_provider = safety.judge(moment.text)
        if not allowed:
            raise Stop(f"the safety judge refused this moment: {reason}")
        say("safety judge", f"allowed by {judge_provider}")
        say("closest risk", reason[:90])

        check_canary()

        memory.claim(moment, run_id)     # nothing expensive runs before this
        claimed = moment
        say("claimed", moment.id)
        raise NotWired("the writer, the critic and the renderer are not built yet")

    except NotWired as reason:
        print(f"\n  stopped: {reason}")
        print("  everything before this point ran. Nothing was posted and no moment was used.")
        return 0
    except memory.ClaimHeld as reason:
        print(f"\n  stopped: {reason}")
        return 1
    except Stop as reason:
        print(f"\n  stopped: {reason}")
        return 1
    finally:
        # A run that ends without a deck gives the moment back. A run that
        # produced one has already retired it, and release only ever touches
        # this run's own claim.
        if claimed is not None:
            memory.release_claim(run_id)


def main() -> None:
    ap = argparse.ArgumentParser(description="Make one @suresilly carousel.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--publish", action="store_true", help="build and post")
    group.add_argument("--no-post", action="store_true",
                       help="build but do not post. Still uses up the moment")
    group.add_argument("--dry-run", action="store_true",
                       help="look at what today would use. Writes nothing, uses nothing")
    args = ap.parse_args()
    mode = "publish" if args.publish else "no-post" if args.no_post else "dry-run"
    raise SystemExit(run(mode))


if __name__ == "__main__":
    main()
