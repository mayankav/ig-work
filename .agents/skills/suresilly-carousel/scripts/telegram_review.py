#!/usr/bin/env python3
"""
telegram_review.py — act on the owner's reply, and say what happened.

A deck the reviewer scored below the bar is held and sent to Telegram. This is
the other way to answer it: you reply in the chat instead of opening GitHub.

    publish 79262b     post the held deck
    rerun 79262b       throw it away, build a fresh one tonight
    list               what is waiting

Both ways in call release.py. Two code paths that post to Instagram is how you
end up with two different ideas of what has already gone out.

TWO ENTRY POINTS, ONE act()

    --reply <verb> <slug>   act on a reply the webhook already parsed, and send
                            the answer back. This is the live path: Telegram
                            pushes the reply to the Cloudflare Worker the instant
                            it is sent, the Worker dispatches review.yml, and
                            review.yml calls this. Nothing polls.

    main() (no args)        the old path: poll getUpdates, parse each message,
                            act. Kept because it carries the chat-id security
                            model and its regression test, but nothing runs it on
                            a schedule anymore — the webhook replaced the poll.

Both go through act(), so there is still one place that decides what a reply
does and one place that talks to release.py.

WHO IS ALLOWED TO SAY THIS

Anybody can message a Telegram bot. Only the chat id in TELEGRAM_CHAT_ID is
obeyed, and every other message is counted and ignored. That check is the whole
security model here, so it happens before the text is even looked at.

The text is DATA. Two verbs and an id are read out of it and nothing else is.
There is no path where a sentence in a chat message becomes an instruction to
this program — it can name a deck that is already held, and it can pick one of
two things to do with it. A message that says anything else is ignored, however
it is phrased and whoever appears to have sent it.

THE CURSOR

Telegram keeps an update queue. Asking for updates with offset=N acknowledges
everything below N and it is never sent again, so the offset has to survive the
run. It is written to state/ and committed, exactly like every other piece of
memory this pipeline keeps, because a schedule that forgets its place either
replays a command or loses one.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import release  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CURSOR = REPO_ROOT / "state" / "telegram_offset.json"
API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 30

# The only things a reply may ask for.
#
# Deliberately no "ok", "yes", "no" or "sure". Those are words that turn up in
# an ordinary chat by accident, and one of them would post to Instagram. Every
# verb here is one somebody had to mean.
#
# This table is mirrored in ops/dispatch-worker/src/index.js, which is where a
# reply is actually parsed now. Kept in step deliberately, so the same word means
# the same thing whichever half reads it.
#
# NOTE "rerun" means DROP, and always has. It reads like "run it again" and does
# the opposite, which is why "retry" is spelled out separately rather than folded
# into the obvious synonym set. Do not add "rerun"/"again"/"redo" to retry.
VERBS = {
    "publish": "publish", "post": "publish", "approve": "publish", "ship": "publish",
    "rerun": "drop", "drop": "drop", "reject": "drop", "discard": "drop",
    "list": "list", "held": "list", "pending": "list", "status": "list",
    # Known here so the word is understood rather than treated as chatter, but
    # this script cannot carry either out: both mean "build a deck", which is a
    # workflow dispatch, and only the Worker holds a token for that. Both paths
    # below decline them explicitly — see act() and reply().
    "retry": "retry", "tryagain": "retry",
    "force": "force", "override": "force", "build": "force",
}
COMMAND = re.compile(r"^\s*(?P<verb>[a-z]+)\s*(?P<slug>[\w-]*)\s*$", re.I)


def _api(token: str, method: str, params: dict) -> dict:
    if method == "sendMessage":
        # Share delivery receipts and bounded retries with run alerts. A failed
        # reply never repeats the action that was already performed.
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import notify
        ok, note = notify._telegram("", params["text"], None, params.get("parse_mode"))
        if not ok:
            print("::warning::Telegram did not confirm the reply: " + note)
        return {"ok": ok}
    url = API.format(token=token, method=method) + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "suresilly-carousel/3.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:                                    # noqa: BLE001
            detail = ""
        return {"ok": False, "description": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:                                 # noqa: BLE001
        return {"ok": False, "description": str(exc)}


def offset() -> int:
    if not CURSOR.is_file():
        return 0
    try:
        return int(json.loads(CURSOR.read_text(encoding="utf-8")).get("offset", 0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def remember(value: int) -> None:
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    CURSOR.write_text(json.dumps({"offset": value}, indent=2) + "\n", encoding="utf-8")


def parse(text: str) -> tuple[str, str] | None:
    """Pull a verb and a deck id out of a reply, or return None.

    Deliberately narrow. Anything that is not one known word plus an optional
    id is not a command, and this is where that is decided — before anything
    reads the rest of the message.
    """
    match = COMMAND.match(text or "")
    if not match:
        return None
    verb = VERBS.get(match.group("verb").lower())
    if not verb:
        return None
    return verb, match.group("slug").strip()


def act(verb: str, slug: str) -> str:
    """Do it, and return the HTML line to send back.

    The reply is Telegram HTML: the outcome is bold, and a deck id is a <code>
    tap-to-copy box, matching the held-deck message the owner is answering. Every
    dynamic value is escaped and no tag spans a newline. The literal words are
    kept ("Nothing held …", "Posted …", "Dropped …") because a test asserts them
    and because they are what a person reads at a glance.
    """
    def esc(text) -> str:
        return html.escape(str(text))

    def row(r: dict) -> str:
        return f"  <code>{esc(r['slug'])}</code>  {esc(r['score'])}/100"

    # Fail closed, and before anything is read or resolved. The way out of this
    # function used to be an unguarded `release.drop(record)`, which made "any
    # verb that is not list or publish" mean DESTROY THE DECK. `retry` and
    # `force` were about to become such verbs: both are in VERBS so the words are
    # understood, but the Worker dispatches them to auto-post.yml and neither must
    # ever arrive here. If one does, the answer is to do nothing and say so — not
    # to drop a held deck because a branch was missing.
    if verb not in ("list", "publish", "drop"):
        return (f"I don't act on <b>{esc(verb)}</b> here — "
                f"that one starts a fresh build, which the Worker dispatches. "
                f"Reply publish, drop or list.")

    if verb == "list":
        waiting = release.held()
        if not waiting:
            return "Nothing is held."
        return "<b>Held</b>\n" + "\n".join(row(r) for r in waiting)

    if verb == "publish":
        import run_control
        if run_control.pause_reason(release.REPO_ROOT / "state/HALT"):
            return "<b>Paused</b>. Nothing was posted. Held decks stay held. Reply <code>list</code> to see them."

    if not slug:
        waiting = release.held()
        if not waiting:
            return "Nothing is held right now."
        if len(waiting) > 1:
            return ("<b>More than one deck is held</b>, so tell me which:\n" +
                    "\n".join(row(r) for r in waiting))
        slug = waiting[0]["slug"]

    record = release.find(slug)
    if record is None:
        return f"Nothing held matching <code>{esc(slug)}</code>."
    if verb == "publish":
        return (f"<b>Posted</b> <code>{esc(record['slug'])}</code>, "
                f"held at {esc(record['score'])}/100."
                if release.publish(record) == 0
                else f"<b>Could not post</b> <code>{esc(record['slug'])}</code>. "
                     f"The run log has the reason.")
    if verb == "drop":
        release.drop(record)
        return (f"<b>Dropped</b> <code>{esc(record['slug'])}</code>, "
                f"held at {esc(record['score'])}/100. Tonight's run builds a fresh one.")

    # Unreachable: the guard at the top of this function already narrowed verb to
    # the three below. Here so the function has no implicit last action at all.
    return f"I don't act on <b>{esc(verb)}</b> here."


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("no Telegram credentials, nothing to read")
        return 0

    updates = _api(token, "getUpdates", {"offset": offset(), "timeout": 0, "limit": 50})
    if not updates.get("ok"):
        print(f"could not read updates: {updates.get('description', 'no reason given')}")
        return 0

    results = updates.get("result", [])
    if not results:
        print("no new messages")
        return 0

    highest = offset() - 1
    acted = ignored = 0
    for update in results:
        highest = max(highest, int(update.get("update_id", 0)))
        message = update.get("message") or update.get("channel_post") or {}
        # The whole security model, and it runs before the text is read.
        if str((message.get("chat") or {}).get("id", "")) != chat:
            ignored += 1
            continue
        command = parse(message.get("text", ""))
        if command is None:
            ignored += 1
            continue
        verb, slug = command
        reply = act(verb, slug)
        print(f"  {verb} {slug or '(unnamed)'} -> {reply.splitlines()[0]}")
        # parse_mode=HTML because act() returns HTML now — the outcome is bold and
        # the slug is a <code> tap-to-copy box. Sent plain, the tags would show as
        # literal <b>…</b> in the chat.
        _api(token, "sendMessage", {"chat_id": chat, "text": reply, "parse_mode": "HTML"})
        acted += 1

    remember(highest + 1)
    print(f"read {len(results)} update(s): {acted} acted on, {ignored} ignored")
    return 0


def reply(verb: str, slug: str) -> int:
    """The live path. The Worker already authenticated the push, matched the chat
    id and parsed the command; review.yml hands us the mapped verb and the slug.
    So there is no getUpdates, no cursor and no chat-id gate here — those belong
    to the poller, and the Worker did the gate. We act and send the one answer.

    The verb is already mapped (publish/drop/list). A safety net anyway: if some
    other word arrives, run it through VERBS so this can never do something the
    reply did not name.

    `retry` and `force` are known verbs that deliberately do not belong to this
    script — both mean "build a deck", which is a workflow dispatch the Worker
    performs directly against auto-post.yml. Reaching here means the routing
    broke, so say that rather than calling either one unknown.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    mapped = VERBS.get(verb.lower(), verb.lower())
    if mapped in ("retry", "force"):
        print(f"{mapped} is dispatched to auto-post by the Worker, not acted on "
              f"here; nothing done")
        return 0
    if mapped not in ("publish", "drop", "list"):
        print(f"unknown decision {verb!r}, nothing done")
        return 0
    answer = act(mapped, slug)
    print(f"  {mapped} {slug or '(unnamed)'} -> {answer.splitlines()[0]}")
    if token and chat:
        _api(token, "sendMessage", {"chat_id": chat, "text": answer, "parse_mode": "HTML"})
    else:
        print("no Telegram credentials, acted but did not send the reply")
    return 0


def cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Act on a Telegram reply.")
    ap.add_argument("--reply", nargs=2, metavar=("VERB", "SLUG"),
                    help="act on one reply the webhook already parsed and send the "
                         "answer back; SLUG may be empty (pass '')")
    a = ap.parse_args(argv)
    if a.reply is not None:
        return reply(a.reply[0], a.reply[1])
    return main()


if __name__ == "__main__":
    raise SystemExit(cli())
