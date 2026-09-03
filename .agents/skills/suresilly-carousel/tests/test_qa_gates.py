import sys, pathlib, numpy as np, cv2
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
from cutout import qa, QAFailure

def clean():
    c = np.zeros((600, 600, 4), np.uint8)
    cv2.circle(c, (300, 250), 165, (88,152,114,255), -1)
    cv2.rectangle(c, (205, 370), (395, 600), (88,152,114,255), -1)
    return c

FAILURES = []


def report(name, img, expect):
    try:
        qa(img, src_shape=(600,600)); got = "accept"
    except QAFailure as e:
        got = "reject"; why = str(e)[:70]
    ok = "✓" if got == expect else "✗✗"
    if got != expect:
        FAILURES.append(name)
    print(f"  {ok} {name:22s} expected {expect:6s} got {got}" + (f"  [{why}]" if got=="reject" else ""))

print("=== realistic synthetic cases ===")
report("clean_figure", clean(), "accept")

# caption text as separate glyph islands — what real printed labels look like.
# Measured on the real fixtures: 9 low components with similar heights.
t = clean()
for k in range(9):
    x = 120 + k * 26
    cv2.rectangle(t, (x, 552), (x + 14, 552 + 16), (0, 0, 0, 255), -1)
report("caption_glyph_run", t, "reject")

# a LONE detached art fragment — a foot mid-jump, a hoof behind a cape.
# Must PASS: one fragment is not text, and rejecting it threw away four good poses.
one = clean()
cv2.ellipse(one, (250, 566), (16, 12), 0, 0, 360, (20, 20, 20, 255), -1)
report("single_art_fragment", one, "accept")

# two fragments still pass; text needs a run
two = clean()
cv2.ellipse(two, (250, 566), (16, 12), 0, 0, 360, (20, 20, 20, 255), -1)
cv2.ellipse(two, (350, 570), (14, 11), 0, 0, 360, (20, 20, 20, 255), -1)
report("two_art_fragments", two, "accept")

# second figure in frame (model returned a 2-pose sheet)
d = clean(); cv2.circle(d, (80, 120), 70, (88,152,114,255), -1)
report("two_subjects", d, "reject")

# clipped by the left edge
l = clean(); cv2.circle(l, (10, 250), 165, (88,152,114,255), -1)
report("clipped_left", l, "reject")

# a patch of backdrop colour left on the subject (magenta key, hue 150)
g = clean()
cv2.circle(g, (300, 300), 34, (255, 0, 255, 255), -1)
try:
    qa(g, src_shape=(600,600), key_bgr=(255,0,255)); print("  \u2717\u2717 key_residue          expected reject got accept"); FAILURES.append("key_residue")
except QAFailure as e:
    print(f"  \u2713 key_residue          expected reject got reject  [{str(e)[:66]}]")

# tiny subject floating in a big crop
s = np.zeros((600,600,4), np.uint8); cv2.circle(s, (300,300), 55, (88,152,114,255), -1)
report("subject_too_small", s, "reject")


# Real-world regression: the artefacts the previous pipeline actually shipped.
OLD = pathlib.Path(__file__).resolve().parent / "fixtures" / "contaminated"
if OLD.is_dir():
    print("\n=== real contaminated poses from the old pipeline (must all reject) ===")
    for f in sorted(OLD.glob("*.png")):
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None or img.shape[2] != 4:
            continue
        try:
            qa(img, src_shape=img.shape[:2]); print(f"  ✗✗ {f.stem:14s} ACCEPTED"); FAILURES.append(f.stem)
        except QAFailure:
            print(f"  ✓  {f.stem:14s} rejected")


# ── lettering written ON the figure ────────────────────────────────────────
#
# glyph_runs counts a mark only when it is a SEPARATE PIECE OF PICTURE — its own
# connected region of non-backdrop. Letters inside a white speech bubble, or on a
# card the donkey is holding, are holes within one component, so it cannot see
# them at all. That is how tiles 7 and 8 of the 2026-09-02 sheet shipped: one
# donkey saying "I'm out", one holding a card reading "Exit Block".
#
# enclosed_runs is the second detector. Same shape of test as the first — a run
# of similar-height marks on a shared baseline — read from the holes of the main
# component instead of from its neighbours.
print("\n=== lettering inside a bubble or on a held card ===")


def frame(marks, held):
    """A green donkey on the magenta key, with a white bubble or card attached."""
    img = np.zeros((600, 600, 3), np.uint8)
    img[:] = (255, 0, 255)
    cv2.circle(img, (300, 250), 150, (88, 152, 114), -1)
    cv2.rectangle(img, (215, 360), (385, 600), (88, 152, 114), -1)
    if held:
        cv2.rectangle(img, (395, 300), (560, 420), (245, 245, 245), -1)
        cv2.rectangle(img, (380, 340), (400, 370), (88, 152, 114), -1)   # the arm
        y0, x0, step = 345, 415, 34
    else:
        cv2.ellipse(img, (410, 140), (120, 70), 0, 0, 360, (245, 245, 245), -1)
        cv2.fillPoly(img, [np.array([[330, 175], [360, 200], [300, 215]])], (245, 245, 245))
        y0, x0, step = 125, 340, 34
    for k in range(marks):
        cv2.rectangle(img, (x0 + k * step, y0), (x0 + k * step + 16, y0 + 32), (25, 25, 25), -1)
    return img


from cutout import enclosed_runs, glyph_runs  # noqa: E402

for held in (False, True):
    what = "held card" if held else "speech bubble"
    for marks, expect in ((0, "accept"), (2, "accept"), (4, "reject")):
        got = "reject" if enclosed_runs(frame(marks, held)) else "accept"
        ok = "\u2713" if got == expect else "\u2717\u2717"
        if got != expect:
            FAILURES.append(f"enclosed_{marks}_{what.replace(' ', '_')}")
        print(f"  {ok} {what:14s} {marks} mark(s)   expected {expect:6s} got {got}")
# Two marks are two eyes, not a word. The whole reason assert_has_pupils can
# coexist with this gate is that a run needs three.

# ── every pose in the library, through both detectors ──────────────────────
#
# A gate that rejects real artwork is worse than no gate: it fails safe to the
# library pose, so a false positive is silent and permanent. The threshold was
# measured against all 194 poses before it landed, and this is the measurement,
# run again on every commit.
#
# Both backdrops, because the two are different pictures to a contrast detector:
# generation happens on the magenta key, which is what assert_no_text actually
# sees, and white is the worst case for a light-on-light mark.
LIB = pathlib.Path(__file__).resolve().parent.parent / "mascot" / "library"
poses = sorted(f for f in LIB.glob("*.png") if not f.name.startswith("_"))
print(f"\n=== {len(poses)} library poses, neither detector may fire ===")
if len(poses) < 190:
    FAILURES.append("library_sweep_found_nothing")
    print(f"  \u2717\u2717 only {len(poses)} poses found — the sweep is proving nothing")
for backdrop, bgr in (("magenta key", (255, 0, 255)), ("white", (255, 255, 255))):
    hits = []
    for f in poses:
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None or img.shape[2] != 4:
            continue
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        back = np.zeros_like(img[:, :, :3], np.float32)
        back[:] = bgr
        flat = (img[:, :, :3].astype(np.float32) * alpha + back * (1 - alpha)).astype(np.uint8)
        if enclosed_runs(flat):
            hits.append(f.stem)
    ok = "\u2713" if not hits else "\u2717\u2717"
    if hits:
        FAILURES.append(f"library_false_positive_on_{backdrop.replace(' ', '_')}")
    print(f"  {ok} on {backdrop:12s} {len(hits)} false reject(s)"
          + (f": {', '.join(hits[:6])}" if hits else ""))

print()
if FAILURES:
    raise SystemExit(f"FAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
print("all QA-gate cases passed")
