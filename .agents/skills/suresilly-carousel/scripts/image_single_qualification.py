"""Bounded offline trial; cannot qualify the production grouped reviewer.

One candidate and one separate control request per case, three repeats.
No retries, fallback, image generation, library approval or publication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import cv2
import numpy

import image_qualification as corpus
import image_single_review as review
import llm

MAX_REQUESTS = 138
MIN_INTERVAL = 40


def plan():
    for repeat in range(corpus.REPETITIONS):
        for case in sorted(corpus.cases(), key=lambda c: corpus.digest([repeat, c["id"]])):
            yield repeat, case


def contract():
    root = Path(__file__).parent
    return corpus.digest({
        "version": review.VERSION,
        "sources": {p: review.digest((root / p).read_bytes()) for p in
                    ("image_single_review.py", "image_single_qualification.py", "image_qualification.py", "llm.py")},
        "cv2": cv2.__version__, "numpy": numpy.__version__,
        "cases": [{"id": c["id"], "codes": c["codes"], "hash": review.digest(c["path"].read_bytes())}
                  for c in corpus.cases()],
    })


def evaluate(record, now=None):
    faults = []
    rejects = [0] * corpus.REPETITIONS
    try:
        if record["contract"] != contract():
            faults.append("check code or images changed")
        if (record["provider"], record["model"]) != (review.PROVIDER, review.MODEL):
            faults.append("wrong model")
        age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(record["started_at"])).total_seconds()
        if not 0 <= age <= corpus.MAX_AGE_DAYS * 86400:
            faults.append("stale or future-dated evidence")
        if record["errors"]:
            faults.append("trial stopped with an error")
        expected = list(plan())
        if len(record["observations"]) != len(expected) or record["http_requests"] != MAX_REQUESTS:
            faults.append("three complete trials required")
        for (repeat, case), observation in zip(expected, record["observations"]):
            if (observation["repeat"], observation["case"]) != (repeat, case["id"]):
                raise ValueError("case order or coverage changed")
            for role, path in (("candidate", case["path"]), ("control", corpus.review.CONTROL_PATH)):
                item = observation[role]
                raw = path.read_bytes()
                if item["source_sha256"] != review.digest(raw) or item["image_sha256"] != review.digest(review.prepare(raw)):
                    raise ValueError("image bytes changed")
                if item["actual_model"] != review.PROVIDER + "/" + review.MODEL:
                    raise ValueError("different model answered")
            review.check_control(observation["control"]["answer"])
            found = review.observed_codes(observation["candidate"]["answer"])
            if case["codes"] and not found.intersection(case["codes"]):
                faults.append(f"trial {repeat+1}: missed {case['id']}")
            if not case["codes"] and found:
                rejects[repeat] += 1
        for repeat, count in enumerate(rejects):
            if count / len(corpus.CLEAN) > corpus.MAX_CLEAN_REJECT_RATE:
                faults.append(f"trial {repeat+1}: rejected {count}/{len(corpus.CLEAN)} correct images")
    except (KeyError, TypeError, ValueError, OSError, cv2.error) as exc:
        faults.append(str(exc))
    return {"qualified": not faults, "faults": faults, "clean_rejects": rejects}


def run(output: Path, interval=MIN_INTERVAL, max_requests=MAX_REQUESTS):
    if not MIN_INTERVAL <= interval <= 3600 or not 1 <= max_requests <= MAX_REQUESTS:
        raise ValueError("invalid spacing or request budget")
    output.mkdir(parents=True, exist_ok=False)
    record = {"version": review.VERSION, "purpose": "offline single-image trial only",
              "provider": review.PROVIDER, "model": review.MODEL, "contract": contract(),
              "started_at": datetime.now(timezone.utc).isoformat(), "system": review.SYSTEM,
              "user": review.USER, "schema": review.SCHEMA, "http_requests": 0,
              "observations": [], "errors": [], "status": "running"}

    def save():
        temporary = output / "results.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.replace(output / "results.json")

    original_post = llm._post
    last_request = None

    def bounded_post(*args, **kwargs):
        nonlocal last_request
        if record["http_requests"] >= max_requests:
            raise RuntimeError("single-image request budget exhausted")
        if last_request is not None:
            time.sleep(max(0, interval - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        record["http_requests"] += 1
        save()
        return original_post(*args, **kwargs)

    save()
    llm._post = bounded_post
    rejects = [0] * corpus.REPETITIONS
    try:
        for repeat, case in plan():
            observation = {"repeat": repeat, "case": case["id"]}
            record["observations"].append(observation)
            for role, path in (("candidate", case["path"]), ("control", corpus.review.CONTROL_PATH)):
                raw = path.read_bytes()
                image = review.prepare(raw)
                source_hash, image_hash = review.digest(raw), review.digest(image)
                (output / (source_hash + ".png")).write_bytes(raw)
                (output / (image_hash + ".jpg")).write_bytes(image)
                item = {"source_sha256": source_hash, "image_sha256": image_hash}
                observation[role] = item
                save()
                print(f"Trial {repeat+1}: {case['id']} {role}; request {record['http_requests']+1}/{max_requests}", flush=True)
                try:
                    answer, actual = llm.look_once(review.SYSTEM, review.USER, review.SCHEMA, image,
                                                  provider=review.PROVIDER, model=review.MODEL)
                except Exception as exc:
                    if hasattr(exc, "answer"):
                        item["answer"] = exc.answer
                    raise
                item.update(answer=answer, actual_model=actual)
                save()
                if actual != review.PROVIDER + "/" + review.MODEL:
                    raise ValueError("different model answered")
                item["assessment"] = review.assessment(answer)
                save()
                found = review.observed_codes(answer)
                if role == "control":
                    review.check_control(answer)
                elif case["codes"] and not found.intersection(case["codes"]):
                    record["status"] = "failed"
                    raise ValueError("missed known defect: " + case["id"])
                elif not case["codes"] and found:
                    rejects[repeat] += 1
                    if rejects[repeat] / len(corpus.CLEAN) > corpus.MAX_CLEAN_REJECT_RATE:
                        record["status"] = "failed"
                        raise ValueError("too many correct images rejected in this trial")
            save()
        record["result"] = evaluate(record)
        record["status"] = "passed" if record["result"]["qualified"] else "failed"
    except Exception as exc:
        if "missed the known extra leg" in str(exc):
            record["status"] = "failed"
        elif record["status"] != "failed":
            record["status"] = "incomplete"
        record["errors"].append({"type": type(exc).__name__, "reason": str(exc)[:500]})
        record["result"] = evaluate(record)
    finally:
        llm._post = original_post
        save()
    print(json.dumps({"status": record["status"], "requests": record["http_requests"], "result": record["result"]}), flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=MIN_INTERVAL)
    parser.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    args = parser.parse_args()
    return int(run(args.output, args.interval_seconds, args.max_requests)["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
