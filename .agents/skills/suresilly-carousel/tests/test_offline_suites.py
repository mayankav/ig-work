"""Routine bibliography tests make no network calls; explicit live failure is red."""
import pytest

import test_bibliography as suite


def test_default_catalogue_suite_is_offline(monkeypatch, capsys):
    def unexpected(*args, **kwargs):
        pytest.fail("routine bibliography tests tried a live request")
    monkeypatch.setattr(suite.bib, "_get", unexpected)
    assert suite.run() == 0
    assert "offline only" in capsys.readouterr().out


def test_explicit_live_check_cannot_pass_by_skipping_outage(monkeypatch, capsys):
    def unavailable(*args, **kwargs):
        raise suite.bib.Unverified("catalogue outage")
    monkeypatch.setattr(suite.bib, "_get", unavailable)
    assert suite.run(live_catalogue=True) == 1
    assert "LIVE catalogue check could not finish" in capsys.readouterr().out
