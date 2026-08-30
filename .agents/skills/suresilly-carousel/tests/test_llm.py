#!/usr/bin/env python3
"""
Provider-chain regression. No network is touched.

Gemini's free tier caps per model per day, so the five model ids are five
independent buckets and the chain walks them before falling through to Groq and
Cloudflare. That fallback works and has never been what stopped a run.

What it did cost was time. Every logical call restarted at the first bucket, and
the calls are paced four seconds apart, so a run that had already spent Gemini
paid twenty seconds per call to be told five times what it already knew. One
build spent about a hundred seconds that way.

The distinction that makes this safe is per-minute against per-day. A minute
limit clears inside a run and must still be retried; a day limit does not clear
until midnight Pacific and there is nothing to be gained by asking again. Only
the quotaId in the error body tells them apart — the Retry-After hint does not,
because a per-day violation can arrive with an eleven second hint.
"""
import contextlib
import io
import os
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import llm  # noqa: E402

PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
PER_DAY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"


def drive(quota: str, logical_calls: int = 3) -> tuple[list[str], set[str]]:
    """Make N Gemini calls against a server that only ever says 429."""
    asked: list[str] = []

    def fake_urlopen(request, timeout=None):
        asked.append(request.full_url.split("/models/")[1].split(":")[0])
        body = ('{"error":{"details":[{"violations":[{"quotaId":"%s"}]}]}}' % quota).encode()
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {},
                                     io.BytesIO(body))

    real_urlopen, real_pace, real_key = urllib.request.urlopen, llm._pace, llm.resolve_key
    llm.urllib.request.urlopen = fake_urlopen
    llm._pace = lambda provider: None      # count requests, not seconds
    llm.resolve_key = lambda name: "test-key"
    llm._SPENT.clear()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(logical_calls):
                try:
                    llm.call_gemini("system", "user", 0.0)
                except llm.RateLimited:
                    pass
        return asked, set(llm._SPENT)
    finally:
        llm.urllib.request.urlopen = real_urlopen
        llm._pace, llm.resolve_key = real_pace, real_key
        llm._SPENT.clear()


def run() -> int:
    failures = []
    models = len(llm.GEMINI_MODELS)

    # A minute limit clears while the run is still going, so every bucket is
    # still worth asking on the next call.
    asked, spent = drive(PER_MINUTE)
    if len(asked) != models * 3:
        failures.append(f"MINUTE stopped retrying a limit that clears: {len(asked)} requests")
    if spent:
        failures.append(f"MINUTE gave up on a bucket that will come back: {sorted(spent)}")

    # A day limit does not clear. One pass to learn it, then nothing.
    asked, spent = drive(PER_DAY)
    if len(asked) != models:
        failures.append(f"DAY kept asking buckets it knew were empty: {len(asked)} requests, "
                        f"expected {models}")
    if spent != set(llm.GEMINI_MODELS):
        failures.append(f"DAY did not record every empty bucket: {sorted(spent)}")

    # The memo must not swallow the failure. The caller still has to hear a
    # rate limit so it can fall through to Groq and Cloudflare, which is the
    # whole reason a second and third vendor are configured.
    real_pace, real_key = llm._pace, llm.resolve_key
    llm._pace, llm.resolve_key = (lambda p: None), (lambda n: "test-key")
    llm._SPENT.update(llm.GEMINI_MODELS)
    try:
        llm.call_gemini("system", "user", 0.0)
        failures.append("EXHAUSTED returned instead of raising, so no fallback would happen")
    except llm.RateLimited as limited:
        if not limited.daily:
            failures.append("EXHAUSTED did not report itself as a daily limit")
    except Exception as other:                       # noqa: BLE001
        failures.append(f"EXHAUSTED raised {type(other).__name__}, which is not retryable")
    finally:
        llm._SPENT.clear()
        llm._pace, llm.resolve_key = real_pace, real_key

    # Reading the quota out of the body is the only way the two are told apart.
    if llm.RateLimited("x", 30, PER_DAY).daily is not True:
        failures.append("QUOTA a per-day violation did not read as daily")
    if llm.RateLimited("x", 30, PER_MINUTE).daily is not False:
        failures.append("QUOTA a per-minute violation read as daily")
    if llm.RateLimited("x", 30).daily is not False:
        failures.append("QUOTA a limit with no quota id was assumed to be daily")

    # The chain can be pinned to one vendor, which is how the fallback gets
    # proven instead of assumed. Checked on the selection itself, because
    # calling ask() here would put a live request in a test suite.
    real_env = os.environ.get("SS_PROVIDERS")
    try:
        for pin, expected, note in [
            ("cloudflare", ["cloudflare"], "one vendor"),
            ("groq, cloudflare", ["groq", "cloudflare"], "two vendors, spaces ignored"),
            ("CLOUDFLARE", ["cloudflare"], "case ignored"),
            ("", ["gemini", "groq", "cloudflare"], "unset means the whole chain"),
            # A typo must never quietly disable the fallback.
            ("nonsense", ["gemini", "groq", "cloudflare"], "an unknown name changes nothing"),
        ]:
            os.environ["SS_PROVIDERS"] = pin
            got = [name for name, _ in llm.chain()]
            if got != expected:
                failures.append(f"PIN {note}: SS_PROVIDERS={pin!r} gave {got}")
    finally:
        os.environ.pop("SS_PROVIDERS", None)
        if real_env is not None:
            os.environ["SS_PROVIDERS"] = real_env

    total = 14
    if failures:
        print(f"llm: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"llm: {total}/{total} passed (minute limits retried, day limits remembered, "
          f"exhaustion still falls through, chain can be pinned to one vendor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
