#!/usr/bin/env python3
"""One free Groq format check. No deck creation, source approval or posting."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / ".agents/skills/suresilly-carousel/scripts"
sys.path.insert(0, str(ENGINE))
import draft_repair
import llm
import writer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    draft = {"script": {"new": "You ask the bike shop when the bike will be ready."},
             "caption": "The bike is at the shop. Keep the pickup time clear."}
    spec = {"type": "object", "additionalProperties": False,
            "required": ["script", "caption"], "properties": {
                "script": {"type": "object", "additionalProperties": False,
                           "required": ["new"], "properties": {
                               "new": {"type": "string", "maxLength": 220}}},
                "caption": {"type": "string", "maxLength": 900}}}

    def verify(value):
        return writer.check_spoken("### Slide 5 · Script\n- **Say:** " + value["script"]["new"])

    faults = verify(draft)
    schema = draft_repair.schema(draft, faults)
    evidence = {"at": datetime.now(timezone.utc).isoformat(), "status": "started",
                "scope": "edit format and merge only; not a full-deck release test",
                "provider": "groq", "model": llm.GROQ_MODEL, "draft": draft,
                "faults": faults, "schema": schema, "http_requests": 0,
                "repair_code_sha256": hashlib.sha256((ENGINE / "draft_repair.py").read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(evidence, handle, indent=2)
    original_post = llm._post

    def once(url, payload, headers, **kwargs):
        if evidence["http_requests"]:
            raise llm.ModelRefused("The one-request trial budget is exhausted.")
        evidence["http_requests"] += 1
        payload = dict(payload, max_completion_tokens=1024)
        return original_post(url, payload, headers, **kwargs)

    llm._post = once
    try:
        user = ("Repair this test draft. Return only edits in the schema. The Say line must "
                "be words spoken to the bike shop, not a direction to the reader. "
                "Do not change the caption.\nDRAFT:\n" + json.dumps(draft)
                + "\nFAULTS:\n" + json.dumps(draft_repair.fault_map(faults)))
        raw = llm.call_groq("Return only the requested JSON field edits. Fix the listed faults.",
                            user, 0.4, schema)
        evidence["raw_reply"] = raw
        reply = llm.extract_json(raw)
        evidence["reply"] = reply
        value, remaining = draft_repair.apply(draft, faults, reply, spec, verify)
        evidence.update(repaired=value, remaining_faults=remaining)
        evidence["status"] = "checked" if not remaining and value["caption"] == draft["caption"] else "refused"
    except Exception as exc:
        evidence.update(status="error", reason=f"{type(exc).__name__}: {exc}")
    finally:
        llm._post = original_post
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("x") as handle:
        json.dump(evidence, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(args.output)
    print(json.dumps({key: evidence.get(key) for key in ("status", "http_requests", "reason")}))
    print(f"Evidence: {args.output}")
    return 0 if evidence["status"] == "checked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
