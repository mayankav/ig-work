#!/usr/bin/env python3
"""Validate saved claims. Quarantine rejected writes without losing usage records."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / ".agents/skills/suresilly-carousel"
sys.path.insert(0, str(ENGINE / "scripts"))
import bibliography


def faults(data: dict) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get("citations"), list):
        return ["the citation pool is not a list"]
    errors = []
    for item in data["citations"]:
        try:
            bibliography.validate_citation(item)
        except bibliography.Unverified as exc:
            errors.append(f"{item.get('id', '?') if isinstance(item, dict) else '?'}: {exc}")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarantine", action="store_true")
    args = ap.parse_args()
    path = ENGINE / "references/citations.json"
    raw = path.read_text()
    try:
        errors = faults(json.loads(raw))
    except ValueError as exc:
        errors = [f"invalid citation JSON: {exc}"]
    if not errors:
        print("Saved claims passed.")
        return 0
    print("Invalid saved claims: " + "; ".join(errors), file=sys.stderr)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.write("reason=Invalid saved claims: " + "; ".join(errors).replace("\n", " ") + "\n")
    if args.quarantine:
        # Never restore state/ here: it contains real quota and usage, even if
        # a content write was bad. Keep the rejected bytes for diagnosis.
        run = os.environ.get("GITHUB_RUN_ID", "local")
        if not run.replace("-", "").isalnum():
            raise ValueError("invalid run id")
        rejected = ROOT / "state/rejected" / run
        rejected.mkdir(parents=True, exist_ok=True)
        (rejected / "citations.txt").write_text(raw)
        (rejected / "faults.json").write_text(json.dumps(errors, indent=2) + "\n")
        baseline = subprocess.check_output(
            ["git", "show", f"HEAD:{path.relative_to(ROOT)}"], cwd=ROOT, text=True)
        if faults(json.loads(baseline)):
            # A broken checkout cannot become a valid baseline by restoring it.
            raise ValueError("the committed citation pool is invalid too")
        path.write_text(baseline)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
