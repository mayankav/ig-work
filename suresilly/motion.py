"""Motion for the A or B Reel: easing, camera shake, confetti, and the soft shapes behind the scene.

Everything is a pure function of time, so a frame can be drawn on its own and the same Reel always
looks the same. Nothing here knows about the layout: it only moves things that were already placed.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter


def clamp(x: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, x))


def progress(t: float, start: float, seconds: float) -> float:
    """0 before `start`, 1 after `start + seconds`, and a straight line between."""
    return clamp((t - start) / seconds)


def out_back(x: float, overshoot: float = 1.70158) -> float:
    """Fast, then a little past the end, then settling: the pop of something landing."""
    x = clamp(x)
    return 1 + (overshoot + 1) * (x - 1) ** 3 + overshoot * (x - 1) ** 2


def out_cubic(x: float) -> float:
    return 1 - (1 - clamp(x)) ** 3


def in_out(x: float) -> float:
    x = clamp(x)
    return 3 * x * x - 2 * x ** 3


def shake(t: float, start: float, seconds: float, amount: float) -> tuple[float, float]:
    """A hit that dies away: a jolt of `amount` pixels that fades to nothing over `seconds`."""
    if not start <= t <= start + seconds:
        return 0.0, 0.0
    fade = (1 - (t - start) / seconds) ** 2
    return amount * fade * math.sin(t * 93.0 + 1.3), amount * fade * math.sin(t * 71.0 + 4.1)


def tremble(t: float, amount: float) -> tuple[float, float]:
    """A steady small shake, for the tension of a count."""
    return amount * math.sin(t * 61.0), amount * math.sin(t * 47.0 + 2.0)


def beat_pulse(t: float, beat: float, start: float, stop: float) -> float:
    """1 on each beat between `start` and `stop`, dying away before the next."""
    if not start <= t < stop:
        return 0.0
    return math.exp(-((t - start) % beat) * 9)


_orb_cache: dict[int, Image.Image] = {}


def orb(radius: int) -> Image.Image:
    """A soft cream disc that fades at the edge, for the slow shapes drifting behind a scene."""
    if radius not in _orb_cache:
        layer = Image.new("RGBA", (radius * 4, radius * 4), (255, 246, 230, 0))
        ImageDraw.Draw(layer).ellipse((radius, radius, radius * 3, radius * 3), fill=(255, 246, 230, 255))
        layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.35))
        alpha = layer.getchannel("A").point(lambda v: int(v * 0.16))
        layer.putalpha(alpha)
        _orb_cache[radius] = layer
    return _orb_cache[radius]


def drift(t: float, which: int) -> tuple[float, float]:
    """Where the `which`-th orb is at time t: slow, wide, different loops, so it never repeats within a Reel."""
    return (540 + 430 * math.sin(2 * math.pi * t / (9.0 + 2 * which) + which * 2.1),
            960 + 620 * math.cos(2 * math.pi * t / (11.0 + 3 * which) + which * 1.3))


COLOURS = ((255, 246, 230), (255, 211, 77), (46, 171, 98), (46, 40, 34), (255, 140, 105))
GRAVITY = 1500.0


class Confetti:
    """A burst of paper bits from one point: thrown up and out, tumbling, then falling away."""

    def __init__(self, origin: tuple[float, float], start: float, count: int = 70, seed: int = 3,
                 angles: tuple[float, float] = (-155, -25), speeds: tuple[float, float] = (450, 1150)):
        rng = random.Random(seed)
        self.origin, self.start, self.bits = origin, start, []
        for _ in range(count):
            angle = math.radians(rng.uniform(*angles))
            speed = rng.uniform(*speeds)
            self.bits.append({"vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed, "spin": rng.uniform(-9, 9),
                              "phase": rng.uniform(0, 6.28), "size": (rng.randint(18, 34), rng.randint(10, 18)),
                              "colour": rng.choice(COLOURS), "life": rng.uniform(1.6, 2.6)})
        self._sprites: dict[tuple, Image.Image] = {}

    def draw(self, image: Image.Image, t: float) -> None:
        age = t - self.start
        if age < 0:
            return
        for bit in self.bits:
            if age > bit["life"]:
                continue
            x = self.origin[0] + bit["vx"] * age
            y = self.origin[1] + bit["vy"] * age + 0.5 * GRAVITY * age * age
            if not -50 < x < image.width + 50 or y > image.height + 50:
                continue
            key = (bit["colour"], bit["size"])
            sprite = self._sprites.setdefault(key, Image.new("RGBA", bit["size"], bit["colour"] + (255,)))
            # a bit seen edge-on is thin: squash it with the spin, so it flutters instead of just turning
            flat = abs(math.cos(bit["phase"] + bit["spin"] * age * 1.7))
            sheet = sprite.resize((bit["size"][0], max(2, int(bit["size"][1] * (0.25 + 0.75 * flat)))))
            turned = sheet.rotate(math.degrees(bit["phase"] + bit["spin"] * age), expand=True, resample=Image.BILINEAR)
            fade = min(1.0, (bit["life"] - age) / 0.4)
            if fade < 1.0:
                turned.putalpha(turned.getchannel("A").point(lambda v: int(v * fade)))
            image.alpha_composite(turned, (int(x - turned.width / 2), int(y - turned.height / 2)))
