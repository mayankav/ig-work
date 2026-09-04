"""Repair outline fields without replacing the outline or its chosen source."""
from copy import deepcopy
import json

import draft_repair
import llm

LOCKED = {"citation_id", "claim_index"}


def projection(plan):
    """Stable short field IDs avoid quoted JSON inside schema enums.

    Text is plain text. Numbers and dependency/export arrays use JSON text.
    Whole beats, hooks, protocol objects and menu arrays are never editable.
    """
    values, paths = {}, {}

    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if len(path) == 0 and key in LOCKED:
                    continue
                walk(child, path + [key])
        elif isinstance(value, list) and (not path or path[-1] not in ("depends_on", "exports")):
            for index, child in enumerate(value):
                walk(child, path + [index])
        else:
            key = f"field_{len(values)+1}"
            values[key] = value if isinstance(value, str) else json.dumps(value)
            paths[key] = (path, isinstance(value, str))
    walk(plan, [])
    return values, paths


def describe(plan):
    values, paths = projection(plan)
    return {key: {"path": "/" + "/".join(map(str, path)),
                  "encoding": "text" if text else "JSON", "value": values[key]}
            for key, (path, text) in paths.items()}


def schema(plan, faults):
    return draft_repair.schema(projection(plan)[0], faults)


def apply(plan, faults, reply, plan_schema, verify):
    values, paths = projection(plan)
    shape = {"type":"object", "additionalProperties":False,
             "required":list(values), "properties":{key:{"type":"string"} for key in values}}

    def rebuild(edited):
        result = deepcopy(plan)
        for key, (path, text) in paths.items():
            value = edited[key] if text else json.loads(edited[key])
            target = result
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
        return result

    def checked(edited):
        try:
            result = rebuild(edited)
        except (ValueError, TypeError):
            return list(faults) + ["invalid field encoding"]
        invalid = llm.validate(result, plan_schema)
        if invalid:
            return list(faults) + ["invalid outline field shape"]
        return verify(result)

    edited, remaining = draft_repair.apply(values, faults, reply, shape, checked)
    return rebuild(edited), remaining
