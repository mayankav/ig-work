"""Real outline checks around bounded field edits; no model or source calls."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import plan_repair
import writer
import llm
from test_writer import good_plan, MOMENT


def valid():
    plan = good_plan()
    plan["hooks"] *= 4
    return plan


def check(plan):
    return writer.validate_plan(plan, MOMENT, "sleep")


def edit(plan, path, value, fault="fault-1"):
    key = next(k for k, field in plan_repair.describe(plan).items() if field["path"] == path)
    return {"path":"/"+key,"value":value,"fault":fault}


def test_text_repair_keeps_clean_work_and_source():
    original = valid()
    plan = deepcopy(original)
    plan["protocol"]["script"] = "The waking is here. I am not checking the clock."
    faults = check(plan)
    assert faults == ["the script has no [bracket] to fill in"]
    answer = {"edits":[edit(plan, "/protocol/script", original["protocol"]["script"]),
                       edit(plan, "/hooks/1/h1", "Unasked rewrite.")]}
    fixed, remaining = plan_repair.apply(plan, faults, answer, writer.PLAN_SCHEMA, check)
    assert fixed == original and not remaining
    assert plan["protocol"]["script"] != original["protocol"]["script"]


def test_number_and_dependency_array_can_be_repaired():
    original = valid()
    plan = deepcopy(original)
    plan["beats"][5]["n"] = 4
    plan["beats"][5]["depends_on"] = [9]
    faults = check(plan)
    assert len(faults) == 2
    answer = {"edits":[edit(plan, "/beats/5/n", "6"),
                       edit(plan, "/beats/5/depends_on", "[]", "fault-2")]}
    assert plan_repair.apply(plan, faults, answer, writer.PLAN_SCHEMA, check) == (original, [])


@pytest.mark.parametrize("value", ["not JSON", "[true]", "[10]", '"text"', "[3,3]", "[6]"])
def test_malformed_or_invalid_dependency_edit_never_clears_fault(value):
    plan = valid()
    plan["beats"][5]["depends_on"] = [9]
    faults = check(plan)
    answer = {"edits":[edit(plan, "/beats/5/depends_on", value)]}
    assert plan_repair.apply(plan, faults, answer, writer.PLAN_SCHEMA, check) == (plan, faults)


def test_source_claim_and_whole_outline_are_not_editable():
    fields = {v["path"] for v in plan_repair.describe(valid()).values()}
    assert not fields.intersection({"/citation_id","/claim_index","/beats","/hooks","/protocol","/protocol/menu"})
    assert "/protocol/menu/0" in fields


@pytest.mark.parametrize("stubborn", [False, True])
def test_live_outline_path_repairs_fields_with_original_provider(monkeypatch, stubborn):
    plan = valid()
    source = writer.load_citations()[plan["citation_id"]]
    monkeypatch.setattr(writer.bibliography, "discover", lambda *a: (None, []))
    monkeypatch.setattr(writer.bibliography, "recent", lambda: [])
    monkeypatch.setattr(writer.bibliography, "supported_indices", lambda c: [0])
    monkeypatch.setattr(writer.bibliography, "require_claim_support", lambda *a: None)
    monkeypatch.setattr(writer, "citations_for", lambda *a: [source])
    monkeypatch.setattr(writer, "recent_formulas", lambda: [])
    plan["protocol"]["script"] = "The waking is here. I am not checking the clock."
    calls = []
    def ask(system, user, schema, **kwargs):
        calls.append(schema)
        if len(calls) == 1:
            return deepcopy(plan), "gemini"
        assert schema["required"] == ["edits"]
        assert [p[0] for p in kwargs["providers"]] == ["gemini"]
        assert "fault-1" in user and "/protocol/script" in user
        answer = {"edits":[edit(plan, "/protocol/script", plan["protocol"]["script"] if stubborn
                                 else good_plan()["protocol"]["script"])]}
        return answer, "gemini"
    monkeypatch.setattr(llm, "ask", ask)
    if stubborn:
        with pytest.raises(writer.Refused) as caught:
            writer.plan_deck(MOMENT, "sleep")
        assert len(calls) == 3 and caught.value.retry is False
    else:
        fixed, _, provider = writer.plan_deck(MOMENT, "sleep")
        assert len(calls) == 2 and provider == "gemini"
        assert not check(fixed)
        assert fixed["hooks"] == plan["hooks"] and fixed["citation_id"] == plan["citation_id"]


def test_owner_review_keeps_only_reviewable_outline_faults(monkeypatch):
    plan = valid()
    source = writer.load_citations()[plan["citation_id"]]
    monkeypatch.setattr(writer.bibliography, "discover", lambda *a: (None, []))
    monkeypatch.setattr(writer.bibliography, "recent", lambda: [])
    monkeypatch.setattr(writer.bibliography, "supported_indices", lambda c: [0])
    monkeypatch.setattr(writer.bibliography, "require_claim_support", lambda *a: None)
    monkeypatch.setattr(writer, "citations_for", lambda *a: [source])
    monkeypatch.setattr(writer, "recent_formulas", lambda: [])
    for hook in plan["hooks"]:
        hook["h2"] = "this subtitle has far too many words to fit"
    faults = writer.validate_plan(plan, MOMENT, "sleep", require_support=True)
    assert len(faults) == 1 and faults[0].startswith("not one hook is usable")
    calls = []
    def ask(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return deepcopy(plan), "gemini"
        # A vendor that makes no progress must not cause an endless retry.
        return {"edits": [{"path": "/field_1", "value": "unchanged", "fault": "fault-1"}]}, "gemini"
    monkeypatch.setattr(writer.llm, "ask", ask)
    kept, _, provider, notes = writer.plan_deck(MOMENT, "sleep", review_plan=True)
    assert kept == plan and provider == "gemini" and notes == faults
    assert len(calls) == 3
    assert writer.best_hook(kept, kept["scene_token"], allow_review=True) in kept["hooks"]


def test_owner_review_never_overrides_source_or_broken_shape():
    plan = valid()
    plan["citation_id"] = "not-a-source"
    assert any("allowlist" in fault for fault in writer.blocking_plan_faults(plan, "sleep"))
    plan = valid()
    plan["beats"][4]["n"] = 7
    assert "the beats are not numbered 1 to 9 in order" in writer.blocking_plan_faults(plan, "sleep")


def test_owner_review_accepts_all_visible_outline_faults(monkeypatch):
    plan = valid()
    source = writer.load_citations()[plan["citation_id"]]
    monkeypatch.setattr(writer.bibliography, "discover", lambda *a: (None, []))
    monkeypatch.setattr(writer.bibliography, "recent", lambda: [])
    monkeypatch.setattr(writer.bibliography, "supported_indices", lambda c: [0])
    monkeypatch.setattr(writer.bibliography, "require_claim_support", lambda *a: None)
    monkeypatch.setattr(writer, "citations_for", lambda *a: [source])
    monkeypatch.setattr(writer, "recent_formulas", lambda: [])
    plan["pattern_name"] = "alexithymia"
    for hook in plan["hooks"]:
        hook["h1"] = "This entire long cover line cannot fit on the card at all"
    expected = writer.validate_plan(plan, MOMENT, "sleep", require_support=True)
    assert expected and not writer.blocking_plan_faults(plan, "sleep")
    calls = []
    def ask(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return deepcopy(plan), "gemini"
        return {"edits": [{"path": "/field_1", "value": "unchanged", "fault": "fault-1"}]}, "gemini"
    monkeypatch.setattr(writer.llm, "ask", ask)
    kept, _, _, notes = writer.plan_deck(MOMENT, "sleep", review_plan=True)
    assert kept == plan and notes == expected
