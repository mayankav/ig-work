"""Field repairs preserve clean text and are judged by checks, not the model."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import draft_repair as repair
import llm
import writer
from test_writer import good_plan, MOMENT


SPEC = {"type": "object", "additionalProperties": False,
        "required": ["bad", "clean", "items"], "properties": {
            "bad": {"type": "string", "maxLength": 40},
            "clean": {"type": "string"},
            "items": {"type": "array", "minItems": 2, "maxItems": 2,
                      "items": {"type": "string"}}}}
BASE = {"bad": "too long", "clean": "Keep exactly this.", "items": ["first", "second"]}


def verify(draft):
    faults = [] if draft["bad"] == "fixed" else ["shorten bad"]
    if draft["items"][0] == "broken":
        faults.append("broken item")
    return faults


def edit(path="/bad", value="fixed", fault="fault-1"):
    return {"path": path, "value": value, "fault": fault}


def test_unsolicited_clean_edits_are_removed():
    before = deepcopy(BASE)
    value, faults = repair.apply(BASE, verify(BASE), {"edits": [edit(),
        edit("/clean", "rewritten"), edit("/items/1", "rewritten")]}, SPEC, verify)
    assert value == BASE | {"bad": "fixed"} and faults == []
    assert BASE == before


def test_fault_ids_do_not_embed_quoted_descriptions():
    faults = ['the Say line starts "You..."', "another fault", 'the Say line starts "You..."']
    assert repair.fault_map(faults) == {"fault-1": faults[0], "fault-2": faults[1]}
    enum = repair.schema(BASE, faults)["properties"]["edits"]["items"]["properties"]["fault"]["enum"]
    assert enum == ["fault-1", "fault-2"]
    assert llm.validate({"edits": [edit()]}, repair.schema(BASE, faults)) == []


@pytest.mark.parametrize("edits", [
    [edit(), edit("/items/0", "broken")],
    [edit(value="still broken")],
    [edit(value="x" * 41)],
    [edit("/unknown")],
    [edit("/items/2")],
    [edit(), edit()],
    [edit(fault="model invented a fault")],
])
def test_invalid_or_nonimproving_edit_keeps_original(edits):
    assert repair.apply(BASE, verify(BASE), {"edits": edits}, SPEC, verify) == (BASE, verify(BASE))


def test_combined_fix_can_keep_two_necessary_fields():
    def combined(value):
        return [] if value["bad"] == value["clean"] == "fixed" else ["fix the pair"]
    value, faults = repair.apply(BASE, combined(BASE), {"edits": [
        edit(), edit("/clean")]}, SPEC, combined)
    assert not faults and value["bad"] == value["clean"] == "fixed"
    assert value["items"] == BASE["items"]


def test_verification_failure_propagates_not_approval():
    def broken(value):
        raise RuntimeError("checker failed")
    with pytest.raises(RuntimeError, match="checker failed"):
        repair.apply(BASE, verify(BASE), {"edits": [edit()]}, SPEC, broken)


def test_real_spoken_fault_is_repaired_without_rewriting_clean_text():
    base = deepcopy(BASE)
    base["bad"] = "Nolen-Hoeksema found that going over things keeps the mood low."
    spec = deepcopy(SPEC)
    spec["properties"]["bad"]["maxLength"] = 220

    def real_check(value):
        return writer.check_repeats(
            "### Slide 3 · Source\n"
            "- **Source:** — Susan Nolen-Hoeksema, *Women Who Think Too Much* (2003)\n"
            "### Slide 5 · Script\n- **Say:** " + value["bad"])

    faults = real_check(base)
    assert len(faults) == 1
    value, remaining = repair.apply(base, faults, {"edits": [
        edit(value="I am done for today."),
        edit("/clean", "An unrelated rewrite.")]}, spec, real_check)
    assert remaining == [] and value["bad"] == "I am done for today."
    assert value["clean"] == base["clean"] and value["items"] == base["items"]


def sample(spec):
    if spec["type"] == "object":
        return {k: sample(v) for k, v in spec["properties"].items()}
    if spec["type"] == "array":
        return [sample(spec["items"]) for _ in range(spec.get("minItems", 1))]
    return "clean text " * max(1, (spec.get("minLength", 0) + 10) // 11)


@pytest.mark.parametrize("stubborn", [False, True])
@pytest.mark.parametrize("owner_review", [False, True])
def test_actual_writer_loop_merges_edits_and_stops_unchanged(monkeypatch, stubborn, owner_review):
    draft = sample(writer.DRAFT_SCHEMA)
    draft["script"]["new"] = "bad speech marker"
    plan = good_plan()
    citation = {"line": "verified source fixture", "claims": ["verified claim fixture"]}
    monkeypatch.setattr(writer, "plan_deck", lambda *a, **k: (plan, writer.draw_axes(MOMENT), "gemini"))
    monkeypatch.setattr(writer, "load_citations", lambda: {plan["citation_id"]: citation})
    monkeypatch.setattr(writer.bibliography, "require_claim_support", lambda *a: None)
    monkeypatch.setattr(writer, "best_hook", lambda *a: plan["hooks"][0])
    monkeypatch.setattr(writer, "verify_draft", lambda md, *a:
                        ["fix spoken line"] if "bad speech marker" in writer.no_accent(md) else [])
    calls = []

    def ask(system, user, schema, **kwargs):
        calls.append((system, user, schema, kwargs))
        if len(calls) == 1:
            return deepcopy(draft), "gemini"
        assert schema["required"] == ["edits"]
        assert [p[0] for p in kwargs["providers"]] == ["gemini"]
        assert "fault-1" in user and "fix spoken line" in user
        return {"edits": [edit("/script/new", "bad speech marker" if stubborn else "I can talk later."),
                          edit("/cost/body", "Unasked rewrite")]}, "gemini"

    monkeypatch.setattr(llm, "ask", ask)
    if stubborn and owner_review:
        monkeypatch.setattr(writer, 'hard_faults', lambda md: [])
        markdown, _, _, wrote, faults = writer.write_deck(MOMENT, "sleep", "title", "pattern", "pillar", review_draft=True)
        assert len(calls) == 3 and faults == ['fix spoken line']
        assert 'bad speech marker' in writer.no_accent(markdown)
    elif stubborn:
        with pytest.raises(writer.Refused) as caught:
            writer.write_deck(MOMENT, "sleep", "title", "pattern", "pillar")
        assert len(calls) == 3 and caught.value.retry is False
    else:
        markdown, _, _, wrote, faults = writer.write_deck(MOMENT, "sleep", "title", "pattern", "pillar")
        assert len(calls) == 2 and wrote == "gemini" and faults == []
        assert "I can talk" in markdown and "Unasked rewrite" not in markdown
        assert citation["line"] in markdown and citation["claims"][0] in markdown


def test_grammar_match_is_not_evidence_of_copied_content():
    text='### Slide 9 · CTA\n- **Closing thought:** You do not have to finish it today.\n'
    assert writer.check_leak(text, {'do not have to'}) == []
    copied='### Slide 9 · CTA\n- **Closing thought:** A bicycle needs new tires.\n'
    assert writer.check_leak(copied, {'bicycle needs new tires'})


def test_common_action_fragment_is_not_an_example_but_subject_words_are():
    ordinary = '### Slide 5 · Script\n- **Say:** I will do this before I sit down.\n'
    assert writer.check_leak(ordinary, {'before i sit down'}) == []
    subject = '### Slide 5 · Script\n- **Say:** Move the cup to the sink.\n'
    assert writer.check_leak(subject, {'move the cup to'})
