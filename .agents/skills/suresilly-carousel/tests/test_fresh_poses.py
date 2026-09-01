#!/usr/bin/env python3
"""
The fallback, which is the only reason build.py is allowed near the network.

AGENTS.md invariant 2 used to say the render path must never import the
generator, because "a build that needs a network is a build that can fail at
8am with nobody watching". The reasoning was right and the rule was a proxy for
it: what must never fail is the DECK. build.py now reaches the generator behind
--fresh, and these tests are what replaces the old prohibition — they assert the
thing the prohibition was protecting.

Every one of them answers the same question: when generation cannot happen, does
a deck still come out, made of the poses the library already chose? Nothing here
touches the network.
"""
import sys
import pathlib
import types

import cv2
import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fresh_poses  # noqa: E402


SLIDES = [
    {"mascot": "sitting on the edge of a bed with his head lowered"},
    {"mascot": "standing square with both hooves raised in a shrug"},
]


def fallback(tmp_path) -> dict[int, pathlib.Path]:
    out = {}
    for n in (1, 2):
        p = tmp_path / f"library_{n}.png"
        p.write_bytes(b"not really a png")
        out[n] = p
    return out


def fake_flux(**overrides) -> types.ModuleType:
    """A stand-in for poses_flux that fails however the test wants it to."""
    mod = types.ModuleType("poses_flux")
    mod.np = np
    mod.QAFailure = fresh_poses.QAFailure
    mod.credentials = lambda: ("acct", "token")
    mod.pick_references = lambda brief="", **k: [("deadpan", b"x")]
    mod.estimate_neurons = lambda w, h, r: 126.0    # one pose at the published rate
    mod.build_prompt = lambda brief: brief
    mod.correct_palette = lambda a: a
    mod.assert_no_text = lambda a, w: None

    class Ledger:
        def __init__(self, budget=None):
            pass

        def check(self, cost):
            pass

        def spend(self, cost, note=""):
            pass

        def reconcile(self, reserved, actual, note=""):
            pass

    mod.Ledger = Ledger
    mod.generate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down"))
    for key, value in overrides.items():
        setattr(mod, key, value)
    return mod


def run(monkeypatch, tmp_path, module):
    monkeypatch.setitem(sys.modules, "poses_flux", module)
    return fresh_poses.generate_for_deck(
        SLIDES, fallback(tmp_path), tmp_path / "out", log=lambda *a: None)


# ─────────────────── every failure keeps the deck ────────────────────────────

def test_no_generator_module_at_all_still_returns_a_full_deck(monkeypatch, tmp_path):
    """The machine with no poses_flux, or a poses_flux that will not import."""
    broken = types.ModuleType("poses_flux")

    def explode(*a, **k):
        raise ImportError("no module")
    monkeypatch.setitem(sys.modules, "poses_flux", None)   # forces an import error
    given = fallback(tmp_path)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert out == given
    assert stats["generated"] == 0
    assert stats["fell_back"] == len(given)


def test_missing_credentials_still_returns_a_full_deck(monkeypatch, tmp_path):
    """The 8am case the old invariant was written for: no key on the runner."""
    mod = fake_flux(credentials=lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert out == given
    assert stats["fell_back"] == len(given)


def test_the_network_failing_mid_deck_still_returns_a_full_deck(monkeypatch, tmp_path):
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", fake_flux())
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert out == given, "a failed generation must leave the library pose in place"
    assert stats["generated"] == 0 and stats["fell_back"] == 2


def test_an_exhausted_budget_still_returns_a_full_deck(monkeypatch, tmp_path):
    class Broke:
        def __init__(self, budget=None):
            pass

        def check(self, cost):
            raise RuntimeError("budget exhausted")
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", fake_flux(Ledger=Broke))
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert out == given


def test_a_frame_with_text_in_it_is_refused_and_falls_back(monkeypatch, tmp_path):
    """Invariant 3 is not suspended because the picture is fresh."""
    frame = np.full((256, 256, 3), (255, 0, 255), np.uint8)
    ok, buf = cv2.imencode(".png", frame)
    assert ok

    def has_text(arr, what):
        raise fresh_poses.QAFailure("no_text: caption")
    mod = fake_flux(generate=lambda *a, **k: (buf.tobytes(), 1.0),
                    assert_no_text=has_text)
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert out == given
    assert any("no_text" in r for r in stats["reasons"])


def _frame_with_eyes(left_pupil: bool, right_pupil: bool,
                     right_size: int = 28) -> bytes:
    """A magenta-backdrop frame holding a green figure with two eye whites."""
    frame = np.full((512, 512, 3), (255, 0, 255), np.uint8)
    cv2.rectangle(frame, (150, 100), (370, 400), (90, 150, 60), -1)
    for cx, size, pupil in ((215, 28, left_pupil), (305, right_size, right_pupil)):
        cv2.circle(frame, (cx, 170), size, (255, 255, 255), -1)
        if pupil:
            cv2.circle(frame, (cx, 170), max(4, size // 3), (25, 25, 25), -1)
    ok, buf = cv2.imencode(".png", frame)
    assert ok
    return buf.tobytes()


def test_a_blank_eye_is_refused_and_falls_back(monkeypatch, tmp_path):
    """The bug that published 20260901_door-pushed-the_572b21.

    Slide 3 went out with a plain white oval where the left eye should have
    been. assert_has_pupils refuses that frame and always would have — measured
    on the published slide, the two whites are 38x37 and 41x40 and the left one
    holds no pupil, which is a matched pair with one blank and the oldest case
    this gate handles. It shipped because THIS function never called the gate.

    poses_flux.check() calls all three of invariant 3's gates. generate_for_deck
    does not go through check() — a scene is not one standing figure — and in
    taking its own route it carried only assert_no_text across. So the test is
    not "does the gate work" (test_poses_flux.py owns that) but "is the gate
    wired into the path that publishes".
    """
    mod = fake_flux(generate=lambda *a, **k: (
        _frame_with_eyes(left_pupil=False, right_pupil=True), 1.0))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                              log=lambda *a: None)
    assert out == given, "a blank-eyed pose must leave the library pose in place"
    assert stats["generated"] == 0
    assert any("pupil" in r for r in stats["reasons"]), stats["reasons"]


def test_a_lopsided_blank_eye_is_refused_and_falls_back(monkeypatch, tmp_path):
    """The neighbouring hole, wired through the same path: a blank eye that is
    also the WRONG SIZE is not a matched pair, and used to be waved through by
    the branch that exists for winks and profiles."""
    mod = fake_flux(generate=lambda *a, **k: (
        _frame_with_eyes(left_pupil=True, right_pupil=False, right_size=14), 1.0))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                              log=lambda *a: None)
    assert out == given
    assert any("pupil" in r for r in stats["reasons"]), stats["reasons"]


def test_two_good_eyes_are_still_generated_for(monkeypatch, tmp_path):
    """The gate must not be so eager that generation stops happening. Same
    frame, both eyes drawn properly, and the pose is used."""
    mod = fake_flux(generate=lambda *a, **k: (
        _frame_with_eyes(left_pupil=True, right_pupil=True), 1.0))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                              log=lambda *a: None)
    assert stats["generated"] == 2, stats["reasons"]
    assert out[1] != given[1] and out[1].is_file()


def test_a_slide_with_no_brief_is_not_generated_for(monkeypatch, tmp_path):
    """Nothing to draw from, so nothing is spent and the library pose stands."""
    calls = []
    mod = fake_flux(generate=lambda *a, **k: calls.append(1) or (b"", 1.0))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    fresh_poses.generate_for_deck([{"mascot": ""}, {"mascot": "  "}], given,
                                  tmp_path / "o", log=lambda *a: None)
    assert calls == []


# ─────────────────── a good frame does get used ──────────────────────────────

def test_a_clean_frame_replaces_the_library_pose(monkeypatch, tmp_path):
    """The fallback must not be so total that generation never takes effect."""
    frame = np.full((512, 512, 3), (255, 0, 255), np.uint8)
    cv2.rectangle(frame, (150, 120), (360, 400), (90, 150, 60), -1)
    ok, buf = cv2.imencode(".png", frame)
    assert ok
    mod = fake_flux(generate=lambda *a, **k: (buf.tobytes(), 1.0))
    given = fallback(tmp_path)
    monkeypatch.setitem(sys.modules, "poses_flux", mod)
    out, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                               log=lambda *a: None)
    assert stats["generated"] == 2
    assert out[1] != given[1] and out[1].is_file()


# ─────────────────── build.py only reaches it when asked ─────────────────────

def test_build_does_not_import_the_generator_at_module_scope():
    """The reachability that matters is at import time. build.py imports
    fresh_poses inside the --fresh branch, so merely importing or running a
    normal build never loads poses_flux and never looks for a key."""
    source = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        if line.startswith(("import ", "from ")):
            assert "fresh_poses" not in line and "poses_flux" not in line, \
                f"module-scope import reaches the generator: {line!r}"
    assert "import fresh_poses" in source, "the flag has to reach it somehow"


def test_fresh_poses_writes_only_into_the_deck_folder(monkeypatch, tmp_path):
    """A pose generated for one deck belongs to that deck. import_poses.py owns
    mascot/library/, and two writers into it is how two subtly different
    libraries happen.

    Checked by watching where it actually writes, not by grepping the source —
    the source explains this rule in a comment, and a grep for the path finds
    the explanation."""
    frame = np.full((512, 512, 3), (255, 0, 255), np.uint8)
    cv2.rectangle(frame, (150, 120), (360, 400), (90, 150, 60), -1)
    ok, buf = cv2.imencode(".png", frame)
    assert ok
    # built BEFORE the patch: this helper writes the stand-in library files, and
    # capturing those would make the test fail on its own fixtures.
    given = fallback(tmp_path)
    written = []
    real = pathlib.Path.write_bytes

    def watched(self, data):
        written.append(pathlib.Path(self).resolve())
        return real(self, data)
    monkeypatch.setattr(pathlib.Path, "write_bytes", watched)

    out_dir = (tmp_path / "deck" / "mascot")
    monkeypatch.setitem(sys.modules, "poses_flux",
                        fake_flux(generate=lambda *a, **k: (buf.tobytes(), 1.0)))
    fresh_poses.generate_for_deck(SLIDES, given, out_dir, log=lambda *a: None)
    library = (ROOT / "mascot" / "library").resolve()
    assert written, "nothing was written, so this test proves nothing"
    for path in written:
        assert library not in path.parents, f"wrote into the library: {path}"
        assert out_dir.resolve() in path.parents, f"wrote outside the deck: {path}"


# ─────────────────── generated poses reach the library, but not directly ─────

def test_the_same_brief_always_lands_on_the_same_library_name():
    """Regenerating a deck must refresh its poses, not pile up near-identical
    ones. And two briefs that open with the same words must not collide, which
    is what the digest of the whole brief is for."""
    a = "sitting on the edge of a bed with his head lowered"
    b = "sitting on the edge of a bed with his head held high"
    assert fresh_poses.pose_name(a) == fresh_poses.pose_name(a)
    assert fresh_poses.pose_name(a) != fresh_poses.pose_name(b)
    assert fresh_poses.pose_name(a).startswith("sitting_edge_bed")


def test_a_kept_frame_is_raw_and_carries_its_brief(monkeypatch, tmp_path):
    """The library wants the frame BEFORE matting, so its own gates and its own
    matte decide. The brief rides along as a sidecar so the pose enters tagged
    with the body it was drawn from."""
    frame = np.full((512, 512, 3), (255, 0, 255), np.uint8)
    cv2.rectangle(frame, (150, 120), (360, 400), (90, 150, 60), -1)
    ok, buf = cv2.imencode(".png", frame)
    assert ok
    given = fallback(tmp_path)
    keep = tmp_path / "candidates"
    monkeypatch.setitem(sys.modules, "poses_flux",
                        fake_flux(generate=lambda *a, **k: (buf.tobytes(), 1.0)))
    _, stats = fresh_poses.generate_for_deck(SLIDES, given, tmp_path / "o",
                                             keep_dir=keep, log=lambda *a: None)
    assert len(stats["kept"]) == 2
    for name in stats["kept"]:
        png = keep / f"{name}.png"
        brief = keep / f"{name}.brief.txt"
        assert png.is_file() and brief.is_file()
        kept = cv2.imread(str(png), cv2.IMREAD_UNCHANGED)
        assert kept.shape[2] == 3, "the library gets the raw frame, not a matte"
        assert brief.read_text().strip() in [s["mascot"] for s in SLIDES]


def test_the_library_is_grown_only_through_the_import_script():
    """build.py hands generated frames to import_poses.py rather than writing
    mascot/library/ itself. One writer, so the gates, the naming and the
    manifest merge are the same for a generated pose as for a hand-made one."""
    source = (ROOT / "scripts" / "build.py").read_text(encoding="utf-8")
    assert "import_poses.main_argv" in source
    fresh = (ROOT / "scripts" / "fresh_poses.py").read_text(encoding="utf-8")
    assert "import_poses" not in fresh.split('"""')[2], \
        "fresh_poses must not reach the library itself"


def test_a_brief_sidecar_becomes_tags():
    """The physical vocabulary the tag corpus never had."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import import_poses
    d = pathlib.Path(__file__).parent / "_sidecar_tmp"
    d.mkdir(exist_ok=True)
    try:
        (d / "x.brief.txt").write_text("sitting on the edge of a bed, ears drooping")
        tags = import_poses.sidecar_tags(d / "x.png")
        assert "sitting" in tags and "bed" in tags and "drooping" in tags
        assert "the" not in tags and "donkey" not in tags
    finally:
        for f in d.iterdir():
            f.unlink()
        d.rmdir()


# ─────────────────── the dashboard never takes a message down ────────────────

def test_the_dashboard_survives_missing_state(tmp_path, monkeypatch):
    """It runs after the post, so a state file it cannot read must print as
    'unknown' rather than costing the whole report. A fresh checkout has no
    insights ledger and no pending folder, and that is normal, not an error."""
    sys.path.insert(0, str(ROOT.parents[2] / "scripts"))
    import dashboard
    monkeypatch.setattr(dashboard, "STATE", tmp_path / "nothing-here")
    monkeypatch.setattr(dashboard, "SKILL", tmp_path / "also-nothing")
    text = dashboard.build("ok", "some_slug", "", None, None)
    assert "PICTURES" in text and "QUEUE" in text
    assert "unknown" in text                      # it degraded rather than raised


def test_the_dashboard_reports_every_section():
    sys.path.insert(0, str(ROOT.parents[2] / "scripts"))
    import dashboard
    text = dashboard.build("held", "a_slug", "held because X", "62", "http://run")
    for section in ("PICTURES", "LIBRARY", "THIS DECK", "QUEUE", "REVIEW", "MEASURED"):
        assert section in text, f"{section} missing from the dashboard"
    assert "held because X" in text and "62/100" in text and "http://run" in text


def test_the_dashboard_never_feeds_numbers_back_into_the_pipeline():
    """Invariant 17. Reach and saves are printed for a person to read and are
    never consumed by anything that decides what ships."""
    source = (ROOT.parents[2] / "scripts" / "dashboard.py").read_text(encoding="utf-8")
    for module in ("library", "writer", "critic", "compose", "run"):
        assert f"import {module}" not in source, \
            f"the dashboard imports {module}; it must only read state"
