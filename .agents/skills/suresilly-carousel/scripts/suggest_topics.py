#!/usr/bin/env python3
"""
suggest_topics.py — Layer 1 + 2 for "I'm feeling lucky"

Mines the topic bank, filters recent, scores on 5 dims (Scene, Self-blame, Stealable, Freshness, Intent fit).
No LLM magic — deterministic so the same bank always suggests the same order unless you add VOC.

Usage:
  .venv/bin/python scripts/suggest_topics.py --suggest 5
  .venv/bin/python scripts/suggest_topics.py --pick --intent sends
"""

from __future__ import annotations
import argparse, re
from pathlib import Path

BANK = Path(__file__).resolve().parent.parent / "references" / "topic-bank.md"
CAROUSELS = Path(__file__).resolve().parent.parent.parent.parent.parent / "carousels"

def parse_bank():
    txt = BANK.read_text(encoding="utf-8")
    rows = []
    for line in txt.splitlines():
        if line.startswith("|") and not line.startswith("| #") and not line.startswith("|---"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 9 or not parts[1].isdigit():
                continue
            # New bank has 9 columns: #, slug, scene, blame, stealable, pillar, pattern, intent, last used
            # Old bank had 8 columns (no pattern) — handle both
            if len(parts) >= 10 and parts[7].lower() in ("hidden mechanism","script / template","visual comparison","identity mirror","uncomfortable truth","contrarian reversal","the diagnosis","relationship archetype"):
                # New format
                rows.append({
                    "id": int(parts[1]),
                    "slug": parts[2],
                    "scene": parts[3],
                    "blame": parts[4],
                    "stealable": parts[5],
                    "pillar": parts[6],
                    "pattern": parts[7],
                    "intent": parts[8].lower(),
                    "last_used": parts[9] if len(parts) > 9 else "-",
                })
            else:
                # Old format fallback
                rows.append({
                    "id": int(parts[1]),
                    "slug": parts[2],
                    "scene": parts[3],
                    "blame": parts[4],
                    "stealable": parts[5],
                    "pillar": parts[6],
                    "pattern": "Hidden Mechanism",
                    "intent": parts[7].lower() if len(parts) > 7 else "sends",
                    "last_used": parts[8] if len(parts) > 8 else "-",
                })
    return rows

def recent_slugs(n=10):
    if not CAROUSELS.is_dir():
        return set()
    slugs = []
    for p in sorted(CAROUSELS.glob("*/carousel.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        slugs.append(p.parent.name)
        if len(slugs) >= n:
            break
    # also check generation folders
    for gen in (CAROUSELS / "_generations").glob("*/*") if (CAROUSELS / "_generations").is_dir() else []:
        slugs.append(gen.name)
    return set(slugs)

def recent_pillars(n=2):
    if not CAROUSELS.is_dir():
        return set()
    pillars = []
    for p in sorted(CAROUSELS.glob("*/carousel.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        # Handle both single-line "**Pattern:** X · **Content Pillar:** Y" and separate lines
        m = re.search(r"Content Pillar:\s*\*?\*?\s*([^\n]+)", txt)
        if m:
            raw = m.group(1).strip()
            # Split on · or | and take first segment, lower and strip markdown
            pil = re.split(r"[·|]", raw)[0].strip().lower()
            pil = re.sub(r"[\*\_]", "", pil).strip()
            pillars.append(pil)
            if len(pillars) >= n:
                break
    return set(pillars)

def recent_patterns(n=2):
    if not CAROUSELS.is_dir():
        return set()
    patterns = []
    for p in sorted(CAROUSELS.glob("*/carousel.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"\*\*Pattern:\*\*\s*([^\n]+)", txt)
        if m:
            raw = m.group(1).strip()
            # Pattern may be "The Hidden Mechanism" or "Tier 1 · **Content Pillar:** Anxiety" — take first segment before ·
            pat = re.split(r"[·|]", raw)[0].strip().lower()
            pat = re.sub(r"[\*\_]", "", pat).strip()
            # Normalize Tier prefix — if empty after stripping Tier, fallback to hidden mechanism (malformed line)
            pat = re.sub(r"^tier\s*\d+\s*", "", pat).strip()
            if not pat:
                pat = "hidden mechanism"
            if pat:
                patterns.append(pat)
            if len(patterns) >= n:
                break
    return set(patterns)

def score_topic(topic, recent, intent_filter=None):
    # 1 Scene: filmable? heuristic: has number/body/place
    scene_l = topic["scene"].lower()
    has_number = bool(re.search(r"\d", topic["scene"]))
    has_body = any(w in scene_l for w in ("chest","heart","palms","stomach","face-down","phone","bed","inbox","clock","email","text"))
    scene = 5 if (has_number and has_body) else 4 if (has_number or has_body) else 3

    # 2 Self-blame: does blame contain "→" with reframe?
    blame = 5 if "→" in topic["blame"] or "→" in topic["blame"] else 4 if "lazy" in topic["blame"].lower() or "too much" in topic["blame"].lower() else 3

    # 3 Stealable: short stealable line? ≤10 words ideal
    steal_words = len(re.findall(r"[A-Za-z0-9']+", topic["stealable"]))
    steal = 5 if 4 <= steal_words <= 10 else 4 if steal_words <= 12 else 3

    # 4 Freshness weighted by ranking + pillar/pattern rotation (fixes "all feel same" — brain did it)
    EMERGING = {"functional-freeze","waiting-mode","waiting-mode-2","rejection-sensitive","RSD","clock-217am","replay-conversations"}
    OVERSATURATED = {"boundaries","high-functioning-anxiety","people-pleasing"}
    freshness = 2 if topic["slug"] in recent or topic["last_used"] not in ("-", "") else 5
    if topic["last_used"] not in ("-", ""):
        freshness = 3
    if topic["slug"] in EMERGING:
        freshness = min(5, freshness + 1)
    if topic["slug"] in OVERSATURATED or "boundaries" in topic["slug"]:
        freshness = max(2, freshness - 1)
    # Pillar rotation: never same pillar as last 2 decks (fixes monotony — e.g., two freeze/waiting in a row)
    try:
        recent_pills = recent_pillars(2)
        # pillar is like "Executive dysfunction / ADHD" or "Anxiety" — lower and check word overlap
        topic_pill_low = topic["pillar"].lower()
        for rp in recent_pills:
            # If any significant word (>3 chars) from recent pillar appears in topic pillar, it's same family
            rp_words = [w for w in re.findall(r"[a-z]{4,}", rp)]
            tp_words = set(re.findall(r"[a-z]{4,}", topic_pill_low))
            if any(w in tp_words for w in rp_words):
                freshness = max(2, freshness - 2)
                break
    except Exception:
        pass
    # Pattern rotation: penalize same pattern as last 2 (fixes "all Hidden Mechanism brain did it" monotony)
    try:
        recent_pats = recent_patterns(2)
        topic_pat = topic.get("pattern","").lower()
        if any(topic_pat == rp.lower() for rp in recent_pats):
            freshness = max(2, freshness - 2)
        # Also penalize Hidden Mechanism if last was Hidden Mechanism (most common)
        hm_count = sum(1 for pat in recent_pats if "hidden" in pat.lower() or "mechanism" in pat.lower())
        if hm_count >= 1 and "hidden" in topic_pat:
            freshness = max(2, freshness - 1)
    except Exception:
        pass

    # 5 Intent fit
    intent = 5 if intent_filter is None or topic["intent"] == intent_filter else 3

    total = scene + blame + steal + freshness + intent
    return {"scene": scene, "blame": blame, "stealable": steal, "freshness": freshness, "intent": intent, "total": total}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suggest", type=int, default=5, help="How many to suggest")
    ap.add_argument("--intent", choices=["sends","saves"], help="Filter by intent")
    ap.add_argument("--pick", action="store_true", help="Pick winner (highest total)")
    args = ap.parse_args()

    topics = parse_bank()
    recent = recent_slugs(10)
    scored = []
    for t in topics:
        s = score_topic(t, recent, args.intent)
        scored.append((s["total"], t, s))
    scored.sort(key=lambda x: x[0], reverse=True)

    if args.pick:
        total, t, s = scored[0]
        print(f"WINNER: {t['slug']}  total {total}/25  intent {t['intent']}")
        print(f"  Scene: {t['scene'][:90]}")
        print(f"  Blame: {t['blame']}")
        print(f"  Stealable: {t['stealable']}")
        print(f"  Scores: scene {s['scene']} blame {s['blame']} steal {s['stealable']} fresh {s['freshness']} intent {s['intent']}")
        print(f"  Last used: {t['last_used']}")
        if total < 18:
            print("  WARNING: total <18 — topic not ready, mine again")
    else:
        for total, t, s in scored[:args.suggest]:
            print(f"{t['id']:02d} {t['slug']:30s} {total:2d}/25  {t['intent']:5s}  fresh {s['freshness']}  {t['scene'][:55]}")

if __name__ == "__main__":
    main()
