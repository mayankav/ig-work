"""Immutable V1 preview manifests and live publication authority."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import urllib.parse
import urllib.request

import owner_art

TOKEN = re.compile(r'[a-f0-9]{16}')


def files(deck):
    deck = Path(deck)
    paths = [deck / 'carousel.md', deck / 'contact_sheet.png', deck / 'slides/checks.json']
    slides = sorted((deck / 'slides').glob('*.png'))
    if len(slides) != 9: raise ValueError('Review needs exactly nine slides')
    paths += slides
    for name in ('content_review.json', 'caption.txt', 'review_notes.txt'):
        if (deck / name).exists(): paths.append(deck / name)
    if any(p.is_symlink() or not p.is_file() for p in paths): raise ValueError('Incomplete or linked preview files')
    return {str(p.relative_to(deck)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def prepare(deck, parent=None):
    if not owner_art.enabled(): raise ValueError('V1 review is not enabled')
    deck = Path(deck)
    for name in ('published.json', 'publication_pending.json'):
        if (deck / name).exists(): raise ValueError('Check the existing Instagram publication before changing this deck')
    from caption_text import parse_caption
    (deck / 'caption.txt').write_text(parse_caption(deck / 'carousel.md'))
    notes = []
    if (deck / 'content_review.json').exists():
        checked = json.loads((deck / 'content_review.json').read_text())
        notes = checked.get('style_notes', []) + [item['why'] for item in checked.get('objections', [])]
    (deck / 'review_notes.txt').write_text('\n'.join('- ' + str(note) for note in notes) if notes else 'No style notes.')
    record = {'policy': owner_art.POLICY, 'token': secrets.token_hex(8), 'slug': deck.name,
              'files': files(deck), 'parent': parent}
    record['manifest'] = digest(record['files'])
    (deck / 'review_window.json').write_text(json.dumps(record, indent=2) + '\n')
    return record


def read(deck):
    record = json.loads((Path(deck) / 'review_window.json').read_text())
    if (record['policy'] != owner_art.POLICY or not TOKEN.fullmatch(record['token']) or
        record['slug'] != Path(deck).name or record['files'] != files(deck) or record['manifest'] != digest(record['files'])):
        raise ValueError('Preview files changed after preparation')
    return record


def api(token, operation, body=None):
    if not TOKEN.fullmatch(token) or operation not in ('register', 'status', 'claim', 'complete'):
        raise ValueError('Invalid review request')
    base = os.environ.get('REVIEW_WINDOW_URL', '').rstrip('/')
    key = os.environ.get('REVIEW_WINDOW_SECRET', '')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.query or parsed.fragment or not key:
        raise ValueError('Review service is not configured')
    request = urllib.request.Request(f'{base}/review/{token}/{operation}',
        data=json.dumps(body or {}).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'suresilly-review-window/1.0', 'X-Review-Key': key})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('error'): raise ValueError('Review service refused the action')
    return result


def require_publication(deck, base_url):
    record = read(deck)
    expected = f'https://media.suresilly.com/slides/{record["slug"]}/reviews/{record["token"]}/slides'
    if base_url.rstrip('/') != expected: raise ValueError('Publication URL is not the reviewed revision')
    remote = api(record['token'], 'status')
    if (remote.get('manifest') != record['manifest'] or remote.get('state') != 'working' or
        not remote.get('claimed') or remote.get('action', {}).get('decision') != 'publish' or
        remote.get('action', {}).get('id') != os.environ.get('REVIEW_ACTION_ID', '')):
        raise ValueError('This exact preview has no live publication claim')
    return remote
