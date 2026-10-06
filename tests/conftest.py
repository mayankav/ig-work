import pytest

from suresilly import llm, sfx


@pytest.fixture(autouse=True)
def usage_in_tmp(tmp_path, monkeypatch):
    """Tests count writer calls in a scratch file, never in the repo's state/usage.json."""
    monkeypatch.setattr(llm, "USAGE", tmp_path / "usage.json")


@pytest.fixture(autouse=True)
def no_freesound_key(monkeypatch):
    """Tests never use a real Freesound key or reach the network; the sound tests set their own fake."""
    monkeypatch.setattr(sfx, "key", lambda name: "")
