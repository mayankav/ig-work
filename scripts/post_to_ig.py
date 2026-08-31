#!/usr/bin/env python3
"""
post_to_ig.py — publish a carousel via Instagram Graph API.

Free, no extra platform. Needs:
  IG_USER_ID, IG_ACCESS_TOKEN (long-lived Page token) in env or GitHub Secrets.

Usage:
  python scripts/post_to_ig.py --carousel carousels/20260828_waiting_mode/carousel.md --base-url https://media.suresilly.com/slides/20260828_waiting_mode/slides
  python scripts/post_to_ig.py --carousel ... --dry-run   # do not publish, just log

Flow per https://developers.facebook.com/docs/instagram-api/content-publishing:
  1. Create 9 image containers: POST /{ig-user}/media image_url=... is_carousel_item=true
  2. Create carousel container: POST /{ig-user}/media media_type=CAROUSEL children=[ids] caption="..."
  3. Publish: POST /{ig-user}/media_publish creation_id=...
  4. Write the published media id into the deck folder as published.json.

Step 4 exists because the id returned by /media_publish used to be printed and
thrown away, and it is the only key that can ever ask Instagram how a deck
performed. scripts/insights.py reads those files days later. Nothing else in
the pipeline reads them, and nothing may.

Image URLs must be public (gh-pages via media.suresilly.com). Caption comes from carousel.md Caption section.
"""

from __future__ import annotations
import argparse, re, os, sys, json, time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not installed — pip install requests")
    sys.exit(1)

GRAPH_FACEBOOK = "https://graph.facebook.com/v20.0"
GRAPH_INSTAGRAM = "https://graph.instagram.com/v21.0"

def graph_base(token: str) -> str:
    """Pick the right API host based on token type.
    IGAAP... tokens come from the new Instagram API → graph.instagram.com
    EAA...  tokens come from Facebook Login       → graph.facebook.com
    """
    if token.startswith("IGAAP"):
        return GRAPH_INSTAGRAM
    return GRAPH_FACEBOOK

# The deck folder is the right home for this. auto-post.yml already `git add`s
# `carousels`, so an id written here is committed by the run that earned it,
# without the posting workflow having to learn anything new.
PUBLISHED_FILENAME = "published.json"


def record_publication(carousel_dir: Path, media_id: str) -> None:
    """Write the published media id next to the deck it belongs to.

    Never raises. By the time this runs the post is already live, so failing the
    job here would blame the wrong step and misreport a deck that did go out.
    A warning is loud enough — the only consequence is that insights.py has one
    fewer deck it can ask about.
    """
    path = carousel_dir / PUBLISHED_FILENAME
    record = {
        "media_id": media_id,
        "deck_slug": carousel_dir.name,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"Recorded media id {media_id} in {path}")
    except OSError as exc:
        print(f"::warning::could not record media id {media_id} in {path}: {exc}", file=sys.stderr)


def parse_caption(md_path: Path) -> str:
    txt = md_path.read_text(encoding="utf-8")
    m = re.search(r"(?is)^##+\s*Caption\s*(.*?)(?=^##+|\Z)", txt, re.M)
    caption = m.group(1).strip() if m else ""
    # Strip markdown headers, keep plain text + hashtags
    # Also append hashtags section if present
    h = re.search(r"(?is)^##+\s*Hashtags\s*(.*?)(?=^##+|\Z)", txt, re.M)
    if h:
        caption = caption.rstrip() + "\n\n" + h.group(1).strip()
    # Fallback: if no Caption block, use first paragraph
    if not caption:
        caption = txt[:500]
    return caption.strip()[:2200]  # IG limit

def list_images(carousel_dir: Path, base_url: str) -> list[str]:
    slides = sorted((carousel_dir / "slides").glob("*.png"))
    if not slides:
        # Fallback: look for slides in carousel_dir itself
        slides = sorted(carousel_dir.glob("*.png"))
    if not slides:
        sys.exit(f"No PNGs found in {carousel_dir}/slides")
    # Build public URLs — base_url is like https://media.suresilly.com/slides/<slug>/slides
    base_url = base_url.rstrip("/")
    urls = [f"{base_url}/{p.name}" for p in slides]
    if len(urls) < 2 or len(urls) > 10:
        print(f"Warning: carousel needs 2-10 images, found {len(urls)}", file=sys.stderr)
    return urls

def create_image_container(ig_user_id: str, token: str, image_url: str) -> str:
    base = graph_base(token)
    r = requests.post(f"{base}/{ig_user_id}/media", data={
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": token,
    }, timeout=30)
    if r.status_code != 200:
        print(f"Failed to create image container for {image_url}: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["id"]

def create_carousel(ig_user_id: str, token: str, children: list[str], caption: str) -> str:
    base = graph_base(token)
    r = requests.post(f"{base}/{ig_user_id}/media", data={
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
        "access_token": token,
    }, timeout=30)
    if r.status_code != 200:
        print(f"Failed to create carousel: {r.text}", file=sys.stderr)
        r.raise_for_status()
    return r.json()["id"]

def publish(ig_user_id: str, token: str, creation_id: str) -> str:
    # Poll for finish — carousel needs ~5-10s
    base = graph_base(token)
    for _ in range(12):
        r = requests.post(f"{base}/{ig_user_id}/media_publish", data={
            "creation_id": creation_id,
            "access_token": token,
        }, timeout=30)
        if r.status_code == 200:
            return r.json().get("id", "")
        # If not ready, error is "Media is not ready" — wait and retry
        if "not ready" in r.text.lower():
            time.sleep(5)
            continue
        print(f"Publish failed: {r.text}", file=sys.stderr)
        r.raise_for_status()
    sys.exit("Publish timed out")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--carousel", required=True, help="Path to carousel.md")
    ap.add_argument("--base-url", help="Public base URL for slides, e.g. https://media.suresilly.com/slides/<slug>/slides")
    ap.add_argument("--dry-run", action="store_true", help="Do not call API, just log")
    args = ap.parse_args()

    md_path = Path(args.carousel)
    if not md_path.is_file():
        sys.exit(f"Not found: {md_path}")

    base_url = args.base_url
    if not base_url:
        # Try to infer from slug — assumes gh-pages at media.suresilly.com/slides/<slug>/slides
        slug = md_path.parent.name
        base_url = f"https://media.suresilly.com/slides/{slug}/slides"
        print(f"Inferred base_url: {base_url}")

    carousel_dir = md_path.parent
    caption = parse_caption(md_path)
    print(f"Caption length {len(caption)} chars, {len(caption.split())} words")

    if args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true":
        print(f"DRY RUN — would post {md_path} with {len(list_images(carousel_dir, base_url))} images")
        print(f"Caption preview:\n{caption[:300]}...")
        return

    ig_user_id = os.getenv("IG_USER_ID", "")
    token = os.getenv("IG_ACCESS_TOKEN", "")
    if not ig_user_id or not token:
        print("IG_USER_ID or IG_ACCESS_TOKEN not set — dry run", file=sys.stderr)
        print(f"Would post {len(list_images(carousel_dir, base_url))} images")
        return

    urls = list_images(carousel_dir, base_url)
    print(f"Creating {len(urls)} image containers...")
    children = []
    for url in urls:
        cid = create_image_container(ig_user_id, token, url)
        print(f"  image {url} -> {cid}")
        children.append(cid)
        time.sleep(1)

    print("Creating carousel container...")
    carousel_id = create_carousel(ig_user_id, token, children, caption)
    print(f"Carousel container: {carousel_id}")

    print("Publishing...")
    media_id = publish(ig_user_id, token, carousel_id)
    print(f"Published: https://www.instagram.com/p/{media_id}/")
    if media_id:
        record_publication(carousel_dir, media_id)

if __name__ == "__main__":
    main()
