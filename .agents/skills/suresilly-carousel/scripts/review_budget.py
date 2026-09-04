"""Decide whether optional generation has known review-request headroom.

This is not a provider-side reservation. Other account users can still spend
quota afterward, so failed reviews continue to reject the generated group.
Cloudflare has a separate shared-neuron reservation. A local request tally is
not evidence of a remaining allowance and must never be treated as one.
"""
from datetime import datetime, timezone
import math

import quotas

MAX_AGE_SECONDS = 60


def fault(provider: str, model: str, requests: int, *, now=None) -> str | None:
    if type(requests) is not int or not 1 <= requests <= 3:
        return "image review request budget is invalid"
    if provider == "cloudflare":
        return None  # fresh_poses protects shared neurons before each image
    if provider not in ("gemini", "groq"):
        return "image reviewer has no known quota policy"
    record = quotas.read().get(provider)
    if not isinstance(record, dict) or record.get("source") != "reported":
        return "image review allowance is unknown; use checked library art"
    if record.get("model") != model:
        return "the quota reading belongs to a different image model"
    try:
        seen = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        if seen.tzinfo is None:
            raise ValueError("missing zone")
        age = ((now or datetime.now(timezone.utc)) - seen).total_seconds()
        dimension = record["requests"]
        remaining, limit = dimension["remaining"], dimension["limit"]
        if not all(type(v) in (int, float) and math.isfinite(v) for v in (remaining, limit)):
            raise ValueError("invalid count")
        if not 0 <= remaining <= limit or limit <= 0:
            raise ValueError("invalid range")
    except (KeyError, TypeError, ValueError, AttributeError):
        return "image review quota reading is incomplete or invalid"
    if not 0 <= age <= MAX_AGE_SECONDS:
        return "image review quota reading is stale or future-dated"
    if remaining < requests:
        return f"image review needs {requests} requests; only {remaining:g} are reported left"
    return None
