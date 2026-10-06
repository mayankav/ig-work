import json

import pytest

from suresilly import hooks, script
from suresilly.script import FACT, TEMPLATES, check

def test_no_fact_carries_post_copy():
    allowed = {"id", "area", "title", "claim", "source", "source_date", "law", "caveat", "status"}
    for fact in FACT.values():
        assert set(fact) <= allowed
        assert fact["status"] in ("checked", "reported") and fact["source"] and fact["source_date"]


def test_no_prompt_carries_a_sample_to_imitate():
    for template, t in TEMPLATES.items():
        for hook in hooks.CARDS:
            prompt = script.system_prompt(template, hook).lower()
            assert "worked example" not in prompt and "for example" not in prompt.split("rules for every field")[0]
    for template in script.IDEA_FIELDS:
        system, user = script.ideas_prompt(template, [], 6, "an email phrase")
        assert "example" not in system.lower()


def good(template="saythis"):
    base = {
        "saythis": {"cover_1": "Your manager wants an early call.", "cover_2": "Here is how.", "payoff": "I can join at 10, if that works for you.",
                    "caption": "An early call does not need an early yes. Save this for Sunday night.", "when": "MANAGER, 9:40 PM",
                    "boss_text": "Can we speak at 8 tomorrow?", "reply_me": "I can join at 10. Shall I send my update by 9?",
                    "why": "You answer with a time of your own.", "key": 3},
        "dictionary": {"cover_1": "Your boss says ____ back.", "cover_2": "Do you know it?", "payoff": "= later, maybe never.", "caption": "Later has no date. Ask for one.",
                       "phrase": "touch base soon", "meaning": "= maybe, one day.", "boss_text": "Let us touch base soon.",
                       "reply_me": "Sure. Can we fix Thursday at 4?", "why": "A date turns soon into a plan.", "key": 3},
    }
    return dict(base[template])


def test_a_good_script_passes_and_a_missing_field_is_named():
    assert check("saythis", good(), None, hooks.BY_ID[3]) == []
    data = good(); del data["reply_me"]
    assert any('"reply_me" is missing' in p for p in check("saythis", data))


def test_too_many_words_and_too_many_characters_are_named_with_the_limit():
    data = good(); data["why"] = "A time replaces a promise with a plan and then some more words here."
    assert any('"why" has' in p and "4 to 10" in p for p in check("saythis", data))
    data = good(); data["reply_me"] = "Respectfully acknowledging your communication regarding scheduling arrangements considerations tomorrow."
    assert any("characters" in p for p in check("saythis", data))


def test_a_chat_too_long_for_the_screen_is_caught():
    data = good(); data["boss_text"] = "Can you check the deck and the numbers tonight please yaar?"
    data["reply_me"] = "Seen. I will check the deck first thing tomorrow, and the numbers by noon, then send both to you together."
    assert any("characters in all" in p for p in check("saythis", data))


def test_a_number_that_is_not_in_the_fact_is_caught_even_when_spelled_out():
    fact = FACT["wages-2-days"]
    data = {"cover_1": "HR says one thing about your last pay.", "cover_2": "Is it?", "payoff": "Final wages are due in two working days.",
            "caption": "Your last pay is not a favour. Save this for your last day.", "hr_says": "Your final settlement takes a month.",
            "law_says": "Final wages are due within four working days.", "key": 3,
            "reply_me": "Please confirm the date my final wages will be paid, under section 17(2) of the Code on Wages."}
    assert any("4" in p for p in check("rights", data, fact))
    data["law_says"] = "Final wages are due within 2 working days."
    assert check("rights", data, fact) == []


def test_the_cover_may_not_print_the_number_the_law_adds():
    fact = FACT["wages-2-days"]
    data = {"cover_1": "Your wages are due in two working days.", "cover_2": "Is it?", "payoff": "Final wages are due in 2 working days.",
            "caption": "Your last pay is not a favour. Save this for your last day.", "hr_says": "Your final settlement takes a month.",
            "law_says": "Final wages are due within 2 working days.", "key": 3,
            "reply_me": "Please confirm the date my final wages will be paid, under section 17(2) of the Code on Wages."}
    assert any("gives away the number 2" in p for p in check("rights", data, fact))


def test_a_cover_with_no_gap_is_caught_and_a_promise_in_the_models_own_words_counts_as_a_gap():
    data = good(); data["cover_1"], data["cover_2"] = "Your manager asks for one thing.", "Late replies work fine."
    assert any("leaves no gap" in p for p in check("saythis", data))
    for promise in ("Here is how.", "The reply is below.", "Say this first."):
        data["cover_2"] = promise
        assert check("saythis", data, None, hooks.BY_ID[3]) == []


def test_an_instruction_without_its_words_and_a_legal_claim_without_a_fact_are_caught():
    data = good(); data["reply_me"] = "Reply and ask for a time tomorrow."
    assert any("without its exact words" in p for p in check("saythis", data))
    data = good(); data["why"] = "The law says a time makes it real."
    assert any("no FACT" in p for p in check("saythis", data))


def test_banned_words_and_dashes_are_caught():
    data = good(); data["caption"] = "A reply with a time is a plan — save it, donkey. Actually good."
    problems = check("saythis", data)
    assert any("donkey" in p for p in problems) and any("dashes" in p for p in problems) and any("actually" in p for p in problems)


def test_clean_fixes_quotes_hyphens_capitals_and_full_stops():
    out = script.clean("saythis", {"reply_me": "  “seen.  I will do it” ", "why": "a time makes it real", "key": "2", "cover_1": "“Hi there”", "boss_text": "non‑stop"})
    assert out == {"reply_me": "Seen. I will do it.", "why": "A time makes it real.", "key": 2, "cover_1": "“Hi there”", "boss_text": "Non-stop."}


def make_call(answers, seen=None):
    answers = list(answers)

    def call(messages):
        if seen is not None:
            seen.append(messages)
        return dict(answers.pop(0))
    return call


def test_write_repairs_a_bad_body_then_writes_the_cover_for_it_and_reports_the_steps():
    seed = {"when": "MANAGER, 9:40 PM", "situation": "your manager asks for an early call tomorrow"}
    bad = dict(good(), reply_me="Reply and ask for a later time.")
    seen = []
    data, report = script.write("saythis", seed, make_call([bad, good(), good()], seen))
    assert data["reply_me"] == good()["reply_me"] and report["steps"] == {"body": 2, "dress": 1} and report["problems"][-1] == []
    assert "without its exact words" in seen[1][-1]["content"]
    assert '"cover_1"' not in seen[0][0]["content"].split("write only these):")[1]          # the body step does not ask for the cover
    assert '"reply_me"' not in seen[2][0]["content"].split("write only these):")[1]        # the dress step does not ask for the body
    assert good()["reply_me"] in seen[2][1]["content"]                                      # but it reads the finished body


def test_write_keeps_the_ideas_given_fields_whatever_the_model_says():
    seed = {"phrase": "touch base soon", "meaning": "= maybe, one day."}
    answer = dict(good("dictionary"), meaning="= something else", phrase="made up phrase")
    data, report = script.write("dictionary", seed, make_call([answer, answer]))
    assert data["phrase"] == "touch base soon" and data["meaning"] == "= maybe, one day." and report["problems"][-1] == []


def test_a_script_that_never_passes_comes_back_with_its_problems_and_no_stock_copy():
    seed = {"phrase": "touch base soon", "meaning": "= maybe, one day."}
    data, report = script.write("dictionary", seed, make_call([{"reply_me": "hi"}] * 3))
    assert report["tries"] == 3 and report["steps"] == {"body": 3} and report["problems"][-1]
    assert "cover_1" not in data


def test_each_step_names_the_fields_it_asks_for_and_none_it_gives_or_leaves_to_the_other_step():
    for template, t in TEMPLATES.items():
        for part in ("body", "dress"):
            prompt = script.system_prompt(template, hooks.pick(t.area), part=part)
            rows = prompt.split("write only these):")[1]
            for f in t.fields:
                assert (f'"{f.name}"' in rows) == (f.name not in t.given and f.part == part)
        assert "hook technique" in script.system_prompt(template, hooks.pick(t.area), part="dress").lower()
        assert "hook technique" not in script.system_prompt(template, hooks.pick(t.area), part="body").lower()


def test_ideate_keeps_only_good_new_ideas():
    answer = {"ideas": [
        {"phrase": "touch base offline", "meaning": "= not in front of everyone."},
        {"phrase": "as per policy", "meaning": "the rule says so"},                  # meaning has no "="
        {"phrase": "the law says so", "meaning": "= you cannot argue."},             # a legal claim
        {"phrase": "kindly revert", "meaning": "= reply to me."},
        {"phrase": "kindly revert", "meaning": "= reply."},                          # repeated in the same list
        {"phrase": "ping me anytime", "meaning": "= any hour."},                     # used lately
        {"phrase": "a phrase that is far too long for the screen", "meaning": "= no."}]}
    ideas = script.ideate("dictionary", make_call([answer]), recent=["ping me anytime"])
    assert [i["phrase"] for i in ideas] == ["touch base offline", "kindly revert"]


def test_ideate_survives_a_bad_reply_and_names_the_area_and_recent_topics_in_the_prompt():
    assert script.ideate("saythis", make_call([{"ideas": "none"}])) == []
    seen = []
    script.ideate("saythis", make_call([{"ideas": []}], seen), recent=["a late file"], area="a polite no")
    assert "a polite no" in seen[0][1]["content"] and "a late file" in seen[0][1]["content"]


def test_a_script_too_close_to_a_recent_post_is_rejected():
    old = good()
    again = dict(good(), cover_1="Another early call is coming.", reply_me="I can join at 10. Shall I send the update by 9?")
    problems = check("saythis", again, None, hooks.BY_ID[3], [old])
    assert any('"reply_me" is too close' in p for p in problems)
    same = dict(good(), cover_2="Here is how.")
    assert any('"cover_2" repeats a recent post' in p for p in check("saythis", same, None, hooks.BY_ID[3], [good()]))
    different = dict(good(), cover_1="A late file lands in your chat.", cover_2="Reply like this.", reply_me="Seen. Tomorrow at 9, with the file attached.",
                     why="A fixed hour keeps your night yours.", boss_text="Need the file tonight.", caption="Seen is not a yes. Save this for the next late ping.")
    assert check("saythis", different, None, hooks.BY_ID[3], [good()]) == []


def test_deal_gives_a_voice_and_a_shape_that_were_not_just_used():
    recent = [("dry", "time"), ("warm", "question"), ("playful", "limit")]
    voice, shape = script.deal(5, recent)
    assert voice[0] not in ("dry", "warm", "playful") and shape[0] not in ("time", "question", "limit")
    assert len({script.deal(d)[0][0] for d in range(8)}) == len(script.VOICES)


def test_pick_area_skips_the_last_four_areas():
    pool = script.AREAS["dictionary"]
    assert all(script.pick_area("dictionary", d, list(pool[:4])) not in pool[:4] for d in range(10))


def test_write_tells_the_model_the_dealt_voice_and_hook_and_reports_them():
    seen = []
    seed = {"when": "MANAGER, 9:40 PM", "situation": "your manager asks for an early call tomorrow"}
    data, report = script.write("saythis", seed, make_call([good(), good()], seen), recent=[{"voice": "dry", "shape": "time", "hook": 3}], day=1)
    assert report["voice"] != "dry" and report["hook"] != 3
    assert f"Voice for this post: {dict(script.VOICES)[report['voice']]}" in seen[0][0]["content"]
    assert dict(script.SHAPES)[report["shape"]] in seen[0][0]["content"]


def test_rank_ideas_reorders_and_never_loses_or_repeats_an_idea():
    ideas = [{"phrase": "a"}, {"phrase": "b"}, {"phrase": "c"}]
    assert [i["phrase"] for i in script.rank_ideas("dictionary", ideas, make_call([{"order": [2, 0]}]))] == ["c", "a", "b"]
    assert [i["phrase"] for i in script.rank_ideas("dictionary", ideas, make_call([{"order": [1, 1, 9, "x"]}]))] == ["b", "a", "c"]


def test_rank_ideas_keeps_the_order_when_the_judge_fails():
    ideas = [{"phrase": "a"}, {"phrase": "b"}]

    def broken(messages):
        raise RuntimeError("503")
    assert script.rank_ideas("dictionary", ideas, broken) == ideas
    assert script.rank_ideas("dictionary", ideas[:1], broken) == ideas[:1]


def test_judge_turns_a_no_into_a_plain_problem_and_survives_a_bad_judge():
    seed = {"when": "MANAGER, 9:40 PM", "situation": "your manager asks for an early call tomorrow"}
    verdict = {"reply_fits": {"ok": False, "fix": "Answer the question about the call."}, "cover_fits": {"ok": True, "fix": ""},
               "faithful": {"ok": True}, "natural": {"ok": False}, "usable": {"ok": True}}
    problems = script.judge("saythis", seed, good(), make_call([verdict]))
    assert problems == ["reply fits: Answer the question about the call.", "natural: a second reader said no"]

    def broken(messages):
        raise RuntimeError("503")
    assert script.judge("saythis", seed, good(), broken) == []
    assert script.judge("saythis", seed, good(), make_call([{"reply_fits": "yes"}])) == []


def test_judge_prompt_shows_the_fact_or_the_topic_and_hides_the_internal_fields():
    system, user = script.judge_prompt("rights", FACT["wages-2-days"], dict(good(), key=3))
    assert "FACT: Final wages are due within 2 working days" in user and '"key"' not in user and '"payoff"' not in user
    assert "strict editor" in system


def test_write_sends_the_judges_problems_back_to_the_writer_step_by_step():
    seed = {"when": "MANAGER, 9:40 PM", "situation": "your manager asks for an early call tomorrow"}
    better = dict(good(), reply_me="Sure, I can join at ten, does that work for you?")
    seen = []
    verdicts = [{"reply_fits": {"ok": False, "fix": "It ignores the time asked."}}, {}, {"cover_fits": {"ok": False, "fix": "The cover is generic."}}, {}]
    data, report = script.write("saythis", seed, make_call([good(), better, good(), good()], seen), repairs=2, reader=script.llm_reader(make_call(verdicts)))
    assert report["steps"] == {"body": 2, "dress": 2}
    assert report["problems"] == [["reply fits: It ignores the time asked."], [], ["cover fits: The cover is generic."], []]
    assert "It ignores the time asked." in seen[1][-1]["content"] and data["reply_me"] == better["reply_me"]
    assert "The cover is generic." in seen[3][-1]["content"]




def test_a_cover_that_promises_three_lines_needs_three_in_the_reply():
    data = dict(good(), cover_1="The 3-line text to say no to late work")
    assert any("promises 3 lines" in p for p in check("saythis", data, None, hooks.BY_ID[18]))
    data["reply_me"] = "Seen. I will do it tomorrow. I can start at 10. Does that work?"
    assert not any("promises" in p for p in check("saythis", data, None, hooks.BY_ID[18]))


def test_a_step_is_checked_on_its_own_fields_only():
    body_only = {k: v for k, v in good().items() if k in ("boss_text", "reply_me", "why", "key", "when")}
    assert check("saythis", body_only, None, None, None, fields={"boss_text", "reply_me", "why", "key"}) == []
    assert any('"cover_1" is missing' in p for p in check("saythis", body_only))


def test_clef_reader_flags_the_questions_scored_under_the_cut_off_and_survives_a_failure():
    seed = {"when": "MANAGER, 9:40 PM", "situation": "your manager asks for an early call tomorrow"}
    sent = []

    def post(body):
        sent.append(body)
        return {"reply_fits": 0.12, "natural": 0.9, "usable": 0.4, "faithful": 0.39}

    problems = script.clef_reader(post)("saythis", seed, good(), ("reply_fits", "faithful", "natural", "usable"))
    assert [p.split(":")[0] for p in problems] == ["reply fits", "faithful"]          # 0.4 itself is not under the cut-off
    assert "scored this 0.12" in problems[0] and "Could the reader send" not in problems[0] or "Check:" in problems[0]
    body = sent[0]
    assert body["state"]["topic"].startswith("Situation:") and "You reply:" in body["state"]["reel_as_the_viewer_sees_it"]
    assert set(body["questions"]) == {"reply_fits", "faithful", "natural", "usable"} and all(q["type"] == "noul" for q in body["questions"].values())

    def broken(body):
        raise RuntimeError("503")
    assert script.clef_reader(broken)("saythis", seed, good(), ("natural",)) == []
    assert script.clef_reader(post, below=0.05)("saythis", seed, good(), ("reply_fits",)) == []


def test_clef_reader_gives_the_fact_for_a_rights_script():
    sent = []
    script.clef_reader(lambda body: sent.append(body) or {})("rights", FACT["wages-2-days"], good(), ("faithful",))
    assert sent[0]["state"]["topic"].startswith("FACT: Final wages are due within 2 working days")


def test_clef_rank_ideas_orders_by_the_average_and_keeps_order_on_failure():
    ideas = [{"phrase": "a"}, {"phrase": "b"}, {"phrase": "c"}]
    scores = {"a": 0.2, "b": 0.8, "c": 0.5}

    def post(body):
        p = scores[body["state"]["topic"]["phrase"]]
        return {"lived": p, "honest": p, "reply": p}
    assert [i["phrase"] for i in script.clef_rank_ideas(post, "dictionary", ideas)] == ["b", "c", "a"]

    def broken(body):
        raise RuntimeError("503")
    assert script.clef_rank_ideas(broken, "dictionary", ideas) == ideas
