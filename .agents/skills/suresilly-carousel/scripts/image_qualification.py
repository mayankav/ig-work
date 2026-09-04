"""Qualify exact image models on fixed, visually reviewed good and bad poses.

Offline CLI, never called to buy extra reviews inside a deck. Evidence contains
the actual replies and sheet hashes. Production recomputes the result; a saved
`passed` flag is not authority. Tests use temporary evidence only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import cv2

import image_review as review
import llm

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "references/image_review_qualifications"
REPETITIONS = 3
MAX_CLEAN_REJECT_RATE = .05
MAX_AGE_DAYS = 30
# Reviewed visually, 2026-09-04. Includes closed eyes, glasses, hidden eyes/limbs,
# lying down, tilted heads, seated poses, props and two-character scenes.
# The excluded leaning_on pose needs a separate audit of stray pieces.
CLEAN = (
    "deadpan", "side_eye", "on_back", "hugging", "kneeling", "running",
    "reading", "self_hug", "high_five", "far_apart", "warm_mug", "point_right",
    "winking", "sitting", "looking_far", "back_to_back_sitting", "peeping",
    "falling", "shoulder_hold", "leaping",
)
BAD = {
    "blank_profile_eye": ("blank_eye",),
    "malformed_eyelids": ("stray_eye_mark", "mismatched_eyes", "blank_eye"),
    "extra_leg": ("extra_limb",),
}


def cases() -> list[dict]:
    return ([{"id": name, "path": ROOT / "mascot/library" / (name + ".png"),
              "codes": []} for name in CLEAN]
            + [{"id": name, "path": ROOT / "tests/fixtures/rejected_art" / (name + ".png"),
                "codes": list(codes)} for name, codes in BAD.items()])


def model_ids() -> list[tuple[str, str]]:
    return ([('gemini', model) for model in llm.GEMINI_MODELS]
            + [('groq', model) for model in llm.GROQ_VISION_MODELS]
            + [('cloudflare', llm.CLOUDFLARE_VISION_MODEL)])


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def contract() -> str:
    # Includes renderer, parser, exact-model transport and qualification rules.
    # A source or dependency-version change invalidates earlier evidence.
    import numpy
    return digest({
        "sources": {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest()
                    for name in ("image_review.py", "image_qualification.py", "llm.py")},
        "cv2": cv2.__version__, "numpy": numpy.__version__,
        "cases": [{"id": c["id"], "codes": c["codes"],
                   "sha256": hashlib.sha256(c["path"].read_bytes()).hexdigest()} for c in cases()],
    })


def batches():
    population = cases()
    for repeat in range(REPETITIONS):
        # Same cases, different neighbours and order each time, decided by code.
        ordered = sorted(population, key=lambda c: digest([repeat, c["id"]]))
        for start in range(0, len(ordered), review.GROUP_SIZE):
            yield repeat, ordered[start:start+review.GROUP_SIZE]


def prepare(group):
    sheet, mapping, control = review.prepare_group({
        n: cv2.imread(str(case["path"]), cv2.IMREAD_UNCHANGED)
        for n, case in enumerate(group, 1)})
    return sheet, mapping, control


def evaluate(record: dict, *, now=None) -> dict:
    """Recompute all three trials. Missing evidence never counts as a pass."""
    faults = []
    if not isinstance(record, dict):
        return {"qualified": False, "faults": ["unreadable qualification"]}
    if (record.get("provider"), record.get("model")) not in model_ids():
        faults.append("unknown exact model")
    if record.get("errors"):
        faults.append("a qualification request failed")
    try:
        if record.get("contract") != contract():
            faults.append("qualification code, images or dependencies changed")
        when = datetime.fromisoformat(record.get("started_at", ""))
        age = ((now or datetime.now(timezone.utc)) - when).total_seconds()
        if not 0 <= age <= MAX_AGE_DAYS * 86400:
            faults.append("qualification is stale or future dated")
    except (ValueError, TypeError, OSError):
        faults.append("qualification date or inputs unavailable")
    observations = record.get("observations", [])
    plan = list(batches())
    if not isinstance(observations, list) or len(observations) != len(plan):
        faults.append("three complete trials are required")
        return {"qualified": False, "faults": faults}
    clean_rejects = [0] * REPETITIONS
    for index, ((repeat, group), observation) in enumerate(zip(plan, observations)):
        try:
            sheet, mapping, control = prepare(group)
            if observation["repeat"] != repeat or observation["cases"] != [c["id"] for c in group]:
                raise ValueError("case coverage or trial order changed")
            if observation["sheet_sha256"] != hashlib.sha256(sheet).hexdigest():
                raise ValueError("inspection sheet changed")
            if observation["actual_model"] != record["provider"] + "/" + record["model"]:
                raise ValueError("different model answered")
            answer = observation["answer"]
            found = review.parse_vetoes(answer, set(mapping) | {control}, control)
            for panel, number in mapping.items():
                case = group[number-1]
                codes = review.observed_codes(answer, panel)
                if case["codes"] and not codes.intersection(case["codes"]):
                    faults.append(f"trial {repeat+1}: missed {case['id']}")
                if not case["codes"] and panel in found:
                    clean_rejects[repeat] += 1
        except (ValueError, KeyError, TypeError, OSError, cv2.error) as exc:
            faults.append(f"request {index+1}: {exc}")
    for repeat, count in enumerate(clean_rejects):
        if count / len(CLEAN) > MAX_CLEAN_REJECT_RATE:
            faults.append(f"trial {repeat+1}: refused {count}/{len(CLEAN)} clean images")
    return {"qualified": not faults, "faults": faults, "clean_rejects": clean_rejects}


_CACHE = {}


def qualified_models() -> list[tuple[str, str]]:
    """Only replayable, current proof. Cache is keyed by every input's hash."""
    try:
        fingerprint = contract()
    except OSError:
        return []
    out = []
    for path in sorted(RECORDS.glob("*.json")):
        try:
            raw = path.read_bytes()
            record = json.loads(raw)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(record["started_at"])).total_seconds()
            if not 0 <= age <= MAX_AGE_DAYS * 86400:
                continue
            # Day in key prevents stale records being cached forever.
            key = (fingerprint, hashlib.sha256(raw).hexdigest(), datetime.now(timezone.utc).date())
            if key not in _CACHE:
                result = evaluate(record)
                _CACHE[key] = ((record["provider"], record["model"]) if result["qualified"] else None)
            if _CACHE[key] is not None and _CACHE[key] not in out:
                out.append(_CACHE[key])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, indent=2) + "\n")
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Evidence file; existing evidence is never overwritten")
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--interval-seconds", type=float, default=40,
                        help="Minimum spacing for the offline free-quota test")
    args = parser.parse_args()
    if (args.provider, args.model) not in model_ids():
        parser.error("unknown exact image model")
    if not 1 <= args.max_requests <= len(list(batches())):
        parser.error("max-requests must be between 1 and 24")
    if args.interval_seconds < 0:
        parser.error("interval-seconds must not be negative")
    if args.output.exists():
        parser.error("evidence already exists; choose a new file")
    record = {"provider": args.provider, "model": args.model, "contract": contract(),
              "started_at": datetime.now(timezone.utc).isoformat(), "observations": [], "errors": []}
    save(args.output, record)
    last_request = None
    for index, (repeat, group) in enumerate(batches()):
        if index >= args.max_requests:
            break
        sheet, mapping, control = prepare(group)
        try:
            if last_request is not None:
                time.sleep(max(0, args.interval_seconds - (time.monotonic() - last_request)))
            last_request = time.monotonic()
            answer, actual = llm.look_once(review.SYSTEM, review.group_prompt(mapping, control),
                                          review.SCHEMA, sheet, provider=args.provider, model=args.model)
            record["observations"].append({"repeat": repeat, "cases": [c["id"] for c in group],
                "sheet_sha256": hashlib.sha256(sheet).hexdigest(), "actual_model": actual, "answer": answer})
            # Do not spend a full sweep after a mandatory control or known
            # serious defect was missed. This run cannot qualify that model.
            review.parse_vetoes(answer, set(mapping) | {control}, control)
            for panel, number in mapping.items():
                case = group[number-1]
                found = review.observed_codes(answer, panel)
                if case["codes"] and not found.intersection(case["codes"]):
                    raise ValueError("missed known defect: " + case["id"])
        except Exception as exc:
            record["errors"].append({"request": index+1, "type": type(exc).__name__,
                "reason": str(exc)[:500], "answer": getattr(exc, "answer", None)})
            save(args.output, record)
            print(f"Qualification stopped: {type(exc).__name__}. Evidence: {args.output}")
            return 1
        save(args.output, record)
        print(f"Request {index+1}/24 saved", flush=True)
    result = evaluate(record)
    record["result"] = result
    save(args.output, record)
    print(json.dumps(result))
    return int(not result["qualified"])


if __name__ == "__main__":
    raise SystemExit(main())
