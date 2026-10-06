from datetime import datetime, timezone

from suresilly import factcheck as F

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)
PAGE = ("# Wage ceiling\n\nThe Employees' Provident Fund wage ceiling is raised to Rs 25,000 a month with effect from 1 October, "
        "and employers must pay contributions on it. Other text follows that says nothing relevant to this topic at all.")
QUOTE = "The Employees' Provident Fund wage ceiling is raised to Rs 25,000 a month with effect from 1 October"


def entry(**k):
    return {"slot": 1, "type": "news", "title": "EPFO wage ceiling raised", "link": "https://www.epfindia.gov.in/x", "angle": "what it changes for pay",
            "fact_check": False, **k}


def model(claims):
    """One fake model for both steps: it reads the page when asked for claims, and says yes to every quote when asked to check them."""
    def call(messages):
        if "check whether quotes" in messages[0]["content"]:
            count = messages[1]["content"].count("\n") - 2
            return {"results": [{"i": n, "supports": True} for n in range(max(count, 1) + 5)]}
        return {"claims": claims}
    return call


def test_a_quote_that_is_in_the_page_is_kept_and_one_that_is_not_is_thrown_away():
    claims = [{"quote": QUOTE, "says": "The ceiling is now Rs 25,000 a month."},
              {"quote": "The ceiling is raised to Rs 30,000 a month with immediate effect for all employers in India", "says": "invented"}]
    got = F.verified_claims(entry(), PAGE, model(claims))
    assert [c["says"] for c in got] == ["The ceiling is now Rs 25,000 a month."]


def test_markup_spacing_and_curly_quotes_do_not_count_as_a_difference():
    page = "**The Employees’ Provident Fund** wage ceiling is\n raised to Rs 25,000 a month with effect from 1 October."
    assert F.verified_claims(entry(), page, model([{"quote": QUOTE, "says": "ok"}]))


def test_too_short_or_too_long_quotes_and_a_missing_meaning_are_rejected():
    assert F.verified_claims(entry(), PAGE, model([{"quote": "wage ceiling is raised", "says": "x"}])) == []
    assert F.verified_claims(entry(), PAGE, model([{"quote": QUOTE, "says": ""}])) == []


def test_a_failed_or_garbled_model_call_gives_no_claims_never_a_guess():
    def down(messages):
        raise RuntimeError("timed out")
    assert F.verified_claims(entry(), PAGE, down) == []
    assert F.verified_claims(entry(), PAGE, lambda m: {"_bad_json": "x"}) == []


def test_the_prompt_forbids_advice_and_carries_no_sample():
    system, user = F.claims_prompt(entry(), PAGE)
    assert "give no advice" in system and "word for word" in system and "for example" not in system.lower() and "e.g." not in system
    assert user.startswith("Topic: EPFO wage ceiling raised.")


def test_an_item_already_from_an_official_site_is_grounded_in_its_own_page():
    got = F.ground(entry(), lambda q, d: [], lambda url: PAGE, model([{"quote": QUOTE, "says": "Ceiling now Rs 25,000."}]), ["epfindia.gov.in"], NOW)
    assert got["status"] == "verified" and got["source"]["official"] and got["source"]["site"] == "epfindia.gov.in" and got["checked_at"] == "2026-10-06"


def test_an_item_from_a_news_site_is_grounded_by_an_official_search_and_the_next_page_is_tried():
    pages = {"https://a.gov.in/1": "Nothing useful here at all, just a menu and some links to other places.", "https://b.gov.in/2": PAGE}
    find = lambda q, d: [{"url": "https://a.gov.in/1", "title": "A"}, {"url": "https://b.gov.in/2", "title": "B"}]
    calls = []

    def call(messages):
        calls.append(1)
        return {"claims": [{"quote": QUOTE, "says": "ok"}]}

    got = F.ground(entry(fact_check=True), find, lambda url: pages[url], call, ["gov.in"], NOW, check=lambda m: {"results": [{"i": 0, "supports": True}]})
    assert got["status"] == "verified" and got["source"]["url"] == "https://b.gov.in/2" and got["tried"] == ["https://a.gov.in/1", "https://b.gov.in/2"]


def test_no_official_page_gives_a_plain_reason():
    assert F.ground(entry(fact_check=True), lambda q, d: [], lambda u: "", model([]), ["gov.in"], NOW)["status"] == "no_source"
    unreadable = F.ground(entry(fact_check=True), lambda q, d: [{"url": "https://a.gov.in", "title": ""}], lambda u: (_ for _ in ()).throw(RuntimeError()), model([]), ["gov.in"], NOW)
    assert unreadable["status"] == "no_claims"


def test_a_search_that_fails_is_reported_not_raised():
    def broken(q, d):
        raise RuntimeError("credits used")
    got = F.ground(entry(fact_check=True), broken, lambda u: "", model([]), ["gov.in"], NOW)
    assert got["status"] == "no_search" and "credits used" in got["why"]


def test_a_lesson_is_grounded_in_its_own_text_without_fetching():
    lesson = {"link": "https://doi.org/1", "title": "Study", "text": PAGE}
    got = F.ground(entry(type="mirror", lesson=lesson), lambda q, d: [], lambda u: (_ for _ in ()).throw(AssertionError("fetched")), model([{"quote": QUOTE, "says": "ok"}]), [], NOW)
    assert got["status"] == "verified" and got["source"]["official"] is False


def test_the_fact_has_the_shape_the_script_writer_checks_numbers_against():
    got = F.ground(entry(), lambda q, d: [], lambda url: PAGE, model([{"quote": QUOTE, "says": "Ceiling now Rs 25,000."}]), [], NOW)
    fact = F.to_fact(entry(), got)
    assert fact["claim"] == "Ceiling now Rs 25,000." and fact["law"] == QUOTE and fact["status"] == "checked" and fact["source_date"] == "2026-10-06"


def test_a_story_is_grounded_in_its_own_article_and_called_reported_not_official():
    got = F.ground(entry(type="story"), lambda q, d: [], lambda u: PAGE, model([{"quote": QUOTE, "says": "ok"}]), [], NOW)
    assert got["status"] == "verified" and got["source"]["official"] is False and F.to_fact(entry(type="story"), got)["status"] == "reported"


def test_a_reddit_story_rests_on_the_preview_text_because_the_post_has_no_link():
    e = entry(type="story", link="https://www.reddit.com/r/IndianWorkplace/new/", blurb=PAGE)
    got = F.ground(e, lambda q, d: [], lambda u: (_ for _ in ()).throw(AssertionError("fetched")), model([{"quote": QUOTE, "says": "ok"}]), [], NOW)
    assert got["status"] == "verified"


def test_a_week_skips_what_cannot_be_grounded_and_falls_back_to_another_type_when_it_can():
    plans = [entry(slot=1, type="news", fact_check=True, alternatives=["story"]), entry(slot=2, type="news", fact_check=True)]
    pages = {"https://a.gov.in/1": "Nothing useful here at all, only a menu and some links to other places.", entry()["link"]: PAGE}
    find = lambda q, d: [{"url": "https://a.gov.in/1", "title": "A"}]
    out = F.check_week(plans, find, lambda u: pages[u], model([{"quote": QUOTE, "says": "ok"}]), ["gov.in"], check=lambda m: {"results": [{"i": 0, "supports": True}]})
    assert out[0]["type"] == "story" and out[0]["fell_back_from"] == "news" and out[0]["ground"]["status"] == "verified" and "skip" not in out[0]
    assert "skip" in out[1] and out[1]["ground"]["status"] == "no_claims"


def test_a_true_quote_that_does_not_support_the_reel_is_dropped_by_the_second_model():
    claims = [{"quote": QUOTE, "says": "Ceiling now Rs 25,000."}]
    read = lambda messages: {"claims": claims}
    no = lambda messages: {"results": [{"i": 0, "supports": False}]}
    assert F.verified_claims(entry(), PAGE, read, no) == []
    yes = lambda messages: {"results": [{"i": 0, "supports": True}]}
    assert len(F.verified_claims(entry(), PAGE, read, yes)) == 1


def test_if_the_second_model_fails_or_garbles_nothing_is_kept():
    claims = [{"quote": QUOTE, "says": "ok"}]
    read = lambda messages: {"claims": claims}

    def down(messages):
        raise RuntimeError("slow")
    assert F.verified_claims(entry(), PAGE, read, down) == []
    assert F.verified_claims(entry(), PAGE, read, lambda m: {"results": [{"i": 0, "supports": "yes"}]}) == []     # only a real true counts


def test_the_support_prompt_names_what_the_reel_would_say_and_has_no_sample():
    system, user = F.support_prompt(entry(), [{"quote": QUOTE, "says": "x"}])
    assert "It would say: what it changes for pay" in user and "0. " + QUOTE in user and "for example" not in system.lower()


def test_a_lesson_with_no_checkable_source_becomes_our_own_reasoning_not_a_skip():
    lesson = {"link": "https://doi.org/1", "title": "Study", "text": "A page with nothing that matches anything the Reel needs, only some other words here."}
    got = F.ground(entry(type="mirror", lesson=lesson), lambda q, d: [], lambda u: "", model([]), [], NOW)
    assert got["status"] == "reasoned" and "names no source" in got["why"]
    none = F.ground(entry(type="contrast"), lambda q, d: [], lambda u: "", model([]), [], NOW)
    assert none["status"] == "reasoned"                                                  # no lesson at all: still allowed, as reasoning


def test_a_rule_or_news_reel_is_never_allowed_to_rest_on_reasoning():
    for kind in ("can_they", "news"):
        assert F.ground(entry(type=kind, fact_check=True), lambda q, d: [], lambda u: "", model([]), ["gov.in"], NOW)["status"] == "no_source"


def test_a_story_is_supported_by_what_happened_not_by_the_takeaway():
    system, user = F.support_prompt(entry(type="story"), [{"quote": QUOTE, "says": "x"}])
    assert "retells this event: EPFO wage ceiling raised" in user and "what the Reel would say" not in user and "It would say" not in user
    system, user = F.support_prompt(entry(type="news"), [{"quote": QUOTE, "says": "x"}])
    assert "It would say: what it changes for pay" in user


def test_a_reasoned_reel_is_not_skipped_and_a_fallback_stops_at_it():
    plans = [entry(slot=1, type="mirror", alternatives=["story"])]
    out = F.check_week(plans, lambda q, d: [], lambda u: "", model([]), [])
    assert out[0]["type"] == "mirror" and out[0]["ground"]["status"] == "reasoned" and "skip" not in out[0]


def test_a_reddit_question_with_no_event_in_it_becomes_reasoning_not_a_skip():
    e = entry(type="story", link="https://www.reddit.com/r/IndianWorkplace/new/", blurb="Which offer should I take as a fresher? I cannot decide between two options.")
    got = F.ground(e, lambda q, d: [], lambda u: "", model([]), [], NOW)
    assert got["status"] == "reasoned"
    news = entry(type="story", link="https://news.test/a")
    assert F.ground(news, lambda q, d: [], lambda u: "", model([]), [], NOW)["status"] == "no_claims"      # a news story with no report of it is still a skip
