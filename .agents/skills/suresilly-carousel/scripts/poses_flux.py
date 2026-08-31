#!/usr/bin/env python3
"""
poses_flux.py — grow the pose library with FLUX.2 [klein] 4B on Workers AI.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  OFFLINE TOOL. Not a runtime path. Nothing in build.py or run.py     │
    │  imports this file, and nothing ever should.                         │
    │                                                                      │
    │  It writes raw PNGs into an inbox folder. The library is then grown  │
    │  the way it has always been grown:                                   │
    │                                                                      │
    │      poses_flux.py --name sulking --brief "..." --out mascot/inbox   │
    │      import_poses.py mascot/inbox --fullbody                         │
    │                                                                      │
    │  The render path keeps working with no key and no network, because   │
    │  by the time a pose reaches a slide it is a file on disk like every  │
    │  other pose.                                                         │
    └──────────────────────────────────────────────────────────────────────┘

Why this file exists at all. The library is 165 poses and frozen, because the
only fresh-generation route was Gemini, which caps image generation at zero
requests on the free tier. Workers AI now hosts a distilled FLUX.2 that takes
up to four reference images, and reference conditioning — not prompt wording —
is what holds a character. A text prompt alone cannot reconstruct Silly; four
pictures of him can get close.

Three things here are deliberate and easy to get wrong:

  · The MODEL. Read the licence note beside MODEL before changing it.
  · The REFERENCES. They come from mascot/library/, never from
    mascot/style_refs/. See pick_references().
  · The BACKDROP. Everything downstream mattes a magenta key, so the prompt
    asks for one and the gates check we got one. A pose on a green or white
    background is unusable no matter how good the drawing is.

Standard library plus the cv2/numpy this repo already has. The multipart body
is built by hand because this endpoint is the one place in the skill that is
not plain JSON, and a form encoder is not worth a new dependency.

What to expect when you run it. The model returns JPEG — always, whatever
output_format says — and JPEG chroma subsampling puts a fringe of half-magenta
pixels along every green edge. Most frames matte cleanly anyway; some come back
over cutout.py's key_residue threshold and are refused. That is the gate doing
its job on a genuinely dirty edge, not a false alarm, and the fix is another
seed, never a looser threshold. Budget for a re-roll now and then.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The character gates live in cutout.py, not here. They used to live in this
# file, which meant the IMPORT path — the way every one of the 180 library poses
# actually arrived — ran none of them. They are re-exported under their old
# names so this module's callers and tests are unaffected by the move.
from cutout import (  # noqa: E402
    CREAM_MAX_S, CREAM_MIN_V, EYE_MAX_SAT, GREEN_HUE_RANGE, LIBRARY_CREAM_HUE,
    LIBRARY_GREEN_SAT, QAFailure, assert_has_pupils, assert_no_text,
    assert_on_palette, auto_chroma_matte, backdrop_mask, correct_palette,
    detect_key_colour, glyph_runs, qa,
)
from imaging import drop_neighbour_bleed, tight_crop  # noqa: E402
# The ledger and the budget constants live in neurons.py: llm.py records the
# TEXT half of the same daily allowance and cannot import this module, because
# this module imports llm for its credentials. Re-exported so callers and tests
# that reach for pf.Ledger keep working.
from neurons import (  # noqa: E402
    DEFAULT_BUDGET, FREE_DAILY_NEURONS, LEDGER_PATH, NEURONS_PER_MEGAPIXEL,
    NEURONS_PER_REFERENCE, BudgetExceeded, Ledger, _today,
)
from llm import resolve_key  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SKILL_DIR.parents[2]
CHARACTER_MD = SKILL_DIR / "mascot" / "CHARACTER.md"
LIBRARY = SKILL_DIR / "mascot" / "library"
MANIFEST = SKILL_DIR / "mascot" / "poses.json"
STYLE_REFS = SKILL_DIR / "mascot" / "style_refs"
DEFAULT_OUT = SKILL_DIR / "mascot" / "inbox"

# ── the model ────────────────────────────────────────────────────────────────
#
# @cf/black-forest-labs/flux-2-klein-4b is APACHE-2.0. Commercial use is
# permitted, which is the only reason this file can exist: @suresilly is a
# commercial page.
#
# DO NOT "UPGRADE" THIS. Cloudflare's catalogue lists three FLUX.2 variants and
# the other two are licensed the other way:
#
#     flux-2-klein-4b   apache-2.0                    ← the only usable one
#     flux-2-klein-9b   flux-non-commercial-license   ← better output, forbidden
#     flux-2-dev        flux-non-commercial-license   ← forbidden
#
# The 9B sits one row below the 4B in Cloudflare's own pricing table and makes
# visibly nicer pictures. That is the trap, and there are two reasons not to
# take it. The first used to be stated wrongly here.
#
# PRICE, which is decisive on its own. Read off Cloudflare's published table on
# 2026-08-31: the 4B is billed "26.05 neurons per output 512x512 tile", so a
# 1024x1024 pose with four references comes to about 126. The 9B is billed per
# megapixel — "1363.64 neurons per first MP" — so the same pose costs about
# 1,554. Twelve times the price. That is six pictures a day instead of forty.
#
# LICENCE, which is real but narrower than this comment claimed. On Hugging
# Face the 4B carries license:apache-2.0 and the 9B carries
# flux-non-commercial-license. Cloudflare's own model pages show NO licence
# string for either one — both link to the same BFL terms — so the distinction
# is invisible in the place you would look for it, which is the whole reason a
# test guards it. And the licence text restricts running and distributing the
# WEIGHTS to non-commercial purposes while expressly permitting commercial use
# of the pictures. So "every pose would be unshippable" was the wrong reason.
# Operating the model for a monetised page is the right one.
#
# If output quality is not good enough, the answer is a better prompt, better
# references, or not using this tool — never a different row in that table.
MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
RUN_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

# The backdrop the whole downstream pipeline expects. Magenta because Silly is
# green: a green key would eat the character. cutout.py detects the key rather
# than assuming it, but the prompt still has to ask for the right one.
CHROMA_HEX = "#FF00FF"
CHROMA_BGR = (255, 0, 255)

MAX_REFS = 4                # the model accepts input_image_0 .. input_image_3
TIMEOUT = 180               # a 1024px generation is slow; this is not a chat call



class FluxError(Exception):
    """The generation call did not produce usable artwork."""


# ─────────────────────────── character bible ─────────────────────────────────

BLOCKS = ("IDENTITY", "FRAMING", "STYLE", "NEGATIVE")


def load_blocks(path: Path = CHARACTER_MD) -> dict[str, str]:
    """The fenced IDENTITY / FRAMING / STYLE / NEGATIVE blocks, verbatim.

    Parsed here rather than imported from mascot.py. mascot.py is marked
    obsolete and live code does not sit in an obsolete file (invariant 6); a
    copy of a twelve-line regex is a smaller cost than a dependency on a script
    whose header tells you not to reach for it.

    Missing block => raise. A prompt assembled from three of the four blocks
    would silently drop the negative lock, which is the one that keeps text out
    of the artwork.
    """
    if not path.is_file():
        raise FluxError(f"character bible missing: {path}")
    text = path.read_text(encoding="utf-8")
    found = dict(re.findall(r"```(" + "|".join(BLOCKS) + r")\n(.*?)```", text, re.S))
    missing = set(BLOCKS) - found.keys()
    if missing:
        raise FluxError(f"{path.name} is missing block(s): {', '.join(sorted(missing))}")
    return {k: v.strip() for k, v in found.items()}


def build_prompt(brief: str, blocks: dict[str, str] | None = None) -> str:
    """One prompt string: who he is, how he is framed, how he is drawn, this
    pose, and what must not appear.

    FLUX has no separate negative-prompt field, so the NEGATIVE block goes into
    the prompt as prohibitions — which is how it is already written. It goes
    LAST because that is the instruction most worth having close to the end,
    and it is never abbreviated.
    """
    brief = " ".join(brief.split())
    if not brief:
        raise FluxError("empty pose brief — expression and posture are required")
    b = blocks or load_blocks()
    return "\n\n".join([
        b["IDENTITY"],
        f"Pose for this image: {brief}.",
        b["FRAMING"],
        b["STYLE"],
        "The reference images show exactly this character. Keep his shapes, his "
        "colours, his single black brow bar and his curly black mane identical to "
        "them, and change only the pose described above.",
        b["NEGATIVE"],
    ])


# ─────────────────────────── reference images ────────────────────────────────

def _flatten_onto_key(rgba: np.ndarray, height: int = 512) -> np.ndarray:
    """Composite a transparent library pose onto the magenta key, as BGR.

    The reference has to show the model the backdrop it is being asked for as
    well as the character. Handing it a transparent PNG teaches it nothing
    about the background, and handing it one on white teaches it the wrong
    thing — white is what the previous generation attempts kept coming back
    with, and white cannot be keyed off cream-coloured artwork.
    """
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise FluxError("reference must be RGBA")
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    key = np.zeros_like(rgba[:, :, :3], dtype=np.float32)
    key[:, :] = CHROMA_BGR
    flat = (rgba[:, :, :3].astype(np.float32) * a + key * (1 - a)).astype(np.uint8)

    h, w = flat.shape[:2]
    scale = height / h
    flat = cv2.resize(flat, (max(1, int(w * scale)), height), interpolation=cv2.INTER_AREA)
    # Pad to a square of key colour: the model reads the aspect of its
    # references, and a tall sliver biases it toward a cropped figure.
    side = max(flat.shape[0], flat.shape[1]) + 48
    canvas = np.zeros((side, side, 3), np.uint8)
    canvas[:, :] = CHROMA_BGR
    y = (side - flat.shape[0]) // 2
    x = (side - flat.shape[1]) // 2
    canvas[y:y + flat.shape[0], x:x + flat.shape[1]] = flat
    return canvas


def _library_poses(manifest: Path = MANIFEST) -> list[str]:
    """Full-body, single-figure, un-mirrored poses, in manifest order.

    Mirrored copies are excluded: the mane only runs down one side of his neck,
    so a flipped Silly is subtly the wrong way round and is a bad thing to
    teach a model. Pair scenes are excluded because they contain the grey
    donkey, and a reference with two characters produces two characters.
    """
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [name for name, meta in data.get("poses", {}).items()
            if meta.get("framing") == "full"
            and meta.get("figures", 1) == 1
            and not meta.get("mirrored")]


# ─────────────────────────── posture matching ────────────────────────────────
#
# References decide the POSTURE. Measured twice on 2026-08-31, and both times
# the brief lost to the pictures: a brief asking for a lowered head and drooping
# ears came back head-up and alert, and a brief asking to tumble head over heels
# came back mid-jump. In both runs the four references were the front of the
# manifest — deadpan, clutching, serene, realising — all upright and alert, and
# that is what the model drew.
#
# So the references have to know what the brief is asking for. The risk in that
# is the one the old fixed slice was protecting against: references that change
# every run make two poses generated a week apart into two different donkeys.
# Hence ANCHORS. Half the slots never move and hold the character; the rest are
# chosen for posture. Identity comes from the constant half, staging from the
# other.
ANCHORS = ("deadpan", "explaining")

# Posture families. A brief matches a family when it uses any of its words, and
# a candidate pose matches when its description or tags do. Deliberately about
# the BODY and nothing else: matching on ordinary words would pick a pose about
# beds for any brief that mentions a bed, whatever the body in it is doing,
# which is the mistake selection already makes (see library._overlap).
POSTURE_FAMILIES = {
    "seated":   ("sitting", "sits", "seated", "sit", "perched", "cross-legged"),
    "lying":    ("lying", "lies", "lie", "flat", "face down", "on his back",
                 "sprawled", "asleep", "sleeping"),
    "curled":   ("curled", "curl", "knees", "hugging", "tucked", "foetal",
                 "huddled", "crouched", "crouching", "crouch"),
    "upright":  ("standing", "stands", "stand", "upright", "squarely", "planted"),
    "leaning":  ("leaning", "leans", "slumped", "hunched", "stooped", "bowed",
                 "drooping", "sagging"),
    "moving":   ("walking", "walks", "running", "runs", "pacing", "stepping",
                 "chasing", "fleeing", "leaving"),
    "airborne": ("jumping", "jumps", "leaping", "falling", "falls", "tumbling",
                 "flying", "mid-air", "dropped"),
    "reaching": ("reaching", "reaches", "pointing", "points", "holding up",
                 "raised", "outstretched", "extending", "offering"),
    "covering": ("covering", "covers", "hiding", "hides", "behind his hooves",
                 "over his eyes", "head in"),
}


def posture_families(text: str) -> set[str]:
    """Which body families a piece of text is talking about."""
    low = " " + " ".join((text or "").lower().split()) + " "
    return {family for family, words in POSTURE_FAMILIES.items()
            if any(w in low for w in words)}


def _descriptions(manifest: Path = MANIFEST) -> dict[str, str]:
    """What each pose's BODY is, in words, from the two places that know.

    GENERATION_PROMPTS.md carries the numbered pose lines the library was drawn
    from — "Standing straight, deadpan, staring at the viewer, arms at his
    sides" — for 115 of the poses, and they have never been read by anything.
    Poses generated from a slide brief carry the brief's own words as tags, so
    they describe their body too. Everything else contributes only its name.
    """
    out: dict[str, str] = {}
    prompts = SKILL_DIR / "mascot" / "GENERATION_PROMPTS.md"
    if prompts.is_file():
        text = prompts.read_text(encoding="utf-8")
        for poses, names in re.findall(
                r"Poses:\n((?:\d+\.[^\n]*\n)+)[\s\S]*?--names ([a-z_,0-9]+)", text):
            lines = [re.sub(r"^\d+\.\s*", "", ln).strip()
                     for ln in poses.strip().split("\n")]
            keys = names.split(",")
            if len(lines) == len(keys):
                out.update(dict(zip(keys, lines)))
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for name, meta in data.get("poses", {}).items():
            words = " ".join(meta.get("tags", []))
            out[name] = (out.get(name, "") + " " + name.replace("_", " ")
                         + " " + words).strip()
    return out


def posture_matches(brief: str, count: int, exclude: tuple[str, ...] = (),
                    manifest: Path = MANIFEST) -> list[str]:
    """Poses whose body is doing what the brief describes, best first.

    Empty when the brief names no posture at all, which is the honest answer:
    a brief that does not say what the body is doing gives nothing to match on,
    and the anchors are a better guess than a coincidence.

    Deterministic. Ties break on the name, so the same brief always draws the
    same references and two poses made a week apart stay the same donkey.
    """
    wanted = posture_families(brief)
    if not wanted:
        return []
    descriptions = _descriptions(manifest)
    brief_words = set(re.findall(r"[a-z]{4,}", brief.lower()))
    scored = []
    for name in _library_poses(manifest):
        if name in exclude:
            continue
        text = descriptions.get(name, name)
        overlap = wanted & posture_families(text)
        if not overlap:
            continue
        # Family count first, then how much of the brief's own wording the
        # description shares. Families alone rank `head_tilt` level with
        # `sitting_ledge` for a brief about legs hanging over the side of a
        # bed, and only one of those is the picture asked for.
        words = len(brief_words & set(re.findall(r"[a-z]{4,}", text.lower())))
        scored.append((-len(overlap), -words, name))
    scored.sort()
    return [name for _, _, name in scored[:count]]


def pick_references(names: list[str] | None = None, count: int = MAX_REFS,
                    library: Path = LIBRARY,
                    manifest: Path = MANIFEST,
                    brief: str = "") -> list[tuple[str, bytes]]:
    """The reference images to condition on, as (label, png bytes).

    They come from mascot/library/ and NOT from mascot/style_refs/, which is
    the obvious-looking choice and the wrong one. The four sheets in style_refs
    are 6-up grids with "1. Innocent", "2. Deadpan" printed under every cell,
    and they are head-and-shoulders only. Conditioning on them asks for exactly
    the two defects the character bible exists to prevent: baked-in caption text
    (invariant 3) and the bust framing that made every slide look identical.
    The library is what those sheets became after matting and QA — same
    character, no text, full body, one figure.

    That is not enforced by a hardcoded ban on a directory. Every reference,
    wherever it came from, goes through assert_no_text() below, and the sheets
    fail it on their own captions.
    """
    if count < 1 or count > MAX_REFS:
        raise FluxError(f"the model takes 1..{MAX_REFS} reference images, asked for {count}")

    if names:
        paths = []
        for n in names:
            p = Path(n)
            if not p.is_file():
                p = library / f"{n}.png"
            if not p.is_file():
                raise FluxError(f"reference not found: {n}")
            paths.append(p)
    else:
        available = _library_poses(manifest)
        if not available:
            raise FluxError(
                f"no full-body single-figure poses in {manifest} to use as references")
        # ANCHORS first, then posture matches, then the front of the manifest
        # to fill up. The anchors are what stops the references drifting run to
        # run; the posture slots are what stops the model drawing an alert,
        # upright donkey for a brief that asked for a lowered head — which it
        # did, twice, when every reference was upright and alert.
        chosen = [n for n in ANCHORS if n in available]
        matched = posture_matches(brief, count - len(chosen),
                                  exclude=tuple(chosen), manifest=manifest)
        chosen += matched
        for n in available:
            if len(chosen) >= count:
                break
            if n not in chosen:
                chosen.append(n)
        paths = [library / f"{n}.png" for n in chosen]
        paths = [p for p in paths if p.is_file()][:count]

    out = []
    for p in paths[:count]:
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise FluxError(f"unreadable reference: {p}")
        transparent = img.ndim == 3 and img.shape[2] == 4 and img[:, :, 3].min() < 250
        # A cutout is checked after compositing, because until then it has no
        # backdrop to be detached FROM. Anything else — a flat sheet, a photo,
        # a fully opaque PNG — is checked exactly as it sits on disk. Padding
        # such an image onto the key first would make its own background part
        # of the subject and hide every caption printed on it, which is how a
        # captioned style sheet slipped through the first time.
        flat = _flatten_onto_key(img) if transparent else img[:, :, :3]
        assert_no_text(flat, f"reference {p.name}")
        ok, buf = cv2.imencode(".png", flat)
        if not ok:
            raise FluxError(f"could not encode reference: {p}")
        out.append((p.stem, buf.tobytes()))
    if not out:
        raise FluxError("no usable reference images")
    return out


# ─────────────────────────── multipart body ──────────────────────────────────

def encode_multipart(fields: dict[str, str],
                     files: list[tuple[str, str, bytes]]) -> tuple[str, bytes]:
    """Build a multipart/form-data body by hand. Returns (content_type, body).

    This endpoint is the only one in the skill that is not plain JSON: its
    input schema is literally {"multipart": {...}} and reference images go up as
    file parts. urllib has no form encoder and the whole repo is standard
    library on purpose, so it is thirty lines here instead of a dependency.

    Everything is written as bytes with explicit CRLF. A stray "\n" between the
    headers and the body of a part is accepted by some servers and turns into a
    400 from others, which is not a thing to debug twice.
    """
    boundary = "----suresilly" + secrets.token_hex(16)
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts += [
            f"--{boundary}".encode(), crlf,
            f'Content-Disposition: form-data; name="{name}"'.encode(), crlf, crlf,
            str(value).encode("utf-8"), crlf,
        ]
    for name, filename, blob in files:
        parts += [
            f"--{boundary}".encode(), crlf,
            (f'Content-Disposition: form-data; name="{name}"; '
             f'filename="{filename}"').encode(), crlf,
            b"Content-Type: image/png", crlf, crlf,
            blob, crlf,
        ]
    parts += [f"--{boundary}--".encode(), crlf]
    return f"multipart/form-data; boundary={boundary}", b"".join(parts)


# ─────────────────────────── neuron ledger ───────────────────────────────────

def estimate_neurons(width: int, height: int, refs: int) -> float:
    """What one call is RESERVED at: the published per-tile rate.

    A four-reference 1024x1024 pose books at about 126 neurons — 104.2 for the
    four output tiles and 5.37 for each reference. The response header claims
    21.48, which is exactly the reference half and nothing for the frame. See
    the note above NEURONS_PER_MEGAPIXEL for why the frame is booked anyway."""
    megapixels = (width * height) / (1024 * 1024)
    return NEURONS_PER_MEGAPIXEL * megapixels + NEURONS_PER_REFERENCE * refs



def credentials() -> tuple[str, str]:
    """Reuses llm.py's resolution: environment, then .env.local, then the two
    config files this repo has historically kept keys in. One implementation of
    "where are the keys", not two."""
    account = resolve_key("CLOUDFLARE_ACCOUNT_ID")
    token = resolve_key("CLOUDFLARE_API_TOKEN")
    if not (account and token):
        raise FluxError(
            "no Cloudflare credentials. Need CLOUDFLARE_ACCOUNT_ID and "
            "CLOUDFLARE_API_TOKEN in the environment or in .env.local.")
    return account, token


def generate(prompt: str, refs: list[tuple[str, bytes]], *,
             width: int = 1024, height: int = 1024, seed: int | None = None,
             steps: int | None = None,
             account: str | None = None,
             token: str | None = None,
             timeout: int = TIMEOUT) -> tuple[bytes, float | None]:
    """One image. Returns (image bytes, neurons billed or None).

    Every failure raises; none returns None for the image.

    The reference images go up as input_image_0 .. input_image_3, which is the
    whole reason for this model: prompt-only generation of a specific cartoon
    character does not work, and four pictures of him is the difference between
    "a green donkey" and "Silly".
    """
    if not refs:
        raise FluxError("refusing to generate with no reference images — a prompt "
                        "alone does not reconstruct the character")
    if len(refs) > MAX_REFS:
        raise FluxError(f"{len(refs)} references given, the model takes {MAX_REFS}")

    if account is None or token is None:
        account, token = credentials()

    fields = {"prompt": prompt, "width": str(width), "height": str(height)}
    if seed is not None:
        fields["seed"] = str(seed)
    if steps is not None:
        fields["num_steps"] = str(steps)
    files = [(f"input_image_{i}", f"ref_{i}_{label}.png", blob)
             for i, (label, blob) in enumerate(refs)]

    content_type, body = encode_multipart(fields, files)
    request = urllib.request.Request(
        RUN_URL.format(account=account, model=MODEL),
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            # Workers AI sits behind Cloudflare's own edge, which answers the
            # default "Python-urllib" with a 403 that reads exactly like an
            # auth failure. llm.py learned this the expensive way.
            "User-Agent": "suresilly-carousel/3.0 (+https://instagram.com/suresilly)",
            "Accept": "application/json",
        })

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            # Workers AI reports the real cost of the call on the way out. This
            # is the only honest number in the whole cost model.
            billed = response.headers.get("cf-ai-neurons")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        # The token is never in the message. It is not in the body either, but
        # this is the one place it would be easy to leak by echoing headers.
        raise FluxError(f"HTTP {exc.code} from Workers AI: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FluxError(f"could not reach Workers AI: {exc.reason}") from exc

    try:
        neurons = float(billed) if billed else None
    except ValueError:
        neurons = None
    return decode_image(raw), neurons


def image_suffix(blob: bytes) -> str:
    """The extension the bytes actually deserve.

    This model returns JPEG. It returns JPEG whatever you put in output_format
    — that field was passed as "png" on a live call and the body still came
    back with an SOI marker. Writing JPEG bytes into a .png would work, because
    cv2.imread sniffs content and import_poses.py globs both extensions, and it
    would still be a lie on disk that somebody debugs later.
    """
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if blob[:3] == b"\xff\xd8\xff":
        return ".jpg"
    raise FluxError("the response is neither a PNG nor a JPEG")


def decode_image(raw: bytes) -> bytes:
    """Pull the image bytes out of the response, or say precisely what came back.

    The documented output is {"result": {"image": "<base64>"}} and the base64
    decodes to a JPEG. A body that is already an image is accepted too, because
    Workers AI returns raw binary for some image models and a silent failure
    here would look like a corrupt file three functions later.
    """
    if raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:3] == b"\xff\xd8\xff":
        return raw
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FluxError(f"unparseable response ({len(raw)} bytes)") from exc

    if isinstance(data, dict) and not data.get("success", True):
        errors = data.get("errors") or data.get("messages") or []
        raise FluxError(f"Workers AI refused: {json.dumps(errors)[:400]}")

    image = (data.get("result") or {}).get("image") if isinstance(data, dict) else None
    if not image:
        raise FluxError(f"no image in response: {json.dumps(data)[:300]}")
    try:
        return base64.b64decode(image, validate=True)
    except Exception as exc:
        raise FluxError("result.image was not valid base64") from exc


# ─────────────────────────── the gates ───────────────────────────────────────

def backdrop_fraction(bgr: np.ndarray) -> float:
    """How much of the frame is the magenta key. Nothing downstream works
    without it: import_poses.py decides between chroma and paper matting on
    border saturation, and a pose on a pale studio background is silently
    matted as paper, which eats the cream muzzle."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    key = cv2.cvtColor(np.uint8([[CHROMA_BGR]]), cv2.COLOR_BGR2HSV)[0, 0, 0]
    dh = np.abs(hsv[:, :, 0].astype(np.int16) - int(key))
    dh = np.minimum(dh, 180 - dh)
    mask = (dh <= 22) & (hsv[:, :, 1] >= 70) & (hsv[:, :, 2] >= 40)
    return float(mask.mean())


MIN_BACKDROP = 0.25


def check(png: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Every gate a freshly generated pose has to pass. Raises QAFailure, and a
    caller that catches it must write nothing.

    Returns (corrected raw frame, matted rgba). The FIRST is what gets written:
    the palette correction has to reach the file, or the gates would be judging
    a picture nobody ever sees.

    Order matters. Text is checked on the raw frame first, because matting a
    captioned image throws the caption away and then the artwork looks clean.
    """
    arr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise QAFailure("decode: the model returned something that is not an image")

    frac = backdrop_fraction(arr)
    if frac < MIN_BACKDROP:
        raise QAFailure(
            f"backdrop: only {frac:.0%} of the frame is the {CHROMA_HEX} key "
            f"(need {MIN_BACKDROP:.0%}) — the model ignored the backdrop "
            f"instruction and this cannot be matted")

    assert_no_text(arr, "generated artwork")

    # Colour is corrected BEFORE matting and before the remaining gates, so the
    # frame that is judged is the frame that gets written.
    arr = correct_palette(arr)

    rgba = tight_crop(drop_neighbour_bleed(auto_chroma_matte(arr)))
    assert_has_pupils(rgba, "generated artwork")
    # The strict configuration, which is the right one here and would be wrong
    # in import_poses.py. There a sheet cell is a tight crop of a grid, so ear
    # tips legitimately touch an edge and a detached fragment is normal. Here
    # the model composed the whole frame to our instructions, so an edge touch
    # means a clipped figure and a second blob means a second thing in the
    # picture. Same gates, tightened — never loosened.
    qa(rgba, src_shape=arr.shape[:2], allow_detached=False, strict_framing=True,
       key_bgr=detect_key_colour(arr))
    return arr, rgba


# ─────────────────────────── driver ──────────────────────────────────────────

def make_pose(name: str, brief: str, out_dir: Path, *, refs: list[tuple[str, bytes]],
              ledger: Ledger, width: int = 1024, height: int = 1024,
              seed: int | None = None, steps: int | None = None,
              account: str | None = None, token: str | None = None) -> Path:
    """Generate one pose, gate it, and write the RAW frame for import_poses.py.

    The raw magenta-backed frame is what lands on disk, not the matted cutout.
    import_poses.py owns matting and naming and the manifest, it already works,
    and a second writer into mascot/library/ is how two subtly different
    libraries happen. The matte done here is only ever to judge the image.
    """
    prompt = build_prompt(brief)
    reserved = estimate_neurons(width, height, len(refs))
    ledger.check(reserved)
    # Booked before the call: a refused or gated image was still generated and
    # still billed, and a ledger that only counts successes walks you into a
    # 429 in the middle of a batch.
    ledger.spend(reserved, note=name)

    blob, billed = generate(prompt, refs, width=width, height=height, seed=seed,
                            steps=steps, account=account, token=token)
    ledger.reconcile(reserved, billed, note=name)
    corrected, _ = check(blob)       # raises QAFailure; nothing written if it does

    out_dir.mkdir(parents=True, exist_ok=True)
    # PNG, not the suffix the model's bytes imply. Two reasons, and the second
    # is the one that matters: the frame has been colour-corrected so it must be
    # re-encoded anyway, and this endpoint returns JPEG whatever we ask for.
    # JPEG chroma subsampling leaves a half-magenta fringe along every green
    # edge, which is exactly what cutout.py's key_residue gate then objects to.
    # Re-encoding lossless removes a whole class of import rejection.
    dest = out_dir / f"{name}.png"
    ok, buf = cv2.imencode(".png", corrected)
    if not ok:
        raise QAFailure(f"could not encode {name} as PNG")
    dest.write_bytes(buf.tobytes())
    return dest


def parse_briefs(args) -> list[tuple[str, str]]:
    if args.briefs:
        rows = json.loads(Path(args.briefs).read_text(encoding="utf-8"))
        if not isinstance(rows, dict) or not rows:
            raise FluxError(f"{args.briefs} must be a non-empty object of name -> brief")
        return list(rows.items())
    if not (args.name and args.brief):
        raise FluxError("give --name and --brief, or --briefs pointing at a JSON object")
    return [(args.name, args.brief)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="pose name, becomes <name>.png in the inbox")
    ap.add_argument("--brief", help="expression and posture, in the CHARACTER.md vocabulary")
    ap.add_argument("--briefs", help="JSON file of {name: brief} for a batch")
    ap.add_argument("--out", default=str(DEFAULT_OUT),
                    help=f"where the raw frames go (default {DEFAULT_OUT})")
    ap.add_argument("--ref", action="append",
                    help="reference pose name or path; repeatable, max 4")
    ap.add_argument("--refs", type=int, default=MAX_REFS,
                    help=f"how many library poses to condition on (1..{MAX_REFS})")
    ap.add_argument("--size", type=int, default=1024, help="square output edge in px")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--budget", type=float, default=DEFAULT_BUDGET,
                    help=f"daily neuron ceiling for this tool (default {DEFAULT_BUDGET})")
    ap.add_argument("--ledger", help=f"where spend is recorded (default {LEDGER_PATH})")
    ap.add_argument("--print-prompt", action="store_true",
                    help="show the assembled prompt and exit, no network")
    ap.add_argument("--dry-run", action="store_true",
                    help="cost the batch and check the references, call nothing")
    a = ap.parse_args(argv)

    try:
        jobs = parse_briefs(a)
        if a.print_prompt:
            for name, brief in jobs:
                print(f"--- {name} ---\n{build_prompt(brief)}\n")
            return 0

        refs = pick_references(a.ref, count=len(a.ref) if a.ref else a.refs)
        ledger = Ledger(a.ledger, budget=a.budget)
        per_call = estimate_neurons(a.size, a.size, len(refs))
    except (FluxError, BudgetExceeded, QAFailure) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"model      {MODEL}  (apache-2.0)")
    print(f"references {', '.join(label for label, _ in refs)}")
    print(f"cost       {per_call:.1f} neurons/pose reserved x {len(jobs)} = "
          f"{per_call * len(jobs):.0f}; {ledger.remaining():.0f} left of "
          f"today's {ledger.budget:.0f} (topped up if a call bills more)")
    if a.dry_run:
        print("dry run — nothing called, nothing written")
        return 0

    out_dir = Path(a.out)
    written, failed = [], []
    for name, brief in jobs:
        try:
            dest = make_pose(name, brief, out_dir, refs=refs, ledger=ledger,
                             width=a.size, height=a.size, seed=a.seed, steps=a.steps)
        except BudgetExceeded as exc:
            failed.append((name, str(exc)))
            print(f"  ✗ {name:20s} {exc}")
            break
        except (FluxError, BudgetExceeded, QAFailure) as exc:
            failed.append((name, str(exc)))
            print(f"  ✗ {name:20s} {str(exc)[:100]}")
            continue
        print(f"  ✓ {name:20s} {dest}")
        written.append(name)
        time.sleep(1.0)

    print(f"\n{len(written)} written, {len(failed)} rejected "
          f"({ledger.spent():.0f} neurons spent today)")
    if failed:
        # Loud on purpose. A partial batch that exits 0 gets imported without
        # anybody noticing three poses are missing.
        print("REJECTED — nothing was written for these:", file=sys.stderr)
        for name, why in failed:
            print(f"  - {name}: {why}", file=sys.stderr)
    if written:
        # No --names: import_poses.py names a folder of singles from their
        # filenames, which is exactly the name given here.
        print(f"\nNext: import_poses.py {out_dir} --fullbody")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
