#!/usr/bin/env python3
"""Write the same briefs with several models and print the slides side by side.

    .venv/bin/python .agents/skills/suresilly-writer/scripts/ab_write.py \
        --models gemini-3.8-flash gemini-3.5-flash --formats list story oneliner

Runs the real writer brief and the real editor pass (suresilly.write.SYSTEM and EDITOR),
so what you read is what production would post. Keys come from .env.local. Output JSON
lands in .agents/skills/suresilly-writer/out/, which is scratch: delete it before committing.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from suresilly import llm, write  # noqa: E402

BRIEFS = {
    "list": ("things you only understand after a certain age or a certain life change", "mum"),
    "story": ("what looked like a small annoyance turns out to be love", "dad"),
    "oneliner": ("nobody talks about a small, true feeling everyone has had", "a friend you drifted from"),
}
OUT = Path(__file__).resolve().parents[1] / "out"


def brief(fmt: str, shape: str, person: str) -> str:
    """The same brief production sends: recent posts to avoid, owner notes, then the angle."""
    daily = write.context(write.recent_posts(), write.owner_notes())
    return write.ask(fmt, {"shape": shape, "person": person, "topic": write.PEOPLE[person]}, daily)


def send(model: str, system: str, user: str) -> dict | str:
    """One call with retries on 429/5xx; Gemini models by name, anything with a slash goes to Groq."""
    if "/" in model:
        api_key, call, read = llm.key("GROQ_API_KEY"), llm._groq, llm._groq_text
    else:
        api_key, call, read = llm.key("GEMINI_API_KEY"), llm._gemini, llm._gemini_text
    if not api_key:
        return "no key for this model in .env.local"
    last = ""
    for attempt in range(4):
        response = call(model, api_key, system, user, 0.9)
        if response.status_code == 200:
            try:
                return json.loads(read(response.json()))
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                return f"reply was not JSON: {exc}"
        last = f"HTTP {response.status_code}: {response.text[:120]}"
        if response.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(6 * (attempt + 1))
    return last


def run(job: tuple[str, str]) -> tuple[tuple[str, str], float, dict | str]:
    model, fmt = job
    started = time.time()
    user = brief(fmt, *BRIEFS[fmt])
    draft = send(model, write.SYSTEM, user)
    if isinstance(draft, str):
        return job, time.time() - started, draft
    edited = send(model, write.EDITOR, user + "\n\nDraft:\n" + json.dumps(draft, ensure_ascii=False))
    post = edited if isinstance(edited, dict) else draft
    return job, time.time() - started, post


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=["gemini-3.8-flash", "gemini-3.5-flash"])
    parser.add_argument("--formats", nargs="+", default=["list", "story", "oneliner"], choices=list(BRIEFS))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    jobs = [(m, f) for m in args.models for f in args.formats]
    with cf.ThreadPoolExecutor(len(jobs)) as pool:
        for (model, fmt), seconds, post in pool.map(run, jobs):
            print(f"\n===== {model}  {fmt}  ({seconds:.0f}s)")
            if isinstance(post, str):
                print(post)
                continue
            (OUT / f"{model.replace('/', '_')}_{fmt}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1))
            for number, slide in enumerate(post.get("slides", []), 1):
                print(f"{number}. {slide.get('text')}   [{slide.get('pose')}]")
            print("caption:", (post.get("caption") or "").replace("\n", " / "))


if __name__ == "__main__":
    main()
