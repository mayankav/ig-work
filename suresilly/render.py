"""Draw a post: cream paper, a warm serif, one highlighted phrase, a small donkey."""
from __future__ import annotations

import html
import random
import re
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from . import ASSETS
from .mascot import path as pose_path

SIZE = (1080, 1350)
FONTS = ASSETS / "fonts"
HANDLE = "@suresilly"

CSS = """
@font-face { font-family: 'Fraunces'; src: url('%(fraunces)s') format('truetype'); font-weight: 100 900; }
@font-face { font-family: 'Inter'; src: url('%(inter)s') format('truetype'); font-weight: 100 900; }
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 1080px; height: 1350px; overflow: hidden; }
body { position: relative; background: #f4ecde url('%(paper)s') no-repeat; color: #2e2822;
       font-family: 'Fraunces', serif; -webkit-font-smoothing: antialiased; }
.vignette { position: absolute; inset: 0;
            background: radial-gradient(ellipse at 50%% 38%%, rgba(255,255,255,.28) 0%%, rgba(255,255,255,0) 55%%, rgba(96,64,30,.14) 100%%); }
.box { position: absolute; left: 118px; right: 118px; top: 150px; bottom: 480px; display: flex; align-items: center; }
.box p { font-size: 64px; line-height: 1.34; font-weight: 420; letter-spacing: -0.004em;
         font-variation-settings: 'SOFT' 100, 'WONK' 0, 'opsz' 60; hyphens: none; }
.cover .box p { font-size: 90px; line-height: 1.14; font-weight: 560; letter-spacing: -0.012em;
                font-variation-settings: 'SOFT' 100, 'WONK' 1, 'opsz' 120; }
.single .box p { font-size: 76px; line-height: 1.24; font-weight: 470; }
.mark { background: linear-gradient(transparent 58%%, rgba(255, 206, 84, .78) 58%%, rgba(255, 206, 84, .78) 90%%, transparent 90%%);
        -webkit-box-decoration-break: clone; box-decoration-break: clone; padding: 0 .06em; }
.donkey { position: absolute; right: 124px; bottom: 104px; height: 340px; }
.sign { position: absolute; left: 120px; bottom: 116px; font-family: 'Inter', sans-serif; font-size: 25px;
        font-weight: 500; letter-spacing: .09em; color: rgba(46, 40, 34, .5); }
.count { position: absolute; left: 120px; top: 96px; font-family: 'Inter', sans-serif; font-size: 23px;
         font-weight: 500; letter-spacing: .12em; color: rgba(46, 40, 34, .35); }
"""

FIT = """
async () => {
  await document.fonts.ready;
  const faces = [...document.fonts];
  if (faces.length !== 2 || !faces.every(face => face.status === "loaded")) return "fonts";
  const box = document.querySelector('.box'), p = box.querySelector('p');
  let size = parseFloat(getComputedStyle(p).fontSize);
  while ((p.scrollHeight > box.clientHeight || p.scrollWidth > box.clientWidth) && size > 36) {
    size -= 2; p.style.fontSize = size + 'px';
  }
  return p.scrollHeight > box.clientHeight ? "overflow" : "ok";
}
"""


class RenderError(RuntimeError):
    pass


def smart_quotes(text: str) -> str:
    text = re.sub(r"(\w)'(\w)", "\\1\u2019\\2", text)
    text = re.sub(r"(^|[\s(\[\u2014-])'", "\\1\u2018", text).replace("'", "\u2019")
    return re.sub(r'(^|[\s(\[\u2014-])"', "\\1\u201c", text).replace('"', "\u201d")


def markup(text: str) -> str:
    safe = html.escape(smart_quotes(" ".join(text.split())), quote=False)
    return re.sub(r"\[\[(.+?)\]\]", r'<span class="mark">\1</span>', safe)


def paper(target: Path) -> Path:
    """A fixed sheet of warm paper: fine grain plus faint fibres. Same every time."""
    rng = random.Random(1350)
    width, height = SIZE
    grain = Image.frombytes("L", SIZE, rng.randbytes(width * height)).filter(ImageFilter.GaussianBlur(0.8))
    cloud = (Image.frombytes("L", (18, 22), rng.randbytes(18 * 22))
             .resize(SIZE, Image.BICUBIC).filter(ImageFilter.GaussianBlur(60)))
    mixed = ImageChops.add(grain, cloud, scale=2.0)
    # Shadows lean warm: blue darkens most, red least, so the paper never goes grey.
    channels = [mixed.point(lambda v, k=k: max(0, min(255, int(250 + (v - 128) * k)))) for k in (0.16, 0.2, 0.27)]
    cream = Image.new("RGB", SIZE, (247, 240, 227))
    ImageChops.multiply(cream, Image.merge("RGB", channels)).save(target)
    return target


def page(text: str, pose: str, kind: str, count: str, assets: dict) -> str:
    css = CSS % assets
    counter = f'<div class="count">{count}</div>' if count else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>"
            f"<body class='{kind}'><div class='vignette'></div>{counter}"
            f"<div class='box'><p>{markup(text)}</p></div>"
            f"<img class='donkey' src='{pose_path(pose).as_uri()}'>"
            f"<div class='sign'>{HANDLE}</div></body></html>")


def render(post: dict, out_dir: Path) -> list[Path]:
    """Render every slide of `post` (slides need text, mood, pose) to out_dir/NN.jpg."""
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    slides = post["slides"]
    total = len(slides)
    written = []
    with tempfile.TemporaryDirectory(prefix="suresilly-") as scratch:
        scratch = Path(scratch)
        assets = {"fraunces": (FONTS / "Fraunces-Variable.ttf").as_uri(),
                  "inter": (FONTS / "Inter-Variable.ttf").as_uri(),
                  "paper": paper(scratch / "paper.png").as_uri()}
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                view = browser.new_page(viewport={"width": SIZE[0], "height": SIZE[1]}, device_scale_factor=1)
                for number, slide in enumerate(slides, 1):
                    kind = "single" if total == 1 else ("cover" if number == 1 else "inner")
                    count = f"{number} / {total}" if total > 1 and number > 1 else ""
                    source = scratch / f"{number:02d}.html"
                    source.write_text(page(slide["text"], slide["pose"], kind, count, assets), encoding="utf-8")
                    view.goto(source.as_uri(), wait_until="load")
                    status = view.evaluate(FIT)
                    if status == "fonts":
                        raise RenderError("A font did not load, so the slide would render in a fallback face.")
                    if status == "overflow":
                        raise RenderError(f"Slide {number} has too much text to fit.")
                    target = out_dir / f"{number:02d}.jpg"
                    view.screenshot(path=str(target), type="jpeg", quality=92,
                                    clip={"x": 0, "y": 0, "width": SIZE[0], "height": SIZE[1]})
                    written.append(target)
            finally:
                browser.close()
    return written


def contact_sheet(slides: list[Path], target: Path) -> Path:
    """All slides on one image, three to a row, for the record and the preview."""
    columns = 1 if len(slides) == 1 else 3
    thumb = (SIZE[0] // 3, SIZE[1] // 3) if columns == 3 else (SIZE[0] // 2, SIZE[1] // 2)
    rows = -(-len(slides) // columns)
    gap = 16
    sheet = Image.new("RGB", (columns * thumb[0] + (columns + 1) * gap, rows * thumb[1] + (rows + 1) * gap), (231, 222, 206))
    for index, path in enumerate(slides):
        with Image.open(path) as image:
            tile = image.convert("RGB").resize(thumb, Image.LANCZOS)
        row, column = divmod(index, columns)
        sheet.paste(tile, (gap + column * (thumb[0] + gap), gap + row * (thumb[1] + gap)))
    sheet.save(target, optimize=True)
    return target
