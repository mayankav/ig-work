import json
import shutil
import subprocess

import pytest

from suresilly import abreel, mascot

EXAMPLES = [
    {"hook": "“on my way”", "a": "“bas 5 min, nikal gaya”", "b": "arrives 20 min early", "win": "“bas 5 min” (in bed)",
     "send": "send this to the friend who is always “on my way”", "pose": "phone_call", "reveal_pose": "on_back", "send_pose": "beckoning"},
    {"hook": "“next time, i’ll pay”", "a": "“next time, i’ll pay”", "b": "sends a ₹14 UPI request", "win": "“next time, i’ll pay”",
     "send": "send this to the friend who always says “next time, i’ll pay”", "pose": "winking", "reveal_pose": "hands_behind_back", "send_pose": "beckoning"},
    {"hook": "“plan banate hain”", "a": "“plan banate hain”", "b": "books the tickets first", "win": "“plan banate hain”",
     "send": "send this to the friend who has been “planning” since 2022", "pose": "idea", "reveal_pose": "facepalm", "send_pose": "beckoning"},
]


@pytest.mark.parametrize("slide", EXAMPLES)
def test_every_element_lines_up_on_the_system(slide):
    screens, log = abreel.scenes(slide)
    assert abreel.layout_problems(log) == []
    assert {scene for scene, *_ in log} == {"hook", "question", "reveal", "send"}


def test_the_check_catches_what_does_not_line_up():
    top = abreel.SAFE[1] + (abreel.SAFE_H - 100) / 2 + abreel.BIAS         # a 100 px element centred the way the layout centres it
    inside = ("hook", "a", 100.0, top, 940.0, top + 100, 0)
    assert abreel.layout_problems([inside]) == []
    assert any("safe area" in p for p in abreel.layout_problems([("hook", "a", 100.0, 100.0, 940.0, 200.0, 0)]))
    assert any("content column" in p for p in abreel.layout_problems([("hook", "a", 40.0, top, 940.0, top + 100, 0)]))
    assert any("not centred" in p for p in abreel.layout_problems([("hook", "a", 100.0, top, 900.0, top + 100, 0)]))
    assert any("group is not centred" in p for p in abreel.layout_problems([("hook", "a", 100.0, top + 80, 940.0, top + 180, 0)]))
    two = [("q", "a", 100.0, 400.0, 940.0, 500.0, 0), ("q", "b", 100.0, 515.0, 940.0, 600.0, 0)]
    assert any("not on the scale" in p for p in abreel.layout_problems(two))


def test_balanced_lines_leave_no_lonely_word():
    line = "send this to the friend who is always “on my way”"
    plain = abreel.wrap(line, abreel.HEADING, abreel.COLW)
    balanced = abreel.wrap(line, abreel.HEADING, abreel.COLW, balance=True)
    assert len(balanced) == len(plain) and len(balanced[-1].split()) >= 3 and " ".join(balanced) == line


def test_timing_follows_reading_and_the_count_ends_on_the_reveal():
    short, long = EXAMPLES[0], {**EXAMPLES[0], "a": "one two three four five six", "b": "one two three four five six"}
    tl, slow = abreel.timeline(short), abreel.timeline(long)
    assert tl.q >= 2.6 and tl.count == (tl.reveal - 3, tl.reveal - 2, tl.reveal - 1)             # 3, 2, 1 then the reveal
    assert tl.q < tl.count[0] < tl.reveal < tl.send < tl.ask < tl.total
    assert slow.reveal - slow.q > tl.reveal - tl.q and slow.total > tl.total                       # more words, more time
    words = len(short["a"].split()) + len(short["b"].split()) + 4
    assert tl.reveal - tl.q >= words / abreel.READ_WPS                                              # the options can be read before the reveal
    assert 15 < tl.total < 30 and tl.total == round(tl.total, 2)


def test_every_screen_starts_on_the_beat_and_words_land_in_order():
    for slide in EXAMPLES:
        tl = abreel.timeline(slide)
        for moment in (tl.q, tl.reveal, tl.send, tl.ask, tl.total):
            assert abs(moment / abreel.BEAT - round(moment / abreel.BEAT)) < 1e-6, moment
        assert list(tl.hook_words) == sorted(tl.hook_words) and tl.hook_words[0] == 0.0 and tl.hook_words[-1] < tl.q - 0.5
        assert len(tl.hook_words) == len(slide["hook"].split()) and len(tl.send_words) == len(slide["send"].split())
        assert tl.send_words[0] > tl.send and tl.send_words[-1] < tl.ask                              # the line lands before the ask


def test_the_quoted_words_of_the_send_line_get_an_underline_and_each_word_a_tile():
    sc, _ = abreel.scenes(EXAMPLES[0])
    assert len(sc["send_words"]) == len(EXAMPLES[0]["send"].split()) and len(sc["hook_words"]) == 3
    assert len(sc["send_bars"]) >= 1 and all(right > left for left, right, _ in sc["send_bars"])
    bar_left = min(left for left, _, _ in sc["send_bars"])
    assert any(abs(cx - bar_left) < 200 for _, cx, _ in sc["send_words"])                            # the bar sits under the quoted words


def test_the_first_frame_already_has_a_face_and_a_word_and_the_reveal_is_not_the_same_as_the_question():
    from PIL import ImageChops
    sc, _ = abreel.scenes(EXAMPLES[0])
    tl = abreel.timeline(EXAMPLES[0])
    first, hook, count, drop = (abreel.frame(sc, tl, t) for t in (0.0, 1.0, tl.count[0] + 0.3, tl.reveal + 0.3))
    background = first.getpixel((5, 5))
    assert first.getbbox() and ImageChops.difference(first, hook).getbbox()                             # words land between frame 0 and 1 s
    assert count.getpixel((5, 5)) != background                                                           # the question screen has its own colour
    assert ImageChops.difference(count, drop).getbbox()


def test_the_still_has_no_confetti_flash_or_shake(tmp_path):
    from PIL import Image
    path = abreel.still({"format": "ab", "slides": [EXAMPLES[0]]}, tmp_path / "01.jpg")
    with Image.open(path) as image:
        assert image.size == (1080, 1350) and image.getpixel((5, 5))[0] > 150                           # red, not a white flash


def test_a_slower_reading_speed_slows_the_whole_reel(monkeypatch):
    before = abreel.timeline(EXAMPLES[0]).total
    monkeypatch.setattr(abreel, "READ_WPS", 1.5)
    assert abreel.timeline(EXAMPLES[0]).total > before


def test_the_still_is_a_4_by_5_picture_of_the_reveal(tmp_path):
    from PIL import Image
    post = {"format": "ab", "slides": [EXAMPLES[0]]}
    path = abreel.still(post, tmp_path / "01.jpg")
    with Image.open(path) as image:
        assert image.size == (1080, 1350)


def test_render_draws_an_ab_post_as_one_still(tmp_path):
    from suresilly import render
    files = render.render({"format": "ab", "slides": [EXAMPLES[1]]}, tmp_path / "slides")
    assert [f.name for f in files] == ["01.jpg"]


def test_poses_are_three_different_real_ones():
    chosen = mascot.ab_poses({"pose": "phone_call", "reveal_pose": "phone_call", "send_pose": "not_a_pose"}, "seed")
    assert set(chosen) == {"pose", "reveal_pose", "send_pose"} and len(set(chosen.values())) == 3
    assert chosen["pose"] == "phone_call" and all(name in mascot.NOTES for name in chosen.values())
    again = mascot.ab_poses({}, "seed", avoid=set(chosen.values()))
    assert not set(again.values()) & set(chosen.values())


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffmpeg is not installed")
def test_makes_a_reel_with_video_and_sound_as_long_as_the_timeline(tmp_path, monkeypatch):
    monkeypatch.setattr(abreel, "FPS", 10)                    # fewer frames: this checks the file, not the motion
    post = {"format": "ab", "slides": [EXAMPLES[0]]}
    folder = tmp_path / "20261006_2000_on-my-way"
    folder.mkdir()
    video = abreel.make(post, folder)
    tl = abreel.timeline(EXAMPLES[0])
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,pix_fmt,duration",
                                      "-of", "json", str(video)], capture_output=True, text=True).stdout)["streams"]
    by = {s["codec_type"]: s for s in info}
    assert (by["video"]["codec_name"], by["video"]["width"], by["video"]["height"], by["video"]["pix_fmt"]) == ("h264", 1080, 1920, "yuv420p")
    assert by["audio"]["codec_name"] == "aac"
    assert abs(float(by["video"]["duration"]) - tl.total) < 0.2 and abs(float(by["audio"]["duration"]) - tl.total) < 0.3   # sound to the very end
    reel = post["reel"]
    assert reel["kind"] == "ab" and reel["seconds"] == tl.total and reel["reveal"] == tl.reveal and reel["sound_theme"] == "phone"
    assert reel["tune"] == "hype" and 900 <= reel["cover_ms"] <= 1500                                  # the grid cover: the hook once all its words have landed
    assert reel["sounds"] and {s["source"] for s in reel["sounds"]} == {"built-in"} and reel["sound_notes"] == []   # no key: all built in


def test_a_reel_that_does_not_fit_is_refused_in_plain_words(tmp_path):
    slide = {**EXAMPLES[0], "hook": "one two three four five six seven eight nine ten eleven twelve thirteen fourteen"}
    folder = tmp_path / "20261006_2000_x"
    folder.mkdir()
    from suresilly.render import RenderError
    with pytest.raises(RenderError, match="does not fit"):
        abreel.make({"format": "ab", "slides": [slide]}, folder)
