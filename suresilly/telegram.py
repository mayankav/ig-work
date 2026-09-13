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
    if post.get("reel"):
        size = f"🎬 Reel, {post['reel']['seconds']:g}s, {post['reel']['tune']} tune"
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


def posted(post: dict, link: str, threads: dict | None = None) -> str:
    where = f'<a href="{html.escape(link)}">Open it on Instagram ↗</a>' if link else "It's live on Instagram."
    if threads and threads.get("error"):
        where += (f"\n🧵 Threads didn't take it: {esc(threads['error'])}. Instagram is fine. "
                  "Nothing to reply; the next one-liner tries Threads again.")
    elif threads:
        where += (f'\n🧵 <a href="{html.escape(threads["link"])}">Also on Threads ↗</a>' if threads.get("link")
                  else "\n🧵 Also on Threads.")
    return (f"✅ <b>Posted!</b>\n{summary(post)}\n<b>“{esc(post['slides'][0]['text'])}”</b>\n\n{where}\n\n"
            f"📊 Saves and shares get measured in 3 days.\n⏭ Next post: {next_slot()}")


def token_trouble(problems: list[tuple[str, str]]) -> str:
    names = {"IG_ACCESS_TOKEN": "Instagram", "THREADS_ACCESS_TOKEN": "Threads"}
    lines = "\n".join(f"• {names.get(name, name)}: {esc(reason)}" for name, reason in problems)
    return (f"🔑 <b>A token couldn't be renewed.</b>\n{lines}\n\n"
            "Posting carries on: a token keeps working until 60 days after its last renewal.\n"
            "↩️ Nothing to reply. The next run tries again. If this message keeps coming, make a new token "
            "(docs/threads.md shows how).\n"
            "If you do nothing and it keeps failing, that app stops posting when the token runs out.")


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


# Why a post was sent back. Two taps: the area, then the specific cause inside it.
# Every cause carries the one sentence the writer will be told, so a rejection
# never becomes a guess. "unsure" is always an option and records the area only.
AREAS = {
    "hook": ("slide 1 didn't pull me in", {
        "slow": ("took too long to say what it's about", "slide 1 took too long to name its subject: put the subject in the first four words"),
        "unclear": ("i didn't get what it meant", "slide 1 was not understood on one read: plain words, one idea, no cleverness"),
        "notme": ("not about me or my people", "slide 1 did not feel like the reader's life: name a person or a moment most readers have, in second person"),
        "noreason": ("gave me no reason to swipe", "slide 1 gave no reason to swipe: promise something the reader wants to see, an open loop, not a label"),
        "seen": ("seen that hook before", "slide 1 used a hook shape the reader has seen: use a different shape from the recent posts"),
    }),
    "line": ("a line was off", {
        "generic": ("could be about anyone", "that line could be about anyone: give it one detail most readers share"),
        "private": ("too specific, not my life", "that line was too private: swap the detail for one most readers have lived"),
        "preachy": ("preachy or advice-y", "that line lectured: state the moment, cut the lesson"),
        "flat": ("true but flat, no feeling", "that line was true but flat: add the second half, what it cost or meant"),
        "machine": ("sounds like a machine wrote it", "that line sounded machine-made: no not-X-but-Y, no triad, no self-answered question"),
        "long": ("too long to read", "that line was too long: under 20 words, one idea"),
    }),
    "ending": ("the last slide", {
        "moral": ("it preached", "the last slide preached: end on a picture or one plain warm sentence, never a lesson"),
        "repeat": ("it just repeated the post", "the last slide repeated the post: end on one image or one sentence that adds something"),
        "ask": ("it ended on a question or an ask", "the last slide ended on a question or an ask: end on a statement"),
        "abrupt": ("stopped too early, felt unfinished", "the last slide felt unfinished: land the turn, one more beat"),
        "down": ("left me feeling low", "the last slide left the reader low: end warm, even after a sad middle"),
    }),
    "topic": ("wrong topic or person", {
        "person": ("not this person again", "the owner does not want this person again for now: pick a different person"),
        "subject": ("this subject isn't us", "this subject is not the page: stay with family, friendship, growing up and love"),
        "recent": ("we did this recently", "this topic was posted recently: pick a topic not in the recent posts"),
    }),
    "format": ("format or length", {
        "long": ("too many slides", "too many slides: 7 or 8 at most, cut the weakest"),
        "short": ("too thin, needed more", "too thin: one more strong item, not padding"),
        "oneliner": ("should have been a one-liner", "this idea was a one-liner, not a carousel: one slide, one twist"),
    }),
    "tone": ("tone off", {
        "sad": ("too sad", "too sad: keep the warmth in every slide, not only the last"),
        "cute": ("too cute, greeting card", "too cute: cut the sweetness, keep the specific thing"),
        "clever": ("trying too hard", "trying too hard: plain words, no wordplay"),
        "cold": ("no warmth", "no warmth: the reader should feel liked, not observed"),
    }),
    "caption": ("caption or send line", {
        "generic": ("send line generic", "the send line was generic: name one specific person to send it to"),
        "repeat": ("repeats slide 1", "the caption repeated slide 1: add one new thought"),
        "long": ("too long", "the caption was too long: 2 to 4 short lines"),
        "tags": ("hashtags off", "the hashtags were off: 3 to 5 lowercase tags from the topic's list, none branded or catch-all"),
    }),
    "donkey": ("donkey didn't fit", {}),
    "whole": ("the whole thing felt off", {
        "generated": ("felt generated", "the post read as generated: fewer parallel shapes, one odd true detail per slide"),
        "boring": ("nothing surprising in it", "nothing surprised the reader: one line must turn or reveal"),
        "dejavu": ("felt like a repeat of us", "the post felt like a repeat of this page: change the shape, the person and the objects"),
    }),
    "fine": ("nothing to learn, just not this one", {}),
}
# Areas where knowing the slide helps. Asked as one more tap.
SLIDE_AREAS = {"line", "donkey"}
# Every code the watchlist can carry: an area, or area.cause. Typed shorthand like
# "preachy" resolves to the one cause with that name.
REASONS = {area: label for area, (label, _) in AREAS.items()}
REASONS.update({f"{area}.{cause}": label for area, (_, causes) in AREAS.items() for cause, (label, _) in causes.items()})
INSTRUCTIONS = {f"{area}.{cause}": tell for area, (_, causes) in AREAS.items() for cause, (_, tell) in causes.items()}
_TRY = {"hook": "hook shape", "line": "shape for that line", "ending": "ending", "topic": "topic and person", "format": "format",
        "tone": "tone", "caption": "caption", "donkey": "pose", "whole": "overall shape"}
INSTRUCTIONS.update({area: f"the owner felt: {AREAS[area][0]}, and could not say more. try a different {noun}; change nothing else that worked"
                     for area, noun in _TRY.items()})
INSTRUCTIONS.update({f"{area}.unsure": INSTRUCTIONS[area] for area in _TRY})
_names = [c for _, (_, causes) in AREAS.items() for c in causes]
ALIASES = {c: f"{a}.{c}" for a, (_, causes) in AREAS.items() for c in causes if _names.count(c) == 1}


def resolve(code: str) -> str:
    code = code.strip().lower()
    return code if code in REASONS else ALIASES.get(code, code)


def why_card(post: dict, token: str) -> tuple[str, list[list[tuple[str, str]]]]:
    """The first question after a rejection: which area. Text plus inline buttons (label, callback data)."""
    text = (f"🧐 <b>Why did this one go?</b>\n<i>“{esc(post['slides'][0]['text'])}”</i>\n\n"
            "Tap the area, then the bot asks one more question so the note is exact. "
            "Or reply to this message with <code>why: your own words</code>.\n"
            "Nothing changes on its own: the next post reads the note, and the same note twice earns a rule. "
            "If you stay quiet, nothing is recorded.\n\n"
            f"Review ID: {token}")
    areas = list(AREAS.items())
    buttons = [[(label, f"why:{token}:{area}") for area, (label, _) in areas[i:i + 2]] for i in range(0, len(areas), 2)]
    return text, buttons


def why_detail_card(area: str, token: str) -> tuple[str, list[list[tuple[str, str]]]]:
    """The second question: which cause inside the area. 'not sure' keeps the area only."""
    label, causes = AREAS[area]
    text = f"<b>{esc(label)}</b>: what exactly? Tap one, or skip it.\n\nReview ID: {token}"
    items = [(cause_label, f"why:{token}:{area}.{cause}") for cause, (cause_label, _) in causes.items()]
    items.append(("not sure", f"why:{token}:{area}.unsure"))
    return text, [items[i:i + 2] for i in range(0, len(items), 2)]


def which_slide_card(post: dict, token: str) -> tuple[str, list[list[tuple[str, str]]]]:
    """The second tap: which slide. Numbers 1-9 and 'all'; silence means 'not sure'."""
    count = min(len(post.get("slides", [])), 9)
    text = ("Which slide? Tap a number, or <code>all</code>. Skip it if you're not sure.\n\n"
            f"Review ID: {token}")
    numbers = [(str(n), f"why:{token}:slide{n}") for n in range(1, count + 1)] + [("all", f"why:{token}:all")]
    return text, [numbers[i:i + 5] for i in range(0, len(numbers), 5)]


def slide_noted(which: str) -> str:
    return f"👍 Got it: slide {which}." if which != "all" else "👍 Got it: the whole post."


def noted(reason: str, count: int, hook: str) -> str:
    times = {1: "first time", 2: "second time", 3: "third time"}.get(count, f"{count}th time")
    nudge = ("" if count == 1 else
             "\nThat's twice: it goes into the editor's strike list in the brief." if count == 2 else
             "\nThree times: it becomes a banned word or a writer rule.")
    return (f"📝 <b>Noted:</b> {esc(reason)} ({times}).\n<i>“{esc(hook)}”</i>{nudge}\n\n"
            "Nothing else to do. It's written in docs/craft-watchlist.md.")


def send(text: str, buttons: list[list[tuple[str, str]]] | None = None) -> None:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        print("Telegram is not configured; message not sent:\n" + text)
        return
    body = {"chat_id": chat, "text": text, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}
    if buttons:
        body["reply_markup"] = {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row]
                                                    for row in buttons]}
    response = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20, json=body)
    if response.status_code != 200 or not response.json().get("ok"):
        raise RuntimeError(f"Telegram did not accept the message (HTTP {response.status_code}).")
