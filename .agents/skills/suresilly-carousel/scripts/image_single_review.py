"""Experimental single-image veto protocol. Not enabled for production use."""
from __future__ import annotations

import hashlib

import cv2
import numpy as np

import llm

VERSION = "single-visible-parts-2"
PROVIDER = "gemini"
MODEL = "gemini-3.5-flash"
SYSTEM = """Inspect the supplied cartoon image. Analyse fully visible and
partially visible body parts, using only their visible shapes and connections.
Do not infer, count or analyse any part that is not visible. Do not invent a
hidden connection or complete a hidden limb. Occlusion alone is not a fault or
uncertainty: do not list an unseen part as something that needs checking.
Count each visible or partially visible limb once per character, not each
separate exposed fragment. Stop tracing where it disappears behind an object.
Distinguish arms and legs from tails, furniture and marks. Describe each
character separately. A count alone is not evidence of a defect. Do not compare
counts with an expected number. Profiles, closed eyes, tilted heads and separate
complete characters are not faults by themselves.
Report uncertainty only about an ambiguous VISIBLE shape or visible connection,
with its location and the ambiguity; do not report generic confidence doubts.
Inspect visible and partially visible eyes for blank open eyes, missing pupils,
stray marks and mismatched eyes. Also inspect visible parts for disconnected
parts, extra limbs, heads or eyes, merged bodies, lettering and off-palette marks.
Each fault must name its location and describe visible evidence supporting it.
Return observations and faults, never permission to publish. Return JSON matching
the requested fields."""
USER = """For each donkey, describe and count only fully visible and partially
visible arms and legs. Describe the visible portion and visible connections of
each limb; state where the visible portion ends without guessing what is hidden.
Describe shapes that could be confused with limbs. Inspect the visible face and
other visible artwork for the listed faults. Do not assess unseen parts."""
CODES = ("extra_limb", "disconnected", "extra_head", "extra_eye", "merged_body",
         "blank_eye", "stray_eye_mark", "mismatched_eyes", "text", "off_palette")
TEXTS = {"type": "array", "items": {"type": "string", "minLength": 1}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["figures", "other_shapes", "uncertainty", "faults"],
    "properties": {
        "figures": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["location", "arms", "legs", "arm_descriptions", "leg_descriptions"],
            "properties": {
                "location": {"type": "string", "minLength": 1},
                "arms": {"type": "integer", "minimum": 0, "maximum": 8},
                "legs": {"type": "integer", "minimum": 0, "maximum": 8},
                "arm_descriptions": TEXTS, "leg_descriptions": TEXTS,
            }}},
        "other_shapes": TEXTS, "uncertainty": TEXTS,
        "faults": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["code", "fault", "location", "visible_evidence"], "properties": {
                "code": {"type": "string", "enum": list(CODES)},
                "fault": {"type": "string", "minLength": 4},
                "location": {"type": "string", "minLength": 1},
                "visible_evidence": {"type": "string", "minLength": 4},
            }}},
    },
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare(raw: bytes) -> bytes:
    """Full original frame, neutral transparency background, no crop or resize."""
    art = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
    if art is None or art.ndim != 3 or art.shape[2] != 4:
        raise ValueError("expected RGBA artwork")
    if not np.any(art[:, :, 3]):
        raise ValueError("empty artwork")
    alpha = art[:, :, 3:4].astype(np.float32) / 255
    frame = (art[:, :, :3] * alpha + 128 * (1-alpha)).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("image encoding failed")
    return encoded.tobytes()


def assessment(answer: dict) -> dict:
    """Separate visible fault reports from unresolved visible details. No approval."""
    if llm.validate(answer, SCHEMA):
        raise ValueError("invalid single-image answer")
    found = {item["code"] for item in answer["faults"]}
    for figure in answer["figures"]:
        for kind in ("arms", "legs"):
            if type(figure[kind]) is not int:
                raise ValueError("limb count must be an integer")
            descriptions = figure[kind[:-1] + "_descriptions"]
            if len(descriptions) != figure[kind] or any(not s.strip() for s in descriptions):
                raise ValueError("limb count does not match its descriptions")
    if any(not f[key].strip() for f in answer["faults"]
           for key in ("fault", "location", "visible_evidence")):
        raise ValueError("missing visible fault evidence")
    if any(not note.strip() for note in answer["uncertainty"]):
        raise ValueError("empty visible uncertainty description")
    return {"codes": sorted(found), "uncertainty": list(answer["uncertainty"]),
            "disposition": "reject" if found else "unresolved" if answer["uncertainty"] else "no_fault_reported"}


def observed_codes(answer: dict) -> set[str]:
    result = assessment(answer)
    # A concrete fault still rejects the image despite uncertainty elsewhere.
    if result["disposition"] == "unresolved":
        raise ValueError("single-image reviewer is uncertain about visible evidence")
    return set(result["codes"])


def check_control(answer: dict) -> None:
    if "extra_limb" not in observed_codes(answer):
        raise ValueError("single-image reviewer missed the known extra leg")
