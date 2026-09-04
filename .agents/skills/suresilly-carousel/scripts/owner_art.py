"""Explicit V1 artwork policy: pixel checks plus an owner review window.

This is not a model approval. Publishing also needs a live review-window claim.
"""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import cv2
import numpy as np
import art_checks

POLICY = 'owner-window-v1'


def enabled():
    return os.environ.get('SS_REVIEW_WINDOW_V1') == '1'


def contract():
    return hashlib.sha256(Path(__file__).read_bytes() + Path(art_checks.__file__).read_bytes()
                          + Path(art_checks.cutout.__file__).read_bytes()).hexdigest()


def proof(raw):
    if not enabled(): raise ValueError('Owner review policy is not enabled')
    faults = art_checks.pixel_faults_bytes(raw)
    if faults: raise ValueError('; '.join(faults))
    return {'policy': POLICY, 'sha256': hashlib.sha256(raw).hexdigest(),
            'pixel_contract': contract(), 'png': base64.b64encode(raw).decode()}


def check(value):
    if not enabled(): raise ValueError('Owner review artwork requires the V1 review workflow')
    raw = base64.b64decode(value['png'], validate=True)
    if proof(raw) != value: raise ValueError('Owner review artwork or pixel checks changed')
    return raw


def generate_one(slide, destination, *, previous=None, budget=None, ledger=None):
    """Draw once from the slide brief and character references, never its old image."""
    if not enabled(): raise ValueError('Owner review policy is not enabled')
    import poses_flux as flux
    import fresh_poses
    brief = (slide.get('mascot') or '').strip()
    if len(brief) < fresh_poses.MIN_BRIEF: raise ValueError('Slide has no usable image brief')
    # Identity references only. Never use the current image as a generation input.
    references = flux.pick_references(names=list(flux.ANCHORS), count=len(flux.ANCHORS))
    if previous is not None:
        references = [(name, raw) for name, raw in references if raw != previous]
    if not references: raise ValueError('No independent character reference is available')
    ledger = ledger or (flux.Ledger(budget=budget) if budget is not None else flux.Ledger())
    reserved = flux.estimate_neurons(1024, 1024, len(references))
    ledger.check(reserved)
    account, token = flux.credentials()
    ledger.spend(reserved, note='owner-review fresh image')
    prompt = flux.build_prompt(brief) + '\nCreate a new composition for this brief. Use the references only for character identity. Do not copy their scene or pose.'
    blob, billed = flux.generate(prompt, references, width=1024, height=1024,
                                seed=secrets.randbelow(2**31), account=account, token=token,
                                timeout=fresh_poses.PER_POSE_TIMEOUT)
    ledger.reconcile(reserved, billed, note='owner-review fresh image')
    frame = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
    if frame is None: raise ValueError('Generator returned no usable image')
    flux.assert_no_text(frame, 'new image')
    rgba = fresh_poses._matte(flux.correct_palette(frame))
    ok, buffer = cv2.imencode('.png', rgba)
    if not ok: raise ValueError('New image could not be encoded')
    raw = buffer.tobytes()
    proof(raw)
    if raw == previous: raise ValueError('Generator repeated the old image')
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return destination


def generate_deck(slides, fallback, destination, budget=None):
    out = dict(fallback)
    import poses_flux as flux
    try:
        flux.credentials()
        ledger = flux.Ledger(budget=budget) if budget is not None else flux.Ledger()
    except Exception as exc:
        print(f'Using library artwork: generator setup failed ({type(exc).__name__})')
        return out
    for number, old in sorted(fallback.items()):
        try:
            out[number] = generate_one(slides[number-1], Path(destination) / f'{number:02d}_owner.png',
                                       previous=old.read_bytes(), ledger=ledger)
        except Exception as exc:
            print(f'Slide {number}: using library artwork ({type(exc).__name__})')
    return out
