#!/usr/bin/env python3
"""Reserve work in committed state BEFORE any generation or provider call.

Both clocks address YYYY-MM-DD_0800 or _2000 (IST). GitHub's creation time,
not the runner's start time, dates its event. A pushed reservation is required;
an unfinished attempt is never silently retried after a crash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

IST = timezone(timedelta(hours=5, minutes=30))
CRONS = {"30 2 * * *": 8, "30 14 * * *": 20}
ROOT = Path(__file__).resolve().parents[1]


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Event time must include its time zone.")
    return result.astimezone(IST)


def slot_at(value: str, cron: str = "") -> str:
    when = timestamp(value)
    if cron:
        if cron not in CRONS:
            raise ValueError("Unknown posting schedule.")
        hour = CRONS[cron]
    else:
        hour = 20 if when.hour >= 20 or when.hour < 8 else 8
    due = when.replace(hour=hour, minute=0, second=0, microsecond=0)
    if due > when:
        due -= timedelta(days=1)
    return f"{due:%Y-%m-%d}_{hour:02}00"


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("Invalid work identifier.")
    return value


def identify(event: dict, event_name: str, created_at: str, run_id: str) -> tuple[str, str, bool]:
    inputs = event.get("inputs") or {}
    mode = "publish" if event_name == "schedule" else inputs.get("mode", "build")
    if mode not in {"publish", "build", "force"}:
        raise ValueError("Unknown build mode.")
    request = safe_id(inputs.get("request_id") or "gh-" + safe_id(run_id))
    retry = inputs.get("retry", False) in (True, "true")
    if event_name == "schedule":
        return slot_at(created_at, event.get("schedule", "unknown")), request, False
    if event_name != "workflow_dispatch":
        raise ValueError("Unsupported event.")
    supplied = inputs.get("slot_id", "")
    if mode != "publish":
        if retry or supplied:
            raise ValueError("Build-only and force requests cannot claim a posting slot.")
        return safe_id("manual-" + request), request, False
    slot = supplied or slot_at(created_at)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_(0800|2000)", slot):
        raise ValueError("Invalid posting slot.")
    due = timestamp(slot[:10] + "T" + slot[11:13] + ":00:00+05:30")
    age = timestamp(created_at) - due
    if not timedelta(0) <= age < timedelta(hours=24):
        raise ValueError("Posting slot is in the future or more than one day old.")
    return slot, request, retry


def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if (not isinstance(value, dict) or value.get("version") != 1
            or value.get("slot_id") != path.stem
            or not isinstance(value.get("attempts"), list) or not value["attempts"]):
        raise ValueError("Invalid saved slot record; refusing new work.")
    for attempt in value["attempts"]:
        if not isinstance(attempt, dict) or not all(isinstance(attempt.get(k), str)
                and attempt[k] for k in ("request_id", "run_id", "created_at")):
            raise ValueError("Invalid saved attempt; refusing new work.")
    return value


def reserve(path: Path, slot: str, request: str, run_id: str, created_at: str,
            retry: bool) -> tuple[dict | None, str, str]:
    """Pure decision; caller must push the returned record before doing work."""
    previous = load(path)
    attempts = previous["attempts"] if previous else []
    if any(a["request_id"] == request or a["run_id"] == run_id for a in attempts):
        return None, "This request was already accepted. No work was repeated.", "duplicate"
    if attempts:
        final = attempts[-1].get("result")
        if not retry:
            return None, "This posting slot was already claimed. No work was repeated.", "duplicate"
        if (not isinstance(final, dict) or final.get("retryable") is not True
                or final.get("published") is not False
                or final.get("outcome") not in {"stopped", "error"}
                or final.get("stage") != "generation"):
            return None, "Retry cannot safely help this attempt. No new work was started.", "retry_refused"
    elif retry:
        return None, "There is no saved attempt to retry. No new work was started.", "retry_refused"
    attempt = dict(request_id=request, run_id=run_id, created_at=created_at, result=None)
    return dict(version=1, slot_id=slot, attempts=[*attempts, attempt]), "Work reserved.", "accepted"


def finish(path: Path, run_id: str, result: dict) -> dict:
    value = load(path)
    if value is None or value["attempts"][-1]["run_id"] != run_id:
        raise ValueError("The final result does not own this slot.")
    required = {"stage", "outcome", "fault_code", "reason", "retryable", "published"}
    if (not isinstance(result, dict) or not required <= result.keys()
            or type(result["retryable"]) is not bool or type(result["published"]) is not bool
            or not all(isinstance(result[k], str) and result[k]
                       for k in required - {"retryable", "published"})):
        raise ValueError("Incomplete final result.")
    old = value["attempts"][-1]["result"]
    if old is not None and old != result:
        raise ValueError("A completed attempt cannot be replaced.")
    value["attempts"][-1]["result"] = result
    return value


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def persist(root: Path, path: Path, value: dict) -> None:
    """Commit only this record. Failed pushes stop work; never mask or force them."""
    if git(root, "status", "--porcelain"):
        raise ValueError("Working tree is not clean; refusing to reserve or finish work.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    temp.replace(path)
    relative = str(path.relative_to(root))
    git(root, "add", "--", relative)
    staged = git(root, "diff", "--cached", "--name-only")
    if not staged:
        # An earlier push might have failed after its local commit. A matching
        # local file alone never proves that another runner can see the result.
        git(root, "push", "origin", "HEAD:main")
        return
    if staged != relative:
        raise ValueError("Unexpected staged files; refusing state commit.")
    git(root, "-c", "user.name=suresilly-bot", "-c", "user.email=bot@suresilly.com",
        "commit", "-m", f"auto: slot {value['slot_id']} [skip ci]")
    git(root, "push", "origin", "HEAD:main")


def output(**fields) -> None:
    import uuid
    dest = os.environ.get("GITHUB_OUTPUT")
    if dest:
        with open(dest, "a") as handle:
            for key, value in fields.items():
                delimiter = uuid.uuid4().hex
                handle.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["reserve", "finish"])
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    try:
        run_id = safe_id(os.environ["GITHUB_RUN_ID"])
        if args.action == "reserve":
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            created = os.environ["RUN_CREATED_AT"]
            slot, request, retry = identify(event, os.environ["GITHUB_EVENT_NAME"], created, run_id)
            path = ROOT / "state/slots" / (slot + ".json")
            value, reason, decision = reserve(path, slot, request, run_id, created, retry)
            if value is not None:
                persist(ROOT, path, value)
            output(accepted=str(value is not None).lower(), slot_id=slot, reason=reason, decision=decision)
            print(reason)
        else:
            slot = safe_id(os.environ["SLOT_ID"])
            path = ROOT / "state/slots" / (slot + ".json")
            value = finish(path, run_id, json.loads(args.result.read_text()))
            persist(ROOT, path, value)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        # Do not copy a command or service body into an alert (it may hold secrets).
        reason = f"Posting-slot {args.action} failed ({type(exc).__name__}). No new work is allowed."
        output(reason=reason)
        raise SystemExit(reason) from exc


if __name__ == "__main__":
    main()
