from datetime import datetime, timezone

from suresilly import telegram


def post(caption="a caption\nsend it to them", count=3):
    return {"format": "list", "topic": "friendship", "caption": caption,
            "slides": [{"text": f"slide [[{n}]] <b>"} for n in range(1, count + 1)]}


def test_card_carries_the_review_id_and_every_reply():
    card = telegram.review_card(post(), "0123456789abcdef")
    assert "Review ID: <code>0123456789abcdef</code>" in card
    for reply in ("approve", "disapprove", "redo all", "redo images 2,4"):
        assert f"<code>{reply}</code>" in card
    assert "Posts itself in 1 hour" in card
    assert "&lt;b&gt;" in card and "[[" not in card


def test_manual_card_says_it_waits():
    card = telegram.review_card(post(), "0123456789abcdef", manual=True)
    assert "won't post on its own" in card and "1 hour" not in card


def test_card_fits_telegram_even_with_a_huge_caption():
    card = telegram.review_card(post(caption="word & " * 2000, count=9), "0123456789abcdef")
    assert len(card) <= telegram.CARD_LIMIT
    assert "Review ID:" in card and "&amp" in card and "&am…" not in card


def test_one_liner_card_has_no_slide_list():
    card = telegram.review_card(post(count=1), "0123456789abcdef")
    assert "📝" not in card and "1 image" in card


def test_failure_says_what_happened_what_to_do_and_what_silence_does():
    text = telegram.failed("The 08:00 post", "Gemini was busy", run_url="https://x/y")
    assert "Gemini was busy" in text and "<code>retry</code>" in text
    assert "If you do nothing" in text and 'href="https://x/y"' in text


def test_next_slot():
    ist_morning = datetime(2026, 9, 11, 1, 0, tzinfo=timezone.utc)   # 06:30 IST
    ist_noon = datetime(2026, 9, 11, 6, 30, tzinfo=timezone.utc)     # 12:00 IST
    ist_night = datetime(2026, 9, 11, 16, 0, tzinfo=timezone.utc)    # 21:30 IST
    assert telegram.next_slot(ist_morning) == "08:00 IST today"
    assert telegram.next_slot(ist_noon) == "20:00 IST today"
    assert telegram.next_slot(ist_night) == "08:00 IST tomorrow"


def test_posted_and_dropped_messages():
    assert "Open it on Instagram" in telegram.posted(post(), "https://www.instagram.com/p/x/")
    assert "Nothing was posted" in telegram.dropped(post())


def test_plain_card_fits_an_older_worker():
    long = post(caption="x" * 5000, count=9)
    long["slides"][0]["text"] = "a very long hook " * 40
    card = telegram.plain_card(long, "0123456789abcdef")
    assert len(card) <= 1000 and "Review ID: 0123456789abcdef" in card and "<" not in card
    assert len(telegram.plain_details(long)) <= 2900


def test_why_cards_cover_every_area_and_cause_and_say_what_silence_does():
    from suresilly import telegram
    post = {"slides": [{"text": "a line"}]}
    text, buttons = telegram.why_card(post, "0123456789abcdef")
    data = [d for row in buttons for _, d in row]
    assert data == [f"why:0123456789abcdef:{area}" for area in telegram.AREAS]
    assert "Review ID: 0123456789abcdef" in text and "stay quiet" in text and "why:" in text
    for area, (_, causes) in telegram.AREAS.items():
        if not causes:
            continue
        _, rows = telegram.why_detail_card(area, "0123456789abcdef")
        codes = [d for row in rows for _, d in row]
        assert codes == [f"why:0123456789abcdef:{area}.{c}" for c in causes] + [f"why:0123456789abcdef:{area}.unsure"]
        assert all(len(d.encode()) <= 64 for d in codes)
        assert all(f"{area}.{c}" in telegram.INSTRUCTIONS for c in causes) and area in telegram.INSTRUCTIONS


def test_noted_escalates_at_two_and_three():
    from suresilly import telegram
    assert "first time" in telegram.noted("preachy or advice-y", 1, "h") and "strike list" not in telegram.noted("x", 1, "h")
    assert "strike list" in telegram.noted("x", 2, "h")
    assert "banned word" in telegram.noted("x", 3, "h")


def test_which_slide_card_offers_each_slide_and_all():
    from suresilly import telegram
    text, rows = telegram.which_slide_card({"slides": [{"text": "a"}] * 7}, "0123456789abcdef")
    data = [d for row in rows for _, d in row]
    assert data == [f"why:0123456789abcdef:slide{n}" for n in range(1, 8)] + ["why:0123456789abcdef:all"]
    assert "Skip it" in text and telegram.slide_noted("3") == "👍 Got it: slide 3."
