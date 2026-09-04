"""A held deck and direct API calls obey the same pause as scheduled builds."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents/skills/suresilly-carousel/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
import post_to_ig
import release
import run_control
import telegram_review


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("SS_HALT", raising=False)
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(run_control, "ROOT", tmp_path)
    monkeypatch.setattr(release, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(release, "PENDING", tmp_path / "state/pending")
    monkeypatch.setattr(post_to_ig.requests, "post", lambda *a, **k: pytest.fail("unexpected live post"))


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", " YES ", "typo"])
def test_pause_values_fail_closed(monkeypatch, value):
    monkeypatch.setenv("SS_HALT", value)
    with pytest.raises(run_control.PostingPaused):
        run_control.require_posting_allowed()


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_explicit_clear_values_are_allowed(monkeypatch, value):
    monkeypatch.setenv("SS_HALT", value)
    run_control.require_posting_allowed()


@pytest.mark.parametrize("kind", ["file", "directory", "broken_symlink"])
def test_any_pause_marker_blocks(tmp_path, kind):
    marker = tmp_path / "state/HALT"
    marker.parent.mkdir()
    if kind == "file":
        marker.write_text("check the artwork")
    elif kind == "directory":
        marker.mkdir()
    else:
        marker.symlink_to(tmp_path / "missing")
    assert run_control.pause_reason()


@pytest.mark.parametrize("call", [
    lambda: post_to_ig.create_image_container("user", "test-token", "https://example.com/image.png"),
    lambda: post_to_ig.create_carousel("user", "test-token", ["1", "2"], "caption"),
    lambda: post_to_ig.publish("user", "test-token", "container"),
])
def test_all_api_write_paths_check_pause(monkeypatch, call):
    monkeypatch.setenv("SS_HALT", "1")
    with pytest.raises(run_control.PostingPaused):
        call()


def hold(tmp_path):
    slug = "20260904_test_aabbcc"
    deck = tmp_path / "carousels" / slug / "carousel.md"
    deck.parent.mkdir(parents=True)
    deck.write_text("test only")
    record = {"slug": slug, "deck": str(deck.relative_to(tmp_path)), "score": 75}
    release.PENDING.mkdir(parents=True)
    marker = release.PENDING / (slug + ".json")
    marker.write_text(json.dumps(record))
    return record, marker, deck


def test_held_publish_is_stopped_before_subprocess(monkeypatch, tmp_path):
    record, marker, _ = hold(tmp_path)
    before = marker.read_bytes()
    monkeypatch.setenv("SS_HALT", "1")
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **k: pytest.fail("started a paused publisher"))
    assert release.publish(record) == 1
    assert marker.read_bytes() == before
    reply = telegram_review.act("publish", record["slug"])
    assert "Paused" in reply and "Nothing was posted" in reply
    assert record["slug"] in telegram_review.act("list", "")


@pytest.mark.parametrize("receipt", [None, {}, {"media_id": "", "deck_slug": "wrong"},
                                    {"media_id": "123", "deck_slug": "wrong"}, "bad-json"])
def test_successful_process_without_valid_receipt_keeps_deck_held(monkeypatch, tmp_path, receipt):
    record, marker, deck = hold(tmp_path)
    if receipt is not None:
        (deck.parent / "published.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="dry run", stderr=""))
    assert release.publish(record) == 1
    assert marker.is_file()


def test_confirmed_post_removes_only_its_held_record(monkeypatch, tmp_path):
    record, marker, deck = hold(tmp_path)
    def confirmed(*a, **k):
        (deck.parent / "published.json").write_text(json.dumps({"media_id": "123", "deck_slug": record["slug"]}))
        return SimpleNamespace(returncode=0, stdout="confirmed", stderr="")
    monkeypatch.setattr(release.subprocess, "run", confirmed)
    assert release.publish(record) == 0
    assert not marker.exists() and deck.is_file()


def test_pause_during_publish_poll_prevents_next_api_write(monkeypatch):
    calls = []
    def not_ready(*a, **k):
        calls.append(1)
        return SimpleNamespace(status_code=400, text="Media is not ready")
    monkeypatch.setattr(post_to_ig.requests, "post", not_ready)
    monkeypatch.setattr(post_to_ig.time, "sleep", lambda _: monkeypatch.setenv("SS_HALT", "1"))
    with pytest.raises(run_control.PostingPaused):
        post_to_ig.publish("user", "test-token", "container")
    assert calls == [1]


def test_both_workflows_pass_pause_into_python():
    for name in ("auto-post.yml", "review.yml"):
        assert "SS_HALT: ${{ vars.SS_HALT }}" in (ROOT / ".github/workflows" / name).read_text()
