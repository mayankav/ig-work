# Cloudflare image comparison — 4 September 2026

Three requests were made. No production settings, image eligibility rules or approvals were changed.

| Model | Known extra-leg image | Correct kneeling image |
|---|---|---|
| Moondream 3.1 | No answer within the existing 45-second HTTP read limit | Not requested after the timeout |
| Gemma 4 26B A4B | Reported two legs, no faults and no uncertainty: missed the defect | No answer within the 45-second HTTP read limit |

Neither model qualifies from this test. A timeout provides no evidence about visual accuracy. It does not prove that the model or service is generally unavailable. Gemma's completed answer does provide evidence that it missed this known defect.

Earlier Robotics ER 2 results detected the extra leg and blank eye; its second answer also expressed uncertainty about another feature. Those are historical observations, not a full repeated comparison: Robotics did not see the kneeling image, and its API received the schema as a structured-output parameter while this Cloudflare comparison included the schema in the prompt.

## Method and limits

Both Cloudflare models received the same full-size JPEG, neutral limb-tracing instructions and JSON schema, temperature 0.2, and an 8192-token output limit. Moondream used its native query API with reasoning enabled; Gemma used its documented message API. These are diagnostic calls, separate from the production model allowlist. The experiment reports detected faults, uncertainty, malformed responses and service errors separately. Continuing to the correct image after Gemma's missed defect was solely for comparison; it did not qualify or approve anything.

The trial had a four-request maximum and no retries. Each model stopped on its first service error. The existing shared Cloudflare ledger reserved the full documented input context plus maximum output at published rates before each request: 1,639 neurons for Moondream and 2,551 for Gemma. Total reserved: 6,741 neurons. Gemma's completed request reported 72.63 neurons, but the reservation was not refunded, following the existing rule. Timeouts also retain their reservations. This ledger covers recorded repository usage, not unknown use by other applications.

`results.json` saves all replies, errors, code hashes and image hashes. Original PNGs and sent JPEGs are included. `current_protocol_usable` means the answer is parseable and has no declared uncertainty; it is NOT approval. `expected_defect_detected: false` is the decisive result for Gemma's extra-leg answer.

## Next decision

Do not replace the production reviewer with Gemma based on these results. Moondream remains unassessed; a future bounded diagnostic with a longer response limit could distinguish slow processing from persistent failure. The current timeout must not be described as a missed defect. No automatic retry or future task has been scheduled.
