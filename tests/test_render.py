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


def test_reel_length_follows_the_words():
    from suresilly import reel
    assert reel.seconds_for("five little words right here") == 8.0          # never under 8
    assert reel.seconds_for(" ".join(["w"] * 20)) == 10.0
    assert reel.seconds_for("[[" + " ".join(["w"] * 23) + "]]") == 11.2   # highlight marks aren't words


def test_every_pose_mood_has_a_tune_and_the_same_seed_gives_the_same_tune(tmp_path):
    import wave
    from suresilly import music
    assert set(mascot.POSES) <= set(music.MOODS)
    a = music.compose("warm", "slug-1", 8.0, tmp_path / "a.wav")
    b = music.compose("warm", "slug-1", 8.0, tmp_path / "b.wav")
    c = music.compose("warm", "slug-2", 8.0, tmp_path / "c.wav")
    assert a.read_bytes() == b.read_bytes() != c.read_bytes()
    with wave.open(str(a)) as tune:
        assert (tune.getnchannels(), tune.getframerate(), tune.getnframes()) == (2, 44100, 8 * 44100)


def test_makes_a_reel_instagram_accepts(tmp_path):
    import json
    import shutil
    import subprocess
    from suresilly import reel
    pytest.importorskip("playwright")
    if not shutil.which("ffprobe"):
        pytest.skip("ffmpeg is not installed")
    post = {"format": "oneliner", "slides": [{"text": "a line [[worth]] sending " * 3, "mood": "wistful", "pose": "photo_frame"}]}
    folder = tmp_path / "20260913_2000_a-line"
    folder.mkdir()
    try:
        video = reel.make(post, folder)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("chromium is not installed")
        raise
    assert post["reel"] == {"seconds": 8.0, "tune": "wistful"}
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                       "stream=codec_name,width,height,pix_fmt:format=duration",
                                       "-of", "json", str(video)], capture_output=True, text=True).stdout)
    streams = {s["codec_name"]: s for s in probe["streams"]}
    assert (streams["h264"]["width"], streams["h264"]["height"], streams["h264"]["pix_fmt"]) == (1080, 1920, "yuv420p")
    assert "aac" in streams and abs(float(probe["format"]["duration"]) - 8.0) < 0.1


def test_two_beat_timing_follows_the_reading_not_a_fixed_delay():
    from suresilly import reel
    assert reel.reveal_for("one two three") == 2.0                        # never before 2 s
    assert reel.reveal_for(" ".join(["w"] * 7)) == 3.0
    assert reel.reveal_for(" ".join(["w"] * 20)) == 3.5                   # never after 3.5 s
    reveal, total = reel.two_beat_seconds(" ".join(["w"] * 9), "three small words")
    assert (reveal, total) == (3.5, 8.0)                                  # the card holds 4 s at least; 8 s floor
    assert reel.two_beat_seconds("a b c d e f", " ".join(["w"] * 10)) == (2.7, 8.7)   # a long twist holds longer


def test_the_blank_blinks_until_the_reveal_then_the_finished_card_holds():
    from pathlib import Path
    from suresilly import reel
    frames = {name: Path(name) for name in ("blank_on", "blank_off", "full")}
    parts = reel.timeline(frames, 2.2, 8.0)
    assert [p.name for p, _ in parts] == ["blank_on", "blank_off", "blank_on", "blank_off", "blank_on", "full"]
    assert [round(length, 1) for _, length in parts] == [0.5, 0.5, 0.5, 0.5, 0.2, 5.8]
    assert round(sum(length for _, length in parts), 1) == 8.0


def test_the_blank_and_the_finished_card_lay_out_identically(tmp_path):
    pytest.importorskip("playwright")
    from PIL import Image, ImageChops
    from suresilly import render
    post = {"slides": [{"text": "we fought over [[the window seat]], but today you can have the whole bus.",
                        "setup": "we fought over [[the window seat]], but", "twist": "today you can have the whole bus.",
                        "pose": "arms_crossed_waiting", "twist_pose": "arms_crossed_waiting"}]}
    try:
        frames = render.reel_frames(post, tmp_path)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("chromium is not installed")
        raise
    assert set(frames) == {"blank_on", "blank_off", "full"}
    on, off, full = (Image.open(frames[k]).convert("L") for k in ("blank_on", "blank_off", "full"))
    top = on.crop((0, 0, 1080, 560))                       # the setup's lines: the same pixels in all three
    assert ImageChops.difference(top, off.crop((0, 0, 1080, 560))).getbbox() is None
    assert ImageChops.difference(top, full.crop((0, 0, 1080, 560))).getbbox() is None
    assert ImageChops.difference(on, off).getbbox() is not None   # the cursor is the only difference between the two blanks
    assert ImageChops.difference(off, full).getbbox() is not None  # the twist is what the reveal adds


def test_only_the_cover_shows_a_donkey_and_a_oneliner_card_shows_the_twist_pose(tmp_path):
    pytest.importorskip("playwright")
    from PIL import Image
    from suresilly import render
    post = {"slides": [{"text": "a short cover", "pose": "hands_over_mouth"},
                       {"text": "an inner line", "pose": None}, {"text": "another inner line", "pose": "warm_mug"}]}
    try:
        files = render.render(post, tmp_path / "s")
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("chromium is not installed")
        raise
    corner = (540, 800, 1080, 1350)                          # lower right: where the donkey is
    assert Image.open(files[0]).convert("L").crop(corner).getextrema()[0] < 100   # the cover's dark outline
    for inner in files[1:]:                                  # even a slide that names a pose has no donkey
        assert Image.open(inner).convert("L").crop(corner).getextrema()[0] > 120


def test_makes_a_two_beat_reel_with_the_reveal_and_a_cover_frame_after_it(tmp_path):
    import json
    import shutil
    import subprocess
    from suresilly import reel
    pytest.importorskip("playwright")
    if not shutil.which("ffprobe"):
        pytest.skip("ffmpeg is not installed")
    post = {"format": "oneliner", "slides": [{
        "text": "we fought over the window seat, but today you can have the whole bus.",
        "setup": "we fought over the window seat, but", "twist": "today you can have the whole bus.",
        "mood": "wistful", "pose": "arms_crossed_waiting", "twist_pose": "laughing"}]}
    folder = tmp_path / "20261006_2000_we-fought"
    folder.mkdir()
    try:
        video = reel.make(post, folder)
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip("chromium is not installed")
        raise
    assert post["reel"] == {"seconds": 8.0, "tune": "wistful", "reveal": 3.0, "cover_ms": 3600}
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                       "stream=codec_name,width,height,pix_fmt:format=duration",
                                       "-of", "json", str(video)], capture_output=True, text=True).stdout)
    streams = {s["codec_name"]: s for s in probe["streams"]}
    assert (streams["h264"]["width"], streams["h264"]["height"], streams["h264"]["pix_fmt"]) == (1080, 1920, "yuv420p")
    assert 7.9 <= float(probe["format"]["duration"]) <= 8.2
