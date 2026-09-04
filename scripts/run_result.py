#!/usr/bin/env python3
"""One truthful final result, including failures after a successful build."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/suresilly-carousel/scripts"))
import publication_record


def result(steps: dict, *, mode: str, slug: str, verdict: str, reason: str,
           retry: bool, published: dict | None) -> dict:
    confirmation = steps.get("post", {}).get("outputs", {})
    confirmed = publication_record.valid(published, slug) or publication_record.valid({
        "media_id": confirmation.get("confirmed_media_id"),
        "deck_slug": confirmation.get("confirmed_deck_slug")}, slug)
    def record(stage, outcome, code, why, can_retry=False):
        return dict(stage=stage, outcome=outcome, fault_code=code,
                    reason=why, retryable=can_retry,
                    published=confirmed, slug=slug, held=verdict == "held")
    stages = [("slot", "work reservation"), ("install", "setup"), ("gates", "tests"), ("verbs", "tests"),
              ("test_state", "tests"), ("restore", "hosting"), ("build", "generation"),
              ("archive", "state saving"),
              ("host", "hosting"), ("reachable", "hosting"),
              ("post", "posting"), ("fetch_host", "hosting"),
              ("prune", "hosting"), ("record", "state saving"), ("save_attempt", "state saving")]
    for key, stage in stages:
        info = steps.get(key, {})
        if info.get("outcome") in {"failure", "cancelled"}:
            if key == "post" and info.get("outputs", {}).get("stage") == "state saving":
                stage = "state saving"
            why = info.get("outputs", {}).get("reason") or (
                reason if key == "build" and reason else f"{stage.capitalize()} failed at {key}.")
            # Publication errors may be ambiguous. Do not invite another post.
            return record(stage, "error", key + "_failed", why,
                          key == "build" and retry)
    slot = steps.get("slot", {})
    if slot.get("outcome") == "success" and slot.get("outputs", {}).get("accepted") == "false":
        if (slot.get("outputs", {}).get("decision") in {"retry_refused", "recovery_refused"}
                or slot.get("outputs", {}).get("alert") == "true"):
            return record("work reservation", "blocked", "request_blocked",
                          slot["outputs"]["reason"])
        return record("work reservation", "duplicate", "work_not_repeated",
                      slot.get("outputs", {}).get("reason") or "No repeated work.")
    if steps.get("build", {}).get("outcome") != "success":
        return record("generation", "error", "build_skipped", "The build did not run.")
    if verdict == "held":
        return record("review", "held", "review_required", reason or "The deck needs review.")
    if published is not None and not publication_record.valid(published, slug):
        return record("state saving", "error", "publication_record_invalid",
                      "The saved post id is invalid or belongs to a different deck. Do not post again.")
    if publication_record.valid(published, slug):
        if steps.get("post", {}).get("outcome") != "success":
            return record("posting", "error", "publication_uncertain", "Check the saved post id before another attempt.")
        return record("posting", "ok", "published", "Instagram confirmed publication.")
    if slug:
        if mode == "publish":
            return record("posting", "error", "publication_unconfirmed", "No confirmed Instagram post id was saved.")
        return record("generation", "built", "built_only", "The deck was built. It was not posted.")
    return record("generation", "stopped", "quality_refused", reason or "No deck passed the checks.", retry)


def main():
    slug = os.environ.get("SLUG", "")
    published = None
    if slug and Path(slug).name == slug:
        path = Path("carousels") / slug / "published.json"
        try:
            published = json.loads(path.read_text())
        except (OSError, ValueError):
            pass
    value = result(json.loads(os.environ.get("STEPS_JSON", "{}")),
                   mode=os.environ.get("MODE", "build"), slug=slug,
                   verdict=os.environ.get("VERDICT", ""), reason=os.environ.get("REASON", ""),
                   retry=os.environ.get("CAN_RETRY") == "true", published=published)
    Path(os.environ.get("RUNNER_TEMP", "/tmp"), "suresilly-result.json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            for key in ("outcome", "stage", "fault_code", "retryable"):
                handle.write(f"{key}={str(value[key]).lower()}\n")
            # Multiline reasons never become workflow commands.
            import uuid
            delimiter = uuid.uuid4().hex
            handle.write(f"reason<<{delimiter}\n{value['reason']}\n{delimiter}\n")


if __name__ == "__main__":
    main()
