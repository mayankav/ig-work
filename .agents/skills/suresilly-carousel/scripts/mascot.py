#!/usr/bin/env python3
"""
mascot.py — OBSOLETE. Paid on-the-fly generation. Not the working path.

    ┌──────────────────────────────────────────────────────────────────────┐
    │  NOT IN USE. Do not reach for this script.                           │
    │                                                                      │
    │  Mascots come from mascot/library/ via scripts/import_poses.py.      │
    │  Build a carousel with:  build.py <script.md>                        │
    │                                                                      │
    │  This file needs a BILLED Google AI Studio project. Gemini image     │
    │  generation has no free tier at all — every Nano Banana model is     │
    │  capped at zero requests, so this returns 429 and writes nothing.    │
    │  Cost if enabled: about $0.43 per nine-slide deck.                   │
    │                                                                      │
    │  Kept because it works the moment billing is switched on, and        │
    │  because it is the only route to a pose the library does not hold.   │
    └──────────────────────────────────────────────────────────────────────┘

The matting and quality gates it used to own now live in cutout.py, which IS
live — import_poses.py depends on them for every import.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from cutout import QAFailure, auto_chroma_matte, detect_key_hue, qa

SKILL_DIR = Path(__file__).resolve().parent.parent
CHARACTER_MD = SKILL_DIR / "mascot" / "CHARACTER.md"
MASTER_PNG = SKILL_DIR / "mascot" / "master" / "silly_master.png"
STYLE_REFS = SKILL_DIR / "mascot" / "style_refs"

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL_PRO = "gemini-3-pro-image"        # $0.134/img — master reference only
MODEL_FLASH = "gemini-2.5-flash-image"  # $0.039/img — the per-slide workhorse

EMPERO_BASE = "https://free.empero.org/v1"
MODEL_EMPERO_PRO = "glm-5.3-flash"      # Empero community model — text only
MODEL_EMPERO_FLASH = "qwen3.8-flash"    # Empero community model — text only

CHROMA_KEY_HEX = "#FF00FF"          # magenta: opposite of the character
MAX_ATTEMPTS = 3


# ───────────────────────────── auth ──────────────────────────────

def resolve_api_key() -> str:
    """env → Claude MCP config → Antigravity MCP config → Empero key → actionable error."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key.strip()

    emperor_key = os.environ.get("EMPERO_API_KEY")
    if emperor_key:
        return emperor_key.strip()

    candidates = [
        (Path.home() / ".claude.json", ("mcpServers", "gemini-mcp", "env", "GEMINI_API_KEY")),
        (Path.home() / ".gemini" / "config" / "mcp_config.json",
         ("mcpServers", "gemini-mcp", "env", "GEMINI_API_KEY")),
    ]
    for path, keys in candidates:
        if not path.is_file():
            continue
        try:
            node = json.loads(path.read_text())
            for k in keys:
                node = node[k]
            if isinstance(node, str) and node.strip():
                return node.strip()
        except (KeyError, TypeError, json.JSONDecodeError):
            continue

    sys.exit(
        "ERROR: no Gemini API key found.\n"
        "Fix (any one):\n"
        "  export GEMINI_API_KEY='...'            # from https://aistudio.google.com/apikey\n"
        "  add it to ~/.claude.json under mcpServers.gemini-mcp.env\n"
        "  add it to ~/.gemini/config/mcp_config.json\n"
        "  or: export EMPERO_API_KEY='free'       # Empero free community endpoint\n"
        "       (https://free.empero.org/v1, any API key accepted)"
    )


# ─────────────────────── character bible ─────────────────────────

def load_blocks() -> dict[str, str]:
    """Read the fenced IDENTITY / FRAMING / STYLE / NEGATIVE blocks."""
    if not CHARACTER_MD.is_file():
        sys.exit(f"ERROR: character bible missing: {CHARACTER_MD}")
    text = CHARACTER_MD.read_text(encoding="utf-8")
    blocks = dict(re.findall(r"```(IDENTITY|FRAMING|STYLE|NEGATIVE)\n(.*?)```", text, re.S))
    missing = {"IDENTITY", "FRAMING", "STYLE", "NEGATIVE"} - blocks.keys()
    if missing:
        sys.exit(f"ERROR: {CHARACTER_MD.name} is missing block(s): {', '.join(sorted(missing))}")
    return {k: v.strip() for k, v in blocks.items()}


def default_briefs() -> dict[str, str]:
    """Role → fallback brief, parsed from the table at the end of CHARACTER.md."""
    text = CHARACTER_MD.read_text(encoding="utf-8")
    tail = text.split("### Default briefs by slide role")[-1]
    out = {}
    for row in re.findall(r"^\|\s*([a-z]+)\s*\|\s*(.+?)\s*\|\s*$", tail, re.M):
        role, brief = row
        if role != "role":
            out[role] = brief
    return out


def build_prompt(brief: str, blocks: dict[str, str]) -> str:
    return (
        f"{blocks['IDENTITY']}\n\n"
        f"POSE FOR THIS IMAGE: {brief.strip().rstrip('.')}.\n\n"
        f"{blocks['FRAMING']}\n\n"
        f"{blocks['STYLE']}\n\n"
        f"{blocks['NEGATIVE']}"
    )


# ───────────────────────── generation ────────────────────────────

def _part_for(path: Path) -> dict:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {"inline_data": {"mime_type": mime,
                            "data": base64.b64encode(path.read_bytes()).decode()}}


def generate_raw(prompt: str, refs: list[Path], *, model: str, seed: int,
                 image_size: str = "1K", api_key: str | None = None) -> bytes:
    """One REST call. Returns raw image bytes as the model produced them."""
    api_key = api_key or resolve_api_key()
    parts: list[dict] = [{"text": prompt}]
    parts += [_part_for(p) for p in refs if p.is_file()]

    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "1:1", "imageSize": image_size},
            "seed": seed,
        },
    }

    req = urllib.request.Request(
        f"{API_BASE}/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )

    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            last_err = f"HTTP {e.code}: {detail}"
            if e.code == 429 and "free_tier" in detail:
                sys.exit(
                    "ERROR: this Gemini API key has no image-generation quota.\n"
                    "Every Nano Banana model is capped at 0 requests on the free tier.\n"
                    "Fix: enable billing on the Google AI Studio project that owns this key\n"
                    "     (https://aistudio.google.com/apikey -> the key's Cloud project).\n"
                    "Meanwhile: build.py --no-mascot renders copy and layout without Silly.")
            if e.code in (429, 500, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            sys.exit(f"ERROR: Gemini request failed — {last_err}")
        except urllib.error.URLError as e:
            last_err = str(e)
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            sys.exit(f"ERROR: could not reach Gemini — {last_err}")

    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])

    reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
    sys.exit(f"ERROR: Gemini returned no image (reason: {reason}). Try rewording the brief.")


# ──────────────────────────── matting ────────────────────────────

def chroma_cutout(raw: bytes) -> np.ndarray:
    """Model output bytes -> tightly cropped BGRA."""
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        sys.exit("ERROR: model returned bytes that are not a decodable image")
    out = auto_chroma_matte(arr)

    ys, xs = np.where(out[:, :, 3] > 20)
    if len(ys) == 0:
        sys.exit("ERROR: cutout removed the entire image (the key matched the character)")
    pad = 4
    t, b = max(0, ys.min() - pad), min(out.shape[0], ys.max() + pad)
    l, r = max(0, xs.min() - pad), min(out.shape[1], xs.max() + pad)
    return out[t:b, l:r]


# ──────────────────────── QA gates ───────────────────────────────

# ──────────────────────── public API ─────────────────────────────

def render_pose(brief: str, out_path: Path, *, model: str = MODEL_FLASH,
                seed: int = 7, refs: list[Path] | None = None,
                api_key: str | None = None, verbose: bool = True) -> Path:
    """Generate → matte → QA → save. Rerolls on QA failure, then hard-errors."""
    blocks = load_blocks()
    prompt = build_prompt(brief, blocks)
    if refs is None:
        refs = [MASTER_PNG] if MASTER_PNG.is_file() else sorted(STYLE_REFS.glob("*"))[:2]

    failures = []
    for attempt in range(MAX_ATTEMPTS):
        s = seed + attempt * 1013
        if verbose:
            print(f"    · generating (attempt {attempt + 1}/{MAX_ATTEMPTS}, seed {s})…", flush=True)
        raw = generate_raw(prompt, refs, model=model, seed=s, api_key=api_key)
        src = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        rgba = chroma_cutout(raw)
        try:
            qa(rgba, src_shape=src.shape[:2], key_hue=detect_key_hue(src))
        except QAFailure as e:
            failures.append(f"attempt {attempt + 1}: {e}")
            if verbose:
                print(f"      ✗ rejected — {e}", flush=True)
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), rgba)
        if verbose:
            print(f"      ✓ {out_path.name} ({rgba.shape[1]}×{rgba.shape[0]})", flush=True)
        return out_path

    raise SystemExit(
        "ERROR: mascot QA failed " + str(MAX_ATTEMPTS) + " times for brief:\n"
        f"  {brief}\n  " + "\n  ".join(failures) +
        "\nNothing was saved. Reword the brief (see CHARACTER.md 'Writing a good brief')."
    )


def build_master(seed: int = 20260822) -> Path:
    brief = ("standing calmly at rest facing the viewer in a relaxed neutral pose, "
             "gentle friendly closed-mouth smile, arms relaxed at his sides with both "
             "hooves visible, no clothing and no props")
    refs = sorted(STYLE_REFS.glob("*.png")) + sorted(STYLE_REFS.glob("*.jpg"))
    print(f"Building canonical master from {len(refs)} style references…")
    return render_pose(brief, MASTER_PNG, model=MODEL_PRO, seed=seed, refs=refs[:4])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("master", help="(re)build the canonical reference")
    m.add_argument("--seed", type=int, default=20260822)

    p = sub.add_parser("pose", help="generate one ad-hoc pose")
    p.add_argument("brief")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--model", choices=["pro", "flash"], default="flash")

    a = ap.parse_args()
    if a.cmd == "master":
        build_master(a.seed)
    else:
        render_pose(a.brief, Path(a.out), seed=a.seed,
                    model=MODEL_PRO if a.model == "pro" else MODEL_FLASH)


if __name__ == "__main__":
    main()
