"""Real local git remotes prove that publication intent survives runner loss."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import reserve_publication as reservation
from test_posting_slots import repos, git
from art_review_fixture import offline_reviewer, check_fixture
import art_eligibility


def deck_at(checkout, monkeypatch):
    deck = checkout / "carousels/test-deck"
    (deck / "slides").mkdir(parents=True)
    (deck / "carousel.md").write_text("exact test copy")
    (deck / "contact_sheet.png").write_bytes(b"test archive image")
    offline_reviewer(monkeypatch, checkout / ".agents/skills/suresilly-carousel/mascot")
    pose = ROOT / ".agents/skills/suresilly-carousel/mascot/library/deadpan.png"
    check_fixture([pose])
    proof = art_eligibility.proof(pose.read_bytes())
    (deck / "slides/checks.json").write_text(json.dumps({
        "artwork": {str(n):proof for n in range(1,10)}}))
    return deck


def test_remote_intent_and_archive_survive_new_checkout(tmp_path, monkeypatch):
    origin, one, _ = repos(tmp_path)
    deck = deck_at(one, monkeypatch)
    reservation.reserve(one, deck, "container-123")
    new = tmp_path / "replacement-runner"
    git(tmp_path, "clone", str(origin), str(new))
    marker = new / "carousels/test-deck/publication_pending.json"
    record = json.loads(marker.read_text())
    assert record["container_id"] == "container-123"
    assert (new / "carousels/test-deck/carousel.md").read_text() == "exact test copy"
    assert len(record["artifacts"]) == 5
    monkeypatch.setattr(art_eligibility, "STORE", new / ".agents/skills/suresilly-carousel/mascot/checks")
    report = json.loads((new / "carousels/test-deck/slides/checks.json").read_text())
    for proof in report["artwork"].values():
        art_eligibility.check_proof(proof)
    with pytest.raises(ValueError, match="unresolved"):
        reservation.reserve(new, new / "carousels/test-deck", "another-container")


def test_only_deck_files_are_committed_and_user_index_is_preserved(tmp_path, monkeypatch):
    origin, one, _ = repos(tmp_path)
    deck = deck_at(one, monkeypatch)
    (one / "README.md").write_text("user staged edit")
    git(one, "add", "README.md")
    (one / "README.md").write_text("user unstaged edit")
    reservation.reserve(one, deck, "container-123")
    assert git(origin, "show", "main:README.md") == "test"
    assert git(one, "show", ":README.md") == "user staged edit"
    assert (one / "README.md").read_text() == "user unstaged edit"
    assert git(one, "diff", "--cached", "--name-only") == "README.md"


def test_stale_main_cannot_reserve(tmp_path, monkeypatch):
    _, one, two = repos(tmp_path)
    deck = deck_at(one, monkeypatch)
    (two / "README.md").write_text("remote changed")
    git(two, "add", "README.md")
    git(two, "-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-m", "advance")
    git(two, "push", "origin", "main")
    with pytest.raises(ValueError, match="differ"):
        reservation.reserve(one, deck, "container-123")
    assert not (deck / "publication_pending.json").exists()


@pytest.mark.parametrize("ack_lost", [False, True])
def test_push_failure_never_returns_permission(tmp_path, monkeypatch, ack_lost):
    origin, one, _ = repos(tmp_path)
    deck = deck_at(one, monkeypatch)
    real_git = reservation.git
    def interrupted(root, *args):
        if args[0] == "push":
            if ack_lost:
                real_git(root, *args)
            raise subprocess.CalledProcessError(1, ["git", *args])
        return real_git(root, *args)
    monkeypatch.setattr(reservation, "git", interrupted)
    with pytest.raises(subprocess.CalledProcessError):
        reservation.reserve(one, deck, "container-123")
    assert (deck / "publication_pending.json").is_file()
    if ack_lost:
        assert "container-123" in git(origin, "show", "main:carousels/test-deck/publication_pending.json")


def test_non_main_branch_cannot_push_feature_commits_as_publication(tmp_path, monkeypatch):
    _, one, _ = repos(tmp_path)
    deck = deck_at(one, monkeypatch)
    git(one, "switch", "-c", "codex/test-only")
    with pytest.raises(ValueError, match="main branch"):
        reservation.reserve(one, deck, "container-123")
    assert not (deck / "publication_pending.json").exists()
