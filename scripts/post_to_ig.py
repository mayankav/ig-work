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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/suresilly-carousel/scripts"))
from run_control import PostingPaused, require_posting_allowed
import publication_record
import reserve_publication
from instagram_api import GRAPH_FACEBOOK, GRAPH_INSTAGRAM, PUBLISHED_FILENAME, graph_base

try:
    import requests
except ImportError:
    print("requests not installed — pip install requests")
    sys.exit(1)

# The deck folder is the right home for this. auto-post.yml already `git add`s
# `carousels`, so an id written here is committed by the run that earned it,
# without the posting workflow having to learn anything new.
PUBLICATION_PENDING = "publication_pending.json"


def check_export(carousel_dir: Path, markdown: Path) -> None:
    """Independent last check: only the exact checked PNG set can be posted."""
    import hashlib
    if (carousel_dir / "render-incomplete").exists():
        raise ValueError("The last render did not pass. This deck cannot be posted.")
    slides = carousel_dir / "slides"
    try:
        report = json.loads((slides / "checks.json").read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("This deck has no final-render check record") from exc
    import render_guard
    if not report.get("complete") or not report.get("has_mascots") or not report.get("check_version"):
        raise ValueError("The export is not a complete, checked mascot deck")
    if (report.get("check_version") != render_guard.VERSION
            or report.get("render_contract") != render_guard.contract()):
        raise ValueError("The render checks, templates or fonts changed. Render this deck again.")
    import art_eligibility
    artwork = report.get("artwork")
    if not isinstance(artwork, dict) or set(artwork) != {str(n) for n in range(1, 10)}:
        raise ValueError("The deck has no complete artwork check record")
    for value in artwork.values():
        art_eligibility.check_proof(value)
    if report.get("markdown_sha256") != hashlib.sha256(markdown.read_bytes()).hexdigest():
        raise ValueError("The copy changed after rendering")
    files = {p.name: p for p in slides.glob("*.png")}
    if len(files) != 9 or set(files) != set(report.get("slides", {})):
        raise ValueError("The checked nine-slide set is incomplete or changed")
    for name, path in files.items():
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != report["slides"][name]:
            raise ValueError(f"Slide changed after inspection: {name}")
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[16:24] != (1080).to_bytes(4,"big") + (1350).to_bytes(4,"big"):
            raise ValueError(f"Invalid PNG size: {name}")


def record_publication(carousel_dir: Path, media_id: str) -> None:
    """Write the published media id next to the deck it belongs to.

    Failure is a state-saving error, not permission to publish again. The
    pending marker remains until a complete receipt has been read back.
    """
    path = carousel_dir / PUBLISHED_FILENAME
    record = {
        "media_id": media_id,
        "deck_slug": carousel_dir.name,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if not publication_record.valid(record, carousel_dir.name):
        raise ValueError("Instagram returned an invalid publication id.")
    publication_record.write_new(path, record)
    publication_record.read(path, carousel_dir.name)
    print(f"Recorded media id {media_id} in {path}")


def publication_outputs(**values):
    """Keep API confirmation distinct from the success of saving it."""
    path = os.getenv("GITHUB_OUTPUT")
    if path:
        import uuid
        with open(path, "a", encoding="utf-8") as handle:
            for key, value in values.items():
                delimiter = uuid.uuid4().hex
                handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def strip_markup(text: str) -> str:
    """carousel.md is a source file. Instagram is a text box.

    The deck's markup means something to the renderer — [[accent]] is the word
    the slide colours, **bold** and *italic* are type. Instagram renders none of
    it and prints the characters, so on 2026-09-01 a post went out reading
    "the [[cost]] of carrying the [[street]] across the [[threshold]]".

    Stripped HERE and not only at the writer, because this is where the caption
    stops being ours. A held deck is posted days later by release.py from a
    fresh checkout of a file written by an older engine, carousel.md is
    hand-editable and gets hand-edited, and neither of those paths goes back
    through the writer. The last thing that touches the text before Instagram
    does is the right place to guarantee what Instagram gets.

    Deliberately its own regex rather than an import of render.plain(): the
    engine does not import this file and this file does not import the engine.
    """
    text = re.sub(r"\[\[|\]\]", "", text)
    return re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)


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
    # One strip, on the way out, so no branch above can skip it — the fallback
    # takes raw markdown off the top of the file and is the likeliest of all of
    # them to carry markup.
    return strip_markup(caption.strip())[:2200]  # IG limit

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

def check_hosted_images(carousel_dir: Path, urls: list[str]) -> None:
    """Instagram must receive the exact nine checked files, not merely live URLs."""
    import hashlib
    from urllib.parse import urlsplit
    files = sorted((carousel_dir / "slides").glob("*.png"))
    if len(files) != 9 or len(urls) != 9:
        raise ValueError("Hosting check needs exactly nine images")
    for path, url in zip(files, urls):
        require_posting_allowed()
        if urlsplit(url).scheme != "https":
            raise ValueError("Hosted slides must use HTTPS")
        expected = path.read_bytes()
        digest, count = hashlib.sha256(), 0
        with requests.get(url, stream=True, timeout=(5, 10), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError(f"Hosted slide {path.name} returned HTTP {response.status_code}")
            for chunk in response.iter_content(chunk_size=65536):
                count += len(chunk)
                if count > len(expected):
                    raise ValueError(f"Hosted slide differs from the checked file: {path.name}")
                digest.update(chunk)
        if count != len(expected) or digest.hexdigest() != hashlib.sha256(expected).hexdigest():
            raise ValueError(f"Hosted slide differs from the checked file: {path.name}")


def create_image_container(ig_user_id: str, token: str, image_url: str) -> str:
    require_posting_allowed()
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
    require_posting_allowed()
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
        require_posting_allowed()
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
    ap.add_argument("--recover", action="store_true", help="Check saved publication state and reuse the original request")
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
    for name in (PUBLISHED_FILENAME, PUBLICATION_PENDING):
        marker = carousel_dir / name
        if marker.is_symlink():
            sys.exit("Publication record is a link. Nothing was posted.")
        if marker.exists() and not args.recover:
            sys.exit("This deck has a completed or unresolved publication record. Refusing a duplicate post.")
    caption = parse_caption(md_path)
    print(f"Caption length {len(caption)} chars, {len(caption.split())} words")

    if args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true":
        print(f"DRY RUN — would post {md_path} with {len(list_images(carousel_dir, base_url))} images")
        print(f"Caption preview:\n{caption[:300]}...")
        return

    require_posting_allowed()

    # Held decks can predate source checks. A manual publish cannot turn a
    # book-level flag into evidence for the exact sentence about to be sent.
    import bibliography
    bibliography.require_deck_support(md_path.read_text(encoding="utf-8"))

    ig_user_id = os.getenv("IG_USER_ID", "")
    token = os.getenv("IG_ACCESS_TOKEN", "")
    if not ig_user_id or not token:
        sys.exit("IG_USER_ID or IG_ACCESS_TOKEN not set. Nothing was posted.")

    if args.recover:
        import reconcile_publication
        reconcile_publication.require_owner(Path(__file__).resolve().parents[1], carousel_dir.name,
                                             os.getenv("SLOT_ID", ""), os.getenv("GITHUB_RUN_ID", ""))

    if args.recover and (Path(__file__).resolve().parents[1] / "state/pending" / f"{carousel_dir.name}.json").exists():
        sys.exit("This deck is held. Use the separate publish decision.")

    if args.recover and (carousel_dir / PUBLISHED_FILENAME).exists():
        receipt = publication_record.read(carousel_dir / PUBLISHED_FILENAME, carousel_dir.name)
        publication_outputs(confirmed_media_id=receipt['media_id'], confirmed_deck_slug=carousel_dir.name)
        print("This deck already has a confirmed post. Nothing was sent.")
        return

    check_export(carousel_dir, md_path)

    if args.recover and (carousel_dir / PUBLICATION_PENDING).exists():
        import reconcile_publication
        pending_record = reconcile_publication.read_pending(Path(__file__).resolve().parents[1], carousel_dir.resolve())
        state, identifier = reconcile_publication.inspect(
            requests, graph_base(token), ig_user_id, token, pending_record, caption)
        if state == "ready":
            check_hosted_images(carousel_dir, list_images(carousel_dir, base_url))
            identifier = publish(ig_user_id, token, identifier)
        publication_outputs(confirmed_media_id=identifier, confirmed_deck_slug=carousel_dir.name)
        record_publication(carousel_dir, identifier)
        (carousel_dir / PUBLICATION_PENDING).unlink()
        return

    urls = list_images(carousel_dir, base_url)
    if len(urls) != 9:
        sys.exit(f"A post needs exactly nine images; found {len(urls)}.")
    try:
        check_hosted_images(carousel_dir, urls)
    except (OSError, ValueError, requests.RequestException) as exc:
        reason = f"Hosted slides failed the final check: {exc}. Nothing was posted."
        publication_outputs(stage="hosting", reason=reason)
        sys.exit(reason)
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
    try:
        pending = reserve_publication.reserve(Path(__file__).resolve().parents[1], carousel_dir, carousel_id)
    except (OSError, ValueError, reserve_publication.subprocess.CalledProcessError) as exc:
        reason = f"The publication intent could not be saved remotely: {type(exc).__name__}. Nothing was published."
        publication_outputs(stage="state saving", reason=reason)
        sys.exit(reason)
    media_id = publish(ig_user_id, token, carousel_id)
    if not media_id:
        sys.exit("Instagram returned no post id. Publication is not confirmed. Do not retry blindly.")
    print(f"Instagram confirmed media id: {media_id}")
    publication_outputs(confirmed_media_id=media_id, confirmed_deck_slug=carousel_dir.name)
    try:
        record_publication(carousel_dir, media_id)
        pending.unlink()
    except (OSError, ValueError) as exc:
        reason = f"Instagram returned media {media_id}, but saving its record failed: {exc}. Do not post again."
        publication_outputs(stage="state saving", reason=reason)
        sys.exit(reason)

if __name__ == "__main__":
    try:
        main()
    except PostingPaused as exc:
        sys.exit(str(exc))
