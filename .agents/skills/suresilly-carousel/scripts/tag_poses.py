#!/usr/bin/env python3
"""
tag_poses.py — propose tags for pose artwork by looking at it.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  OFFLINE TOOL. Not a runtime path. Nothing in build.py or run.py     │
    │  imports this file, and nothing ever should.                         │
    │                                                                      │
    │      tag_poses.py --untagged --out mascot/tag_review.json            │
    │      # read it, edit it, then:                                       │
    │      tag_poses.py --apply mascot/tag_review.json                     │
    │                                                                      │
    │  It NEVER writes poses.json directly. It writes a review file with   │
    │  every proposal marked `known` or `new`, and --apply merges what is   │
    │  still in it. Invariant 11: a model may suggest, it may not decide.  │
    └──────────────────────────────────────────────────────────────────────┘

Why this exists. library.py picks a pose by overlapping the slide's words with
the pose's tags, so a pose is only ever as reachable as its tag list. Measured
across the 94 real and labelled slides in this repo, only 46 of 186 poses ever
rank first: 140 are dead weight that can be chosen only as leftovers, and the
11 poses with four tags or fewer won nothing at all. Tags were written by hand,
the import script printed "add tags in poses.json" and nobody ever did.

WHAT A PROBE OF THE RAW MODEL SHOWED, AND WHY THIS FILE IS SHAPED LIKE IT IS

Asking a vision model to "label this pose" produces fluent, generic wellness
words in the wrong register for a page about how people behave WITH each other.
Probed against four poses whose human tags are known good, `spiralling` came
back as burnout rather than rumination, and `welcoming` as "positive vibes"
rather than "send this" and "share" — which are the words that actually earn it
a call-to-action slide.

The probe also produced a false alarm worth recording, because it is the shape
of mistake this tool exists to catch in BOTH directions. `carrying_it_all` came
back as overload vocabulary with no relational word in it, against human tags
reading "between you", "the pair", "two people". That looked like the model
missing a two-donkey scene. It is one donkey carrying a stack of boxes, the
manifest correctly says figures=1, and the HUMAN tags are the wrong ones — they
pull a single-figure pose onto any slide that mentions two people. The model was
right and the library was wrong. Nothing here assumes the existing tags are
correct; it assumes only that a person reads both.

So three things are done that a bare prompt does not.

  1 · CODE TELLS THE MODEL WHAT CODE ALREADY KNOWS. The manifest records how
      many figures are in a scene. That is a fact, not an observation, so it is
      stated rather than asked, and a two-figure pose is described as relational
      before the model says a word.

  2 · THE REGISTER IS STEERED, THE VOCABULARY IS ENFORCED. The prompt carries a
      SAMPLE of the page's most-used phrases — see steer_vocabulary() for why
      sending all 844 was a mistake that cost the whole daily quota in six
      calls. Precision comes from the filter afterwards, not from the prompt.

  3 · NOTHING IS TRUSTED. Every proposal is sorted into `known`, meaning the
      phrase already exists somewhere in the corpus, and `new`, meaning it is
      vocabulary nobody has approved. A person reads the review file. Tags are
      MERGED with what is there, never substituted.

Free tier, and it stays that way. Image INPUT is free on the flash models; it is
image GENERATION that has a hard quota of zero, which is what mascot.py's header
is about. No image is generated here. Even so the allowance is small and real:
the first full-library attempt died on a 429 after six poses. Pacing, per-model
rotation and --resume are all here because of that, and a full pass over 186
poses is expected to take more than one quota window.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import resolve_keys  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
LIBRARY = SKILL_DIR / "mascot" / "library"
MANIFEST = SKILL_DIR / "mascot" / "poses.json"
CHARACTER_MD = SKILL_DIR / "mascot" / "CHARACTER.md"

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Flash is enough for this and has the largest free allowance. The list mirrors
# llm.py's: quota is per project PER MODEL per day, so a second name is a
# second allowance rather than a fallback for a bad answer.
MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.5-flash")
PACE_SECONDS = 7.0          # free tier is ~10 requests/minute; 7s keeps under it
MAX_RETRIES = 4             # a 429 is a queue, not a failure
VOCAB_SAMPLE = 120          # see steer_vocabulary()
THIN_TAGS = 6               # at or below this, a pose is worth looking at

SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    "required": ["tags"],
}


def corpus(manifest: dict) -> list[str]:
    """Every tag phrase already in use, plus the proved concept terms."""
    seen: set[str] = set()
    for entry in manifest.get("poses", {}).values():
        seen |= set(entry.get("tags", []))
    concepts = manifest.get("concepts")
    if isinstance(concepts, dict):
        seen |= set(concepts)
    elif isinstance(concepts, list):
        seen |= {c for c in concepts if isinstance(c, str)}
    return sorted(seen)


def steer_vocabulary(manifest: dict, limit: int = VOCAB_SAMPLE) -> list[str]:
    """A SAMPLE of the corpus, to show the model the register — not all of it.

    The first version sent all 844 phrases in every system prompt. It steered
    well (49 of 50 proposals landed inside the corpus) and it cost about 2,700
    input tokens per pose, which exhausted the free daily quota after six calls
    with a 429 and no way to finish the library.

    The full list is not what does the work. The model needs to hear the
    REGISTER — short, lowercase, relational, the way these slides talk — and a
    sample carries that. Everything the model returns is checked against the
    complete corpus afterwards regardless, in known/new, so precision is
    enforced by the filter rather than bought by the token.

    Sorted by how many poses use a phrase, so the sample is the page's most
    load-bearing language rather than an arbitrary slice, and deterministic.
    """
    uses: dict[str, int] = {}
    for entry in manifest.get("poses", {}).values():
        for tag in entry.get("tags", []):
            uses[tag] = uses.get(tag, 0) + 1
    ranked = sorted(uses, key=lambda t: (-uses[t], t))
    return ranked[:limit]


def flatten(png: Path, height: int = 520) -> bytes:
    """The pose on white, at a size worth spending tokens on.

    On white rather than on the transparent original: an alpha PNG reaches the
    model as black wherever it is transparent, and a donkey in a black box
    invites the model to describe the box.
    """
    img = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"unreadable: {png}")
    if img.shape[2] == 4:
        a = img[:, :, 3:4].astype(np.float32) / 255.0
        img = (img[:, :, :3] * a + 255 * (1 - a)).astype(np.uint8)
    scale = height / img.shape[0]
    img = cv2.resize(img, (max(1, int(img.shape[1] * scale)), height),
                     interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError(f"could not encode: {png}")
    return buf.tobytes()


def system_prompt(vocabulary: list[str]) -> str:
    return (
        "You label artwork of Silly, a cartoon donkey mascot for @suresilly, an "
        "Instagram page about RELATIONAL psychology — how people behave with each "
        "other, not personal wellness.\n\n"
        "Give the words a SLIDE about this picture would use: the emotional and "
        "relational MEANING, never the physical drawing. 'unimpressed', not 'arms "
        "at his sides'. 'overthinking', not 'hooves on head'.\n\n"
        "Prefer this page's existing vocabulary wherever it fits. These are the "
        "phrases already in use:\n" + ", ".join(vocabulary) + "\n\n"
        "You may add a phrase that is not on the list when nothing on it fits, but "
        "prefer the list. 8 to 14 short lowercase tags, a mix of single words and "
        "two-to-three word phrases a real person would type. No punctuation."
    )


def user_prompt(name: str, entry: dict) -> str:
    """What code KNOWS, stated rather than asked.

    The figure count is the load-bearing line. A raw probe read
    carrying_it_all — two donkeys, one carrying everything — as a picture of one
    overloaded person, and returned burnout vocabulary with no relational word
    in it at all.
    """
    lines = [f"Pose name: {name.replace('_', ' ')}"]
    if entry.get("figures") == 2:
        lines.append(
            "THIS SCENE CONTAINS TWO DONKEYS. It is about something happening "
            "BETWEEN two people — a dynamic, an imbalance, a distance, a repair. "
            "Tag the relationship, not one individual's mood.")
    else:
        lines.append("One donkey. Tag what he is feeling or doing.")
    if entry.get("tags"):
        lines.append("Tags it already has, which you should not repeat but should "
                     "treat as the register to write in: " + ", ".join(entry["tags"]))
    lines.append("Label this pose.")
    return "\n".join(lines)


# Words the model puts on almost everything, because of how the character is
# drawn rather than because of what a pose shows. Silly has ONE thick black brow
# bar and it reads as a scowl on a pose that is inviting, sleeping or cheerful —
# library.py's own note says 38% of the library "reads as cross whatever it is
# called". Measured over twelve poses, the model proposed a word from this set
# for `beckoning` (an inviting pose), `bathrobe`, `back_to_back` and
# `already_leaving`. It is a systematic artefact of the artwork, so it is
# filtered systematically rather than caught by eye each time.
#
# A pose that ALREADY carries one of these keeps it: deadpan really is
# unimpressed. This only stops the word spreading to poses that are not.
BROW_BIAS = {"unimpressed", "not amused", "skeptical", "unconvinced", "deadpan",
             "dry", "flat", "level look", "stern", "cross", "disapproving"}


def sanitise(tags: list[str], name: str, pose_names: set[str],
             existing: set[str]) -> list[str]:
    """Drop proposals that would do harm rather than nothing.

    Three kinds, all found by reading twelve real proposals.

    ANOTHER POSE'S NAME. `approving` was offered "cheering" and "aha",
    `blank_card` was offered "empty space", `spiralling` was offered "sleepless"
    and "3am". Each of those is the name of a DIFFERENT pose that exists and is
    tagged for exactly that slide. A tag like this does not merely fail to help;
    it puts two poses in contention for a slide only one of them is right for,
    and the wrong one can win. This is the most damaging thing the model
    produces and the easiest to catch.

    THE BROW BIAS. See BROW_BIAS above.

    FRAGMENTS. "argu" came back for `accusing` — a stemmed stump, not a word
    anybody types. Anything under three characters or without a vowel goes.
    """
    out = []
    for tag in tags:
        t = " ".join(tag.split()).lower()
        if not t or t in existing:
            continue
        if len(t) < 3 or not set(t) & set("aeiou"):
            continue
        # a pose name, in either spelling, and not this pose's own
        slug = t.replace(" ", "_")
        if (slug in pose_names or t in pose_names) and slug != name:
            continue
        if t in BROW_BIAS and t not in existing:
            continue
        out.append(t)
    return out


class QuotaExhausted(RuntimeError):
    """Every model on every key returned 429. Not a failure — come back later."""


def ask(png: Path, name: str, entry: dict, vocabulary: list[str],
        key: str, model: str, timeout: int = 90) -> tuple[list[str], dict]:
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt(vocabulary)}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": "image/png",
                             "data": base64.b64encode(flatten(png)).decode()}},
            {"text": user_prompt(name, entry)}]}],
        # Temperature 0: this is a labelling job, and two runs over the same
        # library should not disagree for no reason.
        "generationConfig": {"temperature": 0.0,
                             "responseMimeType": "application/json",
                             "responseSchema": SCHEMA},
    }
    request = urllib.request.Request(
        URL.format(model=model) + "?key=" + key,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    text = body["candidates"][0]["content"]["parts"][0]["text"]
    tags = [t.strip().lower() for t in json.loads(text).get("tags", []) if t.strip()]
    return tags, body.get("usageMetadata", {})


def ask_with_retry(png: Path, name: str, entry: dict, vocabulary: list[str],
                   keys: list[str]) -> tuple[list[str], dict]:
    """Walk every (key, model) pair before giving up.

    Gemini's free quota is counted per project PER MODEL per day, exactly as
    llm.py documents, so a second model id is a second allowance rather than a
    retry of the same one. A 429 on flash says nothing about flash-lite.
    """
    last_429 = None
    for key in keys:
        for model in MODELS:
            for attempt in range(MAX_RETRIES):
                try:
                    return ask(png, name, entry, vocabulary, key, model)
                except urllib.error.HTTPError as e:
                    if e.code not in (429, 503):
                        raise
                    last_429 = e
                    if e.code == 429 and attempt == 0:
                        break          # daily quota: move to the next model
                    time.sleep(2 ** attempt * PACE_SECONDS)
    raise QuotaExhausted(str(last_429))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(SKILL_DIR / "mascot" / "tag_review.json"),
                    help="where to write proposals for review")
    ap.add_argument("--untagged", action="store_true",
                    help=f"only poses with {THIN_TAGS} tags or fewer")
    ap.add_argument("--only", help="comma-separated pose names")
    ap.add_argument("--limit", type=int, help="stop after this many poses")
    ap.add_argument("--resume", action="store_true",
                    help="keep what is already in --out and only do the rest")
    ap.add_argument("--apply", metavar="FILE",
                    help="merge a reviewed proposal file into poses.json and exit")
    a = ap.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text())
    poses = manifest["poses"]

    if a.apply:
        review = json.loads(Path(a.apply).read_text())
        changed = 0
        for name, proposal in review.get("poses", {}).items():
            if name not in poses:
                print(f"  ? {name}: not in the manifest, skipped")
                continue
            before = set(poses[name].get("tags", []))
            add = sanitise(proposal.get("known", []) + proposal.get("new", []),
                           name, set(poses), before)
            # MERGE. The hand-written tags are the better ones; this is filling
            # gaps in a library where 140 poses cannot be reached at all.
            poses[name]["tags"] = sorted(before | set(add))
            if set(poses[name]["tags"]) != before:
                changed += 1
                print(f"  + {name:22s} {len(before)} -> {len(poses[name]['tags'])} tags")
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"\n{changed} poses updated in {MANIFEST}")
        return 0

    keys = resolve_keys("GEMINI_API_KEY")
    if not keys:
        sys.exit("ERROR: no GEMINI_API_KEY configured. This tool needs one; the "
                 "render path does not.")

    names = sorted(poses)
    if a.only:
        names = [n.strip() for n in a.only.split(",")]
    elif a.untagged:
        names = [n for n in names if len(poses[n].get("tags", [])) <= THIN_TAGS]
    if a.limit:
        names = names[:a.limit]
    if not names:
        sys.exit("nothing to do")

    known = set(corpus(manifest))          # the FULL corpus, for the filter
    vocabulary = steer_vocabulary(manifest)  # a sample, for the prompt
    review: dict = {"poses": {}}
    out_path = Path(a.out)
    if a.resume and out_path.is_file():
        review = json.loads(out_path.read_text())
        done = set(review.get("poses", {}))
        names = [n for n in names if n not in done]
        print(f"resuming: {len(done)} already done, {len(names)} to go")
    tokens_in = tokens_out = 0
    print(f"{len(names)} pose(s), vocabulary of {len(vocabulary)} phrases\n")

    for i, name in enumerate(names, 1):
        png = LIBRARY / f"{name}.png"
        if not png.is_file():
            print(f"  ? {name}: no artwork")
            continue
        try:
            tags, usage = ask_with_retry(png, name, poses[name], vocabulary, keys)
        except QuotaExhausted:
            print(f"\n  quota exhausted at {name}. {len(review['poses'])} done.")
            print(f"  Re-run the same command later — --resume skips what is written.")
            break
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, RuntimeError) as e:
            print(f"  ✗ {name}: {e}")
            continue
        tokens_in += usage.get("promptTokenCount", 0)
        tokens_out += usage.get("candidatesTokenCount", 0)
        existing = set(poses[name].get("tags", []))
        fresh = sanitise(tags, name, set(poses), existing)
        review["poses"][name] = {
            "known": [t for t in fresh if t in known],
            "new": [t for t in fresh if t not in known],
        }
        entry = review["poses"][name]
        print(f"  [{i}/{len(names)}] {name:22s} +{len(entry['known'])} known "
              f"+{len(entry['new'])} new")
        # Written every pose, not at the end: a quota stop mid-run must not
        # throw away the calls that already succeeded.
        Path(a.out).write_text(json.dumps(review, indent=2) + "\n")
        time.sleep(PACE_SECONDS)

    Path(a.out).write_text(json.dumps(review, indent=2) + "\n")
    print(f"\n{len(review['poses'])} proposals -> {a.out}")
    print(f"tokens: {tokens_in} in, {tokens_out} out (free tier)")
    print("Read it. Delete anything wrong. Then: tag_poses.py --apply " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
