"""Live Chromium checks on every active palette and template. No network/state."""
from pathlib import Path
import sys
import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render
import render_guard


def render_independently(*args, **kwargs):
    # The matrix fixture owns a Playwright event loop on the test thread.
    # Exercise the CLI renderer in its own thread, as a standalone invocation.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(render.render, *args, **kwargs).result()


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": render.W, "height": render.H})
        yield page
        browser.close()


def settle(page, spec, theme="charcoal", pose=None):
    page.set_content(render.slide_html(spec, 1, 9, pose, 0, (theme, theme)))
    page.evaluate("document.fonts.ready")
    assert not page.evaluate(render.FONT_GUARD)
    page.evaluate(render.FIT_FIGURE, {"pageH":1350,"pageW":1080,"margin":92,
        "footerH":180,"gap":22,"top":128,"clear":40,"copyMaxY":1068,"min":470,"max":900})


@pytest.mark.parametrize("theme", render.BLEED_THEMES + render.PAPER_THEMES)
@pytest.mark.parametrize("layout", list("ABCDEFGHIJ"))
def test_active_surfaces(page, theme, layout):
    spec = {"role":"value", "layout":"Template " + layout, "h2":"One [[step]].",
            "body":"Try one small change.", "bullets":["Ask.", "Pause.", "Choose."],
            "old_reaction":"When plans change.", "new_reaction":"Can we choose a new time?",
            "myth":"You must rush.", "reality":"You can ask.",
            "source_claim":"A short claim.", "source":"A verified source.",
            "closing":"A small step counts.", "cta1":"Send this to a friend."}
    # Avoid making every template a script through its old_reaction field.
    if layout not in "CG":
        spec.pop("old_reaction"); spec.pop("new_reaction")
    settle(page, spec, theme)
    assert not render_guard.check(page, require_mascot=False)


def test_hidden_and_overlapping_text_fail(page):
    settle(page, {"role":"hook", "h1":"A short line.", "h2":"A second line."})
    page.add_style_tag(content="h2 {position:absolute;top:0;visibility:hidden}")
    assert any("hidden text" in f for f in render_guard.check(page, require_mascot=False))


def test_missing_mascot_fails(page):
    settle(page, {"role":"hook", "h1":"A short line."})
    assert "the mascot is missing" in render_guard.check(page)


def test_missing_copy_fails(page):
    spec = {"role":"hook", "h1":"A short line."}
    settle(page, spec)
    assert "content not rendered: body" in render_guard.check(
        page, require_mascot=False, expected={**spec, "body":"Lost during rendering."})


def test_long_copy_fails(page):
    settle(page, {"role":"hook", "h1":"A short line.", "body":"Long copy. " * 200})
    assert render_guard.check(page, require_mascot=False)


def test_fixed_type(page):
    sizes = []
    for words in ("One step.", "One small step with a friend."):
        settle(page, {"role":"hook", "h1":words})
        sizes.append(page.locator("h1").evaluate("el=>getComputedStyle(el).fontSize"))
    assert sizes == [f"{render.TYPE['h1'][0]}px"] * 2


def test_nine_pngs_and_failed_rebuild_are_not_publishable(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
    from post_to_ig import check_export
    md = tmp_path / "carousel.md"
    md.write_text("**Palette:** charcoal / cream\n\n" + "\n\n".join(
        f"### Slide {i} · Value\n- **Layout:** Template A\n- **H2:** One [[step]].\n- **Body:** Try one small change."
        for i in range(1, 10)))
    lib = Path(__file__).resolve().parents[1] / "mascot/library"
    poses = {i:lib / ("far_apart2.png" if i % 2 else "deadpan.png") for i in range(1,10)}
    assert all(p.is_file() for p in poses.values())
    from art_review_fixture import offline_reviewer, check_fixture
    offline_reviewer(monkeypatch, tmp_path)
    check_fixture([lib / "far_apart2.png", lib / "deadpan.png"])
    paths = render_independently(md, poses, tmp_path / "slides", verbose=False)
    assert len(paths) == 9
    check_export(tmp_path, md)
    before = {p.name:p.read_bytes() for p in paths}
    md.write_text(md.read_text().replace("Try one small change.", "Long copy. " * 150))
    with pytest.raises(ValueError, match="failed final checks"):
        render_independently(md, poses, tmp_path / "slides", verbose=False)
    assert before == {p.name:p.read_bytes() for p in paths}
    with pytest.raises(ValueError, match="last render"):
        check_export(tmp_path, md)


def test_file_changes_after_check_are_rejected(tmp_path, monkeypatch):
    import hashlib
    import json
    from PIL import Image
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
    from post_to_ig import check_export
    from art_review_fixture import offline_reviewer, check_fixture
    import art_eligibility
    offline_reviewer(monkeypatch, tmp_path)
    pose = Path(__file__).resolve().parents[1] / "mascot/library/deadpan.png"
    check_fixture([pose])
    proof = art_eligibility.proof(pose.read_bytes())
    md = tmp_path / "carousel.md"
    md.write_text("test copy")
    slides = tmp_path / "slides"
    slides.mkdir()
    hashes = {}
    for i in range(9):
        path = slides / f"{i}.png"
        Image.new("RGB", (1080,1350), "white").save(path)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (slides / "checks.json").write_text(json.dumps({"complete":True,"has_mascots":True,
        "artwork": {str(i):proof for i in range(1,10)},
        "check_version":render_guard.VERSION,"render_contract":render_guard.contract(),
        "markdown_sha256":hashlib.sha256(md.read_bytes()).hexdigest(),"slides":hashes}))
    check_export(tmp_path, md)
    (slides / "0.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed after inspection"):
        check_export(tmp_path, md)


def test_tight_heading_lines_do_not_confuse_font_boxes_with_ink(page):
    spec={'role':'hook','h1':'Worth Wait. The mistake at [[6pm]], then waiting.', 'h2':'Own your own steady peace.'}
    settle(page,spec)
    assert not [f for f in render_guard.check(page,require_mascot=False) if 'text overlap' in f]


def test_actual_text_overlap_still_fails(page):
    settle(page,{'role':'hook','h1':'A short line.','h2':'A second line.'})
    page.evaluate("""() => {
      const a=document.querySelector('h1'), b=document.querySelector('h2');
      const ar=a.getBoundingClientRect(), br=b.getBoundingClientRect();
      b.style.transform=`translate(${ar.x-br.x}px,${ar.y-br.y}px)`;
    }""")
    assert any('text overlap' in f for f in render_guard.check(page,require_mascot=False))
