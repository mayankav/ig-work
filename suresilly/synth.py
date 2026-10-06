"""Built-in sound effects. The fallback when Freesound has no key, no answer, or no fitting sound.

Every sound here is made in code, so it is ours and always available. Each function takes a numpy
random generator and returns mono float samples at 44.1 kHz with a peak near 1.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100


def _time(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _lowpass(x: np.ndarray, a: float) -> np.ndarray:
    """One-pole low-pass: each sample moves a fraction `a` of the way to the input."""
    kernel = a * (1 - a) ** np.arange(int(8 / a))
    return np.convolve(x, kernel)[: len(x)]


def _glide(frequency: np.ndarray) -> np.ndarray:
    return np.sin(2 * np.pi * np.cumsum(frequency) / SR)


def _normal(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    top = float(np.max(np.abs(x))) or 1.0
    return x * (peak / top)


def tick(rng) -> np.ndarray:
    """A clock tick: a bright click and a short low knock."""
    t = _time(0.12)
    noise = rng.uniform(-1, 1, len(t))
    click = (noise - _lowpass(noise, 0.25)) * np.exp(-t * 90) * (t < 0.02)
    return _normal(0.55 * click + 0.45 * np.sin(2 * np.pi * 1700 * t) * np.exp(-t * 70)
                   + 0.35 * np.sin(2 * np.pi * 110 * t) * np.exp(-t * 45))


def pop(rng, pitch: float = 520) -> np.ndarray:
    """A soft bubble pop: a quick downward glide."""
    t = _time(0.12)
    return _normal(_glide(pitch * (1 + 0.9 * np.exp(-t * 55))) * np.exp(-t * 38) * np.minimum(1, t / 0.002))


def click(rng) -> np.ndarray:
    t = _time(0.05)
    return _normal(0.4 * rng.uniform(-1, 1, len(t)) * np.exp(-t * 220) + 0.3 * np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 160))


def page_turn(rng) -> np.ndarray:
    """Paper: band-limited noise that swells and falls, with a few crackles."""
    t = _time(0.34)
    noise = rng.uniform(-1, 1, len(t))
    band = _lowpass(noise, 0.55) - _lowpass(noise, 0.06)
    swell = np.sin(np.pi * (t / t[-1]) ** 0.7) ** 2
    crackle = rng.uniform(-1, 1, len(t)) * (rng.random(len(t)) < 0.004) * np.exp(-t * 6) * 0.5
    return _normal(band * swell + crackle)


def whoosh(rng) -> np.ndarray:
    """Air moving past: noise that starts dark and brightens, then fades."""
    t = _time(0.4)
    x = t / t[-1]
    noise = rng.uniform(-1, 1, len(t))
    return _normal((_lowpass(noise, 0.04) * (1 - x) + _lowpass(noise, 0.4) * x) * np.sin(np.pi * x) ** 1.5)


def _bell(frequency: float, seconds: float) -> np.ndarray:
    t = _time(seconds)
    return sum(c * np.sin(2 * np.pi * frequency * r * t) * np.exp(-t * k) for c, r, k in ((1, 1, 6), (0.45, 2.76, 9), (0.2, 5.4, 14)))


def chime(rng, base: float = 784) -> np.ndarray:
    """A small bell, then a higher second note a tenth of a second later."""
    first, second = _bell(base, 0.9), _bell(base * 1.5, 1.1)
    out = np.zeros(int(1.2 * SR))
    out[: len(first)] += first
    out[int(0.1 * SR): int(0.1 * SR) + len(second)] += second
    return _normal(out)


def boing(rng) -> np.ndarray:
    """A cartoon spring."""
    t = _time(0.45)
    return _normal(_glide(300 + 140 * np.sin(2 * np.pi * 7 * t) * np.exp(-t * 4) + 120 * np.exp(-t * 9)) * np.exp(-t * 6))


def notify(rng) -> np.ndarray:
    """A message ping: two quick notes."""
    out = np.zeros(int(0.4 * SR))
    for start, frequency in ((0.0, 988), (0.09, 1318)):
        t = _time(0.3)
        note = np.sin(2 * np.pi * frequency * t) * np.exp(-t * 12) * np.minimum(1, t / 0.003)
        out[int(start * SR): int(start * SR) + len(note)] += note
    return _normal(out)


def ring(rng) -> np.ndarray:
    """A phone ringing: two bursts of a two-tone buzz."""
    out = np.zeros(int(1.2 * SR))
    t = _time(0.38)
    burst = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 20 * t))
    burst *= np.minimum(1, t / 0.01) * np.minimum(1, (0.38 - t) / 0.02)
    for start in (0.0, 0.55):
        out[int(start * SR): int(start * SR) + len(burst)] += burst
    return _normal(out)


def coin(rng) -> np.ndarray:
    """A coin clink: two high metallic pings."""
    out = np.zeros(int(0.7 * SR))
    t = _time(0.5)
    for start, frequency in ((0.0, 2093), (0.07, 3136)):
        ping = (np.sin(2 * np.pi * frequency * t) + 0.4 * np.sin(2 * np.pi * frequency * 2.76 * t)) * np.exp(-t * 11)
        out[int(start * SR): int(start * SR) + len(ping)] += ping
    return _normal(out)


def plate(rng) -> np.ndarray:
    """A plate clink: the coin's pings, lower and shorter."""
    t = _time(0.4)
    return _normal((np.sin(2 * np.pi * 1480 * t) + 0.5 * np.sin(2 * np.pi * 1480 * 2.4 * t)) * np.exp(-t * 16))


def horn(rng) -> np.ndarray:
    """A short two-tone horn."""
    t = _time(0.45)
    return _normal((np.sin(2 * np.pi * 420 * t) + np.sin(2 * np.pi * 530 * t)) * np.minimum(1, t / 0.02) * np.minimum(1, (0.45 - t) / 0.05))


def riser(rng, seconds: float = 2.4) -> np.ndarray:
    """Tension while a count runs: a rising tone that gets louder."""
    t = _time(seconds)
    x = t / t[-1]
    return _normal(_glide(180 + 520 * x * x) * (0.05 + 0.2 * x) * np.minimum(1, t / 0.1))


def kick(rng) -> np.ndarray:
    """A soft kick drum: a sine that falls from a thump to a low note."""
    t = _time(0.28)
    click = rng.uniform(-1, 1, len(t)) * np.exp(-t * 300) * (t < 0.01)
    return _normal(_glide(45 + 110 * np.exp(-t * 28)) * np.exp(-t * 11) * np.minimum(1, t / 0.002) + 0.3 * click)


def hat(rng) -> np.ndarray:
    """A closed hi-hat: a very short burst of bright noise."""
    t = _time(0.06)
    noise = rng.uniform(-1, 1, len(t))
    return _normal((noise - _lowpass(noise, 0.35)) * np.exp(-t * 70))


def hit(rng) -> np.ndarray:
    """An impact for the reveal: a deep drop with a burst of air on top."""
    t = _time(0.7)
    noise = rng.uniform(-1, 1, len(t))
    return _normal(_glide(38 + 90 * np.exp(-t * 10)) * np.exp(-t * 4.5) + 0.4 * (noise - _lowpass(noise, 0.1)) * np.exp(-t * 30))


def confetti(rng) -> np.ndarray:
    """A party popper: a crack, then a rustle."""
    t = _time(0.4)
    noise = rng.uniform(-1, 1, len(t))
    crack = (noise - _lowpass(noise, 0.3)) * np.exp(-t * 60)
    rustle = (_lowpass(noise, 0.5) - _lowpass(noise, 0.08)) * np.exp(-t * 9) * np.minimum(1, t / 0.03)
    return _normal(1.2 * crack + 0.6 * rustle)


def key(rng) -> np.ndarray:
    """A typewriter key: a dry, short tick for each word that lands."""
    t = _time(0.05)
    return _normal(0.5 * rng.uniform(-1, 1, len(t)) * np.exp(-t * 300) + 0.4 * np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 250))


MAKERS = {"tick": tick, "pop": pop, "click": click, "page_turn": page_turn, "whoosh": whoosh, "chime": chime,
          "kick": kick, "hat": hat, "hit": hit, "confetti": confetti, "key": key,
          "boing": boing, "notify": notify, "ring": ring, "coin": coin, "plate": plate, "horn": horn, "riser": riser}


def write(role: str, path: Path, seed: int = 7) -> tuple[Path, float]:
    """Make one sound and save it as a 16-bit wav. Returns (path, seconds)."""
    samples = MAKERS[role](np.random.default_rng(seed))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes((np.clip(samples, -1, 1) * 32000).astype("<i2").tobytes())
    return path, len(samples) / SR
