# Free image model screen — 4 September 2026

Three generation requests were sent. No model was installed for production, no artwork was approved, and no post was attempted.

| Model | Result |
|---|---|
| Gemini Robotics ER 2 Preview | Detected the extra leg, then detected the blank eye. On the second image it also reported uncertainty about a yellow hoof, so the existing uncertainty rule stopped the screen. Not qualified. |
| Gemini 2.5 Pro | HTTP 404: Google says this model is no longer available to new users. No image judgment was returned. |

Both model IDs appeared in the model-list response for the configured Google key and supported `generateContent`. Listing a model therefore did not prove that the account could call it. Google's pricing page listed free API tiers for both; no billing settings were changed. The paid successor suggested by the 404 response was not called.

## Test method

The planned screen was: extra leg, blank profile eye, malformed eyelids, kneeling, two donkeys (`far_apart`), and lying down (`on_back`). It used the same neutral single-image prompt and schema as the earlier test, the full original frame on a gray background, temperature 0.2, and an 8192-token output limit. No expected count or fixture label was sent to the model.

The models were called through a separate offline script, with the existing key resolver, HTTP transport and quota accounting. Production model lists were not changed. The screen allowed at most 12 generation requests, spaced at least 40 seconds apart, with no retry or model fallback. A missed fault, uncertainty, invalid answer, service error, or rejected correct image stopped that model's screen.

`results.json` holds exact prompts, schema, source-code hashes, model responses (including model version and token usage), image hashes and errors. The matching original PNG and sent JPEG files are retained beside it. The source script is `scripts/probe_free_image_models.py`.

## Interpretation

Robotics ER 2 correctly reported both known defects it saw. The second result is an appropriate reason to reject defective artwork, but our current test stops on any uncertainty even when the same answer identifies the expected defect. This is a test-policy issue to review, not evidence that the model missed the blank eye. It has not yet been tested on malformed eyelids or the correct images and cannot replace the current reviewer.

Before spending more requests, decide whether qualification should count a correctly identified defective image as a successful rejection when unrelated uncertainty is also present. Any such change must still reject that image, must not approve uncertain correct images, and must not let uncertainty alone satisfy a known-defect test. No such rule change was made here.

Sources checked: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [Robotics ER 2 model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-robotics-er-2-preview), the live Google model list and the saved generation responses.
