"""A reviewer must see the defect and cover every panel, within real call limits."""
from pathlib import Path
import json
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fresh_poses
import image_review as review
import llm

REAL_LOOK_ONCE = llm.look_once


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(review, "model_for_review", lambda: ("gemini", llm.GEMINI_MODELS[0]))
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("unexpected image request")))


def art():
    return cv2.imread(str(review.CONTROL_PATH), cv2.IMREAD_UNCHANGED)


@pytest.mark.parametrize("reply", [
    {"faults": []},
    {"inspected": [1, 2], "uncertain": [], "faults": [],
     "figures": [{"panel": n, "arms": 2, "legs": 2} for n in (1, 2)]},
])
def test_always_clear_reviewer_cannot_pass_real_extra_leg(monkeypatch, reply):
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: (
        reply, "gemini/" + llm.GEMINI_MODELS[0]))
    faults = fresh_poses.anatomy_faults({1: art()}, log=lambda _: None)
    assert 1 in faults
    assert "unchecked" in faults[1]


def valid():
    return {"inspected": [1, 2, 3, 4], "uncertain": [],
            "figures": [{"panel": n, "arms": 2, "legs": 2} for n in range(1, 5)], "faults": [
        {"panel": 2, "code": "extra_limb", "fault": "three legs on one body"}]}


@pytest.mark.parametrize("change", [
    lambda a: a.update(inspected=[1, 2, 3]),
    lambda a: a.update(inspected=[1, 2, 3, 4, 4]),
    lambda a: a.update(inspected=[True, 2, 3, 4]),
    lambda a: a.update(uncertain=[3]),
    lambda a: a.update(faults=[]),
    lambda a: a["faults"][0].update(code="blank_eye"),
    lambda a: a["faults"][0].update(panel=8),
    lambda a: a.update(approved=True),
    lambda a: a.update(figures=[]),
    lambda a: a["figures"][0].update(legs=True),
])
def test_incomplete_or_unreliable_reply_rejects_group(change):
    answer = valid()
    change(answer)
    with pytest.raises(ValueError):
        review.parse_vetoes(answer, {1, 2, 3, 4}, 2)


def test_visible_fault_is_retained_with_control():
    answer = valid()
    answer["faults"].append({"panel": 3, "code": "blank_eye", "fault": "open eye has no pupil"})
    assert review.parse_vetoes(answer, {1, 2, 3, 4}, 2)[3] == "open eye has no pupil"


def test_counts_add_a_veto_and_count_characters_separately():
    answer = valid()
    answer["figures"][2]["legs"] = 3
    answer["figures"].append({"panel": 1, "arms": 2, "legs": 2})
    found = review.parse_vetoes(answer, {1, 2, 3, 4}, 2)
    assert 3 in found and 1 not in found
    assert "extra_limb" in review.observed_codes(answer, 3)


def test_observed_extra_leg_catches_control_even_if_fault_list_is_empty():
    answer = valid()
    answer["faults"] = []
    answer["figures"][1]["legs"] = 3
    assert 2 in review.parse_vetoes(answer, {1, 2, 3, 4}, 2)


def test_nine_candidates_use_exactly_three_requests_even_on_outage(monkeypatch):
    calls, sheets = [], []
    original = review.inspection_sheet
    def sheet(panels):
        sheets.append(len(panels))
        return original(panels)
    def down(*args, **kwargs):
        calls.append(kwargs)
        raise TimeoutError("service did not answer")
    monkeypatch.setattr(review, "inspection_sheet", sheet)
    monkeypatch.setattr(llm, "look_once", down)
    images = {n: art() for n in range(1, 10)}
    assert set(review.review(images, log=lambda _: None)) == set(images)
    assert len(calls) == 3
    assert sheets == [4, 4, 4]  # three candidates plus the control
    assert len({(c["provider"], c["model"]) for c in calls}) == 1


def test_budget_exceeded_makes_no_call():
    images = {n: art() for n in range(1, 11)}
    assert set(review.review(images)) == set(images)


def test_control_missing_makes_no_call(monkeypatch, tmp_path):
    candidate = art()
    monkeypatch.setattr(review, "CONTROL_PATH", tmp_path / "missing.png")
    assert set(review.review({1: candidate})) == {1}


def test_sheet_has_body_and_upper_view_for_every_panel():
    encoded = review.inspection_sheet({1: art(), 2: art()})
    pixels = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
    assert pixels.shape[:2] == (review.TILE * 2, review.TILE * 3)
    for row in range(2):
        for col in range(3):
            patch = pixels[row*review.TILE+70:(row+1)*review.TILE,
                           col*review.TILE:(col+1)*review.TILE]
            assert np.count_nonzero(patch.std(axis=2) > 10) > 1000


@pytest.mark.parametrize("failure", [llm.ModelRefused("400 refused"), TimeoutError("timeout"),
                                    llm.RateLimited("daily limit", 1, "RequestsPerDay")])
def test_exact_gemini_never_retries_or_changes_model(monkeypatch, failure):
    calls = []
    monkeypatch.setattr(llm, "resolve_keys", lambda _: ["test-key-1", "test-key-2"])
    monkeypatch.setattr(llm, "_pace", lambda _: None)
    monkeypatch.setattr(llm, "_tally", lambda *a: None)
    monkeypatch.setattr(llm, "_SPENT", set())
    def post(url, *args, **kwargs):
        calls.append(url)
        raise failure
    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "look_once", REAL_LOOK_ONCE)
    with pytest.raises(type(failure)):
        llm.look_once(review.SYSTEM, "inspect", review.SCHEMA, b"jpeg",
                      provider="gemini", model=llm.GEMINI_MODELS[0])
    assert len(calls) == 1
    assert llm.GEMINI_MODELS[0] in calls[0]


@pytest.mark.parametrize("model, ultra", [("gemini-2.5-flash", False), ("gemini-3.5-flash", True)])
def test_qualified_transport_keeps_its_resolution_setting(monkeypatch, model, ultra):
    captured = []
    monkeypatch.setattr(llm, "resolve_keys", lambda _: ["test-key"])
    monkeypatch.setattr(llm, "_pace", lambda _: None)
    monkeypatch.setattr(llm, "_tally", lambda *a: None)
    monkeypatch.setattr(llm, "_SPENT", set())
    def post(url, payload, headers):
        captured.append(payload)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(valid())}]}}]}
    monkeypatch.setattr(llm, "_post", post)
    answer, actual = REAL_LOOK_ONCE(review.SYSTEM, "inspect", review.SCHEMA, b"jpeg",
                                    provider="gemini", model=model)
    assert answer == valid() and actual == "gemini/" + model
    part = captured[0]["contents"][0]["parts"][1]
    assert (part.get("media_resolution") == {"level": "MEDIA_RESOLUTION_ULTRA_HIGH"}) is ultra


@pytest.mark.parametrize("model,effort,budget", [("qwen/qwen3.6-27b", "none", 2048),
    ("qwen/qwen3.8-27b", "medium", 4096)])
def test_exact_groq_keeps_the_qualified_model_and_settings(monkeypatch, model, effort, budget):
    import quotas
    captured = []
    monkeypatch.setattr(llm, "resolve_key", lambda _: "test-key")
    monkeypatch.setattr(llm, "_pace", lambda _: None)
    monkeypatch.setattr(quotas, "record", lambda *a: None)
    def post(url, payload, headers, **kwargs):
        captured.append(payload)
        return {"choices": [{"message": {"content": json.dumps(valid())}}]}
    monkeypatch.setattr(llm, "_post", post)
    answer, actual = REAL_LOOK_ONCE(review.SYSTEM, "inspect", review.SCHEMA, b"jpeg",
                                    provider="groq", model=model)
    assert answer == valid() and actual == "groq/" + model
    assert len(captured) == 1
    assert captured[0]["model"] == model
    assert captured[0]["reasoning_effort"] == effort
    assert captured[0]["max_completion_tokens"] == budget


def test_unknown_groq_image_model_cannot_send_a_request(monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a, **k: pytest.fail("unknown model sent a request"))
    with pytest.raises(llm.ModelRefused, match="unknown exact"):
        REAL_LOOK_ONCE(review.SYSTEM, "inspect", review.SCHEMA, b"jpeg", provider="groq", model="unknown")
