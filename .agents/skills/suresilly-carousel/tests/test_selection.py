#!/usr/bin/env python3
"""
Pose-selection accuracy.

Labelled slides, each with the poses a person would accept. Selection quality
is a judgement call, so it needs a number to move rather than an opinion.

TWO sets, and the split matters. TUNED cases were used while building the
scorer, so their score is optimistic by construction — it went 35% to 100%
while the honest number moved far less. HELDOUT cases were written afterwards
and never tuned against; that is the number to trust and the one to quote.
Anyone adding cases should add them to HELDOUT.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import library  # noqa: E402

# (role, brief, headline, body, {poses a person would accept})
TUNED = [
 ("hook", "deadpan, unimpressed, staring at the viewer",
  "Why calm people make your nervous system panic", "",
  {"deadpan", "side_eye", "unimpressed", "slow_blink"}),
 ("agitation", "",
  "Peace feels like danger when chaos was normal",
  "If you spent years bracing for the next mood swing, silence never reads as peace.",
  {"clutching", "spiralling", "watchful", "crouched_tight", "knees_hugged", "guarded"}),
 ("source", "studious, reading glasses, holding an open book",
  "Your nervous system decides safety before you do", "",
  {"reading", "pondering", "knowing_look", "sage"}),
 ("value", "",
  "You mistake adrenaline for attraction",
  "That instant connection is often cortisol, not romance.",
  {"realising", "idea", "pondering", "surprise", "explaining"}),
 ("value", "",
  "Hypervigilance manufactures conflict",
  "When nothing is wrong your brain assumes something is hidden. You reread harmless texts.",
  {"watchful", "spiralling", "phone_down", "peeping", "hesitating"}),
 ("value", "",
  "Healthy love feels remarkably quiet",
  "Real security is repetitive, steady and undramatic.",
  {"serene", "sitting", "contented", "kneeling", "warm_mug", "head_tilt", "relieved"}),
 ("cheat", "", "The reality check", "Four things to hold on to.",
  {"holding_board", "explaining", "presenting", "pointing", "framing"}),
 ("cta", "", "Send this to your favourite overthinker", "",
  {"welcoming", "waving", "beckoning", "pointing", "offering", "high_five"}),
 ("value", "",
  "One of you chases and the other pulls away",
  "The more one partner reaches, the further the other retreats.",
  {"pursue_withdraw", "chasing", "clinging", "checking_back"}),
 ("value", "", "You are both doing the thing that used to keep you safe",
  "Neither of you is the villain here. You are two people protecting themselves at each other.",
  {"back_to_back", "arguing", "sulking", "not_listening", "far_apart", "secure"}),
 ("value", "", "Walking away is not the same as giving up",
  "Sometimes leaving is the boundary.",
  {"walking_away", "already_leaving", "putting_down", "declining", "palm_out"}),
 ("value", "", "The exhaustion of being everyone's therapist",
  "You carry every conversation. Nobody carries yours.",
  {"carrying_it_all", "catching_breath", "floor_slumped", "face_down", "caregiver"}),
 ("value", "", "Saying no without a paragraph of explanation",
  "A boundary does not need a defence.",
  {"palm_out", "declining", "standing_tall", "unimpressed", "guardian"}),
 ("agitation", "", "3am and your brain will not stop",
  "You lie there running the conversation again.",
  {"sleepless", "on_back", "spiralling", "one_awake"}),
 ("value", "", "Repair matters more than never fighting",
  "Every couple ruptures. The ones that last come back.",
  {"repair_attempt", "apologising", "hugging", "reaching", "steadying", "comforting"}),
 ("value", "", "You are allowed to take up space",
  "Standing at full height is not arrogance.",
  {"standing_tall", "hoof_on_chest", "hero_stance", "caped", "proud"}),
 ("value", "", "The relief of being understood",
  "Someone finally says the thing you could not name.",
  {"relieved", "listening", "talking_easily", "head_tilt", "comforting"}),
 ("value", "", "Pretending you are fine is a full time job",
  "The smile costs more than the honesty would.",
  {"fake_smile", "big_sigh", "slow_blink", "guarded"}),
 ("value", "", "Curiosity beats certainty in an argument",
  "Ask one more question before you decide what they meant.",
  {"pondering", "listening", "head_tilt", "explaining", "comparing"}),
 ("value", "", "Small steady effort rebuilds trust",
  "Not one grand gesture. A hundred boring ones.",
  {"gardener", "patient_one", "walking", "ready", "picking_up", "kneeling"}),
]


HELDOUT = [
 ("value", "", "The 'ick' is sometimes just your nervous system getting bored",
  "No emergency to manage, so your brain invents a reason to leave.",
  {"watchful","spiralling","unimpressed","side_eye","slow_blink","hesitating","big_sigh"}),
 ("value", "", "You apologise for things that are not your fault",
  "Sorry has become punctuation. It buys a second of safety and costs you a piece of yourself.",
  {"apologising","fake_smile","guarded","self_hug","caregiver","shrugging","hesitating"}),
 ("agitation", "", "The friend everyone calls and nobody checks on",
  "You hold everyone's worst week. Nobody asks about yours.",
  {"caregiver","catching_breath","floor_slumped","face_down","holding_up","knees_hugged"}),
 ("value", "", "Rest is not a reward you earn",
  "You do not have to be empty before you are allowed to stop.",
  {"serene","sitting","warm_mug","propped_up","on_back","relieved","kneeling"}),
 ("value", "", "Your partner is not a mind reader",
  "Say the thing. The hint is not the message.",
  {"explaining","talking_easily","pointing","reaching","listening","presenting","blank_card"}),
 ("cta", "", "Send this to the person you keep having this fight with", "",
  {"waving","beckoning","pointing","blank_card","high_five","approving","cheering"}),
 ("source", "", "Gottman found bids for connection predict divorce",
  "Ninety four percent accuracy from whether partners turn toward each other.",
  {"reading","sage","pondering","knowing_look","lab_coat","explaining"}),
 ("value", "", "Leaving the room is a skill, not an insult",
  "Twenty minutes apart beats two hours of damage.",
  {"walking_away","palm_out","declining","turning_away","already_leaving","putting_down"}),
 ("value", "", "Jealousy is information, not instruction",
  "It tells you something matters. It does not tell you what to do.",
  {"pondering","comparing","weighing","hesitating","watchful","idea","head_tilt","explaining"}),
 ("cheat", "", "Four things to try before you raise your voice",
  "Keep this for the next one.",
  {"holding_board","presenting","framing","explaining","pointing","comparing"}),
 # No pose's tags contain "checked out" literally — this only resolves if
 # concept expansion maps it to the "withdrawn" cluster's core word, which
 # IS a literal tag on guarded/turning_away.
 ("value", "", "He has completely checked out of this conversation", "",
  {"guarded", "turning_away", "curled_up"}),
]


# Poses quarantined as clipped are deliberately unreachable, so an answer key
# must not name one — see mascot/poses.json "clipped".


def run(cases, label, verbose=False):
    have = library.available()
    hits = 0
    misses = []
    for role, brief, head, body, ok in cases:
        pick = library.pick_for_slide(brief, head, body, role, set(), have)
        good = pick in ok
        hits += good
        if not good:
            misses.append((head[:46], pick, sorted(ok)[:3]))
        if verbose:
            print(f"  {'✓' if good else '✗'} {pick:20s} {head[:48]}")
    return hits, len(cases), misses


def test_recency_penalty():
    """A pose used across recent decks loses ground to a comparable fresh
    pose — but a deck rebuilding itself is never penalised for its own past
    choice. Uses a synthetic usage dict, not real carousels/ state, so it
    stays hermetic as decks are added or removed."""
    have = library.available()
    brief, head, body, role = "", "flat unimpressed expression", "", "hook"
    usage = {
        "20260101_deck_a": ["deadpan"],
        "20260102_deck_b": ["deadpan"],
        "20260103_deck_c": ["deadpan"],
    }

    without_history = library.pick_for_slide(brief, head, body, role, set(), have)
    with_history = library.pick_for_slide(
        brief, head, body, role, set(), have,
        usage=usage, exclude_slug="20260104_deck_d")
    assert with_history != without_history or without_history != "deadpan", (
        "an overused pose should lose ground to a fresh alternative when one exists")

    self_rebuild = library.pick_for_slide(
        brief, head, body, role, set(), have,
        usage=usage, exclude_slug="20260101_deck_a")
    assert self_rebuild == without_history, (
        "rebuilding a deck must not penalise it for its own past choice")
    print("  ✓ recency penalty prefers a fresh pose; self-rebuild is unpenalised")


if __name__ == "__main__":
    print("=== TUNED (optimistic — the scorer was built against these) ===")
    th, tn, tm = run(TUNED, "tuned", verbose=True)
    print(f"  {th}/{tn}  ({100*th//tn}%)\n")

    print("=== HELD OUT (the honest number) ===")
    hh, hn, hm = run(HELDOUT, "heldout", verbose=True)
    print(f"  {hh}/{hn}  ({100*hh//hn}%)\n")

    if hm:
        print("held-out misses — each one is a tag the library does not have yet:")
        for head, got, want in hm:
            print(f"  {head:48s} got {got:18s} wanted e.g. {want}")

    print("\n=== cross-deck recency penalty ===")
    test_recency_penalty()


# ─────────────────── thresholds must live on the current scale ───────────────

def test_the_special_bar_is_reachable_on_the_current_score_scale():
    """SPECIAL_BAR is in absolute score units, so it only means anything against
    the scale _overlap() actually returns.

    When _overlap started returning a per-tag mean instead of a sum, the top of
    the scale fell from 11.96 to 1.708 and the bar stayed at 6. Nothing could
    reach it, so all 24 costume poses took the penalty on every slide and none
    of them scored above zero anywhere — a silent total ban that the accuracy
    numbers did not move, because the labelled cases mostly do not want a
    costume. This test is the one that would have caught it.
    """
    have = library.available()
    special = [p for p in library.SPECIAL if p in have]
    assert special, "no costume poses in the library; this test is meaningless"
    best = max(
        library.score(brief, pose, head, body, role)
        for role, brief, head, body, _ in TUNED + HELDOUT
        for pose in special)
    assert best > 0, (
        f"no costume pose can score above zero (best {best:.3f}); SPECIAL_BAR="
        f"{library.SPECIAL_BAR} is unreachable on the current score scale")


def test_score_is_not_just_a_count_of_tags():
    """The bias that made 140 of 186 poses unreachable: _overlap summed over a
    pose's tags, so a long tag list scored higher for the same quality of match.
    Two poses matching one identical phrase must score the same whatever else
    they are tagged with."""
    words = {"lonely"}
    lean = library._overlap(words, "__lean__")
    assert lean == 0.0, "unknown pose should score nothing"

    library.SYNONYMS["__lean__"] = ["lonely"]
    library.SYNONYMS["__rich__"] = ["lonely"] + [f"filler{i}" for i in range(15)]
    try:
        a = library._overlap(words, "__lean__")
        b = library._overlap(words, "__rich__")
        assert a > 0 and b > 0
        assert b <= a, (
            f"a pose with 16 tags scored {b:.3f} on the same single match that "
            f"earned a 1-tag pose {a:.3f} — tag count is buying score again")
    finally:
        del library.SYNONYMS["__lean__"], library.SYNONYMS["__rich__"]


def test_a_single_figure_pose_is_not_tagged_as_a_pair():
    """carrying_it_all is one donkey carrying a stack of boxes, and it was
    tagged 'two people', 'the pair', 'between you'. Those pull a solo pose onto
    every slide about two people, which is the one thing PAIR_PHRASES exists to
    get right."""
    import json as _json
    manifest = _json.loads((pathlib.Path(library.MANIFEST)).read_text())["poses"]
    pair_words = {"two people", "the pair", "both of you", "between you"}
    wrong = [n for n, e in manifest.items()
             if e.get("figures", 1) == 1 and pair_words & set(e.get("tags", []))]
    assert wrong == [], f"single-figure poses carrying pair tags: {wrong}"
