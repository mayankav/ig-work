import pytest

from suresilly import llm


@pytest.fixture(autouse=True)
def usage_in_tmp(tmp_path, monkeypatch):
    """Tests count writer calls in a scratch file, never in the repo's state/usage.json."""
    monkeypatch.setattr(llm, "USAGE", tmp_path / "usage.json")
