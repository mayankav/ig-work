"""The sound of the A or B Reel, picked for what is on screen.

Each moment of the Reel has a role: a tick for the count, a chime for the reveal, a page turn for the
cut. For each role we ask Freesound for a Creative Commons 0 sound that fits (CC0 needs no credit),
download its preview, level it, and mix it. A theme in the words (a phone, money, a group chat...)
adds one accent sound and a quiet background bed. The page's own music-box tune plays underneath
and ducks under every effect.

Anything that goes wrong (no key, no answer, no fitting sound, too slow) falls back to the built-in
sound for that role, so a post never waits on Freesound. What was used comes back as a list, to be
saved in post.json with the sound's id, author and licence. Setup is in docs/freesound.md.
"""
from __future__ import annotations

import math
import random
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import requests

from . import synth
from .llm import key

API = "https://freesound.org/apiv2"
LICENCE = "Creative Commons 0"        # the search filter
LICENCE_MARK = "publicdomain/zero"    # what a result's own licence link must contain
TIMEOUT = 10                          # seconds for one request
BUDGET = 45                           # seconds for all Freesound work in one run; after that, built-in sounds
MAX_BYTES = 3_000_000

# role -> (what to search for, shortest and longest clip in seconds, the peak the clip is levelled to, in dB)
ROLES = {
    "tick": ("clock tick", 0.03, 0.8, -10),
    "pop": ("bubble pop", 0.03, 0.6, -12),
    "click": ("ui click button", 0.02, 0.5, -14),
    "page_turn": ("page turn paper", 0.2, 1.5, -14),
    "whoosh": ("whoosh swish", 0.2, 1.5, -16),
    "chime": ("chime bell ding", 0.5, 3.0, -10),
    "boing": ("cartoon spring boing", 0.2, 1.5, -12),
    "notify": ("notification", 0.2, 2.0, -12),
    "riser": ("riser", 1.5, 6.0, -24),
    "ring": ("phone ringing", 0.8, 3.0, -14),
    "coin": ("coin clink", 0.3, 2.0, -12),
    "plate": ("plate clink", 0.2, 1.5, -12),
    "horn": ("car horn beep", 0.2, 1.5, -16),
    "key": ("typewriter key click", 0.02, 0.4, -20),
    "confetti": ("confetti", 0.1, 1.5, -10),
    "kick": ("", 0, 0, -14), "hat": ("", 0, 0, -26), "hit": ("", 0, 0, -6),
}
LOCAL_ONLY = {"kick", "hat", "hit"}  # the beat and the impact are always built in, so they match the tune and each other

# A theme: the words that call it up, one accent sound, when it plays, and a background bed to search for.
# The first theme whose words appear wins. "start" and "reveal" are moments on the Reel's clock.
THEMES = (
    ("phone", ("on my way", "call", "phone", "ring"), ("ring", "start", 0.05), "street ambience traffic"),
    ("money", ("pay", "upi", "₹", "bill", "split", "rupee"), ("coin", "reveal", 0.4), "cafe ambience chatter"),
    ("food", ("eat", "food", "plate", "pizza", "chai", "hungry", "order"), ("plate", "reveal", 0.4), "kitchen ambience"),
    ("travel", ("late", "reach", "station", "train", "bus", "cab", "drive", "traffic"), ("horn", "start", 0.05), "street ambience traffic"),
    ("chat", ("plan", "trip", "group", "chat", "reply", "seen", "text", "message"), ("notify", "start", 0.1), "quiet room tone"),
)
BED = (8.0, 90.0, -30)  # shortest and longest bed in seconds, and the loudness (mean, dB) it is levelled to


class SoundError(RuntimeError):
    pass


def _clean(error: Exception) -> str:
    """An error as a short note. A network error carries the request address, and the address carries the key."""
    return re.sub(r"(token=)[^&\s'\")]+", r"\1[hidden]", str(error))[:200]


@dataclass
class Sound:
    role: str
    path: Path
    seconds: float
    gain_db: float
    meta: dict


@dataclass
class Event:
    at: float
    role: str
    until: float | None = None  # a sound that must end on a beat (the riser ends at the reveal)
    db: float = 0.0             # louder or softer than the sound's own level


def theme_of(text: str) -> str:
    """The first theme whose words appear in `text`, or "" when none does."""
    low = text.lower()
    for name, words, _, _ in THEMES:
        if any(re.search(rf"(?<![a-z]){re.escape(word)}", low) for word in words):
            return name
    return ""


def events(tl, theme: str) -> list[Event]:
    """What happens when, from the Reel's clock `tl` (q, count, reveal, send, ask, the word times and the beat).

    Words land with a key click, the count ticks and builds, the beat drops out just before the reveal
    (a breath), and the reveal arrives with an impact, a chime, a spring and a party popper."""
    found = [Event(0.02, "pop"), Event(tl.q, "page_turn"), Event(tl.q + 0.3, "pop"), Event(tl.q + 0.8, "pop"), Event(tl.q + 1.3, "pop"),
             *[Event(at, "key", db=-4) for at in tl.hook_words],
             *[Event(at, "tick") for at in tl.count], Event(tl.count[0] - 0.1, "riser", until=tl.reveal - 0.1),
             Event(tl.reveal, "hit"), Event(tl.reveal, "chime"), Event(tl.reveal + 0.04, "boing"), Event(tl.reveal + 0.05, "confetti"),
             Event(tl.send, "whoosh"), Event(tl.send + 0.05, "notify"), Event(tl.send + 0.15, "pop"),
             *[Event(at, "key", db=-4) for at in tl.send_words], Event(tl.ask, "click")]
    at = 0.0                                              # the beat runs from the first frame
    while at < tl.total - 1.0:
        if at < tl.reveal - 0.45 or at >= tl.reveal + 0.25:  # a breath before the reveal
            louder = 0.0 if at >= tl.reveal else (-7.0 if at < tl.q else -4.0)  # softest in the hook, strongest after the drop
            found += [Event(at, "kick", db=louder), Event(at + tl.beat / 2, "hat", db=louder)]
        at += tl.beat
    for name, _, (role, anchor, offset), _ in THEMES:
        if name == theme:
            found.append(Event((tl.reveal if anchor == "reveal" else 0.0) + offset, role))
    return sorted(found, key=lambda event: event.at)


def bed_words(theme: str) -> str:
    return next((words for name, _, _, words in THEMES if name == theme), "")


# ── measuring ──────────────────────────────────────────────────────────────

def probe_seconds(path: Path) -> float:
    done = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True)
    try:
        return float(done.stdout.strip())
    except ValueError:
        return 0.0


def level_db(path: Path, mean: bool = False) -> float:
    """The clip's loudest point (or its average, for a bed) in dB, as ffmpeg reads it."""
    done = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True)
    found = re.search(r"%s_volume:\s*(-?[\d.]+) dB" % ("mean" if mean else "max"), done.stderr)
    return float(found.group(1)) if found else -20.0


def _gain(path: Path, target: float, mean: bool = False) -> float:
    return max(-40.0, min(24.0, target - level_db(path, mean)))


# ── Freesound ──────────────────────────────────────────────────────────────

def _usable(result: dict, low: float, high: float) -> bool:
    return (LICENCE_MARK in str(result.get("license", "")) and low <= float(result.get("duration") or 0) <= high
            and bool((result.get("previews") or {}).get("preview-hq-mp3")))


def _fetch(role: str, words: str, low: float, high: float, token: str, seed: str, folder: Path, deadline: float,
           target: float, mean: bool = False) -> Sound:
    """One CC0 sound from Freesound, downloaded and levelled. Raises SoundError when it cannot."""
    left = lambda: min(TIMEOUT, deadline - time.monotonic())  # noqa: E731
    if left() <= 1:
        raise SoundError("out of time")
    reply = requests.get(f"{API}/search/", timeout=left(), params={
        "query": words, "filter": f'license:"{LICENCE}" duration:[{low} TO {high}]', "page_size": 15, "token": token,
        "fields": "id,name,username,license,duration,previews,avg_rating,num_ratings"})
    if reply.status_code != 200:
        raise SoundError(f"Freesound said HTTP {reply.status_code}")
    found = [r for r in reply.json().get("results", []) if _usable(r, low, high)]
    if not found:
        raise SoundError("no CC0 sound fits")
    found.sort(key=lambda r: (r.get("avg_rating") or 0) * math.log1p(r.get("num_ratings") or 0), reverse=True)
    pick = random.Random(f"{seed}-{role}").choice(found[:3])
    if left() <= 1:
        raise SoundError("out of time")
    audio = requests.get(pick["previews"]["preview-hq-mp3"], timeout=left())
    if audio.status_code != 200 or not 0 < len(audio.content) <= MAX_BYTES:
        raise SoundError("the preview could not be downloaded")
    path = folder / f"{role}-{pick['id']}.mp3"
    path.write_bytes(audio.content)
    seconds = probe_seconds(path)
    if seconds <= 0:
        raise SoundError("the preview is not audio")
    return Sound(role, path, seconds, _gain(path, target, mean), {
        "role": role, "source": "freesound", "id": pick["id"], "name": pick.get("name", ""), "user": pick.get("username", ""),
        "licence": "CC0", "url": f"https://freesound.org/s/{pick['id']}/"})


def _builtin(role: str, folder: Path) -> Sound:
    path, seconds = synth.write(role, folder / f"{role}.wav")
    return Sound(role, path, seconds, ROLES[role][3] - level_db(path), {"role": role, "source": "built-in"})


def gather(roles: list[str], bed: str, seed: str, folder: Path) -> tuple[dict[str, Sound], Sound | None, list[str]]:
    """A sound for every role, and a bed when there is one to find. Returns (sounds, bed, notes about what fell back)."""
    token = key("FREESOUND_API_KEY")
    deadline = time.monotonic() + BUDGET
    notes: list[str] = []
    wanted = [(role, *ROLES[role]) for role in dict.fromkeys(roles)]

    def one(item) -> tuple[str, Sound]:
        role, words, low, high, target = item
        if token and role not in LOCAL_ONLY:
            try:
                return role, _fetch(role, words, low, high, token, seed, folder, deadline, target)
            except Exception as error:  # a sound that fails is never worth a failed post
                notes.append(f"{role}: {_clean(error)}")
        return role, _builtin(role, folder)

    def the_bed() -> Sound | None:
        if not (token and bed):
            return None
        try:
            return _fetch("bed", bed, BED[0], BED[1], token, seed, folder, deadline, BED[2], mean=True)
        except Exception as error:
            notes.append(f"bed: {_clean(error)}")
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        waiting = pool.submit(the_bed)
        sounds = dict(pool.map(one, wanted))
        return sounds, waiting.result(), notes


# ── mixing ─────────────────────────────────────────────────────────────────

_FORMAT = "aresample=44100,aformat=channel_layouts=stereo"


def mix(found: list[Event], sounds: dict[str, Sound], bed: Sound | None, tune: Path, total: float, target: Path) -> None:
    """The tune and the bed underneath, every effect on its beat, the tune ducking under each effect, then levelled."""
    inputs, chains = [str(tune)], [f"[0:a]{_FORMAT},volume=0.55[tune]"]
    music = "[tune]"
    if bed:
        inputs.append(str(bed.path))
        chains.append(f"[1:a]{_FORMAT},aloop=loop=-1:size=2000000000,atrim=0:{total:.2f},afade=in:d=1,"
                      f"afade=out:st={max(0.0, total - 1.5):.2f}:d=1.5,volume={bed.gain_db:.1f}dB[bed]")
        chains.append("[tune][bed]amix=inputs=2:normalize=0:duration=first[music]")
        music = "[music]"
    labels = []
    for event in found:
        sound = sounds[event.role]
        start, skip, length = event.at, 0.0, sound.seconds
        if event.until is not None:  # end on the beat: keep the last stretch of the sound
            length = min(sound.seconds, event.until - event.at)
            skip, start = sound.seconds - length, event.until - length
        index = len(inputs)
        inputs.append(str(sound.path))
        label = f"e{index}"
        chains.append(f"[{index}:a]{_FORMAT},atrim=start={skip:.3f}:duration={length:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=out:st={max(0.0, length - 0.08):.3f}:d=0.08,volume={sound.gain_db + event.db:.1f}dB,"
                      f"adelay={max(0, int(start * 1000))}:all=1[{label}]")
        labels.append(f"[{label}]")
    # pad the effects to the Reel's full length: the ducking step ends with its shorter input, which would cut the tune short
    chains.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,apad=whole_dur={total:.2f}[fx]")
    chains.append("[fx]asplit=2[fxa][fxb]")
    chains.append(f"{music}[fxa]sidechaincompress=threshold=0.02:ratio=8:attack=5:release=300[ducked]")
    chains.append("[ducked][fxb]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-15:TP=-2.5:LRA=7[out]")
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for path in inputs:
        command += ["-i", path]
    command += ["-filter_complex", ";".join(chains), "-map", "[out]", "-t", f"{total:.2f}", "-ar", "44100", "-c:a", "pcm_s16le", str(target)]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode != 0 or not target.is_file():
        raise SoundError(f"ffmpeg could not mix the sound: {done.stderr.strip()[-300:]}")


def build(tl, words: str, seed: str, tune: Path, target: Path, folder: Path) -> dict:
    """Make the whole soundtrack at `target`. Returns what was used: {"theme", "sounds": [...], "notes": [...]}."""
    theme = theme_of(words)
    found = events(tl, theme)
    sounds, bed, notes = gather([event.role for event in found], bed_words(theme), seed, folder)
    mix(found, sounds, bed, tune, tl.total, target)
    used = [sound.meta for sound in sounds.values()] + ([bed.meta] if bed else [])
    return {"theme": theme or "none", "sounds": used, "notes": notes}
