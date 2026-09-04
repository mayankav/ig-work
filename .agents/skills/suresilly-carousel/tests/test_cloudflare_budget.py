"""No real credentials, ledger changes or HTTP requests in spending tests."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cloudflare_budget as budget
import llm
import neurons


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(neurons, "LEDGER_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(llm, "resolve_key", lambda _: "test-only")
    monkeypatch.setattr(llm, "_pace", lambda _: None)
    monkeypatch.setattr(llm, "_post", lambda *a, **k: pytest.fail("unexpected HTTP request"))
    return neurons.Ledger()


@pytest.mark.parametrize("image,model,output", [
    (None, llm.CLOUDFLARE_MODEL, budget.TEXT_OUTPUT),
    (b"test-image", llm.CLOUDFLARE_VISION_MODEL, budget.VISION_OUTPUT)])
def test_request_is_reserved_before_http(isolated, monkeypatch, image, model, output):
    expected = budget.reservation(model, output)
    def request(url, payload, headers, **kwargs):
        assert isolated.text_spent() == expected
        assert payload["max_tokens"] == output
        assert url.endswith(model)
        return {"result": {"response": "{}"}}
    monkeypatch.setattr(llm, "_post", request)
    assert llm.call_cloudflare("system", "user", 0.2, image=image) == "{}"
    assert isolated.text_spent() == expected


def test_exhaustion_stops_before_http(isolated):
    isolated.spend_text(neurons.FREE_DAILY_NEURONS)
    with pytest.raises(llm.ModelRefused, match="spending stopped"):
        llm.call_cloudflare("system", "user", 0.2)


def test_cannot_save_reservation_means_no_request(isolated, monkeypatch):
    def fail(*a):
        raise OSError("disk full")
    monkeypatch.setattr(neurons.os, "replace", fail)
    with pytest.raises(llm.ModelRefused, match="spending stopped"):
        llm.call_cloudflare("system", "user", 0.2)


def test_failed_request_is_not_refunded(isolated, monkeypatch):
    def fail(*a, **k):
        raise TimeoutError("no response")
    monkeypatch.setattr(llm, "_post", fail)
    with pytest.raises(TimeoutError):
        llm.call_cloudflare("system", "user", 0.2)
    assert isolated.text_spent() == budget.reservation(llm.CLOUDFLARE_MODEL, budget.TEXT_OUTPUT)


@pytest.mark.parametrize("header", ["0", "bad", "NaN", "9999"])
def test_headers_only_raise_recorded_spend(isolated, monkeypatch, header):
    def request(*a, capture, **k):
        capture["cf-ai-neurons"] = header
        return {"result": {"response": "{}"}}
    monkeypatch.setattr(llm, "_post", request)
    llm.call_cloudflare("system", "user", 0.2)
    expected = budget.reservation(llm.CLOUDFLARE_MODEL, budget.TEXT_OUTPUT)
    assert isolated.text_spent() == (9999 if header == "9999" else expected)


@pytest.mark.parametrize("model,output", [("unpriced", 1), (llm.CLOUDFLARE_MODEL, 0),
    (llm.CLOUDFLARE_MODEL, True), (llm.CLOUDFLARE_MODEL, 25000)])
def test_unknown_or_unbounded_request_is_refused(model, output):
    with pytest.raises(ValueError):
        budget.reservation(model, output)
