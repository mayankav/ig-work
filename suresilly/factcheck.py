"""The fact check: a Reel may state only what a real page says, and the page must be one the owner trusts.

For every planned Reel that states something (a rule, news, a "research shows"), this finds the page, reads its text, and asks a model for
the sentences that bear on the topic, each copied word for word. Code then checks every quote appears in the page text. A quote that
does not is thrown away, so a model cannot invent a source. If no quote survives, nothing is posted: the slot is skipped and the owner is
told why. What survives is turned into a FACT in the shape the script writer already checks numbers against.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse

from . import inbox, reeltypes

MIN_QUOTE, MAX_QUOTE = 40, 320
PAGE_CHARS = 8000           # how much of a page the model reads
DASHES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normal(text: str) -> str:
    """Page text and a quote made comparable: markup, spacing, curly quotes and case do not count as a difference."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    text = re.sub(r"[*_#>`|]", " ", text.translate(DASHES))
    return re.sub(r"\s+", " ", text).strip().lower()


def claims_prompt(entry: dict, page: str) -> tuple[str, str]:
    topic = f"{entry['title']}. {entry.get('angle', '')}".strip()
    system = ("You read one web page for a page that helps young people in India at the start of their working life. "
              "Find up to 3 statements in the page that bear on the topic you are given. "
              f"For each, copy the sentence or phrase from the page exactly, word for word, between {MIN_QUOTE} and {MAX_QUOTE} characters, into \"quote\". "
              "Do not join sentences, shorten them or fix them. Say in \"says\" what it means, in about 15 words of your own. "
              "Add nothing the page does not say, and give no advice. If the page says nothing that bears on the topic, return an empty list. "
              "Answer with one JSON object: {\"claims\": [{\"quote\": string, \"says\": string}]}.")
    return system, f"Topic: {topic}\n\nPage:\n{page[:PAGE_CHARS]}"


STRICT = ("can_they", "news")       # state a rule or an event: the quote must support exactly what the Reel says
EVENT = ("story",)                   # retell what happened: the quote must report the event; the takeaway is the model's own reasoning
LESSON = ("contrast", "mirror")      # a scenario and its reasoning: sourced only if it names a source, otherwise our own reasoning


def support_prompt(entry: dict, claims: list[dict]) -> tuple[str, str]:
    about = (f"The Reel retells this event: {entry['title']}\nA quote supports it if it reports what happened." if entry["type"] in EVENT else
             f"The Reel is about: {entry['title']}\nIt would say: {entry.get('angle', '')}")
    system = ("You check whether quotes from a web page support what a Reel would say. For each quote answer true only if the quote itself says "
              "what the Reel needs. Answer false when the quote is about something related, or about a different case, place, group or time, "
              "or when it would need another sentence to make the point. "
              "Answer with one JSON object: {\"results\": [{\"i\": number, \"supports\": true or false}]} with one entry for every quote.")
    listing = "\n".join(f"{n}. {c['quote']}" for n, c in enumerate(claims))
    return system, f"{about}\n\nQuotes:\n{listing}"


def supported(entry: dict, claims: list[dict], check) -> list[dict]:
    """Keep the quotes a second model says really support the Reel. If that model fails or garbles its answer, none are kept."""
    if not claims:
        return []
    system, user = support_prompt(entry, claims)
    try:
        answer = check([{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception:  # noqa: BLE001
        return []
    yes = set()
    for row in answer.get("results", []) if isinstance(answer, dict) else []:
        try:
            if row.get("supports") is True:
                yes.add(int(row["i"]))
        except (KeyError, TypeError, ValueError):
            continue
    return [c for n, c in enumerate(claims) if n in yes]


def verified_claims(entry: dict, page: str, call, check=None) -> list[dict]:
    """The claims whose quotes are really in the page and really support the Reel, with the model's plain-words meaning.

    `check` is a second model (ideally not the one that read the page); it defaults to the same one.
    """
    system, user = claims_prompt(entry, page)
    try:
        answer = call([{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception:  # noqa: BLE001 - a failed call is "no claims", and the slot is skipped, not guessed
        return []
    haystack, out = normal(page), []
    for row in answer.get("claims", []) if isinstance(answer, dict) else []:
        quote, says = str(row.get("quote", "")).strip(), str(row.get("says", "")).strip()
        if MIN_QUOTE <= len(quote) <= MAX_QUOTE and says and normal(quote) in haystack:
            out.append({"quote": quote, "says": says[:160]})
    return supported(entry, out, check or call)


def sources_for(entry: dict, find, domains: list[str]) -> list[dict]:
    """Where to look, best first. A lesson is grounded in its own page; a fact already from an official site in its own link; otherwise an official search."""
    lesson = entry.get("lesson")
    if lesson:
        return [{"url": lesson["link"], "title": lesson.get("title", ""), "text": lesson.get("text", ""), "official": False}]
    if entry["type"] == "story":      # a story rests on its own article, and is said to be reported, never official
        return [{"url": entry["link"], "title": entry["title"], "text": entry.get("blurb", "") if "reddit.com" in entry["link"] else "", "official": False}]
    if not entry.get("fact_check"):
        return [{"url": entry["link"], "title": entry["title"], "text": "", "official": True}]
    query = f"{entry['title']} {entry.get('angle', '')}"
    return [{"url": r["url"], "title": r["title"], "text": "", "official": True} for r in find(query, domains)[:3]]


def ground(entry: dict, find, text_of, call, domains: list[str], now: datetime | None = None, check=None) -> dict:
    """The page and the verified quotes this Reel may rest on, or why there are none. `status` is "verified" only with at least one quote."""
    now = now or datetime.now(timezone.utc)
    tried = []
    try:
        candidates = sources_for(entry, find, domains)
    except Exception as error:  # noqa: BLE001
        if entry["type"] in LESSON:
            return {"status": "reasoned", "why": "No source could be checked, so this is our own reasoning and names no source.", "tried": []}
        return {"status": "no_search", "why": f"The search for an official page failed: {error}", "tried": []}
    if not candidates:
        if entry["type"] in LESSON:
            return {"status": "reasoned", "why": "No source could be checked, so this is our own reasoning and names no source.", "tried": []}
        return {"status": "no_source", "why": "No page from an approved official site was found for this.", "tried": []}
    for source in candidates:
        tried.append(source["url"])
        try:
            page = source["text"] or text_of(source["url"])
        except Exception:  # noqa: BLE001
            continue
        claims = verified_claims(entry, page, call, check)
        if claims:
            site = (urlparse(source["url"]).hostname or "").removeprefix("www.")
            return {"status": "verified", "source": {"url": source["url"], "title": source["title"], "site": site, "official": source["official"]},
                    "claims": claims, "checked_at": now.date().isoformat(), "tried": tried}
    if entry["type"] in LESSON or (entry["type"] in EVENT and "reddit.com" in entry["link"]):     # a lesson with no source, or a question a reader asked (no event to retell)
        return {"status": "reasoned", "why": "No source could be checked, so this is our own reasoning and names no source.", "tried": tried}
    return {"status": "no_claims", "why": "The pages were read, but none had a sentence that matches the topic.", "tried": tried}


def to_fact(entry: dict, grounded: dict) -> dict:
    """A FACT in the shape script.check reads: its numbers are the only numbers the Reel may use."""
    first = grounded["claims"][0]
    source = grounded["source"]
    return {"id": source["url"], "area": entry["type"], "title": source["title"] or entry["title"], "claim": " ".join(c["says"] for c in grounded["claims"]),
            "source": source["site"], "source_date": grounded["checked_at"], "law": " ".join(c["quote"] for c in grounded["claims"]), "caveat": "",
            "status": "checked" if source["official"] else "reported", "url": source["url"]}


NEEDS_GROUND = ("can_they", "news", "contrast", "mirror", "story")     # every Reel type rests on a page


def check_week(plans: list[dict], find, text_of, call, domains: list[str], log=None, check=None, workers: int = 4) -> list[dict]:
    """Every planned Reel with a `ground` result, several at once. A Reel that needs grounding and has none is marked `skip` with the reason in plain words."""
    def one(entry):
        if entry["type"] not in NEEDS_GROUND:
            return {**entry, "ground": {"status": "not_needed"}}
        grounded = ground(entry, find, text_of, call, domains, check=check)
        tried_types = [entry["type"]]
        for alt in entry.get("alternatives", []):      # a second choice: the same item as another type, grounded the same way
            if grounded["status"] in ("verified", "reasoned"):
                break
            grounded = ground({**entry, "type": alt}, find, text_of, call, domains, check=check)
            tried_types.append(alt)
            if grounded["status"] in ("verified", "reasoned"):
                entry = {**entry, "type": alt, "fell_back_from": tried_types[0], "fact_check": False}
        if log:
            log(f"  {entry['slot']:2d} {'/'.join(tried_types):28s} {grounded['status']}")
        return {**entry, "ground": grounded, **({} if grounded["status"] in ("verified", "reasoned") else {"skip": grounded.get("why", "")})}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, plans))
