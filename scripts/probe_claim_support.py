#!/usr/bin/env python3
"""Test one real source claim without saving it to the active citation pool.

Uses existing free-provider configuration and records actual quota usage through
the engine. This is not a dry run or a publication command.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/suresilly-carousel/scripts"))
import bibliography


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("author", "title", "phrase", "claim", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--year", required=True, type=int)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error("output already exists; preserve the earlier result")
    candidate = {key: getattr(args, key) for key in ("author", "title", "year", "phrase", "claim")}
    result = {"at": datetime.now(timezone.utc).isoformat(), "candidate": candidate,
              "active_pool_changed": False, "status": "started"}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the evidence path before network calls; never overwrite a trial.
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    try:
        result["citation"] = bibliography.verify(candidate, "manual-audit", [])
        result["status"] = "checked"
    except bibliography.Unverified as exc:
        result.update(status="refused", reason=str(exc))
        if getattr(exc, "evidence", None) is not None:
            result["rejected_evidence"] = exc.evidence
    except Exception as exc:
        # Keep evidence of an interrupted/broken test, never a success flag.
        result.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(output)
    print(f"{result['status']}: {result.get('reason', 'source record saved outside the active pool')}")
    print(f"Evidence: {output}")
    return 0 if result["status"] == "checked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
