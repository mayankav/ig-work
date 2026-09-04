# Isolated image test — 4 September 2026

Purpose: check whether the reviewers can find the known extra leg when the suspect donkey is shown alone and the prompt does not supply an expected limb count. This is a diagnostic, not a model qualification or permission to post.

| Model | Full image | Lower-body view |
|---|---|---|
| Gemini 3.5 Flash | Reported three legs and described the bent rear leg | HTTP 503; no image assessment |
| Groq Qwen 3.8 27B | Reported two legs; missed one of the downward legs | HTTP 429; no image assessment |

Four HTTP requests were made through `llm.look_once`, with exact models, no fallback, and a four-request limit. Prompts, schema, model names, image hashes, answers and errors are in `results.json`. Existing quota accounting recorded the requests in `state/vendor_quotas.json`.

`body.jpg` is the full `tests/fixtures/rejected_art/extra_leg.png` fixture, with transparency composited onto the same gray background used by the existing reviewer. `lower.jpg` is the bottom-right 512-pixel cell extracted from the reconstructed earlier model sheet (sheet SHA256 `db4d7bc512d1456ebbc02c0c727ae90ed3829dafec90217cbe31e4c5d41b0289`), then encoded as JPEG at quality 90. The scene and limbs were not changed.

Gemini can detect this defect in at least one isolated-image test. Groq did not report the correct count even on the isolated full image. The prompt, resolution and image layout changed together, so this test cannot identify which change helped Gemini. One answer does not establish reliability. Service errors say nothing about visual accuracy.

Next: test Gemini's isolated-image approach repeatedly against both defective and correct artwork. Measure missed defects and false rejections before changing the production reviewer. Keep the current posting block until the required checks pass.
