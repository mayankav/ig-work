"""Write one post: a list, a short story, or a one-liner."""
from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import PACKAGE, POSTS, ROOT, mascot
from .llm import chat_json

# Slides per format. Nine is the ceiling because Telegram's `redo images` reply
# takes single digits 1-9.
FORMATS = {"list": (7, 9), "story": (6, 8), "oneliner": (1, 1)}
MOODS = ("warm", "calm", "wistful", "sad", "tired", "joy", "wise", "invite")
MAX_SLIDE_CHARS = 200
MAX_CAPTION_CHARS = 2000
MAX_HIGHLIGHTS = 3

# Who the post is quietly about, and the topic label that goes with them.
PEOPLE = {
    "a best friend from school": "friendship", "a friend you drifted from": "friendship",
    "a best friend who moved away": "friendship",
    "an old roommate": "adult life", "mum": "parents", "dad": "parents", "a grandparent": "family",
    "an older sibling": "siblings", "a sister": "siblings", "a cousin you grew up with": "nostalgia",
    "a partner": "love",
    "your younger self": "growing up", "a favourite teacher": "school days",
    "a stranger who was kind": "kindness", "yourself, on a hard week": "being kind to yourself",
}

# Shapes, not lines: each is a frame the writer fills with its own words.
SHAPES = {
    "list": (
        "small things someone does that secretly mean 'i love you'",
        "things you only understand after a certain age or a certain life change",
        "what someone taught you without ever saying it out loud",
        "signs you grew up with more love than you realised",
        "free things that are still the best things",
        "things that feel like home, even when you're far from it",
        "rare kinds of people, and why you should keep them close",
        "little things that quietly fix a bad day",
        "last times you didn't know were the last time",
        "small things you did without thinking as a kid that take nerve now, each told as what you did, never as advice",
        "habits of people who are easy to love",
    ),
    "story": (
        "two people in an ordinary moment; one finally says the thing they never said",
        "an ordinary object that turns out to hold a whole memory",
        "a parent's odd habit that the child only understands years later",
        "someone waits a long time for something, and it arrives in a small way",
        "what looked like a small annoyance turns out to be love",
        "a younger self and an older self, one small moment apart",
        "the first time you look after someone who used to look after you, in one small everyday way",
    ),
    "oneliner": (
        "a specific, lasting good thing a lucky person has, then a two- or three-word verdict",
        "nobody talks about a small, true feeling everyone has had",
        "someone does a small thing for you and never mentions it; name that as love",
        "the best version of an everyday thing is a surprisingly small answer",
        "some people feel like a cosy everyday comparison",
        "a small thing you fought as a kid and would welcome now, pinned to one object",
        "a small everyday annoyance someone causes now, seen from the day it stops",
        "someone who lives far away now, and the one small habit you both kept",
    ),
}

# What people search under each topic, from the 2026-09-13 keyword dig (sizes and sources in
# .agents/skills/suresilly-writer/references/keyword-dfs-2026-09-13.md). A topic with no list
# gets none, and the writer picks its own under the caption rule.
TAGS = {
    "friendship": "#friendshipquotes #bestfriendquotes #childhoodfriends #longdistancefriendship",
    "parents": "#mother #momquotes #mumquotes #motherdaughter #motherson #dad #dadquotes #fatherdaughter #fatherson",
    "family": "#grandma #grandparents #grandmashouse",
    "siblings": "#siblings #sisterlove #brotherandsister #siblinglove #oldersiblings #growingupwithsiblings",
    "nostalgia": "#childhoodmemories #nostalgia #childhoodfriends #grandmashouse #growinguptogether",
    "love": "#relationshipquotes #quotesaboutlove",
    "growing up": "#growingup #childhoodmemories",
    "school days": "#childhoodmemories #schoolmemories",
    "kindness": "#kindnessmatters #kindnessquotes #randomactsofkindness",
    "being kind to yourself": "#selflovequotes #bekindtoyourself",
}

BANNED = ("tapestry", "whisper", "whispers", "whispered", "sigh", "sighs", "sighed", "symphony",
          "journey", "embrace", "embraced", "testament", "delve", "vibrant", "cherish", "cherished",
          "gentle reminder", "softly", "the world felt", "in a world", "remember that",
          "it's okay to", "beacon", "navigate", "unspoken", "profound")


def banned_in(text: str) -> list[str]:
    text = plain(text).lower().replace("’", "'")
    return [word for word in BANNED if re.search(rf"\b{re.escape(word)}\b", text)]

# The craft rules live in craft.md, one file the writer, the editor and the humans read.
# Everything above "## editor" is the writer's brief; the rest is the editor's pass.
_CRAFT = (PACKAGE / "craft.md").read_text(encoding="utf-8").replace("{{BANNED}}", ", ".join(BANNED))
_WRITER_CRAFT, _EDITOR_CRAFT = (part.strip() for part in _CRAFT.split("\n## editor\n", 1))

SYSTEM = _WRITER_CRAFT + """

Every slide names the donkey's pose. The donkey is the reader, not a character in the \
story: pick the pose for what the line makes the reader feel or do. Rules:
- pick from the list below, by exact name. never the same pose twice in one post.
- a pose marked OBJECT only when the line is about that object or that exact moment \
(a mug for tea or a slow morning, a book for reading, a phone for a text). otherwise a \
plain-body pose. when the line does name a thing we have a pose for, prefer that pose.
- lying-down poses (curled_up, face_down, on_back, propped_up) only for rest, collapse \
or a lazy evening, never for a tender line.
- slide 1 of a list or a story: point_right, beckoning or presenting.
- the last slide of a list: offering, waving, holding_heart or beckoning.
- winking and approving are cheeky; never on the line that carries the feeling.

Poses:
""" + mascot.notes() + """

Reply with JSON only:
{"hook_options": ["...", "...", "..."], "slides": [{"text": "...", "pose": "..."}], \
"caption": "...", "alt": "one sentence describing the post for screen readers"}"""


EDITOR = SYSTEM + "\n\n" + _EDITOR_CRAFT


class WriteError(RuntimeError):
    pass


def plain(text: str) -> str:
    return text.replace("[[", "").replace("]]", "")


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", plain(text).lower()) if len(w) > 2}


def too_similar(hook: str, previous: list[str], limit: float = 0.6) -> str | None:
    """Return the earlier hook this one repeats, if any (word-set overlap)."""
    mine = words(hook)
    for old in previous:
        theirs = words(old)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= limit:
            return old
    return None


def previous_hooks(root=POSTS) -> list[str]:
    hooks = []
    for path in sorted(root.glob("*/post.json")):
        try:
            hooks.append(json.loads(path.read_text())["slides"][0]["text"])
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return hooks


def recent_posts(root=POSTS, days: int = 14, limit: int = 10) -> list[str]:
    """Our own last posts, one string each, newest first: the do-not-reuse list."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d")
    lines = []
    for path in sorted(root.glob("*/post.json"), reverse=True):
        if path.parent.name[:8] < cutoff:
            break
        try:
            slides = json.loads(path.read_text())["slides"]
        except (OSError, ValueError, KeyError):
            continue
        lines.append(" / ".join(plain(s["text"]) for s in slides))
        if len(lines) >= limit:
            break
    return lines


def owner_notes(path=None, days: int = 14, limit: int = 8) -> list[str]:
    """What the owner said when sending a post back, newest first. 'fine' means nothing to learn."""
    path = path or ROOT / "docs" / "craft-watchlist.md"
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    notes = []
    for line in path.read_text().splitlines():
        parts = [p.strip() for p in line[2:].split(" · ")] if line.startswith("- ") else []
        if len(parts) < 5 or parts[0] < cutoff or parts[1] in ("fine", "okay", "loved"):
            continue
        from .telegram import INSTRUCTIONS
        tell = INSTRUCTIONS.get(parts[1], f"the owner said: {parts[2]}")
        slide = f" ({parts[5]})" if len(parts) > 5 else ""  # the line already says "slide 3"
        notes.append(f"{tell}{slide}. the post: {parts[4]}")
    return list(reversed(notes))[:limit]


def context(previous_posts: list[str], notes: list[str]) -> str:
    """The part of the brief that changes every day: what not to repeat, and what the owner said."""
    text = ""
    if previous_posts:
        text += ("Already posted in the last two weeks. Do not reuse their objects, their openings, "
                 "their people or their sentence shapes; a reader who saw one should not feel they are "
                 "reading it again:\n" + "\n".join(f"- {p}" for p in previous_posts) + "\n\n")
    if notes:
        text += ("Recent notes from the owner on posts that were sent back, newest first. Each note "
                 "names one exact thing. Change that one thing and nothing else: keep every other "
                 "habit of the page that the note does not mention. Do not copy the quoted post.\n"
                 + "\n".join(f"- {n}" for n in notes) + "\n\n")
    return text


def draw(fmt: str, seed: str) -> dict:
    rng = random.Random(seed)
    person = rng.choice(sorted(PEOPLE))
    return {"topic": PEOPLE[person], "person": person, "shape": rng.choice(SHAPES[fmt])}


def ask(fmt: str, angle: dict, daily: str = "", note: str = "") -> str:
    """The user message: what changes every day, the drawn angle, and its topic's hashtags."""
    tags = TAGS.get(angle["topic"])
    tags = f"Hashtags for this topic (use only the ones this post is about): {tags}\n" if tags else ""
    return (f"{daily}Format: {fmt}\nShape to use: {angle['shape']}\n"
            f"Who it is quietly about: {angle['person']}\n{tags}{note}Write it.")


def problems(post: dict, fmt: str) -> list[str]:
    found = []
    slides = post.get("slides")
    low, high = FORMATS[fmt]
    if not isinstance(slides, list) or not low <= len(slides) <= high:
        found.append(f"a {fmt} needs {low}-{high} slides")
        slides = slides if isinstance(slides, list) else []
    for number, slide in enumerate(slides, 1):
        text = slide.get("text", "") if isinstance(slide, dict) else ""
        if not isinstance(text, str) or not text.strip():
            found.append(f"slide {number} is empty")
            continue
        if len(plain(text)) > MAX_SLIDE_CHARS:
            found.append(f"slide {number} is over {MAX_SLIDE_CHARS} characters")
        if re.search(r"https?://|www\.|#\w", text):
            found.append(f"slide {number} has a link or a hashtag")
        if text.count("[[") != text.count("]]") or text.count("[[") > 1:
            found.append(f"slide {number} must highlight at most one phrase in [[ ]]")
        used = banned_in(text)
        if used:
            found.append(f"slide {number} uses {', '.join(repr(w) for w in used)}")
    caption = post.get("caption")
    if not isinstance(caption, str) or not caption.strip():
        found.append("the caption is missing")
    elif len(caption) > MAX_CAPTION_CHARS:
        found.append(f"the caption is over {MAX_CAPTION_CHARS} characters")
    return found


def tidy_caption(caption: str) -> str:
    """Body, a blank line, then every hashtag on one line (at most five)."""
    tags = list(dict.fromkeys(tag.lower() for tag in re.findall(r"#\w+", caption)))[:5]
    body = re.sub(r"#\w+", "", caption)
    lines = [" ".join(line.split()) for line in body.splitlines()]
    body = "\n".join(line for line in lines if line)
    return body + ("\n\n" + " ".join(tags) if tags else "")


def tidy(post: dict, fmt: str) -> list[dict]:
    """Slides with text, a real pose name (or none), and the mood that pose belongs to."""
    slides, highlights = [], 0
    for number, slide in enumerate(post["slides"], 1):
        pose = slide.get("pose") if slide.get("pose") in mascot.NOTES else None
        mood = mascot.MOOD_OF[pose] if pose else (slide.get("mood") if slide.get("mood") in MOODS else "calm")
        if fmt != "oneliner" and number == 1:
            if mood != "invite":  # the donkey points you into the swipe
                mood, pose = "invite", None
        elif mood == "invite":
            mood, pose = "warm", None
        text = " ".join(re.sub(r"\s*[—–]\s*", ", ", slide["text"]).split()).replace(" ,", ",")
        if "[[" in text:
            highlights += 1
            if highlights > MAX_HIGHLIGHTS:
                text = plain(text)
        slides.append({"text": text, "mood": mood, "pose": pose})
    return slides


def write_post(fmt: str, seed: str, previous: list[str] | None = None,
               chat: Callable[[str, str], tuple[dict, str]] = chat_json,
               recent: list[str] | None = None, notes: list[str] | None = None) -> dict:
    if fmt not in FORMATS:
        raise WriteError(f"Unknown format {fmt!r}.")
    angle = draw(fmt, seed)
    previous = previous if previous is not None else previous_hooks()
    daily = context(recent if recent is not None else recent_posts(),
                    notes if notes is not None else owner_notes())
    note = ""
    faults: list[str] = []
    for _ in range(3):
        user = ask(fmt, angle, daily, note)
        post, model = chat(SYSTEM, user)
        faults = problems(post, fmt)
        if not faults:
            try:
                edited, editor = chat(EDITOR, user + "\n\nDraft:\n" + json.dumps(post, ensure_ascii=False))
                if not problems(edited, fmt):
                    post, model = edited, f"{model} + edit by {editor}"
            except Exception as exc:  # the draft already passed; an editor failure keeps it
                print(f"Editor pass skipped: {exc}")
            slides = tidy(post, fmt)
            repeat = too_similar(slides[0]["text"], previous)
            if not repeat:
                return {"format": fmt, **angle, "slides": slides, "caption": tidy_caption(post["caption"]),
                        "alt": str(post.get("alt", "")).strip()[:300],
                        "hook_options": [str(h) for h in post.get("hook_options", [])][:3], "model": model}
            faults = [f"the first line is too close to an earlier post: {plain(repeat)!r}"]
        note = "Fix this in your new version: " + "; ".join(faults) + ".\n"
    raise WriteError("The writer could not produce a usable post: " + "; ".join(faults))
