"""Missing and corrupted browser assets must not replace a complete export."""
from pathlib import Path
import sys

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT.parents[2] / "scripts"))
import render
from post_to_ig import check_export
from art_review_fixture import offline_reviewer, check_fixture
import render_guard


@pytest.fixture(scope="module")
def complete_deck(tmp_path_factory):
    folder = tmp_path_factory.mktemp("render-assets")
    patch = pytest.MonkeyPatch()
    offline_reviewer(patch, folder)
    pose = ROOT / "mascot/library/deadpan.png"
    check_fixture([pose])
    md = folder / "carousel.md"
    md.write_text("**Palette:** charcoal / cream\n\n" + "\n\n".join(
        f"### Slide {n} · Value\n- **H2:** One [[step]].\n- **Body:** Try one small change."
        for n in range(1,10)))
    poses = {n:pose for n in range(1,10)}
    paths = render.render(md, poses, folder / "slides", verbose=False)
    check_export(folder, md)
    before = {p.name:p.read_bytes() for p in paths}
    before["checks.json"] = (folder / "slides/checks.json").read_bytes()
    yield folder, md, poses, before
    patch.undo()


def test_undeclared_font_is_not_mistaken_for_a_loaded_face():
    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch()
        render_guard.check_browser(browser.version)
        page = browser.new_page()
        page.set_content("<p style='font-family:ArchivoBlk'>A test</p>")
        # This is the original false positive, demonstrated in real Chromium.
        assert page.evaluate("document.fonts.check('400 104px ArchivoBlk')") is True
        assert set(page.evaluate(render.FONT_GUARD)) == {"ArchivoBlk", "Familjen"}
        browser.close()


def test_wrong_browser_is_refused():
    with pytest.raises(ValueError, match="Wrong render browser"):
        render_guard.check_browser("0.0.0.0")


def test_dependency_change_invalidates_render_contract(monkeypatch):
    before = render_guard.contract()
    current = render_guard.runtime()
    current["packages"]["playwright"] = "changed"
    monkeypatch.setattr(render_guard, "runtime", lambda: current)
    assert render_guard.contract() != before


def test_changed_render_checks_cannot_publish_an_old_export(complete_deck, monkeypatch):
    folder, md, _, _ = complete_deck
    monkeypatch.setattr(render_guard, "contract", lambda: "a changed check")
    with pytest.raises(ValueError, match="Render this deck again"):
        check_export(folder, md)


@pytest.mark.parametrize("fault", ["missing-font-file", "missing-font-declaration", "bad-font-bytes", "broken-image"])
def test_asset_failure_preserves_previous_export(complete_deck, monkeypatch, tmp_path, fault):
    folder, md, poses, before = complete_deck
    if fault == "missing-font-file":
        monkeypatch.setattr(render, "FONT_DIR", tmp_path / "no-fonts")
        expected, message = SystemExit, "missing font"
    elif fault == "missing-font-declaration":
        monkeypatch.setattr(render, "font_face", lambda *a: "")
        expected, message = SystemExit, "font.*failed to load"
    elif fault == "bad-font-bytes":
        # Keep a real declaration but give the browser invalid font bytes.
        def bad_face(family, filename, weights):
            return f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,YmFk) format('truetype');font-weight:{weights};}}"
        monkeypatch.setattr(render, "font_face", bad_face)
        expected, message = SystemExit, "font.*failed to load"
    else:
        monkeypatch.setattr(render, "data_uri", lambda path: "data:image/png;base64,YmFk")
        expected, message = ValueError, "image.*failed to load"
    with pytest.raises(expected, match=message):
        render.render(md, poses, folder / "slides", verbose=False)
    after = {p.name:p.read_bytes() for p in (folder / "slides").iterdir()}
    assert after == before
    assert (folder / "render-incomplete").exists()
    with pytest.raises(ValueError, match="last render"):
        check_export(folder, md)
