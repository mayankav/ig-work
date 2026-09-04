"""Bounded image vetoes. A missed control invalidates the entire response.

This is not model qualification or library eligibility. Those checks must run
before this module is used to release artwork. No model reply approves art.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

import llm

VERSION = "body-face-feet-counts-3"
GROUP_SIZE = 3
MAX_REQUESTS = 3
TILE = 512
CONTROL_PATH = Path(__file__).resolve().parents[1] / "tests/fixtures/rejected_art/extra_leg.png"
SYSTEM = """Inspect every numbered cartoon donkey panel. Each row shows the
full artwork on the left, a larger upper-body view in the middle, and a larger
lower-body view on the right. These are THREE views of the SAME pose, not three
different characters. Trace each arm and leg back to its body. Count limbs
per character: Silly has TWO arms and TWO legs. Report extra or disconnected
limbs, extra heads or eyes, merged bodies, blank open eyes, stray eye marks,
and mismatched eyes. Closed eyes, profiles, hidden limbs, tilted heads, props,
tails, and separate complete characters are not faults by themselves.
Report coverage for every panel in inspected. List any uncertainty in uncertain;
do not silently ignore a panel or a part you cannot judge. List faults with the
panel number, a code, and the visible reason. Use codes extra_limb, disconnected,
extra_head, extra_eye, merged_body, blank_eye, stray_eye_mark, mismatched_eyes.
The fields are observations and vetoes, never permission to publish.
Return exactly inspected, uncertain, figures, faults as JSON. No other text."""
SYSTEM += """ inspected and uncertain must be arrays of integer panel numbers,
not strings, descriptions, or names. Each faults entry must contain exactly
panel (integer), code (one of the fault codes above), and fault (a short visible
reason). Use empty arrays when there is no observation of that kind."""
SYSTEM += """ For figures, report one object per visible character: panel
(integer), arms (number of visible arms), legs (number of visible legs).
First trace every visible hoof back to its limb and body. Do not assume the
expected count. Count a bent rear leg even if two other feet touch the floor.
Do not count a tail, chair leg, or motion mark as a limb. Report counts for each
character separately in two-character scenes. Hidden limbs are not missing
limbs. If you cannot tell whether a shape is another limb, mark that panel
uncertain rather than silently treating the shape as a prop."""
SCHEMA = {
    "type": "object", "required": ["inspected", "uncertain", "figures", "faults"],
    "additionalProperties": False,
    "properties": {
        "inspected": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 4}},
        "uncertain": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 4}},
        "figures": {"type": "array", "items": {
            "type": "object", "required": ["panel", "arms", "legs"], "additionalProperties": False,
            "properties": {
                "panel": {"type": "integer", "minimum": 1, "maximum": 4},
                "arms": {"type": "integer", "minimum": 0, "maximum": 8},
                "legs": {"type": "integer", "minimum": 0, "maximum": 8},
            }}},
        "faults": {"type": "array", "items": {
            "type": "object", "required": ["panel", "code", "fault"],
            "additionalProperties": False,
            "properties": {
                "panel": {"type": "integer", "minimum": 1, "maximum": 4},
                "code": {"type": "string", "enum": ["extra_limb", "disconnected", "extra_head",
                    "extra_eye", "merged_body", "blank_eye", "stray_eye_mark", "mismatched_eyes"]},
                "fault": {"type": "string", "minLength": 4, "maxLength": 160},
            },
        }},
    },
}


def model_for_review() -> tuple[str, str]:
    """Only a configured model with current, replayable test evidence may veto."""
    import image_qualification
    qualified = image_qualification.qualified_models()
    for provider, _ in llm.chain(llm.PROVIDERS):
        for owner, model in qualified:
            if provider == owner and llm.configured(provider):
                return provider, model
    raise llm.ModelRefused("no image review model has current qualification")


def ready() -> bool:
    try:
        model_for_review()
        return True
    except (llm.ModelRefused, OSError, ValueError):
        return False


def _paste(sheet, image, top, left):
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise ValueError("inspection needs RGBA artwork")
    h, w = image.shape[:2]
    scale = min((TILE - 48) / w, (TILE - 72) / h)
    small = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    y, x = top + 60 + (TILE - 72 - h) // 2, left + (TILE - w) // 2
    alpha = small[:, :, 3:4].astype(np.float32) / 255
    sheet[y:y+h, x:x+w] = (small[:, :, :3] * alpha + 128 * (1-alpha)).astype(np.uint8)


def inspection_sheet(panels: dict[int, np.ndarray]) -> bytes:
    if not 1 <= len(panels) <= GROUP_SIZE + 1:
        raise ValueError("inspection sheet has too many panels")
    sheet = np.full((len(panels) * TILE, 3 * TILE, 3), 128, np.uint8)
    for row, (number, art) in enumerate(sorted(panels.items())):
        if art is None or art.ndim != 3 or art.shape[2] != 4:
            raise ValueError("unreadable inspection image")
        points = cv2.findNonZero((art[:, :, 3] > 0).astype(np.uint8))
        if points is None:
            raise ValueError("empty inspection image")
        x, y, w, h = cv2.boundingRect(points)
        # Retain the full width, including both faces in a two-character pose.
        # Qualification uses this exact crop; uncertainty must veto the group.
        upper = art[y:y+max(1, int(h * .65)), x:x+w]
        lower = art[y+int(h * .5):y+h, x:x+w]
        _paste(sheet, art, row * TILE, 0)
        _paste(sheet, upper, row * TILE, TILE)
        _paste(sheet, lower, row * TILE, TILE * 2)
        for col, name in enumerate(("body", "upper", "lower")):
            cv2.putText(sheet, f"{number} {name}", (col*TILE+16, row*TILE+42),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2, cv2.LINE_AA)
    ok, data = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise ValueError("inspection sheet could not be encoded")
    return data.tobytes()


def parse_vetoes(answer: dict, panels: set[int], control: int) -> dict[int, str]:
    problems = llm.validate(answer, SCHEMA)
    if problems or set(answer) != set(SCHEMA["properties"]):
        raise ValueError("invalid image reply")
    inspected = answer["inspected"]
    if any(type(n) is not int for n in inspected) or set(inspected) != panels or len(inspected) != len(panels):
        raise ValueError("image reply did not cover each panel exactly once")
    if answer["uncertain"]:
        raise ValueError("image reviewer is uncertain")
    faults = {}
    caught_control = False
    if {f["panel"] for f in answer["figures"]} != panels:
        raise ValueError("image reply did not describe a figure in every panel")
    for figure in answer["figures"]:
        if any(type(figure[key]) is not int for key in ("panel", "arms", "legs")):
            raise ValueError("invalid observed limb count")
        if figure["arms"] > 2 or figure["legs"] > 2:
            panel = figure["panel"]
            faults[panel] = f"one figure has {figure['arms']} visible arms and {figure['legs']} visible legs"
            caught_control |= panel == control
    for item in answer["faults"]:
        n = item["panel"]
        if type(n) is not int or n not in panels:
            raise ValueError("image reply names an unknown panel")
        if not item["fault"].strip():
            raise ValueError("image reply gives no visible fault")
        if n == control and item["code"] == "extra_limb":
            caught_control = True
        faults[n] = item["fault"].strip()
    if not caught_control:
        raise ValueError("image reviewer missed the known extra leg")
    return faults


def observed_codes(answer: dict, panel: int) -> set[str]:
    """Observed counts can add a veto, never remove one."""
    codes = {f["code"] for f in answer["faults"] if f["panel"] == panel}
    if any(f["panel"] == panel and (f["arms"] > 2 or f["legs"] > 2) for f in answer["figures"]):
        codes.add("extra_limb")
    return codes


def prepare_group(tiles: dict[int, np.ndarray]):
    """Identical panel construction for production and model qualification."""
    if not 1 <= len(tiles) <= GROUP_SIZE:
        raise ValueError("a review group needs one to three candidates")
    if not CONTROL_PATH.is_file():
        raise ValueError("image review control missing")
    control_art = cv2.imread(str(CONTROL_PATH), cv2.IMREAD_UNCHANGED)
    if control_art is None:
        raise ValueError("image review control unreadable")
    group = sorted(tiles)
    digest = hashlib.sha256(b"".join(tiles[n].tobytes() for n in group)).digest()
    control = digest[0] % (len(group) + 1) + 1
    labels = [n for n in range(1, len(group)+2) if n != control]
    mapping = dict(zip(labels, group))
    panels = {label: tiles[slide] for label, slide in mapping.items()}
    panels[control] = control_art
    return inspection_sheet(panels), mapping, control


def group_prompt(mapping: dict[int, int], control: int) -> str:
    return ("Inspect panels " + json.dumps(sorted(set(mapping) | {control}))
            + ". Inspect all three views of each panel.")


def review(tiles: dict[int, np.ndarray], log=print) -> dict[int, str]:
    """At most three requests, each holding three candidates and one control."""
    if not tiles:
        return {}
    if len(tiles) > GROUP_SIZE * MAX_REQUESTS:
        return {n: "image review request budget exceeded" for n in tiles}
    try:
        provider, model = model_for_review()
    except Exception as exc:
        return {n: f"image review unavailable: {type(exc).__name__}" for n in tiles}
    rejected = {}
    numbers = sorted(tiles)
    for start in range(0, len(numbers), GROUP_SIZE):
        group = numbers[start:start+GROUP_SIZE]
        try:
            sheet, mapping, control = prepare_group({n: tiles[n] for n in group})
            answer, actual = llm.look_once(SYSTEM,
                group_prompt(mapping, control), SCHEMA, sheet, provider=provider, model=model)
            if actual != f"{provider}/{model}":
                raise ValueError("image model changed during review")
            faults = parse_vetoes(answer, set(mapping) | {control}, control)
            rejected.update({mapping[n]: why for n, why in faults.items() if n in mapping})
        except Exception as exc:
            rejected.update({n: f"image group unchecked: {type(exc).__name__}: {str(exc)[:100]}"
                             for n in group})
    log(f"  image review: {len(rejected)} of {len(tiles)} rejected")
    return rejected
