"""Production wiring and replayable evidence, without a vendor or live state."""
import base64
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from art_review_fixture import offline_reviewer, check_fixture
import art_eligibility as art
import image_qualification
import image_review
import llm


@pytest.fixture
def checked(tmp_path, monkeypatch):
    context, reply = offline_reviewer(monkeypatch, tmp_path)
    path = tmp_path / "pose.png"
    path.write_bytes((ROOT / "mascot/library/deadpan.png").read_bytes())
    check_fixture([path])
    return path, context, reply


def test_unchecked_clean_image_is_not_eligible(tmp_path, monkeypatch):
    monkeypatch.setattr(art, "STORE", tmp_path / "missing")
    assert art.faults(ROOT / "mascot/library/deadpan.png")


def test_exact_copy_can_use_same_proof(checked, tmp_path):
    path, _, _ = checked
    other = tmp_path / "renamed.png"
    other.write_bytes(path.read_bytes())
    assert not art.faults(other)
    art.check_proof(art.proof(other.read_bytes()))


def test_changed_bytes_cannot_use_old_check(checked):
    path, _, _ = checked
    path.write_bytes(path.read_bytes() + b"new bytes")
    assert art.faults(path)


def test_changed_version_invalidates_evidence(checked, monkeypatch):
    monkeypatch.setattr(art, "contract", lambda: "new check version")
    assert art.faults(checked[0]) == ("artwork check version changed",)


def test_expired_qualification_blocks_saved_art(checked, monkeypatch):
    monkeypatch.setattr(image_qualification, "qualified_models", lambda: [])
    assert "qualification" in art.faults(checked[0])[0]


def test_tampered_record_cannot_supply_permission(checked):
    raw = checked[0].read_bytes()
    proof = art.proof(raw)
    receipt = art.STORE / "reviews" / (proof["receipt"] + ".json")
    receipt.write_text('{"approved":true}')
    assert art.faults_bytes(raw) == ("artwork check record changed",)


@pytest.mark.parametrize("failure", ["missed-control", "uncertain", "missing-panel", "outage", "wrong-model"])
def test_failed_new_check_revokes_previous_evidence(checked, monkeypatch, failure):
    path, context, reply = checked
    previous = art.proof(path.read_bytes())
    def fail(*args, **kwargs):
        if failure == "outage":
            raise TimeoutError("test outage")
        answer, model = reply()
        if failure == "missed-control":
            for figure in answer["figures"]: figure["legs"] = 2
        elif failure == "uncertain": answer["uncertain"] = [context["control"]]
        elif failure == "missing-panel": answer["inspected"].pop()
        else: model = "another/model"
        return answer, model
    monkeypatch.setattr(llm, "look_once", fail)
    assert art.check_paths({1: path}, log=lambda _: None)
    assert art.faults(path)
    with pytest.raises(ValueError): art.check_proof(previous)


def test_group_veto_only_removes_named_candidate(checked, monkeypatch, tmp_path):
    path, context, reply = checked
    other = tmp_path / "other.png"
    other.write_bytes((ROOT / "mascot/library/side_eye.png").read_bytes())
    def veto(*args, **kwargs):
        answer, model = reply()
        panel = next(p for p, n in context["mapping"].items() if n == 2)
        answer["faults"] = [{"panel": panel, "code": "extra_limb", "fault": "an extra leg"}]
        return answer, model
    monkeypatch.setattr(llm, "look_once", veto)
    assert set(art.check_paths({1: path, 2: other}, log=lambda _: None)) == {2}
    assert not art.faults(path)
    assert art.faults(other)


def test_group_inputs_and_sheet_are_bound(checked):
    path, _, _ = checked
    proof = art.proof(path.read_bytes())
    record = json.loads((art.STORE / "reviews" / (proof["receipt"] + ".json")).read_bytes())
    record["sheet_sha256"] = "wrong"
    art._save(record, [path.read_bytes()])
    assert art.faults(path) == ("artwork inspection sheet changed",)


def test_no_more_than_three_requests(checked, monkeypatch):
    path, _, reply = checked
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return reply()
    monkeypatch.setattr(llm, "look_once", counted)
    assert not art.check_paths({i: path for i in range(1, 10)}, log=lambda _: None)
    assert len(calls) == 3
    assert len(art.check_paths({i: path for i in range(10)}, log=lambda _: None)) == 10
    assert len(calls) == 3


def test_file_changed_during_request_is_rejected(checked, monkeypatch):
    path, _, reply = checked
    def change(*args, **kwargs):
        result = reply()
        path.write_bytes(path.read_bytes() + b"changed")
        return result
    monkeypatch.setattr(llm, "look_once", change)
    assert "changed" in art.check_paths({1: path}, log=lambda _: None)[1]


def test_library_and_explicit_reference_require_same_evidence(checked, monkeypatch, tmp_path):
    import library
    import poses_flux
    path, _, _ = checked
    second = tmp_path / "unchecked.png"
    second.write_bytes((ROOT / "mascot/library/side_eye.png").read_bytes())
    monkeypatch.setattr(library, "LIBRARY_DIR", tmp_path)
    assert library.available() == {"pose"}
    assert poses_flux.pick_references(names=[str(path)], count=1)
    with pytest.raises(poses_flux.FluxError, match="body and eye check"):
        poses_flux.pick_references(names=[str(second)], count=1)


def test_import_does_not_grant_eligibility(checked, monkeypatch, tmp_path):
    import import_poses
    library = tmp_path / "target"
    manifest = tmp_path / "poses.json"
    monkeypatch.setattr(import_poses, "LIBRARY", library)
    monkeypatch.setattr(import_poses, "MANIFEST", manifest)
    monkeypatch.setattr(import_poses, "contact_sheet", lambda *a: None)
    bad = tmp_path / "extra.png"
    bad.write_bytes((ROOT / "tests/fixtures/rejected_art/extra_leg.png").read_bytes())
    import_poses.main_argv([str(bad), "--exact"])
    assert not (library / bad.name).exists()
    import_poses.main_argv([str(checked[0]), "--exact"])
    assert (library / checked[0].name).read_bytes() == checked[0].read_bytes()


def test_direct_render_refuses_unchecked_art_before_browser(tmp_path, monkeypatch):
    import render
    monkeypatch.setattr(art, "STORE", tmp_path / "empty")
    md = tmp_path / "carousel.md"
    md.write_text("\n".join(f"### Slide {i} · Hook\n- **H1:** A test" for i in range(1,10)))
    monkeypatch.setattr(render, "_render", lambda *a: pytest.fail("browser must not run"))
    with pytest.raises(ValueError, match="body and eye check"):
        render.render(md, {i: ROOT / "mascot/library/deadpan.png" for i in range(1,10)}, tmp_path / "slides")
    assert not (tmp_path / "slides/checks.json").exists()


def test_a_veto_applies_to_identical_bytes_in_every_panel(checked, monkeypatch):
    path, context, reply = checked
    def veto(*args, **kwargs):
        answer, model = reply()
        answer["faults"] = [{"panel": min(context["mapping"]), "code": "extra_limb",
                             "fault": "an extra leg"}]
        return answer, model
    monkeypatch.setattr(llm, "look_once", veto)
    assert set(art.check_paths({1:path, 2:path}, log=lambda _: None)) == {1,2}


def test_no_qualified_reviewer_sends_no_request(checked, monkeypatch):
    def unavailable(): raise llm.ModelRefused("no qualified model")
    monkeypatch.setattr(image_review, "model_for_review", unavailable)
    monkeypatch.setattr(llm, "look_once", lambda *a, **k: pytest.fail("no request permitted"))
    assert art.check_paths({1:checked[0]}, log=lambda _: None)


@pytest.mark.parametrize("force", [False, True])
def test_empty_checked_library_stops_before_fetching_or_writing(monkeypatch, force):
    import run as runner
    import library
    events = []
    monkeypatch.setattr(runner, "check_halt", lambda: None)
    monkeypatch.setattr(runner, "check_state_is_current", lambda **k: "current")
    monkeypatch.setattr(library, "available", lambda: set())
    monkeypatch.setattr(runner, "draw", lambda: pytest.fail("no feed request allowed"))
    monkeypatch.setattr(runner, "draw_concept", lambda: pytest.fail("no source request allowed"))
    monkeypatch.setattr(runner, "record_faults", lambda *a: None)
    monkeypatch.setattr(runner, "emit", lambda **k: events.append(k))
    assert runner.run("no-post", force=force) == 0
    assert events[-1]["retry"] == "false"
    assert "Only 0 library images" in events[-1]["reason"]
