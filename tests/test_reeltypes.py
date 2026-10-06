import json

from suresilly import inbox, reeltypes


LESSONS = [{"title": "Study on abusive supervision", "link": "https://doi.org/1", "source": "OpenAlex", "angle": "harsh days carry over", "story_kind": "research"},
           {"title": "Founder on explaining the why", "link": "https://b/1", "source": "Blog", "angle": "explain the why", "story_kind": "opinion"},
           {"title": "Guidance on listening", "link": "https://g/1", "source": "Gallup", "angle": "listen first", "story_kind": "official"}]


def item(n, score=9, link=None):
    return {"title": f"Story {n}", "link": link or f"https://x.test/{n}", "source": "S", "score": score, "angle": f"angle {n}"}


def answer(types_by_index):
    return {"items": [{"i": i, "types": t, "why": "w"} for i, t in types_by_index.items()]}


def test_every_type_has_a_description_and_the_prompt_lists_them_all_without_samples():
    system, user = reeltypes.fit_prompt([item(1)])
    assert all(t.id in system and t.gives in system for t in reeltypes.TYPES)
    assert "Items:\n0. Story 1 | angle: angle 1" in user and "for example" not in system.lower() and "e.g." not in system


def test_unknown_types_and_garbled_answers_leave_an_item_unplanned():
    got = reeltypes.fits([item(0), item(1)], lambda m: answer({0: ["story", "nonsense", "story"], 1: "bad"}))
    assert got[0]["types"] == ["story"] and got[1]["types"] == []
    assert reeltypes.fits([item(0)], lambda m: (_ for _ in ()).throw(RuntimeError("down")))[0]["types"] == []


def test_the_plan_never_repeats_a_type_in_a_row_and_caps_each_type():
    stock = [item(n, score=10 - n % 3) for n in range(14)]
    call = lambda m: answer({n: ["story", "news", "can_they"] for n in range(14)})
    plan = reeltypes.plan(stock, call, slots=14)
    types = [p["type"] for p in plan]
    assert all(a != b for a, b in zip(types, types[1:]))
    assert max(types.count(t) for t in set(types)) <= 4 and len(plan) == 12     # three types x cap 4: two items have no type left


def test_the_plan_takes_the_best_items_first_and_starts_differently_from_last_week():
    stock = [item(1, score=5), item(2, score=9), item(3, score=8)]
    call = lambda m: {"items": [{"i": 0, "types": ["story"]}, {"i": 1, "types": ["story"]}, {"i": 2, "types": ["mirror"], "lesson": 0}]}
    plan = reeltypes.plan(stock, call, history=["story"], slots=2, lessons=LESSONS)
    assert [p["title"] for p in plan] == ["Story 3", "Story 2"] and plan[0]["type"] == "mirror"


def test_a_fact_type_is_flagged_for_the_fact_check_unless_the_source_is_official(monkeypatch):
    monkeypatch.setattr(inbox, "SOURCES", {"official_domains": ["pib.gov.in", "labour.gov.in"]})
    stock = [item(1, link="https://www.pib.gov.in/x"), item(2, link="https://news.test/y"), item(3, link="https://fakepib.gov.in.evil.com/z")]
    plan = {p["title"]: p for p in reeltypes.plan(stock, lambda m: answer({0: ["news"], 1: ["can_they"], 2: ["news"]}), slots=3)}
    assert plan["Story 1"]["fact_check"] is False and plan["Story 2"]["fact_check"] is True and plan["Story 3"]["fact_check"] is True


def test_the_plan_is_saved_with_a_history_that_next_week_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(reeltypes, "PLAN_FILE", tmp_path / "plan.json")
    reeltypes.save([{"type": "story"}, {"type": "mirror"}], ["news"])
    assert reeltypes.load_history() == ["news", "story", "mirror"]


def test_manager_types_need_a_lesson_and_carry_it_into_the_plan():
    stock = [item(0), item(1)]
    call = lambda m: {"items": [{"i": 0, "types": ["mirror"], "lesson": 1, "why": "w"}, {"i": 1, "types": ["contrast", "story"], "lesson": 9, "why": "w"}]}
    plan = {p["title"]: p for p in reeltypes.plan(stock, call, lessons=LESSONS, slots=2)}
    assert plan["Story 0"]["type"] == "mirror" and plan["Story 0"]["lesson"]["link"] == "https://b/1"
    assert plan["Story 1"]["type"] == "story" and "lesson" not in plan["Story 1"]          # an invalid lesson number drops contrast


def test_a_week_keeps_its_manager_side_reels_even_when_other_items_score_higher():
    stock = [item(n, score=10) for n in range(6)] + [item(6, score=6), item(7, score=6), item(8, score=6)]
    rows = {n: {"i": n, "types": ["story"], "lesson": None, "why": "w"} for n in range(6)}
    rows.update({n: {"i": n, "types": ["contrast"], "lesson": n - 6, "why": "w"} for n in (6, 7, 8)})
    plan = reeltypes.plan(stock, lambda m: {"items": [rows[n] for n in range(9)]}, lessons=LESSONS, slots=6)
    assert sum(p["type"] in reeltypes.MANAGER_TYPES for p in plan) == 3


def test_a_lesson_is_used_once_in_a_week_and_not_again_next_week():
    stock = [item(0), item(1)]
    same = lambda m: {"items": [{"i": 0, "types": ["contrast", "story"], "lesson": 0, "why": "w"}, {"i": 1, "types": ["contrast", "story"], "lesson": 0, "why": "w"}]}
    plan = reeltypes.plan(stock, same, lessons=LESSONS, slots=2)
    assert sorted(p["type"] for p in plan) == ["contrast", "story"]                      # the second item falls back to its other type
    plan = reeltypes.plan(stock, same, lessons=LESSONS, slots=2, used_lessons=["https://doi.org/1"])
    assert [p["type"] for p in plan] == ["story", "story"]                               # last week's lesson is resting


def test_used_lessons_are_remembered(tmp_path, monkeypatch):
    monkeypatch.setattr(reeltypes, "PLAN_FILE", tmp_path / "plan.json")
    reeltypes.save([{"type": "mirror", "lesson": {"link": "https://b/1"}}, {"type": "story"}], [])
    assert reeltypes.load_used_lessons() == ["https://b/1"]


def test_every_planned_reel_carries_second_choices_and_a_story_is_always_one():
    stock = [item(0)]
    plan = reeltypes.plan(stock, lambda m: {"items": [{"i": 0, "types": ["news", "can_they"], "lesson": None, "why": "w"}]}, slots=1)
    assert plan[0]["type"] == "news" and plan[0]["alternatives"] == ["can_they", "story"]
    manager = reeltypes.plan(stock, lambda m: {"items": [{"i": 0, "types": ["mirror"], "lesson": 0, "why": "w"}]}, lessons=LESSONS, slots=1)
    assert manager[0]["type"] == "mirror" and manager[0]["alternatives"] == ["story"]
