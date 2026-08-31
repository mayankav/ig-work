#!/usr/bin/env python3
"""
Vendor quota snapshots. No network is touched.

CREDITS.md claimed for months that Groq "does not report a cost per call, so it
cannot be counted". The number was arriving on every single response and being
dropped on the floor, because `_post` only passed a capture dict for the
Cloudflare call. These tests pin the three things that made that claim survive
so long: that the header is read, that it is read on the failure path too, and
that a vendor which reports nothing is recorded as nothing rather than as a
vendor with room to spare.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import llm  # noqa: E402
import quotas  # noqa: E402

# Captured live on 2026-08-31 from openai/gpt-oss-120b. Not invented.
LIVE = {
    "x-ratelimit-limit-requests": "1000",
    "x-ratelimit-remaining-requests": "999",
    "x-ratelimit-limit-tokens": "8000",
    "x-ratelimit-remaining-tokens": "7922",
    "x-ratelimit-reset-requests": "1m26.4s",
    "x-ratelimit-reset-tokens": "585ms",
}


@pytest.mark.parametrize("text,seconds", [
    ("1m26.4s", 86.4),
    ("585ms", 0.585),      # milliseconds, NOT 585 minutes
    ("7.66s", 7.66),
    ("2h30m", 9000.0),
    ("0s", 0.0),           # full right now — a real reading
])
def test_durations_parse(text, seconds):
    assert quotas.parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["", None, "nonsense", "later"])
def test_unreadable_duration_is_absent_not_zero(text):
    """Zero means the bucket is full. Absent means we could not tell. Collapsing
    the two would report an exhausted vendor as a fully refilled one."""
    assert quotas.parse_duration(text) is None


def test_records_what_the_vendor_reported(tmp_path):
    path = tmp_path / "q.json"
    quotas.record("groq", "openai/gpt-oss-120b", LIVE, path=path)
    got = json.loads(path.read_text())["groq"]

    assert got["model"] == "openai/gpt-oss-120b"
    # Requests are the DAILY dimension and tokens the per-minute one; the
    # arithmetic that proves it is 86.4s x 1000 = 86,400s = one day.
    assert got["requests"] == {"limit": 1000, "remaining": 999,
                               "reset_seconds": 86.4}
    assert got["tokens"]["limit"] == 8000
    assert got["tokens"]["reset_seconds"] == pytest.approx(0.585)


def test_counts_are_integers(tmp_path):
    """999, not 999.0 — the file is read by a person as often as by code."""
    path = tmp_path / "q.json"
    quotas.record("groq", "m", LIVE, path=path)
    assert '"remaining": 999' in path.read_text()


def test_no_quota_headers_records_nothing(tmp_path):
    """Gemini's case, measured: a successful call carries no quota header at
    all. That must leave no record, never a record that looks full."""
    path = tmp_path / "q.json"
    assert quotas.record("gemini", "gemini-2.5-flash", {"content-type": "application/json"},
                         path=path) is None
    assert not path.exists()


def test_zero_remaining_is_recorded(tmp_path):
    """The opposite rule, and the reason the two are separate tests: a reported
    zero is a measurement and must survive."""
    path = tmp_path / "q.json"
    quotas.record("groq", "m", {**LIVE, "x-ratelimit-remaining-requests": "0"},
                  path=path)
    assert json.loads(path.read_text())["groq"]["requests"]["remaining"] == 0


def test_a_different_model_replaces_rather_than_merges(tmp_path):
    """Limits are per model. Merging one model's remaining into another's
    reading would produce a number no vendor could account for."""
    path = tmp_path / "q.json"
    quotas.record("groq", "old-model", LIVE, path=path)
    quotas.record("groq", "new-model", {"x-ratelimit-limit-requests": "14400",
                                        "x-ratelimit-remaining-requests": "14400"},
                  path=path)
    got = json.loads(path.read_text())["groq"]
    assert got["model"] == "new-model"
    assert got["requests"]["limit"] == 14400
    assert "tokens" not in got          # not carried over from the old reading


def test_record_never_raises(tmp_path):
    """A quota file that cannot be written must never cost a deck."""
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory")
    assert quotas.record("groq", "m", LIVE, path=blocked / "q.json") is None


def test_age_is_none_when_undated():
    assert quotas.age_seconds({"model": "m"}) is None
    assert quotas.age_seconds(None) is None


# ── the wiring, which is the half that was actually broken ───────────────────

class _Response:
    def __init__(self, headers, body):
        self.headers = headers
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_post_captures_headers_on_success(monkeypatch):
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda req, timeout=None: _Response(LIVE, {"ok": 1}))
    got: dict = {}
    llm._post("https://example.invalid", {}, {}, capture=got)
    assert got["x-ratelimit-remaining-requests"] == "999"


def test_post_captures_headers_on_429(monkeypatch):
    """The reading is most valuable on the response that says the allowance is
    gone. Dropping those headers is why the report could only ever show a
    vendor with room to spare."""
    import email.message
    headers = email.message.Message()
    for k, v in {**LIVE, "x-ratelimit-remaining-requests": "0"}.items():
        headers[k] = v

    def boom(req, timeout=None):
        raise llm.urllib.error.HTTPError(
            "https://example.invalid", 429, "Too Many Requests", headers, None)

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    got: dict = {}
    with pytest.raises(llm.RateLimited):
        llm._post("https://example.invalid", {}, {}, capture=got)
    assert got["x-ratelimit-remaining-requests"] == "0"


def test_call_groq_records_even_when_the_call_fails(monkeypatch, tmp_path):
    path = tmp_path / "q.json"
    monkeypatch.setattr(quotas, "QUOTAS_PATH", path)
    monkeypatch.setattr(llm, "resolve_key", lambda name: "key")
    monkeypatch.setattr(llm, "_pace", lambda provider: None)

    def refuse(url, payload, headers, capture=None):
        capture.update({**LIVE, "x-ratelimit-remaining-requests": "0"})
        raise llm.RateLimited("HTTP 429", 30)

    monkeypatch.setattr(llm, "_post", refuse)
    with pytest.raises(llm.RateLimited):
        llm.call_groq("s", "u", 0.0)

    got = json.loads(path.read_text())["groq"]
    assert got["requests"]["remaining"] == 0
    assert got["model"] == llm.GROQ_MODEL


def test_call_groq_records_on_success(monkeypatch, tmp_path):
    path = tmp_path / "q.json"
    monkeypatch.setattr(quotas, "QUOTAS_PATH", path)
    monkeypatch.setattr(llm, "resolve_key", lambda name: "key")
    monkeypatch.setattr(llm, "_pace", lambda provider: None)

    def reply(url, payload, headers, capture=None):
        capture.update(LIVE)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm, "_post", reply)
    assert llm.call_groq("s", "u", 0.0) == "ok"
    assert json.loads(path.read_text())["groq"]["requests"]["remaining"] == 999


# ── how the reading reaches a person ─────────────────────────────────────────
#
# The dashboard tests live in test_fresh_poses.py, but these are about the
# quota surface rather than the report, so they sit with the thing they pin.

ROOT = pathlib.Path(__file__).resolve().parents[3].parent
sys.path.insert(0, str(ROOT / "scripts"))


def _vendors(*records):
    import capacity
    return list(records)


def test_rows_stay_collapsed_when_nothing_is_low(monkeypatch):
    """Three vendor lines every morning is three lines you learn to skip, and
    the morning they matter you skip them too."""
    import capacity
    import dashboard
    monkeypatch.setattr(capacity, "snapshot", lambda: {"vendors": _vendors(
        {"name": "groq", "unit": "requests", "known": True, "low": False,
         "limit": 1000, "remaining": 980, "share": 0.98})})
    head, rows = dashboard.writing()
    assert rows == []
    assert "room" in head


def test_rows_appear_when_a_vendor_is_low(monkeypatch):
    import capacity
    import dashboard
    monkeypatch.setattr(capacity, "snapshot", lambda: {"vendors": _vendors(
        {"name": "gemini", "unit": "requests", "known": False, "low": False,
         "note": "no quota reported by the vendor"},
        {"name": "groq", "unit": "requests", "known": True, "low": True,
         "limit": 1000, "remaining": 61, "share": 0.061,
         "refills_in_seconds": 48000, "age_seconds": 300})})
    head, rows = dashboard.writing()
    assert "groq" in head and len(rows) == 2
    assert "61/1000 requests" in rows[1]
    # Gemini gets words, not a bar. A bar would be a guess drawn as a reading.
    assert "▓" not in rows[0] and "not counted" in rows[0]


def test_a_stale_reading_says_so(monkeypatch):
    """Groq's allowance drips back all day, so last night's figure is not a
    figure about this morning."""
    import dashboard
    fresh = dashboard._vendor_row({"name": "groq", "unit": "requests", "known": True,
                                   "limit": 1000, "remaining": 61, "share": 0.061,
                                   "refills_in_seconds": 60, "age_seconds": 120})
    stale = dashboard._vendor_row({"name": "groq", "unit": "requests", "known": True,
                                   "limit": 1000, "remaining": 61, "share": 0.061,
                                   "refills_in_seconds": 60, "age_seconds": 7 * 3600})
    assert "ago" not in fresh
    assert "seen 7h ago" in stale


def test_the_caption_is_split_at_a_line_boundary():
    """A blind cut at the caption limit can end a caption at "61/10", which is
    not a truncated number but a different and entirely believable one."""
    import notify
    body = "\n".join(f"  vendor{i}   {i}00/1000 requests" for i in range(60))
    head, rest = notify.split_for_caption(body, limit=200)
    assert not head.endswith(" ") and "\n" not in rest[:1]
    # Every line is wholly in one part or wholly in the other.
    lines = body.split("\n")
    for line in lines:
        assert (line in head) or (line in rest), line
    assert len(head) <= 200


def test_a_single_overlong_line_is_still_cut():
    """The one case with no better answer, pinned so nobody thinks it hangs."""
    import notify
    head, rest = notify.split_for_caption("x" * 50, limit=30)
    assert len(head) == 30 and len(rest) == 20


# ── counted vendors: Gemini, which reports nothing ───────────────────────────

def test_count_increments_per_model(tmp_path):
    path = tmp_path / "q.json"
    for _ in range(3):
        quotas.count("gemini", "gemini-2.5-flash", path=path)
    quotas.count("gemini", "gemini-2.5-flash-lite", path=path)
    models = json.loads(path.read_text())["gemini"]["models"]
    assert models["gemini-2.5-flash"]["made"] == 3
    assert models["gemini-2.5-flash-lite"]["made"] == 1


def test_gemini_is_keyed_on_the_pacific_day_not_ours():
    """The bug this prevents: neurons.py keys on the UTC date because that is
    when Cloudflare's pot returns. Gemini's returns at midnight Pacific, so the
    same key would zero the tally at 17:00 Pacific — seven hours early, every
    day, in the middle of an allowance."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert quotas.VENDOR_ZONE["gemini"] == "America/Los_Angeles"
    expected = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    assert quotas.vendor_day("gemini") == expected


def test_a_vendor_with_no_zone_falls_back_to_utc():
    from datetime import datetime, timezone
    assert quotas.vendor_day("nobody") == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_yesterdays_tally_is_dropped_not_shown(tmp_path):
    """Last night's count is not a smaller count. Showing it would report an
    allowance as part-spent on a morning when it is whole."""
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"gemini": {
        "source": "counted", "day": "1999-01-01",
        "models": {"gemini-2.5-flash": {"made": 240}}}}))
    assert quotas.counted("gemini", path)["models"] == {}


def test_exhaustion_is_recorded_without_inventing_a_ceiling(tmp_path):
    """"We made 14 and the fifteenth was refused" does not establish that the
    limit is 14 — anything else on the same project spends the same quota."""
    path = tmp_path / "q.json"
    quotas.count("gemini", "m", path=path)
    quotas.mark_exhausted("gemini", "m", path=path)
    entry = json.loads(path.read_text())["gemini"]["models"]["m"]
    assert entry["out_of_quota_at"].endswith("Z")
    assert "ceiling" not in entry and "limit" not in entry


def test_counted_never_raises(tmp_path):
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory")
    quotas.count("gemini", "m", path=blocked / "q.json")       # must not raise
    quotas.mark_exhausted("gemini", "m", path=blocked / "q.json")


def test_the_two_kinds_of_record_share_a_file_but_not_a_rule(tmp_path):
    """A tally is not a remaining. Reading one as the other is how a vendor
    with nothing left comes to look full, so every record says which it is."""
    path = tmp_path / "q.json"
    quotas.record("groq", "openai/gpt-oss-120b", LIVE, path=path)
    quotas.count("gemini", "gemini-2.5-flash", path=path)
    data = json.loads(path.read_text())
    assert data["groq"]["source"] == "reported"
    assert data["gemini"]["source"] == "counted"
    # A reported record must never be mistaken for a tally to add to.
    assert quotas.counted("groq", path)["models"] == {}


def test_call_gemini_counts_the_attempt(monkeypatch, tmp_path):
    path = tmp_path / "q.json"
    monkeypatch.setattr(quotas, "QUOTAS_PATH", path)
    monkeypatch.setattr(llm, "resolve_keys", lambda name: ["key"] if "GEMINI" in name else [])
    monkeypatch.setattr(llm, "_pace", lambda provider: None)
    monkeypatch.setattr(llm, "_SPENT", set())
    monkeypatch.setattr(llm, "_post", lambda *a, **k: {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    assert llm.call_gemini("s", "u", 0.0) == "ok"
    models = json.loads(path.read_text())["gemini"]["models"]
    assert models[llm.GEMINI_MODELS[0]]["made"] == 1


def test_call_gemini_counts_a_refused_attempt_too(monkeypatch, tmp_path):
    """A refusal still spent the attempt. A tally of only the answers we liked
    walks into a daily cap believing it has room."""
    path = tmp_path / "q.json"
    monkeypatch.setattr(quotas, "QUOTAS_PATH", path)
    monkeypatch.setattr(llm, "resolve_keys", lambda name: ["key"] if "GEMINI" in name else [])
    monkeypatch.setattr(llm, "_pace", lambda provider: None)
    monkeypatch.setattr(llm, "_SPENT", set())

    def out_of_quota(*a, **k):
        raise llm.RateLimited("HTTP 429", 30,
                              "GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    monkeypatch.setattr(llm, "_post", out_of_quota)
    with pytest.raises(llm.RateLimited):
        llm.call_gemini("s", "u", 0.0)

    models = json.loads(path.read_text())["gemini"]["models"]
    assert len(models) == len(llm.GEMINI_MODELS)
    for model in llm.GEMINI_MODELS:
        assert models[model]["made"] == 1
        assert models[model]["out_of_quota_at"].endswith("Z")


def test_a_gemini_row_shows_what_we_made_not_what_is_left(monkeypatch):
    import dashboard
    row = dashboard._vendor_row({"name": "gemini", "unit": "requests", "known": False,
                                 "made": 14, "models_out": 2, "models_total": 5,
                                 "note": "no ceiling reported by the vendor"})
    assert "14 made today" in row and "2 of 5 models out of quota" in row
    assert "▓" not in row and "left" not in row


def test_the_headline_gives_each_vendor_its_own_reason(monkeypatch):
    """One shared phrase has to be vague enough to fit all three, and "near the
    end of its share" is not what happened when Gemini's models went out."""
    import capacity
    import dashboard
    monkeypatch.setattr(capacity, "snapshot", lambda: {"vendors": [
        {"name": "gemini", "unit": "requests", "known": False, "low": True,
         "made": 14, "models_out": 2, "models_total": 5,
         "low_because": "2 of 5 models out of quota"},
        {"name": "groq", "unit": "requests", "known": True, "low": True,
         "limit": 1000, "remaining": 61, "share": 0.061,
         "low_because": "61 of 1000 requests left"},
    ]})
    head, _ = dashboard.writing()
    assert "gemini: 2 of 5 models out of quota" in head
    assert "groq: 61 of 1000 requests left" in head
