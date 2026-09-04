# Library recovery trial — 4 September 2026

Status: stopped at Step 3. The image checker is implemented for offline tests only. It is not connected to library eligibility, rendering, publishing or new image generation.

## Original failed post

Slot: `2026-09-03_2000`. Latest saved attempt: [33827677228](https://github.com/mayankav/ig-work/actions/runs/33827677228).

The saved result reports zero library images with current checks, no generation request, no deck name and no publication. GitHub lists only the run-evidence and message-delivery artifacts, with no recovery-deck artifact. `failed-slot.json` preserves the original record. No slot was cleared or retried by this trial.

## Live result

Gemini 3.5 Flash received the isolated full image of the known correct `kneeling` pose. It returned two arms and two legs, with no reported artwork faults. However, it also stated that it could not confidently distinguish the front limbs as arms versus legs, and that one hoof was hidden.

The agreed rule stops on uncertainty. The test therefore ended as **incomplete after one HTTP request**. The control request was not sent. This is not a service error, a missed extra-leg control, or proof that the whole image set passed or failed. There is not enough evidence to qualify this model.

`results.json` contains the exact questions, schema, model response, source and JPEG hashes, code contract, status and error. Matching PNG and JPEG files are saved beside it. The result also lists incomplete coverage; the missing-control entry reflects the early stop, not a second model error.

## Implemented

- Separate single-image protocol with neutral limb counting, per-character descriptions, and face/artwork fault reporting.
- A separate extra-leg control request for each candidate.
- Fixed shuffled order over 20 correct and three faulty images, repeated three times.
- A hard maximum of 138 HTTP requests with at least 40 seconds between requests; no retry or model fallback.
- Saved answers and images, repeatable evidence checks, and rejection of stale or changed evidence.
- Unit tests for controls, uncertainty, hidden limbs, multiple characters, incorrect counts, changed evidence, service failures and request limits. Tests use temporary evidence and no live model requests.

## Deferred by the required stop

Steps 4–7 require the complete model test to pass. No production approval format, workflow switch, library approvals, deployment, recovery request or Instagram post was made. Existing production gates remain unchanged. Code and trial evidence are local and have not been pushed.

Before another live trial, the next design review should examine why the model treated an ordinary hidden hoof as uncertainty despite the prompt explicitly allowing hidden limbs. Do not silently ignore uncertainty, count this run as a pass, or repeat the same request unchanged.
