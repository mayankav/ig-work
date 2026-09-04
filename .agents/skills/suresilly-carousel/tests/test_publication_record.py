"""No live API: receipt durability and ambiguous-publication duplicate guards."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".agents/skills/suresilly-carousel/scripts"))
import bibliography
import post_to_ig as post
import publication_record as records
import run as runner


def test_receipt_write_is_complete_and_never_overwrites(tmp_path):
    value = {"media_id": "123", "deck_slug": tmp_path.name}
    path = tmp_path / "published.json"
    records.write_new(path, value)
    assert records.read(path, tmp_path.name) == value
    with pytest.raises(FileExistsError):
        records.write_new(path, value | {"media_id": "456"})
    assert records.read(path, tmp_path.name) == value
    assert list(tmp_path.glob(".publication-*")) == []


def test_failed_final_write_does_not_expose_partial_json(tmp_path, monkeypatch):
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(records.os, "link", fail)
    path = tmp_path / "published.json"
    with pytest.raises(OSError, match="disk full"):
        records.write_new(path, {"media_id": "123", "deck_slug": tmp_path.name})
    assert not path.exists() and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("marker", ["published.json", "publication_pending.json"])
@pytest.mark.parametrize("kind", ["file", "directory", "broken_symlink"])
def test_publication_markers_also_block_rebuilding_the_archive(tmp_path, monkeypatch, marker, kind):
    monkeypatch.setattr(runner, "CAROUSELS", tmp_path)
    folder = tmp_path / "deck"
    folder.mkdir()
    original = folder / "carousel.md"
    original.write_text("preserve this exact copy")
    path = folder / marker
    if kind == "file":
        path.write_text("[]")
    elif kind == "directory":
        path.mkdir()
    else:
        path.symlink_to(folder / "missing")
    with pytest.raises(runner.Stop):
        runner.write_deck("replacement", "deck")
    assert original.read_text() == "preserve this exact copy"


@pytest.mark.parametrize("failure", [None, "publish", "save", "reserve"])
def test_post_attempt_keeps_guard_until_receipt_is_confirmed(tmp_path, monkeypatch, failure):
    deck = tmp_path / "carousel.md"
    deck.write_text("isolated test deck")
    output = tmp_path / "outputs.txt"
    monkeypatch.setattr(sys, "argv", ["post_to_ig.py", "--carousel", str(deck)])
    monkeypatch.setenv("IG_USER_ID", "test-user")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "test-token-not-real")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(post, "require_posting_allowed", lambda: None)
    monkeypatch.setattr(bibliography, "require_deck_support", lambda *a: None)
    monkeypatch.setattr(post, "check_export", lambda *a: None)
    monkeypatch.setattr(post, "parse_caption", lambda *a: "test caption")
    # Exercise the real hosting gate before testing receipt recovery. The old
    # fixture had URLs but no slide files, so it now correctly stops too early.
    from contextlib import contextmanager
    from types import SimpleNamespace
    slides = tmp_path / "slides"
    slides.mkdir()
    for number in range(1, 10):
        (slides / f"{number:02}.png").write_bytes(b"isolated checked slide")
    hosted_calls = []
    @contextmanager
    def hosted(url, **kwargs):
        hosted_calls.append(url)
        yield SimpleNamespace(status_code=200, iter_content=lambda **k: [b"isolated checked slide"])
    monkeypatch.setattr(post.requests, "get", hosted)
    monkeypatch.setattr(post.time, "sleep", lambda *a: None)
    monkeypatch.setattr(post, "create_image_container", lambda *a: "child")
    monkeypatch.setattr(post, "create_carousel", lambda *a: "carousel-container")
    # Remote reservation itself is covered with real git remotes separately.
    def reserve(root, folder, container):
        if failure == "reserve":
            raise OSError("remote intent push failed")
        marker = folder / post.PUBLICATION_PENDING
        records.write_new(marker, {"container_id": container})
        return marker
    monkeypatch.setattr(post.reserve_publication, "reserve", reserve)
    calls = []
    def publish(*args):
        calls.append(args)
        assert json.loads((tmp_path / post.PUBLICATION_PENDING).read_text())["container_id"] == "carousel-container"
        if failure == "publish":
            raise TimeoutError("response lost")
        return "123"
    monkeypatch.setattr(post, "publish", publish)
    if failure == "save":
        monkeypatch.setattr(post, "record_publication", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    if failure:
        with pytest.raises((TimeoutError, SystemExit)):
            post.main()
        if failure == "reserve":
            assert calls == [] and not (tmp_path / post.PUBLICATION_PENDING).exists()
            assert "state saving" in output.read_text()
            return
        assert (tmp_path / post.PUBLICATION_PENDING).exists()
        assert not (tmp_path / post.PUBLISHED_FILENAME).exists()
        if failure == "save":
            assert "confirmed_media_id<<" in output.read_text()
            assert "state saving" in output.read_text()
    else:
        post.main()
        assert not (tmp_path / post.PUBLICATION_PENDING).exists()
        assert records.read(tmp_path / post.PUBLISHED_FILENAME, tmp_path.name)["media_id"] == "123"
    assert len(hosted_calls) == 9
    with pytest.raises(SystemExit, match="Refusing a duplicate"):
        post.main()
    assert len(calls) == 1
