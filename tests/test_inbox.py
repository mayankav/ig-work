import json
from datetime import datetime, timedelta, timezone

import pytest

from suresilly import inbox

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate><description>{b}</description></item>" for t, l, d, b in items)
    return f"<rss><channel>{body}</channel></rss>".encode()


class Reply:
    def __init__(self, content, status=200):
        self.content, self.status = content, status

    def raise_for_status(self):
        if self.status != 200:
            raise RuntimeError(self.status)


def day(n):
    return (NOW - timedelta(days=n)).strftime("%a, %d %b %Y %H:%M:%S +0000")


def item(title, link, n=1, source="A"):
    return {"id": link, "source": source, "kind": "news", "title": title, "link": link,
            "published": (NOW - timedelta(days=n)).isoformat(), "blurb": ""}


def test_fetch_feed_reads_rss_and_atom():
    feed = {"name": "A", "url": "http://x", "kind": "news"}
    items = inbox.fetch_feed(feed, lambda *a, **k: Reply(rss(("Boss calls at 11 pm", "http://a/1", day(1), "<p>He did</p>"))))
    assert items[0]["title"] == "Boss calls at 11 pm" and items[0]["blurb"] == "He did" and items[0]["published"]
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title><link href="http://a/2"/><updated>2026-10-05T00:00:00Z</updated></entry></feed>'
    assert inbox.fetch_feed(feed, lambda *a, **k: Reply(atom))[0]["link"] == "http://a/2"


def test_a_dead_feed_is_reported_and_the_rest_go_on(monkeypatch):
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [{"name": "Dead", "url": "d"}, {"name": "Live", "url": "l"}]})

    def get(url, **k):
        return Reply(b"", 404) if url == "d" else Reply(rss(("Leave denied", "http://a/1", day(1), "")))

    items, failed = inbox.collect(get)
    assert len(items) == 1 and failed == {"Dead": "RuntimeError"}


def test_fresh_drops_old_and_already_seen_and_repeats_in_one_pull():
    state = {"seen": {"http://a/seen": "x"}}
    got = inbox.fresh([item("a", "http://a/seen"), item("b", "http://a/old", n=30), item("c", "http://a/new"), item("c", "http://a/new")], state, NOW)
    assert [i["id"] for i in got] == ["http://a/new"]


def test_the_same_story_from_two_sites_becomes_one_item():
    a = item("Manager revokes approved leave as employee waits at airport", "http://a/1", n=2, source="A")
    b = item("Manager revokes approved leave while employee waits at airport", "http://b/1", n=1, source="B")
    other = item("New labour code overtime rules explained", "http://c/1", source="C")
    merged = inbox.merge_duplicates([b, a, other])
    assert len(merged) == 2 and merged[0]["source"] == "A" and merged[0]["also"] == ["B"]


def test_rate_scores_by_index_and_drops_what_the_model_skips():
    items = [item("one", "1"), item("two", "2"), item("three", "3")]
    answer = {"items": [{"i": 0, "score": 9, "kind": "story", "angle": "boss crosses a line"}, {"i": 2, "score": "x", "kind": "weird"}]}
    rated = inbox.rate(items, lambda messages: answer)
    assert [(r["score"], r["story_kind"]) for r in rated] == [(9, "story"), (0, "other"), (0, "other")]


def test_rate_survives_a_garbled_answer():
    rated = inbox.rate([item("one", "1")], lambda messages: {"_bad_json": "oops"})
    assert rated[0]["score"] == 0


def test_prompt_has_no_sample_item():
    system, user = inbox.rate_prompt([item("T", "1")])
    assert "Items:\n0. [A] T" in user and "for example" not in system.lower() and "e.g." not in system
    assert not any(w in system.lower() for w in ("sport", "politics", "celebrit", "layoff", "manager", "boss"))   # no topic list: any item may be used


def test_run_keeps_the_best_and_never_offers_an_item_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [{"name": "A", "url": "u"}]})
    get = lambda *a, **k: Reply(rss(("Boss refuses sick leave", "http://a/1", day(1), ""), ("Sensex rises", "http://a/2", day(1), "")))

    def call(messages):
        titles = messages[1]["content"].splitlines()[1:]
        return {"items": [{"i": n, "score": 9 if "leave" in line else 1, "kind": "story", "angle": "w"} for n, line in enumerate(titles)]}

    first = inbox.run(call, NOW, get)
    assert first["collected"] == 2 and first["kept"] == 1 and first["stock"][0]["link"] == "http://a/1"
    second = inbox.run(call, NOW + timedelta(days=7), get)
    assert second["new"] == 0 and second["kept"] == 0
    assert json.loads((tmp_path / "inbox.json").read_text())["seen"]


def test_a_failed_source_is_retried_the_next_day_then_given_up(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [{"name": "A", "url": "a"}, {"name": "Reddit", "url": "r"}]})
    down = {"on": True}

    def get(url, **k):
        if url == "r" and down["on"]:
            return Reply(b"", 403)
        return Reply(rss((f"Boss story {url}", f"http://x/{url}", day(1), "")))

    call = lambda messages: {"items": [{"i": n, "score": 9, "kind": "story", "angle": "w"} for n in range(5)]}
    first = inbox.run(call, NOW, get)
    assert first["mode"] == "full" and first["failed_feeds"] == {"Reddit": "RuntimeError"}
    assert inbox.run(call, NOW + timedelta(hours=3), get)["mode"] == "skip"           # too soon
    second = inbox.run(call, NOW + timedelta(days=1), get)                              # next day: only the failed one
    assert second["mode"] == "retry" and second["failed_feeds"] == {"Reddit": "RuntimeError"} and second["collected"] == 0
    down["on"] = False
    third = inbox.run(call, NOW + timedelta(days=2), get)
    assert third["mode"] == "retry" and third["collected"] == 1 and third["failed_feeds"] == {}
    assert "Reddit" not in inbox.load_state()["retry"]


def test_after_four_failures_the_owner_is_told(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [{"name": "Reddit", "url": "r"}]})
    get = lambda url, **k: Reply(b"", 403)
    call = lambda messages: {"items": []}
    reports = [inbox.run(call, NOW + timedelta(days=n), get) for n in range(5)]
    assert [r["gave_up"] for r in reports[:3]] == [[], [], []] and reports[3]["gave_up"] == ["Reddit"]
    assert reports[4]["mode"] == "skip"                                                 # it rests until the next full run


def test_a_listing_page_becomes_items_with_a_date_from_its_age():
    page = {"name": "r/X", "url": "http://r/x/new/", "kind": "post"}
    text = 'ok {"posts": [{"title": "Leave refused", "preview": "He said no", "age": "3h ago"}, {"title": "not shown", "preview": "x", "age": ""}]}'
    items = inbox.fetch_page(page, lambda url, instruction: text, NOW)
    assert len(items) == 1 and items[0]["title"] == "Leave refused" and items[0]["blurb"] == "He said no"
    assert datetime.fromisoformat(items[0]["published"]) == NOW - timedelta(hours=3)


def test_the_reader_hands_over_when_a_models_pool_is_spent():
    calls = []

    def post(url, **k):
        calls.append(url.split("models/")[1].split(":")[0])
        ok = len(calls) == 2
        return type("R", (), {"status_code": 200 if ok else 429, "json": lambda self: {"candidates": [{"content": {"parts": [{"text": "page"}]}}]}})()

    assert inbox.gemini_reader("k", ("a", "b", "c"), post)("http://x", "do") == "page" and calls == ["a", "b"]


def test_a_page_source_without_a_reader_counts_as_failed_and_is_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [], "pages": [{"name": "r/X", "url": "u"}]})
    report = inbox.run(lambda m: {"items": []}, NOW, read=None)
    assert report["failed_feeds"] == {"r/X": "gemini: RuntimeError"} and "r/X" in inbox.load_state()["retry"]


def test_a_batch_whose_calls_fail_is_marked_unrated_not_fatal():
    calls = []

    def call(messages):
        calls.append(1)
        raise RuntimeError("timed out")

    rated = inbox.rate([item("one", "1")], call)
    assert len(calls) == 2 and rated[0]["unrated"] and rated[0]["score"] == 0


def test_a_retry_after_one_failure_succeeds():
    state = {"n": 0}

    def call(messages):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("slow")
        return {"items": [{"i": 0, "score": 8, "kind": "rule", "angle": "a"}]}

    rated = inbox.rate([item("one", "1")], call)
    assert rated[0]["score"] == 8 and "unrated" not in rated[0]


def test_a_news_section_page_read_by_jina_gives_article_links_only():
    md = ("[Home](https://www.site.com/) ![Image 1: Logo](https://www.site.com/logo.svg)\n"
          "[Manager asks employee to log in at midnight, staff reply goes viral online ![Image 5: x](https://i/x.jpg)](https://www.site.com/trending/viral-story-1)\n"
          "[Manager asks employee to log in at midnight, staff reply goes viral online](https://www.site.com/trending/viral-story-1)\n"
          "[New labour code rules on overtime explained for private sector employees](https://www.site.com/news/labour-code)\n"
          "[Share on another site this long text should not count](https://other.com/a/b)\n"
          "[* ![Image 7: alt text](https://i/y.jpg) Gen Z employee refuses weekend call and manager responds in an email](https://www.site.com/trending/third)\n"
          "## [Leave policy changes at big IT firms ### Staff must now give notice 3 m read ![Image 9: pic](https://i/z.jpg)](https://www.site.com/news/fourth)\n"
          "[Latest](https://www.site.com/trending/)")
    page = {"name": "Site", "url": "https://www.site.com/trending/", "kind": "news", "readers": ["jina"]}
    items = inbox.fetch_links(page, lambda url, **k: type("R", (), {"text": md, "raise_for_status": lambda self: None})())
    assert url_ok(items) and [i["link"] for i in items] == ["https://www.site.com/trending/viral-story-1", "https://www.site.com/news/labour-code", "https://www.site.com/trending/third", "https://www.site.com/news/fourth"]
    assert items[0]["title"].startswith("Manager asks employee") and items[0]["published"] == ""
    assert items[2]["title"] == "Gen Z employee refuses weekend call and manager responds in an email"
    assert items[3]["title"] == "Leave policy changes at big IT firms - Staff must now give notice 3 m read"


def url_ok(items):
    return all(i["id"] and i["source"] == "Site" for i in items)


def test_the_ladder_goes_down_until_a_rung_returns_items():
    page = {"name": "r/X", "url": "u", "readers": ["jina", "gemini", "tavily"]}
    tried = []

    def get(url, **k):
        tried.append("jina")
        raise RuntimeError("403")

    def read(url, instruction):
        tried.append("gemini")
        return "no json here"                        # an empty answer counts as a failed rung

    def tavily(page, now):
        tried.append("tavily")
        return [item("A story about leave", "http://t/1")]

    assert inbox.read_page(page, get, read, NOW, tavily)[0]["title"] == "A story about leave" and tried == ["jina", "gemini", "tavily"]


def test_when_every_rung_fails_the_error_names_each_one():
    page = {"name": "r/X", "url": "u", "readers": ["jina", "tavily"]}

    def get(url, **k):
        raise RuntimeError("403")

    with pytest.raises(RuntimeError, match=r"jina: RuntimeError; tavily: RuntimeError"):
        inbox.read_page(page, get, None, NOW, None)


class Posted:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)


def test_a_search_gives_dated_items_from_every_site():
    data = {"results": [{"title": "Quiet quitting rises among young Indians", "url": "https://www.brut.media/a", "published_date": "Thu, 01 Oct 2026 12:00:00 GMT", "content": "A survey..."},
                        {"title": "", "url": "https://x/y"}]}
    got = inbox.fetch_search({"name": "S", "query": "q"}, "k", NOW, lambda url, **k: Posted(data))
    assert len(got) == 1 and got[0]["source"] == "brut.media" and got[0]["published"].startswith("2026-10-01") and got[0]["blurb"] == "A survey..."


def test_the_search_asks_for_the_week_and_sends_the_key_in_the_header_only():
    seen = {}

    def post(url, **k):
        seen.update(url=url, **k)
        return Posted({"results": []})

    inbox.fetch_search({"name": "S", "query": "q", "max_results": 7}, "SECRET", NOW, post)
    assert seen["url"].endswith("/search") and seen["json"]["time_range"] == "week" and seen["json"]["max_results"] == 7
    assert "SECRET" not in json.dumps(seen["json"]) and seen["headers"]["Authorization"] == "Bearer SECRET"


def test_tavily_extract_rung_parses_links_and_fails_when_nothing_comes_back():
    page = {"name": "P", "url": "https://www.site.com/trending/", "kind": "news"}
    md = "[Manager sends a message at midnight and employees reply on the group](https://www.site.com/trending/a)"
    rung = inbox.tavily_extract("k", lambda url, **k: Posted({"results": [{"raw_content": md}]}))
    assert rung(page, NOW)[0]["link"] == "https://www.site.com/trending/a"
    with pytest.raises(RuntimeError, match="failed to fetch"):
        inbox.tavily_extract("k", lambda url, **k: Posted({"results": [], "failed_results": [{}]}))(page, NOW)


def test_run_reads_the_searches_and_a_missing_key_counts_as_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"feeds": [], "searches": [{"name": "S", "query": "q"}]})
    call = lambda m: {"items": [{"i": 0, "score": 9, "kind": "event", "angle": "a"}]}
    none = inbox.run(call, NOW)
    assert none["failed_feeds"] == {"S": "no key"}
    ok = inbox.run(call, NOW + timedelta(days=1), search=lambda source, now: [item("Staff react to new overtime rule", "http://n/1")])
    assert ok["mode"] == "retry" and ok["kept"] == 1


def test_tavily_stops_before_the_free_credits_run_out():
    calls = []
    post = lambda url, **k: calls.append(url) or Posted({"results": [{"title": "Staff react to a new rule", "url": "https://a.com/x"}]})
    usage = lambda used: (lambda url, **k: Posted({"account": {"plan_usage": used, "plan_limit": 1000}}))
    search, rung = inbox.tavily_tools("k", post, usage(100))
    assert search({"name": "S", "query": "q"}, NOW)[0]["link"] == "https://a.com/x"
    search, rung = inbox.tavily_tools("k", post, usage(800))
    with pytest.raises(RuntimeError, match="800 of 1000"):
        search({"name": "S", "query": "q"}, NOW)
    with pytest.raises(RuntimeError, match="800 of 1000"):
        rung({"name": "P", "url": "https://a.com/"}, NOW)
    assert len(calls) == 1


def test_openalex_gives_papers_with_a_link_and_a_date():
    data = {"results": [{"title": "Daily abusive supervision and next-day wellbeing", "publication_date": "2023-05-01", "doi": "https://doi.org/10.1/x",
                         "cited_by_count": 6, "open_access": {"oa_url": "https://oa/x"}}, {"title": "No link", "doi": None, "open_access": {}}]}
    got = inbox.fetch_openalex({"name": "O", "query": "q", "from_year": 2020}, lambda url, **k: type("R", (), {"json": lambda self: data, "raise_for_status": lambda self: None})())
    assert len(got) == 1 and got[0]["link"] == "https://doi.org/10.1/x" and got[0]["kind"] == "research" and got[0]["blurb"] == "6 citations"


def test_a_search_can_be_limited_to_approved_domains_and_a_general_topic_has_no_week():
    seen = {}
    inbox.fetch_search({"name": "S", "query": "q", "topic": "general", "include_domains": ["gallup.com"], "kind": "research"}, "k", NOW,
                       lambda url, **k: seen.update(k["json"]) or Posted({"results": []}))
    assert seen["include_domains"] == ["gallup.com"] and "time_range" not in seen and seen["topic"] == "general"


def test_the_lesson_prompt_is_about_managers_and_has_no_sample():
    system, _ = inbox.rate_prompt([item("t", "1")], lesson=True)
    assert "what professional management looks like" in system and "for example" not in system.lower() and "e.g." not in system


def test_principles_job_builds_a_library_that_keeps_old_lessons_and_never_repeats_one(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "STATE_FILE", tmp_path / "inbox.json")
    monkeypatch.setattr(inbox, "SOURCES", {"principles": {"feeds": [{"name": "B", "url": "u", "kind": "opinion"}]}})
    old = "Mon, 01 Jan 2024 10:00:00 +0000"
    get = lambda url, **k: Reply(rss(("A manager who explains why earns trust from the team", "http://b/1", old, "")))
    call = lambda m: {"items": [{"i": 0, "score": 8, "kind": "opinion", "angle": "explain the why"}]}
    first = inbox.run_principles(call, NOW, get)
    assert first["added"] == 1 and first["library"] == 1                       # an old post still counts: a lesson does not go stale
    second = inbox.run_principles(call, NOW + timedelta(days=7), get)
    assert second["new"] == 0 and second["library"] == 1
