"""The command line the workflows call.

  python -m suresilly.run build [--slot 2026-09-11_0800] [--format list] [--new]
  python -m suresilly.run stage --post posts/<slug>
  python -m suresilly.run register --post posts/<slug> [--manual]
  python -m suresilly.run describe | act --post posts/<slug> | finish-redo | fail
  python -m suresilly.run list | legacy --decision publish --slug abc
  python -m suresilly.run notify-failure --what "The 08:00 post" [--kind post|reply|message|numbers]
  python -m suresilly.run prune --root gh-pages/slides --days 14
  python -m suresilly.run tokens
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import POSTS, ROOT, STATE, instagram, mascot, review, telegram, threads, tokens
from .write import write_post

HOST = ROOT / ".review-host"


# ── small helpers ──────────────────────────────────────────────────────────

def output(**values) -> None:
    """Hand values to the next workflow step (and echo them for local runs)."""
    path = os.environ.get("GITHUB_OUTPUT")
    for key, value in values.items():
        value = " ".join(str(value).split())
        print(f"{key}={value}")
        if path:
            with open(path, "a") as stream:
                stream.write(f"{key}={value}\n")


def halted() -> bool:
    return os.environ.get("SS_HALT") == "1" or (STATE / "HALT").exists()


def format_for(slot: str) -> str:
    """Mornings alternate list and story; evenings are one-liners."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{2})00", slot or "")
    if not match:
        return "list"
    if match.group(2) == "20":
        return "oneliner"
    return "list" if date.fromisoformat(match.group(1)).toordinal() % 2 == 0 else "story"


def slugify(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower().replace("[[", "").replace("]]", ""))
    return "-".join(words[:6])[:48].strip("-") or "post"


def load(post_dir: Path) -> dict:
    return json.loads((post_dir / "post.json").read_text())


def slot_taken(slot: str) -> bool:
    return any(json.loads(p.read_text()).get("slot") == slot for p in POSTS.glob("*/post.json"))


# ── making a post ──────────────────────────────────────────────────────────

def draw(post: dict, post_dir: Path) -> None:
    from . import reel
    from .render import contact_sheet, render
    slides = render(post, post_dir / "slides")
    contact_sheet(slides, post_dir / "contact_sheet.png")
    if post["format"] == "oneliner":  # evenings go out as a Reel; the tune follows the folder, so a redraw keeps it
        reel.make(post, post_dir)
    (post_dir / "post.json").write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    (post_dir / "caption.txt").write_text(post["caption"] + "\n")


def build(fmt: str | None, slot: str, new: bool = False) -> Path | None:
    if halted():
        print("Posting is switched off (SS_HALT or state/HALT). Nothing was made.")
        output(halted="true")
        return None
    if slot and not new and slot_taken(slot):
        print(f"A post for {slot} already exists. Nothing new was made.")
        output(skipped="true")
        return None
    now = datetime.now(timezone.utc)
    fmt = fmt or format_for(slot)
    seed = f"{slot or now.isoformat()}-{os.urandom(4).hex()}"
    post = write_post(fmt, seed)
    for slide, pose in zip(post["slides"], mascot.choose(post["slides"], seed)):
        slide["pose"] = pose  # the writer's pick when it named a real pose, else one for the mood
    post.update(slot=slot or "", created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    post_dir = POSTS / f"{now:%Y%m%d_%H%M}_{slugify(post['slides'][0]['text'])}"
    post_dir.mkdir(parents=True, exist_ok=False)
    post["slug"] = post_dir.name
    draw(post, post_dir)
    print(f"Made {post_dir.relative_to(ROOT)}: {len(post['slides'])} slide(s), {fmt}.")
    output(slug=post_dir.name)
    return post_dir


def redraw(post_dir: Path, numbers: list[int]) -> None:
    """New donkey poses on the named slides; the words stay exactly as they were."""
    post = load(post_dir)
    count = len(post["slides"])
    numbers = sorted({n for n in numbers if 1 <= n <= count})
    if not numbers:
        raise ValueError(f"This post has {count} slide(s); there is nothing to redo at those numbers.")
    current = {slide["pose"] for slide in post["slides"]}
    fresh = mascot.pick([post["slides"][n - 1]["mood"] for n in numbers], os.urandom(4).hex(), avoid=current)
    for number, pose in zip(numbers, fresh):
        post["slides"][number - 1]["pose"] = pose
    draw(post, post_dir)


# ── the review window ──────────────────────────────────────────────────────

def stage(post_dir: Path, parent: str | None = None) -> dict:
    record = review.prepare(post_dir, parent=parent)
    folder = HOST / record["slug"] / "reviews" / record["token"]
    (folder / "slides").mkdir(parents=True, exist_ok=True)
    for path in (post_dir / "slides").glob("*.jpg"):
        shutil.copy2(path, folder / "slides" / path.name)
    shutil.copy2(post_dir / "contact_sheet.png", folder / "contact_sheet.png")
    if "reel.mp4" in record["files"]:
        shutil.copy2(post_dir / "reel.mp4", folder / "reel.mp4")
    output(slug=record["slug"], review_token=record["token"], host_dir=folder)
    return record


def wait_for_hosting(record: dict, tries: int = 18) -> None:
    import requests
    wanted = {name: digest for name, digest in record["files"].items()
              if name in ("contact_sheet.png", "reel.mp4") or name.startswith("slides/")}
    for attempt in range(tries):
        try:
            for name, digest in wanted.items():
                response = requests.get(f"{review.base_url(record)}/{name}", timeout=20)
                if response.status_code != 200 or hashlib.sha256(response.content).hexdigest() != digest:
                    raise ValueError(f"{name} is not live yet")
            return
        except (requests.RequestException, ValueError):
            if attempt == tries - 1:
                raise ValueError("The preview files never went live on media.suresilly.com.")
            time.sleep(10)


def register(post_dir: Path, manual: bool = False) -> None:
    record = review.read(post_dir)
    wait_for_hosting(record)
    post = load(post_dir)
    base = {"token": record["token"], "slug": record["slug"], "manifest": record["manifest"],
            "run_id": os.environ.get("GITHUB_RUN_ID", "0"), "issue_pages": [], "manual_required": manual,
            "sheet_url": f"{review.base_url(record)}/contact_sheet.png"}
    try:
        receipt = review.api(record["token"], "register", {
            **base, "photos": review.slide_urls(record), "html": True, "resources": "",
            "caption": telegram.review_card(post, record["token"], manual=manual, redo_of=record.get("parent"))})
    except ValueError as exc:
        if "Invalid preview" not in str(exc):
            raise
        # A Worker that predates album previews: contact sheet, plain card, details.
        print("The Worker has no album previews yet; sending the plain version.")
        receipt = review.api(record["token"], "register", {
            **base, "resources": telegram.plain_details(post),
            "caption": telegram.plain_card(post, record["token"], manual=manual, redo_of=record.get("parent"))})
    if receipt.get("state") != "waiting" or not receipt.get("message_id"):
        raise ValueError("Telegram did not confirm the preview.")
    (post_dir / "review_delivery.json").write_text(json.dumps(receipt, indent=2) + "\n")
    review.save_history(ROOT, record["token"])
    output(delivered="true")


def describe(token: str, action_id: str) -> None:
    record = review.api(token, "status")
    if (record.get("action", {}).get("id") != action_id or record.get("claimed")
            or record.get("state") not in ("queued", "cancelled", "published")):
        output(accepted="false")
        return
    output(accepted="true", slug=record["slug"], run_id=record["run_id"], decision=record["action"]["decision"])


def act(post_dir: Path, token: str, action_id: str) -> None:
    prior = review.api(token, "status")
    if prior.get("state") == "published" and prior.get("action", {}).get("id") == action_id:
        output(result="published")
        return
    local = review.read(post_dir)
    if local["token"] != token:
        raise ValueError("The restored post belongs to a different preview.")
    record = review.api(token, "claim", {"action_id": action_id, "manifest": local["manifest"]})
    decision = record["action"]["decision"]
    post = load(post_dir)
    try:
        if decision == "publish":
            caption = (post_dir / "caption.txt").read_text().strip()
            if review.reel_url(local):
                media_id = instagram.publish_reel(post_dir, review.reel_url(local), caption)
            else:
                alts = [instagram.alt_text(slide.get("text", "")) for slide in post["slides"]]
                media_id = instagram.publish(post_dir, review.slide_urls(local), caption, alts)
            review.api(token, "complete", {"action_id": action_id, "state": "published", "media_id": media_id})
            telegram.send(telegram.posted(post, instagram.permalink(media_id), threads=echo(post_dir, post, local)))
            output(result="published")
        elif decision == "drop":
            review.api(token, "complete", {"action_id": action_id, "state": "cancelled"})
            telegram.send(telegram.dropped(post))
            telegram.send(*telegram.why_card(post, token))
            output(result="cancelled")
        elif decision == "redo_slide":
            redraw(post_dir, record["action"].get("slides") or [record["action"]["slide"]])
            stage(post_dir, parent=token)
            note_why(token, "donkey")  # a redo of the pictures is itself the answer
            output(result="replacement_ready")
        elif decision == "redo":
            replacement = build(post["format"], post.get("slot", ""), new=True)
            if replacement is None:
                raise ValueError("Posting is switched off, so no redo was made.")
            stage(replacement, parent=token)
            telegram.send(*telegram.why_card(post, token))
            output(result="replacement_ready")
        else:
            raise ValueError(f"Unknown decision {decision!r}.")
    except Exception:
        if review.api(token, "status").get("state") == "working":
            review.api(token, "complete", {"action_id": action_id, "state": "held"})
        raise
    finally:
        review.save_history(ROOT, token)


def echo(post_dir: Path, post: dict, record: dict) -> dict | None:
    """Put a one-liner on Threads after Instagram has it. Never raises; the result goes in published.json."""
    if post["format"] != "oneliner" or not all(threads.credentials()):
        return None
    receipt = post_dir / "published.json"
    published = json.loads(receipt.read_text())
    if "threads" not in published:  # a rerun must not post it twice
        try:
            media, link = threads.publish(post, review.slide_urls(record)[0])
            published["threads"] = {"id": media, "link": link}
        except Exception as error:  # Instagram is already live; this is only the echo
            published["threads"] = {"error": str(error)[:300]}
        receipt.write_text(json.dumps(published, indent=2) + "\n")
    return published["threads"]


def finish(token: str, action_id: str, failed: bool) -> None:
    record = review.api(token, "status")
    if record.get("state") == "working" and record.get("action", {}).get("id") == action_id:
        review.api(token, "complete", {"action_id": action_id, "state": "held" if failed else "replaced"})
    review.save_history(ROOT, token)


# ── owner messages ─────────────────────────────────────────────────────────

STATE_LABEL = {"waiting": "waiting for you", "queued": "about to run", "held": "stuck, needs a reply",
               "dispatch_failed": "stuck, needs a reply", "delivery_failed": "preview never arrived"}


def open_reviews(days: int = 3) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = []
    for path in sorted(POSTS.glob("*/review.json"), reverse=True):
        post_dir = path.parent
        post = load(post_dir)
        if (post_dir / "published.json").exists() or post.get("created_at", "") < cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue
        token = json.loads(path.read_text())["token"]
        try:
            state = review.api(token, "status").get("state", "")
        except ValueError:
            continue
        if state in STATE_LABEL:
            rows.append({"hook": post["slides"][0]["text"], "summary": telegram.summary(post),
                         "state": STATE_LABEL[state], "token": token})
    return rows


WATCHLIST = ROOT / "docs" / "craft-watchlist.md"


def hook_for(token: str) -> tuple[str, str]:
    """(slug, first line) for a review token, from the saved record or the post folder."""
    saved = STATE / "reviews" / f"{token}.json"
    slug = json.loads(saved.read_text()).get("slug", "") if saved.exists() else ""
    if not slug:
        for path in POSTS.glob("*/review.json"):
            if json.loads(path.read_text()).get("token") == token:
                slug = path.parent.name
                break
    if slug and (POSTS / slug / "post.json").exists():
        return slug, load(POSTS / slug)["slides"][0]["text"]
    return slug or token, ""


def note_why(token: str, note: str) -> tuple[str, int]:
    """Write one rejection reason to the watchlist. Returns (reason as read, how many times so far).

    Codes: an area ("hook"), a cause ("hook.slow"), a slide ("slide3", "all"), or free text.
    A cause or a slide refines the latest line for the same post instead of adding one.
    """
    code = telegram.resolve(note)
    slug, hook = hook_for(token)
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    existing = WATCHLIST.read_text() if WATCHLIST.exists() else "# Craft watchlist\n\n"
    lines = existing.rstrip("\n").split("\n")
    latest = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].startswith("- ") and f" · {slug} · " in lines[i]), None)

    which = re.fullmatch(r"slide([1-9])|(all)", code)
    if which and latest is not None:
        where = which.group(1) or "all"
        lines[latest] = lines[latest].split(" · slide ")[0] + f" · slide {where}"
        WATCHLIST.write_text("\n".join(lines) + "\n")
        return f"slide {where}", 0

    if "." in code and code in telegram.INSTRUCTIONS and latest is not None:
        area = code.split(".")[0]
        parts = lines[latest][2:].split(" · ")
        if parts[1] == area:  # refine the area line the first tap wrote
            key = area if code.endswith(".unsure") else code
            parts[1], parts[2] = key, telegram.REASONS.get(key, parts[2])
            lines[latest] = "- " + " · ".join(parts)
            WATCHLIST.write_text("\n".join(lines) + "\n")
            count = sum(1 for line in lines if line.startswith("- ") and f" · {key} · " in line)
            return telegram.REASONS.get(key, key), count

    key = code if code in telegram.REASONS else "other"
    reason = telegram.REASONS.get(key, " ".join(note.split())[:200])
    count = sum(1 for line in lines if line.startswith("- ") and f" · {key} · " in line) + 1
    lines.append(f"- {date.today().isoformat()} · {key} · {reason} · {slug} · “{hook}”")
    WATCHLIST.write_text("\n".join(lines) + "\n")
    return reason, count


def legacy(decision: str, slug: str, note: str = "") -> None:
    if decision == "why":
        if not slug:
            telegram.send("🤔 I don't know which post that was about. Reply to the card or to the question.")
            return
        reason, count = note_why(slug, note)
        code = telegram.resolve(note)
        area = code.split(".")[0]
        folder, hook = hook_for(slug)
        if count == 0:  # a slide number
            telegram.send(telegram.slide_noted(reason.removeprefix("slide ")))
        elif code in telegram.AREAS and telegram.AREAS[code][1]:  # an area with causes: ask which
            telegram.send(*telegram.why_detail_card(code, slug))
        else:
            telegram.send(telegram.noted(reason, count, hook))
            if area in telegram.SLIDE_AREAS and (POSTS / folder / "post.json").exists():
                post = load(POSTS / folder)
                if len(post["slides"]) > 1:
                    telegram.send(*telegram.which_slide_card(post, slug))
        output(changed="true")
        return
    rows = open_reviews()
    if decision == "list":
        telegram.send(telegram.open_reviews(rows))
        return
    hint = ("↩️ Reply <code>approve</code> or <code>disapprove</code> to the preview card itself "
            "(or add its Review ID).")
    telegram.send(hint + "\n\n" + telegram.open_reviews(rows))


def prune(root: Path, days: int) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    for folder in sorted(root.glob("*")):
        stamp = folder.name[:8]
        if folder.is_dir() and stamp.isdigit() and stamp < cutoff:
            shutil.rmtree(folder)
            print(f"Removed hosted images for {folder.name}")


# ── entry point ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("operation", choices=("build", "stage", "register", "describe", "act", "finish-redo",
                                              "fail", "list", "legacy", "notify-failure", "prune", "tokens"))
    parser.add_argument("--slot", default="")
    parser.add_argument("--format", choices=("list", "story", "oneliner"))
    parser.add_argument("--new", action="store_true", help="make a post even if this slot already has one")
    parser.add_argument("--post", type=Path)
    parser.add_argument("--manual", action="store_true", help="the preview waits for a reply; no timer")
    parser.add_argument("--decision", default="list")
    parser.add_argument("--note", default="")
    parser.add_argument("--slug", default="")
    parser.add_argument("--what", default="The post you asked for")
    parser.add_argument("--kind", default="post", choices=tuple(telegram.AFTER), help="what failed, for what to tell you")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args(argv)
    token, action_id = os.environ.get("REVIEW_TOKEN", ""), os.environ.get("REVIEW_ACTION_ID", "")

    if args.operation == "build":
        build(args.format, args.slot, new=args.new)
    elif args.operation == "stage":
        stage(args.post)
    elif args.operation == "register":
        register(args.post, manual=args.manual)
    elif args.operation == "describe":
        describe(token, action_id)
    elif args.operation == "act":
        act(args.post, token, action_id)
    elif args.operation in ("finish-redo", "fail"):
        finish(token, action_id, failed=args.operation == "fail")
    elif args.operation == "list":
        legacy("list", "")
    elif args.operation == "legacy":
        legacy(args.decision, args.slug, args.note)
    elif args.operation == "notify-failure":
        run = os.environ.get("GITHUB_RUN_ID")
        url = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'mayankav/ig-work')}/actions/runs/{run}" if run else ""
        reason = os.environ.get("FAILURE_REASON") or (
            "GitHub stopped the run (it ran too long or was cancelled)." if os.environ.get("JOB_STATUS") == "cancelled"
            else "A step stopped before it could say why. The run log has it.")
        what = args.what
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}", args.slot):
            what = f"The {args.slot[11:13]}:{args.slot[13:15]} post"
        telegram.send(telegram.failed(what, reason, kind=args.kind, run_url=url))
    elif args.operation == "prune":
        prune(args.root, args.days)
    elif args.operation == "tokens":
        problems = tokens.keep_alive()
        if problems:
            telegram.send(telegram.token_trouble(problems))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = f"{exc}"
        for name, value in os.environ.items():
            if value and len(value) >= 8 and any(word in name for word in ("TOKEN", "SECRET", "KEY", "PASSWORD")):
                reason = reason.replace(value, "[hidden]")
        output(reason=reason[:400])
        raise
