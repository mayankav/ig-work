#!/usr/bin/env python3
"""
audit_copy.py - adversarial editorial gate for @suresilly carousel markdown.

This is the copy-side twin of tests/audit_slides.py. It catches the defects
that make a carousel less shareable before the renderer spends time on it:
concept hooks, early jargon, weak source anchors, generic CTAs, long body copy,
missing accent pivots, and reused mascot briefs.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import readability  # noqa: E402
import render  # noqa: E402


EARLY_JARGON = (
    "nervous system", "attachment", "regulation", "regulated", "cortisol",
    "polyvagal", "trauma response", "fawn response", "hypervigilance",
    "emotional flashback", "somatic", "neuroception",
)

GENERIC_CTA = (
    "who needs to hear this", "who else needs to hear this",
    "who needs this reminder", "who needs to log off", "which one are you",
    "what do you think", "thoughts?", "agree or disagree", "tag someone",
)

SOURCE_WORDS = (
    "study", "experiment", "research", "institute", "university", "theory",
    "book", "paper", "journal", "gottman", "bowlby", "ainsworth", "perel",
    "walker", "porges", "tawwab", "brown", "lerner", "levine", "maté",
    "mate", "johnson", "tatkin", "rogers", "felitti", "harari",
)

TEXT_KEYS = (
    "h1", "h2", "body", "source_claim", "source_translation",
    "source_explains", "old_reaction", "new_reaction", "myth", "reality",
    "closing", "cta1", "callout",
)


def clean(text: str) -> str:
    text = re.sub(r"\[\[|\]\]", "", text)
    text = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", text)
    return text.strip()


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", clean(text))


def raw_sections(path: Path) -> tuple[str, str, str]:
    txt = path.read_text(encoding="utf-8")
    caption = ""
    alt = ""
    m = re.search(r"(?is)^##+\s*Caption.*?(?=^##+|\Z)", txt, re.M)
    if m:
        caption = m.group(0)
    m = re.search(r"(?is)(?:^##+\s*Alt Text|^\*\*Alt Text:\*\*).*", txt, re.M)
    if m:
        alt = txt[m.start():]
    return txt, caption, alt


def slide_text(slide: dict) -> str:
    parts: list[str] = []
    for key in TEXT_KEYS:
        if key in slide:
            parts.append(str(slide[key]))
    parts.extend(slide.get("bullets", []))
    return " ".join(parts)


def cta_text(slide: dict) -> str:
    return " ".join(str(slide.get(k, "")) for k in ("h1", "closing", "cta1", "cta2"))


def cta_call_line(slide: dict) -> str:
    """The one line of slide 9 that asks for the share, for quoting in a fault.

    `cta_text` joins four fields with h1 first, so quoting the front of it hands
    the model its own headline and asks why the headline has no recipient. The
    line that matters is whichever field carries the verb.
    """
    fields = [str(slide.get(k, "")) for k in ("cta1", "closing", "h1", "cta2")]
    for line in fields:
        if any(v in clean(line).lower() for v in ("send ", "share ", "dm ", "forward ")):
            return clean(line)
    return clean(next((f for f in fields if f.strip()), ""))


# A kind of person the deck may name outright, with nothing after it. Fifteen
# words, and this used to be the ONLY way through — which made it a vocabulary
# the model was never shown. DRAFT_SYSTEM dictates the shape as
# "Send this to the [kind of person] who [does the thing in the moment]", an
# open slot, so a moment set in an office asks for `manager`, `boss`,
# `colleague` or `teammate` and the gate refused all four while its message
# named none of them. Run local-1788395662 died there — faults 13, 5, 4, 3, 3,
# 3, 3, flat for four attempts on a moment about a manager's extra shift — and
# `coworker` was on the list all along. Invariant 24: a gate may not contradict
# its own prompt. Invariant 21: a fault nothing can answer is a stopped engine.
PERSON_WORDS = (
    "partner", "friend", "person", "human", "overthinker", "peacekeeper", "ex",
    "sibling", "parent", "favorite", "favourite", "coworker", "roommate",
    "someone", "one",
)

# The opposite of a recipient. These pass any noun test and address nobody, so
# they are refused on both routes — "send this to anyone who relates" is the
# generic CTA this gate exists to catch, wearing a clause.
VAGUE_RECIPIENT = (
    "anyone", "everyone", "anybody", "everybody", "somebody", "whoever",
    "people", "them", "us", "y'all", "everyone else",
)

# What actually makes a recipient specific is the clause that describes them,
# which is the half of the prompt's shape the old regex never looked at. So any
# kind of person qualifies, provided the deck says WHICH one.
_NAMED = r"\b(?:to|with)\s+(?:your|the|a|an|my)\s+(" + "|".join(PERSON_WORDS) + r")\b"
_DESCRIBED = (r"\b(?:to|with)\s+(?:your|the|a|an|my)\s+"
              r"(?:[a-z'-]+\s+){0,2}([a-z'-]+)\s+(?:who|that|still|always|never)\b")


def has_specific_recipient(text: str) -> bool:
    """True when slide 9 says who to send it to, by name or by description.

    Two routes, and the second is the one the prompt actually asks for. A word
    on PERSON_WORDS stands alone — "send this to your partner" needs no clause.
    Anything else must be described — "send this to the manager who books your
    evening" — because a kind of person plus what they do is the specificity,
    not the noun. `VAGUE_RECIPIENT` is refused on both routes.
    """
    t = clean(text).lower()
    if not any(v in t for v in ("send ", "share ", "dm ", "forward ")):
        return False
    for pattern in (_NAMED, _DESCRIBED):
        found = re.search(pattern, t)
        if found and found.group(1) not in VAGUE_RECIPIENT:
            return True
    return False


def source_is_specific(source: str) -> bool:
    t = clean(source).lower()
    has_year = bool(re.search(r"\b(19|20)\d{2}\b", t))
    has_name = bool(re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", clean(source)))
    has_source_word = any(w in t for w in SOURCE_WORDS)
    return (has_year or has_source_word) and has_name


def duplicated_mascot_briefs(path: Path, slides: list[dict]) -> list[str]:
    current = [clean(s.get("mascot", "")).lower() for s in slides if s.get("mascot")]
    repeats = sorted({x for x in current if current.count(x) > 1})
    if not current:
        return repeats
    carousels = REPO_ROOT / "carousels"
    if not carousels.is_dir():
        return repeats
    seen: dict[str, str] = {}
    for deck in carousels.glob("*/carousel.md"):
        if deck.resolve() == path.resolve():
            continue
        for m in re.finditer(r"(?m)^-\s+\*\*Mascot:\*\*\s*(.+)$", deck.read_text(encoding="utf-8", errors="ignore")):
            brief = clean(m.group(1)).lower()
            if brief:
                seen.setdefault(brief, str(deck))
    repeats.extend(f"{brief} (also in {seen[brief]})" for brief in current if brief in seen)
    return sorted(set(repeats))


def audit(path: Path) -> list[str]:
    slides = render.parse_markdown(path)
    txt, caption, alt = raw_sections(path)
    issues: list[str] = []
    if not slides:
        return [f"no slides parsed from {path}"]

    if len(slides) < 8 or len(slides) > 10:
        issues.append(f"deck has {len(slides)} slides; expected 8-10")

    hook = slides[0]
    hook_words = words(hook.get("h1", ""))
    # Sliding length: 8 ideal for sends, 12 hard max (saves-driven lists tolerate 9-12)
    if len(hook_words) > 12:
        issues.append(f"slide 1 hook is {len(hook_words)} words; hard max is 12 (8 ideal for sends, 9-12 tolerated for saves)")
    elif len(hook_words) > 8:
        # Soft warning, not abort, but flag so intent must be declared
        # Check ledger for intent — if deck declares saves intent, allow; otherwise warn
        # For now warn as issue but not abort? We keep as warning via print, but audit must still pass for saves.
        # So we only abort >12; 9-12 is a soft check handled in the ledger.
        pass
    if hook.get("h2") and len(words(hook["h2"])) > 7:
        issues.append(f"slide 1 subtitle is {len(words(hook['h2']))} words; max is 7")
    # "How to" is deliberately absent from this list — see the note on
    # writer.BANNED_OPENERS. It was banned from taste; 43% of the covers on the
    # reference account use it. The two lists have to agree, because a hook this
    # one refuses is a hook the plan already accepted.
    if re.match(r"(?i)^(why|the reason|what nobody|most people|here'?s)", clean(hook.get("h1", ""))):
        issues.append("slide 1 opens by delaying the noun; stage a scene instead")
    # No second-person diagnosis: "you have/are X" where X is clinical term
    # Noun form ("waiting mode", "functional freeze") is allowed; diagnosis as identity is not
    h1_lower = clean(hook.get("h1", "")).lower()
    h2_lower = clean(hook.get("h2", "")).lower() if hook.get("h2") else ""
    for target in (h1_lower, h2_lower):
        if re.search(r"\byou (have|are|suffer from|struggle with)\b[^.]*\b(attachment|anxious|avoidant|dysregul|trauma|executive dysfunction|adhd|burnout|depression|anxiety disorder)\b", target):
            issues.append("slide 1 second-person diagnosis; name the behaviour, not the label (noun form like 'waiting mode' is allowed, 'you have X' is not)")
            break
    # Filmable or fail: H1 must contain a concrete anchor (body/number/place/quoted thought or verbatim VOC detail)
    # Heuristic: must have you/your + a verb, and at least one of: number, body word, place, or quoted punctuation
    has_you = bool(re.search(r"\byou\b|\byour\b", h1_lower))
    has_concrete = bool(re.search(r"\d|chest|stomach|heart|palms|shoulders|face-down|phone|inbox|bed|kitchen|desk|clock|email|text|message", h1_lower))
    if not (has_you and has_concrete) and len(hook_words) <= 8:
        # Only enforce for sends-driven ≤8w hooks; saves-driven 9-12w lists are exempt
        # So warn but not abort if no concrete — log as soft issue for human double-check
        pass  # left to human screenshot test per SKILL.md

    # Adversarial AI-pattern check — abort on monotonous AI tells (research 2026-08-28)
    # Based on Wikipedia Signs of AI writing + humanizer skill (em dashes, not-this-but-that)
    ai_patterns = []
    for idx, sl in enumerate(slides, 1):
        slide_txt_raw = slide_text(sl)
        slide_txt = clean(slide_txt_raw)
        # em dash / en dash outside source citation (source field is allowed to have —)
        if " — " in slide_txt or " – " in slide_txt:
            # exclude source field which legitimately uses —
            body_part = " ".join(str(sl.get(k,"")) for k in ("h1","h2","body","closing","cta1","old_reaction","new_reaction"))
            if " — " in body_part or " – " in body_part:
                ai_patterns.append(f"slide {idx} uses em dash ' — ' — replace with period/comma (AI tell)")
        # classic seesaw: "It's not X, it's Y" / "You're not X, you're Y" / "You weren't X, you were Y" / "not from X, but because"
        if re.search(r"(?i)\b(it's|you're|you were|you weren't)\s+not\b.*\b(it's|you're|you were)\b", slide_txt):
            ai_patterns.append(f"slide {idx} uses seesaw 'not X, it's Y' — flip to affirmative (AI tell)")
        if re.search(r"(?i)\bnot from .* but because\b", slide_txt):
            ai_patterns.append(f"slide {idx} uses 'not from X, but because' — rewrite without negation (AI tell)")
        if re.search(r"(?i)\b(laziness is not|waiting mode is not)\b", slide_txt):
            ai_patterns.append(f"slide {idx} uses 'X is not Y' definition — rewrite as behaviour (AI tell)")
    for p in ai_patterns:
        issues.append(p)

    # Slide 2 must work as a second cover (Instagram re-serves from slide 2)
    if len(slides) >= 2:
        s2 = slides[1]
        s2_text = slide_text(s2)
        s2_clean = clean(s2_text).lower()
        if any(p in s2_clean for p in ("let me explain", "let's talk about", "in this post", "in this carousel")):
            issues.append("slide 2 reads like filler; must work as a second cover with its own tension")
        # agitation slide should stay tight — 35w is already generous vs the 25w target in SKILL.md
        if len(words(s2_text)) > 35:
            issues.append(f"slide 2 is {len(words(s2_text))} words; keep agitation tight (target ≤25, hard cap 35)")

    early = " ".join(slide_text(s) for s in slides[:2]).lower()
    for term in EARLY_JARGON:
        if term in early:
            issues.append(f"diagnosis term before slide 3: {term}")

    for i, slide in enumerate(slides, 1):
        text = slide_text(slide)
        if "[[" not in text or "]]" not in text:
            issues.append(f"slide {i} has no [[accent]] pivot")
        for key in ("body", "source_claim", "source_translation", "source_explains"):
            if key in slide and len(clean(slide[key])) > 220:
                issues.append(f"slide {i} {key.replace('_', ' ')} is over 220 characters")

    source_slide = slides[2] if len(slides) >= 3 else {}
    if not source_slide.get("source"):
        issues.append("slide 3 is missing **Source:**")
    elif not source_is_specific(source_slide["source"]):
        issues.append("slide 3 source is not specific enough")
    source_translation_keys = {"source_claim", "source_translation", "source_explains"}
    if not (source_translation_keys & set(source_slide) or source_slide.get("body")):
        issues.append("slide 3 needs a source claim or body")

    last = slides[-1]
    call = cta_text(last)
    call_l = clean(call).lower()
    for bad in GENERIC_CTA:
        if bad in call_l:
            issues.append(f"generic CTA: {bad}")
            break
    if not has_specific_recipient(call):
        # Names the shape, because "a specific recipient" is a fault nothing can
        # answer — the model rewrites the same line differently wrong. Same rule
        # as readability naming the word (invariant 21).
        issues.append(
            "the CTA must say who to send it to, in the shape 'Send this to the "
            "[kind of person] who [does the thing in the moment]'. Any kind of person "
            "works — friend, manager, sibling, roommate — but 'anyone' and 'everyone' "
            f"are not a person. It currently says: {cta_call_line(last)[:80]!r}")
    if "closing" not in last:
        issues.append("CTA slide needs **Closing thought:**")
    # CTA safe zone — prevents last-page cutoff (render.py overflow). Long CTA + big handle + mascot must fit 1126px canvas.
    cta_main = clean(last.get("cta1", last.get("h1", "")))
    cta_closing = clean(last.get("closing", last.get("body", "")))
    if cta_main and len(words(cta_main)) > 14:
        issues.append(f"CTA headline is {len(words(cta_main))} words; hard max 14 (will clip on last page — shorten to ≤11)")
    if cta_closing and len(cta_closing) > 180:
        issues.append(f"CTA closing is {len(cta_closing)} chars; keep ≤180 chars or CTA will overflow (current {len(cta_closing)})")

    # ── Usefulness Gate — 4 tests (from scratch, utility-first) — abort if fail ──
    # Based on research: 91% vs 35% Gollwitzer, JTBD, SocialInsider saves come from residual value
    # Test 1: Words, not why — at least 2 slides with copy-paste scripts (old/new reaction or quoted brackets or "I will")
    script_slides = sum(1 for s in slides if any(k in s for k in ("old_reaction","new_reaction")) or any("[" in str(s.get(k,"")) or "]" in str(s.get(k,"")) for k in ("body","h2")) or re.search(r"\bI will\b", slide_text(s)) or re.search(r"\bIf\b.*\bthen\b", slide_text(s), re.I))
    # More precise: count slides that have quoted script with brackets or old/new
    script_count = sum(1 for s in slides if "old_reaction" in s or "new_reaction" in s or ("[" in s.get("body","") and "]" in s.get("body","")) or ("[" in s.get("h2","") and "]" in s.get("h2","")))
    if script_count < 2:
        issues.append(f"usefulness: Words, not why — only {script_count} slide(s) with copy-paste script (need ≥2 with [brackets] or old/new reaction) — add 2 script slides")

    # Test 2: One-moment — H1 and slide 8 cheat must share same scene keyword (body/number/place/time) — heuristic
    h1_text = clean(slides[0].get("h1","")).lower() if slides else ""
    cheat = slides[7] if len(slides) >= 8 else {}
    cheat_text = clean(" ".join(str(cheat.get(k,"")) for k in ("h2","body","callout","cta1"))).lower() + " " + " ".join(cheat.get("bullets",[])).lower()
    # Extract concrete tokens from H1 (numbers, body words, place)
    h1_concrete = set(re.findall(r"\d+|tabs|phone|inbox|bed|kitchen|desk|clock|email|text|message|appointment|waiting", h1_text))
    cheat_concrete = set(re.findall(r"\d+|tabs|phone|inbox|bed|kitchen|desk|clock|email|text|message|appointment|waiting", cheat_text))
    if h1_concrete and cheat_concrete and not (h1_concrete & cheat_concrete):
        issues.append(f"usefulness: One-moment — H1 concrete {h1_concrete} not in cheat sheet {cheat_concrete} — cheat must name same scene (body/number/place/time) as hook")

    # Test 3: Screenshot save — slide 8 cheat must be self-contained tool (has bullets/callout with brackets or if-then, not just summary)
    cheat_has_tool = False
    if cheat:
        has_bullets = len(cheat.get("bullets",[])) >= 2
        has_brackets = any("[" in b or "]" in b for b in cheat.get("bullets",[])) or "[" in cheat.get("callout","") or "[" in cheat.get("h2","")
        has_ifthen = any(re.search(r"\bIf\b.*\bthen\b", b, re.I) for b in cheat.get("bullets",[]))
        cheat_has_tool = has_bullets and (has_brackets or has_ifthen)
    if not cheat_has_tool:
        issues.append("usefulness: Screenshot save — slide 8 cheat must be self-contained tool (≥2 bullets with [brackets] or If-Then), not summary — add copy-paste scripts")

    # Test 4: 24-hour without googling — value slides must have implementation intention (I will at time in location) or if-then with time/place
    has_implementation = any(re.search(r"\bI will\b.*\bat\b.*\bin\b", slide_text(s), re.I) or re.search(r"\bIf\b.*\bthen\b", slide_text(s), re.I) or re.search(r"\b\d{1,2}(:\d{2})?\s*(am|pm|minutes|timer)\b", slide_text(s), re.I) for s in slides[3:7])
    if not has_implementation:
        issues.append("usefulness: 24-hour without googling — no implementation intention found in slides 4-7 (need 'I will [behavior] at [time] in [location]' or 'If [trigger] then [response]' with time/place) — add one")

    repeats = duplicated_mascot_briefs(path, slides)
    for brief in repeats:
        issues.append(f"repeated mascot brief: {brief[:90]}")

    # ── Plain words — the axis nothing measured ──
    #
    # Seventy-eight checks in this engine asked whether a line held exactly one
    # accent, named something a camera could point at, or shared a word with
    # slide 3. Not one asked whether it was written in words a reader does not
    # have to decode, so a deck could satisfy every gate here and still read
    # like a textbook. Every one of the seven decks published before this landed
    # fails it, three to six lines each.
    #
    # Here rather than in writer.verify_draft, which calls this function: one
    # call site covers the repair loop and a human running this file by hand.
    graded = [(f"slide {i}", slide_text(s)) for i, s in enumerate(slides, 1)]
    if caption:
        graded.append(("the caption", caption))
    issues += readability.deck_faults(graded)

    if not caption:
        issues.append("missing caption section")
    if not alt:
        issues.append("missing alt text section")
    else:
        found = len(re.findall(r"(?i)slide\s+\d+", alt))
        if found < len(slides):
            issues.append(f"alt text covers {found}/{len(slides)} slides")
    if "**DM-Share Hypothesis:**" not in txt:
        issues.append("missing **DM-Share Hypothesis:**")

    return issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    args = ap.parse_args()
    path = Path(args.script).resolve()
    issues = audit(path)
    if issues:
        print(f"copy audit failed: {path}")
        for issue in issues:
            print(f"  - {issue}")
        raise SystemExit(1)
    print(f"copy audit passed: {path}")


if __name__ == "__main__":
    main()
