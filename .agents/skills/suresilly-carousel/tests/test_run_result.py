"""A successful build must never conceal a later failure."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from run_result import result


def resolve(steps, **kwargs):
    args = dict(mode="publish", slug="deck", verdict="", reason="", retry=False, published=None)
    args.update(kwargs)
    return result(steps, **args)


@pytest.mark.parametrize("key,stage", [("gates", "tests"), ("verbs", "tests"),
    ("test_state", "tests"), ("host", "hosting"), ("reachable", "hosting"),
    ("post", "posting"), ("record", "state saving")])
def test_failed_stage_is_not_posted(key, stage):
    r = resolve({"build": {"outcome": "success"}, key: {"outcome": "failure"}})
    assert r["outcome"] == "error"
    assert r["stage"] == stage
    assert not r["retryable"]


def test_built_is_not_posted():
    assert resolve({"build": {"outcome": "success"}}, mode="build")["outcome"] == "built"
    assert resolve({"build": {"outcome": "success"}})["fault_code"] == "publication_unconfirmed"


def test_skipped_is_not_quality_refusal():
    assert resolve({"build": {"outcome": "skipped"}}, slug="")["outcome"] == "error"


def test_confirmed_and_state_failure():
    steps = {"build": {"outcome": "success"}, "post": {"outcome": "success"}}
    assert resolve(steps, published={"media_id": "123", "deck_slug": "deck"})["outcome"] == "ok"
    steps["record"] = {"outcome": "failure"}
    r = resolve(steps, published={"media_id": "123", "deck_slug": "deck"})
    assert r["published"] and r["outcome"] == "error" and not r["retryable"]


def test_exact_test_reason():
    r = resolve({"gates": {"outcome": "failure", "outputs": {"reason": "test_writer.py failed"}}})
    assert r["reason"] == "test_writer.py failed"


def test_force_is_held():
    assert resolve({"build": {"outcome": "success"}}, mode="force", verdict="held")["outcome"] == "held"


@pytest.mark.parametrize("receipt", [[], "bad", True, {}, {"media_id": "123"},
    {"media_id": "123", "deck_slug": "other"}, {"media_id": True, "deck_slug": "deck"},
    {"media_id": "   ", "deck_slug": "deck"}])
def test_unrelated_or_corrupt_receipt_never_reports_posted(receipt):
    value = resolve({"build": {"outcome": "success"}, "post": {"outcome": "success"}}, published=receipt)
    assert value["fault_code"] == "publication_record_invalid"
    assert not value["published"] and not value["retryable"]


def test_api_confirmation_survives_failed_receipt_save():
    value = resolve({"post": {"outcome": "failure", "outputs": {
        "stage": "state saving", "reason": "Disk full. Do not post again.",
        "confirmed_media_id": "123", "confirmed_deck_slug": "deck"}}})
    assert value["published"] and value["stage"] == "state saving"
    assert value["outcome"] == "error" and not value["retryable"]
