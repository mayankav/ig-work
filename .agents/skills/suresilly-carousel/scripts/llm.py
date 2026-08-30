#!/usr/bin/env python3
"""
llm.py — talking to a model, and never trusting what comes back.

Two providers, in order: Gemini writes, Groq stands in when Gemini cannot. They
are different companies on purpose, so a bad afternoon at one is not a bad
afternoon for the pipeline. When both fail we post nothing, because the
alternative — a pre-written fallback — is the recombination this rebuild removed.

Everything here fails closed. A timeout, a malformed body, a reply that does not
match its schema, a refusal: all of them are the same answer, which is no. A
model is never given the benefit of the doubt, because in an unattended pipeline
nobody is watching to catch the one time it was wrong.

Schema checking is done here rather than trusting the provider's structured
output, and it is deliberately a small hand-written validator rather than a
dependency. The subset it covers is the subset our prompts use; anything outside
that is rejected rather than waved through, so a schema feature nobody has
tested cannot quietly become an escape hatch.

Standard library only. This runs twice a day for years and should not be able to
break because something upstream changed its packaging.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLOUDFLARE_URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
CLOUDFLARE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

# Gemini's free quota is per project AND per model, so every model id is its own
# bucket. Listing several is the cheapest capacity we have: nine calls spread
# over five models is nine calls against five separate allowances.
#
# This is capacity, never independence. All of them are Google, and none may be
# used to check another's work. Cross-vendor review is a separate rule and it
# still holds.
GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
)
GROQ_MODEL = "openai/gpt-oss-120b"

# Gemini models whose DAILY quota is gone. Per-model and per-day, so one being
# empty says nothing about the next; per-minute limits are not recorded here
# because they clear inside a run. Process-local on purpose: it is a memo for
# this run, not a fact about tomorrow, and the day rolls over at midnight
# Pacific with nothing to tell us.
_SPENT: set[str] = set()

TIMEOUT = 45
RETRIES = 1

# A rate limit is not a failure, it is a queue. The free tiers cap by the minute,
# so the two-second pause that suits a transient error is useless here — it has
# to be long enough to cross into the next window. The provider's own
# Retry-After is used when it sends one.
RATE_LIMIT_PAUSE = 25
RETRY_PAUSE = 2

# A minimum gap between calls to the same provider. Nine requests fired back to
# back is what produces a burst 429, whichever model each one lands on: a
# per-minute quota does not care that the work was spread across buckets if it
# all arrived in the same ten seconds. Four seconds costs about half a minute
# across a whole run and removes the burst entirely.
MIN_GAP_SECONDS = 4.0
_last_call: dict[str, float] = {}


def _pace(provider: str) -> None:
    """Wait if the last REQUEST to this provider was too recent.

    On the request, not on the logical call. Gemini fires up to five requests
    inside one call as it walks its model buckets, and pacing the call left
    those five arriving inside a second, which is the burst this exists to
    prevent.
    """
    since = time.time() - _last_call.get(provider, 0.0)
    if since < MIN_GAP_SECONDS:
        time.sleep(MIN_GAP_SECONDS - since)
    _last_call[provider] = time.time()


class ModelRefused(Exception):
    """No usable answer. The reason is written for whoever reads the alert."""


class SchemaMismatch(ModelRefused):
    """The reply did not match its schema. Worth one corrected retry, unlike a
    refusal or an outage."""


class RateLimited(ModelRefused):
    """The provider is throttling. Worth waiting for, unlike everything else."""

    def __init__(self, message: str, wait: int, quota: str = ""):
        super().__init__(message)
        self.wait = wait
        # Which quota, verbatim from the body. A per-minute limit clears inside
        # a run and a per-day one does not, and the two are worth opposite
        # reactions: wait for the first, stop asking for the second.
        self.quota = quota

    @property
    def daily(self) -> bool:
        return "PerDay" in self.quota


# ─────────────────────────── keys ────────────────────────────

def resolve_key(name: str) -> str | None:
    """Find a key without it having to be exported.

    Order is environment, then the two config files this repo has historically
    kept keys in. CI sets the environment; a laptop usually has one of the files.
    """
    from_env = os.environ.get(name)
    if from_env:
        return from_env.strip()

    for path in (Path.home() / ".claude.json", Path.home() / ".gemini/config/mcp_config.json"):
        if not path.is_file():
            continue
        try:
            found = _find_key(json.loads(path.read_text(encoding="utf-8")), name)
        except (json.JSONDecodeError, OSError):
            continue
        if found:
            return found.strip()
    return None


def _find_key(blob, name: str) -> str | None:
    if isinstance(blob, dict):
        for key, value in blob.items():
            if key == name and isinstance(value, str) and value:
                return value
            found = _find_key(value, name)
            if found:
                return found
    elif isinstance(blob, list):
        for item in blob:
            found = _find_key(item, name)
            if found:
                return found
    return None


# ─────────────────────────── schema ────────────────────────────

def validate(value, schema: dict, where: str = "response") -> list[str]:
    """Check a value against the subset of JSON Schema our prompts use.

    Returns every problem rather than the first, so a malformed reply can be
    logged once and understood without a second call.
    """
    problems: list[str] = []
    expected = schema.get("type")

    if "const" in schema:
        if value != schema["const"]:
            problems.append(f"{where}: expected {schema['const']!r}, got {value!r}")
        return problems
    if "enum" in schema:
        if value not in schema["enum"]:
            problems.append(f"{where}: {value!r} is not one of {schema['enum']}")
        return problems

    if expected == "object":
        if not isinstance(value, dict):
            return [f"{where}: expected an object, got {type(value).__name__}"]
        for field in schema.get("required", []):
            if field not in value:
                problems.append(f"{where}: missing {field}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for field in value:
                if field not in properties:
                    problems.append(f"{where}: unexpected field {field}")
        for field, subschema in properties.items():
            if field in value:
                problems.extend(validate(value[field], subschema, f"{where}.{field}"))

    elif expected == "array":
        if not isinstance(value, list):
            return [f"{where}: expected a list, got {type(value).__name__}"]
        if "minItems" in schema and len(value) < schema["minItems"]:
            problems.append(f"{where}: has {len(value)} items, needs at least {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{where}: has {len(value)} items, allows at most {schema['maxItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                problems.extend(validate(item, schema["items"], f"{where}[{i}]"))

    elif expected == "string":
        if not isinstance(value, str):
            return [f"{where}: expected text, got {type(value).__name__}"]
        if "minLength" in schema and len(value) < schema["minLength"]:
            problems.append(f"{where}: {len(value)} characters, needs at least {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            problems.append(f"{where}: {len(value)} characters, allows at most {schema['maxLength']}")

    elif expected in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return [f"{where}: expected a number, got {type(value).__name__}"]
        if expected == "integer" and not float(value).is_integer():
            problems.append(f"{where}: expected a whole number")
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{where}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{where}: {value} is above {schema['maximum']}")

    elif expected == "boolean":
        if not isinstance(value, bool):
            problems.append(f"{where}: expected true or false, got {type(value).__name__}")

    return problems


def extract_json(text: str) -> dict:
    """Pull the object out of a reply, tolerating a fenced block around it.

    Models wrap JSON in markdown often enough that refusing it would cost real
    calls, but nothing beyond the outermost braces is read.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ModelRefused("the reply contained no JSON object")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ModelRefused(f"the reply was not valid JSON: {exc}") from exc


# ─────────────────────────── providers ────────────────────────────

# Gemini accepts a subset of OpenAPI schema, not JSON Schema. Sending a key it
# does not know is a 400, so the schema is translated on the way out. Our own
# validator still runs on the way back: the provider enforcing a shape is a
# convenience, never the check.
_GEMINI_KEYS = {"type", "properties", "required", "items", "enum", "description",
                "minItems", "maxItems", "nullable"}


def _limit_note(schema: dict) -> str:
    """Turn the limits Gemini's dialect drops into words it will read.

    minLength, maxLength and minItems are not part of the OpenAPI subset Gemini
    accepts, so they were being stripped on the way out and enforced on the way
    back. The model was refused for breaking a rule nobody had told it.
    """
    bits = []
    if "maxLength" in schema:
        bits.append(f"at most {schema['maxLength']} characters")
    if "minLength" in schema:
        bits.append(f"at least {schema['minLength']} characters")
    if "minItems" in schema:
        bits.append(f"at least {schema['minItems']} items")
    return ", ".join(bits)


def _gemini_schema(schema: dict) -> dict:
    out = {}
    for key, value in schema.items():
        if key == "const":
            out["enum"] = [value]
        elif key == "properties":
            out["properties"] = {k: _gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out["items"] = _gemini_schema(value)
        elif key in _GEMINI_KEYS:
            out[key] = value
    note = _limit_note(schema)
    if note:
        out["description"] = f"{out.get('description', '')} ({note})".strip()
    if out.get("type") == "string" and "enum" in out:
        out["format"] = "enum"
    return out


# Google does not send a Retry-After header on a 429. It puts the wait in the
# error message as "Please retry in 54.6s", so that is where we look before
# falling back to a fixed pause.
_RETRY_HINT = re.compile(r"retry in ([\d.]+)s", re.I)


_QUOTA_ID = re.compile(r'"quotaId":\s*"([^"]+)"')


def _retry_after(exc: urllib.error.HTTPError) -> tuple[int, str]:
    """How long to wait, and which quota was hit."""
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.strip().isdigit():
        return int(header), ""
    body = ""
    try:
        body = exc.read().decode("utf-8", "replace")
    except Exception:
        pass
    # Which quota was hit is in quotaId, and only there. The retry hint does not
    # tell you: a per-day violation can arrive with an eleven second hint, so
    # tuning against the hint tunes against the wrong number.
    quota = _QUOTA_ID.search(body)
    name = quota.group(1) if quota else ""
    if name:
        print(f"    quota hit: {name}")
    match = _RETRY_HINT.search(body)
    if match:
        # A second of slack, so we are not racing the edge of the window.
        return min(90, int(float(match.group(1))) + 1), name
    return RATE_LIMIT_PAUSE, name


def _post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode()
    # A real User-Agent is not politeness. Groq sits behind Cloudflare, which
    # blocks the default "Python-urllib" with a 403 that looks exactly like an
    # auth failure and cost an hour to tell apart from one.
    request = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "suresilly-carousel/3.0 (+https://instagram.com/suresilly)",
        **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 503):
            wait, quota = _retry_after(exc)
            raise RateLimited(f"HTTP {exc.code}", wait, quota) from exc
        # Everything else carries the provider's own complaint in the body, and
        # without it a 400 is undiagnosable from a CI log.
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        raise ModelRefused(f"HTTP {exc.code}: {detail}") from exc


def call_gemini(system: str, user: str, temperature: float, schema: dict | None = None) -> str:
    key = resolve_key("GEMINI_API_KEY") or resolve_key("GOOGLE_API_KEY")
    if not key:
        raise ModelRefused("no Gemini key")
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    if schema:
        payload["generationConfig"]["responseSchema"] = _gemini_schema(schema)
    trouble = []
    live = [m for m in GEMINI_MODELS if m not in _SPENT]
    if not live:
        # Every bucket is gone for the day. Asking again costs four seconds of
        # pacing each and cannot succeed, and it was costing about twenty
        # seconds on every call in a run that had already exhausted Gemini.
        raise RateLimited("every Gemini model is out of daily quota", RATE_LIMIT_PAUSE,
                          "GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    for model in live:
        _pace("gemini")
        try:
            data = _post(GEMINI_URL.format(model=model), payload, {"x-goog-api-key": key})
            break
        except RateLimited as limited:
            if limited.daily:
                _SPENT.add(model)
            trouble.append(f"{model} {limited}")
        except ModelRefused as refused:
            # Any refusal moves to the next bucket, not just a rate limit. One
            # model rejecting a schema or disappearing should cost us that model,
            # not the whole call, and the earlier version aborted on both.
            trouble.append(f"{model} {refused}")
    else:
        raise RateLimited("; ".join(trouble)[:300], RATE_LIMIT_PAUSE)

    candidates = data.get("candidates") or []
    if not candidates:
        # An empty candidate list is a safety block, not an outage. It reads as
        # success at the HTTP layer, so it has to be caught explicitly.
        raise ModelRefused(f"Gemini returned nothing: {data.get('promptFeedback', 'no reason given')}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        raise ModelRefused("Gemini returned an empty answer")
    return text


def _field_note(schema: dict | None) -> str:
    """A compact statement of what the reply must contain.

    The whole nested schema used to be dumped into the prompt, which is large
    and is the most likely thing a 400 Bad Request is objecting to. The model
    only needs to know the field names; our own validator does the checking.
    """
    if not schema:
        return ""
    required = schema.get("required") or list((schema.get("properties") or {}))
    if not required:
        return ""
    return ("\n\nReturn one JSON object with exactly these top level fields: "
            + ", ".join(required) + ".")


def _strict(schema: dict) -> dict:
    """Make a schema acceptable to constrained decoding.

    Strict mode wants every property listed as required and no extras, which our
    schemas nearly satisfy already. Anything optional becomes required, because
    a field we would have accepted as missing is one the model may as well fill.
    """
    out = dict(schema)
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
        out["properties"] = {k: _strict(v) for k, v in out["properties"].items()}
    elif out.get("type") == "array" and "items" in out:
        out["items"] = _strict(out["items"])
    return out


def _groq_format(schema: dict | None, strict: bool = True) -> dict:
    if not schema:
        return {"type": "text"}
    if not strict:
        return {"type": "json_object"}
    return {"type": "json_schema",
            "json_schema": {"name": "reply", "strict": True, "schema": _strict(schema)}}


def call_groq(system: str, user: str, temperature: float, schema: dict | None = None) -> str:
    key = resolve_key("GROQ_API_KEY")
    if not key:
        raise ModelRefused("no Groq key")
    _pace("groq")
    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        # json_object generates freely and validates afterwards, returning 400
        # when the model produced broken JSON. That is what our 400 was: not a
        # quota error, which is always 429. Constrained decoding cannot produce
        # invalid JSON in the first place, so it is tried first.
        "response_format": _groq_format(schema),
        "messages": [
            {"role": "system", "content": system + _field_note(schema)},
            {"role": "user", "content": user},
        ],
    }
    try:
        data = _post(GROQ_URL, payload, {"Authorization": f"Bearer {key}"})
    except ModelRefused as refused:
        # Strict mode has limited model support. If it is refused, fall back to
        # the looser mode rather than losing the provider entirely.
        if "400" not in str(refused):
            raise
        payload["response_format"] = _groq_format(schema, strict=False)
        data = _post(GROQ_URL, payload, {"Authorization": f"Bearer {key}"})

    choices = data.get("choices") or []
    if not choices:
        raise ModelRefused("Groq returned no choices")
    text = choices[0].get("message", {}).get("content", "")
    if not text.strip():
        raise ModelRefused("Groq returned an empty answer")
    return text


def call_cloudflare(system: str, user: str, temperature: float,
                    schema: dict | None = None) -> str:
    """Workers AI, the third vendor.

    Two vendors is one short. The critic may not be whoever wrote the deck, so
    if the writer falls back to the second vendor there is nothing left to
    review it with and the run ends having done all the work. A third means any
    two can always cover both roles.

    It also does not train on what it is sent, unlike the Gemini free tier, so
    it is the one to prefer when that matters.
    """
    account = resolve_key("CLOUDFLARE_ACCOUNT_ID")
    token = resolve_key("CLOUDFLARE_API_TOKEN")
    if not (account and token):
        raise ModelRefused("no Cloudflare credentials")

    _pace("cloudflare")
    payload = {
        "messages": [{"role": "system", "content": system + _field_note(schema)},
                     {"role": "user", "content": user}],
        "temperature": temperature,
    }
    if schema:
        payload["response_format"] = {
            "type": "json_schema", "json_schema": _strict(schema)}

    data = _post(CLOUDFLARE_URL.format(account=account, model=CLOUDFLARE_MODEL),
                 payload, {"Authorization": f"Bearer {token}"})
    result = data.get("result") or {}
    text = result.get("response")
    if isinstance(text, dict):
        # Structured mode hands back the object already parsed.
        return json.dumps(text)
    if not (text or "").strip():
        raise ModelRefused(f"Cloudflare returned nothing: {str(data)[:160]}")
    return text


# Order matters only as a preference. What matters for correctness is that
# there are three, so the critic always has a vendor that did not write the deck.
PROVIDERS = (("gemini", call_gemini), ("groq", call_groq), ("cloudflare", call_cloudflare))


def chain(providers=PROVIDERS):
    """The vendors to try, in order, honouring SS_PROVIDERS.

    SS_PROVIDERS pins the chain to the vendors it names, comma separated. It
    exists so the fallback can be PROVEN rather than assumed: Gemini has written
    every deck that ever passed the gates, and a chain that keeps a run alive is
    not the same as one that finishes it. Set it to "cloudflare" for one run and
    you find out for certain.

    A name that matches nothing leaves the chain alone. A typo in an environment
    variable must not quietly turn the fallback off.
    """
    wanted = {n.strip().lower() for n in os.environ.get("SS_PROVIDERS", "").split(",") if n.strip()}
    if not wanted:
        return providers
    return tuple(p for p in providers if p[0] in wanted) or providers


def ask(system: str, user: str, schema: dict, temperature: float = 0.6,
        providers=PROVIDERS) -> tuple[dict, str]:
    """Ask, validate, and return the answer with the name of who gave it.

    Each provider gets one retry, then we move on. When every provider is
    exhausted the caller gets ModelRefused and the run ends without a post.
    """
    providers = chain(providers)
    trouble: list[str] = []
    original_user = user
    for name, call in providers:
        user = original_user
        pause = RETRY_PAUSE
        for attempt in range(RETRIES + 1):
            if attempt:
                time.sleep(pause)
            try:
                reply = call(system, user, temperature, schema)
                answer = extract_json(reply)
                problems = validate(answer, schema)
                if problems:
                    raise SchemaMismatch("; ".join(problems[:4]))
                return answer, name
            except RateLimited as limited:
                # No retry here on purpose. A per-minute quota does not clear
                # inside a run, and the old behaviour turned one logical call
                # into as many as six requests: two models, twice each, then the
                # fallback twice. Six calls a run became thirty six, which is
                # how the free tier was being exhausted mid-job.
                trouble.append(f"{name}: {limited}")
                break
            except SchemaMismatch as mismatch:
                trouble.append(f"{name}: {mismatch}")
                # Retrying blind asks the same question and gets the same answer.
                # The complaints are literal, so hand them back.
                user = (original_user + "\n\nYour previous reply was rejected. Fix "
                        "exactly these and change nothing else:\n  " + str(mismatch))
            except ModelRefused as refused:
                trouble.append(f"{name}: {refused}")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                trouble.append(f"{name}: {exc}")
            except (KeyError, TypeError, ValueError) as exc:
                trouble.append(f"{name}: unreadable reply ({exc})")
    raise ModelRefused(" | ".join(trouble))
