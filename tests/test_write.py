import json
import re

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


def test_hashtag_lists_belong_to_topics_and_reach_the_writer():
    assert set(write.TAGS) <= set(write.PEOPLE.values())
    for tags in write.TAGS.values():
        assert all(re.fullmatch(r"#[a-z]+", tag) for tag in tags.split())
    angle = {"topic": "siblings", "person": "a sister", "shape": "x"}
    assert "#sisterlove" in write.ask("list", angle) and write.ask("list", angle).endswith("Write it.")
    assert "Hashtags" not in write.ask("list", {**angle, "topic": "adult life"})


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


def test_tidy_gives_only_the_cover_a_pose_and_derives_the_mood():
    post = {"slides": [{"text": "title", "pose": "hands_over_mouth"},   # any real pose may be the cover
                       {"text": "a", "pose": "warm_mug"},               # inner slides have no donkey
                       {"text": "b", "pose": "point_right"},
                       {"text": "c", "pose": "no_such_pose", "mood": "sad"}]}
    tidied = write.tidy(post, "list")
    assert [(s["mood"], s["pose"]) for s in tidied] == [
        ("joy", "hands_over_mouth"), ("calm", None), ("calm", None), ("sad", None)]
    assert write.tidy({"slides": [{"text": "title", "pose": "not_real"}]}, "list")[0]["mood"] == "invite"  # a pointing donkey later


def good_oneliner():
    return {"hook_options": ["a", "b", "c"], "caption": "one line\nsend it to didi\n#siblings", "alt": "a card",
            "slides": [{"setup": "we fought over the window seat, but", "twist": "today you can have the whole bus.",
                        "pose": "arms_crossed_waiting", "twist_pose": "laughing"}]}


def test_a_oneliner_needs_a_setup_and_a_twist_of_sensible_length():
    assert write.problems(good_oneliner(), "oneliner") == []
    for part, value in (("setup", ""), ("setup", "one two"), ("twist", "word"), ("twist", " ".join(["w"] * 11))):
        post = good_oneliner()
        post["slides"][0][part] = value
        assert any(f"needs a {part}" in fault for fault in write.problems(post, "oneliner")), (part, value)
    old_shape = {**good_oneliner(), "slides": [{"text": "just one sentence here", "pose": "sitting"}]}
    assert len(write.problems(old_shape, "oneliner")) == 2          # no setup, no twist
    cut = good_oneliner()
    cut["slides"][0]["setup"] = "we fought over [[the window seat, but"
    assert any("not closed inside" in fault for fault in write.problems(cut, "oneliner"))


def test_tidy_keeps_both_beats_and_both_poses_of_a_oneliner():
    slide = write.tidy(good_oneliner(), "oneliner")[0]
    assert slide["text"] == "we fought over the window seat, but today you can have the whole bus."
    assert (slide["setup"], slide["twist"]) == ("we fought over the window seat, but", "today you can have the whole bus.")
    assert (slide["pose"], slide["twist_pose"], slide["mood"]) == ("arms_crossed_waiting", "laughing", "wistful")
    same = good_oneliner()
    same["slides"][0]["twist_pose"] = "arms_crossed_waiting"       # the same pose twice is no reaction: dropped
    assert write.tidy(same, "oneliner")[0]["twist_pose"] is None


def test_a_oneliner_goes_through_the_writer_with_its_beats():
    post = write.write_post("oneliner", "s", previous=[], chat=lambda s, u: (good_oneliner(), "m"), recent=[], notes=[])
    assert post["slides"][0]["twist"].startswith("today you can") and "window seat" in post["slides"][0]["text"]


def test_the_brief_lists_openings_to_avoid(tmp_path):
    for name, text in (("99990101_0800_a", "some friends feel like a radio"), ("99990101_2000_b", "[[some]] friends feel better"),
                       ("99990102_0800_c", "having someone who writes")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "post.json").write_text(json.dumps({"slides": [{"text": text}]}))
    assert sorted(write.recent_openers(tmp_path)) == ["having someone who", "some friends feel"]  # each once

    seen = []

    def chat(system, user):
        seen.append(user)
        return good_oneliner(), "m"

    write.write_post("oneliner", "s", previous=[], recent=[], notes=[], openers=["some friends feel"], chat=chat)
    assert "some friends feel ..." in seen[0]


def test_the_prompt_lists_every_pose():
    from suresilly import mascot
    assert all(name in write.SYSTEM for name in mascot.NOTES)


def test_the_brief_carries_recent_posts_and_owner_notes_but_not_fine(tmp_path):
    folder = tmp_path / "99990101_0800_x"
    folder.mkdir()
    (folder / "post.json").write_text(json.dumps({"slides": [{"text": "old [[hook]]"}, {"text": "the porch light"}]}))
    assert write.recent_posts(tmp_path) == ["old hook / the porch light"]
    watch = tmp_path / "w.md"
    watch.write_text("# Craft watchlist\n\n- 9999-01-01 · line.preachy · preachy or advice-y · slug · “a hook” · slide 3\n"
                     "- 9999-01-02 · fine · nothing to learn · slug2 · “b”\n"
                     "- 9999-01-03 · other · too long, sister said so · slug3 · “c”\n")
    assert write.owner_notes(watch) == ["the owner said: too long, sister said so. the post: “c”",
                                        "that line lectured: state the moment, cut the lesson (slide 3). the post: “a hook”"]
    seen = []

    def chat(system, user):
        seen.append(user)
        return good_list(), "m"

    write.write_post("list", "s", previous=[], chat=chat, recent=["old hook / the porch light"],
                     notes=["preachy or advice-y: “a hook”"])
    assert "Already posted" in seen[0] and "the porch light" in seen[0] and "preachy or advice-y" in seen[0]
    write.write_post("list", "s", previous=[], chat=chat, recent=[], notes=[])
    assert "Already posted" not in seen[-1] and "notes from the owner" not in seen[-1]


def good_ab():
    return {"hook_options": ["a", "b", "c"], "caption": "one line\nsend it\n#friendship", "alt": "a quiz",
            "slides": [{"hook": "“on my way”", "a": "“bas 5 min, nikal gaya”", "b": "arrives 20 min early", "win": "“bas 5 min” (in bed)",
                        "send": "send this to the friend who is always “on my way”",
                        "pose": "phone_call", "reveal_pose": "on_back", "send_pose": "beckoning"}]}


def test_an_ab_post_needs_its_fields_in_range_and_a_send_line():
    assert write.problems(good_ab(), "ab") == []
    for part, value in (("hook", ""), ("hook", " ".join(["w"] * 6)), ("a", "one"), ("b", " ".join(["w"] * 9)),
                        ("win", "x"), ("send", "send this now")):
        post = good_ab()
        post["slides"][0][part] = value
        assert any(f"needs a {part}" in fault for fault in write.problems(post, "ab")), (part, value)
    post = good_ab()
    post["slides"][0]["send"] = "tell the friend who is always “on my way”"
    assert any("must start" in fault for fault in write.problems(post, "ab"))
    post = good_ab()
    post["slides"][0]["a"] = "[[bas 5 min]] nikal gaya"
    assert any("no highlights" in fault for fault in write.problems(post, "ab"))
    assert "a ab needs 1-1 slides" in write.problems({**good_ab(), "slides": good_ab()["slides"] * 2}, "ab")


def test_tidy_builds_the_text_of_an_ab_post_and_keeps_real_poses_only():
    raw = good_ab()
    raw["slides"][0]["send_pose"] = "not_a_pose"
    slide = write.tidy(raw, "ab")[0]
    assert slide["text"] == "“on my way” which friend are you? A: “bas 5 min, nikal gaya”. B: arrives 20 min early."
    assert (slide["pose"], slide["reveal_pose"], slide["send_pose"], slide["mood"]) == ("phone_call", "on_back", None, "joy")


def test_an_ab_is_always_about_one_close_friend():
    angle = write.draw("ab", "seed")
    assert (angle["person"], angle["topic"]) == ("a close friend", "friendship") and angle["shape"] in write.SHAPES["ab"]
    assert write.FORMATS["ab"] == (1, 1) and len(set(write.SHAPES["ab"])) == len(write.SHAPES["ab"])


def test_an_ab_goes_through_the_writer_and_the_brief_teaches_the_send_test():
    post = write.write_post("ab", "s", previous=[], chat=lambda s, u: (good_ab(), "m"), recent=[], notes=[])
    assert post["format"] == "ab" and post["slides"][0]["send"].endswith("“on my way”") and post["person"] == "a close friend"
    assert "(1) name one real friend by what they say" in write._WRITER_CRAFT and "send_pose" in write.SYSTEM
    assert "for an ab, run the three-part test" in write._EDITOR_CRAFT
