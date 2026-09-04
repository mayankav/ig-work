"""Scene-first covers use the same rule at planning and selection. No network."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import writer
from test_writer import MOMENT, good_plan


def scene_plan():
    plan = good_plan()
    plan["pattern_name"] = ""
    plan["beats"][0]["beat"] = "At 2:17am you watch the clock instead of resting."
    plan["beats"][3]["beat"] = "Explain what checking the clock costs the reader."
    return plan


def test_plan_without_invented_name_is_valid():
    assert writer.validate_plan(scene_plan(), MOMENT, "sleep") == []
    assert writer.PLAN_SCHEMA["properties"]["pattern_name"].get("minLength", 0) == 0


def test_scene_hook_is_used_unchanged():
    plan = scene_plan()
    assert writer.best_hook(plan, "2:17am") == plan["hooks"][0]


def test_optional_name_can_be_explained_later_without_cover_name():
    plan = good_plan()
    plan["beats"][0]["beat"] = "At 2:17am you watch the clock instead of resting."
    assert writer.validate_plan(plan, MOMENT, "sleep") == []


@pytest.mark.parametrize("field", ["h1", "h2"])
def test_optional_label_cannot_replace_cover_scene(field):
    hook = dict(good_plan()["hooks"][0])
    hook[field] = "Clock maths. The [[clock]] keeps you up." if field == "h1" else "Clock maths keeps you up."
    assert any("cover prints pattern name" in f for f in writer.hook_faults(hook, "clock maths"))


def test_chooser_does_not_restore_rejected_name_first_hook():
    plan = good_plan()
    bad = {"h1": "Clock maths at [[2:17am]].", "h2": "Rest need not wait."}
    plan["hooks"].insert(0, bad)
    assert writer.best_hook(plan, "2:17am") != bad


def test_no_valid_hook_stops_instead_of_using_failed_candidate():
    plan = good_plan()
    plan["hooks"] = [{"h1": "Clock maths at [[2:17am]].", "h2": "Rest need not wait."}]
    with pytest.raises(writer.Refused) as caught:
        writer.best_hook(plan, "2:17am")
    assert caught.value.retry is False


@pytest.mark.parametrize("label", ["execution freeze", "boundaries", "you cannot sit down until it is clear"])
def test_optional_does_not_mean_unchecked(label):
    plan = scene_plan()
    plan["pattern_name"] = label
    assert any("pattern name" in f for f in writer.validate_plan(plan, MOMENT, "sleep"))


def test_live_prompts_and_schema_do_not_force_a_name():
    assert "PATTERN NAMES ARE OPTIONAL" in writer.PLAN_SYSTEM
    assert "NO LABEL IS REQUIRED" in writer.DRAFT_SYSTEM
    for instruction in ("THE NAME IS THE POST", "h1 CONTAINS THE NAME", "SAY THE NAME TWICE"):
        assert instruction not in writer.PLAN_SYSTEM + writer.DRAFT_SYSTEM
    assert "Contains the pattern name" not in writer.DRAFT_SCHEMA["properties"]["explains"]["description"]
    assert "short name" not in writer.AXES["formula"]["craft-name"]


def test_active_guidance_does_not_restore_invented_engagement_proof():
    refs = Path(__file__).resolve().parents[1] / "references"
    text = "\n".join((refs / name).read_text() for name in
                     ("brand-voice.md", "content-playbook.md"))
    for unsupported in ("9.8", "340%", "~2B", "4–6x", "4-6x",
                        "real hooks proven", "Highest DM-share", "100+ viral"):
        assert unsupported not in text


def test_source_application_schema_does_not_require_invented_label():
    text = writer.DRAFT_SCHEMA["properties"]["explains"]["description"]
    assert "supported" in text
    assert "pattern name" not in text
