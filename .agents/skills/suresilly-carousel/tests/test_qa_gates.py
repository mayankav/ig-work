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


print()
if FAILURES:
    raise SystemExit(f"FAILED: {len(FAILURES)} case(s): {', '.join(FAILURES)}")
print("all QA-gate cases passed")
