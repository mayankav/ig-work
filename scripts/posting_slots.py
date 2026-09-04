#!/usr/bin/env python3
"""Reserve work in committed state BEFORE any generation or provider call.

Both clocks address YYYY-MM-DD_0800 or _2000 (IST). GitHub's creation time,
not the runner's start time, dates its event. A pushed reservation is required;
an unfinished attempt is never silently retried after a crash.
"""
from __future__ import annotations

import argparse
import hashlib
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
    recover = inputs.get("recover", False) in (True, "true")
    if recover and not supplied:
        raise ValueError("Recovery requires the exact failed slot_id.")
    if recover and (mode != "publish" or retry):
        raise ValueError("Recovery requires publish mode and retry turned off.")
    if mode != "publish":
        if retry or supplied:
            raise ValueError("Build-only and force requests cannot claim a posting slot.")
        return safe_id("manual-" + request), request, False
    slot = supplied or slot_at(created_at)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}_(0800|2000)", slot):
        raise ValueError("Invalid posting slot.")
    due = timestamp(slot[:10] + "T" + slot[11:13] + ":00:00+05:30")
    age = timestamp(created_at) - due
    if not timedelta(0) <= age < timedelta(days=7 if recover else 1):
        raise ValueError("Posting slot is outside the allowed window: one day for new work, seven days for recovery.")
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
            retry: bool, *, recover: bool = False, revision: str = "",
            code_revision: str = "", previous_code: str = "") -> tuple[dict | None, str, str]:
    """Pure decision; caller must push the returned record before doing work."""
    previous = load(path)
    attempts = previous["attempts"] if previous else []
    if any(a["request_id"] == request or a["run_id"] == run_id for a in attempts):
        return None, "This request was already accepted. No work was repeated.", "duplicate"
    resume_slug, resume_run = "", ""
    if attempts:
        prior = attempts[-1]
        final = prior.get("result")
        link = f"https://github.com/{os.getenv('GITHUB_REPOSITORY', 'mayankav/ig-work')}/actions/runs/{prior['run_id']}"
        if recover:
            if not isinstance(final, dict) or final.get("outcome") != "error" or final.get("held") is True:
                return None, f"Recovery needs a saved failed attempt. Check {link}. Nothing new was started.", "recovery_refused"
            old_code = prior.get("code_revision") or previous_code
            if (final.get("stage") in {"setup", "tests"} and final.get("published") is False
                    and not final.get("slug") and old_code and code_revision and old_code != code_revision):
                pass
            elif (final.get("slug") and final.get("stage") in {"setup", "tests", "hosting", "posting", "state saving"}):
                resume_slug = safe_id(final["slug"])
                resume_run = safe_id(prior.get("resume_run") or prior["run_id"])
            else:
                return None, f"Recovery cannot start. Fix the code after a test failure, or check the saved deck. Previous run: {link}. Nothing new was started.", "recovery_refused"
        elif not retry:
            detail = ("The previous attempt has no saved result. Check it before recovery."
                      if not isinstance(final, dict) else
                      f"Previous result: {final.get('reason', 'unknown')}")
            return None, f"This slot is already claimed. {detail} Previous run: {link}. Nothing new was started.", "duplicate"
        elif (not isinstance(final, dict) or final.get("retryable") is not True
                or final.get("published") is not False
                or final.get("outcome") not in {"stopped", "error"}
                or final.get("stage") != "generation"):
            return None, f"Retry cannot help this attempt. Use recovery after a code fix or check the saved deck. Previous run: {link}.", "retry_refused"
    elif retry or recover:
        return None, "There is no saved attempt to recover. No new work was started.", "retry_refused"
    attempt = dict(request_id=request, run_id=run_id, created_at=created_at, result=None,
                   revision=revision, code_revision=code_revision)
    if resume_slug:
        attempt.update(resume_slug=resume_slug, resume_run=resume_run)
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


def should_alert(event_name: str, request: str, repeated: bool, run_attempt: int = 1) -> bool:
    return (event_name == 'workflow_dispatch' and not request.startswith('clock-')
            and (not repeated or run_attempt > 1))


def code_at(root: Path, revision: str) -> str:
    paths = ["scripts", ".github/workflows", "ops/dispatch-worker",
             ".agents/skills/suresilly-carousel/scripts", ".agents/skills/suresilly-carousel/tests",
             ".agents/skills/suresilly-carousel/requirements.txt"]
    return hashlib.sha256(git(root, "ls-tree", "-r", revision, "--", *paths).encode()).hexdigest()


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
            inputs = event.get("inputs") or {}
            recover = inputs.get("recover", False) in (True, "true")
            revision = git(ROOT, "rev-parse", "HEAD")
            previous_code = ""
            prior = load(path)
            if recover and prior:
                last = prior["attempts"][-1]
                # Legacy records did not save code revisions. Read the actual
                # run from GitHub, and only recover completed runs.
                meta = json.loads(subprocess.check_output([
                    "gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{safe_id(last['run_id'])}"
                ], text=True))
                if meta.get("status") != "completed":
                    raise ValueError("Previous run is still active.")
                if not last.get("code_revision"):
                    previous_code = code_at(ROOT, meta["head_sha"])
            value, reason, decision = reserve(path, slot, request, run_id, created, retry,
                recover=recover, revision=revision, code_revision=code_at(ROOT, revision),
                previous_code=previous_code)
            if value is not None:
                persist(ROOT, path, value)
            # Only repeated deliveries and clock duplicates stay quiet. A new
            # manual request always gets an answer, even if it cannot start.
            repeated = prior and any(a["request_id"] == request or a["run_id"] == run_id for a in prior["attempts"])
            alert = value is None and should_alert(os.environ["GITHUB_EVENT_NAME"], request,
                                                   bool(repeated), int(os.getenv("GITHUB_RUN_ATTEMPT", "1")))
            if alert:
                last_result = (prior["attempts"][-1].get("result") or {}) if prior else {}
                if last_result.get("outcome") == "error":
                    reason += f" Open auto-post, set mode=publish, slot_id={slot}, recover=true after fixing the fault."
                elif last_result.get("outcome") == "held":
                    reason += " Use the separate publish reply to release the held deck."
                elif last_result.get("published") is True:
                    reason += " A post is already confirmed. Do not post it again."
                else:
                    reason += " Check the previous run before starting more work."
                reason += " Silence leaves this slot unchanged."
            attempt = value["attempts"][-1] if value else {}
            output(accepted=str(value is not None).lower(), slot_id=slot, reason=reason, decision=decision,
                   alert=str(bool(alert)).lower(), resume_slug=attempt.get("resume_slug", ""),
                   resume_run=attempt.get("resume_run", ""))
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
