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
