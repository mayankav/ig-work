from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from outcomes import fault_signature, unchanged_faults


def test_equal_counts_are_not_equal_faults():
    assert not unchanged_faults([fault_signature([v]) for v in ["too long", "missing source", "missing script"]])


def test_three_unchanged_faults_stop():
    a = fault_signature(["Slide 5 too long", "Slide 3 repeated"])
    b = fault_signature(["  slide 3 repeated  ", "Slide 5 too long"])
    assert not unchanged_faults([a, b])
    assert unchanged_faults([a, b, a])


def test_clean_is_not_stuck():
    assert not unchanged_faults([(), (), ()])
