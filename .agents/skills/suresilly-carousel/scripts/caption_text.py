"""One caption formatter, frozen before owner review."""
import re
from pathlib import Path

def strip_markup(text: str) -> str:
    """carousel.md is a source file. Instagram is a text box.

    The deck's markup means something to the renderer — [[accent]] is the word
    the slide colours, **bold** and *italic* are type. Instagram renders none of
    it and prints the characters, so on 2026-09-01 a post went out reading
    "the [[cost]] of carrying the [[street]] across the [[threshold]]".

    Stripped HERE and not only at the writer, because this is where the caption
    stops being ours. A held deck is posted days later by release.py from a
    fresh checkout of a file written by an older engine, carousel.md is
    hand-editable and gets hand-edited, and neither of those paths goes back
    through the writer. The last thing that touches the text before Instagram
    does is the right place to guarantee what Instagram gets.

    Deliberately its own regex rather than an import of render.plain(): the
    engine does not import this file and this file does not import the engine.
    """
    text = re.sub(r"\[\[|\]\]", "", text)
    return re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)


def parse_caption(md_path: Path) -> str:
    txt = md_path.read_text(encoding="utf-8")
    m = re.search(r"(?is)^##+\s*Caption\s*(.*?)(?=^##+|\Z)", txt, re.M)
    caption = m.group(1).strip() if m else ""
    # Strip markdown headers, keep plain text + hashtags
    # Also append hashtags section if present
    h = re.search(r"(?is)^##+\s*Hashtags\s*(.*?)(?=^##+|\Z)", txt, re.M)
    if h:
        caption = caption.rstrip() + "\n\n" + h.group(1).strip()
    # Fallback: if no Caption block, use first paragraph
    if not caption:
        caption = txt[:500]
    # One strip, on the way out, so no branch above can skip it — the fallback
    # takes raw markdown off the top of the file and is the likeliest of all of
    # them to carry markup.
    return strip_markup(caption.strip())[:2200]  # IG limit

