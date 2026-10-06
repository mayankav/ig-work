import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from suresilly import sfx, synth

TL = SimpleNamespace(q=3.0, count=(6.5, 7.5, 8.5), reveal=9.5, send=13.5, ask=19.5, total=23.0, beat=0.5,
                     hook_words=(0.0, 0.22, 0.44), send_words=(13.85, 14.17, 14.49, 14.81))


def test_the_theme_comes_from_the_words():
    assert sfx.theme_of("“on my way” bas 5 min") == "phone"
    assert sfx.theme_of("next time, i’ll pay. sends a ₹14 UPI request") == "money"
    assert sfx.theme_of("“plan banate hain” books the tickets first") == "chat"
    assert sfx.theme_of("the friend who is late") == "travel"
    assert sfx.theme_of("a chocolate cake") == ""            # "late" inside a word is not a theme
    assert sfx.theme_of("") == ""


def test_events_follow_the_reels_clock_and_the_theme_adds_one_accent():
    plain = sfx.events(TL, "")
    assert [e.role for e in plain].count("tick") == 3 and [e.at for e in plain] == sorted(e.at for e in plain)
    riser = next(e for e in plain if e.role == "riser")
    assert riser.until == pytest.approx(TL.reveal - 0.1) and riser.at < TL.count[0]       # it stops a breath before the reveal
    assert {"page_turn", "chime", "boing", "whoosh", "notify", "click", "pop", "hit", "confetti", "key", "kick", "hat"} <= {e.role for e in plain}
    assert [e.at for e in plain if e.role == "key"] == [*TL.hook_words, *TL.send_words]            # a key click for every word
    kicks = [e.at for e in plain if e.role == "kick"]
    assert kicks[0] == 0.0 and all(abs(k / TL.beat - round(k / TL.beat)) < 1e-6 for k in kicks)       # on the beat grid, from the first frame
    assert not any(TL.reveal - 0.45 <= k < TL.reveal + 0.25 for k in kicks)                          # the breath before the reveal
    assert next(e for e in plain if e.role == "hit").at == TL.reveal
    money = sfx.events(TL, "money")
    assert len(money) == len(plain) + 1 and any(e.role == "coin" and e.at == pytest.approx(TL.reveal + 0.4) for e in money)
    assert any(e.role == "ring" and e.at < 0.1 for e in sfx.events(TL, "phone"))
    assert sfx.bed_words("money") == "cafe ambience chatter" and sfx.bed_words("") == ""


@pytest.mark.parametrize("role", sorted(synth.MAKERS))
def test_every_built_in_sound_is_real_audio(role, tmp_path):
    path, seconds = synth.write(role, tmp_path / f"{role}.wav")
    assert 0.03 < seconds < 3 and path.stat().st_size > 1000
    assert sfx.level_db(path) > -20                          # not silent, and the sample peak is near full scale


def test_without_a_key_nothing_goes_to_the_network_and_every_role_is_built_in(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the network was used")
    monkeypatch.setattr(sfx.requests, "get", boom)
    sounds, bed, notes = sfx.gather(["tick", "pop", "pop", "chime"], "cafe ambience chatter", "seed", tmp_path)
    assert sorted(sounds) == ["chime", "pop", "tick"] and bed is None and notes == []
    assert all(s.meta == {"role": r, "source": "built-in"} for r, s in sounds.items())


class FakeFreesound:
    """Answers Freesound's search and preview download. `results` is what a search returns for every query."""

    def __init__(self, results, status=200, audio_status=200, fit=False):
        self.results, self.status, self.audio_status, self.fit, self.calls = results, status, audio_status, fit, []

    def __call__(self, url, timeout=None, params=None):
        self.calls.append((url, params))
        if url.endswith("/search/"):
            results = self.results
            if self.fit:  # answer every search with sounds of a length that fits what was asked for
                low, high = map(float, re.search(r"duration:\[([\d.]+) TO ([\d.]+)\]", params["filter"]).groups())
                results = [{**r, "duration": (low + high) / 2} for r in results]
            return SimpleNamespace(status_code=self.status, json=lambda: {"results": results})
        return SimpleNamespace(status_code=self.audio_status, content=Path(self.audio).read_bytes())


def result(id, license="http://creativecommons.org/publicdomain/zero/1.0/", duration=0.4, rating=4.5, ratings=20):
    return {"id": id, "name": f"sound {id}", "username": f"user{id}", "license": license, "duration": duration,
            "avg_rating": rating, "num_ratings": ratings, "previews": {"preview-hq-mp3": f"https://cdn.freesound.org/previews/{id}.mp3"}}


@pytest.fixture
def freesound(tmp_path, monkeypatch):
    def install(results, **kwargs):
        fake = FakeFreesound(results, **kwargs)
        fake.audio = synth.write("click", tmp_path / "preview.wav")[0]   # real audio bytes, so ffprobe and ffmpeg can read them
        monkeypatch.setattr(sfx.requests, "get", fake)
        monkeypatch.setattr(sfx, "key", lambda name: "SECRETKEY")
        return fake
    return install


def test_it_asks_for_cc0_of_the_right_length_and_keeps_who_made_it(freesound, tmp_path):
    fake = freesound([result(1, license="http://creativecommons.org/licenses/by-nc/4.0/", rating=5),   # not CC0: never used
                      result(2, duration=9.0),                                                         # too long: never used
                      result(3)])
    sounds, bed, notes = sfx.gather(["tick"], "", "seed", tmp_path)
    search = next(params for url, params in fake.calls if url.endswith("/search/"))
    assert search["token"] == "SECRETKEY" and search["query"] == "clock tick"
    assert 'license:"Creative Commons 0"' in search["filter"] and "duration:[0.03 TO 0.8]" in search["filter"]
    assert sounds["tick"].meta == {"role": "tick", "source": "freesound", "id": 3, "name": "sound 3", "user": "user3",
                                   "licence": "CC0", "url": "https://freesound.org/s/3/"}
    assert notes == [] and bed is None and sounds["tick"].gain_db != 0


def test_it_never_uses_a_sound_that_is_not_cc0_even_if_the_search_returns_one(freesound, tmp_path):
    freesound([result(1, license="http://creativecommons.org/licenses/by/4.0/"), result(2, license="")])
    sounds, _, notes = sfx.gather(["pop"], "", "seed", tmp_path)
    assert sounds["pop"].meta["source"] == "built-in" and notes == ["pop: no CC0 sound fits"]


@pytest.mark.parametrize("kwargs, note", [({"status": 429}, "Freesound said HTTP 429"),
                                          ({"audio_status": 404}, "the preview could not be downloaded")])
def test_a_failure_falls_back_to_the_built_in_sound_and_says_why(freesound, tmp_path, kwargs, note):
    freesound([result(1)], fit=True, **kwargs)
    sounds, _, notes = sfx.gather(["chime"], "", "seed", tmp_path)
    assert sounds["chime"].meta["source"] == "built-in" and notes == [f"chime: {note}"]


def test_a_network_error_never_fails_the_post(freesound, tmp_path, monkeypatch):
    freesound([result(1)], fit=True)
    def down(*args, **kwargs):
        raise sfx.requests.ConnectionError("no route")
    monkeypatch.setattr(sfx.requests, "get", down)
    sounds, bed, notes = sfx.gather(["tick", "pop"], "quiet room tone", "seed", tmp_path)
    assert {s.meta["source"] for s in sounds.values()} == {"built-in"} and bed is None and len(notes) == 3


def test_the_key_never_reaches_a_note_even_when_the_network_error_carries_it(freesound, tmp_path, monkeypatch):
    freesound([result(1)], fit=True)

    def down(url, timeout=None, params=None):
        raise sfx.requests.ConnectionError(f"Max retries exceeded with url: /apiv2/search/?query=pop&token=SECRETKEY&page_size=15 ({url})")
    monkeypatch.setattr(sfx.requests, "get", down)
    _, _, notes = sfx.gather(["pop"], "quiet room tone", "seed", tmp_path)
    assert notes and all("SECRETKEY" not in note and "token=[hidden]" in note for note in notes)


def test_it_gives_up_on_freesound_when_the_time_is_spent(freesound, tmp_path, monkeypatch):
    freesound([result(1)], fit=True)
    monkeypatch.setattr(sfx, "BUDGET", -5)
    sounds, _, notes = sfx.gather(["tick"], "", "seed", tmp_path)
    assert sounds["tick"].meta["source"] == "built-in" and notes == ["tick: out of time"]


def test_a_theme_adds_a_bed_that_is_a_long_cc0_sound(freesound, tmp_path):
    fake = freesound([result(7)], fit=True)
    sounds, bed, _ = sfx.gather(["tick"], "street ambience traffic", "seed", tmp_path)
    queries = [params["query"] for url, params in fake.calls if url.endswith("/search/")]
    assert "street ambience traffic" in queries and bed.meta["id"] == 7 and bed.meta["role"] == "bed"
    assert "duration:[8.0 TO 90.0]" in next(p["filter"] for u, p in fake.calls if p["query"] == "street ambience traffic")


def test_the_beat_and_the_impact_are_never_fetched(freesound, tmp_path):
    fake = freesound([result(1)], fit=True)
    sounds, _, _ = sfx.gather(["kick", "hat", "hit"], "", "seed", tmp_path)
    assert {s.meta["source"] for s in sounds.values()} == {"built-in"} and fake.calls == []


def test_the_same_post_picks_the_same_sounds(freesound, tmp_path):
    freesound([result(i, rating=4.0 + i / 10) for i in range(1, 6)], fit=True)
    (tmp_path / "a").mkdir()
    first, _, _ = sfx.gather(["pop"], "", "post-a", tmp_path / "a")
    again, _, _ = sfx.gather(["pop"], "", "post-a", tmp_path / "a")
    assert first["pop"].meta["id"] == again["pop"].meta["id"] and first["pop"].meta["id"] in (3, 4, 5)   # one of the top three


def loudness(path):
    """Integrated loudness in LUFS, as ffmpeg's EBU R128 meter reads it."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out.stderr)[-1])


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True)
    return float(json.loads(out.stdout)["format"]["duration"])


def test_the_mix_is_as_long_as_the_reel_audible_and_not_clipped(freesound, tmp_path):
    from suresilly import music
    freesound([result(5)], fit=True)
    tune = music.compose("joy", "mix-test", TL.total, tmp_path / "tune.wav")
    out = tmp_path / "mix.wav"
    used = sfx.build(TL, "“on my way” bas 5 min", "seed", tune, out, tmp_path)
    assert abs(probe(out) - TL.total) < 0.2 and used["theme"] == "phone"
    assert abs(loudness(out) + 15) < 2.5 and sfx.level_db(out) < -1                  # levelled to about -15 LUFS, with headroom left
    fetched = [m for m in used["sounds"] if m["role"] not in sfx.LOCAL_ONLY]
    assert {m["source"] for m in fetched} == {"freesound"} and "ring" in {m["role"] for m in fetched}   # the beat and the impact stay built in
    assert {m["role"] for m in used["sounds"] if m["source"] == "built-in"} == sfx.LOCAL_ONLY


def test_a_broken_mix_raises_so_the_caller_can_fall_back(tmp_path):
    found = sfx.events(TL, "")
    sounds, _, _ = sfx.gather([e.role for e in found], "", "seed", tmp_path)
    with pytest.raises(sfx.SoundError, match="could not mix"):
        sfx.mix(found, sounds, None, tmp_path / "missing.wav", TL.total, tmp_path / "x.wav")
