import json

import pytest

from suresilly import instagram, review, run


def make_post(folder, count=2):
    (folder / "slides").mkdir(parents=True)
    for n in range(1, count + 1):
        (folder / "slides" / f"{n:02d}.jpg").write_bytes(f"slide {n}".encode())
    (folder / "contact_sheet.png").write_bytes(b"sheet")
    (folder / "caption.txt").write_text("caption\n")
    slides = [{"text": f"line {n}", "mood": "calm", "pose": "sitting"} for n in range(1, count + 1)]
    (folder / "post.json").write_text(json.dumps({"format": "list", "topic": "love", "slides": slides}))
    return folder


def test_prepare_then_read_round_trip(tmp_path):
    post = make_post(tmp_path / "20260911_0800_x")
    record = review.prepare(post)
    assert review.read(post) == record
    assert review.slide_urls(record) == [
        f"https://media.suresilly.com/slides/20260911_0800_x/reviews/{record['token']}/slides/0{n}.jpg" for n in (1, 2)]


def test_read_refuses_a_changed_post(tmp_path):
    post = make_post(tmp_path / "p")
    review.prepare(post)
    (post / "slides" / "01.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        review.read(post)


def test_prepare_refuses_a_published_post(tmp_path):
    post = make_post(tmp_path / "p")
    (post / "published.json").write_text("{}")
    with pytest.raises(ValueError, match="already on Instagram"):
        review.prepare(post)


def test_api_refuses_a_bad_token():
    with pytest.raises(ValueError):
        review.api("not-a-token", "status")


def test_format_rotation():
    assert run.format_for("2026-09-11_2000") == "oneliner"
    mornings = {run.format_for("2026-09-11_0800"), run.format_for("2026-09-12_0800")}
    assert mornings == {"list", "story"}
    assert run.format_for("") == "list"


def test_slugify():
    assert run.slugify("[[things]] that feel like home, even far away") == "things-that-feel-like-home-even"


def test_prune_removes_only_old_dated_folders(tmp_path):
    for name in ("20200101_0800_old", "29990101_0800_new", "CNAME-folder"):
        (tmp_path / name).mkdir()
    run.prune(tmp_path, 14)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["29990101_0800_new", "CNAME-folder"]


def test_redraw_changes_only_the_named_poses(tmp_path, monkeypatch):
    post = make_post(tmp_path / "p", count=3)
    monkeypatch.setattr(run, "draw", lambda data, folder: (folder / "post.json").write_text(json.dumps(data)))
    run.redraw(post, [2, 9])
    after = json.loads((post / "post.json").read_text())["slides"]
    assert [s["pose"] for s in after][0::2] == ["sitting", "sitting"]
    assert after[1]["pose"] != "sitting" and [s["text"] for s in after] == ["line 1", "line 2", "line 3"]
    with pytest.raises(ValueError, match="nothing to redo"):
        run.redraw(post, [7])


def test_halt_file_stops_a_build(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "STATE", tmp_path)
    (tmp_path / "HALT").write_text("")
    assert run.build("list", "") is None


def test_instagram_carousel_publish_writes_the_receipt(tmp_path, monkeypatch):
    post = make_post(tmp_path / "p")
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "IGAAtoken")
    calls = []

    def fake(method, url, **params):
        calls.append((method, url.rsplit("/", 1)[-1], params))
        if method == "GET":
            return {"status_code": "FINISHED"}
        if url.endswith("media_publish"):
            return {"id": "17900000000000001"}
        return {"id": f"c{len(calls)}"}

    monkeypatch.setattr(instagram, "_call", fake)
    media = instagram.publish(post, ["https://a/1.jpg", "https://a/2.jpg"], "hello")
    assert media == "17900000000000001"
    assert json.loads((post / "published.json").read_text())["media_id"] == media
    assert not (post / "publication_pending.json").exists()
    carousel = [p for m, u, p in calls if p.get("media_type") == "CAROUSEL"]
    assert carousel and carousel[0]["caption"] == "hello"
    # a second call returns the same post and makes no new calls
    count = len(calls)
    assert instagram.publish(post, ["https://a/1.jpg"], "hello") == media and len(calls) == count


def test_instagram_refuses_after_an_unfinished_attempt(tmp_path):
    post = make_post(tmp_path / "p")
    (post / "publication_pending.json").write_text("{}")
    with pytest.raises(instagram.InstagramError, match="Check Instagram"):
        instagram.publish(post, ["https://a/1.jpg"], "hi")



def test_a_reel_is_part_of_the_frozen_post_and_has_a_hosted_url(tmp_path):
    post = make_post(tmp_path / "20260911_2000_x", count=1)
    assert review.reel_url(review.prepare(post)) == ""
    (post / "reel.mp4").write_bytes(b"video")
    record = review.prepare(post)
    assert review.reel_url(record).endswith(f"/reviews/{record['token']}/reel.mp4")
    (post / "reel.mp4").write_bytes(b"another video")
    with pytest.raises(ValueError, match="changed"):
        review.read(post)


def test_instagram_reel_publish_asks_for_a_reel_on_the_grid(tmp_path, monkeypatch):
    post = make_post(tmp_path / "p", count=1)
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "IGAAtoken")
    calls = []

    def fake(method, url, **params):
        calls.append((method, url.rsplit("/", 1)[-1], params))
        if method == "GET":
            return {"status_code": "FINISHED"}
        if url.endswith("media_publish"):
            return {"id": "17900000000000002"}
        return {"id": "c1"}

    monkeypatch.setattr(instagram, "_call", fake)
    media = instagram.publish_reel(post, "https://a/reel.mp4", "hello")
    assert media == "17900000000000002"
    container = calls[0][2]
    assert (container["media_type"], container["video_url"], container["share_to_feed"], container["caption"]) == (
        "REELS", "https://a/reel.mp4", "true", "hello")
    assert json.loads((post / "published.json").read_text())["media_id"] == media
    count = len(calls)
    assert instagram.publish_reel(post, "https://a/reel.mp4", "hello") == media and len(calls) == count

class Reply:
    def __init__(self, status, body):
        self.status_code, self.body, self.text = status, body, json.dumps(body)

    def json(self):
        return self.body


def fake_graph(monkeypatch, refuse=None, live=None):
    """Stub requests for the Graph API. `refuse(data)` may return an error message for a container POST;
    `live` is Instagram's reply when asked, after posting, which images carry alt text."""
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "IGAAtoken")
    sent = []

    def request(method, url, timeout=None, data=None, params=None):
        sent.append((method, url.rsplit("/", 1)[-1], data or params))
        if method == "GET" and params["fields"] != "status_code":
            return live or Reply(200, {})
        if method == "GET":
            return Reply(200, {"status_code": "FINISHED"})
        if url.endswith("media_publish"):
            return Reply(200, {"id": "17900000000000001"})
        if refuse and refuse(data):
            return Reply(400, {"error": {"message": refuse(data), "code": 100}})
        return Reply(200, {"id": f"c{len(sent)}"})

    monkeypatch.setattr(instagram.requests, "request", request)
    return sent


def test_alt_text_goes_on_each_carousel_child_and_not_the_parent(tmp_path, monkeypatch):
    # after posting, Instagram shows alt text on only one of the two slides
    sent = fake_graph(monkeypatch, live=Reply(200, {"children": {"data": [{"id": "c1", "alt_text": "x"}, {"id": "c2"}]}}))
    alts = [instagram.alt_text(text) for text in ("a short [[title]]", "you said,\n[[i missed you]].")]
    assert alts == ["a short title. A small green donkey is in the corner.",
                    "you said, i missed you. A small green donkey is in the corner."]
    post = make_post(tmp_path / "p")
    instagram.publish(post, ["https://a/1.jpg", "https://a/2.jpg"], "hello", alts)
    posts = [data for method, _, data in sent if method == "POST"]
    children = [data for data in posts if data.get("is_carousel_item") == "true"]
    assert [child["alt_text"] for child in children] == alts
    parent = [data for data in posts if data.get("media_type") == "CAROUSEL"]
    assert len(parent) == 1 and "alt_text" not in parent[0]
    assert all("alt_text" not in data for _, name, data in sent if name == "media_publish")
    assert sent[-1][2]["fields"] == "children{alt_text}"
    assert json.loads((post / "published.json").read_text())["alt_text"] == "1/2"


def test_a_refused_alt_text_is_dropped_and_the_post_still_goes_out(tmp_path, monkeypatch):
    sent = fake_graph(monkeypatch, refuse=lambda data: "alt_text" in data and "(#100) Invalid parameter")
    post = make_post(tmp_path / "p", count=1)
    assert instagram.publish(post, ["https://a/1.jpg"], "hi", ["words. A small green donkey is in the corner."])
    first, retry = [data for method, name, data in sent if method == "POST" and name == "media"]
    assert first["alt_text"] and "alt_text" not in retry and retry["caption"] == first["caption"] == "hi"
    assert json.loads((post / "published.json").read_text())["alt_text"] == "0/1"
    # a refusal that has nothing to do with alt text still fails, after one try without it
    sent = fake_graph(monkeypatch, refuse=lambda data: "The image URL could not be fetched")
    with pytest.raises(instagram.InstagramError, match="could not be fetched"):
        instagram.publish(make_post(tmp_path / "q", count=1), ["https://a/1.jpg"], "hi", ["words."])
    assert [("alt_text" in data) for _, _, data in sent] == [True, False]


def test_a_failed_alt_text_check_never_fails_a_live_post(tmp_path, monkeypatch):
    fake_graph(monkeypatch, live=Reply(400, {"error": {"message": "(#100) Tried accessing nonexisting field"}}))
    post = make_post(tmp_path / "p", count=1)
    assert instagram.publish(post, ["https://a/1.jpg"], "hi", ["words."]) == "17900000000000001"
    assert json.loads((post / "published.json").read_text())["alt_text"].startswith("unknown: ")


def test_register_falls_back_to_the_plain_preview(tmp_path, monkeypatch):
    post = make_post(tmp_path / "20260911_0800_x")
    (post / "post.json").write_text(json.dumps({"format": "list", "topic": "love", "caption": "c",
                                                "slides": [{"text": "hook"}, {"text": "two"}]}))
    review.prepare(post)
    sent = []

    def api(token, operation, body=None):
        if operation == "register":
            sent.append(body)
            if "photos" in body:
                raise ValueError("The review service refused register: Invalid preview")
            return {"state": "waiting", "message_id": 5}
        return {"state": "waiting"}

    monkeypatch.setattr(run, "wait_for_hosting", lambda record: None)
    monkeypatch.setattr(run.review, "api", api)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    run.register(post)
    assert len(sent) == 2 and "photos" not in sent[1] and "Review ID:" in sent[1]["caption"]
    assert sent[1]["resources"].startswith("📝 Slides")


def test_note_why_records_area_then_refines_with_cause_and_slide(tmp_path, monkeypatch):
    post = make_post(tmp_path / "20260913_0800_x", count=4)
    monkeypatch.setattr(run, "POSTS", tmp_path)
    monkeypatch.setattr(run, "STATE", tmp_path / "state")
    monkeypatch.setattr(run, "WATCHLIST", tmp_path / "docs" / "craft-watchlist.md")
    token = review.prepare(post)["token"]
    assert run.note_why(token, "line") == ("a line was off", 1)
    assert run.note_why(token, "line.preachy") == ("preachy or advice-y", 1)
    assert run.note_why(token, "slide3") == ("slide 3", 0)
    text = run.WATCHLIST.read_text()
    assert text.count("\n- ") == 1 and "· line.preachy · preachy or advice-y · 20260913_0800_x · “line 1” · slide 3" in text
    # a typed shorthand resolves to the same cause and counts as the second time
    assert run.note_why(token, "PREACHY ") == ("preachy or advice-y", 2)
    # unsure keeps the area
    assert run.note_why(token, "hook") == ("slide 1 didn't pull me in", 1)
    assert run.note_why(token, "hook.unsure") == ("slide 1 didn't pull me in", 1)
    # free text is kept as the owner's words
    reason, count = run.note_why(token, "the joke\nlanded flat | honestly")
    assert (reason, count) == ("the joke landed flat | honestly", 1) and "· other · the joke landed flat" in run.WATCHLIST.read_text()


def test_note_why_survives_an_unknown_token(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "POSTS", tmp_path)
    monkeypatch.setattr(run, "STATE", tmp_path / "state")
    monkeypatch.setattr(run, "WATCHLIST", tmp_path / "w.md")
    assert run.note_why("0123456789abcdef", "hook.slow") == ("took too long to say what it's about", 1)
    assert "0123456789abcdef" in run.WATCHLIST.read_text()
