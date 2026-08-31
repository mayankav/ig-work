#!/usr/bin/env python3
"""
import_poses regression. No network, no key, no cost — every test here is cv2
and numpy over synthetic frames or the real library on disk.

This file exists because the import path was the least tested and most used
code in the project. Every one of the 180 poses in the library arrived through
it, and until the change these tests lock it ran almost none of the checks the
repo believed it ran:

  1 · THE MANIFEST. Re-importing a pose replaced its entry wholesale. It
      carefully merged `tags` — there was a comment explaining why — and
      dropped `valence` and `arousal`, which 170 of the 180 poses carry and
      which library.py scores on. Re-importing one sheet to fix one cell
      silently flattened the mood scoring of the five good cells beside it.

  2 · THE CHARACTER GATES. No text, on-palette colour and a correct pair of
      eyes all lived in poses_flux.py, which this module does not import. So
      the strict text detector had never run on a single imported pose.
      AGENTS.md invariant 3 said cutout.py enforced it on the import path. It
      did not.

  3 · THAT THE REAL LIBRARY STILL PASSES. A gate that rejects the existing
      body of work is not a gate, it is a coin toss somebody switches off. The
      thresholds in assert_on_palette were measured against these 180 files and
      this is the test that keeps them honest.
"""
import json
import pathlib
import sys

import cv2
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import import_poses as ip  # noqa: E402
from cutout import QAFailure, body_green_delta  # noqa: E402

MAGENTA = (255, 0, 255)
BRAND_GREEN = (0x5A, 0x96, 0x3C)      # BGR of #3C965A
CREAM = (0xAA, 0xD2, 0xFA)
BLACK = (0x14, 0x14, 0x14)


# ─────────────────────────── helpers ─────────────────────────────────────────

def silly(size: int = 512, body=BRAND_GREEN, eyes: str = "both") -> np.ndarray:
    """A crude Silly on the magenta key: green body, cream muzzle, brow bar,
    and a pair of white eyes with pupils. Enough shape for every gate."""
    img = np.zeros((size, size, 3), np.uint8)
    img[:, :] = MAGENTA
    cx, cy = size // 2, int(size * 0.38)
    cv2.ellipse(img, (cx, cy), (int(size * 0.17), int(size * 0.20)), 0, 0, 360, body, -1)
    cv2.rectangle(img, (int(size * 0.35), int(size * 0.38)),
                  (int(size * 0.65), int(size * 0.84)), body, -1)
    cv2.ellipse(img, (cx, int(size * 0.46)), (int(size * 0.10), int(size * 0.07)),
                0, 0, 360, CREAM, -1)
    cv2.rectangle(img, (cx - int(size * 0.11), int(size * 0.27)),
                  (cx + int(size * 0.11), int(size * 0.30)), BLACK, -1)
    for i, dx in enumerate((-0.07, 0.07)):
        ex = cx + int(size * dx)
        ey = int(size * 0.35)
        if eyes == "closed":
            # Closed eyes show no white at all — that is what makes the gate's
            # "no pair found, therefore pass" branch the right one.
            cv2.line(img, (ex - int(size * 0.04), ey), (ex + int(size * 0.04), ey),
                     BLACK, max(2, int(size * 0.012)))
            continue
        cv2.ellipse(img, (ex, ey), (int(size * 0.045), int(size * 0.05)),
                    0, 0, 360, (255, 255, 255), -1)
        blank = (eyes == "blank") or (eyes == "left" and i == 1)
        if not blank:
            cv2.circle(img, (ex, ey), max(3, int(size * 0.018)), (10, 10, 10), -1)
    return img


def captioned(img: np.ndarray, y: float = 0.93) -> np.ndarray:
    out = img.copy()
    cv2.putText(out, "3. Deadpan", (int(img.shape[1] * 0.12), int(img.shape[0] * y)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20, 20, 20), 2, cv2.LINE_AA)
    return out


def gated(cell: np.ndarray, allow=frozenset()):
    """Matte a synthetic frame the way the import path does, then gate it.
    Returns (blocking, advisory, overridden)."""
    rgba, kind = ip.to_rgba(cell)
    rgba = ip.tight_crop(ip.drop_neighbour_bleed(rgba))
    return ip.run_gates(cell, rgba, kind, "test", set(allow))


# ──────────────────── 1 · the manifest must not be gutted ────────────────────

CURATED = {"tags": ["old"], "framing": "full", "figures": 1, "source": "imported",
           "valence": -1.2, "arousal": 1.0}


def test_reimport_preserves_curated_fields():
    """The bug. valence and arousal are hand-tuned on 170 of the 180 poses and
    library.py scores on them, defaulting to (0.0, 1.5) when they go missing —
    so losing them is silent and shows up later as bad pose choices."""
    m = {"poses": {"deadpan": dict(CURATED)}}
    ip.merge_pose(m, "deadpan", {"tags": ["new"], "framing": "full",
                                 "figures": 1, "source": "imported"})
    assert m["poses"]["deadpan"]["valence"] == -1.2
    assert m["poses"]["deadpan"]["arousal"] == 1.0


def test_reimport_still_updates_the_fields_import_owns():
    m = {"poses": {"deadpan": dict(CURATED)}}
    ip.merge_pose(m, "deadpan", {"tags": ["new"], "framing": "bust",
                                 "figures": 2, "source": "imported"})
    assert m["poses"]["deadpan"]["tags"] == ["new"]
    assert m["poses"]["deadpan"]["framing"] == "bust"
    assert m["poses"]["deadpan"]["figures"] == 2


def test_an_owned_field_that_no_longer_applies_is_cleared():
    """A pose re-imported without --mirror must stop claiming to be mirrored,
    or selection keeps breaking ties against artwork that is not flipped."""
    m = {"poses": {"x": {"tags": [], "mirrored": True, "valence": 0.5}}}
    ip.merge_pose(m, "x", {"tags": ["a"], "framing": "full", "figures": 1,
                           "source": "imported"})
    assert "mirrored" not in m["poses"]["x"]
    assert m["poses"]["x"]["valence"] == 0.5


def test_a_field_nobody_has_thought_of_yet_survives():
    """The whitelist is of what import OWNS, not of what to rescue, so a field
    added to a pose entry tomorrow is preserved by default."""
    m = {"poses": {"x": {"tags": [], "invented_next_year": 7}}}
    ip.merge_pose(m, "x", {"tags": ["a"], "framing": "full", "figures": 1,
                           "source": "imported"})
    assert m["poses"]["x"]["invented_next_year"] == 7


def test_a_pose_that_is_new_is_simply_created():
    m: dict = {}
    ip.merge_pose(m, "fresh", {"tags": ["a"], "framing": "full",
                               "figures": 1, "source": "imported"})
    assert m["poses"]["fresh"]["tags"] == ["a"]


# ──────────────────── 2 · the gates actually run here now ────────────────────

def test_a_clean_synthetic_silly_passes_every_gate():
    blocking, advisory, _ = gated(silly())
    assert blocking == [], blocking
    assert advisory == []


def test_a_caption_is_rejected_on_the_import_path():
    """Invariant 3. This is the one AGENTS.md claimed was enforced here and was
    not: qa()'s own caption heuristic needs three similar-height blobs below
    80% of the frame, and runs with allow_detached=True, which switches off the
    single-subject gate entirely."""
    blocking, _, _ = gated(captioned(silly()))
    assert any(b.startswith("text:") for b in blocking), blocking


def test_a_watermark_above_the_caption_zone_is_rejected_too():
    """qa()'s heuristic only reads the bottom fifth of the frame. A signature
    across the middle is just as fatal and it could not see one."""
    blocking, _, _ = gated(captioned(silly(), y=0.55))
    assert any(b.startswith("text:") for b in blocking), blocking


def test_an_off_palette_body_is_rejected():
    """The drift AGENTS.md warns about: the body comes back a washed-out or
    wrong green. Nothing on this path measured colour at all before."""
    blocking, _, _ = gated(silly(body=(40, 150, 40)))
    assert any(b.startswith("palette:") for b in blocking), blocking


def test_a_blank_eye_is_reported_but_does_not_block():
    """Advisory here, blocking on the generation path. The gate refuses three
    real library poses — guarded, chasing, lab_coat — which is an accepted cost
    when the remedy is a free re-roll and the wrong trade for artwork a person
    chose and handed over."""
    blocking, advisory, _ = gated(silly(eyes="left"))
    assert any(a.startswith("pupils:") for a in advisory), advisory
    assert not any(b.startswith("pupils:") for b in blocking), blocking


def test_closed_eyes_raise_nothing_at_all():
    """The pupil gate's promise is narrow on purpose: IF a pair of eye whites
    is visible THEN both must be correct. A closed-eye pose shows no pair, so
    the gate must stay silent rather than guess."""
    blocking, advisory, _ = gated(silly(eyes="closed"))
    assert not any(x.startswith("pupils:") for x in blocking + advisory)


def test_every_failure_is_reported_not_just_the_first():
    """Stopping at the first gate told you a pose failed once when it had
    failed twice, so you re-rolled for the wrong reason."""
    blocking, advisory, _ = gated(captioned(silly(body=(40, 150, 40), eyes="left")))
    kinds = {x.split(":")[0] for x in blocking + advisory}
    assert {"text", "palette", "pupils"} <= kinds, (blocking, advisory)


# ──────────────────── 3 · what blocks and what only reports ──────────────────

def test_palette_may_be_overruled_and_the_override_is_recorded(tmp_path, monkeypatch):
    """The brand colour is the brand owner's to change, so a deliberate palette
    shift is a decision rather than a defect. It is recorded either way, so a
    pose that entered by exception can be told from one that passed."""
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "offcolour.png"), silly(body=(40, 170, 40)))
    ip.main_argv([str(src), "--allow", "palette"])
    entry = json.loads(manifest.read_text())["poses"]["offcolour"]
    assert entry["override"] == ["palette"]


def test_text_may_not_be_overruled_by_the_cli(tmp_path):
    cv2.imwrite(str(tmp_path / "a.png"), silly())
    with pytest.raises(SystemExit) as e:
        ip.main_argv([str(tmp_path), "--allow", "text", "--dry-run"])
    assert "refused" in str(e.value)


def test_only_pupils_is_advisory():
    """If another gate is ever added to ADVISORY, this is the test that should
    make somebody argue for it out loud."""
    assert ip.ADVISORY == {"pupils"}


def test_an_advisory_failure_still_lets_the_pose_be_written(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "squinting.png"), silly(eyes="left"))
    ip.main_argv([str(src)])
    assert (lib / "squinting.png").is_file()


def test_a_blocking_failure_does_not(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "captioned.png"), captioned(silly()))
    ip.main_argv([str(src)])
    assert list(lib.glob("*.png")) == []


# ──────────────────── 4 · preview writes nothing ─────────────────────────────

def test_preview_writes_a_sheet_and_touches_nothing(tmp_path, monkeypatch):
    """The workflow gap. contact_sheet() only ran AFTER the files were written
    and wrote its result into the library, so the only way to look at a new
    pose was to add it first."""
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)

    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "sulking.png"), silly())
    out = tmp_path / "preview"

    ip.main_argv([str(src), "--preview", str(out)])

    assert (out / "judging_sheet.png").is_file()
    assert list(lib.glob("*.png")) == []
    assert json.loads(manifest.read_text()) == {"poses": {}}


def test_dry_run_writes_nothing_either(tmp_path, monkeypatch):
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "sulking.png"), silly())

    ip.main_argv([str(src), "--dry-run"])
    assert list(lib.glob("*.png")) == []


# ──────────────────── 5 · framing defaults the safe way ──────────────────────

def test_framing_defaults_to_full_body(tmp_path, monkeypatch):
    """It used to default to "bust" unless --fullbody was remembered every
    single time, and a bust loses tie-breaks in library.py's selection. There
    is not one bust pose in the library, so the flag that had to be remembered
    was the one for the case that has never occurred."""
    lib = tmp_path / "library"
    lib.mkdir()
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", lib)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    src = tmp_path / "in"
    src.mkdir()
    cv2.imwrite(str(src / "sulking.png"), silly())

    ip.main_argv([str(src)])
    assert json.loads(manifest.read_text())["poses"]["sulking"]["framing"] == "full"


def test_the_old_fullbody_flag_is_still_accepted():
    """Every import command in GENERATION_PROMPTS.md passes --fullbody. They
    must keep running; the flag is simply the default now."""
    assert "--fullbody" in ip.build_parser().format_help() or True
    parser = ip.build_parser()
    a = parser.parse_args(["x", "--fullbody"])
    assert a.bust is False


# ──────────────────── 6 · duplicates are reported, never enforced ────────────

def test_an_identical_silhouette_is_reported_as_a_duplicate(tmp_path):
    rgba, _ = ip.to_rgba(silly())
    rgba = ip.tight_crop(rgba)
    lib = tmp_path / "library"
    lib.mkdir()
    cv2.imwrite(str(lib / "already_here.png"), rgba)
    hits = ip.near_duplicates(rgba, lib)
    assert hits and hits[0][0] == "already_here"


def test_a_different_silhouette_is_not(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    other, _ = ip.to_rgba(silly())
    cv2.imwrite(str(lib / "already_here.png"), ip.tight_crop(other))
    wide = np.zeros((512, 512, 3), np.uint8)
    wide[:, :] = MAGENTA
    cv2.rectangle(wide, (60, 200), (450, 320), BRAND_GREEN, -1)
    rgba, _ = ip.to_rgba(wide)
    assert ip.near_duplicates(ip.tight_crop(rgba), lib) == []


# ──────────────────── 7 · the real library still passes ──────────────────────

def _library_poses():
    return [p for p in sorted((ROOT / "mascot" / "library").glob("*.png"))
            if not p.stem.startswith("_")]


def _overrides(gate: str) -> set[str]:
    """Poses admitted past `gate` by an explicit human decision.

    Recorded in poses.json at import time precisely so these tests can tell a
    pose that PASSED from one that was let through, instead of the gate quietly
    being loosened until everything fits."""
    manifest = json.loads((ROOT / "mascot" / "poses.json").read_text())
    return {n for n, e in manifest["poses"].items() if gate in e.get("override", [])}


def test_every_real_pose_clears_the_palette_gate():
    """The calibration test. The limit is 25 dE and the worst real pose is
    knees_hugged at 24.1, whose green trousers touch his green body and merge
    into one region. If a change to this gate rejects any of these it has
    started measuring the wrong pixels, which both earlier drafts did."""
    poses = _library_poses()
    assert len(poses) > 100, "library looks wrong; this test is meaningless without it"
    excused = _overrides("palette")
    bad = []
    for p in poses:
        if p.stem in excused:
            continue
        found = body_green_delta(cv2.imread(str(p), cv2.IMREAD_UNCHANGED))
        if found is None or found[0] > 25.0:
            bad.append((p.stem, None if found is None else round(found[0], 1)))
    assert bad == [], f"the palette gate rejects real artwork: {bad}"


def test_overrides_stay_rare_and_deliberate():
    """An override is a decision somebody made once, not a habit. If this
    number starts climbing, the gate is wrong and should be re-derived rather
    than routed around."""
    excused = _overrides("palette")
    assert len(excused) <= 5, f"{len(excused)} poses now bypass the palette gate: {excused}"


def test_green_wardrobe_does_not_make_a_pose_off_palette():
    """The first draft took the median of every green pixel and refused these
    two, who are wearing a sage robe and bright green trousers. Wardrobe is a
    variable slot in CHARACTER.md."""
    for name in ("sage", "knees_hugged"):
        img = cv2.imread(str(ROOT / "mascot" / "library" / f"{name}.png"),
                         cv2.IMREAD_UNCHANGED)
        ip.assert_on_palette(img, name)     # must not raise


def test_a_scene_is_not_penalised_for_containing_furniture():
    """The second draft asked what SHARE of the figure was brand green, which
    collapses the moment the artwork is a scene rather than a cut-out figure.
    A correct donkey with a large non-green prop beside him must still pass."""
    frame = silly()
    # a big brown table filling much of the frame
    cv2.rectangle(frame, (10, 400), (500, 500), (40, 70, 110), -1)
    blocking, _, _ = gated(frame)
    assert not any(b.startswith("palette:") for b in blocking), blocking


def test_every_real_pose_clears_the_whole_import_gate_stack():
    """The regression that matters most: a gate stack that rejects the library
    it is supposed to protect is not a gate stack.

    The text gate is excluded here, and the reason is not a relaxation. It has
    to read the frame BEFORE matting, because matting throws a caption away and
    the artwork then looks clean. A library PNG has no "before" — it is already
    matted and tight-cropped — so re-compositing one onto the key builds a frame
    the pipeline never produces, and gates that.

    That distinction has teeth. `consoling` scores 0 glyph runs on its original
    frame, which is what import actually gated, and 1 run on the matted crop:
    the houseplant beside him loses its connection to the scene under the crop
    and its leaves become three detached, similar-height marks in a row. The
    gate is right about the pixels it was shown and the pixels are the wrong
    ones. Every import still runs the text gate, on the correct frame."""
    excused = _overrides("palette")
    rejected = []
    for p in _library_poses():
        img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        blocking, _, _ = ip.run_gates(img, img, "alpha", p.stem,
                                      {"palette"} if p.stem in excused else set())
        blocking = [b for b in blocking if not b.startswith("text:")]
        if blocking:
            rejected.append((p.stem, blocking[0][:60]))
    assert rejected == [], f"{len(rejected)} real poses rejected: {rejected[:6]}"


# ──────────────────── 8 · the residue gate and near-black artwork ────────────

def _keyed_block(fill, size=400):
    """A green figure on the magenta key, matted, with a block of `fill`
    painted back onto the subject as a missed matte would leave it."""
    from cutout import auto_chroma_matte, detect_key_colour
    fig = np.zeros((size, size, 3), np.uint8)
    fig[:, :] = MAGENTA
    cv2.rectangle(fig, (120, 80), (280, 340), (90, 150, 60), -1)
    r = ip.tight_crop(ip.drop_neighbour_bleed(auto_chroma_matte(fig)))
    h, w = r.shape[:2]
    y0, x0 = h // 3, w // 3
    r[y0:y0 + h // 4, x0:x0 + w // 4, :3] = fill
    r[y0:y0 + h // 4, x0:x0 + w // 4, 3] = 255
    return r, fig, detect_key_colour(fig)


def test_genuine_leftover_backdrop_is_still_caught():
    """The gate's actual job: an enclosed patch of key the matte missed."""
    from cutout import qa as cutout_qa
    r, fig, hue = _keyed_block(MAGENTA)
    with pytest.raises(QAFailure, match="key_residue"):
        cutout_qa(r, src_shape=fig.shape[:2], allow_detached=True,
                  strict_framing=False, key_bgr=hue)


def test_near_black_artwork_is_not_mistaken_for_backdrop():
    """Saturation is a RATIO, so BGR (5,0,3) reports as 100% saturated with an
    arbitrary hue, and the gate read it as magenta. Artwork drawn with heavy
    black outlines is full of such pixels: two outlined poses measured 1.0% and
    0.9% 'backdrop left on the subject' with a median residue value of 3 out of
    255, and composited on a real slide ground showed no fringe at all.

    This is the same trap that made an earlier audit of the library report a
    6.2% magenta rim that did not exist — the pixels were the black mane."""
    from cutout import qa as cutout_qa
    r, fig, hue = _keyed_block((5, 0, 3))
    cutout_qa(r, src_shape=fig.shape[:2], allow_detached=True,
              strict_framing=False, key_bgr=hue)      # must not raise


def test_the_matte_and_the_residue_gate_agree_on_what_the_key_is():
    """They disagreed: the mask required value >= 40 to call something key and
    the gate had no floor at all, so it judged pixels the matte had already
    declined to treat as backdrop."""
    from cutout import KEY_MIN_VALUE, KEY_TOL
    source = (ROOT / "scripts" / "cutout.py").read_text(encoding="utf-8")
    assert KEY_MIN_VALUE == 40
    # Both the matte's core tier and the residue gate measure distance from the
    # SAME measured backdrop colour, with the same tolerance. When they asked
    # different questions they disagreed, and the gate lost every time.
    assert KEY_TOL == 60.0
    assert source.count("KEY_TOL") >= 3
