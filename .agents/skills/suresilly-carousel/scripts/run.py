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
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import abstracter  # noqa: E402
import critic  # noqa: E402
import novelty  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import pick_moment  # noqa: E402
import render  # noqa: E402
import safety  # noqa: E402
import writer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
HALT_FILE = REPO_ROOT / "state" / "HALT"

# How many moments to try before giving up. The harvest returns about five
# usable candidates and it costs nothing to use them all: a refusal here is one
# cheap call, and stopping early throws away the run for no reason.
MAX_ATTEMPTS = 5

CAROUSELS = REPO_ROOT / "carousels"
PREVIEW = REPO_ROOT / ".preview"
MEDIA_BASE = "https://media.suresilly.com/slides"

# The keys a slide carries, used when a gate needs the slide as plain text.
TEXT_KEYS = ("h1", "h2", "body", "source_claim", "source_translation", "source_explains",
             "old_reaction", "new_reaction", "closing", "cta1", "callout")


def slide_text(slide: dict) -> str:
    return " ".join([str(slide[k]) for k in TEXT_KEYS if k in slide] + slide.get("bullets", []))


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

def plan_token(moment: memory.Moment) -> str:
    """A concrete word from the moment, for the coherence gate's allowed set."""
    for kind in ("clock", "place", "object"):
        values = moment.anchors.get(kind) or []
        if values:
            return str(values[0])
    return ""


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


def check_critic_canary(index: int, written_by: str) -> None:
    """Send one deliberately bad deck past the critic, every run.

    Three outcomes, and only one of them halts. An unreachable critic says
    nothing about whether the critic works, and must never be read as if it did.
    """
    status, note = critic.run_canary(index, written_by)
    if status == "caught":
        say("critic canary", note[:86])
        return
    if status == "inconclusive":
        say("critic canary", note[:86])
        return
    HALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    HALT_FILE.write_text(
        f"The critic approved a known-bad deck: {note}\n"
        "Publishing is halted. Delete this file once the critic has been checked.\n",
        encoding="utf-8")
    raise Stop(f"{note}. Publishing halted, see state/HALT")


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


# ─────────────────────────── steps 10 and 11 ────────────────────────────

def deck_slug(moment: memory.Moment, token: str, when: str) -> str:
    """A folder name that is readable and cannot collide.

    Readable because a person reading an alert should recognise the deck, and
    unique because two decks about a similar evening on the same day would
    otherwise land in the same folder and one would overwrite the other.
    """
    words = re.findall(r"[a-z0-9]+", f"{token} {moment.text}".lower())[:4]
    stub = "-".join(w for w in words if len(w) > 1)[:32].strip("-") or "moment"
    return f"{when}_{stub}_{moment.id[2:8]}"


def write_deck(markdown: str, slug: str, preview: bool) -> Path:
    """Put the deck where the renderer expects it.

    A preview never touches carousels/. That directory is the published corpus,
    and a deck sitting in it is a deck that happened.
    """
    root = PREVIEW if preview else CAROUSELS
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "carousel.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def render_slides(path: Path) -> None:
    """Render the PNGs with the existing builder.

    Called as a subprocess rather than imported: build.py owns argument parsing,
    palette rotation and its own QA gates, and running it the way a person would
    keeps one code path instead of two.
    """
    done = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "build.py"),
         "--random-palette", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        tail = (done.stdout + done.stderr).strip().splitlines()[-4:]
        raise Stop("the renderer refused this deck: " + " | ".join(tail))


def publish(path: Path, slug: str) -> None:
    """Hand the deck to Instagram.

    The slides have to be publicly reachable first, which is the workflow's job,
    so this only runs where that has happened.
    """
    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "post_to_ig.py"),
         "--carousel", str(path), "--base-url", f"{MEDIA_BASE}/{slug}/slides"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        tail = (done.stdout + done.stderr).strip().splitlines()[-4:]
        raise Stop("Instagram refused the post: " + " | ".join(tail))


def emit_slug(slug: str, path: Path) -> None:
    """Tell the caller what was built.

    Printed for a person and written to the workflow's output file for CI, so a
    later step can find the deck without guessing at the folder name.
    """
    print(f"\n  slug: {slug}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"slug={slug}\n")
            handle.write(f"deck={path.relative_to(REPO_ROOT)}\n")


def tag_caption(markdown: str, moment_id: str) -> str:
    """Hide the moment id in the caption as a short tag.

    It is the idempotency key at the sink: after a run dies between posting and
    recording, the next one can ask Instagram whether this moment already went
    out instead of guessing.
    """
    tag = f"#ss{moment_id[2:8]}"
    lines = markdown.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#") and " #" in line:
            lines[i] = f"{line} {tag}"
            return "\n".join(lines)
    return markdown


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
        # One candidate refusing is not a failed run. The rewrite can come back
        # too close to the original, and the judge can rule a moment too thin to
        # build on, and both are the machinery working. The feed handed us five
        # candidates; using one and giving up wasted the other four.
        #
        # The judge sits inside this loop rather than after it because its
        # refusals are about the moment, not the deck. A moment with no feeling
        # in it is the next moment's problem to solve, not this run's.
        moment = topic = judge_provider = reason = None
        for attempt, candidate in enumerate(candidates[:MAX_ATTEMPTS], 1):
            try:
                candidate_moment = abstract(candidate)
            except Skip as why:
                say(f"attempt {attempt}", f"rewrite refused: {str(why)[:70]}")
                continue

            allowed, why, judge_provider, topic = safety.judge(candidate_moment.text)
            if not allowed:
                say(f"attempt {attempt}", f"judge refused: {str(why)[:70]}")
                continue

            moment, reason = candidate_moment, why
            say("rewritten", f"on attempt {attempt}, original discarded")
            break

        if moment is None:
            tried = min(MAX_ATTEMPTS, len(candidates))
            raise Stop(f"no moment survived the rewrite and the judge in {tried} attempts")

        print(f"\n  moment  {moment.text}\n")
        say("safety judge", f"allowed by {judge_provider}, subject {topic}")
        say("closest risk", str(reason)[:90])

        check_canary()

        memory.claim(moment, run_id)     # nothing expensive runs before this
        claimed = moment
        say("claimed", moment.id)

        markdown, plan, axes = writer.write_deck(
            moment.text, topic, title=moment.text[:40].rstrip(" .,"),
            pattern="Hidden Mechanism", pillar=topic.replace("_", " ").title(),
            moment_anchors=set(moment.anchors) | {plan_token(moment)},
        )
        say("written", ", ".join(axes.values()))

        published_ok, reason, objections = critic.review(markdown, moment.text, "gemini")
        if not published_ok:
            raise Stop(f"the critic refused this deck: {reason}")
        say("critic", f"{len(objections)} objection(s), none disqualifying")
        check_critic_canary(memory.used_count(), "gemini")

        when = time.strftime("%Y%m%d", time.gmtime())
        slug = deck_slug(moment, plan["scene_token"], when)
        markdown = tag_caption(markdown, moment.id)
        path = write_deck(markdown, slug, preview=False)
        say("deck", str(path.relative_to(REPO_ROOT)))

        render_slides(path)
        say("rendered", "slides and contact sheet")

        # Recorded at render, not at publish. A deck that was built and never
        # posted still counts as used, or a manual build could be repeated later.
        slides = render.parse_markdown(path)
        fingerprint = novelty.fingerprint(slug, slides, sorted(moment.anchors), slide_text)

        # The novelty gate runs here, after the deck exists and before it is
        # recorded. Unique moments are enforced upstream, so what this catches is
        # the other failure: the writer saying the same thing twice about two
        # different evenings.
        repeats = novelty.check(fingerprint)
        if repeats:
            raise Stop("this deck is too close to one we published: " + "; ".join(repeats[:3]))
        say("novelty", "clear of the last 30 decks and every scene match")

        novelty.record(fingerprint)
        memory.mark_used(moment, slug, published=(mode == "publish"))
        say("recorded", "fingerprint written, moment retired")

        # The slug is handed to whatever runs next. In CI that is the step that
        # pushes the slides to the public host and only then posts, because
        # Instagram fetches the images itself and cannot see a local file.
        emit_slug(slug, path)

        if mode == "publish":
            publish(path, slug)
            say("posted", slug)
        else:
            say("not posted", "built only, and the moment is used up either way")
        return 0

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
