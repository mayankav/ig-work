#!/usr/bin/env python3
"""
trends.py — layer 0's second source. What is already working on this subject.

A stranger's late evening tells us what happened to one person. It does not tell
us what anybody wants to read. This asks the other question: under the hashtags
this page lives in, which posts did people actually stop for?

An idea is not ownable and copying one is not what this does. We read what the
post is ABOUT — the angle, the promise, the shape of the hook — and then write
our own, better, in our own words. The firewall that makes that safe is the one
compose.py already has: no run of seven words survives from anything harvested.
It is checked, not trusted.

WHAT THE API ACTUALLY GIVES US, because the gap matters

  Instagram's hashtag search returns the CAPTION, the like count and the comment
  count. It does not return saves or shares, which are the numbers that decide
  whether a carousel worked — those exist only for media you own. So this ranks
  on the two signals it can see and says so, rather than pretending to measure
  the thing we care about.

  It also does not return the words printed ON the slides, and in this niche the
  hook usually lives in the image rather than the caption. A caption is a
  shadow of the post, not the post.

  Hashtag search needs a Facebook-Login token (EAA...) against graph.facebook.com
  and an Instagram BUSINESS account. The newer Instagram-Login token (IGAAP...)
  can publish but cannot search, so a page set up that way gets a clear refusal
  here instead of a puzzling empty result.

  The hard limit is 30 unique hashtags per rolling 7 days. That is not a rate
  limit that clears in a minute; spend it carelessly on a Monday and there is
  nothing left on a Thursday. Which hashtags have been spent is written down.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SPEND_FILE = REPO_ROOT / "state" / "hashtag_spend.json"

GRAPH = "https://graph.facebook.com/v20.0"
TIMEOUT = 30

# Seven days, in seconds. Instagram counts unique hashtags queried in a rolling
# window of exactly this length.
WINDOW = 7 * 24 * 60 * 60
MAX_HASHTAGS = 30

# The tags this page lives under. Ordered by how close they sit to what we
# publish, because the budget runs out before the list does.
HASHTAGS = (
    "relationshipadvice", "peoplepleasing", "boundaries", "emotionalintelligence",
    "attachmentstyles", "innerchildhealing", "burnoutrecovery", "overthinking",
    "anxietyrelief", "selfworth", "psychologyfacts", "philosophyofmind",
    "nervoussystemregulation", "adhdinattentive", "sleephygiene",
)


class NoSearch(Exception):
    """Hashtag search is not available with these credentials."""


def _get(path: str, params: dict) -> dict:
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": "suresilly-carousel/3.0 (+https://instagram.com/suresilly)"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:                                    # noqa: BLE001
            detail = ""
        raise NoSearch(f"HTTP {exc.code}: {detail}") from exc
    except Exception as exc:                                 # noqa: BLE001
        raise NoSearch(str(exc)) from exc


def _spend() -> dict:
    """Which hashtags have been queried, and when. Survives between runs."""
    if not SPEND_FILE.is_file():
        return {}
    try:
        return json.loads(SPEND_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _record(tag: str, now: float) -> None:
    spent = {t: at for t, at in _spend().items() if now - at < WINDOW}
    spent[tag] = now
    SPEND_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPEND_FILE.write_text(json.dumps(spent, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def affordable(now: float | None = None) -> list[str]:
    """Hashtags we may still ask about inside the 7-day allowance.

    A tag already queried this week is free to query again — the limit counts
    UNIQUE tags — so those come first, and a new tag is only spent when the
    budget has room for it.
    """
    now = time.time() if now is None else now
    spent = {t: at for t, at in _spend().items() if now - at < WINDOW}
    already = [t for t in HASHTAGS if t in spent]
    room = MAX_HASHTAGS - len(spent)
    fresh = [t for t in HASHTAGS if t not in spent][:max(0, room)]
    return already + fresh


def harvest(tags: list[str] | None = None, per_tag: int = 25) -> dict:
    """Top posts under each hashtag we can afford to ask about.

    Returns {"ok", "posts", "asked", "why"}. Never raises for a missing token or
    a wrong account type: a page with no hashtag search still has Bluesky, and
    this is an extra source rather than a dependency.
    """
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    user = os.environ.get("IG_USER_ID", "").strip()
    if not token or not user:
        return {"ok": False, "posts": [], "asked": [], "why": "no Instagram credentials"}
    if token.startswith("IGAAP"):
        return {"ok": False, "posts": [], "asked": [],
                "why": "this is an Instagram-Login token. It can publish but cannot search "
                       "hashtags, which needs a Facebook-Login token and a Business account"}

    now = time.time()
    wanted = tags if tags is not None else affordable(now)
    posts, asked, why = [], [], []
    for tag in wanted:
        try:
            found = _get("ig_hashtag_search", {"user_id": user, "q": tag, "access_token": token})
            hashtag_id = (found.get("data") or [{}])[0].get("id")
            if not hashtag_id:
                why.append(f"{tag}: not found")
                continue
            media = _get(f"{hashtag_id}/top_media", {
                "user_id": user, "access_token": token, "limit": per_tag,
                "fields": "id,caption,like_count,comments_count,media_type,permalink"})
        except NoSearch as refused:
            why.append(f"{tag}: {refused}")
            continue
        _record(tag, now)
        asked.append(tag)
        for item in media.get("data", []):
            caption = (item.get("caption") or "").strip()
            if not caption:
                continue
            posts.append({
                "tag": tag,
                "caption": caption,
                "likes": item.get("like_count") or 0,
                "comments": item.get("comments_count") or 0,
                "type": item.get("media_type", ""),
                "permalink": item.get("permalink", ""),
            })

    # Comments are weighted above likes. A like is a thumb moving; a comment is
    # somebody stopping to type, which is the closest visible thing to the save
    # and the share that the API will not show us.
    posts.sort(key=lambda p: p["comments"] * 8 + p["likes"], reverse=True)
    return {"ok": bool(posts), "posts": posts, "asked": asked, "why": why[:4]}


if __name__ == "__main__":
    print(f"budget: {len(affordable())} of {len(HASHTAGS)} hashtags askable now")
    result = harvest()
    if not result["ok"]:
        print(f"no trends: {result['why']}")
        raise SystemExit(0)
    print(f"asked {', '.join(result['asked'])}, {len(result['posts'])} posts\n")
    for post in result["posts"][:12]:
        first = post["caption"].splitlines()[0][:96]
        print(f"  {post['likes']:>8,}L {post['comments']:>6,}C  #{post['tag']:<22} {first}")
