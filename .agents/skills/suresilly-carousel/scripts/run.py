#!/usr/bin/env python3
"""
run.py — the only way to make a post.

The scheduled job and a person at a laptop run this same script against the same
state. There is deliberately no second path, because a second path is how two
runs end up with two different ideas of what has already been used.

    run.py --publish     build and post          (scheduled, and manual live)
    run.py --no-post     build, do not post      (still uses up the moment)
    run.py --dry-run     look only, write nothing
    run.py --no-post --no-fresh    as above, but do not generate artwork

Poses are GENERATED from each slide's own brief by default. Add --no-fresh to
take them from the library instead, which is worth doing when you are building
to look at copy or layout and would only throw the artwork away.

That default is safe because generation can never fail the deck: no key, dead
network, spent budget, a frame that fails a QA gate — every one of them hands
the slide back the library pose it was already given, and tests/test_fresh_poses
proves each path.

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
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bibliography  # noqa: E402
import compose  # noqa: E402
import critic  # noqa: E402
import discovery  # noqa: E402
import novelty  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import pick_moment  # noqa: E402
import render  # noqa: E402
import safety  # noqa: E402
import screen  # noqa: E402
import writer  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
HALT_FILE = REPO_ROOT / "state" / "HALT"

# How many moments to try before giving up. The harvest returns about five
# usable candidates and it costs nothing to use them all: a refusal here is one
# cheap call, and stopping early throws away the run for no reason.
MAX_ATTEMPTS = 5

CAROUSELS = REPO_ROOT / "carousels"
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


def anchor_words(moment: memory.Moment) -> set[str]:
    """The concrete words the moment is made of.

    `moment.anchors` is {kind: [words]}, so iterating it yields "place" and
    "object" rather than "bed" and "text". The coherence gate treats anything
    outside this set as a scene the deck invented, so handing it the kind names
    told it that every real word in the deck was foreign, and no deck could pass.
    """
    return {str(word).lower() for words in moment.anchors.values() for word in words if word}


def draw() -> dict:
    """Fetch live, screen, drop what we have used, and take the best."""
    result = pick_moment.pick()
    if not result["ok"]:
        if result["route"] == "reserve":
            raise Stop(f"the feed is unreachable and the reserve is empty ({result['note']})")
        raise Stop(f"nothing usable in {result['fetched']} posts fetched")
    return result


def draw_concept() -> dict:
    """Take the best unused concept from the proved vocabulary.

    The other channel. `draw` asks a public feed what somebody did tonight;
    this asks the vocabulary what idea has not been written about yet, and the
    moment is invented from that instead.

    Both channels hand the same thing to the same code below, so nothing
    downstream knows or cares which one produced the deck. The difference is
    only in what each one can answer. A phrase finds what somebody DID; the
    vocabulary knows what it is CALLED, which is the thing a harvested moment
    never arrives with.
    """
    chosen = discovery.pick()
    if not chosen:
        raise Stop("no unused concept in the vocabulary. Run discovery.py "
                   "--refresh to prove more, or use the feed for this run")
    return {"candidates": [chosen], "route": "concept", "fetched": 1,
            "tally": {}, "note": None}


# ─────────────────────────── steps 3 to 9 ────────────────────────────

def invent(candidate: dict) -> tuple[memory.Moment, str]:
    """Read the harvested post as a seed, then invent our own moment.

    The post is never republished, quoted or rewritten. It supplies the subject
    and the shape of the problem, and nothing else survives this step.

    The anchors are recomputed from the invented moment, and that is not a
    detail. They travel on to the writer as the only scene the deck may be set
    in, and they used to be the SEED's anchors while the deck was built on a
    different sentence entirely — the writer was told the scene was a bed and a
    text when the moment said a phone and 11pm. Zero words in common.
    """
    concept = "term" in candidate
    try:
        if concept:
            result = compose.from_concept(candidate["term"], candidate["summary"])
        else:
            result = compose.invent(candidate["text"])
    except llm.ModelRefused as refused:
        raise Skip(str(refused))
    shaped = screen.shape(result["moment"])
    moment = memory.Moment.make(
        text=result["moment"],
        source="concept" if concept else "bluesky",
        # A concept's id is stable, so the moment id derived from it is too, and
        # used_ids() then refuses the same concept a second time on its own.
        # That is a second lock on the door discovery.recent() already closes,
        # and it is the one that survives somebody deleting the history file.
        source_ref=f"concept:{candidate['id']}" if concept else candidate["ref"],
        anchors=shaped["anchors"],
        score=shaped["score"],
    )
    # The subject comes back with the moment. The composer chose it out of a
    # closed list while inventing, which makes it a better answer than asking
    # the judge to work it out afterwards from the finished sentence — and the
    # judge sometimes left the field empty, which stopped runs on moments it had
    # just allowed.
    return moment, result["subject"]


PENDING = REPO_ROOT / "state" / "pending"


def hold_for_review(slug: str, path: Path, score: int, reason: str,
                    objections: list[dict]) -> None:
    """Keep a deck back and tell the owner it is waiting.

    A held deck is finished — written, checked and rendered — and it is not
    posted. It sits here until somebody says publish or says build another. The
    moment is used up either way, the same as any other run that produced a
    deck, so a held deck can never come round again as a duplicate.

    Nothing here decides anything. It writes a record and sends a message.
    """
    PENDING.mkdir(parents=True, exist_ok=True)
    record = {
        "slug": slug,
        "deck": str(path.relative_to(REPO_ROOT)),
        "score": score,
        "reason": reason,
        "notes": [f"{o['category']} slide {o['slide']} (severity {o['severity']}): {o['why']}"
                  for o in objections],
        "held_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (PENDING / f"{slug}.json").write_text(json.dumps(record, indent=2) + "\n",
                                          encoding="utf-8")

    lines = [f"Held for you: {slug}",
             f"Score {score} of 100, and the bar is {critic.PUBLISH_AT}.",
             "", reason[:400], ""]
    if record["notes"]:
        lines += ["What the reviewer said:"] + [f"  {n}" for n in record["notes"][:6]] + [""]
    lines += ["Reply to this message with:",
              f"  publish {slug}    to post it as it is",
              f"  rerun {slug}      to throw it away and build another"]
    sheet = REPO_ROOT / path.parent / "contact_sheet.png"
    # The reason and the reply instructions first, then the same dashboard every
    # other message carries, so one glance answers "what else needs me today".
    # It reads local state only and never fails; if it cannot run, the message
    # still goes with the part that matters.
    board = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "dashboard.py"),
         "--status", "held", "--slug", slug, "--score", str(score)],
        cwd=REPO_ROOT, capture_output=True, text=True)
    body = "\n".join(lines)
    if board.returncode == 0 and board.stdout.strip():
        body += "\n\n" + board.stdout.strip()
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "notify.py"),
         "--subject", f"@suresilly held a deck: {slug} ({score}/100)",
         "--body", body]
        + (["--attach", str(sheet)] if sheet.is_file() else []),
        cwd=REPO_ROOT, capture_output=True, text=True)


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


def write_deck(markdown: str, slug: str) -> Path:
    """Put the deck where the renderer expects it.

    carousels/ is the published corpus: a deck sitting in it is a deck that
    happened, and every novelty check from here on compares against it. So this
    is called once, after every gate has already said yes, and there is no
    second destination to write to speculatively.
    """
    folder = CAROUSELS / slug
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "carousel.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def render_slides(path: Path, fresh: bool = True) -> None:
    """Render the PNGs with the existing builder.

    Called as a subprocess rather than imported: build.py owns argument parsing,
    palette rotation and its own QA gates, and running it the way a person would
    keeps one code path instead of two.

    `fresh` is ON by default, so a scheduled run draws a pose from each slide's
    OWN brief instead of taking the nearest thing the library happens to hold.
    The flag existed and nothing ever passed it, which made the whole path dead
    code: measured over 63 real slides, 50 name a physical object, the library
    knows seven of those words, and a bed appears in 17 briefs while no pose has
    ever had one. On those slides selection was picking the least wrong pose.

    Turning it on does not make the deck depend on the network. Every failure —
    no key, dead network, spent budget, a frame that fails a QA gate, a matte
    that will not cut — hands the slide back the library pose already chosen,
    and tests/test_fresh_poses.py proves each of those paths. What must never
    fail is the DECK, and it still cannot.
    """
    args = [sys.executable, str(Path(__file__).resolve().parent / "build.py"),
            "--random-palette"]
    if fresh:
        args.append("--fresh")
    args.append(str(path))
    done = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True)
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


def run(mode: str, source: str = "feed", fresh: bool = True) -> int:
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{int(time.time())}"
    poses = "generated" if fresh else "library"
    print(f"\nrun {run_id}  mode {mode}  source {source}  poses {poses}\n")

    claimed: memory.Moment | None = None
    try:
        check_halt()
        say("kill switch", "clear")

        if mode == "dry-run":
            say("state check", "skipped, this run writes nothing")
        else:
            say("state check", check_state_is_current(strict=(mode == "publish")))

        result = draw_concept() if source == "concept" else draw()
        candidates = result["candidates"]
        say("moment source", result["route"])
        say("fetched", str(result["fetched"]))
        say("usable", str(len(candidates)))

        best = candidates[0]
        if source == "concept":
            print(f"\n  concept {best['term']}  ({best['demand']}/month, "
                  f"{best['scanned_hits']} scanned books)")
            print(f"  means   {best['summary'][:150]}\n")
        else:
            print(f"\n  moment  {best['text'][:150]}")
            print(f"  anchors {', '.join(best.get('anchors', {}))}  score {best.get('score')}\n")

        if mode == "dry-run":
            say("done", "looked only, nothing written or used")
            return 0

        # One concept means one attempt. The feed hands over eight candidates
        # and the loop below is built to spend up to five of them; a concept run
        # has exactly one and must not report five failures after one.

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
        refusals: list[str] = []
        for attempt, candidate in enumerate(candidates[:MAX_ATTEMPTS], 1):
            try:
                candidate_moment, candidate_topic = invent(candidate)
            except Skip as why:
                say(f"attempt {attempt}", f"could not compose a moment: {str(why)[:70]}")
                refusals.append("compose")
                continue

            # The judge answers one question: may this be published. The subject
            # is already decided, so its own guess at one is not read.
            allowed, why, judge_provider, _ = safety.judge(candidate_moment.text)
            if not allowed:
                # The rewritten text is printed because the refusal is about it
                # and not about the moment shown at the top of the run. Reading
                # five refusals without seeing what was judged is guesswork, and
                # it cost several evenings.
                say(f"attempt {attempt}", f"judge refused ({judge_provider}, "
                                          f"subject {candidate_topic})")
                print(f"      judged: {candidate_moment.text[:104]}")
                print(f"      reason: {str(why)[:104]}")
                refusals.append("judge")
                continue

            moment, reason, topic = candidate_moment, why, candidate_topic
            say("composed", f"on attempt {attempt}, the seed discarded")
            break

        if moment is None:
            tried = min(MAX_ATTEMPTS, len(candidates))
            # Which gate did the refusing matters for what to do next. All five
            # at the rewrite is a firewall or a model problem; all five at the
            # judge is the harvest, or a judge that has gone strict.
            where = ", ".join(f"{refusals.count(k)} at the {k}"
                              for k in ("compose", "judge") if refusals.count(k))
            raise Stop(f"no moment survived {tried} attempts ({where})")

        print(f"\n  moment  {moment.text}\n")
        say("safety judge", f"allowed by {judge_provider}, subject {topic}")
        say("closest risk", str(reason)[:90])

        check_canary()

        memory.claim(moment, run_id)     # nothing expensive runs before this
        claimed = moment
        say("claimed", moment.id)

        markdown, plan, axes, wrote_by = writer.write_deck(
            moment.text, topic, title=moment.text[:40].rstrip(" .,"),
            pattern="Hidden Mechanism", pillar=topic.replace("_", " ").title(),
            moment_anchors=anchor_words(moment) | {plan_token(moment)},
            # The field's name for the idea, on a concept run. It is what makes
            # a concept deck different from a harvested one: without it the
            # concept only picks the subject and is then thrown away.
            term=best["term"] if source == "concept" else "",
        )
        say("written", f"by {wrote_by}, {', '.join(axes.values())}")

        # The critic must not be the vendor that wrote this. Passing the real
        # writer rather than assuming one is what keeps that true when a
        # fallback did the writing.
        outcome, score, reason, objections = critic.review(markdown, moment.text, wrote_by)
        # Three outcomes, not two. The reviewer stops a deck only for harm or a
        # claim the deck invented; a deck that is merely not good enough is
        # HELD, and a person decides what happens to it. That is the whole
        # difference between a gate and a prosecutor.
        if outcome == "block":
            raise Stop(f"the reviewer stopped this deck: {reason}")
        say("review", f"score {score}/100, {len(objections)} note(s), "
                      f"{'ready' if outcome == 'publish' else 'holding for you'}")
        check_critic_canary(memory.used_count(), wrote_by)

        when = time.strftime("%Y%m%d", time.gmtime())
        slug = deck_slug(moment, plan["scene_token"], when)
        path = write_deck(markdown, slug)
        say("deck", str(path.relative_to(REPO_ROOT)))

        render_slides(path, fresh=fresh)
        say("rendered", "slides and contact sheet")

        # Recorded at render, not at publish. A deck that was built and never
        # posted still counts as used, or a manual build could be repeated later.
        slides = render.parse_markdown(path)
        # anchor_words(), not moment.anchors. The anchors are {kind: [words]},
        # so passing the dict passed "place" and "clock" — the same mistake this
        # file already fixed once for the writer, made a second time here. Every
        # deck then filed itself under the same three labels, which quietly cost
        # the gate its ability to reach back past the recent window to an older
        # deck set in the same kitchen.
        fingerprint = novelty.fingerprint(slug, slides, sorted(anchor_words(moment)), slide_text)

        # The novelty gate runs here, after the deck exists and before it is
        # recorded. Unique moments are enforced upstream, so what this catches is
        # the other failure: the writer saying the same thing twice about two
        # different evenings.
        repeats = novelty.check(fingerprint)
        if repeats:
            raise Stop("this deck is too close to one we published: " + "; ".join(repeats[:3]))
        say("novelty", "clear of the last 30 decks and every scene match")

        novelty.record(fingerprint)
        bibliography.remember(slug, plan["citation_id"])
        if source == "concept":
            discovery.remember(slug, best["id"])
        memory.mark_used(moment, slug, mode=mode)
        say("recorded", "fingerprint written, moment retired")

        # The slug is handed to whatever runs next. In CI that is the step that
        # pushes the slides to the public host and only then posts, because
        # Instagram fetches the images itself and cannot see a local file.
        emit_slug(slug, path)

        if outcome == "review":
            hold_for_review(slug, path, score, reason, objections)
            say("held", f"scored {score}, below {critic.PUBLISH_AT}. Sent to you to decide")
            return 0

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
    except critic.NoReview as why:
        # No critic could be reached. Not the same as a deck being refused, and
        # it was reaching the top of the program as a stack trace: in CI, one
        # expired Groq key would have looked like the pipeline crashing.
        print(f"\n  stopped: {why}")
        print("  the deck was written but never reviewed, so it was not posted.")
        return 1
    except llm.ModelRefused as refused:
        # A layer that could not get a usable answer out of any vendor. It is an
        # ordinary no, the same as any other gate saying no, and it was reaching
        # the top of the program as a stack trace that looked like a crash.
        print(f"\n  stopped: {str(refused)[:400]}")
        return 1
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
    # Which channel the idea comes from. The feed is the default because it is
    # what has been running, and switching what an unattended account posts
    # about is a decision somebody makes on purpose rather than a default that
    # changes underneath them.
    ap.add_argument("--source", choices=("feed", "concept"), default="feed",
                    help="feed: a moment harvested from Bluesky (default). "
                         "concept: an idea from the proved vocabulary")
    # Generation is ON. The opt-out exists for a build you are running to look
    # at the copy or the layout, where spending the day's neuron budget on
    # artwork you are about to throw away is waste. It cannot make a deck fail:
    # without it, every slide simply keeps the library pose it was already
    # given.
    ap.add_argument("--no-fresh", action="store_true",
                    help="do not generate poses; use the library for every slide")
    args = ap.parse_args()
    mode = "publish" if args.publish else "no-post" if args.no_post else "dry-run"
    raise SystemExit(run(mode, source=args.source, fresh=not args.no_fresh))


if __name__ == "__main__":
    main()
