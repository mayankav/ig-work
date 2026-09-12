"""Write one post: a list, a short story, or a one-liner."""
from __future__ import annotations

import json
import random
import re
from typing import Callable

from . import POSTS
from . import mascot
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
    "an old roommate": "adult life", "mum": "parents", "dad": "parents", "a grandparent": "family",
    "an older sibling": "siblings", "a cousin you grew up with": "nostalgia", "a partner": "love",
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
        "things we lose while growing up, without noticing",
        "habits of people who are easy to love",
    ),
    "story": (
        "two people in an ordinary moment; one finally says the thing they never said",
        "an ordinary object that turns out to hold a whole memory",
        "a parent's odd habit that the child only understands years later",
        "someone waits a long time for something, and it arrives in a small way",
        "what looked like a small annoyance turns out to be love",
        "a younger self and an older self, one small moment apart",
    ),
    "oneliner": (
        "a specific, lasting good thing a lucky person has, then a two- or three-word verdict",
        "nobody talks about a small, true feeling everyone has had",
        "someone does a small thing for you and never mentions it; name that as love",
        "the best version of an everyday thing is a surprisingly small answer",
        "some people feel like a cosy everyday comparison",
    ),
}

BANNED = ("tapestry", "whisper", "whispers", "whispered", "sigh", "sighs", "sighed", "symphony",
          "journey", "embrace", "embraced", "testament", "delve", "vibrant", "cherish", "cherished",
          "gentle reminder", "softly", "the world felt", "in a world", "remember that",
          "it's okay to", "beacon", "navigate", "unspoken", "profound")


def banned_in(text: str) -> list[str]:
    text = plain(text).lower().replace("’", "'")
    return [word for word in BANNED if re.search(rf"\b{re.escape(word)}\b", text)]

SYSTEM = """You write posts for @suresilly, an easy-going Instagram page of tiny truths. \
A small green donkey sits on every slide, but it never speaks and is never mentioned.

The goal: a reader stops, feels seen, and sends the post to one specific person.

How the words should feel:
- all lowercase, including "i". simple, everyday english. short words, short lines.
- concrete beats abstract: name the object, the room, the time of day, the small action.
- talk to "you" or say "we". never preachy, never an advice column, never therapy-speak.
- universal: a 16-year-old and a 60-year-old should both nod.
- original lines only. never quote anyone. never name an author, book, celebrity or brand.
- no hashtags, emojis, links, em dashes or en dashes on the slides.
- never use these words: """ + ", ".join(BANNED) + """.
- you may wrap ONE key phrase in [[double brackets]] to highlight it, on at most 3 slides \
of the whole post. highlight the phrase a reader would underline, not decoration.

Formats:
- list: slide 1 is the list's title: an open loop under 12 words, no full stop, that makes \
someone need to see the items. then 6 or 7 slides, one item each: one standalone line under \
30 words that still works as a screenshot on its own. the last slide is a warm line about who \
to send it to or why to save it. 8 or 9 slides in total.
- story: 6 to 8 slides. slide 1 opens a small everyday moment and stops on a question or an \
unfinished beat, so the reader has to swipe. the middle slides move time forward, one or two \
sentences each. the second-last slide turns it. the last slide is one quotable line.
- oneliner: exactly 1 slide, under 25 words, with a small twist at the end.

First think of three different opening lines and pick the one a stranger would stop \
scrolling for. Put all three in "hook_options"; slide 1 must be the one you picked.

Caption: 2 to 4 short lines that add one new thought (never a repeat of the slides), then one \
plain call to action on its own line (send it to someone, save it, or tag someone), then 3 to \
5 lowercase hashtags.

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


EDITOR = SYSTEM + """

You are now the editor, not the writer. You get a draft post as JSON. Make it better:
- slide 1 must be something a stranger stops scrolling for. if it isn't, rewrite it or use a \
stronger line from hook_options.
- every line must make literal sense on first read. a reader must never have to guess what \
happened or why. fix any story whose logic has a gap.
- replace vague lines with concrete ones. cut anything that sounds like a greeting card.
- a oneliner must end on a small twist or a short verdict.
- keep the same format, the same number of slides (or trim a list item that is weak), and \
every rule above. reply with the improved post in the same JSON shape."""


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


def draw(fmt: str, seed: str) -> dict:
    rng = random.Random(seed)
    person = rng.choice(sorted(PEOPLE))
    return {"topic": PEOPLE[person], "person": person, "shape": rng.choice(SHAPES[fmt])}


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
               chat: Callable[[str, str], tuple[dict, str]] = chat_json) -> dict:
    if fmt not in FORMATS:
        raise WriteError(f"Unknown format {fmt!r}.")
    angle = draw(fmt, seed)
    previous = previous if previous is not None else previous_hooks()
    note = ""
    faults: list[str] = []
    for _ in range(3):
        user = (f"Format: {fmt}\nShape to use: {angle['shape']}\n"
                f"Who it is quietly about: {angle['person']}\n{note}Write it.")
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
