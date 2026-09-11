"""Pick a donkey pose for each slide's mood. Library poses only: no text in the art."""
from __future__ import annotations

import random
from pathlib import Path

from . import ASSETS

LIBRARY = ASSETS / "mascot"

POSES = {
    "warm": ("holding_heart", "self_hug", "warm_mug", "hoof_on_chest", "flower", "waving",
             "head_tilt", "winking", "offering"),
    "calm": ("serene", "sitting", "cardigan_mug", "reading", "sitting_ledge", "listening",
             "relieved", "stretching"),
    "wistful": ("pondering", "looking_far", "looking_up", "glancing_back", "walking_away",
                "knowing_look", "walking"),
    "sad": ("knees_hugged", "big_sigh", "curled_up", "phone_down", "sleepless", "leaning_on",
            "slow_blink", "turning_away"),
    "tired": ("floor_slumped", "face_down", "propped_up", "carrying_it_all", "catching_breath",
              "on_back"),
    "joy": ("cheering", "laughing", "jumping", "leaping", "idea", "approving"),
    "wise": ("sage", "storyteller", "explaining", "point_up", "lantern_bearer", "realising"),
    "invite": ("point_right", "beckoning", "presenting"),
}


def path(name: str) -> Path:
    found = LIBRARY / f"{name}.png"
    if not found.is_file():
        raise FileNotFoundError(f"No donkey pose called {name!r}")
    return found


def pick(moods: list[str], seed: str, avoid: set[str] | frozenset = frozenset()) -> list[str]:
    """One pose per mood, never the same pose twice in a post, and none from `avoid`."""
    rng = random.Random(seed)
    used = set(avoid)
    chosen = []
    for mood in moods:
        options = POSES.get(mood, POSES["calm"])
        fresh = [name for name in options if name not in used]
        if not fresh:  # a mood can run out in a long post; borrow a neighbour
            fresh = [name for group in ("calm", "warm", "wistful") for name in POSES[group] if name not in used]
        name = rng.choice(fresh or list(options))
        used.add(name)
        chosen.append(name)
    return chosen
