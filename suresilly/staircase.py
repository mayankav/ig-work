"""The writer's call through the OpenCode CLI, and the staircase of models behind it.

OpenCode's free models answer only through its own CLI (a direct HTTP call gets 403), so a call is a subprocess. A model that times out,
errors or returns nothing rests for a cool-down and the next step of the staircase answers. `call(messages)` has the shape the writer already
uses, so nothing in script.py knows which model answered.

The CLI keeps one local database. Several calls at once on the same database fail with "database is locked", so each worker thread gets
its own data folder (made once, reused for that thread's calls).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time

import requests

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
COOL = 600          # seconds a failing model rests before it is tried again
TASK_END = "\n\nAnswer with one JSON object and nothing else. No code fences. Do not use tools, read files or run commands."
_local = threading.local()


class ModelDown(RuntimeError):
    pass


THINK = re.compile(r"<think>.*?</think>", re.S)


def parse(text: str) -> dict:
    text = THINK.sub("", ANSI.sub("", text or "")).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        found = re.search(r"\{.*\}", text, re.S)
        if found:
            try:
                return json.loads(found.group(0))
            except Exception:
                pass
    return {"_bad_json": text[:100]}


def flatten(messages: list[dict]) -> str:
    tags = {"system": "INSTRUCTIONS", "user": "REQUEST", "assistant": "YOUR EARLIER ANSWER"}
    return "\n\n".join(f"{tags[m['role']]}:\n{m['content']}" for m in messages) + TASK_END


def _own_home() -> dict:
    """The environment for this thread's CLI calls: its own data folder, so no two calls share a database."""
    if not hasattr(_local, "home"):
        _local.home = tempfile.mkdtemp(prefix="opencode-")
    return {**os.environ, "XDG_DATA_HOME": _local.home, "XDG_STATE_HOME": _local.home}


def opencode(model: str, timeout: int = 300, run=subprocess.run):
    """One model through the CLI. Raises ModelDown when it gives nothing usable."""
    def call(messages: list[dict]) -> dict:
        with tempfile.TemporaryDirectory() as empty:
            try:
                p = run(["opencode", "run", "-m", f"opencode/{model}", flatten(messages)], cwd=empty, env=_own_home(),
                        capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise ModelDown(f"{model}: timed out after {timeout}s")
        out = ANSI.sub("", p.stdout or "")
        out = "\n".join(line for line in out.splitlines() if not line.startswith("> build")).strip()
        if p.returncode != 0 or not out:
            raise ModelDown(f"{model}: exit {p.returncode}: {(ANSI.sub('', p.stderr or '') or out)[:160]}")
        return parse(out)
    call.model = model
    return call


ENDPOINTS = {      # OpenAI-compatible chat endpoints, and the .env.local name of the key for each
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "cohere": ("https://api.cohere.ai/compatibility/v1", "COHERE_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "tencent": ("https://tokenhub-intl.tencentcloudmaas.com/v1", "TENCENT_API_KEY"),
}


def http_chat(model: str, base_url: str, key: str, timeout: int = 180, post=requests.post, max_tokens: int = 3000, temperature: float = 0.8,
              json_mode: bool = True):
    """One model through an OpenAI-compatible chat endpoint. Raises ModelDown on any failure, so a staircase can move on.

    `json_mode` asks the provider for a JSON object. A provider that rejects the option (HTTP 400 or 422) is asked again without it.
    """
    def call(messages: list[dict]) -> dict:
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        try:
            reply = post(base_url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {key}"},
                         json={**body, **({"response_format": {"type": "json_object"}} if json_mode else {})}, timeout=timeout)
            if json_mode and reply.status_code in (400, 422):
                reply = post(base_url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=timeout)
        except requests.RequestException as error:
            raise ModelDown(f"{model}: {type(error).__name__}")
        if reply.status_code != 200:
            raise ModelDown(f"{model}: HTTP {reply.status_code}: {reply.text[:120]}")
        try:
            text = reply.json()["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, ValueError, TypeError):
            text = ""
        if not text.strip():
            raise ModelDown(f"{model}: empty answer")
        return parse(text)
    call.model = model
    return call


def from_env(provider: str, model: str, timeout: int = 180, env: dict | None = None, post=requests.post):
    """`http_chat` for a provider in ENDPOINTS, with its key read from the environment or from .env.local. A missing key is a ModelDown at call time."""
    base, name = ENDPOINTS[provider]
    key = (env or os.environ).get(name, "")
    if not key:
        from . import ROOT
        path = ROOT / ".env.local"
        if path.exists():
            for line in path.read_text().splitlines():
                found, _, value = line.partition("=")
                if found.strip() == name:
                    key = value.strip().strip("\"'")
    if not key:
        def missing(messages):
            raise ModelDown(f"{model}: no {name}")
        missing.model = f"{provider}/{model}"
        return missing
    call = http_chat(model, base, key, timeout, post)
    call.model = f"{provider}/{model}"
    return call


class Staircase:
    """Try the steps in order. The first that answers wins; a step that fails rests for COOL seconds. Safe to call from several threads.

    A step is an OpenCode model name (a string) or any `call(messages)` with a `.model` name, such as `http_chat` or `from_env`.
    """
    def __init__(self, models: list, timeout: int = 300, run=subprocess.run):
        self.steps = [(getattr(m, "model", m), m if callable(m) else opencode(m, timeout, run)) for m in models]
        self.rest: dict[str, float] = {}
        self.answered = {name: 0 for name, _ in self.steps}
        self.failed = {name: 0 for name, _ in self.steps}
        self.last = ""
        self._lock = threading.Lock()

    def _note(self, model: str, ok: bool) -> None:
        with self._lock:
            (self.answered if ok else self.failed)[model] += 1
            if ok:
                self.last = model
            else:
                self.rest[model] = time.time() + COOL

    def __call__(self, messages: list[dict]) -> dict:
        errors = []
        for model, call in self.steps:
            if self.rest.get(model, 0) > time.time():
                continue
            try:
                out = call(messages)
            except ModelDown as error:
                self._note(model, False)
                errors.append(str(error))
                continue
            self._note(model, True)
            return out
        model, call = min(self.steps, key=lambda s: self.rest.get(s[0], 0))      # everyone is resting: the one that rests least gets one more try
        try:
            out = call(messages)
            self._note(model, True)
            return out
        except ModelDown as error:
            raise ModelDown("every step of the staircase failed: " + " | ".join(errors + [str(error)]))
