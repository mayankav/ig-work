"""Real production defects are evidence, never selectable library material."""
from pathlib import Path
import sys
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cutout


@pytest.mark.parametrize("name", ["blank_profile_eye", "malformed_eyelids"])
def test_real_eye_defects_fail(name):
    path = Path(__file__).parent / "fixtures/rejected_art" / (name + ".png")
    with pytest.raises(cutout.QAFailure, match="pupil"):
        cutout.assert_has_pupils(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), name)


def test_extra_leg_is_preserved_for_vision_qualification():
    assert (Path(__file__).parent / "fixtures/rejected_art/extra_leg.png").is_file()


def test_bad_art_is_not_in_library():
    library = Path(__file__).resolve().parents[1] / "mascot/library"
    for name in ("turning_head_away_from_56e9", "standing_quietly_by_closed_cb47", "shifting_weight_from_front_6ae5"):
        assert not (library / (name + ".png")).exists()
