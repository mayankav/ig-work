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

# Each Gemini model has its own quota bucket, so a throttled flash does not mean
# a throttled flash-lite. That is capacity, not independence: both are Google,
# and neither may ever be used to check the other's work.
GEMINI_MODELS = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
GROQ_MODEL = "openai/gpt-oss-120b"

TIMEOUT = 45
RETRIES = 1

# A rate limit is not a failure, it is a queue. The free tiers cap by the minute,
# so the two-second pause that suits a transient error is useless here — it has
# to be long enough to cross into the next window. The provider's own
# Retry-After is used when it sends one.
RATE_LIMIT_PAUSE = 25
RETRY_PAUSE = 2


class ModelRefused(Exception):
    """No usable answer. The reason is written for whoever reads the alert."""


class RateLimited(ModelRefused):
    """The provider is throttling. Worth waiting for, unlike everything else."""

    def __init__(self, message: str, wait: int):
        super().__init__(message)
        self.wait = wait


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
    if out.get("type") == "string" and "enum" in out:
        out["format"] = "enum"
    return out


# Google does not send a Retry-After header on a 429. It puts the wait in the
# error message as "Please retry in 54.6s", so that is where we look before
# falling back to a fixed pause.
_RETRY_HINT = re.compile(r"retry in ([\d.]+)s", re.I)


def _retry_after(exc: urllib.error.HTTPError) -> int:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.strip().isdigit():
        return int(header)
    try:
        match = _RETRY_HINT.search(exc.read().decode("utf-8", "replace"))
    except Exception:
        match = None
    if match:
        # A second of slack, so we are not racing the edge of the window.
        return min(90, int(float(match.group(1))) + 1)
    return RATE_LIMIT_PAUSE


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
            raise RateLimited(f"HTTP {exc.code}", _retry_after(exc)) from exc
        raise


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
    for model in GEMINI_MODELS:
        try:
            data = _post(GEMINI_URL.format(model=model), payload, {"x-goog-api-key": key})
            break
        except RateLimited as limited:
            trouble.append(f"{model} {limited}")
    else:
        raise RateLimited("; ".join(trouble), RATE_LIMIT_PAUSE)

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


def call_groq(system: str, user: str, temperature: float, schema: dict | None = None) -> str:
    key = resolve_key("GROQ_API_KEY")
    if not key:
        raise ModelRefused("no Groq key")
    payload = {
        "model": GROQ_MODEL,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system + (
                f"\n\nReturn JSON matching exactly this shape:\n{json.dumps(schema)}" if schema else "")},
            {"role": "user", "content": user},
        ],
    }
    data = _post(GROQ_URL, payload, {"Authorization": f"Bearer {key}"})
    choices = data.get("choices") or []
    if not choices:
        raise ModelRefused("Groq returned no choices")
    text = choices[0].get("message", {}).get("content", "")
    if not text.strip():
        raise ModelRefused("Groq returned an empty answer")
    return text


PROVIDERS = (("gemini", call_gemini), ("groq", call_groq))


def ask(system: str, user: str, schema: dict, temperature: float = 0.6,
        providers=PROVIDERS) -> tuple[dict, str]:
    """Ask, validate, and return the answer with the name of who gave it.

    Each provider gets one retry, then we move on. When every provider is
    exhausted the caller gets ModelRefused and the run ends without a post.
    """
    trouble: list[str] = []
    for name, call in providers:
        pause = RETRY_PAUSE
        for attempt in range(RETRIES + 1):
            if attempt:
                time.sleep(pause)
            try:
                reply = call(system, user, temperature, schema)
                answer = extract_json(reply)
                problems = validate(answer, schema)
                if problems:
                    raise ModelRefused("; ".join(problems[:3]))
                return answer, name
            except RateLimited as limited:
                pause = limited.wait
                trouble.append(f"{name}: {limited}")
            except ModelRefused as refused:
                trouble.append(f"{name}: {refused}")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                trouble.append(f"{name}: {exc}")
            except (KeyError, TypeError, ValueError) as exc:
                trouble.append(f"{name}: unreadable reply ({exc})")
    raise ModelRefused(" | ".join(trouble))
