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
