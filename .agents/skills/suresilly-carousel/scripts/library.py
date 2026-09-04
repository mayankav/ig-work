#!/usr/bin/env python3
"""
library.py — picks a pose from the library for a slide.

The library is the zero-cost path: full-body Silly artwork generated as 6-up
sheets and cut out by import_poses.py. It is finite, so it cannot invent a pose
on demand the way live generation can — but it is free, instant, and reads as
the same character every time.

Selection scores the slide's plain-English mascot brief against a synonym table,
so the SAME brief field drives both this and generation. Ties and repeats are
broken so a nine-slide deck does not show the same face three times.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LIBRARY_DIR = Path(__file__).resolve().parent.parent / "mascot" / "library"

MANIFEST = Path(__file__).resolve().parent.parent / "mascot" / "poses.json"

HISTORY_PATH = Path(__file__).resolve().parent.parent / "mascot" / "usage_history.json"


def _load() -> tuple[dict[str, list[str]], dict[str, str], list[str]]:
    """Pose metadata lives in mascot/poses.json so growing the library is a data
    edit, not a code edit. Adding a pose = drop the PNG in, add a manifest row."""
    if not MANIFEST.is_file():
        return {}, {}, []
    m = json.loads(MANIFEST.read_text())
    syn = {k: v.get("tags", []) for k, v in m.get("poses", {}).items()}
    return syn, m.get("role_default", {}), m.get("rotation", [])


SYNONYMS, ROLE_DEFAULT, VALUE_ROTATION = _load()


def _load_concepts() -> dict[str, list[str]]:
    """Concept clusters: a core word already used somewhere in the tag
    corpus, mapped to synonym phrases that mean the same thing but never
    appear in any pose's literal tags. See CONCEPTS below for why this
    doesn't touch IDF."""
    if not MANIFEST.is_file():
        return {}
    return json.loads(MANIFEST.read_text()).get("concepts", {})


CONCEPTS = _load_concepts()

_META: dict = (json.loads(MANIFEST.read_text()).get("poses", {})
               if MANIFEST.is_file() else {})


def is_clipped(pose: str) -> bool:
    """A pose that lost a limb to the sheet grid. Five of these exist and the
    source sheets are gone, so they are kept out of selection entirely."""
    return bool(_META.get(pose, {}).get("clipped", False))


def is_pair(pose: str) -> bool:
    """True for a two-donkey scene."""
    return _META.get(pose, {}).get("figures", 1) == 2


def is_mirrored(pose: str) -> bool:
    """Mirrored copies are valid but slightly off-model — the mane flips sides."""
    return bool(_META.get(pose, {}).get("mirrored", False))


def framing_of(pose: str) -> str:
    """'bust' or 'full' — full-body poses compose better and win ties."""
    return _META.get(pose, {}).get("framing", "bust")


def available() -> set[str]:
    if not LIBRARY_DIR.is_dir():
        return set()
    import art_eligibility
    import owner_art
    import os
    blocked = set(os.environ.get("OWNER_REDO_EXCLUDE_HASHES", "").split(",")) if owner_art.enabled() else set()
    return {f.stem for f in LIBRARY_DIR.glob("*.png")
            if not f.stem.startswith("_") and not art_eligibility.faults(f)
            and art_eligibility.digest(f.read_bytes()) not in blocked}


def load_usage() -> dict[str, list[str]]:
    """Which poses each past deck used, keyed by carousel slug.

    Nothing writes here until a build finishes cleanly, so a deck that failed
    QA or aborted never pollutes what "recently used" means.
    """
    if not HISTORY_PATH.is_file():
        return {}
    return json.loads(HISTORY_PATH.read_text())


def record_usage(slug: str, chosen: dict[int, str]) -> None:
    """Record this deck's pose choices, replacing any prior record for the
    same slug so rebuilding a deck updates its entry instead of piling up."""
    history = load_usage()
    history[slug] = [chosen[i] for i in sorted(chosen)]
    HISTORY_PATH.write_text(json.dumps(history, indent=2) + "\n")


def _recent_pose_count(pose: str, usage: dict[str, list[str]],
                        exclude_slug: str | None, k: int = 5) -> int:
    """How many times `pose` shows up across the k most recent OTHER decks.

    Slugs sort chronologically (YYYYMMDD_name), so the tail of the sorted key
    list is the most recent history. Rebuilding a deck excludes its own past
    record — a deck is never penalised for having used a pose itself.
    """
    slugs = sorted(s for s in usage if s != exclude_slug)[-k:]
    return sum(usage[s].count(pose) for s in slugs)


# Function words carry no meaning on their own. Corpus rarity cannot catch
# these: "you" is tagged by exactly one pose, so it looked RARE and scored like
# a specialist term — while appearing in almost every headline ever written.
# That single word was putting the pointing pose on a third of all slides.
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "with", "by",
    "his", "her", "their", "its", "he", "she", "they", "them", "we", "us", "i",
    "me", "my", "you", "your", "yours", "it", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "am", "as", "for", "from", "but",
    "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "not", "no", "yes", "all", "any", "some", "more", "most", "very",
    "just", "like", "what", "when", "where", "why", "how", "who", "while",
    "so", "than", "then", "there", "here", "now", "one", "own", "get", "got",
    "make", "makes", "keep", "keeps", "thing", "things", "way",
}

# Phrases, not single words. Every bare word tried here misfired on ordinary
# solo briefs: "both hooves" is two limbs, and "one hoof holding a book, the
# other resting under his chin" is one donkey — but both scored as two people
# and pulled a pair scene onto a solo slide.
PAIR_PHRASES = (
    "each other", "one another", "the other one", "while the other",
    "and the other", "the other donkey", "the other person",
    "two people", "two donkeys", "another donkey", "someone else",
    "with someone", "at someone", "for someone", "to someone",
    "his partner", "her partner", "their partner", "your partner", "a partner",
    "both of you", "both of them", "between them", "between you",
    "side by side", "back to back", "relationship", "together",
    "every couple", "a couple", "couples", "the two of", "one of you",
    "both partners", "you and your", "each of you",
)


def mentions_two(brief: str) -> bool:
    t = " " + " ".join(brief.lower().split()) + " "
    return any(ph in t for ph in PAIR_PHRASES)


def _stem(w: str) -> str:
    """Crude suffix strip so 'clings' and 'clinging' both reduce to 'cling'."""
    w = w.lower().strip(".,;:!?\"'()")
    for suf in ("ings", "ing", "ed", "es", "s"):
        if len(w) - len(suf) >= 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[A-Za-z]+", text)} - STOP


# A brief saying "shut down" should match a pose tagged "withdrawn" without
# the two sharing a single literal word. Each CONCEPTS core is a word that
# ALREADY exists in the tag corpus — expansion only recognises a synonym
# phrase and injects the existing core word, so no new vocabulary ever
# enters _build_idf(). That is deliberate: a brand-new marker token seen in
# only one or two poses would get an inflated IDF weight the same way "you"
# once did (see STOP above), just from the opposite direction. Reusing an
# existing, already-safely-weighted word sidesteps that risk entirely.
def _expand_concepts(words: set[str]) -> set[str]:
    if not CONCEPTS:
        return words
    out = set(words)
    for core, phrases in CONCEPTS.items():
        if _stem(core) in out:
            continue
        for phrase in phrases:
            need = _words(phrase)
            if need and need <= words:
                out.add(_stem(core))
                break
    return out


# Poses that carry a costume or a named prop. They are great when the slide
# actually calls for them and jarring when it does not, so they need a real
# keyword hit rather than a stray one.
SPECIAL = {
    "scarf", "cardigan_mug", "bathrobe", "detective", "lab_coat", "caped",
    "guardian", "sage", "healer", "explorer", "caregiver", "rebel",
    "hero_stance", "hero_flying", "hero_landing", "hero_fumbling",
    "hero_defeated", "hero_hiding", "lantern_bearer", "traveller",
    "storyteller", "gardener", "patient_one", "night_watch",
}
# Both of these live on the score scale, so they moved when _overlap started
# returning a per-tag mean instead of a sum. Measured on the same 94-slide
# corpus, the top of the scale went from 11.96 to 1.708 — a factor of 7 — so
# the bar and its penalty are the old 6 divided by that.
#
# Leaving them at 6 was a silent ban, not a bias: nothing could reach a bar of
# 6 on a scale that tops out at 1.7, so every one of the 24 costume poses took
# the penalty on every slide and none of them scored above zero anywhere. A
# threshold in absolute units is only ever calibrated for the scale it was
# written against, and this is the note for whoever changes the scale next.
SPECIAL_BAR = 0.857
SPECIAL_PENALTY = 0.857


def mood_of(pose: str) -> tuple[float, float]:
    m = _META.get(pose, {})
    return float(m.get("valence", 0.0)), float(m.get("arousal", 1.5))


def _lex():
    if not MANIFEST.is_file():
        return {}, {}
    lex = json.loads(MANIFEST.read_text()).get("mood_lexicon", {})
    v = {w: int(k) for k, ws in lex.get("valence", {}).items() for w in ws}
    a = {w: int(k) for k, ws in lex.get("arousal", {}).items() for w in ws}
    return v, a


_VL, _AL = _lex()


def slide_mood(text: str) -> tuple[float, float] | tuple[None, None]:
    """Read valence and arousal out of the slide's own words."""
    t = " " + " ".join(text.lower().split()) + " "
    vs = [v for w, v in _VL.items() if w in t]
    a_s = [a for w, a in _AL.items() if w in t]
    if not vs and not a_s:
        return None, None
    return (sum(vs) / len(vs) if vs else 0.0,
            sum(a_s) / len(a_s) if a_s else 1.5)


def _build_idf() -> dict[str, float]:
    """How rare each tag word is across the whole library.

    Without this, "you" — which sits in one pose's tag list and in nearly every
    headline ever written — scored exactly like "hypervigilant". That one word
    was enough to put the pointing pose on a third of all slides.
    """
    import math
    df: dict[str, int] = {}
    for tags in SYNONYMS.values():
        seen = set()
        for t in tags:
            seen |= _words(t)
        for w in seen:
            df[w] = df.get(w, 0) + 1
    n = max(1, len(SYNONYMS))
    return {w: math.log(1 + n / c) for w, c in df.items()}


_IDF = _build_idf()
_IDF_MAX = max(_IDF.values()) if _IDF else 1.0


def _weight(word: str) -> float:
    """Rare words count; words that mean nothing on their own barely do."""
    return _IDF.get(word, _IDF_MAX) / _IDF_MAX


def _overlap(words: set[str], pose: str) -> float:
    """How well a pose's tags match a slide's words, per tag.

    PER TAG is the whole point. This used to return the raw sum, so a pose with
    sixteen tags had sixteen chances to accumulate score and a pose with five
    had five. That rewards whoever wrote the longest tag list, not the pose that
    fits, and it shows up in the library exactly that way. Measured over the 94
    real and labelled slides in this repo:

        2-4 tags    11 poses    won   0 slides    0 of 11 ever reachable
        5-6 tags    93 poses    won  32 slides   16 of 93 ever reachable
        9-16 tags   68 poses    won  52 slides   24 of 68 ever reachable

    Tag count correlates +0.31 with mean score and +0.22 with wins. The eleven
    thinnest poses — which includes every scene imported so far — could not win
    a single slide out of ninety-four.

    Dividing by the count removes the arithmetic advantage and leaves the real
    one: a pose with more tags still has more ways to match, it just cannot bank
    a weak match as a strong one. Held-out accuracy 54% -> 63%, tuned unchanged
    at 95%, reachable poses 26 -> 32.

    Be honest about that held-out number: the set is eleven cases, so it moved
    by one. The justification is the bias, which is arithmetic and does not
    depend on the sample; the accuracy figure is a check that fixing it does no
    harm, not the reason for doing it.

    Dividing by sqrt(n) and by log(1+n) were both tried. Same accuracy, fewer
    poses reachable (27 and 29 against 32), so the plain mean wins on the one
    measure that separated them.
    """
    total = 0.0
    for tag in SYNONYMS.get(pose, []):
        tw = _words(tag)
        if not tw:
            continue
        common = tw & words
        if not common:
            continue
        w = sum(_weight(x) for x in common)
        if len(common) == len(tw):
            total += 3 * w                    # the whole phrase is present
        else:
            total += 0.35 * w                 # one word of a phrase is weak
            # "brain will not stop" hitting the stop in palm_out, or "take up
            # space" hitting the up in point_up, is a word-sense accident. A
            # partial hit should never outrank a pose that matches the theme.
    return total / max(1, len(SYNONYMS.get(pose, [])))


# What a slide is FOR constrains which moods belong on it, whatever the words
# happen to match. A before-and-after slide is offering the reader a better
# option; an arms-folded scowl reads as telling them off.
# Valence is now read off the drawing, so these floors actually bite. 38% of
# the library has a heavy angled brow and reads as cross whatever it is called;
# a slide that offers the reader something kind must not use one.
ROLE_MOOD_FLOOR = {"script": 0.0, "cta": 1.0}

# How much a never-placed pose is favoured over a comparable veteran.
#
# Chosen by measuring the trade rather than by taste. Over the seven real decks,
# scoring each chosen pose by its UNBOOSTED merit so the boost cannot flatter
# itself:
#
#     boost   mean fit of chosen   placements of never-used poses
#     off     1.438                 2 / 63
#     1.25    1.435                 4 / 63
#     1.50    1.387 (-3.5%)        10 / 63
#     1.75    1.339 (-6.9%)        13 / 63
#
# 1.5 buys five times the variety for three and a half percent of fit. The
# median chosen pose is still the highest-scoring one available at every level
# on that table — the boost only decides slides where two poses were already
# close, which is exactly the case where variety is free.
COLD_BOOST = 1.5


def _ever_used(pose: str, usage: dict[str, list[str]],
               exclude_slug: str | None) -> bool:
    """Has this pose been placed on any deck other than the one being rebuilt."""
    return any(pose in poses for slug, poses in usage.items() if slug != exclude_slug)


def score(brief: str, pose: str, headline: str = "", body: str = "",
          role: str = "", usage: dict[str, list[str]] | None = None,
          exclude_slug: str | None = None) -> float:
    """How well a pose fits a slide.

    The brief is the strongest signal but it is often absent — most slides never
    write one. Reading the headline and body as well is what took this from
    guessing the role default to actually matching the slide. Weighted so an
    explicit brief still wins when there is one.
    """
    if is_clipped(pose):
        return -1000.0

    total = 0.0
    for text, weight in ((brief, 3.0), (headline, 2.0), (body, 1.0)):
        if text:
            total += weight * _overlap(_expand_concepts(_words(text)), pose)

    joined = " ".join(x for x in (brief, headline, body) if x)

    # Two donkeys only belong on a slide that describes two people. Scaling
    # beats subtracting: a flat penalty is outrun by a strong keyword match, and
    # a slide reading "real security is steady" pulled the two-donkey `secure`
    # scene onto a page about one person.
    if is_pair(pose):
        total = total * 1.5 if mentions_two(joined) else total * 0.12

    # A costume or prop needs a real hit, not a stray one.
    if pose in SPECIAL and total < SPECIAL_BAR:
        total -= SPECIAL_PENALTY

    # A strong penalty, not an exclusion. Made absolute, this removed so many
    # candidates that weak accidental matches surfaced instead and held-out
    # accuracy fell from 60% to 30% — worse than leaving it alone. The stern
    # poses still lose to any warm pose with a comparable match.
    floor = ROLE_MOOD_FLOOR.get(role)
    if floor is not None and mood_of(pose)[0] < floor:
        total *= 0.30

    # Cross-deck variety. Soft and bounded, same lesson as the mood floor above:
    # a pose used across recent decks loses ground to a comparably-scoring
    # fresh one, but is never excluded outright.
    #
    # COLD_BOOST is the other half of that, and it exists because the penalty
    # alone was not enough. Measured over the 35 decks in usage_history.json:
    # 89 of 186 poses have never been placed once, and the top 20 poses take 55%
    # of all 315 placements. Penalising the overused ones spreads the top of the
    # distribution; it does nothing for a pose sitting at zero, which never
    # competes closely enough for the penalty on its rival to matter.
    #
    # It can only ever amplify a match that already exists. The multiply happens
    # before the `total <= 0` return below, so a pose with no word in common
    # scores zero, and zero times anything is still zero. This buys a
    # never-placed pose a nudge past a comparable veteran, never a slide it does
    # not fit.
    #
    # NOT given to mirrored copies either. A flipped Silly has his mane on the
    # wrong side and selection already breaks ties against him. At a boost of
    # 1.25 without this guard, five of the seven poses the boost newly
    # introduced were mirrors — it was surfacing the off-model half of the
    # library rather than the unused good half, which is the opposite of the
    # point.
    #
    # NOT given to pair scenes. 19 of the 65 idle poses are two-donkey scenes,
    # and they are idle because only 1 of 63 real slides is about two people —
    # a fact about what has been written, not a fault in the scoring. Boosting
    # them would rebuild the exact defect the is_pair scaling above was added to
    # fix: a slide reading "real security is steady" pulling the two-donkey
    # `secure` scene onto a page about one person.
    if usage is not None:
        recent = _recent_pose_count(pose, usage, exclude_slug)
        if recent:
            total *= max(0.35, 1.0 - 0.20 * recent)
        elif (not is_pair(pose) and not is_mirrored(pose)
              and not _ever_used(pose, usage, exclude_slug)):
            total *= COLD_BOOST

    if total <= 0:
        return total

    # Emotional fit SCALES a real match rather than standing in for one.
    # As a separate penalty it let a pose with no word in common win on mood.
    #
    # Only when the slide has NO brief. This brand writes in contrasts — "peace
    # feels like danger", "healthy love feels boring", "repair matters more than
    # fighting" — so the words a slide NAMES are routinely the opposite of the
    # feeling it describes. Reading mood off that text scaled an explicitly
    # briefed panic pose down to a quarter and handed the slide to `relieved`.
    # A written brief is the author saying what the mood is; believe it.
    sv, sa = (None, None) if brief.strip() else slide_mood(joined)
    if sv is not None:
        pv, pa = mood_of(pose)
        # Deliberately gentle. Mood is a weak signal on copy written in
        # contrasts — "peace feels like danger" names the pleasant thing and
        # then subverts it — so it may nudge a ranking, never overturn a strong
        # keyword match.
        gap = 0.16 * abs(sv - pv) + 0.10 * abs(sa - pa)
        total *= max(0.60, 1.0 - gap)

    return total


def pick_for_slide(brief: str, headline: str, body: str, role: str,
                   used: set[str], have: set[str],
                   usage: dict[str, list[str]] | None = None,
                   exclude_slug: str | None = None) -> str | None:
    """Best unused pose for this slide, judged on everything the slide says."""
    if not have:
        return None
    brief = re.sub(r"S\d\.\d", "", brief or "")

    ranked = sorted(
        ((score(brief, p, headline, body, role, usage, exclude_slug),
          framing_of(p) == "full", is_mirrored(p), p)
         for p in have),
        key=lambda t: (-t[0], not t[1], t[2], t[3]))

    for sc, _, _, p in ranked:
        if sc > 0 and p not in used:
            return p

    default = ROLE_DEFAULT.get(role, "explaining")
    # A slide with no brief at all always lands here — the exact case that
    # kept putting the same role_default pose on every deck's cheat/CTA
    # slide. Same soft-preference approach as score()'s recency penalty: try
    # the default first, but if it's been used a lot lately, a fresher
    # rotation pose is offered ahead of it.
    fallback = [default] + [p for p in VALUE_ROTATION if p != default]
    fallback = [p for p in fallback if p in have and p not in used]
    if usage is not None and fallback:
        fallback = sorted(fallback,
                          key=lambda p: _recent_pose_count(p, usage, exclude_slug))
    if fallback:
        return fallback[0]
    for p in sorted(have, key=lambda x: (is_mirrored(x), x)):
        if p not in used:
            return p
    return default if default in have else sorted(have)[0]


def pick(brief: str, role: str, used: set[str], have: set[str],
         usage: dict[str, list[str]] | None = None,
         exclude_slug: str | None = None) -> str | None:
    """Brief-only entry point, kept for callers that have no slide copy."""
    return pick_for_slide(brief, "", "", role, used, have, usage, exclude_slug)


def assign_deck(slides: list[dict], have: set[str],
                 usage: dict[str, list[str]] | None = None,
                 exclude_slug: str | None = None) -> dict[int, str]:
    """Choose poses for a WHOLE deck at once.

    Picking slide by slide is greedy and cascades: an early slide takes the
    pose a later slide needed far more, and the later slide falls through to
    something wrong. Here every slide is scored against every pose, then the
    strongest pairing in the whole grid is taken first and its row and column
    are struck out — so a pose goes to the slide with the best claim on it,
    not to whichever slide happened to come first.

    `slides` is a list of {brief, headline, body, role}.
    """
    if not have or not slides:
        return {}
    poses = sorted(have)
    grid = [[score(s.get("brief", ""), p, s.get("headline", ""), s.get("body", ""),
                   s.get("role", ""), usage, exclude_slug)
             for p in poses] for s in slides]

    cells = sorted(
        ((grid[i][j], i, j) for i in range(len(slides)) for j in range(len(poses))
         if grid[i][j] > 0),
        key=lambda c: (-c[0], poses[c[2]]))

    out: dict[int, str] = {}
    taken_pose: set[int] = set()
    for sc, i, j in cells:
        if i in out or j in taken_pose:
            continue
        out[i] = poses[j]
        taken_pose.add(j)
        if len(out) == len(slides):
            break

    # anything that matched nothing falls back to its role — same
    # recency-aware ordering as pick_for_slide's fallback, so a deck full of
    # brief-less slides doesn't just hand every one of them the same default.
    used = set(out.values())
    for i, s in enumerate(slides):
        if i in out:
            continue
        d = ROLE_DEFAULT.get(s.get("role", ""), "explaining")
        fallback = [d] + [p for p in VALUE_ROTATION if p != d]
        fallback = [p for p in fallback if p in have and p not in used]
        if usage is not None and fallback:
            fallback = sorted(fallback,
                              key=lambda p: _recent_pose_count(p, usage, exclude_slug))
        out[i] = fallback[0] if fallback else next(
            (p for p in poses if p not in used), poses[0])
        used.add(out[i])
    return out


def path_for(pose: str) -> Path:
    return LIBRARY_DIR / f"{pose}.png"
