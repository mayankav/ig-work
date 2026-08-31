#!/usr/bin/env python3
"""
novelty.py — is this deck new?

Unique moments are enforced upstream, so two decks can never be about the same
evening. What is left for this module is the other failure: the writer saying
the same thing twice about two different moments.

That first sentence was an assumption, and for a long time it was false. Upstream
checked the SEED — the stranger's post id and a hash of their wording — which is
decided before our moment exists, so two different seeds produced "I sat on the
edge of the bed at 11:45pm and stared at the dark hallway" twice and both
shipped. `compose.repetition_faults` is what makes the sentence true now: it
compares each invented moment against every earlier one, on words and on shape.
Do not delete it and leave this docstring standing.

The cost of checking has to stay flat as the archive grows, so nothing here ever
opens a past carousel. Each deck writes a small fingerprint once, when it is
rendered, and every later check reads fingerprints only.

Three checks, and they catch different things:

  1. Exact slide reuse       O(1) set membership against the whole archive
  2. A copied run of words    O(1) set membership against the whole archive
  3. Fuzzy resemblance        compared against a BOUNDED set: the last 30 decks,
                              plus any older deck that shares a scene anchor

Checks 1 and 2 cover all of history at constant cost, because a hash either is
or is not in a set. Check 3 is the expensive one, so it looks at about 30 decks
whether the archive holds 100 or 10,000.

Thresholds are measured, not guessed. Across this repo's own decks:

    hand-written vs hand-written      0.006 - 0.016   5-gram Jaccard
    the broken generated decks        0.714 - 0.897

Two orders of magnitude apart, so 0.15 sits nowhere near either population.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent.parent.parent
STATE_DIR = REPO_ROOT / "state"
FP_DIR = STATE_DIR / "fp"
INDEX_PATH = STATE_DIR / "fp_index.json"
PHRASES_PATH = STATE_DIR / "phrases.json"

# Deck-level resemblance. Above this, two decks are saying the same thing.
DECK_JACCARD_MAX = 0.15
# One recycled slide inside an otherwise fresh deck.
SLIDE_JACCARD_MAX = 0.35
# A copied sentence. Every legitimate repeat we found in the hand-written decks
# was a brand phrase, and those are masked out below before this applies.
SHARED_RUN_MAX = 8
# Same topic every time means term overlap has a high floor, so this sits well
# above the 0.12 our good decks reach and below the 0.49 the broken ones hit.
COSINE_MAX = 0.45
# How many recent decks get the expensive comparison.
RECENT_WINDOW = 30

# Lines the brand says on purpose, every time. Without this mask the shared-run
# check fires on our own signature and every deck fails.
BRAND_PHRASES = (
    "send this to the friend who",
    "share this with the friend who",
    "screenshot this for later",
    "save this for the next",
    "here is what to do next",
    "still feeling stuck",
    "@suresilly",
)

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "with", "by",
    "is", "it", "you", "your", "for", "that", "this", "was", "as", "but", "not",
    "be", "are", "from", "have", "has", "had", "i", "my", "me", "so", "if",
}


def _words(text: str) -> list[str]:
    """Words, with the accent markup and the brand's own phrases removed.

    Order matters. The accent markers come out first, because the brand phrases
    are written plainly and the deck writes them as "still feeling [[stuck]]".
    Masking before stripping silently matches nothing, which is how our own
    signature ended up looking like plagiarism.
    """
    text = re.sub(r"\[\[|\]\]", " ", text.lower())
    text = re.sub(r"\s+", " ", text)
    for phrase in BRAND_PHRASES:
        text = text.replace(phrase, " ")
    return re.findall(r"[a-z0-9']+", text)


def shingles(text: str, n: int) -> set[str]:
    """Hashed word n-grams. Hashes rather than the words themselves, so a
    fingerprint file never contains readable copy from a past deck."""
    tokens = _words(text)
    return {
        hashlib.blake2s(" ".join(tokens[i:i + n]).encode(), digest_size=8).hexdigest()
        for i in range(max(0, len(tokens) - n + 1))
    }


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    shared = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in shared)
    if not dot:
        return 0.0
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


def terms(text: str) -> Counter:
    return Counter(w for w in _words(text) if w not in STOP and len(w) > 2)


def longest_shared_run(a: str, b: str) -> int:
    """The longest run of words the two texts share, in order.

    Catches a copied sentence that resemblance scores can miss when the rest of
    the deck is genuinely different.
    """
    x, y = _words(a), _words(b)
    if not x or not y:
        return 0
    best = 0
    previous = [0] * (len(y) + 1)
    for i in range(1, len(x) + 1):
        current = [0] * (len(y) + 1)
        for j in range(1, len(y) + 1):
            if x[i - 1] == y[j - 1]:
                current[j] = previous[j - 1] + 1
                best = max(best, current[j])
        previous = current
    return best


# ─────────────────────────── fingerprints ────────────────────────────

def fingerprint(slug: str, slides: list[dict], anchors: list[str], text_of) -> dict:
    """Everything a later deck needs in order to be compared against this one.

    No readable copy is stored. `text_of` turns a parsed slide into its text, so
    this module does not need to know the deck format.
    """
    texts = [text_of(s) for s in slides]
    whole = " ".join(texts)

    # Shingles are collected per slide and unioned, never over the concatenated
    # deck. Joining slides end to end invents word runs that span a boundary —
    # the tail of slide 5 running into the opening of slide 6 — and those look
    # exactly like copied sentences when two decks share a closing rhythm.
    deck_shingles: set[str] = set()
    runs: set[str] = set()
    for text in texts:
        deck_shingles |= shingles(text, 5)
        runs |= shingles(text, SHARED_RUN_MAX)

    return {
        "slug": slug,
        "anchors": sorted(set(anchors)),
        "deck_shingles": sorted(deck_shingles),
        "terms": dict(terms(whole)),
        "slides": [
            {
                "hash": hashlib.sha256(" ".join(_words(text)).encode()).hexdigest()[:32],
                "shingles": sorted(shingles(text, 3)),
            }
            for text in texts
        ],
        "runs": sorted(runs),
    }


def _load(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_index() -> dict:
    """`order` is slugs oldest-first. `anchors` maps a scene anchor to the decks
    that used it, so an older deck about the same kind of evening is still
    compared even when it falls outside the recent window."""
    return _load(INDEX_PATH, {"order": [], "anchors": {}})


def comparison_set(anchors: list[str]) -> list[str]:
    """The decks this one is checked against. Bounded, and stays bounded."""
    index = load_index()
    recent = index["order"][-RECENT_WINDOW:]
    related = []
    for anchor in anchors:
        related.extend(index["anchors"].get(anchor, []))
    return list(dict.fromkeys(recent + related))


def load_fingerprint(slug: str) -> dict | None:
    return _load(FP_DIR / f"{slug}.json", None)


def record(fp: dict) -> None:
    """Store the fingerprint and update both indexes. Called once, at render."""
    FP_DIR.mkdir(parents=True, exist_ok=True)
    (FP_DIR / f"{fp['slug']}.json").write_text(json.dumps(fp) + "\n", encoding="utf-8")

    index = load_index()
    if fp["slug"] not in index["order"]:
        index["order"].append(fp["slug"])
    for anchor in fp["anchors"]:
        index["anchors"].setdefault(anchor, [])
        if fp["slug"] not in index["anchors"][anchor]:
            index["anchors"][anchor].append(fp["slug"])
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    known = set(_load(PHRASES_PATH, {"slides": [], "runs": []})["slides"])
    runs = set(_load(PHRASES_PATH, {"slides": [], "runs": []})["runs"])
    known.update(s["hash"] for s in fp["slides"])
    runs.update(fp["runs"])
    PHRASES_PATH.write_text(
        json.dumps({"slides": sorted(known), "runs": sorted(runs)}) + "\n", encoding="utf-8"
    )


# ─────────────────────────── the gate ────────────────────────────

def check(fp: dict) -> list[str]:
    """Return every reason this deck is not new. Empty means it is.

    Reasons are written to be readable in an alert, because in an unattended
    system this text is the only thing a person will see.
    """
    problems: list[str] = []
    corpus = _load(PHRASES_PATH, {"slides": [], "runs": []})

    # A deck is never compared against its own record. Rebuilding a deck is an
    # ordinary thing to do, and without this it would be caught plagiarising
    # itself the second time.
    mine_already = load_fingerprint(fp["slug"])
    own_slides = {s["hash"] for s in mine_already["slides"]} if mine_already else set()
    own_runs = set(mine_already["runs"]) if mine_already else set()

    # 1 and 2 — exact reuse, checked against all of history at constant cost.
    seen_slides = set(corpus["slides"]) - own_slides
    for i, slide in enumerate(fp["slides"], 1):
        if slide["hash"] in seen_slides:
            problems.append(f"slide {i} is word-for-word a slide we already published")

    repeated_runs = set(fp["runs"]) & (set(corpus["runs"]) - own_runs)
    if repeated_runs:
        problems.append(
            f"{len(repeated_runs)} run(s) of {SHARED_RUN_MAX}+ words appear in an earlier deck"
        )

    # 3 — resemblance, against the bounded set.
    mine = set(fp["deck_shingles"])
    my_terms = Counter(fp["terms"])
    for slug in comparison_set(fp["anchors"]):
        if slug == fp["slug"]:
            continue
        other = load_fingerprint(slug)
        if not other:
            continue

        score = jaccard(mine, set(other["deck_shingles"]))
        if score >= DECK_JACCARD_MAX:
            problems.append(f"too close to {slug}: {score:.2f} word overlap (limit {DECK_JACCARD_MAX})")

        sim = cosine(my_terms, Counter(other["terms"]))
        if sim >= COSINE_MAX:
            problems.append(f"too close to {slug}: {sim:.2f} vocabulary overlap (limit {COSINE_MAX})")

        for i, slide in enumerate(fp["slides"], 1):
            for j, theirs in enumerate(other["slides"], 1):
                s = jaccard(set(slide["shingles"]), set(theirs["shingles"]))
                if s >= SLIDE_JACCARD_MAX:
                    problems.append(
                        f"slide {i} repeats slide {j} of {slug}: {s:.2f} (limit {SLIDE_JACCARD_MAX})"
                    )
    return sorted(set(problems))
