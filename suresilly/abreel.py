"""The A or B Reel: a phrase one kind of friend says, "which friend are you?" with a countdown,
a reveal where the donkey is A, and one line to send to the friend who says it.

Layout. Drawn with Pillow on one spacing system, so every element lines up:
  - a 1080x1920 canvas; Instagram's own buttons and caption cover the edges, so everything rests inside
    SAFE (left 60, top 220, right 950, bottom 1490), in one content column (100 to 940);
  - five text sizes, four gaps (all multiples of 8), one card, one badge;
  - each screen's group is centred in the safe area, a little high, and the donkey is centred by its
    body, not its box (the tail pulls the box off-centre);
  - line breaks are balanced, so no line holds one lonely word.

Pace. Timing follows reading speed (READ_WPS): raise it to make the Reel faster, lower it to slow it down.
Reading time is not dead time: while a viewer reads, something is always moving. Words land one at a time,
cards slide in, the background drifts, a 120 bpm beat runs under it all, and every
key moment sits on the beat. The count tightens (a ring, a tremble, a darkening edge), the beat drops out
for a breath, and the reveal arrives with a flash, a shake, a punch-in, a spring and confetti. The donkey itself never moves: flat cut-outs look cheap when they tilt, bob or squash, so it only appears.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import ASSETS, motion, music, sfx
from .render import RenderError, smart_quotes

W, H, FPS = 1080, 1920, 30
SAFE = (60, 220, 950, 1490)                       # left, top, right, bottom
SAFE_H = SAFE[3] - SAFE[1]
COL_L, COL_R = 100, 940                           # 100 px left margin, 140 on the right (the button strip)
COLW, CX = COL_R - COL_L, (COL_L + COL_R) // 2
BIAS = -32                                        # a group sits a little above true centre: the eye reads true centre as low
GAP_S, GAP_M, GAP_L, GAP_XL = 32, 48, 64, 96      # the only gaps
DISPLAY, TITLE, HEADING, BODY, CAPTION = 128, 88, 72, 56, 44  # the only text sizes
RADIUS, PAD, BADGE, DISC = 40, 40, 88, 224
RED, TEAL = (194, 66, 50, 255), (28, 86, 94, 255)
CREAM, INK, GOLD = (255, 246, 230, 255), (46, 40, 34, 255), (255, 211, 77, 255)
QUESTION, ASK = "which friend\nare you?", "A or B? tell me below"
MOOD = "hype"                                    # 120 bpm: bright, and fast enough to carry a beat
BEAT = 60 / music.MOODS[MOOD][0]                  # seconds a beat; every key moment is on this grid
READ_WPS = 2.2                                    # words a second a viewer can read on screen
COUNT_STEP = 1.0                                  # seconds for each of 3, 2, 1 (two beats)
TRANSITION = 0.3                                  # seconds a screen takes to slide out
FILE = "reel.mp4"


# ── time ───────────────────────────────────────────────────────────────────

def grid(seconds: float) -> float:
    """Round up to the next beat, so the screens change on the beat."""
    return round(BEAT * math.ceil(seconds / BEAT - 1e-6), 2)


@dataclass
class Timeline:
    q: float                    # the question appears
    count: tuple[float, float, float]
    reveal: float
    send: float
    ask: float
    total: float
    hook_words: tuple[float, ...] = ()   # when each word of the hook lands
    send_words: tuple[float, ...] = ()   # when each word of the send line lands
    beat: float = BEAT


def timeline(slide: dict) -> Timeline:
    """When each screen starts, from how many words there are to read. Every start is on the beat."""
    n = lambda text: len(text.replace("\n", " ").split())  # noqa: E731
    q = grid(max(2.6, 1.0 + n(slide["hook"]) / READ_WPS))
    length = grid(max(1.0 + 1.5 + 3 * COUNT_STEP, 0.5 + (n(QUESTION) + n(slide["a"]) + n(slide["b"])) / READ_WPS))
    reveal = round(q + length, 2)
    count = tuple(round(reveal - 3 * COUNT_STEP + i * COUNT_STEP, 2) for i in range(3))
    send = round(reveal + grid(max(2.4, 1.4 + n(slide["win"]) / READ_WPS)), 2)
    ask = round(send + grid(0.8 + n(slide["send"]) / READ_WPS), 2)
    total = round(ask + grid(max(2.0, 0.6 + n(ASK) / READ_WPS)), 2)
    return Timeline(q, count, reveal, send, ask, total,
                    hook_words=tuple(round(i * 0.22, 2) for i in range(n(slide["hook"]))),
                    send_words=tuple(round(send + 0.35 + i * 0.32, 2) for i in range(n(slide["send"]))))


# ── type and parts ─────────────────────────────────────────────────────────

_fonts: dict[int, ImageFont.FreeTypeFont] = {}
_probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))


def font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _fonts:
        face = ImageFont.truetype(str(ASSETS / "fonts" / "Fraunces-Variable.ttf"), size)
        try:
            face.set_variation_by_axes([max(9, min(144, int(size * 0.6))), 640, 100, 0])  # optical size, weight, softness, wonk
        except Exception:  # an older FreeType: the font's own default weight
            pass
        _fonts[size] = face
    return _fonts[size]


def _height_of(size: int, glyph: str) -> int:
    return -font(size).getbbox(glyph, anchor="ls")[1]


def wrap(text: str, size: int, width: int, balance: bool = False) -> list[str]:
    """Greedy wrap. With balance, narrow the measure until the line count would grow, so no line holds one word."""
    face = font(size)

    def greedy(paragraph: str, limit: float) -> list[str]:
        lines, current = [], ""
        for word in paragraph.split():
            attempt = (current + " " + word).strip()
            if _probe.textlength(attempt, font=face) <= limit or not current:
                current = attempt
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    out: list[str] = []
    for paragraph in text.split("\n"):
        lines = greedy(paragraph, width)
        if balance and len(lines) > 1:
            limit = width
            while limit > 80 and len(greedy(paragraph, limit - 8)) == len(lines):
                limit -= 8
            lines = greedy(paragraph, limit)
        out += lines
    return out


def text_block(text: str, size: int, fill=CREAM, width: int = COLW, leading: float = 1.15, align: str = "center") -> Image.Image:
    """A tight text layer: its height is exactly lines x line height, each line centred on its box by x-height."""
    lines = wrap(text, size, width, balance=(align == "center"))
    step = round(size * leading)
    layer = Image.new("RGBA", (width, step * len(lines)), (0, 0, 0, 0))
    draw, x_height = ImageDraw.Draw(layer), _height_of(size, "x")
    for number, line in enumerate(lines):
        base = number * step + step / 2 + x_height / 2
        if align == "center":
            draw.text((width / 2, base), line, font=font(size), fill=fill, anchor="ms")
        else:
            draw.text((0, base), line, font=font(size), fill=fill, anchor="ls")
    return layer


def word_tiles(text: str, size: int, fill=CREAM, width: int = COLW, leading: float = 1.15) -> tuple[list, list]:
    """The same block as text_block, one tile a word, so words can land one at a time.

    Returns (tiles, bars): tiles are (image, centre x, centre y) relative to the block's top left; bars are
    (left, right, y) for each quoted stretch, where an underline can be drawn."""
    lines, step, face = wrap(text, size, width, balance=True), round(size * leading), font(size)
    x_height, tiles, bars = _height_of(size, "x"), [], []
    open_from: float | None = None
    for number, line in enumerate(lines):
        left = (width - _probe.textlength(line, font=face)) / 2
        base = number * step + step / 2 + x_height / 2
        if open_from is not None:
            open_from = left                                   # a quote carried over from the line above
        position = 0
        for word in line.split(" "):
            start = left + _probe.textlength(line[:position], font=face)
            length = _probe.textlength(word, font=face)
            tile = Image.new("RGBA", (int(length) + 10, step), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((5, step / 2 + x_height / 2), word, font=face, fill=fill, anchor="ls")
            tiles.append((tile, start + length / 2, number * step + step / 2))
            if "“" in word:
                open_from = start
            if "”" in word and open_from is not None:
                bars.append((open_from, start + length, base + 14))
                open_from = None
            position += len(word) + 1
        if open_from is not None and number == len(lines) - 1:
            bars.append((open_from, left + _probe.textlength(line, font=face), base + 14))
    return tiles, bars


def card_height(*texts: str) -> int:
    room = COLW - (PAD + BADGE + GAP_S) - PAD
    lines = max(len(wrap(text, BODY, room)) for text in texts)
    return max(BADGE + 2 * PAD, round((lines * round(BODY * 1.2) + 2 * PAD) / 8) * 8)


def card(letter: str, text: str, fill, height: int) -> Image.Image:
    """A full-width option: a letter badge, then the words, left aligned, with equal padding all round."""
    left = PAD + BADGE + GAP_S
    layer = Image.new("RGBA", (COLW, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle((0, 0, COLW - 1, height - 1), RADIUS, fill=fill)
    draw.ellipse((PAD, (height - BADGE) / 2, PAD + BADGE - 1, (height + BADGE) / 2 - 1), fill=INK)
    draw.text((PAD + BADGE / 2, height / 2 + _height_of(BODY, "A") / 2), letter, font=font(BODY), fill=CREAM, anchor="ms")
    words = text_block(text, BODY, INK, COLW - left - PAD, 1.2, "left")
    layer.alpha_composite(words, (left, int((height - words.height) / 2)))
    return layer


def glow(height: int) -> Image.Image:
    """A soft gold halo the size of a card, for the winner."""
    layer = Image.new("RGBA", (COLW + 160, height + 160), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((80, 80, COLW + 79, height + 79), RADIUS, fill=GOLD)
    return layer.filter(ImageFilter.GaussianBlur(34))


def disc(number: int | None) -> Image.Image:
    layer = Image.new("RGBA", (DISC, DISC), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((0, 0, DISC - 1, DISC - 1), fill=INK)
    if number is not None:
        draw.text((DISC / 2, DISC / 2 + _height_of(DISPLAY, str(number)) / 2), str(number), font=font(DISPLAY), fill=CREAM, anchor="ms")
    return layer


def ring(share: float) -> Image.Image:
    """A gold ring around the count that fills clockwise over each second."""
    size = DISC + 56
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(layer).arc((6, 6, size - 7, size - 7), -90, -90 + 360 * share, fill=GOLD, width=14)
    return layer


def donkey(pose: str, width: int, height: int) -> tuple[Image.Image, float]:
    """The donkey cropped to what shows, fitted into width x height, and how far its weight sits from the box centre."""
    layer = Image.open(ASSETS / "mascot" / f"{pose}.png").convert("RGBA")
    layer = layer.crop(layer.getchannel("A").getbbox())
    scale = min(width / layer.width, height / layer.height)
    layer = layer.resize((round(layer.width * scale), round(layer.height * scale)), Image.LANCZOS)
    alpha = layer.getchannel("A").resize((max(1, layer.width // 4), max(1, layer.height // 4)))
    pixels, total, weighted = alpha.load(), 0, 0
    for y in range(alpha.height):
        for x in range(alpha.width):
            total += pixels[x, y]
            weighted += pixels[x, y] * x
    shift = (weighted / total) * 4 - layer.width / 2
    if layer.width + 2 * abs(shift) > width:  # centring the body must not push the box out of the column
        k = width / (layer.width + 2 * abs(shift))
        layer = layer.resize((round(layer.width * k), round(layer.height * k)), Image.LANCZOS)
        shift *= k
    return layer, shift


# ── layout ─────────────────────────────────────────────────────────────────

def _stack(scene: str, items: list, log: list) -> list:
    """items: (name, layer, gap after, body shift). Centre the group in the safe area, a little high."""
    total = sum(layer.height for _, layer, _, _ in items) + sum(gap for _, _, gap, _ in items[:-1])
    top = SAFE[1] + (SAFE_H - total) / 2 + BIAS
    placed = []
    for name, layer, gap, shift in items:
        centre = CX - shift
        placed.append((name, layer, centre, top + layer.height / 2))
        log.append((scene, name, centre - layer.width / 2, top, centre + layer.width / 2, top + layer.height, shift))
        top += layer.height + gap
    return placed


def _absolute(placed: tuple, tiles: list) -> list:
    """Word tiles from block coordinates to canvas coordinates, given where the block was placed."""
    _, layer, cx, cy = placed
    left, top = cx - layer.width / 2, cy - layer.height / 2
    return [(tile, left + x, top + y) for tile, x, y in tiles]


def scenes(slide: dict) -> tuple[dict, list]:
    """Every screen laid out once. Returns (screens, a log of each element's box for the layout check)."""
    log: list = []
    slide = {**slide, **{key: smart_quotes(slide[key]) for key in ("hook", "a", "b", "win", "send")}}
    height = card_height(slide["a"], slide["b"], slide["win"])
    phrase = text_block(slide["hook"], DISPLAY, CREAM, COLW, 1.12)
    room = SAFE_H - phrase.height - GAP_L - 2 * 96  # what the phrase leaves for the donkey
    if room < 360:
        raise RenderError("The Reel does not fit: the hook phrase is too long to leave room for the donkey.")
    hook_donkey, shift = donkey(slide["pose"], COLW, min(760, room))
    screens = {"hook": _stack("hook", [("phrase", phrase, GAP_L, 0), ("donkey", hook_donkey, 0, shift)], log)}
    hook_tiles, _ = word_tiles(slide["hook"], DISPLAY, CREAM, COLW, 1.12)
    screens["hook_words"] = _absolute(screens["hook"][0], hook_tiles)
    screens["question"] = _stack("question", [
        ("title", text_block(QUESTION, TITLE, CREAM, COLW, 1.12), GAP_L, 0),
        ("card A", card("A", slide["a"], CREAM, height), GAP_S, 0), ("card B", card("B", slide["b"], CREAM, height), GAP_XL, 0),
        ("count", disc(None), 0, 0)], log)
    reveal_donkey, shift = donkey(slide["reveal_pose"], COLW, 640)
    screens["reveal"] = _stack("reveal", [
        ("card A", card("A", slide["win"], GOLD, height), GAP_S, 0), ("card B", card("B", slide["b"], CREAM, height), GAP_L, 0),
        ("donkey", reveal_donkey, 0, shift)], log)
    send_donkey, shift = donkey(slide["send_pose"], COLW, 520)
    screens["send"] = _stack("send", [
        ("line", text_block(slide["send"], HEADING, CREAM, COLW, 1.2), GAP_L, 0), ("donkey", send_donkey, GAP_M, shift),
        ("ask", text_block(ASK, CAPTION, CREAM, COLW, 1.2), 0, 0)], log)
    send_tiles, send_bars = word_tiles(slide["send"], HEADING, CREAM, COLW, 1.2)
    screens["send_words"] = _absolute(screens["send"][0], send_tiles)
    line_left, line_top = screens["send"][0][2] - screens["send"][0][1].width / 2, screens["send"][0][3] - screens["send"][0][1].height / 2
    screens["send_bars"] = [(line_left + a, line_left + b, line_top + y) for a, b, y in send_bars]
    screens["numbers"] = {number: disc(number) for number in (3, 2, 1)}
    screens["glow"] = glow(height)
    return screens, log


def layout_problems(log: list) -> list[str]:
    """Measure every element against the system. An empty list means everything lines up."""
    bad = []
    for scene, name, left, top, right, bottom, shift in log:
        if left < SAFE[0] - 0.5 or right > SAFE[2] + 0.5 or top < SAFE[1] - 0.5 or bottom > SAFE[3] + 0.5:
            bad.append(f"{scene}/{name} is outside the safe area")
        if left < COL_L - 0.5 or right > COL_R + 0.5:
            bad.append(f"{scene}/{name} is outside the content column")
        if abs((left + right) / 2 - (CX - shift)) > 1:
            bad.append(f"{scene}/{name} is not centred")
    groups: dict[str, list] = {}
    for scene, name, _, top, _, bottom, _ in log:
        groups.setdefault(scene, []).append((name, top, bottom))
    for scene, items in groups.items():
        for (first, _, above), (second, below, _) in zip(items, items[1:]):
            if round(below - above) not in (GAP_S, GAP_M, GAP_L, GAP_XL):
                bad.append(f"{scene}: the gap from {first} to {second} is {round(below - above)}, not on the scale")
        room_above, room_below = items[0][1] - SAFE[1], SAFE[3] - items[-1][2]
        if abs((room_below - room_above) + 2 * BIAS) > 2:
            bad.append(f"{scene}: the group is not centred ({room_above:.0f} above, {room_below:.0f} below)")
    return bad


# ── drawing ────────────────────────────────────────────────────────────────

def _blit(base: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """Composite `layer` with its top left at (x, y), clipped to the canvas (alpha_composite cannot go off the edge)."""
    if x >= base.width or y >= base.height or x + layer.width <= 0 or y + layer.height <= 0:
        return
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(layer.width, base.width - x), min(layer.height, base.height - y)
    if (left, top, right, bottom) != (0, 0, layer.width, layer.height):
        layer = layer.crop((left, top, right, bottom))
    base.alpha_composite(layer, (max(0, x), max(0, y)))


def _put(base: Image.Image, layer: Image.Image, cx: float, cy: float, cam=(1.0, 0.0, 0.0), scale: float = 1.0,
         opacity: float = 1.0, angle: float = 0.0, squash=(1.0, 1.0)) -> None:
    """Place a layer with its centre at (cx, cy), seen through the camera (zoom, shake x, shake y)."""
    zoom, dx, dy = cam
    x, y = W / 2 + (cx - W / 2) * zoom + dx, H / 2 + (cy - H / 2) * zoom + dy
    sx, sy = scale * zoom * squash[0], scale * zoom * squash[1]
    if abs(sx - 1) > 1e-3 or abs(sy - 1) > 1e-3:
        layer = layer.resize((max(1, round(layer.width * sx)), max(1, round(layer.height * sy))), Image.BILINEAR)
    if abs(angle) > 0.05:
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    if opacity < 1.0:
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * max(0.0, opacity))))
    _blit(base, layer, round(x - layer.width / 2), round(y - layer.height / 2))


def _backdrop(colour, t: float, pulse: float = 0.0, calm: bool = False) -> Image.Image:
    """The colour, three soft shapes drifting across it, and a lift on the beat."""
    image = Image.new("RGBA", (W, H), colour)
    for which, radius in enumerate((240, 280, 320)):
        x, y = motion.drift(0.0 if calm else t, which)
        shape = motion.orb(radius)
        _blit(image, shape, round(x - shape.width / 2), round(y - shape.height / 2))
    if pulse > 0.02:
        image.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * 0.07 * pulse))))
    return image


_edge: Image.Image | None = None


def _darken_edges(image: Image.Image, strength: float) -> None:
    """The edges of the screen darken as the count tightens."""
    global _edge
    if _edge is None:
        _edge = Image.radial_gradient("L").resize((W, H), Image.BILINEAR)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade.putalpha(_edge.point(lambda v: int(max(0, v - 90) * 1.55 * strength)))
    image.alpha_composite(shade)


def _flash(image: Image.Image, strength: float) -> None:
    if strength > 0.01:
        image.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * min(1.0, strength)))))


def draw_hook(sc: dict, tl: Timeline, t: float, calm: bool = False) -> Image.Image:
    """The phrase lands word by word and the donkey pops in. Frame 0 already has a face and a first word."""
    image = _backdrop(RED, t, calm=calm)
    cam = (1 + 0.05 * motion.progress(t, 0, tl.q), 0.0, 0.0)
    for index, (tile, cx, cy) in enumerate(sc["hook_words"]):
        start = tl.hook_words[index]
        if t < start and not calm:
            continue
        landed = motion.out_back(motion.progress(t, start, 0.26))
        _put(image, tile, cx, cy, cam, scale=1.5 - 0.5 * landed, opacity=0.35 + 0.65 * motion.progress(t, start, 0.1))
    _, layer, cx, cy = sc["hook"][1]
    _put(image, layer, cx, cy, cam)                           # the donkey never wobbles: it is there from the first frame
    return image


def draw_question(sc: dict, tl: Timeline, t: float, calm: bool = False) -> Image.Image:
    """The question and the two options slide in, then the count tightens: a ring, a tremble, darker edges."""
    holding = min(t, tl.reveal - 0.45)                                  # everything holds its breath before the reveal
    image = _backdrop(TEAL, t, motion.beat_pulse(t, tl.beat, tl.q, tl.reveal - 0.45) * 0.6, calm)
    tension = motion.progress(t, tl.count[0], 3.0)
    shake_x, shake_y = motion.tremble(t, 4.5 * tension)
    cam = (1 + 0.045 * motion.progress(holding, tl.q, tl.reveal - tl.q), shake_x, shake_y)
    for (name, layer, cx, cy), start in zip(sc["question"], (tl.q + 0.3, tl.q + 0.8, tl.q + 1.3, tl.q + 1.9)):
        landed = motion.progress(t, start, 0.45)
        if name == "title":
            rise = motion.out_back(landed)
            _put(image, layer, cx, cy + 60 * (1 - rise), cam, opacity=min(1.0, landed * 2.5))
        elif name == "card A":
            _put(image, layer, cx - W * (1 - motion.out_back(landed, 1.2)), cy, cam, scale=1 + 0.008 * math.sin(t * 4.0))
        elif name == "card B":
            _put(image, layer, cx + W * (1 - motion.out_back(landed, 1.2)), cy, cam, scale=1 + 0.008 * math.sin(t * 4.0 + 1.5))
        elif t >= start:
            if t < tl.count[0]:
                _put(image, layer, cx, cy, cam, scale=motion.out_back(motion.progress(t, start, 0.3)), opacity=0.3)
            for number, begins in zip((3, 2, 1), tl.count):
                if begins <= t < begins + COUNT_STEP:
                    landed = motion.out_back(motion.progress(t, begins, 0.3))
                    _put(image, ring(motion.progress(t, begins, COUNT_STEP)), cx, cy, cam)
                    _put(image, sc["numbers"][number], cx, cy, cam, scale=1.7 - 0.7 * landed)
    if tension > 0:
        _darken_edges(image, 0.55 * tension)
    return image


def draw_reveal(sc: dict, tl: Timeline, t: float, calm: bool = False) -> Image.Image:
    """The drop: a flash, a jolt, a punch-in, the winner slammed in gold, the donkey flung up, confetti."""
    image = _backdrop(RED, t, motion.beat_pulse(t, tl.beat, tl.reveal + 0.25, tl.send) * 0.8, calm)
    punch = 0.09 * (1 - motion.out_cubic(motion.progress(t, tl.reveal, 0.4))) if not calm else 0.0
    shake_x, shake_y = (0.0, 0.0) if calm else motion.shake(t, tl.reveal, 0.5, 18)
    cam = (1 + punch, shake_x, shake_y)
    for name, layer, cx, cy in sc["reveal"]:
        landed = motion.progress(t, tl.reveal, 0.4)
        if name == "card A":
            if not calm:
                _put(image, sc["glow"], cx, cy, cam, opacity=0.65 * (1 - motion.progress(t, tl.reveal, 1.4)))
            _put(image, layer, cx, cy, cam, scale=1.0 if calm else 1 + 0.35 * (1 - motion.out_back(landed)))
        elif name == "card B":
            _put(image, layer, cx, cy + 26 * (1 if calm else motion.progress(t, tl.reveal, 0.3)), cam, opacity=0.4)
        elif t >= tl.reveal or calm:                              # a hard cut on the beat, under the flash
            _put(image, layer, cx, cy, cam)
    if not calm and t >= tl.reveal:
        for origin, angles, seed in (((60.0, 1560.0), (-82, -48), 3), ((1020.0, 1560.0), (-132, -98), 4)):  # two corner cannons, arcing over the donkey
            motion.Confetti(origin, tl.reveal + 0.02, 70, seed, angles, (1100, 1900)).draw(image, t)
        _flash(image, 0.75 * (1 - motion.progress(t, tl.reveal, 0.14)))
    return image


def draw_send(sc: dict, tl: Timeline, t: float, calm: bool = False) -> Image.Image:
    """The line to send lands word by word; its quoted words are underlined; the donkey beckons and hops."""
    image = _backdrop(RED, t, motion.beat_pulse(t, tl.beat, tl.send, tl.total - 1.0) * 0.5, calm)
    cam = (1 + 0.04 * motion.progress(t, tl.send, tl.total - tl.send), 0.0, 0.0)
    last = tl.send_words[-1]
    sweep = motion.out_cubic(motion.progress(t, last + 0.15, 0.5))
    if sweep > 0:
        bars, zoom = ImageDraw.Draw(image), cam[0]
        for left, right, y in sc["send_bars"]:
            bars.rounded_rectangle((W / 2 + (left - W / 2) * zoom, H / 2 + (y - H / 2) * zoom,
                                    W / 2 + (left + (right - left) * sweep - W / 2) * zoom, H / 2 + (y + 14 - H / 2) * zoom), 7, fill=GOLD)
    for index, (tile, cx, cy) in enumerate(sc["send_words"]):
        start = tl.send_words[index]
        if t < start:
            continue
        landed = motion.out_back(motion.progress(t, start, 0.24))
        _put(image, tile, cx, cy, cam, scale=1.4 - 0.4 * landed, opacity=0.35 + 0.65 * motion.progress(t, start, 0.1))
    for (name, layer, cx, cy), start in zip(sc["send"][1:], (tl.send + 0.15, tl.ask)):
        landed = motion.progress(t, start, 0.5)
        if name == "donkey":
            _put(image, layer, cx, cy, cam, opacity=motion.progress(t, start, 0.2))      # a quick fade in, no movement
        elif t >= start:
            _put(image, layer, cx, cy + 50 * (1 - motion.out_cubic(landed)), cam, opacity=min(1.0, landed * 2.5))
    return image


def _slide(leaving: Image.Image, arriving: Image.Image, amount: float) -> Image.Image:
    """The old screen slides out to the left as the new one slides in behind it."""
    canvas = Image.new("RGBA", (W, H))
    canvas.paste(leaving, (round(-W * amount), 0))
    canvas.paste(arriving, (round(W * (1 - amount)), 0))
    return canvas.convert("RGB")


def frame(sc: dict, tl: Timeline, t: float, calm: bool = False) -> Image.Image:
    """One frame. `calm` leaves out the flash, shake and confetti, for a still picture of the reveal."""
    if calm:
        return draw_reveal(sc, tl, t, True).convert("RGB")
    if tl.q <= t < tl.q + TRANSITION:
        return _slide(draw_hook(sc, tl, tl.q), draw_question(sc, tl, t), motion.in_out((t - tl.q) / TRANSITION))
    if tl.send <= t < tl.send + TRANSITION:
        return _slide(draw_reveal(sc, tl, tl.send), draw_send(sc, tl, t), motion.in_out((t - tl.send) / TRANSITION))
    scene = draw_hook if t < tl.q else draw_question if t < tl.reveal else draw_reveal if t < tl.send else draw_send
    return scene(sc, tl, t).convert("RGB")


def still(post: dict, target: Path) -> Path:
    """A 4:5 picture of the reveal, for Threads and the review sheet. It is the Reel's middle, cropped."""
    slide = post["slides"][0]
    sc, _ = scenes(slide)
    tl = timeline(slide)
    top = (H - 1350) // 2
    frame(sc, tl, tl.reveal + 1.4, calm=True).crop((0, top, W, top + 1350)).save(target, quality=92)
    return target


def make(post: dict, post_dir: Path) -> Path:
    """Write post_dir/reel.mp4 (video and sound) and note its timing and sounds in post["reel"]."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderError("ffmpeg is not installed, so the Reel could not be made.")
    slide = post["slides"][0]
    tl = timeline(slide)
    screens, log = scenes(slide)
    problems = layout_problems(log)
    if problems:
        raise RenderError("The Reel does not fit: " + "; ".join(problems[:3]))
    target = post_dir / FILE
    with tempfile.TemporaryDirectory(prefix="suresilly-ab-") as scratch:
        scratch = Path(scratch)
        tune = music.compose(MOOD, post_dir.name, tl.total, scratch / "tune.wav")
        words = " ".join([slide["hook"], slide["a"], slide["b"], slide["send"]])
        try:
            used = sfx.build(tl, words, str(post.get("sound_seed") or post_dir.name), tune, scratch / "mix.wav", scratch)
            audio = scratch / "mix.wav"
        except Exception as error:  # no effects is better than no post: the tune alone goes out
            used, audio = {"theme": "none", "sounds": [], "notes": [f"the mix failed: {error}"]}, tune
        # Instagram's Reel spec: H.264 4:2:0, 30 fps, AAC at 44.1 kHz and 128 kbps, index at the front.
        command = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                   "-i", str(audio), "-map", "0:v", "-map", "1:a", "-t", str(tl.total), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(target)]
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for number in range(int(tl.total * FPS)):
                encoder.stdin.write(frame(screens, tl, number / FPS).tobytes())
            encoder.stdin.close()
            error = encoder.stderr.read().decode()[-300:]
        except BrokenPipeError:
            error = encoder.stderr.read().decode()[-300:]
        if encoder.wait() != 0 or not target.is_file():
            raise RenderError(f"ffmpeg could not make the Reel: {error.strip()}")
    post["reel"] = {"seconds": tl.total, "tune": MOOD, "kind": "ab", "reveal": tl.reveal, "sound_theme": used["theme"],
                    "sounds": used["sounds"], "sound_notes": used["notes"],
                    "cover_ms": int((tl.hook_words[-1] + 0.6) * 1000)}  # the grid cover is the hook once its last word has landed
    return target
