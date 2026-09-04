"""Push a deck-bound publication intent before the external publish request.

Only the exact deck's archive and intent are committed. No force push, rebase,
automatic retry, or unrelated staged changes may enter this commit.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/suresilly-carousel/scripts"))
import publication_record
import art_eligibility


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()


def reserve(root, deck, container_id):
    root, deck = Path(root).resolve(), Path(deck).resolve()
    if deck.parent != root / "carousels":
        raise ValueError("Publication must use a deck directly inside this repository's carousels folder.")
    if git(root, "rev-parse", "--show-toplevel") != str(root):
        raise ValueError("Publication state is not in the expected repository.")
    if git(root, "branch", "--show-current") != "main":
        raise ValueError("Publish from the main branch after the release is installed.")
    head = git(root, "rev-parse", "HEAD")
    remote = git(root, "ls-remote", "origin", "refs/heads/main").split()
    if len(remote) != 2 or remote[0] != head:
        raise ValueError("Local and remote main differ. Reconcile state before publishing.")
    for name in ("published.json", "publication_pending.json"):
        marker = deck / name
        if marker.exists() or marker.is_symlink():
            raise ValueError("This deck already has a completed or unresolved publication attempt.")
    paths = [deck / "carousel.md", deck / "contact_sheet.png", deck / "slides/checks.json"]
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("The exact deck archive and render checks must exist before publication.")
    report = json.loads((deck / "slides/checks.json").read_text())
    artwork = report.get("artwork")
    if not isinstance(artwork, dict) or set(artwork) != {str(n) for n in range(1, 10)}:
        raise ValueError("Publication needs checked artwork for all nine slides.")
    for proof in artwork.values():
        for path in art_eligibility.evidence_paths(proof):
            if not path.resolve().is_relative_to(root) or path.is_symlink():
                raise ValueError("Artwork evidence must be inside this repository.")
            if path not in paths:
                paths.append(path)
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    marker = deck / "publication_pending.json"
    publication_record.write_new(marker, {
        "deck_slug": deck.name, "container_id": container_id,
        "status": "publication_requested", "requested_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": hashes,
    })
    names = [str(p.relative_to(root)) for p in paths + [marker]]
    git(root, "add", "--", *names)
    git(root, "-c", "user.name=suresilly-bot", "-c", "user.email=bot@suresilly.com",
        "commit", "--only", "-m", f"auto: reserve publication {deck.name} [skip ci]", "--", *names)
    changed = set(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
    if not changed <= set(names):
        raise ValueError("Unexpected files entered the publication reservation commit.")
    git(root, "push", "origin", "HEAD:refs/heads/main")
    return marker
