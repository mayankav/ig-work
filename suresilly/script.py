"""The Reel script: the words a model writes, the prompt that asks for them, and the check that decides if they are good enough.

Nothing the viewer reads is written by hand, and no prompt carries a sample to imitate: a model shown a sample writes copies of it.
A model proposes the topic (an office phrase, a work moment) and writes every word. The only fixed data are the sourced facts
(`facts.json`) that a rights Reel may state. Posts differ because the code deals each one a different set of constraints
(an area, a hook technique, a voice, a shape for the reply) and rejects any script too close to a recent post. One table
(`TEMPLATES`) drives the prompt and the check, so the spec a weak model reads and the rule that rejects its answer cannot drift
apart. A model never lays anything out and never writes a source line.

When no model passes the check within its tries, nothing is posted: the caller tells the owner in plain words and the slot is skipped.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from . import ROOT, hooks, lint

FACTS = json.loads((ROOT / "suresilly" / "facts.json").read_text())
FACT = {f["id"]: f for f in FACTS["facts"]}

BANNED = ("donkey", "follow", "tag a friend", "comment yes", "let that sink in", "double-tap", "game changer", "hustle", "delve",
          "unlock", "journey", "navigate", "landscape", "crucial", "ensure", "many think", "most people think", "actually", "unlike")
LAW_WORDS = ("law", "legal", "legally", "illegal", "court", "rights", "pf", "gratuity", "tax")
TIME = re.compile(r"\b\d{1,2}(:\d\d)?\s?(am|pm)\b", re.I)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
NUMBER_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
                "eleven": "11", "twelve": "12", "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
                "sixty": "60", "ninety": "90", "hundred": "100", "thousand": "1000", "lakh": "100000"}
PROMISE = re.compile(r"\b(here|below|next|inside|swipe|answer|reply|find|see|which|why|how|what|say|copy|check|read|watch)\b|[?]|_{3}", re.I)
CHAT_CHARS = 130        # the most two chat bubbles hold, measured with the layout audit
SENTENCE_FIELDS = ("law_says", "why", "reply_me", "hr_says", "boss_text", "caption", "payoff")


@dataclass(frozen=True)
class F:
    """One field the model writes."""
    name: str
    lo: int                 # fewest words
    hi: int                 # most words
    rule: str               # one sentence, plain words
    tag: str = ""           # the scene tag it appears under, for the completeness lint
    chars: int = 0          # most characters, where the screen cannot hold more (0 = no limit)
    part: str = "body"      # "body": the exchange, written first. "dress": cover, caption, written for the finished body


@dataclass(frozen=True)
class Template:
    name: str
    area: str               # the content area, for the hook picker
    scenes: str             # what the viewer sees, in order, so the model knows where its words go
    fields: tuple[F, ...]
    given: tuple[str, ...] = ()    # fields the idea supplies; the model must not write them


COVER = (
    F("cover_1", 1, 12, "Line 1 of the cover. Follow the hook technique's shape. It raises a question and does NOT contain the answer.", part="dress"),
    F("cover_2", 2, 6, "Line 2 of the cover: a short promise line from the hook technique. It never gives the answer.", part="dress"),
    F("payoff", 1, 20, "The answer the cover holds back, in your own words. It appears inside the Reel, never on the cover.", part="dress"),
    F("caption", 4, 28, "Two short sentences for the caption. The second adds one new thought. No hashtags, no follow line.", part="dress"),
)
KEY = F("key", 1, 1, "A number from 1 to 4: how many of the last words of the line above it to highlight.")

TEMPLATES = {
    "rights": Template(
        "rights", "rights",
        "Scene 1: HR says hr_says. Scene 2: the law says law_says. Scene 3: the source card (written by Python from the FACT). "
        "Scene 4: a chat where HR writes hr_says again and you answer with reply_me.",
        COVER + (
            F("hr_says", 3, 9, "What HR says: the belief people are told, as one plain sentence. No number unless the FACT has it.", chars=60),
            F("law_says", 5, 14, "What the rule says, in plain words, one sentence. Use only the FACT. Every number comes from the FACT.", "THE LAW SAYS"),
            KEY,
            F("reply_me", 8, 20, "The exact message the reader can send back. Real words, polite, one sentence. Never 'send a message'.", "SAY THIS", chars=100),
        )),
    "saythis": Template(
        "saythis", "saythis",
        "Scene 1: a message arrives, shown big with the tag `when`. Scene 2: a chat where the sender writes boss_text and you answer with reply_me. "
        "Scene 3: one line on why the reply works.",
        COVER + (
            F("when", 1, 4, "Who and when the message came."),
            F("boss_text", 3, 10, "The exact message that arrives. A real, short work message that fits the Situation.", chars=60),
            F("reply_me", 6, 16, "The exact reply the reader can send. Real words, polite, one or two short sentences, with a time or a question. Never 'send a message'.", "SAY THIS", chars=100),
            F("why", 4, 10, "One sentence on why the reply works. It names what the reply does, not a feeling.", "WHY IT WORKS"),
            KEY,
        ), given=("when",)),
    "dictionary": Template(
        "dictionary", "dictionary",
        "Scene 1: the phrase, shown big with the tag YOUR BOSS SAYS. Scene 2: a dictionary page with the phrase and its meaning. "
        "Scene 3: a chat where the boss writes boss_text and you answer with reply_me. Scene 4: one line on why the reply works.",
        COVER + (
            F("phrase", 1, 5, "The office phrase."),
            F("meaning", 2, 8, "What the phrase really means."),
            F("boss_text", 3, 10, "A sentence a boss would write that uses the phrase.", chars=60),
            F("reply_me", 6, 16, "The exact reply the reader can send. Real words, polite, one or two short sentences. Never 'send a message'.", "YOUR MOVE", chars=100),
            F("why", 4, 10, "One sentence on why the reply works. It names what the reply does, not a feeling.", "WHY IT WORKS"),
            KEY,
        ), given=("phrase", "meaning")),
    # The types made from the weekly plan (suresilly/reeltypes.py). Their words come from a plan entry, not from an idea the model proposes.
    "story": Template(
        "story", "saythis",
        "Scene 1: what happened, shown big (event). Scene 2: the detail that makes it matter (turn). Scene 3: what a young worker can do (move). "
        "Scene 4: the source card (written by Python from the FACT).",
        COVER + (
            F("event", 8, 22, "What happened, as one plain sentence. Only what the FACT block says. No name of a private person.", chars=120),
            F("turn", 6, 18, "The detail that makes it matter to a young worker, one sentence. Only what the FACT block supports.", chars=100),
            F("move", 8, 22, "What a young worker can do or say next, with the exact words if it is a message. This part is your own reasoning: practical and honest.",
              "WHAT YOU CAN DO", chars=110),
            KEY,
        )),
    "can_they": Template(
        "can_they", "asked",
        "Scene 1: a situation, shown big under the tag CAN THEY DO THIS (situation). Scene 2: the answer (answer). Scene 3: the source card (written by Python from the FACT). "
        "Scene 4: a chat where you send reply_me to the employer.",
        COVER + (
            F("situation", 5, 14, "A situation a young worker may face, as one plain sentence. The FACT block must cover it.", chars=80),
            F("answer", 6, 20, "What the FACT block says about it, in plain words. If it says it depends, say that. No advice, no prediction.", "THE ANSWER", chars=120),
            KEY,
            F("reply_me", 8, 20, "The exact message a worker could send to ask for what the rule gives them. Polite, one or two sentences. Never 'send a message'.",
              "SAY THIS", chars=100),
        )),
    "news": Template(
        "news", "newrule",
        "Scene 1: what changed, shown big (headline). Scene 2: what it changes for a young worker (changes). Scene 3: the source card (written by Python from the FACT). "
        "Scene 4: one thing to check this week (move).",
        COVER + (
            F("headline", 4, 12, "What changed, as a short plain headline. Only what the FACT block says.", chars=80),
            F("changes", 6, 20, "What it changes for a young worker, in plain words. Only what the FACT block supports.", chars=120),
            KEY,
            F("move", 6, 20, "One thing a worker can check or ask this week, with the exact words.", "CHECK THIS", chars=110),
        )),
    "contrast": Template(
        "contrast", "saythis",
        "Scene 1: the request both managers face (request). Scene 2: the pressuring manager writes pushy. Scene 3: the professional manager writes professional. "
        "Scene 4: one line on why the second works (why). Scene 5: a chat where you answer the first with reply_me.",
        COVER + (
            F("request", 5, 14, "The one request or situation both managers face, as one plain sentence.", chars=80),
            F("pushy", 3, 12, "What the pressuring manager writes. A real, short message of a real person, not a cartoon.", chars=70),
            F("professional", 4, 14, "What the professional manager writes for the same request. It gives a reason, a time or a real choice.", chars=80),
            F("why", 6, 16, "One sentence on the behaviour that makes the second better. It names what the manager does, not a feeling.", "WHY IT WORKS", chars=110),
            F("reply_me", 8, 20, "If the reader gets the first message, the exact reply they can send. Polite, one or two sentences. Never 'send a message'.",
              "SAY THIS", chars=100),
            KEY,
        )),
    "mirror": Template(
        "mirror", "saythis",
        "Scene 1: a message a manager sent (sent). Scene 2: how it lands on the junior who reads it (lands). Scene 3: what the manager could send instead (better). "
        "Scene 4: one line on why that works (why).",
        COVER + (
            F("sent", 3, 12, "A message a manager really sends, as one short line.", chars=70),
            F("lands", 6, 18, "How it lands on the junior who reads it: what they think and do next. Honest and specific, never melodramatic.", "HOW IT LANDS", chars=110),
            F("better", 4, 14, "What the manager could send instead. Real words.", "SAY THIS INSTEAD", chars=80),
            F("why", 6, 16, "One sentence on why that works. It names what the manager does, not a feeling.", "WHY IT WORKS", chars=110),
            KEY,
        )),
}
NEW = ("story", "can_they", "news", "contrast", "mirror")
CHAT_FIRST = ("hr_says", "boss_text", "pushy", "sent")    # the line a chat or message scene opens with, for the length check
ATTRIBUTION = ("research", "study", "studies", "survey", "according to", "experts", "scientists", "data shows", "statistics", "report says")


# ── ideas: the model proposes the topic ──────────────────────────────────────
IDEA_FIELDS = {
    "dictionary": (F("phrase", 1, 5, "An office phrase first-job readers in India have really heard, written exactly as people say it. Corporate speak or Indian office English, not slang."),
                   F("meaning", 2, 8, "What it really means. Starts with '= '. Short, honest, a little funny. Never an insult.")),
    "saythis": (F("when", 1, 4, "Who sends the message, a comma, then the time of day. Capital letters."),
                F("situation", 5, 16, "One sentence: what happens, so the reader must reply. A moment many first-job readers have lived: late work, an extra task, a deadline, feedback, credit, leave, a pushy colleague.")),
}


AREAS = {      # where to look for a topic. A direction, never a topic: the model supplies the topic.
    "dictionary": ("an email phrase", "a meeting phrase", "a deadline phrase", "a feedback phrase", "a phrase from the first week at a new job",
                   "a phrase from a team group chat", "a phrase a boss says on a call", "a phrase from hiring and onboarding",
                   "a phrase from Indian office English that people elsewhere do not use"),
    "saythis": ("a late-night message", "an extra task on a full week", "a deadline that moves", "feedback or criticism", "credit for your work",
                "time off or leave", "a meeting you did not want", "a colleague who leaves their work to you", "a request for an answer right now",
                "a polite no", "a message from HR", "a message from a client"),
}


def pick_area(template: str, day: int = 0, recent: list[str] | None = None) -> str:
    pool = AREAS[template]
    fresh = [a for a in pool if a not in (recent or [])[-4:]] or list(pool)
    return fresh[day % len(fresh)]


def ideas_prompt(template: str, recent: list[str], n: int = 6, area: str = "") -> tuple[str, str]:
    rows = "\n".join(f'- "{f.name}": {f.lo} to {f.hi} words. {f.rule}' for f in IDEA_FIELDS[template])
    system = (f"You find topics for short Instagram Reels for @suresilly. The readers are people in India, age 18 to 30, in their first job.\n"
              f"Reply with one JSON object: {{\"ideas\": [...]}} with {n} different ideas. Each idea has exactly these fields:\n{rows}\n\n"
              "Rules: no law, tax, money or HR-policy claim. Nothing about gender, religion, caste, region or a named person. "
              "Plain English, short words. The ideas must differ from each other. Choose what readers have really lived, "
              "not what sounds like a training slide. The honest, slightly funny truth beats a dictionary definition.")
    user = (f"Look in this area: {area or 'anywhere in a first job'}.\n"
            "Topics already used lately (do not repeat or rephrase): " + (", ".join(recent[-14:]) if recent else "none") + f".\nWrite {n} new ideas.")
    return system, user


def idea_problems(template: str, idea: dict, recent: list[str]) -> list[str]:
    found = []
    if not isinstance(idea, dict):
        return ["not an object"]
    for f in IDEA_FIELDS[template]:
        raw = idea.get(f.name)
        if not isinstance(raw, str) or not raw.strip():
            found.append(f'"{f.name}" is missing')
        elif not f.lo <= len(raw.split()) <= f.hi:
            found.append(f'"{f.name}" has {len(raw.split())} words; it must have {f.lo} to {f.hi}')
    if found:
        return found
    text = " ".join(str(idea[f.name]) for f in IDEA_FIELDS[template]).lower()
    for word in BANNED:
        if re.search(rf"\b{re.escape(word)}\b", text):
            found.append(f'the phrase "{word}" is not allowed')
    for word in LAW_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text):
            found.append(f'the word "{word}": no law, tax or money claims in a topic')
            break
    if template == "dictionary" and not idea["meaning"].strip().startswith("="):
        found.append('"meaning" must start with "= "')
    key = str(idea.get("phrase") or idea.get("situation")).lower().strip(" ?.!")
    if key in [r.lower().strip(" ?.!") for r in recent]:
        found.append("already used")
    return found


def ideate(template: str, call, recent: list[str] | None = None, n: int = 6, area: str = "") -> list[dict]:
    """Ask the model for topics; keep the ones that pass. `call(messages)` returns a dict. A bad idea is dropped, never raised."""
    recent = list(recent or [])
    system, user = ideas_prompt(template, recent, n, area)
    raw = call([{"role": "system", "content": system}, {"role": "user", "content": user}])
    items = raw.get("ideas", []) if isinstance(raw, dict) else []
    good, used = [], list(recent)
    for item in items:
        item = clean(template, item) if isinstance(item, dict) else item
        if not idea_problems(template, item, used):
            good.append({f.name: item[f.name] for f in IDEA_FIELDS[template]})
            used.append(item.get("phrase") or item.get("situation"))
    return good


def rank_ideas(template: str, ideas: list[dict], call) -> list[dict]:
    """Ask a model (ideally not the one that wrote them) to order the ideas best first. Falls back to the given order.

    The checks cannot see a flat meaning or a moment nobody has lived; a second reader can.
    """
    if len(ideas) < 2:
        return ideas
    listing = "\n".join(f"{i}. " + "; ".join(f"{k}: {v}" for k, v in idea.items()) for i, idea in enumerate(ideas))
    system = ("You judge topics for short Instagram Reels for people in India, age 18 to 30, in their first job. "
              "Order the topics from best to worst. A topic is better when: readers have really lived or heard it; it is honest and "
              "specific, a little funny, never a dictionary definition; a polite, exact reply can be written for it. "
              "A topic is worse when it is generic, wrong, or only sounds like a training slide. "
              'Reply with one JSON object: {"order": [numbers, best first]}.')
    try:
        raw = call([{"role": "system", "content": system}, {"role": "user", "content": listing}])
        order = []
        for i in raw.get("order", []):
            try:
                order.append(int(i))
            except (TypeError, ValueError):
                pass
    except Exception:
        return ideas
    seen = [i for n, i in enumerate(order) if 0 <= i < len(ideas) and i not in order[:n]]
    return [ideas[i] for i in seen] + [idea for n, idea in enumerate(ideas) if n not in seen]


# ── the second reader ────────────────────────────────────────────────────────
QUESTIONS = {
    "reply_fits": "Is reply_me a message the reader could send back to the sender, and does it answer what the sender wrote or asked? "
                  "Say no if it is a note to self, a comment about the topic, thanks only, or a promise to look into it.",
    "cover_fits": "Is the cover about this exact topic, and does the Reel deliver what the cover promises? "
                  "Say no if the cover is generic, about something else, or promises a number, a form or a script that the Reel does not give.",
    "faithful": "Is every claim true to the FACT, or, with no FACT, to the plain meaning of the phrase or situation? "
                "Say no if a line changes the FACT, adds to it, or contradicts it, or if the meaning is wrong or unkind.",
    "natural": "Would a person in an Indian office write these lines? Say no for stiff, robotic or textbook phrasing, "
               "or a line that makes no sense on its own.",
    "usable": "Could the reader send reply_me tomorrow, unchanged, in a real chat? Say no if it needs a name, a number or a fact the reader does not have.",
    "coherent": "Read the chat as a viewer who sees nothing else. Does the reply make sense as the answer to the message before it, and is it clear who is speaking? "
                "Say no if the reply answers a different question, if the roles are mixed up (the reply talks about the sender's screen, files or tabs as if they were the replier's, "
                "or the replier answers as if they were the one asking), or if it only makes sense with context the viewer cannot see.",
    "adds_value": "Does the reply make a move a viewer can copy, such as fixing a time, asking the one question that removes the guess, setting a limit, or putting it in writing? "
                  "Say no if it only agrees, repeats the request, or promises something vague. Say no if it commits the replier to something worse than the sender asked, "
                  "such as a later deadline than the sender set, with no reason given.",
    "consistent": "Do the cover, the phrase's meaning, the reply and the line on why it works agree with each other? "
                  "Say no if one contradicts another, or the line on why claims something the reply does not do.",
}
QUESTIONS.update({
    "coherent_story": "Read the Reel as a viewer who sees nothing else. Do the scenes follow each other and make sense, and is it clear who says what? "
                      "Say no if a scene answers a different question, repeats the one before, or only makes sense with context the viewer cannot see.",
    "grounded": "Does every statement about the world, a law, a number, a company or a person come from the FACT block? With no FACT block, does the Reel name no source, no study and no number? "
                "Say no if a line adds, changes or overstates what the FACT says.",
    "moves": "Does the Reel give the viewer something specific to do, say or check tomorrow, in exact words? Say no if it only informs or stays vague.",
    "fair": "Is the pressuring manager a realistic person and not a cartoon, and is the professional version something a real manager in India could write? "
            "Say no if the second is only politer, if the two answer different requests, or if the Reel insults a group.",
})
ASK = {"body": ("coherent", "reply_fits", "adds_value", "faithful", "natural", "usable"), "dress": ("cover_fits", "consistent", "natural")}   # what each step's reader is asked
ASKS = {"story": ("coherent_story", "grounded", "moves", "natural"), "can_they": ("coherent_story", "grounded", "moves", "natural"),
        "news": ("coherent_story", "grounded", "moves", "natural"), "contrast": ("coherent_story", "fair", "moves", "natural"),
        "mirror": ("coherent_story", "fair", "natural")}


def asks(template: str, part: str) -> tuple[str, ...]:
    return ("cover_fits", "consistent", "natural") if part == "dress" else ASKS.get(template, ASK["body"])


def about(template: str, seed: dict) -> str:
    """What the Reel is about, in one line or two, for a reader or a decision model."""
    if template == "rights":
        return "FACT: " + str(seed.get("claim", ""))
    if template == "saythis":
        return f"Situation: {seed.get('situation', '')} (sender and time: {seed.get('when', '')})"
    if template in NEW:
        fact = seed.get("fact")
        lesson = seed.get("lesson") or {}
        return (f"Topic: {seed.get('title', '')}. Angle: {seed.get('angle', '')}." + (f" Lesson: {lesson['angle']}." if lesson.get("angle") else "") +
                (" FACT: " + str(fact.get("claim", "")) if fact else " No FACT: it is our own reasoning and names no source."))
    return f"Office phrase: {seed.get('phrase', '')}; its meaning: {seed.get('meaning', '')}"


def viewer_text(template: str, data: dict) -> str:
    """The Reel as a viewer sees it, scene by scene, with nothing the viewer cannot see."""
    cover = f"{data.get('cover_1', '')} / {data.get('cover_2', '')}".strip(" /")
    if template == "rights":
        scenes = [f"Scene 1, HR says: {data.get('hr_says', '')}", f"Scene 2, the law says: {data.get('law_says', '')}", "Scene 3: a source card.",
                  f"Scene 4, chat: HR writes: {data.get('hr_says', '')} / You reply: {data.get('reply_me', '')}"]
    elif template == "saythis":
        scenes = [f"Scene 1, a message arrives ({data.get('when', '')}): {data.get('boss_text', '')}",
                  f"Scene 2, chat: {data.get('when', 'Sender').split(',')[0].title()} writes: {data.get('boss_text', '')} / You reply: {data.get('reply_me', '')}",
                  f"Scene 3, why it works: {data.get('why', '')}"]
    elif template == "story":
        scenes = [f"Scene 1, what happened: {data.get('event', '')}", f"Scene 2, why it matters: {data.get('turn', '')}",
                  f"Scene 3, what you can do: {data.get('move', '')}", "Scene 4: a source card, written by the system from the FACT, showing the FACT's own source. It is not part of the lines."]
    elif template == "can_they":
        scenes = [f"Scene 1, can they do this: {data.get('situation', '')}", f"Scene 2, the answer: {data.get('answer', '')}", "Scene 3: a source card, written by the system from the FACT, showing the FACT's own source.",
                  f"Scene 4, chat: You write: {data.get('reply_me', '')}"]
    elif template == "news":
        scenes = [f"Scene 1, what changed: {data.get('headline', '')}", f"Scene 2, what it changes for you: {data.get('changes', '')}", "Scene 3: a source card, written by the system from the FACT, showing the FACT's own source.",
                  f"Scene 4, check this: {data.get('move', '')}"]
    elif template == "contrast":
        scenes = [f"Scene 1, the request: {data.get('request', '')}", f"Scene 2, the pressuring manager writes: {data.get('pushy', '')}",
                  f"Scene 3, the professional manager writes: {data.get('professional', '')}", f"Scene 4, why it works: {data.get('why', '')}",
                  f"Scene 5, chat: You answer the first with: {data.get('reply_me', '')}"]
    elif template == "mirror":
        scenes = [f"Scene 1, a manager sent: {data.get('sent', '')}", f"Scene 2, how it lands: {data.get('lands', '')}",
                  f"Scene 3, say this instead: {data.get('better', '')}", f"Scene 4, why it works: {data.get('why', '')}"]
    else:
        scenes = [f"Scene 1, the boss says: {data.get('phrase', '')}", f"Scene 2, dictionary: {data.get('phrase', '')} {data.get('meaning', '')}",
                  f"Scene 3, chat: Boss writes: {data.get('boss_text', '')} / You reply: {data.get('reply_me', '')}",
                  f"Scene 4, why it works: {data.get('why', '')}"]
    return (f"Cover shown on the profile grid: {cover}\n" if cover else "") + "\n".join(scenes) + (f"\nCaption: {data['caption']}" if data.get("caption") else "")


def judge_prompt(template: str, seed: dict, data: dict, which: tuple[str, ...] = tuple(QUESTIONS)) -> tuple[str, str]:
    questions = "\n".join(f'- "{k}": {QUESTIONS[k]}' for k in which)
    shape = ", ".join(f'"{k}": {{"ok": true, "fix": ""}}' for k in which)
    system = ("You are a strict editor for short Instagram Reels for people in India, age 18 to 30, in their first job. "
              "You are shown a Reel exactly as a viewer sees it. First write \"story\": one sentence on what happens in the Reel and what the viewer learns. "
              "If the story does not make sense, say so there. Then answer each question with true or false and, when false, one short sentence (under 20 words) "
              "that says what is wrong. Never write a replacement line or a sample: the writer must find its own words. "
              "Be strict: a generic, flat or confusing line is a no.\n"
              f"Questions:\n{questions}\nReply with one JSON object: {{\"story\": \"...\", {shape}}}.")
    return system, about(template, seed) + "\n\nThe Reel:\n" + viewer_text(template, data)


def judge(template: str, seed: dict, data: dict, call, which: tuple[str, ...] = tuple(QUESTIONS)) -> list[str]:
    """Problems a chat model found as a second reader, in plain words. Empty when it found none. A reader that fails finds nothing."""
    system, user = judge_prompt(template, seed, data, which)
    try:
        raw = call([{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception:
        return []
    found = []
    for key in which:
        row = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(row, dict) and row.get("ok") is False:
            found.append(f"{key.replace('_', ' ')}: {str(row.get('fix') or 'a second reader said no').strip()}")
    return found


def llm_reader(call):
    """A reader that asks a chat model. Gives the writer a sentence on what to change."""
    return lambda template, seed, data, which: judge(template, seed, data, call, which)


CLEF_BELOW = 0.4    # a decision model's probability under this is a no (measured 2026-10-06: catches 9 of 12 bad scripts, flags 3 of 12 good)


def clef_reader(post, below: float = CLEF_BELOW):
    """A reader that asks a decision model (Cloudflare's Clef). `post(body) -> {question: probability_true}`.

    Cheap, one call, and the cut-off is a dial. It returns only a number, so the writer is told the question it failed, not a fix.
    """
    def read(template: str, seed: dict, data: dict, which: tuple[str, ...]) -> list[str]:
        topic = about(template, seed)
        body = {"state": {"topic": topic, "reel_as_the_viewer_sees_it": viewer_text(template, data)},
                "questions": {k: {"type": "noul", "instructions": QUESTIONS[k]} for k in which}}
        try:
            answers = post(body)
        except Exception:
            return []
        return [f"{k.replace('_', ' ')}: a second reader scored this {p:.2f} out of 1. Check: {QUESTIONS[k]}"
                for k, p in answers.items() if k in which and isinstance(p, (int, float)) and p < below]
    return read


IDEA_QUESTIONS = {
    "lived": "Have first-job readers in India really lived or heard this?",
    "honest": "Is it honest and specific, a little funny, and not a dictionary definition or a training-slide line?",
    "reply": "Could a polite, exact reply be written for it that a reader would actually send?",
}


def clef_rank_ideas(post, template: str, ideas: list[dict]) -> list[dict]:
    """Order ideas best first by a decision model's average probability over three questions. Keeps the given order on any failure."""
    if len(ideas) < 2:
        return ideas
    scored = []
    try:
        for n, idea in enumerate(ideas):
            answers = post({"state": {"topic": idea}, "questions": {k: {"type": "noul", "instructions": q} for k, q in IDEA_QUESTIONS.items()}})
            scored.append((sum(answers[k] for k in IDEA_QUESTIONS) / len(IDEA_QUESTIONS), -n, idea))
    except Exception:
        return ideas
    return [idea for _, _, idea in sorted(scored, key=lambda row: (row[0], row[1]), reverse=True)]


# ── what each post is dealt: constraints that make posts differ ──────────────
VOICES = (("dry", "Dry and short. Understate. No exclamation marks."),
          ("warm", "Warm, like an older cousin who has been through it."),
          ("playful", "Playful: one light joke, never at the reader's cost."),
          ("matter-of-fact", "Matter of fact, like a checklist read aloud."))
SHAPES = (("time", "reply_me offers a time or a date."),
          ("question", "reply_me asks one clear question back."),
          ("limit", "reply_me agrees to part of it and names the limit."),
          ("confirm", "reply_me says the task back in your own words, to confirm it."))


def deal(day: int, recent: list[tuple[str, str]] | None = None) -> tuple[tuple[str, str], tuple[str, str]]:
    """A voice and a reply shape for this post; neither is one of the last three used. `recent` holds (voice, shape) names."""
    voices = [v for v in VOICES if v[0] not in [r[0] for r in (recent or [])[-3:]]] or list(VOICES)
    shapes = [x for x in SHAPES if x[0] not in [r[1] for r in (recent or [])[-3:]]] or list(SHAPES)
    return voices[day % len(voices)], shapes[(day // 2 + day) % len(shapes)]


# ── the prompts: two small jobs, the body first, then the cover written for it ─
COMMON = """You write the words for a short Instagram Reel for @suresilly. The readers are people in India, age 18 to 30, in their first job. Be warm, plain and exact. Reply with one JSON object and nothing else.

Rules for every field:
1. Plain English. Short words. Sentences under 14 words. Write like one friend to one friend.
2. Every instruction carries its exact words. Never write "send a message" or "say something": write the message itself.
3. Only the FACT block may supply a law, a rule, a number, a date or a name. With no FACT block, state no law, tax or money rule at all.
4. Every number you write must be copied from the FACT block. Times of day are fine in a reply.
5. No emojis, hashtags, links, dashes or quotation marks around a field.
6. Never write these words: {banned}.
7. Write your own words, fresh for this topic. No stock phrases."""
COVER_RULE = ("The cover is a hook. cover_1 raises a question or a conflict about this exact topic. cover_2 is a short promise line. Neither may contain the answer, "
              "and the Reel body below must deliver everything the cover promises. Never promise a number, a form or a script that the body does not have.")


def _rows(fields) -> str:
    return "\n".join(f'- "{f.name}": {f.lo} to {f.hi} words' + (f", at most {f.chars} characters" if f.chars else "") + f". {f.rule}" for f in fields)


def system_prompt(template: str, hook: hooks.Hook, voice: tuple[str, str] = VOICES[0], shape: tuple[str, str] = SHAPES[0], part: str = "body") -> str:
    t = TEMPLATES[template]
    asked = [f for f in t.fields if f.name not in t.given and f.part == part]
    rules = COMMON.format(banned=", ".join(BANNED))
    if part == "dress":
        return (rules + "\n\n" + COVER_RULE + "\n\n" + hooks.prompt_card(hook) + f"\n\nVoice for this post: {voice[1]}\n\n"
                f"Fields to write, exact names (write only these):\n{_rows(asked)}")
    shape_line = f"\nShape of the reply: {shape[1]}" if any(f.name == "reply_me" for f in asked) else ""
    return (rules + f"\n\nVoice for this post: {voice[1]}{shape_line}\n\n"
            f"What the viewer sees: {t.scenes}\n\nFields to write, exact names (write only these):\n{_rows(asked)}")


def new_about(template: str, seed: dict) -> str:
    """The topic block for a type made from the weekly plan, then either the FACT it may state or the rule for reasoning without one."""
    lesson = seed.get("lesson") or {}
    lines = {"story": f"Item the Reel retells: {seed['title']}\nTakeaway to aim for (your own reasoning, change it if you see a better one): {seed.get('angle', '')}",
             "can_they": f"Question the Reel answers: {seed['title']}\nWhat the viewer needs to know: {seed.get('angle', '')}",
             "news": f"News the Reel explains: {seed['title']}\nWhat the viewer needs to know: {seed.get('angle', '')}",
             "contrast": f"Pressure at work: {seed['title']}\nProfessional behaviour to show: {lesson.get('angle') or seed.get('angle', '')}",
             "mirror": f"Pressure at work: {seed['title']}\nProfessional behaviour to show: {lesson.get('angle') or seed.get('angle', '')}"}[template]
    fact = seed.get("fact")
    if fact:
        keys = ("claim", "source", "source_date", "law", "caveat")
        grounding = "FACT (the only facts you may state about the world, a company or a person):\n" + "\n".join(f"{k}: {fact[k]}" for k in keys if fact.get(k))
        if fact.get("status") != "checked":
            grounding += "\nsay this is reported by the source, never that it is official"
    else:
        grounding = ("No FACT block. This Reel is your own reasoning about how people behave at work. State no law, tax or money rule and no number except a time. "
                     "Name no source: never write research, study, survey, experts or according to.")
    return (lines + "\n\n" + grounding + "\nName no private person. Name a company only if the FACT block names it."
            "\nAnything you add that the FACT block does not say is your own view: mark it with words like it may, it can, or worth asking, and never state it as a fact."
            "\nSpeak to the viewer as you. Never claim an experience of your own: no I, my or me in the cover or the caption, and no made-up person who told or texted you.")


def user_prompt(template: str, seed: dict, body: dict | None = None) -> str:
    if template == "rights":
        keys = ("claim", "source", "source_date", "law", "caveat")
        about = "FACT (the only facts you may state):\n" + "\n".join(f"{k}: {seed[k]}" for k in keys if seed.get(k))
    elif template in NEW:
        about = new_about(template, seed)
    elif template == "saythis":
        about = (f"Situation: {seed['situation']}\nGiven (do not write it): when = {seed['when']}\n\n"
                 "No FACT block: state no law, tax or money rule.")
    else:
        about = (f"Office phrase: {seed['phrase']}\nIts meaning: {seed['meaning']}\n\nNo FACT block: state no law, tax or money rule. "
                 "Do not write the phrase or its meaning again.")
    if body is None:
        return about + "\n\nWrite the Reel body for this."
    return about + "\n\nThe finished Reel body (read it, do not change it):\n" + json.dumps(body, ensure_ascii=False) + "\n\nWrite the cover and the rest for this body."


def repair_prompt(problems: list[str]) -> str:
    listing = "\n".join(f"- {p}" for p in problems)
    return ("Your last reply had these problems:\n" + listing +
            "\nWrite the whole JSON object again. Fix only these problems. Keep every field that was fine. Reply with JSON only.")


# ── the check ─────────────────────────────────────────────────────────────────
def _numbers(text: str) -> set[str]:
    """The numbers in a text, written as digits or as words ("two" is "2"). "one" is skipped: it is mostly a pronoun."""
    found = {m.replace(",", "") for m in NUMBER.findall(text)}
    return found | {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in NUMBER_WORDS}


def _plain(value: str) -> str:
    return value.strip().strip("\"'“”‘’").strip()


def check(template: str, data: dict, fact: dict | None = None, hook: hooks.Hook | None = None, recent: list[dict] | None = None,
          fields: set[str] | None = None) -> list[str]:
    """Every problem found in a model's answer, in plain words. An empty list means it may be built.
    `fact` is the FACT a rights Reel may state; the other templates have none, so they state no law, tax or money rule.
    `recent` holds the last scripts that were posted; a script too close to one of them fails.
    `fields` limits the check to one step's fields (the body, then the dress); None checks the whole script."""
    t = TEMPLATES[template]
    if not isinstance(data, dict):
        return ["the reply is not a JSON object"]
    scope = {f.name for f in t.fields} if fields is None else set(fields)
    found: list[str] = []
    values: dict[str, str] = {}
    for f in t.fields:
        raw = data.get(f.name)
        if f.name == "key":
            if "key" in scope and raw not in (1, 2, 3, 4, "1", "2", "3", "4"):
                found.append('"key" must be 1, 2, 3 or 4')
            continue
        if f.name not in scope and f.name not in data:
            continue
        if not isinstance(raw, str) or not raw.strip():
            if f.name in scope:
                found.append(f'the field "{f.name}" is missing')
            continue
        values[f.name] = raw.strip()
        if f.name in t.given or f.name not in scope:
            continue
        n = len(raw.split())
        if n < f.lo or n > f.hi:
            found.append(f'"{f.name}" has {n} words; it must have {f.lo} to {f.hi}')
        elif f.chars and len(raw.strip()) > f.chars:
            found.append(f'"{f.name}" has {len(raw.strip())} characters; at most {f.chars} fit on the screen: use shorter words')
    extra = [k for k in data if k not in {f.name for f in t.fields}]
    if extra:
        found.append("these fields are not in the spec, remove them: " + ", ".join(extra))
    if any("is missing" in p for p in found):
        return found

    first = next((values[k] for k in CHAT_FIRST if k in values), "")
    chat = len(first) + len(values.get("reply_me", ""))
    if chat > CHAT_CHARS:
        found.append(f"the chat has {chat} characters in all; at most {CHAT_CHARS} fit on the screen: shorten reply_me")
    written = {k: v for k, v in values.items() if k in scope and k not in t.given}   # what the model wrote in this step
    text = " ".join(written.values())
    low = text.lower()
    for word in BANNED:
        if re.search(rf"\b{re.escape(word)}\b", low):
            found.append(f'the phrase "{word}" is not allowed')
    if re.search(r"[#@]|https?://|www\.", text):
        found.append("no hashtags, mentions or links")
    if any(unicodedata.category(c) == "So" for c in text.replace("₹", "")):
        found.append("no emojis")
    if re.search(r"[—–]", text):
        found.append("no dashes: use a full stop or a comma")

    # facts: numbers and law words
    allowed = _numbers(" ".join(str(fact.get(k, "")) for k in ("claim", "caveat", "law", "title", "source_date"))) if fact else set()
    for name, value in written.items():
        times = {n for m in TIME.finditer(value) for n in _numbers(m.group(0))}
        small = set() if (fact or template in NEW) else {n for n in _numbers(value) if n.isdigit() and int(n) <= 59 and "₹" not in value}
        bad = sorted(n for n in _numbers(value) if n not in allowed and n not in times and n not in small)
        if bad:
            found.append(f'"{name}" has the number {", ".join(bad)}, which is not in the FACT: remove it or use a number from the FACT')
    if template in NEW:
        for name in ("cover_1", "cover_2", "caption"):
            if name in written and re.search(r"\b(i|i'm|i've|i'd|my|mine|me)\b", written[name].lower()):
                found.append(f'"{name}" speaks as "I" or "my": speak to the viewer as you, and claim no experience of your own')
    if not fact and template in NEW:
        for word in ATTRIBUTION:
            if re.search(rf"\b{re.escape(word)}\b", low):
                found.append(f'the word "{word}": there is no source, so name none: write your own reasoning, not "research shows"')
                break
    if not fact:
        for word in LAW_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", low):
                found.append(f'the word "{word}": there is no FACT for this topic, so state no law, tax or money rule')
                break

    # completeness: every instruction has its exact words
    for f in t.fields:
        if f.name in written:
            if f.tag:
                found += [f'"{f.name}": {p}' for p in lint.incomplete(f.tag, written[f.name])]
            if f.name not in ("payoff", "caption"):
                found += [f'"{f.name}": {p}' for p in lint.incomplete("", written[f.name]) if p.startswith("vague")]

    # the cover is a hook
    if "cover_1" in scope:
        cover = f"{values.get('cover_1', '')} {values.get('cover_2', '')}"
        promised = bool(PROMISE.search(values.get("cover_2", "")))      # line 2 is a promise that the answer follows
        found += [f"the cover: {p}" for p in lint.cover_problems(cover, []) if not promised or "leaves no gap" not in p]
        if fact:   # the numbers the law states that HR's line does not are the answer; they stay off the cover
            answer = _numbers(fact["claim"]) - _numbers(values.get("hr_says", ""))
            for n in sorted(answer & _numbers(cover)):
                found.append(f"the cover gives away the number {n}, which belongs inside the Reel")
        pay = values.get("payoff", "")
        if pay and pay.lower().strip(" .") in cover.lower():
            found.append("the cover contains the payoff")
        if values.get("cover_1", "").strip().lower() == values.get("cover_2", "").strip().lower():
            found.append("cover_1 and cover_2 are the same")
        for n in sorted(_numbers(values.get("cover_1", "")) & _lines_promised(values)):   # "3-line text" needs three lines in the body
            found.append(f"the cover promises {n} lines but the reply has fewer")

    # not a copy of a recent post
    for old in recent or []:
        found += similar(written, old)
    return found


def _lines_promised(values: dict) -> set[str]:
    """Numbers the cover promises as lines or steps that the body does not have: '3-line text' with a one-line reply."""
    cover = values.get("cover_1", "").lower()
    asked = {m for m in re.findall(r"(\d+)[- ](?:line|step|point|word)s?", cover)}
    have = len(re.findall(r"[.?!]", values.get("reply_me", "")))
    return {n for n in asked if int(n) > max(have, 1)}


def _grams(text: str) -> set[tuple[str, str]]:
    words = re.findall(r"[a-z0-9₹']+", text.lower())
    return set(zip(words, words[1:])) or {(w, "") for w in words}


def similar(new: dict, old: dict) -> list[str]:
    """Where `new` is too close to a recent script: the same line, or most of the same word pairs."""
    found = []
    for name in ("cover_1", "cover_2", "reply_me", "why", "hr_says", "boss_text", "law_says", "caption", "event", "turn", "move", "situation", "answer",
                 "headline", "changes", "request", "pushy", "professional", "sent", "lands", "better"):
        a, b = str(new.get(name, "")), str(old.get(name, ""))
        if not a or not b:
            continue
        if _plain(a).lower().strip(" .") == _plain(b).lower().strip(" ."):
            found.append(f'"{name}" repeats a recent post word for word: write something different')
        elif len(a.split()) >= 5:
            ga, gb = _grams(a), _grams(b)
            if ga and gb and len(ga & gb) / len(ga | gb) >= 0.5:
                found.append(f'"{name}" is too close to a recent post: use other words and another shape')
    return found


def clean(template: str, data: dict) -> dict:
    """Quietly fix what nobody would call a mistake: wrapping quotes, stray spaces, a hyphen the font lacks, a missing full stop."""
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            v = re.sub(r"\s+", " ", v.replace("‑", "-").replace("‐", "-")).strip()
            if k not in ("cover_1", "cover_2"):
                v = _plain(v)
            if k in SENTENCE_FIELDS and v:
                v = v[0].upper() + v[1:]
                if v[-1] not in ".?!":
                    v += "."
        out[k] = v
    if "key" in out:
        try:
            out["key"] = int(out["key"])
        except (TypeError, ValueError):
            pass
    return out


def write(template: str, seed: dict, call, recent: list[dict] | None = None, day: int = 0, repairs: int = 2,
          extra_check=None, reader=None) -> tuple[dict, dict]:
    """Write one script in two small steps, the body (the exchange) and then the dress (cover, caption) for that body.

    Each step asks `call(messages)` for a dict, checks it, and asks again with the problems if it fails. `seed` is the FACT for a
    rights Reel, or the idea (`ideate`) for the other two. `recent` is the last posted scripts, each with the keys "hook", "voice"
    and "shape" that its own report gave, so this post is dealt something else. `messages` is the chat so far:
    [{"role": "system" | "user" | "assistant", "content": str}, ...].
    `extra_check(script) -> list[str]` runs on the finished script, for the one thing only the renderer knows: does it fit.
    `reader(template, seed, data, which) -> list[str]` is a second reader (`llm_reader`, `clef_reader`; ideally not the writer's model) that reads each step and says what a check cannot see.
    Returns (script, report). `report["problems"][-1]` is empty when the script passed. When it is not, the caller must not post:
    it says why in plain words and skips the slot. There is no stock script to fall back on.
    """
    t = TEMPLATES[template]
    fact = seed if template == "rights" else (seed.get("fact") if template in NEW else None)
    recent = recent or []
    hook = hooks.pick(t.area, [r.get("hook") for r in recent if r.get("hook")], day)
    voice, shape = deal(day, [(r.get("voice", ""), r.get("shape", "")) for r in recent])
    given = {k: seed[k] for k in t.given if k in seed}
    report = {"hook": hook.id, "voice": voice[0], "shape": shape[0], "tries": 0, "problems": [], "steps": {}}

    def step(part: str, body: dict | None) -> tuple[dict, bool]:
        names = {f.name for f in t.fields if f.part == part and f.name not in t.given}
        messages = [{"role": "system", "content": system_prompt(template, hook, voice, shape, part)},
                    {"role": "user", "content": user_prompt(template, seed, body)}]
        mine: dict = {}
        for attempt in range(repairs + 1):
            report["tries"] += 1
            report["steps"][part] = attempt + 1
            mine = {k: v for k, v in clean(template, call(messages)).items() if k in names or k not in {f.name for f in t.fields}}
            data = {**given, **(body or {}), **mine}
            problems = check(template, data, fact, hook, recent, fields=names)
            if not problems and part == "dress" and extra_check:
                problems = extra_check(data)
            if not problems and reader:
                problems = reader(template, seed, data, asks(template, part))
            report["problems"].append(problems)
            if not problems:
                return mine, True
            messages += [{"role": "assistant", "content": json.dumps(mine, ensure_ascii=False)}, {"role": "user", "content": repair_prompt(problems)}]
        return mine, False

    body, ok = step("body", None)
    if not ok:
        return {**given, **body}, report
    dress, ok = step("dress", {**given, **body})
    return {**given, **body, **dress}, report
