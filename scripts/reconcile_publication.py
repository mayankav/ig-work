"""Resolve an uncertain Instagram request without creating another container.

Meta's container status API identifies FINISHED and PUBLISHED:
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
A missing post in a feed is never treated as proof that publishing failed.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re


def require_owner(root: Path, slug: str, slot: str, run_id: str) -> None:
    from posting_slots import git, load, safe_id
    value = load(root / 'state/slots' / (safe_id(slot) + '.json'))
    last = value['attempts'][-1] if value else {}
    if (last.get('run_id') != run_id or last.get('resume_slug') != slug
            or last.get('result') is not None):
        raise ValueError('This run does not own recovery of this deck.')
    remote = git(root, 'ls-remote', 'origin', 'refs/heads/main').split()
    if (git(root, 'branch', '--show-current') != 'main' or len(remote) != 2
            or remote[0] != git(root, 'rev-parse', 'HEAD')):
        raise ValueError('Recovery requires current main and a saved slot claim.')


def read_pending(root: Path, deck: Path) -> dict:
    path = deck / 'publication_pending.json'
    if path.is_symlink():
        raise ValueError('Publication record is a link. Check the saved state.')
    pending = json.loads(path.read_text())
    if (not isinstance(pending, dict) or pending.get('deck_slug') != deck.name
            or not re.fullmatch(r'[0-9]+', str(pending.get('container_id', '')))
            or pending.get('status') != 'publication_requested'):
        raise ValueError('The saved publication request is invalid.')
    artifacts = pending.get('artifacts')
    required = {str((deck / name).relative_to(root)) for name in
                ('carousel.md', 'contact_sheet.png', 'slides/checks.json')}
    if not isinstance(artifacts, dict) or not required <= artifacts.keys():
        raise ValueError('The publication request has no complete file checks.')
    for name, digest in artifacts.items():
        file = root / name
        if (not file.resolve().is_relative_to(root.resolve()) or file.is_symlink()
                or hashlib.sha256(file.read_bytes()).hexdigest() != digest):
            raise ValueError('A file changed after the publication request was saved.')
    when = datetime.fromisoformat(pending['requested_at'].replace('Z', '+00:00'))
    if when.tzinfo is None:
        raise ValueError('Publication request time has no time zone.')
    return pending


def inspect(requests, base: str, user: str, token: str, pending: dict, caption: str) -> tuple[str, str]:
    """Return (published, media id) or (ready, original container id)."""
    def get(path, params):
        response = requests.get(f'{base}/{path}', params={**params, 'access_token': token}, timeout=30)
        if response.status_code != 200:
            raise ValueError(f'Instagram check failed (HTTP {response.status_code}). Nothing was sent.')
        data = response.json()
        if not isinstance(data, dict) or data.get('error'):
            raise ValueError('Instagram returned an invalid check result.')
        return data
    cid = pending['container_id']
    status = get(cid, {'fields': 'status_code'}).get('status_code')
    # The exact full caption and request time bind the feed result to this deck.
    since = datetime.fromisoformat(pending['requested_at'].replace('Z', '+00:00')) - timedelta(minutes=5)
    matches, after = set(), None
    for _ in range(20):
        params = {'fields': 'id,caption,timestamp', 'limit': 100}
        if after:
            params['after'] = after
        page = get(f'{user}/media', params)
        if not isinstance(page.get('data'), list):
            raise ValueError('Instagram returned no readable media list.')
        for item in page['data']:
            if item.get('caption') == caption:
                stamp = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                if stamp >= since and re.fullmatch(r'[0-9]+', str(item.get('id', ''))):
                    matches.add(item['id'])
        paging = page.get('paging', {})
        if not paging.get('next'):
            break
        cursor = paging.get('cursors', {}).get('after')
        if not cursor or cursor == after:
            raise ValueError('Instagram media paging could not finish.')
        after = cursor
    else:
        raise ValueError('Instagram media check reached its limit. Nothing was sent.')
    if len(matches) > 1:
        raise ValueError('More than one matching post exists. Check Instagram before recovery.')
    if matches:
        return 'published', matches.pop()
    if status == 'FINISHED':
        # Only reuse the original container. Never create a replacement here.
        return 'ready', cid
    raise ValueError(f'Instagram reports {status or "unknown"}; no unique post id was found. Nothing was sent.')
