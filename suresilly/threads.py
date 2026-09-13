"""Post each evening one-liner to Threads too, once Instagram has it.

Best effort: Threads never holds up or undoes an Instagram post. With no
THREADS_USER_ID / THREADS_ACCESS_TOKEN set, it does nothing. Setup and the
60-day token renewal are in docs/threads.md.
"""
from __future__ import annotations

import os
import time

import requests

BASE = "https://graph.threads.net/v1.0"
TOPIC = {"being kind to yourself": "Self Love"}  # Threads' one topic tag; the rest read fine title-cased


class ThreadsError(RuntimeError):
    pass


def credentials() -> tuple[str, str]:
    return os.environ.get("THREADS_USER_ID", ""), os.environ.get("THREADS_ACCESS_TOKEN", "")


def _call(method: str, url: str, **params) -> dict:
    response = requests.request(method, url, timeout=60, **{"data" if method == "POST" else "params": params})
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200:
        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        if error.get("code") == 190:
            raise ThreadsError("the Threads token has expired. Make a new one with docs/threads.md")
        raise ThreadsError(f"Threads said HTTP {response.status_code}: {error.get('message') or response.text[:200]}")
    return body


def publish(post: dict, image_url: str) -> tuple[str, str]:
    """Post the slide with its line as the text. Returns (Threads media id, link or "")."""
    user, token = credentials()
    line = " ".join(post["slides"][0]["text"].replace("[[", "").replace("]]", "").split())[:500]
    topic = post.get("topic", "")
    params = {"media_type": "IMAGE", "image_url": image_url, "text": line, "access_token": token,
              "alt_text": f"{line} A small green donkey is in the corner."}
    if topic:
        params["topic_tag"] = TOPIC.get(topic, topic.title())
    container = _call("POST", f"{BASE}/{user}/threads", **params)["id"]
    for _ in range(20):  # Meta says a container takes about 30 seconds
        status = _call("GET", f"{BASE}/{container}", fields="status,error_message", access_token=token)
        if status.get("status") == "FINISHED":
            break
        if status.get("status") in ("ERROR", "EXPIRED"):
            raise ThreadsError(f"Threads could not take the image: {status.get('error_message') or status['status']}")
        time.sleep(3)
    else:
        raise ThreadsError("Threads took too long to take the image.")
    media = str(_call("POST", f"{BASE}/{user}/threads_publish", creation_id=container, access_token=token).get("id", ""))
    if not media.isdigit():
        raise ThreadsError("Threads gave no post id.")
    try:
        link = _call("GET", f"{BASE}/{media}", fields="permalink", access_token=token).get("permalink", "")
    except (ThreadsError, requests.RequestException):
        link = ""
    return media, link if link.startswith("https://www.threads.") else ""
