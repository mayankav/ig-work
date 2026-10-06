import json

from suresilly import telegram, weekly


def item(n, kind="story", source="HR Katha"):
    return {"title": f"Manager story number {n} about a pulled leave", "source": source, "story_kind": kind, "score": 9, "angle": "what to do",
            "link": f"https://x.test/{n}", "published": "2026-10-04T10:00:00+00:00"}


def report(kept=14, failed=None, below=None, gave_up=None):
    return {"mode": "full", "collected": 1094, "first_cut": 61, "kept": kept, "stock": [item(n) for n in range(kept)],
            "below_cut": below if below is not None else [item(99)], "failed_feeds": failed or {}, "gave_up": gave_up or [],
            "per_source": {"HR Katha": 40, "r/IndianWorkplace": 25}, "at": "2026-10-05T18:00:00+00:00"}


def test_a_redo_button_shows_only_when_it_can_help():
    labels = lambda r: [label for label, _ in weekly.actions(r)]
    assert labels(report()) == ["Use my picks", "Show below the cut"]                     # enough items, nothing failed: no redo
    assert "Retry the failed source" in labels(report(failed={"r/X": "gemini: HTTP 429"}))
    assert "Look wider" in labels(report(kept=9))
    assert "Look wider" not in labels(report(kept=14))
    assert "Show below the cut" not in labels(report(below=[]))


def test_every_action_is_a_stock_callback():
    assert all(data.startswith("stock:") for _, data in weekly.actions(report(kept=3, failed={"a": "x"})))


def test_the_card_says_what_happened_what_to_tap_and_what_happens_if_quiet():
    text, rows = weekly.card(report(), page_url="https://media.suresilly.com/stock/2026-10-05/")
    assert "Weekly stock: 14 ready for 14 slots" in text and "Read 1094 items" in text       # what happened
    assert "Tap a button" in text and "If you stay quiet, I use my picks from Monday 08:00 IST" in text
    assert rows[0] == [("Open full list", "https://media.suresilly.com/stock/2026-10-05/")]
    assert len(text) < telegram.CARD_LIMIT and text.count("\n1. ") == 1 and "6. " not in text   # five items when a page holds the rest


def test_the_card_names_a_failed_source_and_whether_it_will_retry():
    text, _ = weekly.card(report(failed={"r/developersIndia": "gemini: HTTP 429"}, gave_up=[]))
    assert "Failed: r/developersIndia (retry tomorrow)" in text
    text, _ = weekly.card(report(failed={"r/developersIndia": "x"}, gave_up=["r/developersIndia"]))
    assert "(gave up)" in text


def test_an_empty_week_is_said_plainly():
    text, rows = weekly.card(report(kept=0, below=[]))
    assert "Nothing passed the cut this week." in text and "slots wait for new items" in text
    assert [label for row in rows for label, _ in row] == ["Use my picks", "Look wider"]


def test_titles_are_escaped_for_telegram_html():
    r = report(kept=1)
    r["stock"][0]["title"] = "A <b>boss</b> & his rules"
    text, _ = weekly.card(r)
    assert "&lt;b&gt;boss&lt;/b&gt; &amp; his rules" in text


def test_a_url_button_is_sent_as_a_link_and_the_rest_as_callbacks(monkeypatch):
    sent = {}
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(telegram.requests, "post", lambda url, **k: sent.update(k["json"]) or type("R", (), {"status_code": 200, "json": lambda self: {"ok": True}})())
    telegram.send("x", [[("Open full list", "https://media.suresilly.com/stock/")], [("Use my picks", "stock:picks")]])
    keyboard = sent["reply_markup"]["inline_keyboard"]
    assert keyboard[0][0] == {"text": "Open full list", "url": "https://media.suresilly.com/stock/"}
    assert keyboard[1][0] == {"text": "Use my picks", "callback_data": "stock:picks"}


def test_the_page_carries_the_data_and_cannot_be_broken_by_a_title(tmp_path):
    r = report(kept=2)
    r["stock"][0]["title"] = "</script><script>alert(1)</script>"
    html = weekly.page(r)
    assert "</script><script>alert(1)" not in html and "Read-only" in html
    data = json.loads(html.split('type="application/json">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert data["kept"][0]["title"].startswith("</script>") and data["collected"] == 1094
    weekly.write_page(r, tmp_path / "w")
    assert (tmp_path / "w" / "index.html").exists() and json.loads((tmp_path / "w" / "stock.json").read_text())["kept"] == 2


def test_search_domains_are_not_counted_as_sources(monkeypatch):
    monkeypatch.setattr(weekly.inbox, "SOURCES", {"feeds": [{"name": "HR Katha"}], "pages": [{"name": "r/IndianWorkplace"}], "searches": [{"name": "S"}]})
    r = report()
    r["per_source"] = {"HR Katha": 40, "r/IndianWorkplace": 25, "tribuneindia.com": 3, "ndtv.com": 1}
    text, _ = weekly.card(r)
    assert "3 of 3 sources answered, plus 2 more sites found by search" in text
    r["failed_feeds"] = {"S": "no key"}
    assert "2 of 3 sources answered" in weekly.card(r)[0]
