"""Two small copy lints for the first-job posts. Neither judges meaning; they catch the failures the owner has already seen.

`incomplete`: a scene or slide that tells the reader to do something must carry the exact words in the same place.
`cover_problems`: a cover is a hook, so it must leave a gap and must not print the post's own payoff.
Both return a list of plain-words problems; an empty list means nothing was caught.
"""
from __future__ import annotations

import re

ACTION_TAGS = {"YOUR MOVE", "CHECK THIS", "ASK THIS", "SAY THIS", "SEND THIS", "THE ANSWER", "SO", "ASK THIS BEFORE YOU SIGN", "WHY IT WORKS"}
VAGUE = ("one line", "a line", "a message", "something", "stuff", "etc", "and so on", "a few words", "the thing", "that thing")
IMPERATIVE = re.compile(r"^(ask|say|send|write|tell|check|set|read|look|open|find|keep|try|use|call|mail|email|reply|do|go)\b", re.I)
GAP_MARKERS = ("?", "___", "(typing)", "here is", "here’s", "here's", "inside", "we checked", "which one", "different number",
               "what it really means", "not in your", "say this", "copy it")


def incomplete(tag: str, text: str) -> list[str]:
    """Instructions without their exact words, and vague stand-ins, in a scene or slide with an action tag."""
    found = []
    low = text.lower()
    for phrase in VAGUE:
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            found.append(f"vague phrase “{phrase}”: say what it is")
    if tag.upper() in ACTION_TAGS:
        for sentence in re.split(r"(?<=[.?!])\s+", text.strip()):
            if (IMPERATIVE.match(sentence.strip()) and len(sentence.split()) <= 9
                    and not re.search(r"[“\"]", sentence) and ":" not in sentence):
                found.append(f"an instruction without its exact words: “{sentence.strip()}”")
    return found


def cover_problems(cover: str, payoffs: list[str]) -> list[str]:
    """A cover that prints a payoff, or leaves no gap. `cover` is every word a stranger can read on it."""
    low = cover.lower()
    found = [f"the cover gives away “{p}”, which belongs inside the post" for p in payoffs if p and p.lower() in low]
    if not any(marker in low for marker in GAP_MARKERS):
        found.append("the cover leaves no gap: it needs a question, a blank, a hidden answer or a promise like “Here is how.”")
    return found
