"""Publish a single image or a carousel through the Instagram Graph API."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PUBLISHED = "published.json"
PENDING = "publication_pending.json"


class InstagramError(RuntimeError):
    pass


def graph_base(token: str) -> str:
    # Instagram-login tokens start IGAA and live on graph.instagram.com.
    return "https://graph.instagram.com/v21.0" if token.startswith("IGAA") else "https://graph.facebook.com/v20.0"


def credentials() -> tuple[str, str]:
    user, token = os.environ.get("IG_USER_ID", ""), os.environ.get("IG_ACCESS_TOKEN", "")
    if not user or not token:
        raise InstagramError("IG_USER_ID or IG_ACCESS_TOKEN is not set. Nothing was posted.")
    return user, token


def _call(method: str, url: str, **params) -> dict:
    response = requests.request(method, url, timeout=60, **{"data" if method == "POST" else "params": params})
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        message = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else ""
        raise InstagramError(f"Instagram said HTTP {response.status_code}: {message or response.text[:200]}")
    return body


def _wait_until_ready(base: str, container: str, token: str, tries: int = 30) -> None:
    for _ in range(tries):
        status = _call("GET", f"{base}/{container}", fields="status_code", access_token=token).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(f"Instagram could not process the upload ({status}).")
        time.sleep(4)
    raise InstagramError("Instagram took too long to process the upload.")


def publish(post: Path, urls: list[str], caption: str) -> str:
    """Post it and return the media id. Never posts the same folder twice."""
    if (post / PUBLISHED).exists():
        return json.loads((post / PUBLISHED).read_text())["media_id"]
    if (post / PENDING).exists():
        raise InstagramError("An earlier attempt may already be live. Check Instagram before trying again.")
    if not 1 <= len(urls) <= 10:
        raise InstagramError(f"A post needs 1 to 10 images, not {len(urls)}.")
    user, token = credentials()
    base = graph_base(token)
    if len(urls) == 1:
        container = _call("POST", f"{base}/{user}/media", image_url=urls[0], caption=caption, access_token=token)["id"]
    else:
        children = []
        for url in urls:
            child = _call("POST", f"{base}/{user}/media", image_url=url, is_carousel_item="true", access_token=token)["id"]
            children.append(child)
        for child in children:
            _wait_until_ready(base, child, token)
        container = _call("POST", f"{base}/{user}/media", media_type="CAROUSEL", children=",".join(children),
                          caption=caption, access_token=token)["id"]
    _wait_until_ready(base, container, token)
    (post / PENDING).write_text(json.dumps({"container_id": container}) + "\n")
    media_id = _call("POST", f"{base}/{user}/media_publish", creation_id=container, access_token=token).get("id", "")
    if not str(media_id).isdigit():
        raise InstagramError("Instagram gave no post id. It may or may not be live. Check before trying again.")
    record = {"media_id": str(media_id), "deck_slug": post.name,
              "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (post / PUBLISHED).write_text(json.dumps(record, indent=2) + "\n")
    (post / PENDING).unlink()
    return str(media_id)


def permalink(media_id: str) -> str:
    _, token = credentials()
    try:
        link = _call("GET", f"{graph_base(token)}/{media_id}", fields="permalink", access_token=token).get("permalink", "")
    except (InstagramError, requests.RequestException):
        return ""
    return link if link.startswith(("https://www.instagram.com/", "https://instagram.com/")) else ""
