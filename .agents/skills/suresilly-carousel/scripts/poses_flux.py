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
from cutout import QAFailure, auto_chroma_matte, detect_key_hue, qa  # noqa: E402
from imaging import drop_neighbour_bleed, tight_crop  # noqa: E402
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
# visibly nicer pictures. That is the trap. Its licence forbids commercial use,
# and every pose made with it would be unshippable. If output quality is not
# good enough, the answer is a better prompt, better references, or not using
# this tool — never a different row in that table.
MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
RUN_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"

# The backdrop the whole downstream pipeline expects. Magenta because Silly is
# green: a green key would eat the character. cutout.py detects the key rather
# than assuming it, but the prompt still has to ask for the right one.
CHROMA_HEX = "#FF00FF"
CHROMA_BGR = (255, 0, 255)

MAX_REFS = 4                # the model accepts input_image_0 .. input_image_3
TIMEOUT = 180               # a 1024px generation is slow; this is not a chat call

# ── neuron budget ────────────────────────────────────────────────────────────
#
# Workers AI gives 10,000 neurons/day free, per ACCOUNT — the same account
# llm.py bills its third text vendor against. So this tool may not spend the
# lot: whatever it takes, the writer and the critic no longer have.
#
# Two numbers disagree about what a call costs, by a factor of ten, and this
# module believes the expensive one.
#
#   PUBLISHED   ~104 neurons for a 1024x1024 frame, ~21 for references.
#   MEASURED    every response carries a cf-ai-neurons header. Five calls on
#               2026-08-31 at 1024x1024 reported 5.37 neurons per reference
#               image and nothing at all for the output frame:
#                   1 ref -> 5.37    2 refs -> 10.74    4 refs -> 21.48
#               Exactly linear, three independent confirmations.
#
# One of those is wrong and there is no way from here to tell which. If the
# header is right, believing the published rate costs some throughput. If the
# header undercounts — it plainly does not bill the output frame, so something
# is missing from it — then believing the header runs ten times over the free
# allowance and starts spending the user's money.
#
# So: RESERVE at the published rate, which is the pessimistic one and does not
# depend on the header being complete. Reconcile against the header only when
# the header is HIGHER than the reservation. Reconciliation can raise the
# recorded spend and can never lower it, which means a surprise expensive call
# is caught and a suspiciously cheap one buys nothing. Same rule as everywhere
# else here: "we could not check" must never come out the same as "we checked".
NEURONS_PER_MEGAPIXEL = 104.0     # published, per 1024x1024-equivalent output
NEURONS_PER_REFERENCE = 21.0      # published, per reference image
FREE_DAILY_NEURONS = 10_000
DEFAULT_BUDGET = 6_000            # 60%: the text vendors draw on the same pot

LEDGER_PATH = Path(os.environ.get(
    "SS_FLUX_LEDGER", REPO_DIR / "state" / "flux_neurons.json"))


class FluxError(Exception):
    """The generation call did not produce usable artwork."""


class BudgetExceeded(FluxError):
    """Refusing to spend past the daily neuron budget."""


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


def backdrop_mask(bgr: np.ndarray, tolerance: int = 44) -> np.ndarray:
    """Pixels close to the frame's border colour — the flat backdrop.

    Border median, the same trick cutout.py and import_poses.py both use, so it
    works on the magenta key we ask for, on the cream of the old style sheets,
    and on whatever a model hands back instead.
    """
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
    med = np.median(border, axis=0)
    return (np.abs(bgr.astype(np.int16) - med).max(2) <= tolerance)


def glyph_runs(bgr: np.ndarray) -> list[list[tuple[int, int, int, int]]]:
    """Runs of small, similar-height marks sitting on one baseline, detached
    from the figure: the shape of text. Each run is a list of bounding boxes.

    Two conditions, and the second one is what makes this usable.

    Size and alignment alone are not enough. Silly's mane is dense black
    corkscrew curls, his hooves are four small black shapes and his ear insides
    are two more — small dark blobs of near-identical height, and the hooves
    genuinely do line up along the bottom of the frame. A detector that looks
    only at shape calls 82 of the 181 poses in the library "text".

    So a mark counts only if it is a SEPARATE PIECE OF PICTURE: its own
    connected region of non-backdrop, not part of the main figure. A caption is
    printed on the background with clear space round every letter. A hoof is
    attached to a leg, and a mane curl to a head. That condition takes the
    false-positive rate on the real 180-pose library to zero while still
    catching every caption on the four old style sheets.

    Working on non-backdrop regions rather than on dark pixels also means the
    colour of the lettering does not matter. A pale watermark is as detectable
    as a black caption.

    cutout.qa() has a cousin of this that only looks BELOW 80% of the frame,
    because that is where a sheet cell's caption lives and looking higher would
    reject legitimate detached artwork in imported poses. Here the composition
    came from a model we prompted, so the whole frame is fair game: a watermark
    across the middle or a signature in a corner is just as fatal and cutout's
    version would not see either. Superset, never a relaxation.
    """
    H, W = bgr.shape[:2]
    total = float(H * W)
    subject = (~backdrop_mask(bgr)).astype(np.uint8)
    subject = cv2.morphologyEx(subject, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(subject, 8)
    if n <= 2:
        return []
    main = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])

    glyphs = []
    for i in range(1, n):
        if i == main:
            continue
        area = stats[i, cv2.CC_STAT_AREA]
        h, w = stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_WIDTH]
        top, left = stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_LEFT]
        if not (0.00002 * total <= area <= 0.006 * total):
            continue
        if not (0.008 * H <= h <= 0.12 * H):
            continue
        if w > 0.25 * W or w > 6 * h:
            continue
        glyphs.append((top + h, h, left, (left, top, w, h)))

    runs = []
    used: set[tuple[int, int, int, int]] = set()
    for base, h, _, box in sorted(glyphs):
        if box in used:
            continue
        row = [g for g in glyphs if abs(g[0] - base) <= max(3, 0.5 * h)]
        if len(row) < 3:
            continue
        heights = sorted(g[1] for g in row)
        med = heights[len(heights) // 2]
        similar = [g for g in row if med / 2.0 <= g[1] <= med * 2.0]
        xs = sorted(g[2] for g in similar)          # spread across x, not a stack
        if len(similar) >= 3 and (xs[-1] - xs[0]) >= 2 * med:
            runs.append([g[3] for g in similar])
            used.update(g[3] for g in similar)
    return runs


def assert_no_text(bgr: np.ndarray, what: str) -> None:
    """Invariant 3. Raises QAFailure — it never warns.

    Runs on the frame BEFORE matting, because matting a captioned image throws
    the caption away and then the artwork looks clean. cutout.qa()'s component
    gates are the net that catches text after matting. Both have to hold.
    """
    runs = glyph_runs(bgr)
    if runs:
        raise QAFailure(
            f"no_text: {what} contains {len(runs)} run(s) of "
            f"{sum(len(r) for r in runs)} detached, similar-height marks on a "
            f"shared baseline — this is what lettering looks like, and no "
            f"mascot artwork may carry any")


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


def pick_references(names: list[str] | None = None, count: int = MAX_REFS,
                    library: Path = LIBRARY,
                    manifest: Path = MANIFEST) -> list[tuple[str, bytes]]:
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
        # A fixed, front-of-manifest slice on purpose: references are the one
        # input that must not drift run to run, or two poses generated a week
        # apart are two different donkeys.
        paths = [library / f"{n}.png" for n in available]
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
    """What one call is RESERVED at: the published rate, which is the
    pessimistic one. A four-reference 1024x1024 pose books at 188 neurons and
    the response header claims 21.48. See the note above NEURONS_PER_MEGAPIXEL
    for why the expensive number is the one that governs."""
    megapixels = (width * height) / (1024 * 1024)
    return NEURONS_PER_MEGAPIXEL * megapixels + NEURONS_PER_REFERENCE * refs


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Ledger:
    """What this tool has spent today, on disk, so two runs cannot both think
    they have the whole allowance.

    Keyed on the UTC date because that is when Cloudflare's allowance rolls
    over. Spend is recorded BEFORE the call and never refunded on failure: a
    refused image is an image you were still billed for, and a ledger that only
    counts successes will walk you straight into a 429 in the middle of a batch.
    """

    def __init__(self, path: Path | str | None = None,
                 budget: float = DEFAULT_BUDGET):
        # Resolved here rather than defaulted in the signature, which binds the
        # module constant once at import and then ignores every attempt to
        # point it somewhere else. A test suite that cannot redirect this file
        # writes its arithmetic into the repo's real ledger, and the next run
        # believes it has already spent the afternoon.
        self.path = Path(path) if path is not None else LEDGER_PATH
        self.budget = float(budget)
        if self.budget > FREE_DAILY_NEURONS:
            raise BudgetExceeded(
                f"budget {self.budget:.0f} exceeds the free daily allowance of "
                f"{FREE_DAILY_NEURONS} neurons — this tool does not spend money")

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def spent(self) -> float:
        day = self._read().get(_today())
        return float(day.get("neurons", 0.0)) if isinstance(day, dict) else 0.0

    def remaining(self) -> float:
        return max(0.0, self.budget - self.spent())

    def check(self, cost: float) -> None:
        if cost > self.remaining():
            raise BudgetExceeded(
                f"this call is booked at {cost:.0f} neurons and only "
                f"{self.remaining():.0f} of today's {self.budget:.0f} budget are left "
                f"(the account's free allowance is {FREE_DAILY_NEURONS}/day and the "
                f"text vendors draw on it too). Try again tomorrow.")

    def _write(self, neurons_delta: float, calls_delta: int, note: str = "") -> None:
        data = self._read()
        day = data.get(_today())
        day = day if isinstance(day, dict) else {"neurons": 0.0, "calls": 0}
        day["neurons"] = max(0.0, round(float(day.get("neurons", 0.0)) + neurons_delta, 2))
        day["calls"] = int(day.get("calls", 0)) + calls_delta
        if note:
            day["last"] = note
        data[_today()] = day
        # Keep a fortnight; the file is a rate limiter, not an archive.
        for stale in sorted(data)[:-14]:
            data.pop(stale, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    def spend(self, cost: float, note: str = "") -> None:
        self._write(cost, 1, note)

    def reconcile(self, reserved: float, actual: float | None, note: str = "") -> None:
        """Top the reservation up if Cloudflare billed MORE than we booked.

        One-directional on purpose. The cf-ai-neurons header reports about a
        tenth of the published rate and visibly does not bill the output frame,
        so it is trustworthy as a floor and not as a total: a call that comes
        back dearer than expected is news worth acting on, and one that comes
        back cheap buys no extra throughput.

        actual is None when the response carried no header at all. Then the
        reservation stands, because "we could not check" must never come out
        the same as "we checked".
        """
        if actual is None or actual <= reserved:
            return
        self._write(actual - reserved, 0, note)


# ─────────────────────────── the call ────────────────────────────────────────

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
             token: str | None = None) -> tuple[bytes, float | None]:
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
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
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


# ── palette correction ───────────────────────────────────────────────────────
#
# Measured, not guessed. Across the first four generated poses, against the four
# library poses used as references:
#
#     body green     library saturation 49-52   generated 30-41
#     muzzle/belly   library hue 38-40 deg      generated 22-28 deg
#
# So the model holds the SHAPES from the references and drifts the COLOUR: a
# sage body instead of the brand green, and a blush muzzle instead of a buttery
# one. Consistent in one direction, which is what makes it correctable.
#
# This is a colour correction and nothing more. It moves saturation and hue of
# pixels already in the right family; it cannot repair a wrong shape and must
# never be asked to. It runs BEFORE the gates, so what is judged and what is
# written are the same picture.
LIBRARY_GREEN_SAT = 0.51        # median of the library reference poses
LIBRARY_CREAM_HUE = 39.0        # degrees, ditto
GREEN_HUE_RANGE = (35, 95)      # OpenCV H is 0-179, so this is 70-190 deg
CREAM_MIN_V, CREAM_MAX_S = 180, 120
EYE_MAX_SAT = 45          # an eye white is white; the cream muzzle is 73-94


def correct_palette(bgr: np.ndarray) -> np.ndarray:
    """Pull the body green and the cream back onto the brand palette.

    Returns a new frame. The magenta key is untouched on purpose — everything
    downstream mattes against it and shifting it would break the one thing that
    is already right.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    green = (h > GREEN_HUE_RANGE[0]) & (h < GREEN_HUE_RANGE[1]) & (sat > 25)
    if green.sum() <= 500:
        green = np.zeros_like(green)
    else:
        current = float(np.median(sat[green])) / 255.0
        if current > 0.01:
            sat[green] = np.clip(sat[green] * (LIBRARY_GREEN_SAT / current), 0, 255)

    # The cream is pale and barely saturated, which is what separates it from
    # both the green and the magenta without needing a mask from anywhere else.
    cream = (val > CREAM_MIN_V) & (sat < CREAM_MAX_S) & (sat > 12) & (h < 45)
    if cream.sum() <= 500:
        cream = np.zeros_like(cream)
    else:
        h[cream] += (LIBRARY_CREAM_HUE / 2.0) - float(np.median(h[cream]))
        h[cream] = np.clip(h[cream], 0, 179)

    fixed = cv2.cvtColor(np.stack([h, sat, val], -1).astype(np.uint8),
                         cv2.COLOR_HSV2BGR)

    # Write back ONLY the pixels we meant to change. A BGR->HSV->BGR round trip
    # is not lossless — it moved the magenta key from 255 to 254 — and while one
    # level is nothing to the eye, cutout.py's key_residue gate measures exactly
    # that kind of thing. Compositing on the masks keeps every untouched pixel
    # byte-identical, so the correction cannot cost us an import rejection.
    touched = (green | cream)[..., None]
    return np.where(touched, fixed, bgr).astype(np.uint8)


def assert_has_pupils(rgba: np.ndarray, what: str) -> None:
    """Refuse a pose whose eyes came back blank.

    Two of the first four generations had white eyes with no pupil at all. It is
    the single most obvious way a generated pose reads as wrong beside a library
    one, and it is cheap to detect: Silly's eyes are large white blobs, and a
    correct eye has a dark island inside its own bounding box.

    So: find the white regions in the upper half of the figure that are the
    right size to be eyes, and require a dark core inside at least one. One is
    enough — a profile or a wink legitimately shows a single eye, and a gate
    that demanded two would refuse good poses.
    """
    if rgba.shape[2] < 4:
        return
    solid = rgba[..., 3] > 200
    bgr = rgba[..., :3]
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1]
    height, width = grey.shape
    upper = np.zeros_like(solid)
    upper[: int(height * 0.62)] = True          # the head, generously

    # An eye white is WHITE: near-zero saturation. The cream muzzle is bright
    # too — and measured across the library it sits at saturation 73-94, so a
    # brightness-only mask finds the muzzle, decides it is a blank eye, and
    # refuses a perfectly good pose. That is what happened: cheering, relieved,
    # guarded, floor_slumped and cheering_m all have closed or curved eyes, so
    # the muzzle was the only bright blob and none of them had a pupil in it.
    whites = ((grey > 200) & (sat < EYE_MAX_SAT) & solid & upper).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(whites, 8)
    figure_area = max(int(solid.sum()), 1)

    eyes, with_pupil = 0, 0
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if not (0.0008 * figure_area < area < 0.06 * figure_area):
            continue
        if w < 4 or h < 4 or not (0.35 < w / h < 2.8):
            continue
        eyes += 1
        # A pupil is a dark island INSIDE the white blob's own box. Looking only
        # inside the box is what stops the brow bar above the eye counting.
        patch = grey[y:y + h, x:x + w]
        inner = patch[max(1, h // 6):h - max(1, h // 6), max(1, w // 6):w - max(1, w // 6)]
        if inner.size and (inner < 110).sum() >= max(4, int(0.04 * inner.size)):
            with_pupil += 1

    if eyes and not with_pupil:
        raise QAFailure(
            f"pupils: {what} has {eyes} blank eye(s) with no pupil. The model "
            f"does this often and it is the loudest way a generated pose reads "
            f"as wrong beside a library one. Re-roll with another seed.")


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
       key_hue=detect_key_hue(arr))
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
    except (FluxError, QAFailure) as exc:
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
        except (FluxError, QAFailure) as exc:
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
