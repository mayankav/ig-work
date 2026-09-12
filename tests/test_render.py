import pytest
from PIL import Image

from suresilly import mascot, render


def test_markup_escapes_highlights_and_curls_quotes():
    html = render.markup("don't <b>[[stop]]</b> \"now\"")
    assert html == "don’t &lt;b&gt;<span class=\"mark\">stop</span>&lt;/b&gt; “now”"


def test_every_mood_has_poses_on_disk():
    for mood, names in mascot.POSES.items():
        assert names, mood
        for name in names:
            assert mascot.path(name).is_file()


def test_pick_never_repeats_inside_a_post_and_honours_avoid():
    chosen = mascot.pick(["joy"] * 6, "seed")
    assert len(set(chosen)) == 6
    again = mascot.pick(["joy"], "seed", avoid=set(chosen))
    assert again[0] not in chosen


def test_paper_is_the_same_every_time(tmp_path):
    a = render.paper(tmp_path / "a.png").read_bytes()
    b = render.paper(tmp_path / "b.png").read_bytes()
    assert a == b


def test_renders_slides_at_instagram_size(tmp_path):
    pytest.importorskip("playwright")
    post = {"slides": [{"text": "a short [[title]]", "pose": "point_right"},
                       {"text": "a longer line " * 12, "pose": "warm_mug"}]}
    try:
        files = render.render(post, tmp_path / "slides")
    except Exception as exc:  # no browser installed on this machine
        if "Executable doesn't exist" in str(exc):
            pytest.skip("chromium is not installed")
        raise
    assert [f.name for f in files] == ["01.jpg", "02.jpg"]
    for path in files:
        with Image.open(path) as image:
            assert image.size == (1080, 1350) and image.format == "JPEG"
    sheet = render.contact_sheet(files, tmp_path / "sheet.png")
    assert sheet.exists()


def test_every_pose_on_disk_has_a_note_and_a_mood():
    on_disk = {p.stem for p in mascot.LIBRARY.glob("*.png")}
    assert set(mascot.NOTES) == on_disk
    assert set(mascot.MOOD_OF) == on_disk


def test_choose_keeps_the_writers_pose_and_falls_back_by_mood():
    slides = [{"text": "t", "mood": "invite", "pose": "presenting"},
              {"text": "a", "mood": "warm", "pose": "warm_mug"},
              {"text": "b", "mood": "sad", "pose": "warm_mug"},       # repeat: falls back
              {"text": "c", "mood": "joy", "pose": "not_a_pose"},     # unknown: falls back
              {"text": "d", "mood": "calm", "pose": None}]
    chosen = mascot.choose(slides, "seed")
    assert chosen[:2] == ["presenting", "warm_mug"]
    assert chosen[2] in mascot.POSES["sad"] and chosen[3] in mascot.POSES["joy"] and chosen[4] in mascot.POSES["calm"]
    assert len(set(chosen)) == 5
    assert mascot.choose(slides, "seed") == chosen
