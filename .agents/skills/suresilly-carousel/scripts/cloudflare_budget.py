"""Conservative per-request reservations for the two configured Llama models.

Rates and hosted context limits checked 2026-09-04:
https://developers.cloudflare.com/workers-ai/platform/pricing/
https://developers.cloudflare.com/workers-ai/models/llama-3.3-70b-instruct-fp8-fast/
https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/
Reserve the complete input context and requested maximum output. This avoids
guessing image token counts. Missing/cheap billing headers never refund usage.
This ledger cannot account for other applications using the same account.
"""
import math

# context tokens, neurons per million input tokens, per million output tokens
LIMITS = {
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": (24000, 26668, 204805),
    "@cf/meta/llama-3.2-11b-vision-instruct": (128000, 4410, 61493),
}
TEXT_OUTPUT = 4096
VISION_OUTPUT = 1024


def reservation(model: str, max_tokens: int) -> int:
    if model not in LIMITS:
        raise ValueError("Cloudflare model has no checked spending bound")
    context, input_rate, output_rate = LIMITS[model]
    if type(max_tokens) is not int or not 1 <= max_tokens <= context:
        raise ValueError("Cloudflare output limit is invalid")
    return math.ceil((context * input_rate + max_tokens * output_rate) / 1_000_000)
