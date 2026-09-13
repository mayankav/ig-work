"""A short tune for each Reel, composed here: a music box over a soft pad.

It is nobody else's music, so Instagram has nothing to mute or flag, and every
Reel gets a tune of its own. The mood sets the speed and the chords; the seed
sets the key and the melody, so the same post always gets the same tune.
"""
from __future__ import annotations

import random
import wave
from pathlib import Path

import numpy as np

RATE = 44100
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)

# mood: (beats a minute, scale, four chords as scale degrees counted from 0)
MOODS = {
    "warm": (72, MAJOR, (0, 5, 3, 4)),     # I vi IV V
    "calm": (64, MAJOR, (0, 3, 0, 4)),     # I IV I V
    "wistful": (62, MAJOR, (5, 3, 0, 4)),  # vi IV I V
    "sad": (58, MINOR, (0, 5, 2, 6)),      # i VI III VII
    "tired": (56, MAJOR, (3, 0, 3, 4)),    # IV I IV V
    "joy": (92, MAJOR, (0, 4, 5, 3)),      # I V vi IV
    "wise": (68, MAJOR, (0, 2, 3, 0)),     # I iii IV I
}
MOODS["invite"] = MOODS["warm"]

# One bar of melody, in beats. The last bar of a tune is always (2, 2).
RHYTHMS = ((1, 1, 1, 1), (1.5, .5, 1, 1), (1, .5, .5, 2), (2, 1, 1), (.5, .5, 1, 2), (1, 1, 2))
# A music-box tine: a clear fundamental, a few overtones, slightly out of tune at the top.
TINE = ((1, 1.0), (2, .28), (3, .1), (4.2, .06), (5.4, .03))
LOW, HIGH = 7, 16  # the melody stays between the tonic and the fifth, one octave up


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _time(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _tine(hz: float) -> np.ndarray:
    t = _time(2.4)
    tone = sum(level * np.exp(-t * (1.6 + 1.2 * k)) * np.sin(2 * np.pi * hz * ratio * t)
               for k, (ratio, level) in enumerate(TINE))
    return tone * np.minimum(1, t / .003)


def _pluck(hz: float) -> np.ndarray:
    t = _time(2.0)
    return (np.sin(2 * np.pi * hz * t) + .25 * np.sin(4 * np.pi * hz * t)) * np.exp(-2 * t) * np.minimum(1, t / .005)


def _pad(hz: float, seconds: float) -> np.ndarray:
    t = _time(seconds)
    tone = .5 * (np.sin(2 * np.pi * hz * t) + np.sin(2 * np.pi * hz * 1.004 * t)) + .15 * np.sin(4 * np.pi * hz * t)
    return tone * np.minimum(1, t / .5) * np.minimum(1, (seconds - t) / .6)


def _room(dry: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A small warm room: the dry sound convolved with two seconds of fading, softened noise."""
    t = _time(2.0)
    impulse = np.convolve(rng.standard_normal(len(t)) * np.exp(-t / .45), np.ones(8) / 8, mode="same")
    size = 1 << (len(dry) + len(impulse)).bit_length()
    wet = np.fft.irfft(np.fft.rfft(dry, size) * np.fft.rfft(impulse, size), size)[:len(dry)]
    return dry + .5 * wet * np.sqrt(np.sum(dry ** 2) / max(np.sum(wet ** 2), 1e-12))


def compose(mood: str, seed: str, seconds: float, target: Path) -> Path:
    """Write a stereo WAV of `seconds` for `mood` to target."""
    tempo, scale, chords = MOODS.get(mood, MOODS["calm"])
    rng = random.Random(seed)
    root = rng.choice((58, 60, 62, 63, 65))  # B♭, C, D, E♭ or F
    beat = 60 / tempo
    bars = int(np.ceil((seconds + 1) / (4 * beat)))
    song = np.zeros(int((bars * 4 * beat + 3) * RATE))

    def midi(degree: int) -> int:
        return root + 12 * (degree // 7) + scale[degree % 7]

    def place(sound: np.ndarray, at: float) -> None:
        start = int(at * RATE)
        song[start:start + len(sound)] += sound[:len(song) - start]

    melody = 9
    for number in range(bars):
        chord, start = chords[number % 4], number * 4 * beat
        for degree in (chord, chord + 2, chord + 4):
            place(.07 * _pad(_hz(midi(degree)), 4 * beat + .6), start)
        place(.3 * _pluck(_hz(midi(chord) - 12)), start)
        rhythm = (2, 2) if number == bars - 1 else rng.choice(RHYTHMS)
        position = 0.0
        for length in rhythm:
            if position in (0, 2):  # strong beats land on a note of the chord
                tones = [d for d in range(LOW, HIGH + 1) if (d - chord) % 7 in (0, 2, 4)]
                melody = min(tones, key=lambda d: (abs(d - melody), rng.random()))
            else:
                step = rng.choice((1, 1, 1, 2)) * (1 if rng.random() < (HIGH - melody) / (HIGH - LOW) else -1)
                melody = max(LOW, min(HIGH, melody + step))
            if position in (0, 2) or rng.random() > .1:  # now and then a weak beat rests
                place((.5 if position in (0, 2) else .38) * _tine(_hz(midi(melody))), start + position * beat)
            position += length

    t = _time(seconds)
    song = song[:len(t)]
    noise = np.random.default_rng(rng.randrange(1 << 32))
    left, right = _room(song, noise), _room(song, noise)  # two rooms, so the ears hear it wide
    fade = np.minimum(1, np.minimum(t / .05, (seconds - t) / 1.8))
    stereo = np.stack([left, right], axis=1) * fade[:, None]
    stereo *= .8 / max(np.abs(stereo).max(), 1e-9)
    with wave.open(str(target), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((stereo * 32767).astype("<i2").tobytes())
    return target
