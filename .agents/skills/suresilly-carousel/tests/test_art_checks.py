"""The saved library cannot bypass the pixel gates used at image creation."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import art_checks
import library


def test_known_bad_eyes_are_not_selectable(monkeypatch):
    monkeypatch.setattr(library, "LIBRARY_DIR", ROOT / "tests/fixtures/rejected_art")
    available = library.available()
    assert "blank_profile_eye" not in available
    assert "malformed_eyelids" not in available
    # Extra-leg review is not claimed by a pixel test; qualification owns it.


@pytest.mark.parametrize("name", ["chasing", "guarded", "lab_coat", "sulking", "hoodie_drink", "kaleidoscope"])
def test_library_audit_failures_have_no_exception(name):
    assert art_checks.pixel_faults(ROOT / "mascot/library" / (name + ".png"))


def test_changed_bytes_invalidate_cached_pixel_result(tmp_path):
    path = tmp_path / "same-name.png"
    path.write_bytes((ROOT / "mascot/library/deadpan.png").read_bytes())
    assert not art_checks.pixel_faults(path)
    path.write_bytes((ROOT / "tests/fixtures/rejected_art/blank_profile_eye.png").read_bytes())
    assert art_checks.pixel_faults(path)


def test_unreadable_art_is_rejected(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    assert art_checks.pixel_faults(path)
    assert art_checks.pixel_faults(tmp_path / "missing.png")


@pytest.mark.parametrize("name", ["deadpan", "hoodie_drink", "chasing"])
def test_in_memory_and_saved_file_have_identical_checks(name):
    path = ROOT / "mascot/library" / (name + ".png")
    assert art_checks.pixel_faults_bytes(path.read_bytes()) == art_checks.pixel_faults(path)


@pytest.mark.parametrize("raw", [b"", b"not a png", b"\x89PNG\r\n\x1a\ntruncated"])
def test_invalid_encoding_always_refuses(raw):
    assert art_checks.pixel_faults_bytes(raw)


def test_dependency_version_change_invalidates_pixel_cache(monkeypatch):
    raw = (ROOT / "mascot/library/deadpan.png").read_bytes()
    assert not art_checks.pixel_faults_bytes(raw)
    monkeypatch.setattr(art_checks.cv2, "__version__", "different-test-version")
    def changed_check(*args):
        raise art_checks.cutout.QAFailure("new check ran")
    monkeypatch.setattr(art_checks.cutout, "assert_on_palette", changed_check)
    assert "new check ran" in art_checks.pixel_faults_bytes(raw)


def test_generation_reference_cannot_bypass_bad_eyes():
    import poses_flux
    path = ROOT / "tests/fixtures/rejected_art/blank_profile_eye.png"
    with pytest.raises(poses_flux.FluxError, match="pixel checks.*pupil"):
        poses_flux.pick_references(names=[str(path)], count=1)
