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

    # LOOK FIRST. Mattes, gates and writes a judging sheet. Touches nothing.
    import_poses.py ~/inbox --preview /tmp/silly

    # a 6-up sheet, name the cells in reading order
    import_poses.py sheets/batch1.png --grid 3x2 \
        --names slumped,pointing,shrugging,covering_eyes,leaning_in,arms_crossed

    # a folder of singles, named from their filenames
    import_poses.py inbox/

Anything that fails QA is reported and NOT written, with the reason.

The gates, and why they are here rather than where they used to be
------------------------------------------------------------------
Every one of the 180 poses in the library arrived through this script, and
until now this script checked almost nothing. `qa()` was called with
allow_detached=True and strict_framing=False, which switches off two of its
five gates, and the three CHARACTER gates — no text, on-palette colour, a
correct pair of eyes — lived in poses_flux.py, a module this one does not
import. So the strict text detector never ran on a single imported pose, and
neither did the eye check or any colour check at all.

They now live in cutout.py, which both paths import, and run here on every
cell. All of them run, and all failures are reported together: stopping at the
first one told you a pose failed once when it had failed three times.

Two deliberate choices about who decides:

  · --preview writes a judging sheet and NOTHING else. The sheet puts each new
    pose on three real slide grounds beside three library poses, because a pose
    is judged against the body of work (invariant 8) and against the background
    it will actually be printed on — not on a checkerboard, and not after it
    has already been added to the library, which was the only way to see one
    before.

  · The pupil gate blocks imports too. A person choosing a file does not make
    its eye faults safe for automatic use.

  · --exact preserves the bytes of an already-checked RGBA PNG. It still runs
    every pixel gate, but cannot crop, matte, mirror, recolour or override a
    failure. This is how a generated deck offers its checked file to the library.

--correct-palette is off by default. The generation path corrects colour
automatically because it knows the model drifts; here the artwork came from a
person, and silently rewriting their colours is not this script's decision to
make. The measured brand-green share is printed for every pose either way.
"""

from __future__ import annotations

import argparse
import re
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import art_checks
import art_eligibility

sys.path.insert(0, str(Path(__file__).resolve().parent))
from imaging import (  # noqa: E402
    contact_sheet, drop_neighbour_bleed, judging_sheet, tight_crop,
)
from cutout import (  # noqa: E402
    QAFailure, assert_has_pupils, assert_no_text, assert_on_palette,
    auto_chroma_matte, body_green_delta, correct_palette, detect_key_colour, qa,
)

# The backdrop every prompt in GENERATION_PROMPTS.md asks for. Only used to
# give an already-transparent input something to be text-checked against.
CHROMA_BGR = (255, 0, 255)

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



def sidecar_tags(path: Path) -> list[str]:
    """Tags from a `<stem>.brief.txt` beside the image, if there is one.

    A pose generated from a slide's own brief arrives with a plain-English
    description of the BODY — "sitting on the edge of a bed with his head
    lowered". That is exactly the vocabulary library.py has never had: the tag
    corpus is emotional and the briefs are physical, so a brief asking for a
    sitting pose could not tell a sitting pose from a standing one.

    Writing those words in as tags is what makes a generated pose findable
    later by the next brief that wants the same body. Stop words are dropped so
    "the" and "with" do not enter the corpus and get an inflated rarity weight,
    which is the mistake documented above library.STOP.
    """
    brief = path.with_suffix("").with_suffix(".brief.txt")
    if not brief.is_file():
        brief = path.parent / f"{path.stem}.brief.txt"
    if not brief.is_file():
        return []
    words = re.findall(r"[a-zA-Z]{3,}", brief.read_text(encoding="utf-8").lower())
    return sorted({w for w in words if w not in BRIEF_STOP})


# Function words plus the words every brief contains, which describe nothing.
BRIEF_STOP = {
    "the", "and", "with", "his", "her", "its", "one", "two", "both", "small",
    "donkey", "silly", "into", "onto", "from", "for", "out", "off", "over",
    "under", "while", "that", "this", "then", "than", "are", "was", "has",
    "have", "been", "being", "very", "just", "like", "toward", "towards",
}


def _flatten_for_text(cell: np.ndarray, rgba: np.ndarray, kind: str) -> np.ndarray:
    """The BGR frame the text gate should read.

    Text has to be looked for BEFORE matting: matting throws a caption away and
    then the artwork looks clean. For a chroma or paper input the original cell
    is that frame. For an input that arrived already transparent there is no
    "before", so the pose is composited back onto the key — the caption, if
    there is one, is opaque and survives the trip.
    """
    if kind != "alpha":
        return cell[:, :, :3]
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    key = np.zeros_like(rgba[:, :, :3], np.float32)
    key[:, :] = CHROMA_BGR
    return (rgba[:, :, :3].astype(np.float32) * a + key * (1 - a)).astype(np.uint8)


# Automated imports must not turn an eye failure into a warning. Four difficult
# clean poses are conservatively refused; no unattended exception admits them.
ADVISORY = set()  # Imports have the same blocking eye rule as fresh artwork.

# Gates a person may overrule with --allow. `text` is not among them: invariant
# 3 admits no exceptions and no amount of looking at a picture makes a caption
# acceptable. `palette` is, because the brand colour is the brand owner's to
# change and a deliberate palette shift is a decision, not a defect — but an
# overruled pose records the fact in poses.json, so a colour that entered the
# library by exception can always be told apart from one that passed.
OVERRIDABLE = {"palette"}


def run_gates(cell: np.ndarray, rgba: np.ndarray, kind: str, name: str,
              allow: set[str] | None = None) -> tuple[list[str], list[str], list[str]]:
    """Every gate, all of them, reported rather than stopping at the first.

    Returns (blocking, advisory, overridden). `blocking` empty means the pose
    may be written. Nothing here writes anything.

    Reporting all of them is the point. The old path ran one composite gate and
    stopped, so a pose that failed twice looked like a pose that failed once,
    and you fixed the wrong thing and re-rolled for nothing.
    """
    allow = (allow or set()) & OVERRIDABLE
    blocking: list[str] = []
    advisory: list[str] = []
    overridden: list[str] = []

    def gate(label: str, fn) -> None:
        try:
            fn()
        except QAFailure as e:
            # Every gate already names itself in its own message, so prefixing
            # with the label again reads "palette: palette: only 0.4% ...".
            msg = str(e)
            line = msg if msg.startswith(f"{label}:") else f"{label}: {msg}"
            if label in allow:
                overridden.append(line)
            elif label in ADVISORY:
                advisory.append(line)
            else:
                blocking.append(line)

    # 1 · invariant 3, on the pre-matte frame. Strictly stronger than qa()'s
    #     bottom-strays heuristic, which only reads the lowest fifth of the
    #     frame and cannot see a watermark or a signature.
    gate("text", lambda: assert_no_text(_flatten_for_text(cell, rgba, kind), name))
    # 2 · is this actually made of Silly's green
    gate("palette", lambda: assert_on_palette(rgba, name))
    # 3 · the eyes, which is the other way a generated face reads as wrong
    gate("pupils", lambda: assert_has_pupils(rgba, name))
    # 4 · the structural gates, unchanged. allow_detached and the loose framing
    #     are correct HERE and wrong for a generated frame: a sheet cell is a
    #     tight crop of a grid, so ear tips legitimately reach an edge and a
    #     detached fragment is normal.
    gate("qa", lambda: qa(rgba, src_shape=cell.shape[:2], allow_detached=True,
                          strict_framing=False,
                          key_bgr=detect_key_colour(cell[:, :, :3]) if kind == "chroma" else None))
    return blocking, advisory, overridden


def near_duplicates(rgba: np.ndarray, library: Path, top: int = 1,
                    thresh: float = 0.93) -> list[tuple[str, float]]:
    """Existing poses whose silhouette matches this one.

    Compares alpha silhouettes on a common 64x64 grid, which is deliberately
    crude: it is looking for "you already have this pose", not for a subtle
    difference in expression. A duplicate is a real cost — library.py picks a
    pose by tag overlap, so two near-identical poses split the same tags and
    make the choice worse, not better.

    Advisory. It is printed, never enforced: a mirrored pair is a legitimate
    near-duplicate and the library has 36 of them on purpose.
    """
    def sig(a: np.ndarray) -> np.ndarray:
        m = (a > 128).astype(np.float32)
        return cv2.resize(m, (64, 64), interpolation=cv2.INTER_AREA)

    if rgba.shape[2] < 4:
        return []
    mine = sig(rgba[:, :, 3])
    hits = []
    for p in sorted(library.glob("*.png")):
        if p.stem.startswith("_"):
            continue
        other = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if other is None or other.shape[2] < 4:
            continue
        theirs = sig(other[:, :, 3])
        inter = np.minimum(mine, theirs).sum()
        union = np.maximum(mine, theirs).sum()
        iou = float(inter / union) if union else 0.0
        if iou >= thresh:
            hits.append((p.stem, iou))
    return sorted(hits, key=lambda t: -t[1])[:top]


# Fields import owns and may overwrite. Everything else in a pose's manifest
# entry is curated by hand and survives a re-import untouched.
IMPORT_OWNED = {"tags", "framing", "figures", "source", "mirrored", "override"}


def merge_pose(manifest: dict, name: str, fields: dict) -> None:
    """Update a pose entry in place, preserving every field import does not own.

    This is the whole bug that made re-importing dangerous. The old code did
    `manifest["poses"][name] = {...}` — a wholesale replacement that carefully
    merged `tags` from the prior entry and then dropped everything else on the
    floor. 170 of the 180 poses carry hand-tuned `valence` and `arousal`, and
    library.py scores poses on exactly those two numbers, falling back to
    (0.0, 1.5) when they are missing. So re-importing a sheet to fix one bad
    cell silently flattened the mood scoring of the five good ones beside it,
    and nothing anywhere said so.

    The comment above the old `tags` merge described this failure exactly, for
    tags, and was never carried to the fields next to it. Hence a whitelist of
    what import owns rather than a list of what to rescue: a field added to a
    pose entry tomorrow is preserved by default, which is the safe direction.
    """
    entry = manifest.setdefault("poses", {}).setdefault(name, {})
    stale = set(entry) & IMPORT_OWNED - set(fields)
    for key in stale:
        del entry[key]
    entry.update(fields)


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


def build_parser() -> argparse.ArgumentParser:
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
    # Full body is the DEFAULT, and --bust is the opt-out.
    #
    # It used to be the other way round: --fullbody opted in, and forgetting it
    # silently recorded the pose as "bust", which loses tie-breaks in
    # library.py's selection. Nobody would ever see that happen. All 180 poses
    # in the library are full — there is not one bust among them — so the flag
    # that had to be remembered every single time was the one for the case that
    # has never once occurred.
    ap.add_argument("--bust", action="store_true",
                    help="head-and-shoulders artwork, not a full standing figure "
                         "(the library has none; full body is the default)")
    ap.add_argument("--fullbody", action="store_true",
                    help=argparse.SUPPRESS)   # accepted, now the default, kept
                                              # so the commands in
                                              # GENERATION_PROMPTS.md still run
    ap.add_argument("--allow", default="",
                    help="comma-separated gates to overrule, e.g. --allow palette. "
                         "Only 'palette' may be overruled, and the override is "
                         "recorded in poses.json. 'text' may not.")
    ap.add_argument("--correct-palette", action="store_true",
                    help="pull the body green and cream back onto the brand palette "
                         "before matting. Off by default: this rewrites your artwork.")
    ap.add_argument("--preview", metavar="DIR",
                    help="matte, gate and write a judging sheet to DIR. Writes NOTHING "
                         "to the library and nothing to the manifest.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--exact", action="store_true",
                    help="import an RGBA PNG without changing any bytes; all gates still block")
    return ap


def main_argv(argv: list[str] | None = None) -> None:
    a = build_parser().parse_args(argv)
    if a.exact and (a.grid or a.mirror or a.correct_palette or a.allow):
        sys.exit("ERROR: --exact cannot crop, mirror, recolour, or override a gate.")
    allow = {t.strip() for t in a.allow.split(",") if t.strip()}
    refused = allow - OVERRIDABLE
    if refused:
        sys.exit(f"ERROR: --allow {','.join(sorted(refused))} refused. Only "
                 f"{'/'.join(sorted(OVERRIDABLE))} may be overruled; text is an "
                 f"invariant, not a judgement call.")
    preview_dir = Path(a.preview) if a.preview else None
    writing = not (a.dry_run or preview_dir)

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
    entries: list[dict] = []
    for f in files:
        exact_bytes = f.read_bytes() if a.exact else None
        img = (cv2.imdecode(np.frombuffer(exact_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
               if a.exact else cv2.imread(str(f), cv2.IMREAD_UNCHANGED))
        if img is None:
            failed.append(f"{f.name}: unreadable")
            continue
        if a.exact and (not exact_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                        or img.ndim != 3 or img.shape[2] != 4):
            failed.append(f"{f.name}: exact import requires an RGBA PNG")
            continue
        for cell in cells(img, a.grid):
            name = (names[idx] if names and idx < len(names)
                    else (f.stem if not a.grid else f"{f.stem}_{idx + 1}"))
            idx += 1
            if a.correct_palette and cell.shape[2] == 3:
                # Opt-in, and it happens BEFORE matting so what is judged and
                # what is written are the same picture — the same ordering the
                # generation path uses for the same reason.
                cell = correct_palette(cell)
            rgba, kind = (cell, "alpha") if a.exact else to_rgba(cell)
            # A pair scene's second donkey is legitimately small and often sits
            # near a side edge — exactly what drop_neighbour_bleed is designed
            # to delete. Skip it for --pair imports so it doesn't eat the
            # partner donkey; single-figure cells still get the bleed cleanup.
            if not a.exact:
                rgba = tight_crop(rgba if a.pair else drop_neighbour_bleed(rgba))

            blocking, advisory, overridden = run_gates(cell, rgba, kind, name, allow)
            if a.exact:
                blocking.extend(art_checks.pixel_faults_bytes(exact_bytes))
            # Import cannot grant body eligibility. Check the exact bytes that
            # will be saved, including transformed and mirrored imports.
            ok, encoded = cv2.imencode(".png", rgba)
            saved_bytes = exact_bytes if a.exact else (encoded.tobytes() if ok else b"")
            if preview_dir is None:
                blocking.extend(art_eligibility.faults_bytes(saved_bytes))
                if a.mirror:
                    mirror_ok, mirror_encoded = cv2.imencode(".png", cv2.flip(rgba, 1))
                    blocking.extend(art_eligibility.faults_bytes(
                        mirror_encoded.tobytes() if mirror_ok else b""))
            dupes = near_duplicates(rgba, LIBRARY)
            notes = list(advisory) + [f"[OVERRULED] {o}" for o in overridden]
            found = body_green_delta(rgba)
            green = (f"body green #{found[1][2]:02X}{found[1][1]:02X}{found[1][0]:02X} "
                     f"({found[0]:.0f} dE off brand)") if found else "no green found"
            notes.append(f"{green} · {rgba.shape[1]}x{rgba.shape[0]} · bg={kind}")
            if dupes:
                notes.append("near-duplicate of " + ", ".join(
                    f"{n} ({v:.0%} silhouette overlap)" for n, v in dupes))
            entries.append({"name": name, "rgba": rgba, "ok": not blocking,
                            "verdicts": blocking + notes, "encoded": saved_bytes})

            if blocking:
                failed.append(f"{name}: {blocking[0]}")
                print(f"  ✗ {name:20s} {len(blocking)} gate(s) failed")
                for line in blocking:
                    print(f"      {line[:96]}")
                continue
            print(f"  ✓ {name:20s} {rgba.shape[1]:3d}x{rgba.shape[0]:3d}  bg={kind}")
            for line in notes:
                print(f"      {line[:96]}")

            base_tags = sorted(set(
                manifest.get("poses", {}).get(name, {}).get("tags", [])
                + [name.replace("_", " ")] + extra + sidecar_tags(f)))
            if writing:
                (LIBRARY / f"{name}.png").write_bytes(saved_bytes)
                # sorted(set(...)) here, not append: base_tags already carries
                # these pair markers on a re-import (they merged in from the
                # prior entry last time), and appending again without dedup
                # double-lists them — which then double-counts them in scoring,
                # since _overlap() sums over every tag in the list.
                pair_tags = (["two people", "both of you", "the pair",
                              "relationship", "between you"] if a.pair else [])
                fields = {
                    "tags": sorted(set(base_tags + pair_tags)),
                    "framing": "bust" if a.bust else "full",
                    "figures": 2 if a.pair else 1,
                    "source": "imported",
                }
                if overridden:
                    # Recorded, so a pose that entered by exception can always be
                    # told apart from one that passed on its own.
                    fields["override"] = sorted(
                        {o.split(":")[0] for o in overridden})
                merge_pose(manifest, name, fields)
            written.append(name)

            if a.mirror:
                # A flipped copy doubles the directional poses for free. The mane
                # only runs down one side of his neck, so a mirrored Silly is
                # subtly the wrong way round — selection breaks ties against them.
                mname = f"{name}_m"
                print(f"  ✓ {mname:20s} mirrored")
                if writing:
                    (LIBRARY / f"{mname}.png").write_bytes(mirror_encoded.tobytes())
                    prior_m = manifest.get("poses", {}).get(mname, {}).get("tags", [])
                    merge_pose(manifest, mname, {
                        "tags": sorted(set(prior_m + mirror_tags(base_tags))),
                        "framing": "bust" if a.bust else "full",
                        "figures": 2 if a.pair else 1,
                        "source": "imported",
                        "mirrored": True,
                    })
                written.append(mname)

    if preview_dir is not None and entries:
        sheet = judging_sheet(entries, LIBRARY, preview_dir / "judging_sheet.png")
        for entry in entries:
            # A preview is staging, never a selectable library. Retain the
            # exact final bytes so an offline audit can precede --exact import.
            (preview_dir / (entry["name"] + ".png")).write_bytes(entry["encoded"])
        print(f"\njudging sheet: {sheet}")
        print("Nothing was written to the library. Check the staged PNGs with "
              "art_eligibility.py, then import those exact files with --exact.")

    if writing and written:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        contact_sheet(LIBRARY)

    verb = "imported" if writing else "would import"
    print(f"\n{len(written)} {verb}, {len(failed)} rejected")
    if failed:
        print("Rejected (nothing written for these):")
        for x in failed:
            print("  -", x)
    if written and writing:
        print(f"\nAdd tags in {MANIFEST} so briefs match them well.")


if __name__ == "__main__":
    main_argv()
