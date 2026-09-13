"""The Telegram review window: a fixed preview, and the Worker that holds its decision.

The Worker (ops/dispatch-worker) keeps one record per preview token. It sends the
preview, starts a one-hour timer, and turns replies (approve / disapprove / redo)
into review-window.yml runs. This module is the Python side of that contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = re.compile(r"[a-f0-9]{16}")
MEDIA = "https://media.suresilly.com"
RECORD = "review.json"


def files(post: Path) -> dict[str, str]:
    paths = [post / "post.json", post / "caption.txt", post / "contact_sheet.png"]
    paths += sorted((post / "slides").glob("*.jpg"))
    if any(not path.is_file() or path.is_symlink() for path in paths) or len(paths) < 4:
        raise ValueError("The post folder is incomplete.")
    if (post / "reel.mp4").is_file() and not (post / "reel.mp4").is_symlink():
        paths.append(post / "reel.mp4")
    return {str(path.relative_to(post)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(post: Path, parent: str | None = None) -> dict:
    """Freeze this exact post under a new preview token."""
    if (post / "published.json").exists():
        raise ValueError("This post is already on Instagram.")
    record = {"token": secrets.token_hex(8), "slug": post.name, "files": files(post), "parent": parent}
    record["manifest"] = digest(record["files"])
    (post / RECORD).write_text(json.dumps(record, indent=2) + "\n")
    return record


def read(post: Path) -> dict:
    record = json.loads((post / RECORD).read_text())
    if (not TOKEN.fullmatch(record.get("token", "")) or record.get("slug") != post.name
            or record.get("files") != files(post) or record.get("manifest") != digest(record["files"])):
        raise ValueError("The post changed after its preview was made.")
    return record


def base_url(record: dict) -> str:
    return f"{MEDIA}/slides/{record['slug']}/reviews/{record['token']}"


def slide_urls(record: dict) -> list[str]:
    names = sorted(name for name in record["files"] if name.startswith("slides/"))
    return [f"{base_url(record)}/{name}" for name in names]


def reel_url(record: dict) -> str:
    """Where the frozen Reel is hosted, or "" for a post that goes out as images."""
    return f"{base_url(record)}/reel.mp4" if "reel.mp4" in record["files"] else ""


def api(token: str, operation: str, body: dict | None = None) -> dict:
    if not TOKEN.fullmatch(token or "") or operation not in ("register", "status", "claim", "complete"):
        raise ValueError("Invalid review request.")
    base = os.environ.get("REVIEW_WINDOW_URL", "").rstrip("/")
    key = os.environ.get("REVIEW_WINDOW_SECRET", "")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or not key:
        raise ValueError("The review service is not configured (REVIEW_WINDOW_URL / REVIEW_WINDOW_SECRET).")
    request = urllib.request.Request(
        f"{base}/review/{token}/{operation}", data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "suresilly/2.0", "X-Review-Key": key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("error", "")
        except ValueError:
            detail = ""
        raise ValueError(f"The review service refused {operation}: {detail or exc.code}") from exc
    if not isinstance(result, dict) or result.get("error"):
        raise ValueError(f"The review service refused {operation}: {result.get('error', 'no reason')}")
    return result


def save_history(root: Path, token: str) -> None:
    history = root / "state" / "reviews"
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{token}.json").write_text(json.dumps(api(token, "status"), indent=2) + "\n")
