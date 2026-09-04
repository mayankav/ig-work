"""Apply bounded text edits only when the complete draft checks prove progress."""
from copy import deepcopy

import llm
from outcomes import fault_signature

MAX_EDITS = 12


def fault_map(faults):
    """Short IDs survive structured-output quoting; descriptions remain data."""
    return {f"fault-{i}": text for i, text in enumerate(dict.fromkeys(faults), 1)}


def fields(value, prefix=""):
    """Existing string leaves only: no new keys, deleted fields or resized arrays."""
    if isinstance(value, str):
        return {prefix: value}
    pairs = value.items() if isinstance(value, dict) else enumerate(value)
    result = {}
    for key, child in pairs:
        result.update(fields(child, f"{prefix}/{key}"))
    return result


def put(value, path, text):
    parts = path.split("/")[1:]
    for part in parts[:-1]:
        value = value[int(part)] if isinstance(value, list) else value[part]
    key = int(parts[-1]) if isinstance(value, list) else parts[-1]
    value[key] = text


def schema(draft, faults):
    return {"type": "object", "additionalProperties": False, "required": ["edits"],
            "properties": {"edits": {"type": "array", "minItems": 1,
                "maxItems": MAX_EDITS, "items": {"type": "object",
                    "additionalProperties": False, "required": ["path", "value", "fault"],
                    "properties": {"path": {"type": "string", "enum": list(fields(draft))},
                                   "value": {"type": "string"},
                                   "fault": {"type": "string", "enum": list(fault_map(faults))}}}}}}


def apply(draft, faults, reply, draft_schema, verify):
    """Keep an edit set only if it removes faults without introducing others.

    The model's stated reason is not evidence. Recheck the assembled deck.
    Then restore each edited field in turn whenever doing so preserves or
    improves the remaining faults. This removes unsolicited clean-line edits.
    All untouched leaves remain byte-for-byte identical to the prior draft.
    """
    if llm.validate(reply, schema(draft, faults)):
        return deepcopy(draft), list(faults)
    old = fields(draft)
    edits = reply["edits"]
    paths = [e["path"] for e in edits]
    if len(paths) != len(set(paths)):
        return deepcopy(draft), list(faults)
    candidate = deepcopy(draft)
    for edit in edits:
        put(candidate, edit["path"], edit["value"])
    if llm.validate(candidate, draft_schema):
        return deepcopy(draft), list(faults)
    remaining = verify(candidate)
    if not set(fault_signature(remaining)) < set(fault_signature(faults)):
        return deepcopy(draft), list(faults)
    for path in paths:
        trial = deepcopy(candidate)
        put(trial, path, old[path])
        trial_faults = verify(trial)
        if set(fault_signature(trial_faults)) <= set(fault_signature(remaining)):
            candidate, remaining = trial, trial_faults
    # Verify exactly the returned object, not an earlier candidate.
    return candidate, verify(candidate)
