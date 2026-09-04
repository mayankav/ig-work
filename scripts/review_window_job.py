"""Act on one durable V1 decision; always use the existing Instagram publisher."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / '.agents/skills/suresilly-carousel/scripts'
sys.path.insert(0, str(ENGINE))
import review_window as window
import owner_art
import publication_record


def output(**values):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a') as stream:
            for key, value in values.items():
                if '\n' in str(value): raise ValueError('Invalid workflow output')
                stream.write(f'{key}={value}\n')


def describe(token, action_id):
    record = window.api(token, 'status')
    if (record.get('action', {}).get('id') != action_id or record.get('claimed') or
        record.get('state') not in ('queued', 'cancelled', 'published')):
        output(accepted='false'); return
    output(accepted='true', slug=record['slug'], run_id=record['run_id'], decision=record['action']['decision'])


def claim(token, action_id, deck):
    local = window.read(deck)
    if local['token'] != token: raise ValueError('Downloaded artifact belongs to a different preview')
    remote = window.api(token, 'status')
    if remote.get('action', {}).get('decision') != 'publish':
        for name in ('published.json', 'publication_pending.json'):
            if (deck / name).exists(): raise ValueError('Resolve the existing Instagram publication before redo or cancellation')
    return window.api(token, 'claim', {'action_id': action_id, 'manifest': local['manifest']})


def stage(deck):
    record = window.read(deck)
    folder = ROOT / '.review-host' / record['slug'] / 'reviews' / record['token']
    folder.mkdir(parents=True, exist_ok=True)
    # Only public preview files. No encoded evidence, secrets or source state.
    (folder / 'slides').mkdir(exist_ok=True)
    for path in (deck / 'slides').glob('*.png'): shutil.copy2(path, folder / 'slides' / path.name)
    shutil.copy2(deck / 'contact_sheet.png', folder / 'contact_sheet.png')
    caption = __import__('post_to_ig').parse_caption(deck / 'carousel.md')
    (folder / 'caption.txt').write_text(caption)
    output(slug=record['slug'], review_token=record['token'], host_dir=str(folder), deck=str(deck / 'carousel.md'))
    return record


def resume(deck):
    record = window.read(deck)
    for name in ('published.json', 'publication_pending.json'):
        if (deck / name).exists(): raise ValueError('Resolve the Instagram publication using its review action')
    output(slug=record['slug'], deck=str(deck / 'carousel.md'), review_token=record['token'], verdict='held')


def register(deck):
    record = window.read(deck)
    base = f'https://media.suresilly.com/slides/{record["slug"]}/reviews/{record["token"]}'
    # Verify every hosted image against the actual bytes before inviting review.
    import post_to_ig
    import requests
    for attempt in range(12):
        try:
            sheet = requests.get(base + '/contact_sheet.png', timeout=15)
            if sheet.status_code != 200 or hashlib.sha256(sheet.content).hexdigest() != record['files']['contact_sheet.png']:
                raise ValueError('The hosted contact sheet does not match this preview')
            post_to_ig.check_hosted_images(deck, post_to_ig.list_images(deck, base + '/slides'))
            break
        except (requests.RequestException, ValueError):
            if attempt == 11: raise
            time.sleep(10)
    import dashboard
    caption = dashboard.review_window_message(record['token'], base + '/caption.txt')
    receipt = window.api(record['token'], 'register', {
        **{k: record[k] for k in ('token', 'slug', 'manifest')}, 'run_id': os.environ['GITHUB_RUN_ID'],
        'sheet_url': base + '/contact_sheet.png', 'caption': caption})
    if receipt.get('state') != 'waiting' or not receipt.get('message_id'): raise ValueError('Telegram review window did not open')
    (deck / 'review_delivery.json').write_text(json.dumps(receipt, indent=2) + '\n')
    save_history(record['token'])
    output(delivered='true', deadline=receipt['deadline'])
    return receipt


def redo_slide(deck, number):
    import render
    import post_to_ig
    before = window.read(deck)
    post_to_ig.check_export(deck, deck / 'carousel.md')
    checks = json.loads((deck / 'slides/checks.json').read_text())
    slides = render.parse_markdown(deck / 'carousel.md')
    with tempfile.TemporaryDirectory(prefix='owner-redo-') as scratch:
        staged = Path(scratch) / deck.name; staged.mkdir()
        shutil.copy2(deck / 'carousel.md', staged / 'carousel.md')
        mascots = {}
        for key, proof in checks['artwork'].items():
            raw = owner_art.check(proof)
            path = staged / f'mascot-{key}.png'; path.write_bytes(raw); mascots[int(key)] = path
        old = mascots[number].read_bytes()
        mascots[number] = owner_art.generate_one(slides[number-1], staged / 'replacement.png', previous=old)
        rendered = render.render(staged / 'carousel.md', mascots, staged / 'slides', palette_override=checks['palette'])
        ordered = sorted((deck / 'slides').glob('*.png'))
        for index, path in enumerate(ordered, 1):
            if index != number and path.read_bytes() != (staged / 'slides' / path.name).read_bytes():
                raise ValueError(f'Redo would change untouched slide {index}')
        if ordered[number-1].read_bytes() == (staged / 'slides' / ordered[number-1].name).read_bytes():
            raise ValueError('The slide image did not change')
        render.contact_sheet(rendered, staged / 'contact_sheet.png')
        backup = deck / 'slides-before-redo'
        if backup.exists(): raise ValueError('An earlier interrupted replacement needs inspection')
        (deck / 'slides').rename(backup)
        try:
            shutil.copytree(staged / 'slides', deck / 'slides')
            shutil.copy2(staged / 'contact_sheet.png', deck / 'contact_sheet.png')
            window.prepare(deck, parent=before['token'])
        except Exception:
            (deck / 'render-incomplete').write_text('Replacement commit failed; review required')
            raise
        shutil.rmtree(backup)
    return deck


def notify(text):
    import notify as notifier
    ok, note = notifier._telegram('', text, None)
    if not ok: raise ValueError('Telegram did not confirm delivery: ' + note)


def deliver_result(deck, media_id):
    import requests
    import post_to_ig
    saved = deck / 'review_post_message.json'
    if saved.exists():
        receipt = json.loads(saved.read_text())
        if receipt.get('media_id') == media_id and receipt.get('telegram_accepted') is True: return
    for attempt in range(3):
        try:
            key = os.environ['IG_ACCESS_TOKEN']
            response = requests.get(f'{post_to_ig.graph_base(key)}/{media_id}',
                                    params={'fields': 'permalink', 'access_token': key}, timeout=30)
            link = response.json().get('permalink', '')
            if response.status_code != 200 or not link.startswith(('https://www.instagram.com/', 'https://instagram.com/')):
                raise ValueError('Instagram confirmed the post but did not return its link')
            notify('Posted on Instagram:\n' + link)
            saved.write_text(json.dumps({'media_id': media_id, 'link': link, 'telegram_accepted': True}) + '\n')
            return
        except (requests.RequestException, ValueError):
            if attempt == 2: raise
            time.sleep(5)


def run_child(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.stdout: print(result.stdout, end='', flush=True)
    if result.stderr: print(result.stderr, end='', file=sys.stderr, flush=True)
    if result.returncode:
        lines = [line.strip() for line in (result.stdout + '\n' + result.stderr).splitlines() if line.strip()]
        pause = next((line for line in lines if 'Posting is paused' in line), None)
        reason = pause or (lines[-1] if lines else 'The child job stopped without a reason')
        raise ValueError(reason[:600])
    return result


def act(token, action_id, deck):
    prior = window.api(token, 'status')
    if prior.get('state') == 'published' and prior.get('action', {}).get('id') == action_id:
        deliver_result(deck, prior['result']['media_id'])
        output(result='published')
        return
    record = claim(token, action_id, deck)
    decision = record['action']['decision']
    os.environ['REVIEW_ACTION_ID'] = action_id
    try:
        if decision == 'publish':
            base = f'https://media.suresilly.com/slides/{deck.name}/reviews/{token}/slides'
            args = [sys.executable, str(ROOT / 'scripts/post_to_ig.py'), '--carousel', str(deck / 'carousel.md'), '--base-url', base]
            if any((deck / name).exists() for name in ('published.json', 'publication_pending.json')): args.append('--recover')
            run_child(args, cwd=ROOT)
            receipt = publication_record.read(deck / 'published.json', deck.name)
            window.api(token, 'complete', {'action_id': action_id, 'state': 'published', 'media_id': receipt['media_id']})
            deliver_result(deck, receipt['media_id'])
            output(result='published')
        elif decision == 'drop':
            window.api(token, 'complete', {'action_id': action_id, 'state': 'cancelled'})
            notify('Cancelled this carousel. Future posts and generations are unchanged.')
            output(result='cancelled')
        elif decision == 'redo_slide':
            revised = redo_slide(deck, record['action']['slide'])
            stage(revised)
            output(result='replacement_ready', parent_token=token, parent_action=action_id)
        elif decision == 'redo':
            previous = json.loads((deck / 'slides/checks.json').read_text())
            env = dict(os.environ)
            env['OWNER_REDO_EXCLUDE_HASHES'] = ','.join(value['sha256'] for value in previous['artwork'].values())
            with tempfile.NamedTemporaryFile() as outputs:
                env['GITHUB_OUTPUT'] = outputs.name
                run_child([sys.executable, str(ENGINE / 'run.py'), '--no-post', '--source', 'concept'], cwd=ROOT, env=env)
                values = dict(line.split('=', 1) for line in Path(outputs.name).read_text().splitlines() if '=' in line)
            if not values.get('review_token') or not values.get('slug'): raise ValueError('The new carousel did not pass its checks')
            revised = ROOT / 'carousels' / values['slug']
            replacement = json.loads((revised / 'slides/checks.json').read_text())
            old_hashes = {value['sha256'] for value in previous['artwork'].values()}
            if any(value['sha256'] in old_hashes for value in replacement['artwork'].values()):
                raise ValueError('Full redo repeated artwork from the old carousel')
            stage(revised)
            output(result='replacement_ready', parent_token=token, parent_action=action_id)
        else: raise ValueError('Unknown durable decision')
    except Exception:
        # Never reopen a confirmed post because sending its link failed.
        current = window.api(token, 'status')
        if current.get('state') == 'working': window.api(token, 'complete', {'action_id': action_id, 'state': 'held'})
        raise
    finally:
        save_history(token)


def save_history(token):
    history = ROOT / 'state/review_history'; history.mkdir(parents=True, exist_ok=True)
    (history / f'{token}.json').write_text(json.dumps(window.api(token, 'status'), indent=2) + '\n')


def finish(token, action_id, failed=False):
    record = window.api(token, 'status')
    if record.get('state') == 'working' and record.get('action', {}).get('id') == action_id:
        window.api(token, 'complete', {'action_id': action_id, 'state': 'held' if failed else 'replaced'})
    save_history(token)


def prune(deck):
    args = [sys.executable, str(ROOT / 'scripts/prune_slides.py'), '--root', str(ROOT / 'gh-pages/slides'),
            '--days', '14', '--protect', deck.name]
    held = {path.stem for path in (ROOT / 'state/pending').glob('*.json')}
    for path in (ROOT / 'state/review_history').glob('*.json'):
        record = json.loads(path.read_text())
        if record['state'] not in ('published', 'cancelled', 'replaced'): held.add(record['slug'])
    for slug in sorted(held): args += ['--protect-if-present', slug]
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('describe', 'act', 'stage', 'register', 'finish-redo', 'fail', 'prune', 'resume'))
    parser.add_argument('--token', default=os.environ.get('REVIEW_TOKEN', ''))
    parser.add_argument('--action-id', default=os.environ.get('REVIEW_ACTION_ID', ''))
    parser.add_argument('--deck', type=Path)
    args = parser.parse_args()
    if args.operation == 'describe': describe(args.token, args.action_id)
    elif args.operation == 'act': act(args.token, args.action_id, args.deck)
    elif args.operation == 'stage': stage(args.deck)
    elif args.operation == 'resume': resume(args.deck)
    elif args.operation == 'register': register(args.deck)
    elif args.operation == 'prune': prune(args.deck)
    else: finish(args.token, args.action_id, failed=args.operation == 'fail')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        reason = f'{type(exc).__name__}: {exc}'
        for name, value in os.environ.items():
            if value and len(value) >= 8 and any(word in name for word in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY')):
                reason = reason.replace(value, '[hidden]')
        output(reason=' '.join(reason.split())[:400])
        raise
