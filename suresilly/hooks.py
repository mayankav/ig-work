"""Hook techniques, one card each, and the picker that gives a post exactly one.

The full list with sources is `.agents/skills/suresilly-writer/references/hook-playbook.md`. A card says, in plain words a
small model can follow, how to fill the cover for that technique. A post gets one card, so the writer's prompt stays short
and no two posts in a row open the same way.
"""
from __future__ import annotations

from dataclasses import dataclass

AREAS = ("rights", "saythis", "newrule", "asked", "dictionary", "notbehind")


@dataclass(frozen=True)
class Hook:
    id: int                      # the number in the playbook
    name: str
    areas: tuple[str, ...]
    how: str                     # one instruction for the writer
    pattern: str                 # the cover, with the slots to fill
    promise: tuple[str, ...]     # lines that may stand as line 2


CARDS = (
    Hook(1, "calibrated info gap", ("rights", "newrule"),
         "Give two facts that do not add up. Hold back the reason. The reader must want the reason.",
         "{what they expected} / {what they got}", ("Where did the rest go?", "Do you know why?")),
    Hook(2, "forward reference", ("rights", "newrule"),
         "Say a clause, a rule or a line exists and that people skip it. Do not say what it says.",
         "{document} has one {thing} {who} skips.", ("This one.", "Here is which.")),
    Hook(3, "open loop", ("saythis",),
         "Show the message that arrives. Hold back the reply.",
         "{who} texted “{the exact message}.”", ("Say this first.", "Here is the reply.")),
    Hook(5, "redaction", ("dictionary", "rights"),
         "Write the sentence and hide the one number or word that matters with ____.",
         "{sentence with ____ where the answer goes}", ("Fill it in.", "Do you know it?")),
    Hook(6, "myth versus reality", ("rights", "asked"),
         "Quote the belief in quotation marks. Hold back the correction.",
         "“{the belief}”", ("Is it?", "Here is what is true.")),
    Hook(8, "negation", ("rights", "notbehind"),
         "Name something people are told they have and say it is not in the document.",
         "“{the promise}” is not in your {document}.", ("Here is what is.", "Here is what is there instead.")),
    Hook(9, "specific count", ("notbehind",),
         "Give a number of items and say only some matter. Do not list them.",
         "{a document} has {n} {parts}. Only {k} matter.", ("Here are the {k}.", "This one first.")),
    Hook(10, "stakes", ("newrule", "rights"),
         "Name the cost of missing one small thing. Hold back the fix.",
         "{one small miss} costs {what it costs}.", ("Check yours.", "Here is how to check.")),
    Hook(11, "audience callout", ("asked", "notbehind", "saythis"),
         "Name who this is for and one condition, so the right reader stops.",
         "{who you are} in {situation}?", ("Check one thing.", "Here is one thing to check.")),
    Hook(12, "time-boxed promise", ("rights",),
         "Name the question and a short time to answer it. Use only a time the post truly needs.",
         "{the question you can ask}", ("A {n}-second check.", "Check it in {n} seconds.")),
    Hook(13, "cold open", ("saythis",),
         "Start inside the moment: the message on the screen, no greeting, no setup.",
         "“{the message, word for word}”", ("Now what?", "Say this.")),
    Hook(17, "translation", ("dictionary", "asked"),
         "Quote the exact phrase. Hold back what it means.",
         "“{the phrase}”", ("What it really means.", "Here is what it means.")),
    Hook(18, "script as promise", ("saythis",),
         "Promise the exact words to send. The words themselves stay inside.",
         "The {n}-line text to {goal}.", ("Copy it.", "Here it is.")),
    Hook(21, "authority tag", ("rights", "newrule"),
         "Name the kind of source (a law, a clause, a court ruling) without its content.",
         "A {kind of source} most {people} never read.", ("Which one?", "Here is what it says.")),
    Hook(25, "awareness match", ("notbehind", "asked"),
         "Describe the symptom the reader already feels. Say it has a name or a cause.",
         "{the thing they feel}.", ("It has a name.", "Here is why.")),
)

BY_ID = {card.id: card for card in CARDS}


def pick(area: str, recent: list[int] | None = None, day: int = 0) -> Hook:
    """One card for this area. A card used in the last 6 posts is skipped; `day` rotates the choice so runs differ."""
    recent = list(recent or [])[-6:]
    pool = [card for card in CARDS if area in card.areas]
    if not pool:
        raise ValueError(f"no hook technique for the area {area!r}")
    fresh = [card for card in pool if card.id not in recent] or pool
    return fresh[day % len(fresh)]


def prompt_card(card: Hook) -> str:
    """The card as the writer reads it. It gives the shape of the idea, never a line to copy."""
    return (f"Hook technique for this post: {card.name}.\n"
            f"How: {card.how}\n"
            f"Shape of line 1: {card.pattern}\n"
            "Line 2: a promise, in your own 2 to 6 words, that the answer is coming. Never a line you have used before.")
