from datetime import datetime, timezone

import pytest

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


def test_reel_card_says_it_is_a_reel():
    one = post(count=1)
    one["reel"] = {"seconds": 10.4, "tune": "warm"}
    assert "Reel, 10.4s, warm tune" in telegram.review_card(one, "0123456789abcdef")


def test_failure_says_what_happened_what_to_do_and_what_silence_does():
    text = telegram.failed("The 08:00 post", "No writing model answered (gemini: 429)", run_url="https://x/y")
    plain = text.split("<blockquote")[0]
    assert "Gemini and Groq (the AIs that write our posts) didn't answer" in plain and "429" not in plain and "<code>retry</code>" in plain
    assert "If you do nothing:" in plain and 'href="https://x/y"' in text and "gemini: 429" in text  # raw, folded


@pytest.mark.parametrize("raw, plain", [
    ("Instagram said HTTP 400: Invalid parameter", "Instagram turned the post down"),
    ("Instagram said HTTP 400: Error validating access token: Session has expired", "The token has expired (a token is the password our code uses to post)"),
    ("An earlier attempt may already be live. Check Instagram before trying again.", "may have posted it already"),
    ("ffmpeg could not make the Reel: moov atom not found", "Reel's video couldn't be made (ffmpeg, the video tool, failed)"),
    ("Slide 1 has too much text to fit.", "too long to fit"),
    ("The preview files never went live on media.suresilly.com.", "didn't finish uploading to media.suresilly.com"),
    ("The review service refused register: 502", "The Worker (the Cloudflare program behind the Telegram approvals)"),
    ("GitHub stopped the run (it ran too long or was cancelled).", "GitHub stopped the run"),
    ("A step stopped before it could say why. The run log has it.", "A GitHub Actions step (the machine that runs our code) broke"),
    ("KeyError: 'slides'", "Something unexpected broke"),
])
def test_every_known_failure_reads_in_plain_words(raw, plain):
    assert plain in telegram.explain(raw)[0]


def test_what_to_do_depends_on_what_failed():
    reply = telegram.failed("Your reply", "Instagram said HTTP 500: oops", kind="reply")
    assert "reply <code>approve</code> to the preview card again" in reply and "stays unposted" in reply
    live = telegram.failed("Your reply", "Instagram gave no post id. It may or may not be live.", kind="reply")
    assert "open Instagram and look first. If it isn't there, reply <code>approve</code> to the preview card" in live
    numbers = telegram.failed("The 3-day numbers check", "", kind="numbers")
    assert "tries again within the hour" in numbers and "<code>retry</code>" not in numbers


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


def test_posted_says_where_threads_went():
    one = post(count=1)
    assert "Also on Threads" in telegram.posted(one, "", {"id": "5", "link": "https://www.threads.com/p"})
    failed = telegram.posted(one, "", {"error": "the Threads token has expired"})
    assert "token has expired" in failed and "Instagram is fine" in failed and "Nothing to reply" in failed
    assert "Threads" not in telegram.posted(one, "")


def test_a_problem_that_blocks_everything_does_not_promise_the_next_post():
    text = telegram.failed("The 20:00 post", "IG_USER_ID or IG_ACCESS_TOKEN is not set. Nothing was posted.")
    assert "send this message to Claude" in text and "every post fails the same way" in text
    assert "the next post is at" not in text
