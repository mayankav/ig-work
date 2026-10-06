"""The evening one-liner as a Reel, with its own tune.

A two-beat one-liner plays the setup over a blinking blank, then the twist lands and the donkey
changes pose, then the finished card holds long enough to read and send. The blank is there from
the first frame so a viewer knows a payoff is coming. An older post with just a text plays as one
still card, held long enough to read.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import music
from .render import RenderError, reel_frame, reel_frames

FILE = "reel.mp4"
BLINK = 0.5        # seconds the cursor stays on, and then off
COVER_AFTER = 0.6  # seconds past the reveal where the grid cover is taken, so the cover is the finished card


def count(text: str) -> int:
    return len(text.replace("[[", "").replace("]]", "").split())


def seconds_for(text: str) -> float:
    """A single still card: 2 seconds to find the words, then 2.5 words a second; never under 8 seconds."""
    return round(max(8.0, 2 + count(text) / 2.5), 1)


def reveal_for(setup: str) -> float:
    """When the twist lands: about when the setup has been read, never before 2 s or after 3.5 s."""
    return round(min(3.5, max(2.0, 1 + count(setup) / 3.5)), 1)


def two_beat_seconds(setup: str, twist: str) -> tuple[float, float]:
    """(reveal, total): the finished card then holds for the twist to be read plus a beat to send it, 4 s at least."""
    reveal = reveal_for(setup)
    hold = max(4.0, 2.0 + count(twist) / 2.5)
    return reveal, round(max(8.0, reveal + hold), 1)


def timeline(frames: dict[str, Path], reveal: float, total: float) -> list[tuple[Path, float]]:
    """(picture, seconds) in order: the blank blinks until the reveal, then the finished card to the end."""
    parts, at, on = [], 0.0, True
    while at < reveal - 1e-6:
        length = round(min(BLINK, reveal - at), 3)
        parts.append((frames["blank_on" if on else "blank_off"], length))
        at, on = at + length, not on
    parts.append((frames["full"], round(total - reveal, 3)))
    return parts


def make(post: dict, post_dir: Path) -> Path:
    """Write post_dir/reel.mp4 and note its length, tune and (if two-beat) reveal time in post["reel"]."""
    if post.get("format") == "ab":
        from . import abreel
        return abreel.make(post, post_dir)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderError("ffmpeg is not installed, so the Reel could not be made.")
    slide = post["slides"][0]
    two_beat = bool(slide.get("setup") and slide.get("twist"))
    if two_beat:
        reveal, seconds = two_beat_seconds(slide["setup"], slide["twist"])
    else:
        reveal, seconds = 0.0, seconds_for(slide["text"])
    mood = slide.get("mood", "calm") if slide.get("mood") in music.MOODS else "calm"
    target = post_dir / FILE
    with tempfile.TemporaryDirectory(prefix="suresilly-reel-") as scratch:
        scratch = Path(scratch)
        tune = music.compose(mood, post_dir.name, seconds, scratch / "tune.wav")
        if two_beat:
            parts = timeline(reel_frames(post, scratch), reveal, seconds)
            listing = scratch / "frames.txt"
            # the concat demuxer drops the last duration, so the last picture is named twice
            listing.write_text("".join(f"file '{path}'\nduration {length}\n" for path, length in parts)
                               + f"file '{parts[-1][0]}'\n", encoding="utf-8")
            source = ["-f", "concat", "-safe", "0", "-i", str(listing)]
            video = "fps=30,scale=out_range=tv,format=yuv420p"
        else:
            source = ["-loop", "1", "-framerate", "30", "-i", str(reel_frame(post, scratch / "frame.jpg"))]
            video = "scale=out_range=tv,format=yuv420p"
        # Instagram's Reel spec: H.264 4:2:0, 30 fps, AAC at 44.1 kHz and 128 kbps, index at the front.
        done = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", *source, "-i", str(tune), "-t", str(seconds),
             "-c:v", "libx264", "-tune", "stillimage", "-vf", video, "-r", "30",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(target)],
            capture_output=True, text=True)
    if done.returncode != 0 or not target.is_file():
        raise RenderError(f"ffmpeg could not make the Reel: {done.stderr.strip()[-300:]}")
    post["reel"] = {"seconds": seconds, "tune": mood}
    if two_beat:
        post["reel"].update(reveal=reveal, cover_ms=int((reveal + COVER_AFTER) * 1000))
    return target
