# Image review: proof required before release

Checked on 4 September 2026. No image reviewer is qualified yet.

## Current result

The local engine refuses all unchecked artwork, including library fallbacks,
imports and generation references. A key, a valid JSON reply, or a saved
`qualified: true` flag is not proof. It also checks exact artwork evidence at
render and publication time. A run with fewer than nine checked library images
stops before generation and does not offer retry.

Live attempts are saved under
`.agents/skills/suresilly-carousel/references/image_review_qualifications/`.
The tested Groq and Gemini candidates missed the real extra-leg control. One
Gemini attempt also hit the daily free limit. No paid service was enabled.

The old Groq Scout ID is no longer returned by the authenticated models API.
The current candidate is `qwen/qwen3.6-27b`, listed with image input in
[Groq's model documentation](https://console.groq.com/docs/model/qwen/qwen3.6-27b).
Availability does not prove quality. Groq lists it as a preview model.

Gemini 3 inspection uses per-image ultra-high resolution, supported by
[Google's media-resolution API](https://ai.google.dev/gemini-api/docs/generate-content/media-resolution).
The tested model still missed the control at this setting.

## What a qualification run must prove

1. Inspect 20 body-and-eye-clean poses and all three supplied defects, three times.
2. Use the same sheet, prompt, parser and exact model as production.
3. Catch every serious defect and every inserted control.
4. Refuse no more than one clean pose out of 20 in each trial.
5. Preserve replies and sheet hashes. Failed or incomplete runs cannot qualify.

The clean set includes closed eyes, a wink, one eye partly hidden by a hand,
glasses, covered limbs, tilted heads, seated and lying poses, props, and
two-character scenes. It tests anatomy, not every brand rule. A valid true
single-visible-eye profile still needs to be added before the fixed set fully
covers the release plan; the current library has no confirmed example of that
specific pose.

## Run a bounded test — engineering work, not an owner task

From the project folder:

```sh
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/image_qualification.py \
  --provider gemini \
  --model gemini-3.5-flash \
  --output .agents/skills/suresilly-carousel/references/image_review_qualifications/NEW-RUN-NAME.json \
  --max-requests 24
```

Use a new output name; the tool refuses to overwrite earlier evidence.
It waits at least 40 seconds between requests and stops at the first missed
control, known serious defect, or failed request. A full run takes at least
16 minutes. It never changes models or retries inside a request.

The result is recalculated when production selects a reviewer. A change to
the source code, dependency versions, test images, or inspection pixels
invalidates old proof. Proof also expires after 30 days.

## Remaining release work

Do not mistake the pixel audit for a complete artwork audit. Six saved files
failed pixel checks and are now excluded from local selection. The other files
still need body-review evidence linked to their exact bytes. Imports, selected
fallback art and generation references now require that same evidence through
`art_eligibility.py`. No model is qualified and no library image currently meets
that full requirement. The wiring is tested; actual reviewer quality is not
established. The tests use temporary simulated model replies, not live approval.

Keep `SS_HALT = 1` until the complete release checks pass.
