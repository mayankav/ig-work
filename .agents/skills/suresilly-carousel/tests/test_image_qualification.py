"""Production needs test evidence, not a flag or a working credential."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import image_qualification as qualify
import image_review as review
import llm


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(qualify, "RECORDS", tmp_path / "proof")
    monkeypatch.setattr(qualify, "_CACHE", {})
    monkeypatch.setattr(llm, "configured", lambda _: True)
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: pytest.fail("test reached the network"))


@pytest.fixture(scope="module")
def evidence():
    """Perfect simulated observations, used only in temporary test records.

    Uses the actual inspection images and production panel mapping. No record
    produced here is installed as production qualification.
    """
    provider, model = "gemini", llm.GEMINI_MODELS[0]
    record = {"provider": provider, "model": model, "contract": qualify.contract(),
              "started_at": datetime.now(timezone.utc).isoformat(), "observations": [], "errors": []}
    for repeat, group in qualify.batches():
        sheet, mapping, control = qualify.prepare(group)
        found = [{"panel": control, "code": "extra_limb", "fault": "one body has three legs"}]
        for panel, number in mapping.items():
            case = group[number-1]
            if case["codes"]:
                found.append({"panel": panel, "code": case["codes"][0], "fault": "visible known defect"})
        record["observations"].append({"repeat": repeat, "cases": [c["id"] for c in group],
            "sheet_sha256": hashlib.sha256(sheet).hexdigest(), "actual_model": provider+"/"+model,
            "answer": {"inspected": sorted(set(mapping) | {control}), "uncertain": [],
                       "figures": [{"panel": n, "arms": 2, "legs": 2} for n in set(mapping) | {control}],
                       "faults": found}})
    return record


def test_perfect_observations_are_recomputed_not_trusted(evidence):
    record = copy.deepcopy(evidence)
    record["result"] = {"qualified": False}
    assert qualify.evaluate(record)["qualified"]


@pytest.mark.parametrize("change", [
    lambda r: r.update(contract="old rules"),
    lambda r: r.update(model="a different model"),
    lambda r: r.update(observations=r["observations"][:-1]),
    lambda r: r["observations"][0].update(sheet_sha256="different pixels"),
    lambda r: r["observations"][0].update(actual_model="different/model"),
    lambda r: r["observations"][0]["answer"].update(uncertain=[1]),
    lambda r: r.update(started_at="2000-01-01T00:00:00+00:00"),
    lambda r: r.update(errors=[{"type": "TimeoutError"}]),
])
def test_bad_evidence_cannot_be_approved_by_saved_flag(evidence, change):
    record = copy.deepcopy(evidence)
    change(record)
    record["result"] = {"qualified": True}
    assert not qualify.evaluate(record)["qualified"]


def test_missed_known_bad_candidate_fails_even_when_control_is_caught(evidence):
    record = copy.deepcopy(evidence)
    for observation, (_, group) in zip(record["observations"], qualify.batches()):
        if any(c["codes"] for c in group):
            _, _, control = qualify.prepare(group)
            observation["answer"]["faults"] = [f for f in observation["answer"]["faults"] if f["panel"] == control]
            break
    result = qualify.evaluate(record)
    assert not result["qualified"]
    assert any("missed" in fault for fault in result["faults"])


@pytest.mark.parametrize("number, expected", [(1, True), (2, False)])
def test_clean_rejection_limit_is_five_percent_per_trial(evidence, number, expected):
    record = copy.deepcopy(evidence)
    added = 0
    for observation, (repeat, group) in zip(record["observations"], qualify.batches()):
        if repeat != 0:
            break
        _, mapping, _ = qualify.prepare(group)
        for panel, index in mapping.items():
            if not group[index-1]["codes"] and added < number:
                observation["answer"]["faults"].append({"panel": panel, "code": "extra_limb", "fault": "false defect"})
                added += 1
    assert added == number
    assert qualify.evaluate(record)["qualified"] is expected


def test_keys_alone_do_not_enable_image_generation():
    assert not review.ready()
    with pytest.raises(llm.ModelRefused, match="qualification"):
        review.model_for_review()


def test_current_record_selects_exact_model_then_image_change_disables_it(evidence, monkeypatch):
    qualify.RECORDS.mkdir()
    (qualify.RECORDS / "test-only.json").write_text(json.dumps(evidence))
    assert review.model_for_review() == (evidence["provider"], evidence["model"])
    monkeypatch.setattr(qualify, "contract", lambda: "changed image bytes")
    assert not review.ready()


def test_always_clear_evidence_is_not_qualified(evidence):
    record = copy.deepcopy(evidence)
    for observation in record["observations"]:
        observation["answer"]["faults"] = []
    assert not qualify.evaluate(record)["qualified"]
