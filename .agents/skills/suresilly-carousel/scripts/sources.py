#!/usr/bin/env python3
"""
sources.py — layer 0. Where moments come from.

The cheapest safety control in the whole pipeline is choosing where we read.
Anything we never fetch is something layer 1 never has to filter.

Bluesky is the source. It is the only place that is simultaneously free, open,
high-volume and written in the right register: ordinary people describing
ordinary evenings, not people performing for an audience. No key, no account,
no card, no application.

Everything else was checked against its own terms and ruled out. Reddit's free
tier is non-commercial only and its agreement bans automated access by any
method, browser automation included. Quora, X, YouTube comments, Tumblr and the
review sites each forbid this use outright. The public mental-health datasets
are either non-commercial, unlicensed, or scraped from real counselling
sessions. See references/strategy.md for the full log.

Standard library only, on purpose. This has to run in CI twice a day for years
without a dependency deciding to break.

Two things this module is careful about:

  * It fetches, it does not judge. Screening is layers 1 and 2, and they run on
    everything this returns.
  * It never returns a person's words as publishable text. What comes back is
    raw material for the abstraction step, and the original is discarded there.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

# Two hosts serve the same read endpoint and they do not fail together. From a
# laptop, api.bsky.app answers search and public.api.bsky.app refuses it. From a
# GitHub runner the first run found every request failing, which is the case
# this fallback exists for: a data-centre address can be treated differently
# from a home one, and the second host is worth a try before giving up on a run.
SEARCH_HOSTS = (
    "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
    "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
)

# Anonymous search is refused outright from a data-centre address. Both public
# hosts answer 403 from a GitHub runner while both answer normally from a
# laptop, so it is a deliberate block rather than a rate limit and no amount of
# backing off reaches it.
#
# Signing in is the way through. A session is made from a handle and an app
# password, which is a revocable credential that cannot change the account's
# real password, and authenticated reads go through the account's own server.
SESSION_URL = "https://bsky.social/xrpc/com.atproto.server.createSession"
AUTHED_SEARCH_URL = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"

_session: dict | None = None


def _sign_in() -> dict | None:
    """Return auth headers, or None when no credentials are set.

    Cached for the process: a run makes fourteen searches and one session
    serves all of them.
    """
    global _session
    if _session is not None:
        return _session or None

    handle = os.environ.get("BLUESKY_HANDLE", "").strip()
    password = os.environ.get("BLUESKY_APP_PASSWORD", "").strip()
    if not (handle and password):
        _session = {}
        return None

    body = json.dumps({"identifier": handle, "password": password}).encode()
    request = urllib.request.Request(SESSION_URL, data=body, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            token = json.loads(response.read().decode())["accessJwt"]
    except Exception as exc:
        raise SourceUnavailable(f"could not sign in to Bluesky: {exc}") from exc

    _session = {"Authorization": f"Bearer {token}"}
    return _session

USER_AGENT = "suresilly-carousel/3.0 (+https://instagram.com/suresilly)"
TIMEOUT = 20

# Bluesky throttles a burst of searches from one address. Fetching every phrase
# back to back loses most of them silently, which looks like a thin day rather
# than a broken fetch. A short pause and one retry recovers nearly all of it.
PAUSE_SECONDS = 0.7
RETRY_PAUSE_SECONDS = 3.0

# Phrases that appear in the middle of an ordinary account of an ordinary
# evening. These are retrieval handles, not a topic list — layer 2 decides what
# is actually usable, and these only decide where we look.
#
# Written as fragments people type about themselves, never as clinical terms. A
# query for "anxiety" returns people talking ABOUT anxiety; a query for "woke up
# at" returns people who were awake.
QUERIES = (
    "woke up at",
    "couldn't sleep",
    "stared at the ceiling",
    "read the message again",
    "kept refreshing",
    "closed my laptop",
    "sat in the car",
    "stood in the kitchen",
    "checked my phone again",
    "typed and deleted",
    "said yes when I meant",
    "apologised before",
    "put my phone face down",
    "opened the fridge",
    # These carry a feeling as well as a behaviour, and that turned out to be
    # the thing that mattered. The fourteen above search for actions and find
    # people describing actions: of 344 posts fetched by them, seventeen
    # contained any feeling word and none of those survived the shape filter.
    # The safety judge then refused every candidate for having nothing felt in
    # it, which is what killed several runs.
    #
    # Each of these was measured with probe_phrases.py and each returned at
    # least one moment with a felt state in it. Yield is low, roughly one per
    # fifty posts, which is why there are several rather than one.
    "cried in the car",
    "too tired to",
    "dreading tomorrow",
    "so tired i",
)


class SourceUnavailable(Exception):
    """The feed could not be reached. The caller falls back to the reserve, and
    if that is empty, posts nothing."""


def _get(url: str, params: dict, headers: dict | None = None, retries: int = 1) -> dict:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}", headers={"User-Agent": USER_AGENT, **(headers or {})})
    last: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(RETRY_PAUSE_SECONDS)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as exc:
            last = exc
    raise SourceUnavailable(f"{url}: {last}") from last


def search(phrase: str, limit: int = 25, lang: str = "en") -> list[dict]:
    """Return raw posts matching one phrase.

    Each result is reduced to what the pipeline actually needs: the text, and a
    reference we hash rather than store. Author handles, display names, avatars,
    counts and thread context are dropped here and never enter the pipeline.
    """
    auth = _sign_in()
    # Signed in, the account's own server answers and the public hosts are not
    # needed. Anonymous, they are all there is.
    hosts = (AUTHED_SEARCH_URL,) + SEARCH_HOSTS if auth else SEARCH_HOSTS

    trouble = []
    for url in hosts:
        try:
            payload = _get(url, {"q": phrase, "limit": limit, "lang": lang}, auth)
            break
        except SourceUnavailable as exc:
            trouble.append(str(exc)[-90:])
    else:
        raise SourceUnavailable(" | ".join(trouble))
    out = []
    for post in payload.get("posts", []):
        text = (post.get("record") or {}).get("text", "").strip()
        if text:
            out.append({"text": text, "ref": post.get("uri", ""), "query": phrase})
    return out


def harvest(queries=QUERIES, per_query: int = 25, limit: int | None = None) -> dict:
    """Pull candidates across every phrase, and report how the pull went.

    The phrase order is shuffled each run. Two reasons: the last phrases in a
    fixed order are the ones a throttle eats, so a fixed order would quietly
    narrow what we ever see; and rotating which phrase leads changes the kind of
    evening we are looking at that day.

    One failing phrase never fails the harvest — a single bad response should not
    cost a post. It fails only when nothing at all came back, which is the case
    the reserve exists for.
    """
    phrases = list(queries)
    random.shuffle(phrases)

    seen: set[str] = set()
    out: list[dict] = []
    failed: list[str] = []
    # Keep why it failed, not just that it did. A harvest that reports
    # "14/14 failed" and nothing else cannot be diagnosed from a CI log, which
    # is the only place this ever runs unattended.
    why: list[str] = []

    for index, phrase in enumerate(phrases):
        if index:
            time.sleep(PAUSE_SECONDS)
        try:
            results = search(phrase, limit=per_query)
        except SourceUnavailable as exc:
            failed.append(phrase)
            if len(why) < 3:
                why.append(str(exc)[-160:])
            continue
        for item in results:
            key = item["text"].lower().strip()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        if limit and len(out) >= limit:
            break

    if not out:
        raise SourceUnavailable(
            f"every phrase failed ({len(failed)}/{len(phrases)}). " + " | ".join(why))
    return {"items": out, "attempted": len(phrases), "failed": failed, "why": why}


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    try:
        result = harvest(queries=QUERIES[:3], per_query=10)
    except SourceUnavailable as exc:
        print(f"source unavailable: {exc}")
        raise SystemExit(1)
    items = result["items"]
    print(f"{len(items)} candidates, {len(result['failed'])}/{result['attempted']} phrases failed")
    for item in items[:n]:
        print(f"  [{item['query']}] {item['text'][:110]}")
