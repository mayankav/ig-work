"""Text and artwork spend one allowance; unreadable usage is not zero usage."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import neurons


def test_text_spending_limits_images(tmp_path):
    ledger = neurons.Ledger(tmp_path / "usage.json")
    ledger.spend_text(9500)
    ledger.spend(100)
    assert ledger.remaining() == 400
    ledger.check(400)
    with pytest.raises(neurons.BudgetExceeded):
        ledger.check(401)
    # The same shared state is honoured by a new process/ledger instance.
    assert neurons.Ledger(ledger.path).remaining() == 400


def test_picture_cap_still_applies_when_account_has_room(tmp_path):
    ledger = neurons.Ledger(tmp_path / "usage.json", budget=100)
    ledger.spend(90)
    assert ledger.account_left() == 9910
    assert ledger.remaining() == 10


@pytest.mark.parametrize("budget", [-1, float("nan"), float("inf")])
def test_invalid_budget_is_refused(tmp_path, budget):
    with pytest.raises(neurons.BudgetExceeded):
        neurons.Ledger(tmp_path / "usage.json", budget=budget)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "5"])
def test_invalid_saved_usage_cannot_be_reset(tmp_path, value):
    path = tmp_path / "usage.json"
    raw = json.dumps({neurons._today(): {"neurons": value}})
    path.write_text(raw)
    ledger = neurons.Ledger(path)
    with pytest.raises(neurons.BudgetExceeded):
        ledger.check(1)
    assert path.read_text() == raw


@pytest.mark.parametrize("raw", ["[]", "null", '{"2026-09-04": null}', "not JSON"])
def test_bad_ledger_shape_cannot_be_spent(tmp_path, raw):
    path = tmp_path / "usage.json"
    path.write_text(raw)
    with pytest.raises(neurons.BudgetExceeded):
        neurons.Ledger(path).spend(1)
    assert path.read_text() == raw


def test_failed_replacement_preserves_previous_usage(tmp_path, monkeypatch):
    ledger = neurons.Ledger(tmp_path / "usage.json")
    ledger.spend(10)
    before = ledger.path.read_bytes()
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(neurons.os, "replace", fail)
    with pytest.raises(OSError):
        ledger.spend(5)
    assert ledger.path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [ledger.path]


def test_zero_budget_allows_no_paid_work(tmp_path):
    ledger = neurons.Ledger(tmp_path / "usage.json", budget=0)
    assert ledger.remaining() == 0
    with pytest.raises(neurons.BudgetExceeded):
        ledger.check(0.01)


def test_broken_ledger_link_is_not_a_new_account(tmp_path):
    path = tmp_path / "usage.json"
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(neurons.BudgetExceeded, match="link is broken"):
        neurons.Ledger(path).spend(1)
    assert path.is_symlink()
