"""A JSON-returning chat call: Gemini first (better prose), Groq as the fallback.

Keys come from the environment or from .env.local: GEMINI_API_KEY, GEMINI_API_KEY_2
and GROQ_API_KEY. Any that are missing are skipped.
"""
from __future__ import annotations

import json
import os
import time

import requests

from . import ROOT

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ("openai/gpt-oss-120b",)


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
        for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2"):
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
            if response.status_code == 200:
                try:
                    return json.loads(read(response.json())), model
                except (KeyError, IndexError, TypeError, ValueError):
                    last = f"{model}: the reply was not JSON"
                    continue
            last = f"{model}: HTTP {response.status_code}"
            if response.status_code == 429 and "per day" in response.text.lower():
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
