#!/usr/bin/env python3
"""
Telegram reply-reader regression. No network is touched.

Anybody can message a Telegram bot. The chat id is the only thing that decides
whether a message is obeyed, so most of this file is about that, and about the
two ways the reader could do something worse than nothing: obey a stranger, or
lose its place in the update queue and replay a command that already ran.

The parser is deliberately narrow, and the words it does NOT know are as much
the point as the ones it does. "ok" and "yes" turn up in an ordinary chat by
accident, and one of them posting to Instagram is the failure this shape avoids.
"""
import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import release  # noqa: E402
import telegram_review as tg  # noqa: E402

OWNER = "8531521479"
STRANGER = "111222333"


def message(text: str, chat: str = OWNER, update_id: int = 1) -> dict:
    return {"update_id": update_id, "message": {"chat": {"id": int(chat)}, "text": text}}


def run() -> int:
    failures = []

    # ── what counts as a command ──
    for text, expected in [
        ("publish 79262b", ("publish", "79262b")),
        ("PUBLISH 79262b", ("publish", "79262b")),
        ("  drop  aa1234  ", ("drop", "aa1234")),
        ("rerun 79262b", ("drop", "79262b")),        # the word the held message suggests
        ("list", ("list", "")),
        ("publish", ("publish", "")),                 # only one held, so no id needed
    ]:
        if tg.parse(text) != expected:
            failures.append(f"PARSE {text!r} gave {tg.parse(text)}, expected {expected}")

    # The words it must NOT know. A stray "ok" in the chat cannot post to
    # Instagram, and neither can a sentence that happens to contain "publish".
    for text in ("ok", "yes", "yes please", "no", "sure", "publish this one I think",
                 "hey did you see the deck?", "", "   ", "post it when you get a sec"):
        if tg.parse(text) is not None:
            failures.append(f"PARSE {text!r} was read as a command: {tg.parse(text)}")

    # ── the cursor ──
    real_cursor, real_pending, real_api = tg.CURSOR, release.PENDING, tg._api
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="tg-"))
    tg.CURSOR = tmp / "offset.json"
    release.PENDING = tmp / "pending"
    release.PENDING.mkdir()
    try:
        if tg.offset() != 0:
            failures.append("CURSOR a missing cursor did not start at zero")
        tg.remember(42)
        if tg.offset() != 42:
            failures.append("CURSOR did not survive being written")
        tg.CURSOR.write_text("{not json", encoding="utf-8")
        if tg.offset() != 0:
            failures.append("CURSOR an unreadable cursor was not treated as zero")

        # ── who is obeyed ──
        (release.PENDING / "20260830_x_79262b.json").write_text(json.dumps({
            "slug": "20260830_x_79262b", "deck": "carousels/x/carousel.md",
            "score": 74, "reason": "thin", "notes": [], "held_at": "2026-08-30T20:00:00Z"}),
            encoding="utf-8")

        sent, dropped = [], []
        release.publish = lambda record: (dropped.append(("publish", record["slug"])), 0)[1]
        release.drop = lambda record: (dropped.append(("drop", record["slug"])), 0)[1]

        def fake_api(token, method, params):
            if method == "getUpdates":
                return {"ok": True, "result": FEED}
            sent.append(params.get("text", ""))
            return {"ok": True}
        tg._api = fake_api

        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
        os.environ["TELEGRAM_CHAT_ID"] = OWNER

        # A stranger asking for exactly the right thing must be ignored, and the
        # owner's own message in the same batch must still be acted on.
        tg.remember(0)
        FEED = [message("publish 79262b", chat=STRANGER, update_id=7),
                message("list", chat=OWNER, update_id=8)]
        tg.main()
        if any(action[0] == "publish" for action in dropped):
            failures.append("OWNER a stranger's publish was obeyed")
        if not sent:
            failures.append("OWNER the owner's own message was not answered")
        if tg.offset() != 9:
            failures.append(f"CURSOR did not advance past the batch: {tg.offset()}")

        # A command that already ran is never seen again, because the cursor
        # moved past it. A schedule that forgets its place double-posts.
        sent.clear(); dropped.clear()
        FEED = []
        tg.main()
        if sent or dropped:
            failures.append("CURSOR an acknowledged batch was processed again")

        # And the real thing.
        tg.remember(0)
        FEED = [message("rerun 79262b", chat=OWNER, update_id=11)]
        tg.main()
        if ("drop", "20260830_x_79262b") not in dropped:
            failures.append(f"ACT rerun did not drop the held deck: {dropped}")

        # An id nobody is holding is answered, not acted on.
        sent.clear(); dropped.clear()
        tg.remember(0)
        FEED = [message("publish ffffff", chat=OWNER, update_id=12)]
        tg.main()
        if dropped:
            failures.append("ACT an unknown id was acted on")
        if not any("Nothing held" in line for line in sent):
            failures.append(f"ACT an unknown id was not answered: {sent}")
    finally:
        tg.CURSOR, release.PENDING, tg._api = real_cursor, real_pending, real_api

    total = 22
    if failures:
        print(f"telegram: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"telegram: {total}/{total} passed (6 commands, 10 non-commands refused, cursor "
          f"survives and advances, a stranger ignored, unknown id answered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
