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
