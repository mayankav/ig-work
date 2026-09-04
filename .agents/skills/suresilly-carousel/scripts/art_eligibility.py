"""One eligibility rule for fresh, imported, saved and reference artwork.

Receipts contain the actual group inputs and response, not an `approved` flag.
Selection replays the inspection sheet, coverage, control and veto checks. A
receipt is bound to exact PNG bytes, current check code and a qualified model.
No keys or requests are needed to use a checked library image.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

import cv2
import numpy as np

import art_checks
import owner_art
import image_qualification
import image_review
import llm

STORE = Path(__file__).resolve().parents[1] / "mascot/checks"
MAX_IMAGE_BYTES = 16 * 1024 * 1024


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def contract() -> str:
    return digest((image_qualification.contract() + digest(Path(__file__).read_bytes())
                   + digest(Path(art_checks.__file__).read_bytes())
                   + digest(Path(art_checks.cutout.__file__).read_bytes())).encode())


def _json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".checking-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _decode(raw: bytes):
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("artwork exceeds inspection size limit")
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise ValueError("inspection needs an RGBA PNG")
    return image


def _replay(record: dict, raw: bytes) -> tuple[str, ...]:
    if record["contract"] != contract():
        return ("artwork check version changed",)
    if (record["provider"], record["model"]) not in image_qualification.qualified_models():
        return ("artwork reviewer no longer has current qualification",)
    when = datetime.fromisoformat(record["checked_at"])
    if when.tzinfo is None or when > datetime.now(timezone.utc):
        return ("invalid artwork check time",)
    if record["actual_model"] != record["provider"] + "/" + record["model"]:
        return ("different image model answered",)
    if record.get("error"):
        return ("artwork review failed: " + str(record["error"]),)
    inputs = record["inputs"]
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= image_review.GROUP_SIZE:
        return ("invalid artwork group",)
    encoded = [base64.b64decode(item, validate=True) for item in inputs]
    if raw not in encoded:
        return ("artwork bytes were not inspected",)
    sheet, mapping, control = image_review.prepare_group({
        n: _decode(value) for n, value in enumerate(encoded, 1)})
    if digest(sheet) != record["sheet_sha256"]:
        return ("artwork inspection sheet changed",)
    vetoes = image_review.parse_vetoes(record["answer"], set(mapping) | {control}, control)
    # If duplicate bytes occupied two panels, a veto in either still blocks.
    return tuple(vetoes[panel] for panel, n in mapping.items()
                 if encoded[n-1] == raw and panel in vetoes)


def faults_bytes(raw: bytes) -> tuple[str, ...]:
    pixel = art_checks.pixel_faults_bytes(raw)
    if pixel:
        return pixel
    if owner_art.enabled():
        return ()
    try:
        index = json.loads((STORE / "index" / (digest(raw) + ".json")).read_bytes())
        receipt = index["receipt"]
        if not isinstance(receipt, str) or len(receipt) != 64 or any(
                c not in "0123456789abcdef" for c in receipt):
            raise ValueError("invalid receipt name")
        evidence = (STORE / "reviews" / (receipt + ".json")).read_bytes()
        if digest(evidence) != receipt:
            return ("artwork check record changed",)
        return _replay(json.loads(evidence), raw)
    except (OSError, ValueError, TypeError, KeyError, cv2.error) as exc:
        return (f"artwork has no usable body and eye check: {type(exc).__name__}",)


def faults(path: Path) -> tuple[str, ...]:
    try:
        return faults_bytes(path.read_bytes())
    except OSError:
        return ("artwork cannot be read",)


def proof(raw: bytes) -> dict:
    if owner_art.enabled():
        return owner_art.proof(raw)
    problems = faults_bytes(raw)
    if problems:
        raise ValueError("; ".join(problems))
    index = json.loads((STORE / "index" / (digest(raw) + ".json")).read_bytes())
    return {"sha256": digest(raw), "receipt": index["receipt"]}


def check_proof(value: dict) -> None:
    """Validate the exact image proof retained with a rendered deck."""
    if value.get("policy") == owner_art.POLICY:
        owner_art.check(value)
        return
    try:
        for name in ("sha256", "receipt"):
            if (not isinstance(value[name], str) or len(value[name]) != 64
                    or any(c not in "0123456789abcdef" for c in value[name])):
                raise ValueError("invalid image proof")
        evidence = (STORE / "reviews" / (value["receipt"] + ".json")).read_bytes()
        if digest(evidence) != value["receipt"]:
            raise ValueError("artwork check record changed")
        for encoded in json.loads(evidence)["inputs"]:
            raw = base64.b64decode(encoded, validate=True)
            if digest(raw) == value["sha256"]:
                if proof(raw) != value:
                    raise ValueError("artwork review changed after rendering")
                return
        raise ValueError("rendered artwork was not inspected")
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("rendered artwork has no usable check record") from exc


def evidence_paths(value: dict) -> list[Path]:
    check_proof(value)
    if value.get("policy") == owner_art.POLICY:
        return []
    return [STORE / "reviews" / (value["receipt"] + ".json"),
            STORE / "index" / (value["sha256"] + ".json")]


def _save(record: dict, inputs: list[bytes]) -> None:
    evidence = _json(record)
    receipt = digest(evidence)
    _write(STORE / "reviews" / (receipt + ".json"), evidence)
    for raw in inputs:
        # A later failed inspection replaces the pointer, never the evidence.
        _write(STORE / "index" / (digest(raw) + ".json"), _json({"receipt": receipt}))


def check_paths(paths: dict[int, Path], log=print) -> dict[int, str]:
    """Inspect at most nine exact files in at most three single requests.

    This operation saves evidence, including failed replies. It does not add
    artwork to the library. Promotion remains after the complete deck check.
    """
    if not paths:
        return {}
    if len(paths) > image_review.GROUP_SIZE * image_review.MAX_REQUESTS:
        return {n: "image review request budget exceeded" for n in paths}
    try:
        provider, model = image_review.model_for_review()
        version = contract()
    except Exception as exc:
        return {n: f"image review unavailable: {type(exc).__name__}" for n in paths}
    rejected, candidates = {}, {}
    for n, path in sorted(paths.items()):
        try:
            raw = path.read_bytes()
            problems = art_checks.pixel_faults_bytes(raw)
            if problems:
                raise ValueError("; ".join(problems))
            _decode(raw)
            candidates[n] = raw
        except (OSError, ValueError, cv2.error) as exc:
            rejected[n] = str(exc)
    numbers = list(candidates)
    for start in range(0, len(numbers), image_review.GROUP_SIZE):
        group = numbers[start:start+image_review.GROUP_SIZE]
        inputs = [candidates[n] for n in group]
        record = {"contract": version, "provider": provider, "model": model,
                  "checked_at": datetime.now(timezone.utc).isoformat(),
                  "inputs": [base64.b64encode(raw).decode() for raw in inputs],
                  "actual_model": "", "error": ""}
        try:
            sheet, mapping, control = image_review.prepare_group({
                n: _decode(raw) for n, raw in enumerate(inputs, 1)})
            record["sheet_sha256"] = digest(sheet)
            answer, actual = llm.look_once(image_review.SYSTEM,
                image_review.group_prompt(mapping, control), image_review.SCHEMA,
                sheet, provider=provider, model=model)
            record.update(answer=answer, actual_model=actual)
            if actual != f"{provider}/{model}":
                raise ValueError("image model changed during review")
            image_review.parse_vetoes(answer, set(mapping) | {control}, control)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        try:
            _save(record, inputs)
            for n in group:
                problems = faults(paths[n])
                if paths[n].read_bytes() != candidates[n]:
                    problems = ("artwork changed during inspection",)
                if problems:
                    rejected[n] = "; ".join(problems)
        except (OSError, ValueError, TypeError) as exc:
            rejected.update({n: f"image evidence could not be saved: {exc}" for n in group})
    log(f"  image checks: {len(rejected)} of {len(paths)} rejected")
    return rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    args = parser.parse_args()
    rejected = check_paths(dict(enumerate(args.images, 1)))
    for number, reason in rejected.items():
        print(f"{args.images[number-1]}: {reason}")
    return int(bool(rejected))


if __name__ == "__main__":
    raise SystemExit(main())
