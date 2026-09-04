"""Unknown, stale and wrong-model quota must not trigger optional generation."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_budget
import fresh_poses

NOW = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)


@pytest.fixture
def record(monkeypatch):
    row = {"source": "reported", "model": "tested-model", "observed_at": NOW.isoformat(),
           "requests": {"remaining": 3, "limit": 1000}}
    monkeypatch.setattr(review_budget.quotas, "read", lambda: {"groq": row})
    return row


def check():
    return review_budget.fault("groq", "tested-model", 3, now=NOW)


def test_exact_remaining_boundary(record):
    assert check() is None
    record["requests"]["remaining"] = 2
    assert "only 2" in check()


@pytest.mark.parametrize("age,accepted", [(0, True), (60, True), (61, False), (-1, False)])
def test_snapshot_age(record, age, accepted):
    record["observed_at"] = (NOW - timedelta(seconds=age)).isoformat()
    assert (check() is None) == accepted


@pytest.mark.parametrize("value", [None, "3", True, -1, 1001, float("nan"), float("inf")])
def test_invalid_remaining(record, value):
    record["requests"]["remaining"] = value
    assert check() is not None


def test_model_must_match(record):
    record["model"] = "another-model"
    assert "different" in check()


def test_counted_usage_is_not_remaining_allowance(record):
    record["source"] = "counted"
    assert "unknown" in check()


def test_missing_reading_does_not_mean_full_allowance(monkeypatch):
    monkeypatch.setattr(review_budget.quotas, "read", lambda: {})
    assert "unknown" in review_budget.fault("gemini", "model", 3)


def test_unknown_budget_stops_before_generator_import(tmp_path, monkeypatch):
    monkeypatch.setattr(review_budget.quotas, "read", lambda: {})
    monkeypatch.setattr(fresh_poses.image_review, "ready", lambda: True)
    monkeypatch.setattr(fresh_poses.image_review, "model_for_review", lambda: ("gemini", "model"))
    monkeypatch.setitem(sys.modules, "poses_flux", None)
    fallback = {1: tmp_path / "checked-library.png"}
    result, stats = fresh_poses.generate_for_deck([{"mascot": "an adequate test brief"}],
                                                 fallback, tmp_path / "out")
    assert result == fallback and stats["generated"] == 0
    assert "allowance is unknown" in stats["reasons"][0]
    assert not (tmp_path / "out").exists()
