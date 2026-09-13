"""A JSON-returning chat call: Gemini first (better prose), Groq as the fallback.

Keys come from the environment or from .env.local: GEMINI_API_KEY, GEMINI_API_KEY_2,
GEMINI_API_KEY_3 and GROQ_API_KEY. Any that are missing are skipped. Each Gemini key should
come from its own Google project: the free tier allows 20 requests a day per model per project.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from . import ROOT

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ("openai/gpt-oss-120b",)
GEMINI_KEYS = ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3")
GEMINI_DAILY = 20  # free requests a day per model per project (see above); Google refills them at midnight Pacific
PACIFIC = ZoneInfo("America/Los_Angeles")
USAGE = ROOT / "state" / "usage.json"  # what the writer used today, so Telegram can say what is left


class LLMError(RuntimeError):
    pass


def key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    env = ROOT / ".env.local"
    if env.exists():
        for line in env.read_text().splitlines():
            found, _, value = line.partition("=")
            if found.strip() == name and value.strip():
                return value.strip().strip("'\"")
    return ""


def _gemini(model: str, api_key: str, system: str, user: str, temperature: float) -> requests.Response:
    return requests.post(GEMINI_URL.format(model=model), timeout=120, headers={"x-goog-api-key": api_key}, json={
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    })


def _gemini_text(body: dict) -> str:
    parts = body["candidates"][0]["content"]["parts"]
    return "".join(part.get("text", "") for part in parts if not part.get("thought"))


def _groq(model: str, api_key: str, system: str, user: str, temperature: float) -> requests.Response:
    return requests.post(GROQ_URL, timeout=120, headers={"Authorization": f"Bearer {api_key}"}, json={
        "model": model, "temperature": temperature, "reasoning_effort": "medium", "max_completion_tokens": 6000,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    })


def _groq_text(body: dict) -> str:
    return body["choices"][0]["message"]["content"]


def routes() -> list[tuple[str, str, object, object]]:
    found = []
    for model in GEMINI_MODELS:
        for name in GEMINI_KEYS:
            if key(name):
                found.append((model, key(name), _gemini, _gemini_text))
    for model in GROQ_MODELS:
        if key("GROQ_API_KEY"):
            found.append((model, key("GROQ_API_KEY"), _groq, _groq_text))
    return found


def chat_json(system: str, user: str, temperature: float = 0.9) -> tuple[dict, str]:
    """Return (the model's JSON object, model name)."""
    available = routes()
    if not available:
        raise LLMError("No writing model is configured (GEMINI_API_KEY or GROQ_API_KEY).")
    last = "no attempt made"
    for model, api_key, send, read in available:
        for attempt in range(2):
            try:
                response = send(model, api_key, system, user, temperature)
            except requests.RequestException as exc:
                last = f"{model}: {type(exc).__name__}"
                time.sleep(3)
                continue
            _count(model, api_key, response)
            if response.status_code == 200:
                try:
                    return json.loads(read(response.json())), model
                except (KeyError, IndexError, TypeError, ValueError):
                    last = f"{model}: the reply was not JSON"
                    continue
            last = f"{model}: HTTP {response.status_code}"
            # Groq says "tokens per day"; Gemini says "GenerateRequestsPerDayPerProjectPerModel".
            if response.status_code == 429 and "perday" in response.text.lower().replace(" ", ""):
                break  # this model's daily allowance is gone; try the next one
            if response.status_code == 429 or response.status_code >= 500 or "json_validate_failed" in response.text:
                try:
                    wait = float(response.headers.get("retry-after") or 8)
                except ValueError:
                    wait = 8
                time.sleep(min(wait, 30))
                continue
            break  # any other 4xx will not fix itself
    raise LLMError(f"No writing model answered ({last}).")


def _label(model: str, api_key: str) -> str:
    """"gemini-3.8-flash · key 2": which allowance a call came out of, without the key itself."""
    number = next((n for n, name in enumerate(GEMINI_KEYS, 1) if key(name) == api_key), 0)
    return f"{model} · key {number}"


def _count(model: str, api_key: str, response: requests.Response) -> None:
    """Note one call in state/usage.json. Only a count for Telegram, so it never raises."""
    try:
        usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}
        if model in GROQ_MODELS:
            usage["groq"] = {"left": int(response.headers["x-ratelimit-remaining-requests"]),
                             "limit": int(response.headers["x-ratelimit-limit-requests"]),
                             "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        else:
            today = datetime.now(PACIFIC).date().isoformat()
            if usage.get("gemini_day") != today:  # Google refilled everything at midnight Pacific
                usage["gemini_day"], usage["gemini"] = today, {}
            usage["gemini_routes"] = [_label(m, k) for m, k, send, _ in routes() if send is _gemini]
            row = usage["gemini"].setdefault(_label(model, api_key), {"used": 0, "empty": False})
            row["used"] += 1
            if response.status_code == 429 and "perday" in response.text.lower().replace(" ", ""):
                row["empty"] = True
        USAGE.parent.mkdir(parents=True, exist_ok=True)
        USAGE.write_text(json.dumps(usage, indent=2) + "\n")
    except Exception as error:  # a missing header or an unwritable file must not stop a post
        print(f"Could not count this call: {error}")


def left_today(now: datetime | None = None) -> dict:
    """What is left of today's free writer calls, from state/usage.json. Empty when nothing was counted."""
    try:
        usage = json.loads(USAGE.read_text())
    except (OSError, ValueError):
        return {}
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(PACIFIC).date()
    counted = usage.get("gemini", {}) if usage.get("gemini_day") == today.isoformat() else {}
    routes_seen = usage.get("gemini_routes", [])
    found = {}
    if routes_seen:
        found["gemini_left"] = sum(0 if counted.get(r, {}).get("empty") else
                                   max(0, GEMINI_DAILY - counted.get(r, {}).get("used", 0)) for r in routes_seen)
        found["gemini_total"] = GEMINI_DAILY * len(routes_seen)
        midnight = datetime.combine(today + timedelta(days=1), datetime.min.time(), PACIFIC)
        found["gemini_refill"] = midnight.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%H:%M")
    if usage.get("groq"):
        found["groq_left"], found["groq_total"] = usage["groq"]["left"], usage["groq"]["limit"]
    return found
