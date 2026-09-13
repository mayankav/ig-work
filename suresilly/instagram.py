"""Publish a single image, a carousel or a Reel through the Instagram Graph API."""
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


def alt_text(slide_text: str) -> str:
    """What a screen reader hears for one slide: its own words, then the donkey."""
    words = " ".join(slide_text.replace("[[", "").replace("]]", "").split())
    if words[-1:].isalnum():
        words += "."
    return f"{words} A small green donkey is in the corner.".strip()[:1000]  # Instagram's limit


def _image(base: str, user: str, token: str, alt: str, **params) -> str:
    """Make one image container. Alt text is a nice-to-have: if Instagram refuses the call, try once without it."""
    if alt:
        try:
            return _call("POST", f"{base}/{user}/media", alt_text=alt, access_token=token, **params)["id"]
        except InstagramError as error:
            print(f"Trying this image again without alt text: {error}")
    return _call("POST", f"{base}/{user}/media", access_token=token, **params)["id"]


def _alt_text_live(base: str, media_id: str, token: str, carousel: bool) -> str:
    """How many images show alt text on Instagram now, like "7/8". Only a note, so it never raises."""
    try:
        media = _call("GET", f"{base}/{media_id}", fields="children{alt_text}" if carousel else "alt_text",
                      access_token=token)
        images = media["children"]["data"] if carousel else [media]
        return f"{sum(bool(image.get('alt_text')) for image in images)}/{len(images)}"
    except Exception as error:  # the post is already live; a failed check must not look like a failed post
        return f"unknown: {error}"


def _already(post: Path) -> str:
    """The media id if this folder is already live; raises if an earlier attempt may be."""
    if (post / PUBLISHED).exists():
        return json.loads((post / PUBLISHED).read_text())["media_id"]
    if (post / PENDING).exists():
        raise InstagramError("An earlier attempt may already be live. Check Instagram before trying again.")
    return ""


def _go_live(post: Path, base: str, user: str, token: str, container: str) -> dict:
    """Publish a finished container and write the receipt."""
    (post / PENDING).write_text(json.dumps({"container_id": container}) + "\n")
    media_id = _call("POST", f"{base}/{user}/media_publish", creation_id=container, access_token=token).get("id", "")
    if not str(media_id).isdigit():
        raise InstagramError("Instagram gave no post id. It may or may not be live. Check before trying again.")
    record = {"media_id": str(media_id), "deck_slug": post.name,
              "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    (post / PUBLISHED).write_text(json.dumps(record, indent=2) + "\n")
    (post / PENDING).unlink()
    return record


def publish_reel(post: Path, video_url: str, caption: str) -> str:
    """Post the video as a Reel that also shows on the grid, and return the media id. Never twice."""
    if done := _already(post):
        return done
    user, token = credentials()
    base = graph_base(token)
    container = _call("POST", f"{base}/{user}/media", media_type="REELS", video_url=video_url, caption=caption,
                      share_to_feed="true", access_token=token)["id"]
    _wait_until_ready(base, container, token, tries=75)  # a video takes longer than an image: allow 5 minutes
    return _go_live(post, base, user, token, container)["media_id"]


def publish(post: Path, urls: list[str], caption: str, alts: list[str] | None = None) -> str:
    """Post it and return the media id. Never posts the same folder twice."""
    if done := _already(post):
        return done
    if not 1 <= len(urls) <= 10:
        raise InstagramError(f"A post needs 1 to 10 images, not {len(urls)}.")
    if len(alts or []) != len(urls):
        alts = [""] * len(urls)  # never describe a slide with another slide's words
    user, token = credentials()
    base = graph_base(token)
    if len(urls) == 1:
        container = _image(base, user, token, alts[0], image_url=urls[0], caption=caption)
    else:
        children = [_image(base, user, token, alt, image_url=url, is_carousel_item="true")
                    for url, alt in zip(urls, alts)]
        for child in children:
            _wait_until_ready(base, child, token)
        container = _call("POST", f"{base}/{user}/media", media_type="CAROUSEL", children=",".join(children),
                          caption=caption, access_token=token)["id"]
    _wait_until_ready(base, container, token)
    record = _go_live(post, base, user, token, container)
    if any(alts):
        record["alt_text"] = _alt_text_live(base, record["media_id"], token, len(urls) > 1)
        (post / PUBLISHED).write_text(json.dumps(record, indent=2) + "\n")
    return record["media_id"]


def permalink(media_id: str) -> str:
    _, token = credentials()
    try:
        link = _call("GET", f"{graph_base(token)}/{media_id}", fields="permalink", access_token=token).get("permalink", "")
    except (InstagramError, requests.RequestException):
        return ""
    return link if link.startswith(("https://www.instagram.com/", "https://instagram.com/")) else ""
