#!/usr/bin/env python3
"""
telegram_review.py — read the owner's reply and act on it.

A deck the reviewer scored below the bar is held and sent to Telegram. This is
the other way to answer it: you reply in the chat instead of opening GitHub.

    publish 79262b     post the held deck
    rerun 79262b       throw it away, build a fresh one tonight
    list               what is waiting

Both ways in call release.py. Two code paths that post to Instagram is how you
end up with two different ideas of what has already gone out.

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
VERBS = {
    "publish": "publish", "post": "publish", "approve": "publish", "ship": "publish",
    "rerun": "drop", "drop": "drop", "reject": "drop", "discard": "drop",
    "list": "list", "held": "list", "pending": "list", "status": "list",
}
COMMAND = re.compile(r"^\s*(?P<verb>[a-z]+)\s*(?P<slug>[\w-]*)\s*$", re.I)


def _api(token: str, method: str, params: dict) -> dict:
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
    """Do it, and return the line to send back."""
    if verb == "list":
        waiting = release.held()
        if not waiting:
            return "Nothing is held."
        return "Held:\n" + "\n".join(
            f"  {r['slug']}  {r['score']}/100" for r in waiting)

    if not slug:
        waiting = release.held()
        if not waiting:
            return "Nothing is held right now."
        if len(waiting) > 1:
            return ("More than one deck is held, so tell me which:\n" +
                    "\n".join(f"  {r['slug']}  {r['score']}/100" for r in waiting))
        slug = waiting[0]["slug"]

    record = release.find(slug)
    if record is None:
        return f"Nothing held matching {slug!r}."
    if verb == "publish":
        return (f"Posted {record['slug']}, held at {record['score']}/100."
                if release.publish(record) == 0
                else f"Could not post {record['slug']}. The run log has the reason.")
    release.drop(record)
    return (f"Dropped {record['slug']}, held at {record['score']}/100. "
            f"Tonight's run builds a fresh one.")


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
        _api(token, "sendMessage", {"chat_id": chat, "text": reply})
        acted += 1

    remember(highest + 1)
    print(f"read {len(results)} update(s): {acted} acted on, {ignored} ignored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
