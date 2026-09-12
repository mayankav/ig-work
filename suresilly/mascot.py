"""The donkey poses: what each one shows, and how a slide gets one.

The writer picks a pose by name for every slide, reading the notes below. The
mood groups are the fallback: when a name is missing, misspelt or already used
in the post, the slide gets a pose from its mood's group instead.
Library poses only: no new art, no text in the art.
"""
from __future__ import annotations

import random
from pathlib import Path

from . import ASSETS

LIBRARY = ASSETS / "mascot"

# Every pose, grouped by the feeling it carries. The writer sees this list with
# the group headings; the groups double as the fallback when a slide's pose is
# missing or already used. One line per pose says what the donkey is doing, as a
# writer would read it. OBJECT marks a pose with a thing in it (mug, book,
# lantern...), because the thing is what looks wrong under a line that has
# nothing to do with it.
GROUPS = {
    "invite": ("slide 1 only: points you into the swipe", {
        "point_right": "pointing to the right, serious face",
        "beckoning": "one hoof up, waving you over",
        "presenting": "arm out to the side, showing you something",
    }),
    "warm": ("love, tenderness, giving, hello and goodbye", {
        "holding_heart": "OBJECT: hugging a red heart to the chest, eyes closed",
        "self_hug": "arms wrapped around itself, eyes closed",
        "hoof_on_chest": "hoof on the chest, eyes closed, touched",
        "head_tilt": "standing, head tilted, small curious smile",
        "waving": "one hoof up, waving hello or goodbye",
        "offering": "hoof held out, palm up, giving you something",
        "winking": "hoof behind the head, winking, cheeky",
        "flower": "OBJECT: holding out a small daisy, soft smile",
        "warm_mug": "OBJECT: holding a mug with both hooves, eyes closed, warm",
        "gift_box": "OBJECT: holding out a small wrapped gift with both hooves, eyes closed, pleased",
        "holding_note": "OBJECT: standing, reading a small folded note held in both hooves",
        "phone_call": "OBJECT: phone to the ear, listening, small smile",
    }),
    "calm": ("quiet, settled, everyday", {
        "serene": "standing, eyes closed, hooves together, peaceful",
        "sitting": "sitting on the floor, looking up, waiting",
        "sitting_ledge": "sitting on a ledge, legs dangling, looking to one side",
        "listening": "leaning in, eyes wide, listening closely",
        "relieved": "eyes closed, small smile, letting a breath out",
        "slow_blink": "standing, eyes closed, soft face, a slow blink",
        "stretching": "arms up, mouth open, a yawn and a stretch",
        "cardigan_mug": "OBJECT: in a beige cardigan, holding a mug of tea with both hooves",
        "reading": "OBJECT: glasses on, reading an open book",
        "stirring_pot": "OBJECT: in an apron, stirring a cooking pot with a wooden spoon",
        "holding_plant": "OBJECT: holding a small potted plant with both hooves, looking at it",
        "wiping_hands": "OBJECT: standing, wiping the hooves on a small yellow cloth, job done",
        "flashlight": "OBJECT: standing, holding a small torch pointed forward",
        "lunchbox": "OBJECT: holding a small closed lunchbox with both hooves",
        "umbrella": "OBJECT: standing under a small open yellow umbrella, looking up",
    }),
    "wistful": ("remembering, waiting, looking back", {
        "pondering": "glasses on, hoof on chin, thinking hard",
        "knowing_look": "glasses on, hoof to chin, a knowing sideways look",
        "looking_far": "hoof shading the eyes, looking into the distance",
        "looking_up": "chin up, looking at the sky, hopeful",
        "glancing_back": "walking away, looking back over the shoulder",
        "walking": "walking briskly, going somewhere",
        "arms_crossed_waiting": "standing, arms crossed, tapping a hoof, waiting",
        "photo_frame": "OBJECT: looking down at a small photo frame held in both hooves",
        "looking_at_watch": "OBJECT: looking at a watch on the wrist",
        "holding_key": "OBJECT: holding up a single small key, looking at it",
    }),
    "sad": ("hurt, small, alone", {
        "big_sigh": "head thrown back, mouth open, a long groan",
        "turning_away": "turned away, looking back with a hurt side-eye",
        "walking_away": "walking away, head down, sad",
        "leaning_on": "leaning sideways on a wall, arms crossed, low",
        "curled_up": "lying curled on the floor, eyes shut, switched off",
        "facepalm": "standing, one hoof over the face",
        "covering_ears": "both hooves over the ears, eyes shut tight",
        "hands_behind_back": "standing, hooves behind the back, looking down, shy",
        "knees_hugged": "OBJECT: sitting under a blanket, knees hugged, made small",
        "sleepless": "OBJECT: wrapped in a blanket, eyes wide open, awake at night",
        "phone_down": "OBJECT: looking down at a phone in one hoof",
    }),
    "tired": ("worn out, chores, collapse", {
        "floor_slumped": "sitting on the floor, head hanging, eyes closed, deflated",
        "catching_breath": "bent forward, hooves on knees, worn out",
        "face_down": "lying flat on the floor, face in the ground",
        "on_back": "lying on the back, legs up, staring at the ceiling",
        "propped_up": "lying on one side, head propped on a hoof, lounging",
        "asleep_on_floor": "sitting on the floor, chin on chest, asleep",
        "asleep_on_desk": "OBJECT: asleep at a desk, head on folded arms",
        "carrying_it_all": "OBJECT: staggering under a tall stack of tied-up boxes, sweating",
        "carrying_bags": "OBJECT: walking with two paper grocery bags, one in each hoof",
    }),
    "joy": ("delight, surprise, laughter", {
        "cheering": "both arms up, eyes shut, shouting with joy",
        "laughing": "head back, eyes shut, laughing out loud",
        "jumping": "mid-air, arms out, delighted",
        "leaping": "flying diagonally, arms and legs stretched, free",
        "idea": "finger up, eyes wide, a lightbulb moment",
        "approving": "thumbs up, big toothy grin",
        "hands_over_mouth": "both hooves over the mouth, eyes wide, surprised",
        "holding_hands_out_rain": "both hooves out, palms up, looking up with an open mouth, catching rain",
        "sneaking_cookie": "OBJECT: tiptoeing with one bitten cookie, looking to the side, caught",
    }),
    "wise": ("telling, explaining, the lesson", {
        "explaining": "pointing to one side, mouth open, mid-sentence",
        "point_up": "finger up, making a point",
        "realising": "finger up, mouth open, just got it",
        "sage": "OBJECT: in a robe with a wooden staff, a calm elder",
        "storyteller": "OBJECT: cross-legged in a waistcoat, arms open, telling a story",
        "lantern_bearer": "OBJECT: in a cloak, holding up a lantern in the dark",
    }),
}

NOTES = {name: what for _, poses in GROUPS.values() for name, what in poses.items()}
POSES = {mood: tuple(poses) for mood, (_, poses) in GROUPS.items()}
MOOD_OF = {name: mood for mood, names in POSES.items() for name in names}


def path(name: str) -> Path:
    found = LIBRARY / f"{name}.png"
    if not found.is_file():
        raise FileNotFoundError(f"No donkey pose called {name!r}")
    return found


def notes() -> str:
    """The pose list as the writer sees it: a heading per group, one pose per line."""
    blocks = []
    for mood, (label, poses) in GROUPS.items():
        blocks.append(f"{mood} ({label}):\n" + "\n".join(f"- {name}: {what}" for name, what in poses.items()))
    return "\n\n".join(blocks)


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


def choose(slides: list[dict], seed: str) -> list[str]:
    """The writer's pose for each slide when it names a real, unused one; else a pose for its mood."""
    rng = random.Random(seed)
    used: set[str] = set()
    chosen: list[str | None] = []
    for slide in slides:
        name = slide.get("pose")
        if name in NOTES and name not in used:
            used.add(name)
            chosen.append(name)
        else:
            chosen.append(None)
    for index, slide in enumerate(slides):
        if chosen[index] is None:
            chosen[index] = pick([slide.get("mood", "calm")], f"{seed}-{index}-{rng.random()}", avoid=used)[0]
            used.add(chosen[index])
    return chosen  # type: ignore[return-value]
