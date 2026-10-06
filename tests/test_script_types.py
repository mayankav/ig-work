import json

import pytest

from suresilly import factcheck, script as S

FACT = {"id": "u", "area": "news", "title": "EPFO ceiling", "claim": "The wage ceiling is now Rs 25,000 a month.", "source": "pib.gov.in",
        "source_date": "2026-10-06", "law": "The ceiling is raised to Rs 25,000 a month from 1 October.", "caveat": "", "status": "checked"}


def seed(kind, fact=None, **more):
    base = {"type": kind, "title": "EPFO wage ceiling raised", "angle": "what it changes for pay", "link": "https://x.test/a", "source": "S"}
    return {**base, **({"fact": fact} if fact else {}), **more}


GOOD = {
    "story": {"event": "The wage ceiling for provident fund rose to Rs 25,000 a month.", "turn": "More young workers now get contributions on their pay.",
              "move": "Ask HR in writing: does my contribution use the new ceiling this month?", "key": 2},
    "can_they": {"situation": "Can HR keep your pay slip for a week?", "answer": "The source says the ceiling is Rs 25,000 a month, nothing about slips.",
                 "reply_me": "Hi, please send my pay slip for this month by Friday.", "key": 2},
    "news": {"headline": "Wage ceiling goes up to Rs 25,000", "changes": "Pay up to that level now counts for contributions.",
             "move": "Check your pay slip: is the new ceiling used?", "key": 2},
    "contrast": {"request": "A deliverable is needed a day early.", "pushy": "Send it by tonight, no excuses.", "professional": "Can we move it to noon tomorrow, and I will clear your queue?",
                 "why": "The second names a time and offers a trade.", "reply_me": "I can send it by noon tomorrow, does that work?", "key": 2},
    "mirror": {"sent": "Why is this still not done?", "lands": "The junior freezes and starts hiding questions.", "better": "What is blocking you, and what do you need?",
               "why": "It asks for the blocker and offers help.", "key": 2},
}


@pytest.mark.parametrize("kind", S.NEW)
def test_every_new_type_has_a_spec_a_hook_area_and_no_sample(kind):
    t = S.TEMPLATES[kind]
    assert t.area in S.hooks.AREAS and any(f.name == "key" for f in t.fields) and t.fields[0].name == "cover_1"
    from suresilly import hooks
    system = S.system_prompt(kind, hooks.pick(t.area, [], 0))
    assert all(f.name in system for f in t.fields if f.part == "body") and "for example" not in system.lower() and "e.g." not in system


@pytest.mark.parametrize("kind", S.NEW)
def test_a_good_body_passes_the_check_with_a_fact(kind):
    body = {k: v for k, v in GOOD[kind].items()}
    fields = {f.name for f in S.TEMPLATES[kind].fields if f.part == "body"}
    assert S.check(kind, body, FACT, fields=fields) == []


@pytest.mark.parametrize("kind", ("contrast", "mirror", "story"))
def test_without_a_source_the_reel_may_not_name_one_or_use_a_number(kind):
    body = dict(GOOD[kind])
    if kind == "story":
        body["event"] = "A fresher asked online which job offer to take."      # a reasoned story has no number in it
    field = {"contrast": "why", "mirror": "why", "story": "turn"}[kind]
    fields = {f.name for f in S.TEMPLATES[kind].fields if f.part == "body"}
    body[field] = "Research shows that clear asks cut stress by 40 percent in teams."
    problems = S.check(kind, body, None, fields=fields)
    assert any("research" in p and "no source" in p for p in problems) and any("40" in p or "number" in p for p in problems)
    body[field] = "A clear ask lets the other person plan, so nothing waits in silence."
    assert S.check(kind, body, None, fields=fields) == []


def test_a_sourced_reel_may_use_only_the_numbers_of_its_fact():
    body = dict(GOOD["news"], changes="Pay up to Rs 30,000 now counts for contributions.")
    problems = S.check("news", body, FACT, fields={"headline", "changes", "move", "key"})
    assert any("30000" in p for p in problems)


def test_the_user_prompt_gives_a_fact_block_or_the_reasoning_rule_and_never_both():
    with_fact = S.user_prompt("news", seed("news", FACT))
    assert "FACT (the only facts you may state" in with_fact and "claim: The wage ceiling is now Rs 25,000" in with_fact and "No FACT block" not in with_fact
    without = S.user_prompt("mirror", seed("mirror", lesson={"angle": "ask for the blocker"}))
    assert "No FACT block" in without and "never write research" in without and "ask for the blocker" in without and "FACT (the only" not in without
    reported = S.user_prompt("story", seed("story", {**FACT, "status": "reported"}))
    assert "reported by the source, never that it is official" in reported


def test_the_viewer_text_and_the_questions_exist_for_every_new_type():
    for kind in S.NEW:
        text = S.viewer_text(kind, {**GOOD[kind], "cover_1": "What now?", "cover_2": "Here is the answer"})
        assert "Scene 1" in text and "Cover shown" in text
        assert all(q in S.QUESTIONS for q in S.asks(kind, "body") + S.asks(kind, "dress"))
    assert S.asks("saythis", "body") == S.ASK["body"]                      # the old types keep their questions


class Model:
    """A fake writer: the body, then the dress, for any type."""
    def __init__(self, kind):
        self.kind, self.calls = kind, []

    def __call__(self, messages):
        self.calls.append(messages[0]["content"])
        if "Fields to write" in messages[0]["content"] and "cover_1" in messages[0]["content"].split("Fields to write")[1]:
            return {"cover_1": "Why is your pay slip late?", "cover_2": "Here is what to ask", "payoff": "Ask for it in writing by a date.",
                    "caption": "A date makes it easy to chase it. Keep the reply short."}
        return dict(GOOD[self.kind])


@pytest.mark.parametrize("kind", S.NEW)
def test_write_makes_a_whole_script_for_each_new_type_in_two_steps(kind):
    model = Model(kind)
    script, report = S.write(kind, seed(kind, FACT), model, day=1, repairs=1)
    assert not report["problems"][-1] and report["steps"] == {"body": 1, "dress": 1}
    assert all(f.name in script for f in S.TEMPLATES[kind].fields)


def test_a_reasoned_reel_that_cites_research_is_sent_back_with_the_reason():
    seen = []

    def model(messages):
        seen.append(messages[-1]["content"])
        if "cover_1" in messages[0]["content"].split("Fields to write")[1]:
            return {"cover_1": "Why does it freeze them?", "cover_2": "Here is the fix", "payoff": "Ask for the blocker, not for the date.", "caption": "Blockers hide when blame comes first. Ask about the block."}
        body = dict(GOOD["mirror"])
        if len(seen) == 1:
            body["lands"] = "A study shows juniors freeze under blame."
        return body

    script, report = S.write("mirror", seed("mirror"), model, day=2, repairs=2)
    assert report["steps"]["body"] == 2 and "no source" in json.dumps(report["problems"][0]) and "study" not in script["lands"].lower()


def test_the_factcheck_fact_feeds_the_writer_without_changes():
    grounded = {"status": "verified", "source": {"url": "https://pib.gov.in/x", "title": "Wage ceiling", "site": "pib.gov.in", "official": True},
                "claims": [{"quote": "The ceiling is raised to Rs 25,000 a month from 1 October.", "says": "The ceiling is Rs 25,000 a month."}], "checked_at": "2026-10-06"}
    fact = factcheck.to_fact({"type": "news", "title": "t"}, grounded)
    body = dict(GOOD["news"])
    assert S.check("news", body, fact, fields={"headline", "changes", "move", "key"}) == []


def test_a_cover_or_caption_may_not_claim_a_personal_experience():
    dress = {"cover_1": "My senior texted me about AI", "cover_2": "Here is what I told her", "payoff": "Ask for the blocker first.", "caption": "A clear ask saves a week."}
    body = dict(GOOD["mirror"], **dress)
    problems = S.check("mirror", body, None, fields={"cover_1", "cover_2", "payoff", "caption"})
    assert sum("speaks as" in p for p in problems) == 2
    ok = dict(dress, cover_1="Your manager texted you again?", cover_2="Here is what to ask")
    assert not any("speaks as" in p for p in S.check("mirror", dict(GOOD["mirror"], **ok), None, fields={"cover_1", "cover_2", "payoff", "caption"}))


def test_the_prompt_tells_the_writer_to_mark_its_own_view_and_to_speak_to_you():
    text = S.user_prompt("story", seed("story", {**FACT, "status": "reported"}))
    assert "mark it with words like it may" in text and "Speak to the viewer as you" in text and "no I, my or me" in text
