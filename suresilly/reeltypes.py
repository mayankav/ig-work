"""Reel types, and the plan that gives each stock item a type and a slot.

A type is a shape for what the viewer gets, not content: its description is an instruction to the writer, never a sample. A model says
which types an item can honestly become (it reads the item and its angle); code then deals them out so that no type repeats in a row,
no type takes more than its share of the week, and last week's types are remembered. A type that states a fact (`needs_official`) is
flagged for the fact check unless the item already comes from an official site.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from urllib.parse import urlparse

from . import STATE, inbox

PLAN_FILE = STATE / "plan.json"


@dataclass(frozen=True)
class ReelType:
    id: str
    name: str
    gives: str                  # what the viewer gets; read by the model that matches items to types
    needs_official: bool = False


TYPES = (
    ReelType("contrast", "Two managers, one request",
             "The viewer sees one request handled by a pressuring manager and by a professional one, and learns what makes the second work."),
    ReelType("can_they", "Can they do this?",
             "A situation at work and whether an employer may do it, answered from an official source the viewer can check.", needs_official=True),
    ReelType("story", "Real story, retold",
             "A real situation from the news or a public post, retold in our own words with no names, ending in what the viewer can do or learn."),
    ReelType("mirror", "Manager's mirror",
             "How a manager's words or habit land on the junior who receives them, so a junior can forward it and a manager can learn from it."),
    ReelType("news", "News reaction",
             "Something new this week, such as a rule or an event, and what it changes for a young worker.", needs_official=True),
)
BY_ID = {t.id: t for t in TYPES}
SLOTS = inbox.SLOTS_A_WEEK


MANAGER_TYPES = ("contrast", "mirror")      # lessons for and about managers: built from a situation plus a lesson, not from a fact
MANAGER_SLOTS = 3                            # a week keeps at least this many of them when items allow


def fit_prompt(items: list[dict], lessons: list[dict] | None = None) -> tuple[str, str]:
    kinds = "\n".join(f"- {t.id}: {t.gives}" for t in TYPES)
    listing = "\n".join(f"{n}. {item['title']} | angle: {item.get('angle', '')}" for n, item in enumerate(items))
    if lessons:
        listing += "\n\nLessons about managers, from research and from people who manage:\n" + "\n".join(
            f"L{n}. {lesson.get('angle', lesson['title'])} ({lesson.get('story_kind', 'other')})" for n, lesson in enumerate(lessons))
    system = ("You plan short Reels for a page for people in India, age 18 to 30, at the start of their working life. "
              "These are the Reel types and what the viewer gets from each:\n" + kinds + "\n\n"
              "For every item, name the types it can honestly become, best first: zero, one, two or three ids. "
              "A type fits only if the item really gives what that type needs; leave a type out when you would have to invent something. "
              "Two types, contrast and mirror, are lessons and not facts: an item fits them when it shows or implies a pressure at work or a manager's habit, "
              "even if it is not about a manager, and you can pair it with one of the lessons listed. Then give that lesson's number in \"lesson\". "
              "Use each lesson for at most one item. For every other type, \"lesson\" is null. "
              "Say in \"why\" in about 8 words of your own what the Reel would show. "
              "Answer with one JSON object: {\"items\": [{\"i\": number, \"types\": [string], \"lesson\": number or null, \"why\": string}]} "
              "with one entry for every item.")
    return system, "Items:\n" + listing


def official(item: dict) -> bool:
    host = (urlparse(item.get("link", "")).hostname or "").removeprefix("www.")
    return any(host == d or host.endswith("." + d) for d in inbox.SOURCES.get("official_domains", []))


def fits(items: list[dict], call, lessons: list[dict] | None = None) -> list[dict]:
    """Each item with `types` (valid ids, best first), `why` and, for contrast or mirror, the `lesson` it pairs with.

    A failed or garbled answer gives no types, so the item is not planned. A contrast or mirror with no valid lesson is dropped.
    """
    out = []
    for start in range(0, len(items), 20):
        chunk = items[start:start + 20]
        system, user = fit_prompt(chunk, lessons)
        try:
            answer = call([{"role": "system", "content": system}, {"role": "user", "content": user}])
        except Exception:  # noqa: BLE001 - one failed call leaves these items unplanned
            answer = None
        rows = {}
        for row in answer.get("items", []) if isinstance(answer, dict) else []:
            try:
                rows[int(row["i"])] = row
            except (KeyError, TypeError, ValueError):
                continue
        for n, item in enumerate(chunk):
            row = rows.get(n, {})
            ids = [t for t in (row.get("types") or []) if t in BY_ID]
            number = row.get("lesson")
            lesson = lessons[number] if lessons and isinstance(number, int) and 0 <= number < len(lessons) else None
            if lesson is None:
                ids = [t for t in ids if t not in MANAGER_TYPES]
            out.append({**item, "types": list(dict.fromkeys(ids)), "why": str(row.get("why", ""))[:100],
                        **({"lesson": {k: lesson[k] for k in ("title", "link", "source", "angle") if k in lesson}} if lesson else {})})
    return out


def plan(stock: list[dict], call, history: list[str] | None = None, slots: int = SLOTS, lessons: list[dict] | None = None,
         used_lessons: list[str] | None = None) -> list[dict]:
    """Up to `slots` Reels: {slot, type, item, why, fact_check}. Best items first; each type takes at most its share; no type twice in a row."""
    history = history or []
    cap = math.ceil(slots / len(TYPES)) + 1
    used = {t.id: 0 for t in TYPES}
    taken = set(used_lessons or [])      # a lesson is used once: not twice in a week, and not again for a while
    chosen, planned = [], sorted(fits(stock, call, lessons), key=lambda i: -i.get("score", 0))
    for item in planned:        # first the manager-side Reels, so the week keeps its share of them
        manager = [t for t in item["types"] if t in MANAGER_TYPES]
        link = item.get("lesson", {}).get("link")
        if manager and link not in taken and sum(used[t] for t in MANAGER_TYPES) < MANAGER_SLOTS and used[manager[0]] < cap:
            used[manager[0]] += 1
            taken.add(link)
            chosen.append((manager[0], item))
            item["planned"] = True
    for item in planned:
        if item.get("planned"):
            continue
        item["types"] = [t for t in item["types"] if t not in MANAGER_TYPES or item.get("lesson", {}).get("link") not in taken]
        for type_id in item["types"]:
            if used[type_id] < cap:
                used[type_id] += 1
                if type_id in MANAGER_TYPES:
                    taken.add(item["lesson"]["link"])
                chosen.append((type_id, item))
                break
        if len(chosen) == slots:
            break
    chosen = chosen[:slots]
    groups: dict[str, list] = {}
    for type_id, item in chosen:
        groups.setdefault(type_id, []).append(item)
    ordered, last = [], history[-1] if history else None
    while groups:   # always take from the type with most Reels left that differs from the one before; this keeps a run of one type from piling up at the end
        options = [t for t in groups if t != last] or list(groups)
        type_id = max(options, key=lambda t: len(groups[t]))
        ordered.append((type_id, groups[type_id].pop(0)))
        if not groups[type_id]:
            del groups[type_id]
        last = type_id
    return [{"slot": n + 1, "type": t, "title": it["title"], "link": it["link"], "source": it["source"], "angle": it.get("angle", ""),
             "blurb": it.get("blurb", ""), "alternatives": [a for a in dict.fromkeys(it["types"] + ["story"]) if a != t and (a not in MANAGER_TYPES or it.get("lesson"))],
             "why": it["why"], "fact_check": BY_ID[t].needs_official and not official(it),
             **({"lesson": it["lesson"]} if t in MANAGER_TYPES and it.get("lesson") else {})} for n, (t, it) in enumerate(ordered)]


def load_history() -> list[str]:
    return json.loads(PLAN_FILE.read_text()).get("history", []) if PLAN_FILE.exists() else []


def load_used_lessons() -> list[str]:
    return json.loads(PLAN_FILE.read_text()).get("lessons_used", []) if PLAN_FILE.exists() else []


def save(plans: list[dict], history: list[str], lessons_used: list[str] | None = None) -> None:
    used = (lessons_used or []) + [p["lesson"]["link"] for p in plans if "lesson" in p]
    PLAN_FILE.write_text(json.dumps({"plan": plans, "history": (history + [p["type"] for p in plans])[-28:], "lessons_used": used[-40:]},
                                    indent=1, ensure_ascii=False))
