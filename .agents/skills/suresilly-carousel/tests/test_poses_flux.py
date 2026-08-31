#!/usr/bin/env python3
"""
poses_flux regression. No network is touched by any test in this file.

The three things worth locking here, in order of what they would cost:

  1 · THE LICENCE. @cf/black-forest-labs/flux-2-klein-4b is apache-2.0. The 9B
      that sits one row below it in Cloudflare's pricing table makes visibly
      nicer pictures and is licensed flux-non-commercial. @suresilly is a
      commercial page, so every pose made with the 9B would be unshippable and
      nothing downstream would notice. A one-word edit does that, which is
      exactly why it is a test.

  2 · INVARIANT 3, no text in mascot artwork. The gate has to reject a caption
      wherever it lands in the frame, and it has to accept all 180 poses in the
      real library. The first draft of the detector had the shape rules right
      and no isolation rule, and called 82 of those 180 poses "text" — a gate
      that fires on nearly half the good artwork is not a gate, it is a coin
      toss somebody eventually switches off.

  3 · THAT THIS IS NOT A RUNTIME PATH. build.py renders with no key and no
      network. If anything on the render path ever imports this module that
      stops being true, and it stops being true on the machine that has no
      credentials, which is not the machine anybody tests on.
"""
import json
import re
import pathlib
import sys

import cv2
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import poses_flux as pf  # noqa: E402
from cutout import QAFailure  # noqa: E402

MAGENTA = pf.CHROMA_BGR
GREEN = (90, 150, 60)


# ─────────────────────────── helpers ─────────────────────────────────────────

def frame(size: int = 512, bg=MAGENTA) -> np.ndarray:
    img = np.zeros((size, size, 3), np.uint8)
    img[:, :] = bg
    return img


def figure(size: int = 512, bg=MAGENTA) -> np.ndarray:
    """A single blob on a chroma backdrop: the shape a good generation has."""
    img = frame(size, bg)
    cv2.ellipse(img, (size // 2, int(size * 0.42)), (int(size * 0.16), int(size * 0.20)),
                0, 0, 360, GREEN, -1)
    cv2.rectangle(img, (int(size * 0.36), int(size * 0.40)),
                  (int(size * 0.64), int(size * 0.82)), GREEN, -1)
    return img


def caption(img: np.ndarray, y: float, x: float = 0.12, scale: float = 0.9,
            colour=(20, 20, 20)) -> np.ndarray:
    out = img.copy()
    cv2.putText(out, "2. Deadpan", (int(img.shape[1] * x), int(img.shape[0] * y)),
                cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 2, cv2.LINE_AA)
    return out


def encoded(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


# ─────────────────────────── 1 · the licence ─────────────────────────────────

FORBIDDEN = ("flux-2-klein-9b", "flux-2-dev")


def test_model_is_the_apache_licensed_one():
    assert pf.MODEL == "@cf/black-forest-labs/flux-2-klein-4b"


def test_non_commercial_models_are_never_the_model():
    """They may be NAMED in the source — the comment beside MODEL warns about
    them by id, and that warning is the point. What must never happen is one of
    them being what the module actually calls."""
    source = (ROOT / "scripts" / "poses_flux.py").read_text(encoding="utf-8")
    for bad in FORBIDDEN:
        assert bad not in pf.MODEL
        assert f'MODEL = "@cf/black-forest-labs/{bad}"' not in source
    # and the warning itself is still there for whoever reads it next
    assert "non-commercial" in source
    assert "apache-2.0" in source


# ─────────────────────────── 2 · the prompt ──────────────────────────────────

def test_prompt_carries_every_block_of_the_bible():
    blocks = pf.load_blocks()
    prompt = pf.build_prompt("arms crossed, weight on one leg, brow bar low")
    for name in pf.BLOCKS:
        first_line = blocks[name].splitlines()[0]
        assert first_line in prompt, f"{name} block missing from the prompt"
    assert "arms crossed" in prompt


def test_prompt_keeps_the_negative_lock_last():
    """FLUX has no negative-prompt field, so the lock rides in the prompt. It
    goes last because that is the instruction most worth having near the end,
    and it is never abbreviated."""
    prompt = pf.build_prompt("standing, deadpan")
    negative = pf.load_blocks()["NEGATIVE"]
    assert prompt.endswith(negative)
    assert "no letters, no numbers" in prompt


def test_empty_brief_is_refused():
    with pytest.raises(pf.FluxError):
        pf.build_prompt("   ")


def test_a_bible_missing_a_block_is_refused(tmp_path):
    """Three blocks out of four would silently drop the negative lock."""
    text = pf.CHARACTER_MD.read_text(encoding="utf-8")
    text = text.replace("```NEGATIVE", "```NOTNEGATIVE")
    maimed = tmp_path / "CHARACTER.md"
    maimed.write_text(text, encoding="utf-8")
    with pytest.raises(pf.FluxError, match="NEGATIVE"):
        pf.load_blocks(maimed)


# ─────────────────────── 3 · invariant 3, no text ────────────────────────────

@pytest.mark.parametrize("where", [0.95, 0.55, 0.14])
def test_a_caption_is_rejected_anywhere_in_the_frame(where):
    """cutout.qa()'s own caption gate only looks below 80% of the height, which
    is right for an imported sheet cell and blind to a watermark across the
    middle or a signature up in a corner. This one is a superset."""
    with pytest.raises(QAFailure, match="no_text"):
        pf.assert_no_text(caption(figure(), where), "test")


def test_pale_lettering_is_rejected_too():
    """Worked on non-backdrop regions, not on dark pixels, so the colour of the
    lettering does not matter."""
    with pytest.raises(QAFailure, match="no_text"):
        pf.assert_no_text(caption(figure(), 0.92, colour=(255, 220, 255)), "test")


def test_a_clean_figure_passes():
    pf.assert_no_text(figure(), "test")


def test_one_detached_fragment_is_not_text():
    """A sweat drop, a heart, a hoof behind a cape. One blob is not a run, and
    rejecting these threw away good poses the last time somebody tried."""
    img = figure()
    cv2.circle(img, (150, 200), 9, (40, 40, 40), -1)
    pf.assert_no_text(img, "test")


def test_the_whole_real_library_passes_the_text_gate():
    """The regression that matters. An earlier detector keyed on size and
    baseline alone and rejected 82 of these 180 poses, because Silly's mane is
    dozens of small dark curls and his four hooves genuinely do line up along
    the bottom of the frame."""
    poses = [p for p in sorted(pf.LIBRARY.glob("*.png")) if not p.stem.startswith("_")]
    assert len(poses) > 100, "library looks wrong; this test is meaningless without it"
    rejected = []
    for path in poses:
        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        flat = pf._flatten_onto_key(img) if img.shape[2] == 4 else img[:, :, :3]
        try:
            pf.assert_no_text(flat, path.name)
        except QAFailure:
            rejected.append(path.stem)
    assert rejected == [], f"{len(rejected)} good poses called text: {rejected[:8]}"


def test_the_old_style_sheets_are_refused_as_references():
    """mascot/style_refs/ is the obvious-looking source of reference images and
    the wrong one: four 6-up grids with "1. Innocent", "2. Deadpan" printed
    under every cell, head-and-shoulders only. Conditioning on them asks for
    both defects the character bible exists to prevent. Nothing bans that
    directory by name — the sheets fail the text gate on their own captions."""
    sheets = sorted(pf.STYLE_REFS.iterdir())
    assert sheets, "style_refs is empty; this test proves nothing"
    for sheet in sheets:
        with pytest.raises(QAFailure, match="no_text"):
            pf.pick_references([str(sheet)])


# ─────────────────────────── 4 · the other gates ─────────────────────────────

def test_a_missing_chroma_backdrop_is_refused():
    """Downstream picks chroma or paper matting off border saturation. A pose
    on a pale studio background is silently matted as paper, which eats the
    cream muzzle — so it never gets that far."""
    with pytest.raises(QAFailure, match="backdrop"):
        pf.check(encoded(figure(bg=(245, 245, 245))))


def test_a_clean_generation_passes_every_gate():
    pf.check(encoded(figure()))


def test_a_second_figure_is_refused():
    """allow_detached=False here, unlike import_poses.py. There a sheet cell
    legitimately carries fragments; here the model composed the whole frame to
    our instructions, so a second big blob is a second thing in the picture."""
    img = figure()
    cv2.circle(img, (100, 140), 62, GREEN, -1)
    with pytest.raises(QAFailure, match="single_subject"):
        pf.check(encoded(img))


def test_a_clipped_figure_is_refused():
    """strict_framing=True here, also unlike import_poses.py: the FRAMING block
    asks for clear margin on every side, so an edge touch is a bad crop."""
    img = frame()
    cv2.rectangle(img, (150, 0), (360, 470), GREEN, -1)   # ears out of the top
    with pytest.raises(QAFailure, match="framing"):
        pf.check(encoded(img))


def test_junk_bytes_are_refused_not_crashed():
    with pytest.raises(QAFailure, match="decode"):
        pf.check(b"this is not an image")


# ─────────────────────────── 5 · references ──────────────────────────────────

def test_at_most_four_references():
    with pytest.raises(pf.FluxError):
        pf.pick_references(count=pf.MAX_REFS + 1)
    with pytest.raises(pf.FluxError):
        pf.pick_references(count=0)


def test_default_references_come_from_the_library():
    refs = pf.pick_references()
    assert 1 <= len(refs) <= pf.MAX_REFS
    names = [name for name, _ in refs]
    for name in names:
        assert (pf.LIBRARY / f"{name}.png").is_file()
        assert not name.endswith("_m"), "mirrored poses are the wrong way round"
    blobs = [blob for _, blob in refs]
    assert all(b[:8] == b"\x89PNG\r\n\x1a\n" for b in blobs)


def test_references_are_stable_between_runs():
    """Two poses generated a week apart must be the same donkey, so the
    references may not drift."""
    assert pf.pick_references() == pf.pick_references()


def test_references_are_composited_onto_the_key_not_left_transparent():
    """A transparent reference teaches the model nothing about the background,
    and one on white teaches it the wrong thing."""
    rgba = cv2.imread(str(pf.LIBRARY / "deadpan.png"), cv2.IMREAD_UNCHANGED)
    flat = pf._flatten_onto_key(rgba)
    assert flat.shape[2] == 3
    assert flat.shape[0] == flat.shape[1], "reference should be square"
    assert pf.backdrop_fraction(flat) > 0.4
    assert tuple(int(v) for v in flat[0, 0]) == MAGENTA


def test_generation_without_references_is_refused():
    with pytest.raises(pf.FluxError, match="reference"):
        pf.generate("prompt", [], account="a", token="t")


def test_more_than_four_references_is_refused_before_the_call():
    fake = [(f"r{i}", b"x") for i in range(5)]
    with pytest.raises(pf.FluxError):
        pf.generate("prompt", fake, account="a", token="t")


# ─────────────────────────── 6 · the multipart body ──────────────────────────

def test_multipart_shape():
    """The only non-JSON endpoint in the skill, so the encoder is hand-built and
    has to be exactly right: CRLF everywhere, a filename and a content type on
    every file part, and a closing boundary with trailing dashes."""
    content_type, body = pf.encode_multipart(
        {"prompt": "a donkey", "width": "1024"},
        [("input_image_0", "ref_0_deadpan.png", b"\x89PNG-bytes")])

    assert content_type.startswith("multipart/form-data; boundary=")
    boundary = content_type.split("boundary=", 1)[1]
    assert boundary.encode() in body

    assert b'Content-Disposition: form-data; name="prompt"\r\n\r\na donkey\r\n' in body
    assert b'name="input_image_0"; filename="ref_0_deadpan.png"' in body
    assert b"Content-Type: image/png\r\n\r\n\x89PNG-bytes\r\n" in body
    assert body.endswith(f"--{boundary}--\r\n".encode())
    # a bare LF anywhere is the 400 that costs an afternoon
    assert b"\n" not in body.replace(b"\r\n", b"")


def test_reference_images_are_numbered_from_zero():
    refs = [("a", b"1"), ("b", b"2"), ("c", b"3"), ("d", b"4")]
    files = [(f"input_image_{i}", f"ref_{i}_{n}.png", b)
             for i, (n, b) in enumerate(refs)]
    _, body = pf.encode_multipart({}, files)
    for i in range(pf.MAX_REFS):
        assert f'name="input_image_{i}"'.encode() in body
    assert b'name="input_image_4"' not in body


# ─────────────────────────── 7 · the response ────────────────────────────────

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_decode_documented_shape():
    import base64
    raw = json.dumps({"result": {"image": base64.b64encode(JPEG).decode()},
                      "success": True}).encode()
    assert pf.decode_image(raw) == JPEG


def test_decode_raw_binary_body():
    assert pf.decode_image(PNG) == PNG


def test_decode_refusal_is_an_error_not_an_empty_image():
    raw = json.dumps({"success": False, "errors": [{"message": "nope"}]}).encode()
    with pytest.raises(pf.FluxError, match="refused"):
        pf.decode_image(raw)


def test_decode_missing_image_is_an_error():
    with pytest.raises(pf.FluxError, match="no image"):
        pf.decode_image(json.dumps({"result": {}, "success": True}).encode())


def test_suffix_matches_the_actual_bytes():
    """This model returns JPEG whatever output_format says. Writing JPEG into a
    .png works, because cv2 sniffs content, and is still a lie on disk."""
    assert pf.image_suffix(JPEG) == ".jpg"
    assert pf.image_suffix(PNG) == ".png"
    with pytest.raises(pf.FluxError):
        pf.image_suffix(b"GIF89a")


def test_the_extension_written_is_one_import_poses_reads():
    import import_poses  # noqa: F401  — only to prove the module still imports
    accepted = {".png", ".jpg", ".jpeg", ".webp"}
    assert pf.image_suffix(JPEG) in accepted
    assert pf.image_suffix(PNG) in accepted


# ─────────────────────────── 8 · the neuron ledger ───────────────────────────

def ledger(tmp_path, budget=pf.DEFAULT_BUDGET):
    return pf.Ledger(tmp_path / "neurons.json", budget=budget)


def test_a_budget_over_the_free_allowance_is_refused(tmp_path):
    """This tool does not spend money."""
    with pytest.raises(pf.BudgetExceeded):
        pf.Ledger(tmp_path / "n.json", budget=pf.FREE_DAILY_NEURONS + 1)


def test_spend_accumulates_and_stops_at_the_budget(tmp_path):
    book = ledger(tmp_path, budget=100)
    book.spend(60)
    assert book.spent() == 60
    book.check(40)
    with pytest.raises(pf.BudgetExceeded, match="left"):
        book.check(41)


def test_reconcile_tops_up_when_the_call_cost_more_than_booked(tmp_path):
    book = ledger(tmp_path)
    book.spend(188.0)
    book.reconcile(188.0, 260.0)
    assert book.spent() == pytest.approx(260.0)


def test_reconcile_never_refunds_a_cheap_looking_header(tmp_path):
    """The header reports about a tenth of the published rate and does not bill
    the output frame at all, so it is a floor and not a total. A cheap header
    must not buy throughput — that is how a day runs ten times over the free
    allowance and starts spending the user's money."""
    book = ledger(tmp_path)
    book.spend(188.0)
    book.reconcile(188.0, 21.48)
    assert book.spent() == pytest.approx(188.0)


def test_reconcile_without_a_header_keeps_the_reservation(tmp_path):
    """"We could not check" must never come out the same as "we checked"."""
    book = ledger(tmp_path)
    book.spend(188.0)
    book.reconcile(188.0, None)
    assert book.spent() == pytest.approx(188.0)


def test_the_reservation_uses_the_pessimistic_published_rate():
    """Measured live on 2026-08-31, the header said 5.37 neurons per reference:
    21.48 with four, 10.74 with two, 5.37 with one. The published rate is ten
    times that. One of them is wrong and there is no way from here to tell
    which, so the reservation believes the expensive one."""
    four = pf.estimate_neurons(1024, 1024, 4)
    assert four == pytest.approx(188.0)
    assert four > 21.48 * 5
    assert pf.estimate_neurons(1024, 1024, 1) > 5.37 * 5
    # and a whole day of it still cannot cost real money
    assert pf.DEFAULT_BUDGET <= pf.FREE_DAILY_NEURONS


def test_a_ledger_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "n.json"
    path.write_text("{ not json")
    book = pf.Ledger(path, budget=100)
    assert book.spent() == 0.0
    book.spend(5)
    assert book.spent() == 5


def test_the_ledger_is_shared_between_runs(tmp_path):
    """Two runs must not each believe they have the whole allowance."""
    ledger(tmp_path, budget=100).spend(70)
    assert ledger(tmp_path, budget=100).remaining() == 30


# ─────────────────────────── 9 · the driver ──────────────────────────────────

def test_cost_is_booked_before_the_call_and_kept_on_failure(tmp_path, monkeypatch):
    """A refused or gated image was still generated and still billed."""
    book = ledger(tmp_path)
    monkeypatch.setattr(pf, "generate",
                        lambda *a, **k: (encoded(caption(figure(), 0.94)), 21.48))
    with pytest.raises(QAFailure, match="no_text"):
        pf.make_pose("x", "standing, deadpan", tmp_path, refs=[("d", b"x")],
                     ledger=book)
    assert book.spent() == pytest.approx(pf.estimate_neurons(1024, 1024, 1))
    assert list(tmp_path.glob("x.*")) == [], "a gated pose must write nothing"


def test_a_good_pose_is_written_with_the_right_name(tmp_path, monkeypatch):
    book = ledger(tmp_path)
    monkeypatch.setattr(pf, "generate", lambda *a, **k: (encoded(figure()), 21.48))
    dest = pf.make_pose("sulking", "slumped forward", tmp_path,
                        refs=[("d", b"x")], ledger=book)
    assert dest.name == "sulking.png"
    assert dest.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_budget_stops_a_batch_before_it_calls(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(pf, "generate",
                        lambda *a, **k: called.append(1) or (encoded(figure()), 1.0))
    book = ledger(tmp_path, budget=1)
    with pytest.raises(pf.BudgetExceeded):
        pf.make_pose("x", "standing", tmp_path, refs=[("d", b"x")], ledger=book)
    assert called == [], "the call must not happen once the budget says no"


def test_a_partial_batch_exits_loud(tmp_path, monkeypatch, capsys):
    """A partial batch that exits 0 gets imported without anybody noticing
    three poses are missing."""
    briefs = tmp_path / "briefs.json"
    briefs.write_text(json.dumps({"good": "standing", "bad": "standing"}))
    seen = []

    def fake(*a, **k):
        seen.append(1)
        return (encoded(figure() if len(seen) == 1 else caption(figure(), 0.94)),
                21.48)

    monkeypatch.setattr(pf, "generate", fake)
    monkeypatch.setattr(pf.time, "sleep", lambda *_: None)
    code = pf.main(["--briefs", str(briefs), "--out", str(tmp_path / "out"),
                    "--refs", "1", "--ledger", str(tmp_path / "n.json")])
    out = capsys.readouterr()
    assert code == 1
    assert "REJECTED" in out.err
    assert "bad" in out.err


def test_print_prompt_touches_no_network(monkeypatch, capsys):
    monkeypatch.setattr(pf, "generate", lambda *a, **k: pytest.fail("called out"))
    assert pf.main(["--name", "x", "--brief", "standing, deadpan",
                    "--print-prompt"]) == 0
    assert "stylised cartoon donkey" in capsys.readouterr().out


def test_dry_run_calls_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pf, "generate", lambda *a, **k: pytest.fail("called out"))
    assert pf.main(["--name", "x", "--brief", "standing", "--dry-run",
                    "--ledger", str(tmp_path / "n.json")]) == 0
    assert "nothing called" in capsys.readouterr().out


def test_the_ledger_path_can_be_redirected(monkeypatch, tmp_path):
    """Bound at construction, not at import. A Ledger whose default is frozen
    into the signature writes a test suite's arithmetic into the repo's real
    ledger, and the next real run believes it has already spent the day."""
    monkeypatch.setattr(pf, "LEDGER_PATH", tmp_path / "redirected.json")
    pf.Ledger(budget=100).spend(7)
    assert (tmp_path / "redirected.json").is_file()
    assert json.loads((tmp_path / "redirected.json").read_text())


# ─────────────────────── 10 · this is not a runtime path ─────────────────────

RENDER_PATH = ("build.py", "run.py", "render.py", "compose.py", "library.py",
               "mascot.py", "import_poses.py", "cutout.py")


IMPORTS_FLUX = re.compile(
    r"^\s*(?:import\s+poses_flux"
    r"|from\s+poses_flux\s+import"
    r"|.*\bimport_module\s*\(\s*[\"']poses_flux)",
    re.MULTILINE)


def test_nothing_on_the_render_path_imports_this_module():
    """No render-path file may pull this module in AT IMPORT TIME.

    Two narrowings, both deliberate, and the second one matters.

    It matches IMPORT STATEMENTS rather than the bare string, because the
    character gates moved into cutout.py and cutout.py had to explain in a
    comment where they came from. A sentence in a docstring cannot open a
    socket.

    And the guarantee has moved. This rule used to be absolute, on the reasoning
    that "a build that needs a network is a build that can fail at 8am with
    nobody watching". The reasoning is right; the rule was a proxy for it. What
    must never fail is the DECK. build.py can now reach the generator through
    fresh_poses under --fresh, and every way that can fail hands the slide back
    the library pose selection already chose. tests/test_fresh_poses.py is where
    that promise is actually tested — missing module, missing key, dead network,
    exhausted budget, a frame that fails a gate — and it is the real replacement
    for the prohibition this test used to be.

    What is still enforced here is the part a fallback cannot cover: nothing on
    the render path may load this module simply by being imported. A default
    build must not look for a key, so the import lives inside the flag.
    """
    for name in RENDER_PATH:
        path = ROOT / "scripts" / name
        if not path.is_file():
            continue
        hit = IMPORTS_FLUX.search(path.read_text(encoding="utf-8"))
        assert not hit, \
            f"{name} imports poses_flux ({hit.group(0).strip()!r}); it is an offline tool"


def test_live_code_is_not_hiding_in_the_obsolete_file():
    """Invariant 6. mascot.py is the obsolete generation script and this work
    does not belong in it."""
    source = (ROOT / "scripts" / "mascot.py").read_text(encoding="utf-8")
    assert "flux" not in source.lower()
    assert "cloudflare" not in source.lower()


def test_this_module_reuses_the_existing_gates_rather_than_reimplementing_them():
    """cutout.qa() decides whether a pose is fit to ship, here as everywhere."""
    source = (ROOT / "scripts" / "poses_flux.py").read_text(encoding="utf-8")
    assert "from cutout import" in source
    assert "auto_chroma_matte" in source
    assert "qa(rgba" in source


def test_credentials_come_from_llm_not_a_second_resolver():
    assert pf.resolve_key.__module__ == "llm"


# ─── palette correction and the pupil gate ───────────────────────────────────
#
# Both exist because of what the first real batch came back looking like: a sage
# body instead of the brand green, a blush muzzle instead of a buttery one, and
# two of four with blank white eyes. The colours were measurably wrong in one
# direction, which is what makes them correctable; the eyes are not correctable
# and are refused instead.

def _library_rgba(name):
    import cv2
    return cv2.imread(str(ROOT / "mascot" / "library" / f"{name}.png"),
                      cv2.IMREAD_UNCHANGED)


def test_correction_moves_the_green_onto_the_library_and_leaves_the_key_alone():
    """The magenta key must survive untouched — everything downstream mattes
    against it, and shifting it would break the one thing already right."""
    import cv2, numpy as np
    sage = np.full((80, 80, 3), (103, 138, 94), np.uint8)      # BGR, washed out
    frame = np.full((200, 200, 3), (255, 0, 255), np.uint8)    # magenta key
    frame[60:140, 60:140] = sage

    before = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[70:130, 70:130, 1].mean()
    fixed = pf.correct_palette(frame)
    after = cv2.cvtColor(fixed, cv2.COLOR_BGR2HSV)[70:130, 70:130, 1].mean()

    assert after > before, "the correction did not raise saturation"
    assert abs(int(after) - int(pf.LIBRARY_GREEN_SAT * 255)) < 30, \
        f"corrected to {after:.0f}, wanted about {pf.LIBRARY_GREEN_SAT * 255:.0f}"
    corners = [fixed[0, 0], fixed[0, -1], fixed[-1, 0], fixed[-1, -1]]
    for px in corners:
        assert tuple(int(c) for c in px) == (255, 0, 255), \
            f"the correction moved the chroma key to {tuple(px)}"


def test_correction_is_idempotent():
    """Running it twice must not keep pushing. A correction that compounds is a
    correction that eventually posterises."""
    import cv2, numpy as np
    frame = np.full((120, 120, 3), (255, 0, 255), np.uint8)
    frame[30:90, 30:90] = (103, 138, 94)
    once = pf.correct_palette(frame)
    twice = pf.correct_palette(once)
    a = cv2.cvtColor(once, cv2.COLOR_BGR2HSV)[40:80, 40:80, 1].mean()
    b = cv2.cvtColor(twice, cv2.COLOR_BGR2HSV)[40:80, 40:80, 1].mean()
    assert abs(a - b) < 8, f"a second pass moved saturation {a:.0f} -> {b:.0f}"


def test_the_pupil_gate_does_not_refuse_the_real_library():
    """The lesson from assert_no_text, which in its first draft called 82 of the
    180 real poses 'text'. A gate is worth nothing until it has been run against
    everything we already ship.

    Three poses are refused and all three are known: `guarded` (narrowed lids),
    `chasing` and `lab_coat`. They are good poses. On THIS path the cost of that
    strictness is a re-roll, which is free, and the cost of loosening it is
    shipping a blank-eyed or cross-eyed Silly beside a proper one. Refusing 1.7%
    is the right side of that trade, and this test exists to make the number
    visible rather than to bless it.

    The gate also runs on the import path now, where it REPORTS and does not
    block — see import_poses.ADVISORY. That is the same 1.7% landing on artwork
    a person chose and handed over, where re-rolling is not free and the picture
    is right there to look at. Same gate, same strictness, different consequence,
    because the cost of a false refusal is different on the two paths.
    """
    import cv2, glob
    from cutout import QAFailure
    refused = []
    files = sorted(glob.glob(str(ROOT / "mascot" / "library" / "*.png")))
    assert len(files) > 100, "the library did not load"
    for path in files:
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None or img.shape[2] < 4:
            continue
        try:
            pf.assert_has_pupils(img, path)
        except QAFailure:
            refused.append(path.rsplit("/", 1)[-1])
    assert set(refused) <= {"guarded.png", "chasing.png", "lab_coat.png"}, \
        f"the pupil gate started refusing library poses: {refused}"
    assert len(refused) / len(files) < 0.03, \
        f"{len(refused)}/{len(files)} refused — too strict to be useful"


def test_the_pupil_gate_catches_a_blank_eye():
    """A white blob with nothing inside it is the failure this gate is for."""
    import numpy as np
    from cutout import QAFailure
    rgba = np.zeros((400, 300, 4), np.uint8)
    rgba[..., :3] = (80, 150, 70)
    rgba[..., 3] = 255
    for cx in (110, 190):                       # two blank white eyes
        rgba[90:150, cx - 30:cx + 30, :3] = (255, 255, 255)
    try:
        pf.assert_has_pupils(rgba, "blank")
    except QAFailure as why:
        assert "pupil" in str(why).lower()
    else:
        raise AssertionError("two blank white eyes were accepted")

    for cx in (110, 190):                       # now give them pupils
        rgba[110:132, cx - 11:cx + 11, :3] = (20, 20, 20)
    pf.assert_has_pupils(rgba, "with pupils")   # must not raise


def test_the_cream_muzzle_is_not_mistaken_for_an_eye():
    """Measured: the library's cream sits at saturation 73-94 and an eye white
    is near zero. A brightness-only mask finds the muzzle, calls it a blank eye,
    and refuses a good pose — which is exactly what the first draft did."""
    import numpy as np
    rgba = np.zeros((400, 300, 4), np.uint8)
    rgba[..., :3] = (80, 150, 70)
    rgba[..., 3] = 255
    rgba[120:200, 100:200, :3] = (180, 227, 253)   # BGR of the cream #FDE3B4
    pf.assert_has_pupils(rgba, "muzzle only")      # closed eyes: must not raise


def test_the_written_frame_is_the_corrected_one():
    """The correction has to reach the file. Judging a picture nobody ever sees
    is worse than not correcting at all, because it looks like it worked."""
    source = (ROOT / "scripts" / "poses_flux.py").read_text(encoding="utf-8")
    assert "corrected, _ = check(blob)" in source
    assert "dest.write_bytes(blob)" not in source, \
        "make_pose is writing the raw model bytes again, discarding the correction"


def test_a_white_prop_cannot_pass_as_an_eye():
    """The defect that made this gate a pair-finder.

    A train-window scene passed with two blank eyes because the picture held a
    135x279 rectangle of pale glass. It was white, blob-shaped and in the upper
    half, so it counted as an eye; something dark inside it satisfied "at least
    one eye has a pupil"; and a prop rescued a face that had none. A fridge, a
    sink, a plate and a laptop screen all do this.

    A lone prop cannot make a matched pair, which is why the unit is the pair.
    """
    import numpy as np
    from cutout import QAFailure
    rgba = np.zeros((500, 400, 4), np.uint8)
    rgba[..., :3] = (80, 150, 70)
    rgba[..., 3] = 255
    for cx in (150, 250):                            # two blank eyes
        rgba[100:160, cx - 30:cx + 30, :3] = (255, 255, 255)
    rgba[60:290, 300:380, :3] = (250, 250, 250)      # a tall pale "window"
    rgba[150:200, 320:360, :3] = (30, 30, 30)        # something dark inside it
    try:
        pf.assert_has_pupils(rgba, "window scene")
    except QAFailure as why:
        assert "blank" in str(why)
    else:
        raise AssertionError("a white prop rescued a face with two blank eyes")


def test_a_tilted_head_is_not_a_crooked_stare():
    """Measured on the real library: comparing the two pupils' ABSOLUTE heights
    refused 11 good poses — jumping, leaping, falling, chasing, on_back — every
    one of them a tilted head, where eyes at different heights is correct
    drawing. Each pupil is judged inside its own eye instead."""
    import numpy as np
    rgba = np.zeros((500, 400, 4), np.uint8)
    rgba[..., :3] = (80, 150, 70)
    rgba[..., 3] = 255
    # Two eyes, the right one 40px lower — a head tilted hard. Both pupils sit
    # in the same place within their own white.
    for cx, top in ((150, 90), (250, 130)):
        rgba[top:top + 60, cx - 30:cx + 30, :3] = (255, 255, 255)
        rgba[top + 22:top + 42, cx - 10:cx + 10, :3] = (25, 25, 25)
    pf.assert_has_pupils(rgba, "tilted head")        # must not raise


def test_one_pupil_high_and_one_low_is_refused():
    import numpy as np
    from cutout import QAFailure
    rgba = np.zeros((500, 400, 4), np.uint8)
    rgba[..., :3] = (80, 150, 70)
    rgba[..., 3] = 255
    rgba[100:160, 120:180, :3] = (255, 255, 255)
    rgba[104:120, 140:160, :3] = (25, 25, 25)        # left pupil near the top
    rgba[100:160, 220:280, :3] = (255, 255, 255)
    rgba[142:158, 240:260, :3] = (25, 25, 25)        # right pupil near the bottom
    try:
        pf.assert_has_pupils(rgba, "crooked")
    except QAFailure as why:
        assert "crooked" in str(why) or "high in its eye" in str(why)
    else:
        raise AssertionError("a crooked stare was accepted")


# ─────────────────── references match the brief's posture ────────────────────

def test_a_falling_brief_draws_airborne_references():
    """The defect this fixes, measured twice on 2026-08-31: a brief asking Silly
    to tumble head over heels came back mid-jump and upright, because all four
    references were upright. References decide the body; wording does not."""
    names = [n for n, _ in pf.pick_references(
        brief="tumbling and falling head over heels through the air")]
    descriptions = pf._descriptions()
    airborne = [n for n in names
                if "airborne" in pf.posture_families(descriptions.get(n, n))]
    assert airborne, f"nothing airborne among {names}"


def test_a_lying_brief_draws_lying_references():
    names = [n for n, _ in pf.pick_references(
        brief="lying face down on the floor, not moving")]
    descriptions = pf._descriptions()
    lying = [n for n in names
             if "lying" in pf.posture_families(descriptions.get(n, n))]
    assert lying, f"nothing lying down among {names}"


def test_the_anchors_are_always_there():
    """Half the slots never move. That is what keeps two poses generated a week
    apart the same donkey, which is what the old fixed slice was protecting and
    what this must not give up."""
    for brief in ("tumbling through the air", "lying flat on his back",
                  "walking away down a hallway", ""):
        names = [n for n, _ in pf.pick_references(brief=brief)]
        for anchor in pf.ANCHORS:
            assert anchor in names, f"{anchor} missing for {brief!r}"


def test_the_same_brief_always_draws_the_same_references():
    brief = "sitting on the edge of a bed with his head lowered"
    assert pf.pick_references(brief=brief) == pf.pick_references(brief=brief)


def test_a_brief_with_no_posture_falls_back_to_the_fixed_set():
    """A brief that never says what the body is doing gives nothing to match on,
    and the anchors are a better guess than a coincidence."""
    assert pf.posture_matches("a thoughtful moment about trust", 2) == []


def test_posture_references_are_never_mirrored_or_pair_scenes():
    """The same rule the fixed slice had: a flipped Silly has his mane on the
    wrong side, and a two-donkey reference produces two donkeys."""
    for brief in ("sitting down", "standing tall", "falling through the air"):
        for name, _ in pf.pick_references(brief=brief):
            assert not name.endswith("_m")
            assert pf._library_poses().count(name) == 1
