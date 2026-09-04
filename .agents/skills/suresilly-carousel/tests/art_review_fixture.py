"""Offline response fixture, NOT evidence that any real model can judge art.

Eligibility tests exercise the real receipt and parser around this substitute.
All evidence is saved under pytest's temporary directory, never the library.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import art_eligibility as eligibility
import image_review
import image_qualification
import llm


def offline_reviewer(monkeypatch, tmp_path):
    model = ("gemini", llm.GEMINI_MODELS[0])
    monkeypatch.setattr(eligibility, "STORE", tmp_path / "checks")
    monkeypatch.setattr(image_review, "model_for_review", lambda: model)
    monkeypatch.setattr(image_qualification, "qualified_models", lambda: [model])
    context = {}
    original = image_review.prepare_group

    def prepare(tiles):
        sheet, mapping, control = original(tiles)
        context.update(mapping=mapping, control=control)
        return sheet, mapping, control

    def reply(*args, **kwargs):
        panels = sorted(set(context["mapping"]) | {context["control"]})
        return {"inspected": panels, "uncertain": [], "faults": [],
                "figures": [{"panel": n, "arms": 2,
                             "legs": 3 if n == context["control"] else 2}
                            for n in panels]}, "/".join(model)

    monkeypatch.setattr(image_review, "prepare_group", prepare)
    monkeypatch.setattr(llm, "look_once", reply)
    return context, reply


def check_fixture(paths):
    assert not eligibility.check_paths(dict(enumerate(paths, 1)), log=lambda _: None)
