"""Every Telegram message the bot sends, in one place.

Each message says what happened, what you can reply, and what happens if you
stay quiet. Telegram HTML: <b>, <i>, <code>, <a>, <blockquote expandable>.
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timedelta, timezone

import requests

IST = timezone(timedelta(hours=5, minutes=30))
CARD_LIMIT = 3900
LABEL = {"list": "📚 List", "story": "📖 Story", "oneliner": "💬 One-liner"}
SLOTS = (8, 20)


def esc(text: str) -> str:
    return html.escape(text.replace("[[", "").replace("]]", ""), quote=False)


def next_slot(now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    for hour in SLOTS:
        if now.hour < hour:
            return f"{hour:02d}:00 IST today"
    return f"{SLOTS[0]:02d}:00 IST tomorrow"


def summary(post: dict) -> str:
    count = len(post["slides"])
    size = "1 image" if count == 1 else f"{count} slides"
    return f"{LABEL.get(post['format'], post['format'])} · {esc(post.get('topic', ''))} · {size}"


def review_card(post: dict, token: str, *, manual: bool = False, redo_of: str | None = None) -> str:
    """The message you reply to. It must carry 'Review ID: <token>' in plain text."""
    title = "🔁 <b>Redo ready</b>" if redo_of else "🫏 <b>New post ready</b>"
    hook = esc(post["slides"][0]["text"])
    timer = ("✋ <b>This one waits for you.</b> It won't post on its own." if manual else
             "⏰ <b>Posts itself in 1 hour</b> if you don't reply.")
    replies = ("↩️ <b>Reply to this message with:</b>\n"
               "✅ <code>approve</code> · post it now\n"
               "🗑 <code>disapprove</code> · cancel it\n"
               "🔁 <code>redo all</code> · write a new one\n"
               "🎨 <code>redo images 2,4</code> · new donkey on those slides")
    footer = f"Review ID: <code>{token}</code>"

    def build(slides_text: str, caption: str) -> str:
        parts = [f"{title}\n{summary(post)}", f"<b>“{hook}”</b>"]
        if slides_text:
            parts.append(f"📝 <b>Slides</b>\n<blockquote expandable>{slides_text}</blockquote>")
        parts.append(f"✍️ <b>Caption</b>\n<blockquote expandable>{esc(caption)}</blockquote>")
        parts += [timer, replies, footer]
        return "\n\n".join(parts)

    lines = [f"{n}. {esc(s['text'])}" for n, s in enumerate(post["slides"], 1)] if len(post["slides"]) > 1 else []
    caption = post["caption"]
    card = build("\n".join(lines), caption)
    while len(card) > CARD_LIMIT and len(caption) > 80:  # trim the caption before anything else
        caption = caption[: max(80, len(caption) - (len(card) - CARD_LIMIT) - 8)].rstrip() + "…"
        card = build("\n".join(lines), caption)
    if len(card) > CARD_LIMIT:
        card = build("", caption)
    return card


def plain_card(post: dict, token: str, *, manual: bool = False, redo_of: str | None = None) -> str:
    """The same card in plain text, under 1000 characters, for a Worker without HTML cards."""
    title = "🔁 Redo ready" if redo_of else "🫏 New post ready"
    timer = "✋ This one waits for you. It won't post on its own." if manual else "⏰ Posts itself in 1 hour if you don't reply."
    label = summary(post).replace("&amp;", "&")
    hook = post["slides"][0]["text"].replace("[[", "").replace("]]", "")[:300]
    return (f"{title}\n{label}\n\n“{hook}”\n\n{timer}\n\n↩️ Reply to this message with:\n"
            f"✅ approve · post it now\n🗑 disapprove · cancel it\n🔁 redo all · write a new one\n"
            f"🎨 redo images 2,4 · new donkey on those slides\n\nReview ID: {token}")


def plain_details(post: dict) -> str:
    """Slide texts and caption in plain text, under 2900 characters."""
    lines = [f"{n}. {s['text'].replace('[[', '').replace(']]', '')}" for n, s in enumerate(post["slides"], 1)]
    text = ("📝 Slides\n" + "\n".join(lines) + "\n\n" if len(lines) > 1 else "") + "✍️ Caption\n" + post["caption"]
    return text if len(text) <= 2900 else text[:2899] + "…"


def posted(post: dict, link: str) -> str:
    where = f'<a href="{html.escape(link)}">Open it on Instagram ↗</a>' if link else "It's live on Instagram."
    return (f"✅ <b>Posted!</b>\n{summary(post)}\n<b>“{esc(post['slides'][0]['text'])}”</b>\n\n{where}\n\n"
            f"📊 Saves and shares get measured in 3 days.\n⏭ Next post: {next_slot()}")


def dropped(post: dict) -> str:
    return (f"🗑 <b>Cancelled.</b> Nothing was posted.\n<i>“{esc(post['slides'][0]['text'])}”</i>\n\n"
            f"⏭ Next post: {next_slot()}. Reply <code>retry</code> if you want a new one now.")


def failed(what: str, reason: str, *, can_retry: bool = True, run_url: str = "") -> str:
    lines = [f"🔴 <b>{esc(what)} didn't happen</b>", "", f"<b>What went wrong:</b> {esc(reason)}"]
    lines.append("<b>What you can do:</b> reply <code>retry</code> to try again now." if can_retry else
                 "<b>What you can do:</b> nothing from here, this needs a code fix.")
    lines.append(f"<b>If you do nothing:</b> the next post is at {next_slot()}.")
    if run_url:
        lines += ["", f'<a href="{html.escape(run_url)}">Open the run log ↗</a>']
    return "\n".join(lines)


def open_reviews(rows: list[dict]) -> str:
    if not rows:
        return f"📭 <b>Nothing is waiting for you.</b>\n⏭ Next post: {next_slot()}"
    lines = ["📬 <b>Waiting for your reply</b>", ""]
    for row in rows:
        lines.append(f"• <b>“{esc(row['hook'])}”</b>\n  {row['summary']} · {esc(row['state'])}\n"
                     f"  Reply <code>approve {row['token']}</code> or <code>disapprove {row['token']}</code>")
    return "\n".join(lines)


def send(text: str) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("Telegram is not configured; message not sent:\n" + text)
        return
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20, json={
        "chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}})
    if response.status_code != 200 or not response.json().get("ok"):
        raise RuntimeError(f"Telegram did not accept the message (HTTP {response.status_code}).")
