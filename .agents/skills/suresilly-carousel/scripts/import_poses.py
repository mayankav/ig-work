#!/usr/bin/env python3
"""
import_poses.py — ingest hand-generated Silly artwork into the pose library.

Feed it whatever you got out of an image tool and it does the rest: detects the
background type, mattes to clean alpha, runs the QA gates, and writes named
PNGs plus manifest rows.

Handles three input shapes:
  · a 2x3 / 3x2 grid sheet of 6 poses      --grid 3x2
  · a single pose per file                 (default)
  · already-transparent PNGs               (matting is skipped)

and three background types, detected automatically: chroma green, flat white or
paper, and existing alpha.

    # a 6-up sheet, name the cells in reading order
    import_poses.py sheets/batch1.png --grid 3x2 --fullbody \
        --names slumped,pointing,shrugging,covering_eyes,leaning_in,arms_crossed

    # a folder of singles, named from their filenames
    import_poses.py inbox/ --fullbody

Anything that fails QA is reported and NOT written, with the reason.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from imaging import contact_sheet, drop_neighbour_bleed, tight_crop  # noqa: E402
from cutout import QAFailure, auto_chroma_matte, detect_key_hue, qa  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
LIBRARY = SKILL_DIR / "mascot" / "library"
MANIFEST = SKILL_DIR / "mascot" / "poses.json"


def border_stats(bgr: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Median hue / saturation / value of the frame border."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    border = np.concatenate([hsv[0], hsv[-1], hsv[:, 0], hsv[:, -1]])
    med = np.median(border, axis=0)
    return med, float(med[1]), float(med[2])


def detect_background(bgr: np.ndarray, alpha: np.ndarray | None) -> str:
    if alpha is not None and alpha.min() < 250:
        return "alpha"
    _, sat, _ = border_stats(bgr)
    # A chroma backdrop is deliberately saturated; paper and white are not.
    return "chroma" if sat > 90 else "flat"


def matte_chroma(bgr: np.ndarray) -> np.ndarray:
    """Delegates to the shared implementation in mascot.py.

    One matting implementation, used by both the generation path and this one,
    so a fix lands in both places at once.
    """
    return auto_chroma_matte(bgr)


def matte_flat(bgr: np.ndarray) -> np.ndarray:
    """White or paper background, removed by border-connected components.

    Connectivity is what protects enclosed light areas: the cream muzzle and the
    eye whites are ringed by the body, so they never touch an edge and survive
    even though they are close to white.
    """
    border = np.concatenate([bgr[0], bgr[-1], bgr[:, 0], bgr[:, -1]])
    bg = np.median(border, axis=0)
    near = (np.abs(bgr.astype(np.int16) - bg).max(2) <= 15).astype(np.uint8)
    n, labels, _, _ = cv2.connectedComponentsWithStats(near, 4)
    edge = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
    edge.discard(0)
    alpha = np.where(np.isin(labels, list(edge)), 0, 255).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)

    a = (alpha.astype(np.float32) / 255.0)[:, :, None]
    sub = (bgr.astype(np.float32) - (1.0 - a) * bg.astype(np.float32)) / np.clip(a, 0.25, 1.0)
    rgb = np.where(a > 0.004, np.clip(sub, 0, 255), bgr).astype(np.uint8)
    return np.dstack([rgb, alpha])



LR_SWAP = [("left", "\x00"), ("right", "left"), ("\x00", "right")]


def mirror_tags(tags: list[str]) -> list[str]:
    """Swap left and right in a tag list, so a flipped pose matches the opposite brief."""
    out = []
    for t in tags:
        for a, b in LR_SWAP:
            t = t.replace(a, b)
        out.append(t)
    return out


def to_rgba(img: np.ndarray) -> tuple[np.ndarray, str]:
    alpha = img[:, :, 3] if img.ndim == 3 and img.shape[2] == 4 else None
    bgr = img[:, :, :3]
    kind = detect_background(bgr, alpha)
    if kind == "alpha":
        return img, kind
    return (matte_chroma(bgr) if kind == "chroma" else matte_flat(bgr)), kind


def cells(img: np.ndarray, grid: str | None):
    if not grid:
        yield img
        return
    c, r = (int(v) for v in grid.lower().split("x"))
    h, w = img.shape[:2]
    ch, cw = h // r, w // c
    for ri in range(r):
        for ci in range(c):
            yield img[ri * ch:(ri + 1) * ch, ci * cw:(ci + 1) * cw]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="image file or a folder of images")
    ap.add_argument("--grid", help="grid layout of each sheet, e.g. 3x2")
    ap.add_argument("--names", help="comma-separated pose names, in reading order")
    ap.add_argument("--tags", help="comma-separated extra tags applied to every imported pose")
    ap.add_argument("--pair", action="store_true",
                    help="two Sillys in the frame — marks them so selection can find them")
    ap.add_argument("--mirror", action="store_true",
                    help="also write a horizontally flipped copy of each pose as <name>_m")
    ap.add_argument("--fullbody", action="store_true",
                    help="mark these as full-body (they win ties over the old bust-only poses)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    src = Path(a.src)
    files = sorted(p for p in (src.iterdir() if src.is_dir() else [src])
                   if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
                   and not p.stem.startswith("_"))
    if not files:
        sys.exit(f"ERROR: no images found at {src}")

    names = [n.strip() for n in a.names.split(",")] if a.names else None
    if a.grid and not names:
        # Fallback names like "sheet1_3" are never what you want from a grid, and
        # they hide a mis-typed command instead of failing it.
        sys.exit("ERROR: --grid needs --names, one per cell, in reading order.")
    if names and a.grid:
        c, r = (int(v) for v in a.grid.lower().split("x"))
        want = c * r * len(files)
        if len(names) != want:
            sys.exit(f"ERROR: --grid {a.grid} over {len(files)} file(s) needs {want} "
                     f"names, got {len(names)}.")
    extra = [t.strip() for t in a.tags.split(",")] if a.tags else []
    LIBRARY.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {"poses": {}}

    written, failed, idx = [], [], 0
    for f in files:
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            failed.append(f"{f.name}: unreadable")
            continue
        for cell in cells(img, a.grid):
            name = (names[idx] if names and idx < len(names)
                    else (f.stem if not a.grid else f"{f.stem}_{idx + 1}"))
            idx += 1
            rgba, kind = to_rgba(cell)
            # A pair scene's second donkey is legitimately small and often sits
            # near a side edge — exactly what drop_neighbour_bleed is designed
            # to delete. Skip it for --pair imports so it doesn't eat the
            # partner donkey; single-figure cells still get the bleed cleanup.
            rgba = tight_crop(rgba if a.pair else drop_neighbour_bleed(rgba))
            key = detect_key_hue(cell[:, :, :3]) if kind == "chroma" else None
            try:
                qa(rgba, src_shape=cell.shape[:2], allow_detached=True,
                   strict_framing=False, key_hue=key)
            except QAFailure as e:
                failed.append(f"{name}: {e}")
                print(f"  ✗ {name:20s} {str(e)[:62]}")
                continue
            print(f"  ✓ {name:20s} {rgba.shape[1]:3d}x{rgba.shape[0]:3d}  bg={kind}")
            # MERGE, never replace. Re-importing a sheet used to reset a pose's
            # tags to just its name, which silently gutted the curated
            # vocabulary — including the hook and CTA defaults — and only
            # surfaced later as bad pose choices.
            prior = manifest.get("poses", {}).get(name, {}).get("tags", [])
            base_tags = sorted(set(prior + [name.replace("_", " ")] + extra))
            if not a.dry_run:
                cv2.imwrite(str(LIBRARY / f"{name}.png"), rgba)
                manifest["poses"][name] = {
                    # sorted(set(...)) here, not append: base_tags already
                    # carries these pair markers on a re-import (they merged
                    # in from `prior` last time), and appending again without
                    # dedup double-lists them — which then double-counts them
                    # in scoring, since _overlap() sums over every tag in the
                    # list, duplicates included.
                    "tags": sorted(set(base_tags + (
                        ["two people", "both of you", "the pair",
                         "relationship", "between you"] if a.pair else []))),
                    "framing": "full" if a.fullbody else "bust",
                    "figures": 2 if a.pair else 1,
                    "source": "imported",
                }
            written.append(name)

            if a.mirror:
                # A flipped copy doubles the directional poses for free. The mane
                # only runs down one side of his neck, so a mirrored Silly is
                # subtly the wrong way round — selection breaks ties against them.
                mname = f"{name}_m"
                print(f"  ✓ {mname:20s} mirrored")
                if not a.dry_run:
                    cv2.imwrite(str(LIBRARY / f"{mname}.png"), cv2.flip(rgba, 1))
                    prior_m = manifest.get("poses", {}).get(mname, {}).get("tags", [])
                    manifest["poses"][mname] = {
                        "tags": sorted(set(prior_m + mirror_tags(base_tags))),
                        "framing": "full" if a.fullbody else "bust",
                        "figures": 2 if a.pair else 1,
                        "source": "imported",
                        "mirrored": True,
                    }
                written.append(mname)

    if not a.dry_run and written:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        contact_sheet(LIBRARY)

    verb = "would import" if a.dry_run else "imported"
    print(f"\n{len(written)} {verb}, {len(failed)} rejected")
    if failed:
        print("Rejected (nothing written for these):")
        for x in failed:
            print("  -", x)
    if written and not a.dry_run:
        print(f"\nAdd tags in {MANIFEST} so briefs match them well.")


if __name__ == "__main__":
    main()
