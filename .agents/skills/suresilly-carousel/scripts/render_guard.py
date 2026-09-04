"""Check the settled browser surface, not a second copy of layout arithmetic."""
from __future__ import annotations
import io
import hashlib
import json
from importlib import metadata
from pathlib import Path
from PIL import Image

VERSION = "surface-2"


def runtime() -> dict:
    """Record installed render dependencies and the bundled browser identity."""
    import playwright
    manifest = Path(playwright.__file__).parent / "driver/package/browsers.json"
    browsers = json.loads(manifest.read_text())["browsers"]
    chromium = next(item for item in browsers if item["name"] == "chromium-headless-shell")
    return {"packages": {name: metadata.version(name) for name in
                         ("playwright", "pillow", "numpy", "opencv-python-headless")},
            "chromium": {key: chromium[key] for key in ("revision", "browserVersion")}}


def check_browser(version: str) -> None:
    expected = runtime()["chromium"]["browserVersion"]
    if version != expected:
        raise ValueError(f"Wrong render browser: {version}; expected {expected}. Reinstall bundled Chromium.")


def contract() -> str:
    """A render check cannot survive changed checks, templates or font bytes."""
    root = Path(__file__).resolve().parents[1]
    files = [root / "scripts/render.py", Path(__file__),
             root / "assets/fonts/ArchivoBlack.ttf",
             root / "assets/fonts/FamiljenGrotesk-Variable.ttf"]
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    return hashlib.sha256(json.dumps([VERSION, hashes, runtime()], sort_keys=True).encode()).hexdigest()

MEASURE = r"""() => {
  const faults = [], runs = [];
  const ink = document.createElement("canvas").getContext("2d");
  for (const img of document.images) {
    if (!img.complete || !img.naturalWidth || !img.naturalHeight)
      faults.push('an image did not load');
  }
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode, el = node.parentElement;
    if (!node.textContent.trim() || !el.closest('.canvas,.footer,.swipe')) continue;
    const style = getComputedStyle(el);
    // DOM text rectangles include the font's empty ascent/descent space.
    // Tight, readable heading lines overlap those boxes without touching ink.
    // Measure each visible word using the loaded font's actual glyph bounds.
    ink.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    ink.letterSpacing = style.letterSpacing === "normal" ? "0px" : style.letterSpacing;
    for (const match of node.textContent.matchAll(/\S+/g)) {
      const range = document.createRange();
      range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length);
      const rects = [...range.getClientRects()];
      if (!rects.length || style.visibility !== 'visible' || Number(style.opacity) === 0)
        faults.push('hidden text: ' + match[0]);
      const metrics = ink.measureText(match[0]);
      for (const box of rects) {
        if (box.width < 1 || box.height < 1) continue;
        const baseline = box.y + metrics.fontBoundingBoxAscent;
        const r = {x:box.x-metrics.actualBoundingBoxLeft,
                   y:baseline-metrics.actualBoundingBoxAscent,
                   width:metrics.actualBoundingBoxLeft+metrics.actualBoundingBoxRight,
                   height:metrics.actualBoundingBoxAscent+metrics.actualBoundingBoxDescent};
        if (r.x < 40 || r.x+r.width > 1040 || r.y < 40 || r.y+r.height > 1310)
          faults.push('text outside safe bounds: ' + match[0]);
        runs.push({x:r.x,y:r.y,w:r.width,h:r.height,layoutX:box.x,layoutW:box.width,color:style.color,
                   size:parseFloat(style.fontSize),weight:parseFloat(style.fontWeight),text:match[0]});
      }
    }
  }
  for (let i=0; i<runs.length; i++) for(let j=i+1;j<runs.length;j++) {
    const a=runs[i],b=runs[j];
    if(Math.min(a.layoutX+a.layoutW,b.layoutX+b.layoutW)-Math.max(a.layoutX,b.layoutX)>2 &&
       Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)>2 &&
       Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y)>2)
      faults.push('text overlap: ' + a.text.slice(0,25) + ' / ' + b.text.slice(0,25));
  }
  const fig=document.querySelector('#fig img');
  let figure=null;
  if(fig) {
    const r=fig.getBoundingClientRect(), s=getComputedStyle(fig);
    figure={x:r.x,y:r.y,w:r.width,h:r.height};
    if(r.width<80 || r.height<160 || r.left<40 || r.right>1040 || r.top<40 || r.bottom>1218 || s.visibility!=='visible')
      faults.push('mascot is too small, hidden or outside its bounds');
    for(const a of runs) {
      if(Math.min(a.x+a.w,r.right)-Math.max(a.x,r.left)>2 &&
         Math.min(a.y+a.h,r.bottom)-Math.max(a.y,r.top)>2)
        faults.push('mascot overlaps text: '+a.text.slice(0,30));
    }
  }
  if(!runs.length) faults.push('no visible slide text');
  return {faults,runs,figure};
}"""


def contrast(a, b):
    def lum(rgb):
        v = [c / 255 for c in rgb[:3]]
        v = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in v]
        return sum(x * y for x, y in zip(v, (.2126, .7152, .0722)))
    lo, hi = sorted((lum(a), lum(b)))
    return (hi + .05) / (lo + .05)


def check(page, *, require_mascot=True, expected=None):
    import re
    data = page.evaluate(MEASURE)
    faults = list(data["faults"])
    if expected:
        import html
        def words(text):
            text = html.unescape(str(text)).replace("[[", "").replace("]]", "")
            return " ".join(re.findall(r"\w+", text.casefold()))
        visible = words(" ".join(r["text"] for r in data["runs"]))
        for key in ("h1", "h2", "body", "old_reaction", "new_reaction", "source",
                    "source_claim", "source_translation", "source_explains", "myth",
                    "reality", "closing", "cta1", "cta2", "callout", "bullets"):
            value = expected.get(key)
            if not value:
                continue
            for text in value if isinstance(value, list) else [value]:
                if words(text) and words(text) not in visible:
                    faults.append(f"content not rendered: {key}")
    if require_mascot and data["figure"] is None:
        faults.append("the mascot is missing")
    # Remove only glyph paint, leaving card fills, grids and layout unchanged.
    # This image is the actual background beneath every measured text run.
    style = page.add_style_tag(content="* {color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important}")
    try:
        surface = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    finally:
        style.evaluate("el => el.remove()")
    for run in data["runs"]:
        values = [float(v) for v in re.findall(r"[\d.]+", run["color"])]
        if len(values) < 3:
            faults.append("unreadable text color")
            continue
        alpha = values[3] if len(values) > 3 else 1
        large = run["size"] >= 24 or (run["size"] >= 19 and run["weight"] >= 700)
        minimum = 3.0 if large else 4.5
        ratios = []
        for dx in (.2, .5, .8):
            for dy in (.2, .5, .8):
                x, y = int(run["x"] + run["w"] * dx), int(run["y"] + run["h"] * dy)
                if 0 <= x < surface.width and 0 <= y < surface.height:
                    bg = surface.getpixel((x, y))
                    fg = [values[i] * alpha + bg[i] * (1-alpha) for i in range(3)]
                    ratios.append(contrast(fg, bg))
        if ratios and min(ratios) < minimum:
            faults.append(f"text contrast {min(ratios):.2f} below {minimum}: {run['text'][:40]}")
    return list(dict.fromkeys(faults))
