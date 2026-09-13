"""The evening one-liner as a Reel: its slide on a tall page, held long enough to read, with its own tune."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import music
from .render import RenderError, reel_frame

FILE = "reel.mp4"


def seconds_for(text: str) -> float:
    """2 seconds to find the words, then 2.5 words a second; never under 8 seconds."""
    words = len(text.replace("[[", "").replace("]]", "").split())
    return round(max(8.0, 2 + words / 2.5), 1)


def make(post: dict, post_dir: Path) -> Path:
    """Write post_dir/reel.mp4 and note its length and tune in post["reel"]."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RenderError("ffmpeg is not installed, so the Reel could not be made.")
    slide = post["slides"][0]
    seconds = seconds_for(slide["text"])
    mood = slide.get("mood", "calm") if slide.get("mood") in music.MOODS else "calm"
    target = post_dir / FILE
    with tempfile.TemporaryDirectory(prefix="suresilly-reel-") as scratch:
        frame = reel_frame(post, Path(scratch) / "frame.jpg")
        tune = music.compose(mood, post_dir.name, seconds, Path(scratch) / "tune.wav")
        # Instagram's Reel spec: H.264 4:2:0, 30 fps, AAC at 44.1 kHz and 128 kbps, index at the front.
        done = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", str(frame), "-i", str(tune),
             "-t", str(seconds), "-c:v", "libx264", "-tune", "stillimage", "-vf", "scale=out_range=tv,format=yuv420p", "-r", "30",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart", str(target)],
            capture_output=True, text=True)
    if done.returncode != 0 or not target.is_file():
        raise RenderError(f"ffmpeg could not make the Reel: {done.stderr.strip()[-300:]}")
    post["reel"] = {"seconds": seconds, "tune": mood}
    return target
