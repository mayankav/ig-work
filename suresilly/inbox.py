"""The weekly story inbox: what happened at work in India this week, found in the feeds the owner approves.

Once a week one job collects every feed (`collect`), drops what is old or already seen (`fresh`), merges the same story told by
several sites (`merge_duplicates`), asks a model which items are about a first job, a manager or a workplace rule (`rate`), and keeps
the best as the week's stock (`run`). The stock holds only a link, a date, a source, a score and the angle (what a young worker could take from it) in the model's own
words. No article text is kept: the writer fetches the page when it writes. State lives in `state/inbox.json` so next week's job
never offers the same item twice.
"""
from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from . import PACKAGE, STATE

SOURCES = json.loads((PACKAGE / "sources.json").read_text())
STATE_FILE = STATE / "inbox.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MAX_AGE_DAYS = 10       # an item older than this is not news any more
KEEP_SEEN_DAYS = 60     # how long an item id is remembered
BATCH = 20              # items per model call when the model reads title and blurb
FIRST_BATCH = 25        # items per call in the first, title-only cut
FIRST_MIN = 4           # the first cut keeps what scores at least this, so the careful read sees a few dozen, not a thousand
WORKERS = 4             # model calls at once
MIN_SCORE = 6           # of 10; the model's own score for "a first-jobber would stop for this"
SLOTS_A_WEEK = 14       # two posts a day
BELOW_CUT = 30          # items just under the cut that the owner may look at
STOCK = 20              # items kept for the week (14 posts and some spare)
WEEK_DAYS = 7           # a full collection runs this often
RETRY_HOURS = 20        # a source that failed is tried again once this long has passed (the next day's run)
RETRY_TRIES = 4         # after this many failures in a row the owner is told and the source rests until the next full run
SAME_STORY = 0.45       # title word overlap above this means two sites told the same story
KINDS = ("event", "story", "rule", "other")
ATOM = "{http://www.w3.org/2005/Atom}"


def _text(node, *tags) -> str:
    for tag in tags:
        found = node.find(tag)
        if found is None:
            found = node.find(ATOM + tag)
        if found is not None:
            text = "".join(found.itertext()).strip() or found.attrib.get("href", "").strip()
            if text:
                return text
    return ""


def _when(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def fetch_feed(feed: dict, get=requests.get) -> list[dict]:
    """One feed as a list of items: id, source, kind, title, link, published (iso or ''), blurb."""
    response = get(feed["url"], headers={"User-Agent": UA}, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for node in root.findall(".//item") + root.findall(".//" + ATOM + "entry"):
        link = _text(node, "link")
        title = _plain(_text(node, "title"))
        if not link or not title:
            continue
        when = _when(_text(node, "pubDate", "published", "updated"))
        items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "source": feed["name"], "kind": feed.get("kind", "news"),
                      "title": title, "link": link, "published": when.isoformat() if when else "",
                      "blurb": _plain(_text(node, "description", "summary"))[:300]})
    return items


READER_MODELS = ("gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash")   # each has its own free pool
AGE = re.compile(r"(\d+)\s*(m|min|h|hr|d|day|w|wk|mo|y)\b", re.I)
UNIT_MINUTES = {"m": 1, "min": 1, "h": 60, "hr": 60, "d": 1440, "day": 1440, "w": 10080, "wk": 10080, "mo": 43200, "y": 525600}


def gemini_reader(key: str, models=READER_MODELS, post=requests.post):
    """`read(url, instruction) -> text`: Google's own fetcher opens the page (Reddit refuses cloud servers but lets this through).

    A model whose free pool is spent (429) hands over to the next one. The page text is copied by the model, so the instruction asks
    for values word for word and "not shown" when the page has none.
    """
    def read(url: str, instruction: str) -> str:
        last = ""
        for model in models:
            reply = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key},
                         timeout=180, json={"contents": [{"role": "user", "parts": [{"text": f"Open {url} . {instruction}"}]}],
                                            "tools": [{"url_context": {}}], "generationConfig": {"temperature": 0}})
            if reply.status_code == 200:
                parts = reply.json()["candidates"][0]["content"]["parts"]
                return "".join(part.get("text", "") for part in parts)
            last = f"{model}: HTTP {reply.status_code}"
        raise RuntimeError(last)
    return read


def _age(text: str, now: datetime) -> str:
    found = AGE.search(text or "")
    if not found:
        return ""
    return (now - timedelta(minutes=int(found.group(1)) * UNIT_MINUTES[found.group(2).lower()])).isoformat()


def fetch_page(page: dict, read, now: datetime) -> list[dict]:
    """A listing page (a subreddit's newest posts) as items. Each has a title, a short preview and an age; no score and no link."""
    text = read(page["url"], "Return JSON only: {\"posts\": [{\"title\": string, \"preview\": string, \"age\": string}]} for the first 25 posts. "
                "Copy title and preview word for word from the page, and age as the page shows it. Write \"not shown\" for anything the page does not "
                "show. Do not guess or calculate.")
    match = re.search(r"\{.*\}", text or "", re.S)
    posts = json.loads(match.group(0)).get("posts", []) if match else []
    items = []
    for post in posts:
        title = _plain(str(post.get("title", "")))
        if not title or title == "not shown":
            continue
        preview = _plain(str(post.get("preview", "")))
        items.append({"id": hashlib.sha1((page["name"] + title).encode()).hexdigest()[:16], "source": page["name"], "kind": page.get("kind", "post"),
                      "title": title, "link": page["url"], "published": _age(str(post.get("age", "")), now),
                      "blurb": "" if preview == "not shown" else preview[:300]})
    return items


IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"(?<!!)\[([^\]]{25,}?)\]\((https?://[^)\s]+)(?:\s+\"[^\"]*\")?\)")


def fetch_links(page: dict, get=requests.get) -> list[dict]:
    """A news section page read by Jina Reader: every long link text on the same site is an article. No date is given, so the item
    counts as new the first time it is seen and never again."""
    response = get("https://r.jina.ai/" + page["url"], headers={"User-Agent": "suresilly-inbox/1.0"}, timeout=90)   # Jina refuses a browser-style agent
    response.raise_for_status()
    return parse_links(response.text, page)


def parse_links(markdown: str, page: dict) -> list[dict]:
    """Page text in markdown to items: every long link text on the same site is an article."""
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", page["url"]).split("/")[0])
    items, seen = [], set()
    for title, link in LINK.findall(IMAGE.sub(" ", markdown)):     # images first: their text sits inside the link text
        title = _plain(title).lstrip("*# ").replace(" ### ", " - ")
        link = link.split("#")[0]
        if host not in link or link.rstrip("/") == page["url"].rstrip("/") or link in seen or len(title) < 25 or title.count(" ") < 3:
            continue
        seen.add(link)
        items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "source": page["name"], "kind": page.get("kind", "news"),
                      "title": title, "link": link, "published": "", "blurb": ""})
    return items


TAVILY = "https://api.tavily.com/"


def tavily_extract(key: str, post=requests.post, guard=None):
    """A ladder rung: Tavily reads the page and gives its text, which the same link parser turns into items."""
    def rung(page: dict, now: datetime) -> list[dict]:
        if guard:
            guard()
        reply = post(TAVILY + "extract", headers={"Authorization": f"Bearer {key}"}, json={"urls": [page["url"]]}, timeout=90)
        reply.raise_for_status()
        results = reply.json().get("results", [])
        if not results:
            raise RuntimeError("failed to fetch")
        return parse_links(results[0].get("raw_content", ""), page)
    return rung


def _tavily_guard(key: str, get=requests.get, share: float = 0.8):
    def guard():
        account = get(TAVILY + "usage", headers={"Authorization": f"Bearer {key}"}, timeout=30).json().get("account") or {}
        if account.get("plan_limit") and account.get("plan_usage", 0) >= share * account["plan_limit"]:
            raise RuntimeError(f"tavily credits used: {account['plan_usage']} of {account['plan_limit']}")
    return guard


def tavily_reader(key: str, post=requests.post, get=requests.get, share: float = 0.8):
    """(find, text) for the fact check, guarded like the rest: `find(query, domains)` searches only those sites, `text(url)` gives a page's text."""
    guard = _tavily_guard(key, get, share)

    def find(query: str, domains: list[str], n: int = 5) -> list[dict]:
        guard()
        reply = post(TAVILY + "search", headers={"Authorization": f"Bearer {key}"}, timeout=90,
                     json={"query": query, "topic": "general", "max_results": n, "include_domains": domains})
        reply.raise_for_status()
        return [{"url": r["url"], "title": _plain(r.get("title", ""))} for r in reply.json().get("results", []) if r.get("url")]

    def text(url: str) -> str:
        guard()
        reply = post(TAVILY + "extract", headers={"Authorization": f"Bearer {key}"}, json={"urls": [url]}, timeout=90)
        reply.raise_for_status()
        results = reply.json().get("results", [])
        if not results:
            raise RuntimeError("failed to fetch")
        return results[0].get("raw_content", "")

    return find, text


def tavily_tools(key: str, post=requests.post, get=requests.get, share: float = 0.8):
    """(search, rung) that stop before the free credits run out: each call first reads the usage counter and refuses at `share` of the plan."""
    guard = _tavily_guard(key, get, share)

    def search(source: dict, now: datetime) -> list[dict]:
        guard()
        return fetch_search(source, key, now, post)

    return search, tavily_extract(key, post, guard)


def fetch_search(source: dict, key: str, now: datetime, post=requests.post) -> list[dict]:
    """A broad search of the news for the week: each result has a link, a date, a site and a snippet."""
    topic = source.get("topic", "news")
    body = {"query": source["query"], "topic": topic, "max_results": source.get("max_results", 20)}
    time_range = source.get("time_range", "week" if topic == "news" else None)
    if time_range:
        body["time_range"] = time_range
    if source.get("include_domains"):
        body["include_domains"] = source["include_domains"]
    reply = post(TAVILY + "search", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=90)
    reply.raise_for_status()
    items = []
    for result in reply.json().get("results", []):
        link, title = result.get("url", ""), _plain(result.get("title", ""))
        if not link or not title:
            continue
        when = _when(result.get("published_date", ""))
        site = re.sub(r"^www\.", "", re.sub(r"^https?://", "", link).split("/")[0])
        items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "source": site, "kind": source.get("kind", "news"), "title": title, "link": link,
                      "published": when.isoformat() if when else "", "blurb": _plain(result.get("content", ""))[:300]})
    return items


def _abstract(index) -> str:
    """OpenAlex stores an abstract as word -> positions; this puts the words back in order."""
    if not index:
        return ""
    words = {}
    for word, positions in index.items():
        for position in positions:
            words[position] = word
    return " ".join(words[i] for i in sorted(words))


def fetch_openalex(source: dict, get=requests.get) -> list[dict]:
    """Open-access research papers on a question: free, no key. Each item has a title, a link to the paper and its date."""
    reply = get("https://api.openalex.org/works", timeout=60, params={
        "search": source["query"], "filter": f"is_oa:true,type:article,publication_year:>{source.get('from_year', 2020) - 1}",
        "per-page": source.get("per_page", 15), "select": "title,publication_date,doi,open_access,cited_by_count,abstract_inverted_index"})
    reply.raise_for_status()
    items = []
    for work in reply.json().get("results", []):
        link = work.get("doi") or (work.get("open_access") or {}).get("oa_url") or ""
        title = _plain(work.get("title") or "")
        if not link or not title:
            continue
        items.append({"id": hashlib.sha1(link.encode()).hexdigest()[:16], "source": "OpenAlex", "kind": source.get("kind", "research"), "title": title,
                      "link": link, "published": work.get("publication_date") or "", "blurb": f"{work.get('cited_by_count', 0)} citations",
                      "text": _abstract(work.get("abstract_inverted_index"))})
    return items


def read_page(page: dict, get, read, now: datetime, tavily=None) -> list[dict]:
    """A page's ladder of readers: the first that returns items wins. If none does, the error names every rung and why it failed."""
    problems = []
    for name in page.get("readers") or ["gemini"]:
        try:
            if name == "jina":
                items = fetch_links(page, get)
            elif name == "gemini":
                if read is None:
                    raise RuntimeError("no key")
                items = fetch_page(page, read, now)
            elif name == "tavily":
                if tavily is None:
                    raise RuntimeError("no key")
                items = tavily(page, now)
            else:
                raise ValueError(name)
            if items:
                return items
            problems.append(f"{name}: no items")
        except Exception as error:  # noqa: BLE001 - a failed rung hands over to the next
            problems.append(f"{name}: {type(error).__name__}")
    raise RuntimeError("; ".join(problems))


def collect(get=requests.get, only: list[str] | None = None, read=None, now: datetime | None = None, tavily=None, search=None) -> tuple[list[dict], dict[str, str]]:
    """The feeds and listing pages (or only the named ones). A source that fails is reported with its error, never fatal: the rest go on."""
    now = now or datetime.now(timezone.utc)
    items, failed = [], {}
    for feed in SOURCES["feeds"]:
        if only is not None and feed["name"] not in only:
            continue
        try:
            items += fetch_feed(feed, get)
        except Exception as error:  # noqa: BLE001 - one dead feed must not stop the job
            failed[feed["name"]] = type(error).__name__
    for page in SOURCES.get("pages", []):
        if only is not None and page["name"] not in only:
            continue
        try:
            items += read_page(page, get, read, now, tavily)
        except Exception as error:  # noqa: BLE001
            failed[page["name"]] = str(error)
    for source in SOURCES.get("searches", []):
        if only is not None and source["name"] not in only:
            continue
        try:
            if search is None:
                raise RuntimeError("no key")
            found = search(source, now)
            if not found:
                raise RuntimeError("no results")
            items += found
        except Exception as error:  # noqa: BLE001
            failed[source["name"]] = str(error) or type(error).__name__
    return items, failed


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen": {}, "last_run": "", "stock": [], "retry": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=1, ensure_ascii=False))


def fresh(items: list[dict], state: dict, now: datetime, max_age_days: int | None = MAX_AGE_DAYS) -> list[dict]:
    """Drop what is too old and what an earlier week already saw. Items with no date count as new the first time.

    `max_age_days=None` keeps old items: a lesson does not go stale the way news does.
    """
    oldest = now - timedelta(days=max_age_days) if max_age_days is not None else None
    out, ids = [], set()
    for item in items:
        if item["id"] in state["seen"] or item["id"] in ids:
            continue
        if oldest and item["published"] and _when(item["published"]) and _when(item["published"]) < oldest:
            continue
        ids.add(item["id"])
        out.append(item)
    return out


def _grams(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {a + " " + b for a, b in zip(words, words[1:])} or set(words)


def merge_duplicates(items: list[dict]) -> list[dict]:
    """The same story from several sites becomes one item, the earliest, with the other sources listed."""
    out: list[dict] = []
    for item in sorted(items, key=lambda i: i["published"] or "9"):
        grams = _grams(item["title"])
        for kept in out:
            other = _grams(kept["title"])
            if grams and other and len(grams & other) / min(len(grams), len(other)) >= SAME_STORY:
                kept.setdefault("also", []).append(item["source"])
                break
        else:
            out.append(dict(item))
    return out


LESSON = ("You work for a small Instagram page that helps young people in India at the start of their working life, and also shows managers "
          "what professional management looks like. You are given writings by people who manage, research papers and official guidance. "
          "Score every item from 0 to 10 for how much it can teach a manager, or help a junior understand a manager, in a way that is honest "
          "and can be shown without inventing anything: a habit, a choice, a reason and what follows from it. "
          "Give a low score when it is about something else, or when the lesson would need a claim the item does not support. "
          "Say in \"angle\" what the lesson is, in about 12 words of your own. "
          "Also say what it is: \"research\" (a study or data), \"official\" (guidance from an authority), \"opinion\" (one person's view), or \"other\". "
          "Answer with one JSON object: {\"items\": [{\"i\": number, \"score\": number, \"kind\": string, \"angle\": string}]} "
          "with one entry for every item.")
LESSON_KINDS = ("research", "official", "opinion", "other")


def rate_prompt(items: list[dict], titles_only: bool = False, lesson: bool = False) -> tuple[str, str]:
    listing = "\n".join(f"{n}. [{item['source']}] {item['title']}" + ("" if titles_only else f" - {item['blurb'][:160]}") for n, item in enumerate(items))
    system = ("You work for a small Instagram page for people in India, age 18 to 30, at the start of their working life. "
              "You are given news items. Any item may be used, whatever its topic. Your job is to find the ones from which the page can make "
              "something a young Indian at work would use, remember or send to a friend: something that changes what they know, say, expect, "
              "choose or can ask for. Score every item from 0 to 10 for how useful and honest that thing could be for this reader. "
              "Give a low score when you cannot name a real use for this reader, or when the use would need a claim the item does not support. "
              "Say in \"angle\" what the reader could take from it, in about 12 words of your own. "
              "Also say what shape the item has: \"event\" (something that happened in the news), \"story\" (a person's experience at work), "
              "\"rule\" (a law, a rule or an official notice), or \"other\". "
              "Answer with one JSON object: {\"items\": [{\"i\": number, \"score\": number, \"kind\": string, \"angle\": string}]} "
              "with one entry for every item.")
    return (LESSON if lesson else system), "Items:\n" + listing


def _rate_chunk(chunk: list[dict], call, titles_only: bool, lesson: bool = False) -> list[dict]:
    system, user = rate_prompt(chunk, titles_only, lesson)
    answer, unrated = None, False
    for _ in range(2):      # one retry: a slow or failed call must not stop the week
        try:
            answer = call([{"role": "system", "content": system}, {"role": "user", "content": user}])
            break
        except Exception:  # noqa: BLE001
            unrated = True
    if answer is not None:
        unrated = False
    by_index = {}
    for row in answer.get("items", []) if isinstance(answer, dict) else []:
        try:
            by_index[int(row["i"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    rated = []
    for n, item in enumerate(chunk):
        row = by_index.get(n, {})
        try:
            score = max(0, min(10, int(row.get("score", 0))))
        except (TypeError, ValueError):
            score = 0
        kind = row.get("kind") if row.get("kind") in (LESSON_KINDS if lesson else KINDS) else "other"
        rated.append({**item, "score": score, "story_kind": kind, "angle": str(row.get("angle", ""))[:120], **({"unrated": True} if unrated else {})})
    return rated


def rate(items: list[dict], call, titles_only: bool = False, workers: int = WORKERS, log=None, lesson: bool = False) -> list[dict]:
    """Score every item with a model, several batches at once. An item the model skips or garbles gets score 0, never a guess."""
    size = FIRST_BATCH if titles_only else BATCH
    chunks = [items[start:start + size] for start in range(0, len(items), size)]
    done = []

    def work(chunk):
        out = _rate_chunk(chunk, call, titles_only, lesson)
        done.append(1)
        if log:
            log(f"  rated batch {len(done)} of {len(chunks)}")
        return out

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return [row for part in pool.map(work, chunks) for row in part]


def due(state: dict, now: datetime) -> tuple[str, list[str] | None]:
    """What today's run should do: ("full", None) once a week, ("retry", names) the day after a source failed, else ("skip", None)."""
    last = datetime.fromisoformat(state["last_run"]) if state.get("last_run") else None
    if last is None or now - last >= timedelta(days=WEEK_DAYS):
        return "full", None
    ready = [name for name, r in state.get("retry", {}).items()
             if r["tries"] < RETRY_TRIES and now - datetime.fromisoformat(r["last"]) >= timedelta(hours=RETRY_HOURS)]
    return ("retry", ready) if ready else ("skip", None)


def run(call, now: datetime | None = None, get=requests.get, read=None, tavily=None, search=None, log=None) -> dict:
    """Today's run: a full weekly collection, or only the sources that failed before, or nothing. Returns the report; state is saved.

    A source that fails is tried again the next day, up to RETRY_TRIES times; `gave_up` then names it so the caller can tell the owner.
    """
    now = now or datetime.now(timezone.utc)
    state = load_state()
    state.setdefault("retry", {})
    mode, names = due(state, now)
    if mode == "skip":
        return {"mode": mode, "collected": 0, "per_source": {}, "failed_feeds": {}, "gave_up": [], "new": 0, "unrated": 0, "first_cut": 0, "rated": 0,
                "kept": len(state["stock"]), "stock": state["stock"], "below_cut": state.get("below_cut", []), "at": now.isoformat()}
    items, failed = collect(get, names, read, now, tavily, search)
    for name in (names or [f["name"] for f in SOURCES["feeds"] + SOURCES.get("pages", []) + SOURCES.get("searches", [])]):
        if name not in failed:
            state["retry"].pop(name, None)
    for name, error in failed.items():
        tries = state["retry"].get(name, {}).get("tries", 0) + 1 if mode == "retry" else 1
        state["retry"][name] = {"tries": tries, "last": now.isoformat(), "error": error}
    gave_up = [n for n, r in state["retry"].items() if r["tries"] >= RETRY_TRIES]
    new = merge_duplicates(fresh(items, state, now))
    per_source = {}
    for item in items:
        per_source[item["source"]] = per_source.get(item["source"], 0) + 1
    if log:
        log(f"collected {len(items)}, new {len(new)}; first cut starts")
    first = rate(new, call, titles_only=True, log=log)
    cut = [i for i in first if i["score"] >= FIRST_MIN]    # first cut: titles only, big batches
    if log:
        log(f"first cut kept {len(cut)}; careful read starts")
    rated = rate([{k: v for k, v in i.items() if k not in ("score", "story_kind", "angle", "unrated")} for i in cut], call, log=log)    # careful read
    top = sorted((i for i in rated if i["score"] >= MIN_SCORE), key=lambda i: (-i["score"], i["published"] or ""))
    below = sorted((i for i in rated if i["score"] < MIN_SCORE), key=lambda i: (-i["score"], i["published"] or ""))[:BELOW_CUT]
    keep = top[:STOCK] if mode == "full" else (state["stock"] + top)[:STOCK]
    for item in items:
        state["seen"][item["id"]] = now.isoformat()
    state["seen"] = {k: v for k, v in state["seen"].items() if datetime.fromisoformat(v) > now - timedelta(days=KEEP_SEEN_DAYS)}
    if mode == "full":
        state["last_run"] = now.isoformat()
    state["stock"] = keep
    state["below_cut"] = below
    save_state(state)
    return {"mode": mode, "collected": len(items), "per_source": per_source, "failed_feeds": failed, "gave_up": gave_up, "new": len(new),
            "unrated": sum(1 for i in first if i.get("unrated")), "first_cut": len(cut), "rated": len(rated), "kept": len(keep),
            "stock": keep, "below_cut": below, "at": now.isoformat()}


LESSON_MIN = 7          # a lesson must score higher than a story to be kept: most blog posts are about something else
LIBRARY = 60            # lessons kept, best first; they stay useful, so the library grows week by week


def run_principles(call, now: datetime | None = None, get=requests.get, search=None, log=None) -> dict:
    """The weekly lessons job: opinions of people who manage, research and official guidance, scored as lessons and kept in a library.

    A source that fails is reported and retried like the stories' sources. The library keeps the best LIBRARY lessons ever found.
    """
    now = now or datetime.now(timezone.utc)
    state = load_state()
    lanes = SOURCES.get("principles", {})
    items, failed = [], {}
    for feed in lanes.get("feeds", []):
        try:
            items += fetch_feed(feed, get)
        except Exception as error:  # noqa: BLE001
            failed[feed["name"]] = type(error).__name__
    for source in lanes.get("searches", []):
        try:
            if search is None:
                raise RuntimeError("no key")
            found = search(source, now)
            if not found:
                raise RuntimeError("no results")
            items += found
        except Exception as error:  # noqa: BLE001
            failed[source["name"]] = str(error) or type(error).__name__
    for source in lanes.get("openalex", []):
        try:
            items += fetch_openalex(source, get)
        except Exception as error:  # noqa: BLE001
            failed[source["name"]] = type(error).__name__
    seen = state.setdefault("seen_lessons", {})
    new = merge_duplicates(fresh(items, {"seen": seen}, now, max_age_days=None))
    if log:
        log(f"lessons: collected {len(items)}, new {len(new)}")
    rated = rate(new, call, log=log, lesson=True)
    good = [i for i in rated if i["score"] >= LESSON_MIN]
    for item in items:
        seen[item["id"]] = now.isoformat()
    library = {i["id"]: i for i in state.get("principles", [])}
    library.update({i["id"]: i for i in good})
    state["principles"] = sorted(library.values(), key=lambda i: -i["score"])[:LIBRARY]
    save_state(state)
    return {"collected": len(items), "failed": failed, "new": len(new), "unrated": sum(1 for i in rated if i.get("unrated")),
            "added": len(good), "library": len(state["principles"]), "added_items": good}
