# Visible-parts review — 4 September 2026

The experimental single-image protocol is now `single-visible-parts-2`.

- Inspect fully visible and partially visible parts. Describe only exposed shapes and connections.
- Do not infer, count or analyse hidden parts. Stop tracing at the occluding object.
- Count each visible or partially visible limb once per character, not each exposed fragment.
- Occlusion by itself is neither a defect nor a reason for uncertainty.
- A count alone cannot establish an extra limb. Each fault requires a location and visible evidence.
- Uncertainty concerns an ambiguous visible shape or connection, not unseen anatomy or general confidence.

The offline parser records fault codes, uncertainty and disposition separately.
A reported fault rejects the image even when another visible detail is unresolved.
An unresolved answer without a fault still cannot establish usable evidence.
A known-defect case must identify the expected defect; uncertainty alone does not count.
The separate control must report the extra limb with visible evidence; a count alone does not count.

This version changes the prompt, schema and code contract. Prior answers remain saved as original evidence and cannot qualify this version. No historical results have been rewritten.

This is an experimental check, not a production approval path. The production grouped review and pixel checks are unchanged. Prompt instructions and required evidence fields do not prove that a model followed the instructions; image-based comparison is still required.
