"""Bounded source recovery, without retrying denied content or changing books."""
import io
from pathlib import Path
import sys
import urllib.error
import importlib.util
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bibliography as bib
import claim_support as support


@pytest.mark.parametrize("status,retries", [(400, 0), (401, 0), (403, 0), (404, 0),
                                           (429, 1), (500, 1), (503, 1)])
def test_only_temporary_http_errors_retry(monkeypatch, status, retries):
    calls, waits = [], []
    def fail(request, **kwargs):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, status, "test", {}, None)
    monkeypatch.setattr(bib.urllib.request, "urlopen", fail)
    monkeypatch.setattr(bib.time, "sleep", waits.append)
    with pytest.raises(bib.Unverified, match=f"HTTP {status}"):
        bib._get("https://openlibrary.org/search.json", {"q": "test"})
    assert len(calls) == 1 + retries
    assert len(waits) == retries


def test_temporary_error_can_recover_once(monkeypatch):
    attempts = []
    def open_url(request, **kwargs):
        attempts.append(request.full_url)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "test", {}, None)
        return io.BytesIO(b'{"docs": []}')
    monkeypatch.setattr(bib.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(bib.time, "sleep", lambda _: None)
    assert bib._get("https://openlibrary.org/search.json", {}) == {"docs": []}
    assert len(attempts) == 2


def test_source_lookup_skips_scanless_catalogue_duplicate(monkeypatch):
    base = {"title": "Test Book", "author_name": ["Test Author"],
            "first_publish_year": 2000, "lcc": ["BF1"]}
    monkeypatch.setattr(bib, "_get", lambda *args: {"docs": [
        {**base, "key": "/works/OL1W", "ia": []},
        {**base, "key": "/works/OL2W", "ia": ["public-edition"]}]})
    book = bib.verify_book("Test Author", "Test Book", 2000, require_scan=True)
    assert book["work_key"] == "/works/OL2W"
    assert book["scan_ids"] == ["public-edition"]


def test_source_lookup_refuses_when_only_scanless_records_exist(monkeypatch):
    monkeypatch.setattr(bib, "_get", lambda *args: {"docs": [{"title": "Test Book",
        "author_name": ["Test Author"], "first_publish_year": 2000, "lcc": ["BF1"]}]})
    with pytest.raises(bib.Unverified, match="no catalogue-linked scan"):
        bib.verify_book("Test Author", "Test Book", 2000, require_scan=True)


@pytest.mark.parametrize("failed_stage", ["metadata", "passage"])
def test_second_catalogue_edition_can_work(failed_stage):
    book = {"work_key": "/works/OL1W", "scan_ids": ["first", "second", "third"]}
    calls = []
    def get(url, params):
        calls.append((url, params))
        scan = url.rsplit("/", 1)[-1] if "/metadata/" in url else params["item_id"]
        if scan == "first" and (("/metadata/" in url) == (failed_stage == "metadata")):
            raise bib.Unverified("the source request failed (HTTP 403)")
        if "/metadata/" in url:
            return {"d1": "ia800204.us.archive.org", "dir": "/27/items/" + scan}
        return {"ia": scan, "matches": [{"text": "A whole source passage is retained.",
                                          "par": [{"page": 4}]}]}
    result = support.passages_for(book, "shared task", get)
    assert result["scan_id"] == "second"
    assert result["work_key"] == book["work_key"]
    assert not any("third" in str(call) for call in calls)


def test_no_more_than_two_editions_are_requested():
    calls = []
    def unavailable(url, params):
        calls.append(url)
        raise bib.Unverified("the source request failed (HTTP 403)")
    with pytest.raises(support.Unsupported, match="HTTP 403"):
        support.passages_for({"work_key": "/works/OL1W", "scan_ids": ["one", "two", "three"]},
                             "shared task", unavailable)
    assert len(calls) == support.MAX_SCANS == 2


def test_wrong_book_reply_never_becomes_a_fallback():
    def get(url, params):
        if "/metadata/" in url:
            return {"d1": "ia800204.us.archive.org", "dir": "/27/items/first"}
        return {"ia": "other-book", "matches": [{"text": "A whole source passage is retained.",
                                                   "par": [{"page": 4}]}]}
    with pytest.raises(support.Unsupported):
        support.passages_for({"work_key": "/works/OL1W", "scan_ids": ["first"]}, "shared task", get)


@pytest.mark.parametrize("status", ["checked", "refused", "error"])
def test_trial_never_changes_active_pool(tmp_path, monkeypatch, status):
    path = Path(__file__).resolve().parents[4] / "scripts/probe_claim_support.py"
    spec = importlib.util.spec_from_file_location("probe_source", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    pool = tmp_path / "citations.json"
    pool.write_text('{"citations": []}')
    before = pool.read_bytes()
    monkeypatch.setattr(bib, "CITATIONS_PATH", pool)
    output = tmp_path / "trial.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--author", "Test Author", "--title", "Test Book",
        "--year", "2000", "--phrase", "shared task", "--claim", "A test claim.", "--output", str(output)])
    def verify(*args, **kwargs):
        if status == "refused":
            exc = bib.Unverified("the control was missed")
            exc.evidence = {"review": {"vetoes": []}}
            raise exc
        if status == "error": raise RuntimeError("test failure")
        return {"id": "test", "claims": ["A test claim."]}
    monkeypatch.setattr(bib, "verify", verify)
    assert probe.main() == (0 if status == "checked" else 1)
    data = json.loads(output.read_text())
    assert data["status"] == status
    assert data["active_pool_changed"] is False
    if status == "refused": assert data["rejected_evidence"]["review"]["vetoes"] == []
    assert pool.read_bytes() == before
    monkeypatch.setattr(bib, "verify", lambda *args: pytest.fail("existing result was retried"))
    old = output.read_bytes()
    with pytest.raises(SystemExit): probe.main()
    assert output.read_bytes() == old
