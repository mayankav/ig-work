"""The reviewed bytes, not another crop of the source, enter the library."""
from pathlib import Path
import hashlib
import json
import sys

import cv2
import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import import_poses as ip
from art_review_fixture import offline_reviewer, check_fixture


@pytest.fixture
def target(tmp_path, monkeypatch):
    offline_reviewer(monkeypatch, tmp_path)
    check_fixture([SKILL / "mascot/library/deadpan.png"])
    library = tmp_path / "library"
    manifest = tmp_path / "poses.json"
    manifest.write_text(json.dumps({"poses": {}}))
    monkeypatch.setattr(ip, "LIBRARY", library)
    monkeypatch.setattr(ip, "MANIFEST", manifest)
    monkeypatch.setattr(ip, "contact_sheet", lambda *a: None)
    return library, manifest


def source(tmp_path, name="deadpan"):
    path = tmp_path / "source.png"
    path.write_bytes((SKILL / "mascot/library" / (name + ".png")).read_bytes())
    return path


def test_exact_import_preserves_every_byte(tmp_path, target, monkeypatch):
    path = source(tmp_path)
    raw = path.read_bytes()
    for function in ("to_rgba", "tight_crop", "drop_neighbour_bleed", "correct_palette"):
        monkeypatch.setattr(ip, function, lambda *a: pytest.fail("Exact art must not be changed"))
    ip.main_argv([str(path), "--exact"])
    library, manifest = target
    assert (library / path.name).read_bytes() == raw
    assert "source" in json.loads(manifest.read_text())["poses"]


@pytest.mark.parametrize("options", [["--mirror"], ["--grid", "1x1"],
    ["--correct-palette"], ["--allow", "palette"], ["--allow", "pupils"]])
def test_exact_mode_cannot_transform_or_override(tmp_path, target, options):
    path = source(tmp_path)
    with pytest.raises(SystemExit, match="cannot crop"):
        ip.main_argv([str(path), "--exact", *options])
    assert not target[0].exists()


def test_exact_rejects_raw_rgb_frame(tmp_path, target):
    path = source(tmp_path)
    rgb = cv2.imread(str(path), cv2.IMREAD_COLOR)
    cv2.imwrite(str(path), rgb)
    ip.main_argv([str(path), "--exact"])
    assert not (target[0] / path.name).exists()
    assert json.loads(target[1].read_text())["poses"] == {}


@pytest.mark.parametrize("name", ["blank_profile_eye", "malformed_eyelids"])
def test_exact_mode_still_blocks_real_eye_faults(tmp_path, target, name):
    path = tmp_path / "bad.png"
    path.write_bytes((SKILL / "tests/fixtures/rejected_art" / (name + ".png")).read_bytes())
    ip.main_argv([str(path), "--exact"])
    assert not (target[0] / path.name).exists()
    assert json.loads(target[1].read_text())["poses"] == {}


def test_source_changed_during_check_cannot_replace_checked_bytes(tmp_path, target, monkeypatch):
    path = source(tmp_path)
    raw = path.read_bytes()
    real = ip.run_gates
    def change_after_check(*args, **kwargs):
        result = real(*args, **kwargs)
        path.write_bytes(b"unreviewed replacement")
        return result
    monkeypatch.setattr(ip, "run_gates", change_after_check)
    ip.main_argv([str(path), "--exact"])
    assert (target[0] / path.name).read_bytes() == raw


def test_build_requires_exact_import_and_candidate_hash():
    code = (SKILL / "scripts/build.py").read_text()
    assert '"--exact"' in code
    assert 'hashlib.sha256(raw).hexdigest() != expected_hash' in code


def test_promotion_preserves_reviewed_bytes(tmp_path, target):
    import build
    path = source(tmp_path)
    raw = path.read_bytes()
    build.promote_checked_candidates([(path, hashlib.sha256(raw).hexdigest())])
    assert (target[0] / path.name).read_bytes() == raw


def test_changed_candidate_blocks_whole_promotion(tmp_path, target):
    import build
    first = source(tmp_path)
    raw = first.read_bytes()
    second = tmp_path / "changed.png"
    second.write_bytes(raw + b"changed after check")
    with pytest.raises(ValueError, match="changed before import"):
        build.promote_checked_candidates([(first, hashlib.sha256(raw).hexdigest()),
                                          (second, hashlib.sha256(raw).hexdigest())])
    assert not target[0].exists()
    assert json.loads(target[1].read_text())["poses"] == {}


@pytest.mark.parametrize("refused", [False, True])
def test_repeated_copy_cannot_generate_or_promote_art(tmp_path, monkeypatch, refused):
    import run as runner
    events = []
    path = tmp_path / "carousel.md"
    path.write_text("### Slide 1 · Hook\n- **H1:** A small test\n")
    monkeypatch.setattr(runner, "anchor_words", lambda m: {"bed", "evening"})
    def check(value):
        events.append("check")
        assert value["slug"] == "test"
        return ["repeated wording"] if refused else []
    monkeypatch.setattr(runner.novelty, "check", check)
    monkeypatch.setattr(runner, "render_slides", lambda *a, **k: events.append("render"))
    if refused:
        with pytest.raises(runner.Refused, match="repeated wording"):
            runner.check_novelty_then_render(path, "test", object(), lambda s: s.get("h1", ""), True)
        assert events == ["check"]
    else:
        runner.check_novelty_then_render(path, "test", object(), lambda s: s.get("h1", ""), True)
        assert events == ["check", "render"]
