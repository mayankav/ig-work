"""Single-image experiments cannot grant production approval."""
import copy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import image_single_review as review
import image_single_qualification as qualify
import image_qualification as grouped
import llm


def fault(code="extra_limb"):
    return {"code": code, "fault": "visible drawing defect", "location": "lower body",
            "visible_evidence": "Three separate legs visibly connect to the same pelvis"}


def answer(legs=2):
    return {"figures": [{"location": "center", "arms": 2, "legs": legs,
                         "arm_descriptions": ["left arm", "right arm"],
                         "leg_descriptions": [f"visible leg {n}" for n in range(legs)]}],
            "other_shapes": [], "uncertainty": [], "faults": [fault()] if legs == 3 else []}


@pytest.fixture(autouse=True)
def no_live_requests(monkeypatch):
    monkeypatch.setattr(llm, "_post", lambda *a, **k: pytest.fail("test reached network"))
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: pytest.fail("test reached model"))
    monkeypatch.setattr(qualify.time, "sleep", lambda _: None)
    monkeypatch.setattr(qualify, "contract", lambda: "test-contract")
    monkeypatch.setattr(review, "prepare", lru_cache(maxsize=30)(review.prepare))


def test_counts_are_per_character_and_hidden_limbs_are_not_faults():
    two = answer(1)
    two["figures"].append(answer()["figures"][0])
    assert review.observed_codes(two) == set()
    assert review.observed_codes(answer(3)) == {"extra_limb"}


@pytest.mark.parametrize("change", [
    lambda a: a.update(uncertainty=["cannot trace the rear shape"]),
    lambda a: a.update(figures=[]),
    lambda a: a["figures"][0].update(legs=2.0),
    lambda a: a["figures"][0].update(legs=3),
    lambda a: a.update(unexpected=True),
])
def test_unusable_answers_stop(change):
    value = answer()
    change(value)
    with pytest.raises(ValueError):
        review.observed_codes(value)


def test_control_must_show_the_defect():
    with pytest.raises(ValueError, match="missed"):
        review.check_control(answer())
    review.check_control(answer(3))


def evidence():
    record = {"contract": qualify.contract(), "provider": review.PROVIDER, "model": review.MODEL,
              "started_at": datetime.now(timezone.utc).isoformat(), "http_requests": 138,
              "observations": [], "errors": []}
    for repeat, case in qualify.plan():
        observation = {"repeat": repeat, "case": case["id"]}
        for role, path in (("candidate", case["path"]), ("control", grouped.review.CONTROL_PATH)):
            value = answer(3 if role == "control" or case["id"] == "extra_leg" else 2)
            if role == "candidate" and case["codes"]:
                value["faults"] = [fault(case["codes"][0])]
            raw = path.read_bytes()
            observation[role] = {"source_sha256": review.digest(raw),
                                  "image_sha256": review.digest(review.prepare(raw)),
                                  "actual_model": review.PROVIDER + "/" + review.MODEL,
                                  "answer": value}
        record["observations"].append(observation)
    return record


def test_complete_evidence_replays():
    value = evidence()
    assert qualify.evaluate(value)["qualified"]
    assert not grouped.evaluate(value)["qualified"]


@pytest.mark.parametrize("change", [
    lambda r: r.update(contract="old"),
    lambda r: r.update(started_at="2000-01-01T00:00:00+00:00"),
    lambda r: r.update(http_requests=137),
    lambda r: r.update(errors=[{"reason": "HTTP 503"}]),
    lambda r: r["observations"][0]["candidate"].update(image_sha256="changed"),
    lambda r: r["observations"][0]["control"].update(source_sha256="changed"),
    lambda r: r["observations"][0]["control"].update(answer=answer()),
    lambda r: r["observations"][0]["candidate"].update(actual_model="other"),
    lambda r: r["observations"].pop(),
])
def test_saved_pass_cannot_override_bad_evidence(change):
    value = evidence()
    change(value)
    value["result"] = {"qualified": True}
    assert not qualify.evaluate(value)["qualified"]


@pytest.mark.parametrize("rejects,passes", [(1, True), (2, False)])
def test_correct_image_rejection_limit(rejects, passes):
    value = evidence()
    clean = [o for o in value["observations"] if o["repeat"] == 0 and o["case"] in grouped.CLEAN]
    for row in clean[:rejects]:
        row["candidate"]["answer"] = answer(3)
    assert qualify.evaluate(value)["qualified"] is passes


def test_missed_known_fault_cannot_pass():
    value = evidence()
    row = next(o for o in value["observations"] if o["case"] == "blank_profile_eye")
    row["candidate"]["answer"] = answer()
    assert not qualify.evaluate(value)["qualified"]


def test_service_error_stops_without_retry(monkeypatch, tmp_path):
    calls = []
    def post(*a, **k):
        calls.append(1)
        raise llm.ModelRefused("HTTP 503")
    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: llm._post())
    result = qualify.run(tmp_path / "evidence")
    assert result["status"] == "incomplete"
    assert result["http_requests"] == len(calls) == 1
    assert llm._post is post


def test_http_budget_is_enforced_and_output_is_not_overwritten(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(llm, "_post", lambda: calls.append(1))
    def call(*a, **k):
        llm._post()
        return answer(), review.PROVIDER + "/" + review.MODEL
    monkeypatch.setattr(llm, "look_once", call)
    result = qualify.run(tmp_path / "evidence", max_requests=1)
    assert result["status"] == "incomplete"
    assert len(calls) == result["http_requests"] == 1
    with pytest.raises(FileExistsError):
        qualify.run(tmp_path / "evidence")


def test_uncertainty_stops_before_control_and_saves_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_post", lambda: None)
    value = answer()
    value["uncertainty"] = ["cannot distinguish arm from leg"]
    def call(*a, **k):
        llm._post()
        return value, review.PROVIDER + "/" + review.MODEL
    monkeypatch.setattr(llm, "look_once", call)
    result = qualify.run(tmp_path / "evidence")
    assert result["status"] == "incomplete"
    assert result["http_requests"] == 1
    assert result["observations"][0]["candidate"]["answer"] == value
    assert "control" not in result["observations"][0]


def test_missed_control_stops_trial(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "_post", lambda: None)
    def call(*a, **k):
        llm._post()
        return answer(), review.PROVIDER + "/" + review.MODEL
    monkeypatch.setattr(llm, "look_once", call)
    result = qualify.run(tmp_path / "evidence")
    assert result["status"] == "failed"
    assert result["http_requests"] == 2
    assert "missed the known extra leg" in result["errors"][0]["reason"]


def test_count_alone_cannot_invent_a_fault_or_satisfy_control():
    value = answer(3)
    value["faults"] = []
    assert review.observed_codes(value) == set()
    with pytest.raises(ValueError, match="missed"):
        review.check_control(value)


def test_visible_and_partial_parts_without_guessing_hidden_connections():
    value = answer(1)
    value["figures"][0]["leg_descriptions"] = [
        "A hoof and short leg segment below the chair; visible segment ends at the chair edge"]
    assert review.assessment(value)["disposition"] == "no_fault_reported"
    value["figures"][0].update(legs=0, leg_descriptions=[])
    assert review.observed_codes(value) == set()


def test_visible_partial_defect_can_reject():
    value = answer(1)
    value["faults"] = [{"code": "disconnected", "fault": "detached hoof",
                         "location": "below the chair",
                         "visible_evidence": "Background separates the hoof from the exposed leg end"}]
    assert review.observed_codes(value) == {"disconnected"}


def test_detected_missing_pupil_survives_unrelated_visible_uncertainty():
    value = answer()
    value["faults"] = [{"code": "blank_eye", "fault": "missing pupil",
                         "location": "open eye on the face",
                         "visible_evidence": "The outlined open eye is empty inside"}]
    value["uncertainty"] = ["The yellow mark beside the visible hoof is ambiguous"]
    result = review.assessment(value)
    assert result["disposition"] == "reject"
    assert result["uncertainty"] == value["uncertainty"]
    assert review.observed_codes(value) == {"blank_eye"}


def test_control_with_visible_defect_and_unrelated_uncertainty_is_detected():
    value = answer(3)
    value["uncertainty"] = ["The mark beside the visible ear is ambiguous"]
    review.check_control(value)
    value["faults"] = []
    with pytest.raises(ValueError):
        review.check_control(value)


@pytest.mark.parametrize("field", ["location", "visible_evidence"])
def test_fault_requires_visible_evidence(field):
    value = answer(3)
    del value["faults"][0][field]
    with pytest.raises(ValueError):
        review.observed_codes(value)


def test_fault_and_uncertainty_replay_without_becoming_approval():
    value = evidence()
    for row in value["observations"]:
        if row["case"] == "blank_profile_eye":
            row["candidate"]["answer"]["uncertainty"] = ["Ambiguous visible mark beside hoof"]
    assert qualify.evaluate(value)["qualified"]
    assert not grouped.evaluate(value)["qualified"]


def test_prompt_limits_inspection_to_visible_evidence():
    assert "partially visible" in review.SYSTEM
    assert "Do not infer, count or analyse any part that is not visible" in review.SYSTEM
    assert "Occlusion alone is not a fault or" in review.SYSTEM
    assert "A count alone is not evidence of a defect" in review.SYSTEM
    assert review.VERSION == "single-visible-parts-2"
