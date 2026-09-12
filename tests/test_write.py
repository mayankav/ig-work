import json

import pytest

from suresilly import write


def slides(*texts, mood="calm"):
    return [{"text": t, "mood": mood} for t in texts]


def good_list():
    return {"hook_options": ["a", "b", "c"],
            "slides": slides("things that feel like home", *[f"item number {n} is here" for n in range(6)],
                             "send this to your person"),
            "caption": "one line\nsend it to someone\n#home #love", "alt": "a list"}


def test_counts_by_format():
    assert write.problems(good_list(), "list") == []
    assert "a oneliner needs 1-1 slides" in write.problems(good_list(), "oneliner")


def test_catches_links_hashtags_and_double_highlights():
    post = good_list()
    post["slides"][1]["text"] = "see www.example.com"
    post["slides"][2]["text"] = "so #blessed"
    post["slides"][3]["text"] = "[[one]] and [[two]]"
    found = " ".join(write.problems(post, "list"))
    assert "slide 2 has a link" in found and "slide 3 has a link or a hashtag" in found
    assert "slide 4 must highlight at most one phrase" in found


def test_banned_words_match_whole_words_only():
    assert write.banned_in("a quiet sigh at night") == ["sigh"]
    assert write.banned_in("out of sight, out of mind") == []
    assert write.banned_in("It’s okay to rest") == ["it's okay to"]


def test_tidy_sets_cover_pose_caps_highlights_and_strips_dashes():
    post = {"slides": slides("title", "[[a]] x", "[[b]] y", "[[c]] z", "[[d]] w — end", mood="invite")}
    tidied = write.tidy(post, "list")
    assert tidied[0]["mood"] == "invite" and all(s["mood"] == "warm" for s in tidied[1:])
    assert sum("[[" in s["text"] for s in tidied) == write.MAX_HIGHLIGHTS
    assert tidied[4]["text"] == "d w, end"


def test_caption_puts_hashtags_on_one_last_line():
    caption = write.tidy_caption("first line #a\nsend it to them\n\n#b\n#c #a")
    assert caption == "first line\nsend it to them\n\n#a #b #c"


def test_similar_hooks_are_caught():
    assert write.too_similar("things that feel like home", ["things that feel like home to me"])
    assert not write.too_similar("things that feel like home", ["small ways a friend shows up"])


def test_draw_ties_topic_to_person():
    angle = write.draw("list", "seed-1")
    assert write.PEOPLE[angle["person"]] == angle["topic"]
    assert angle["shape"] in write.SHAPES["list"]


def test_retries_then_uses_the_editor():
    calls = []

    def chat(system, user):
        calls.append(system)
        if len(calls) == 1:
            return {"slides": slides("too few"), "caption": "x"}, "m"
        post = good_list()
        if system == write.EDITOR:
            post["slides"][0]["text"] = "edited title"
        return post, "m"

    post = write.write_post("list", "s", previous=[], chat=chat)
    assert post["slides"][0]["text"] == "edited title"
    assert "edit by" in post["model"] and len(calls) == 3


def test_a_broken_edit_keeps_the_draft():
    def chat(system, user):
        if system == write.EDITOR:
            return {"slides": [], "caption": ""}, "m"
        return good_list(), "m"

    post = write.write_post("list", "s", previous=[], chat=chat)
    assert post["slides"][0]["text"] == "things that feel like home"


def test_gives_up_with_the_reason():
    with pytest.raises(write.WriteError, match="needs 7-9 slides"):
        write.write_post("list", "s", previous=[], chat=lambda s, u: ({"slides": [], "caption": "x"}, "m"))


def test_previous_hooks_reads_post_folders(tmp_path):
    folder = tmp_path / "20260101_0800_x"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps({"slides": [{"text": "old hook"}]}))
    assert write.previous_hooks(tmp_path) == ["old hook"]


def test_tidy_takes_the_pose_by_name_and_derives_the_mood():
    post = {"slides": [{"text": "title", "pose": "sitting"},          # not an invite pose: dropped
                       {"text": "a", "pose": "warm_mug"},
                       {"text": "b", "pose": "point_right"},          # invite pose mid-post: dropped
                       {"text": "c", "pose": "no_such_pose", "mood": "sad"},
                       {"text": "d", "pose": "presenting"}]}
    tidied = write.tidy(post, "list")
    assert [(s["mood"], s["pose"]) for s in tidied] == [
        ("invite", None), ("warm", "warm_mug"), ("warm", None), ("sad", None), ("warm", None)]
    assert write.tidy({"slides": [{"text": "one", "pose": "listening"}]}, "oneliner")[0]["pose"] == "listening"


def test_the_prompt_lists_every_pose():
    from suresilly import mascot
    assert all(name in write.SYSTEM for name in mascot.NOTES)
