"""Recovery must preserve the deck, publication identity, and previous attempts."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
import posting_slots as slots
import reconcile_publication as reconcile
import restore_deck
import concept_topup
import notify
from run_result import result
from test_posting_slots import SLOT, CREATED, final, save, repos, git


def failed(path, **changes):
    value, _, _ = slots.reserve(path, SLOT, 'old', '100', CREATED, False,
                                revision='a', code_revision='old-code')
    value['attempts'][0]['result'] = final(stage='tests', outcome='error', retryable=False, **changes)
    save(path, value)
    return value


def recover(path, **kwargs):
    return slots.reserve(path, SLOT, 'new', '101', CREATED, False,
                         recover=True, revision='b', code_revision='fixed-code', **kwargs)


def test_fixed_code_recovers_failed_tests_without_erasing_history(tmp_path):
    path = tmp_path / f'{SLOT}.json'
    old = failed(path)
    value, _, decision = recover(path)
    assert decision == 'accepted' and len(value['attempts']) == 2
    assert value['attempts'][0] == old['attempts'][0]
    assert not value['attempts'][-1].get('resume_slug')
    assert slots.load(path) == old  # decision itself cannot write


def test_state_only_commit_is_not_a_code_fix(tmp_path):
    _, repo, _ = repos(tmp_path)
    before = slots.code_at(repo, 'HEAD')
    (repo / 'state').mkdir()
    (repo / 'state/example.json').write_text('{}')
    git(repo, 'add', 'state')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-m', 'state')
    assert slots.code_at(repo, 'HEAD') == before
    (repo / 'scripts').mkdir()
    (repo / 'scripts/fix.py').write_text('fixed=True')
    git(repo, 'add', 'scripts')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-m', 'fix')
    assert slots.code_at(repo, 'HEAD') != before


def test_same_code_and_repeated_delivery_never_recover(tmp_path):
    path = tmp_path / f'{SLOT}.json'
    failed(path)
    assert slots.reserve(path, SLOT, 'new', '101', CREATED, False,
                         recover=True, code_revision='old-code')[0] is None
    assert slots.reserve(path, SLOT, 'old', '101', CREATED, False,
                         recover=True, code_revision='fixed')[0] is None


@pytest.mark.parametrize('stage', ['hosting', 'posting', 'state saving'])
def test_resume_binds_to_original_deck_and_artifact(tmp_path, stage):
    path = tmp_path / f'{SLOT}.json'
    value = failed(path, slug='test-deck')
    value['attempts'][0]['result']['stage'] = stage
    save(path, value)
    value, _, _ = recover(path)
    attempt = value['attempts'][-1]
    assert attempt['resume_slug'] == 'test-deck' and attempt['resume_run'] == '100'
    save(path, value)
    save(path, slots.finish(path, '101', final(stage='hosting', outcome='error', slug='test-deck')))
    value, _, _ = slots.reserve(path, SLOT, 'third', '102', CREATED, False, recover=True)
    assert value['attempts'][-1]['resume_run'] == '100'


def test_held_and_unfinished_attempts_cannot_recover(tmp_path):
    path = tmp_path / f'{SLOT}.json'
    value = failed(path, held=True, slug='test-deck')
    assert recover(path)[0] is None
    value['attempts'][0]['result'] = None
    save(path, value)
    assert recover(path)[0] is None


def test_recovery_needs_explicit_slot_and_cannot_mix_with_retry():
    for inputs in ({'mode': 'publish', 'recover': True},
                   {'mode': 'publish', 'recover': True, 'slot_id': SLOT, 'retry': True}):
        with pytest.raises(ValueError):
            slots.identify({'inputs': inputs}, 'workflow_dispatch', CREATED, '101')


def test_new_blocked_request_has_reportable_result():
    value = result({'slot': {'outcome': 'success', 'outputs': {
        'accepted': 'false', 'decision': 'duplicate', 'alert': 'true',
        'reason': 'The previous tests failed. Open the earlier run.'}}},
        mode='publish', slug='', verdict='', reason='', retry=False, published=None)
    assert value['outcome'] == 'blocked' and not value['published']
    assert 'tests failed' in value['reason']


class Response:
    status_code = 200
    ok = True
    def __init__(self, data):
        self.data = data
    def json(self):
        return self.data


class Instagram:
    def __init__(self, status, items):
        self.status, self.items, self.calls = status, items, []
    def get(self, url, **kwargs):
        self.calls.append(url)
        return Response({'data': self.items} if url.endswith('/media') else {'status_code': self.status})
    def post(self, *args, **kwargs):
        raise AssertionError('A read-only check attempted to publish')


PENDING = {'container_id': '123', 'requested_at': CREATED}
ITEM = {'id': '456', 'caption': 'exact caption', 'timestamp': CREATED}


@pytest.mark.parametrize('status', ['PUBLISHED', 'FINISHED', 'IN_PROGRESS'])
def test_existing_post_is_found_without_publishing(status):
    api = Instagram(status, [ITEM])
    assert reconcile.inspect(api, 'https://example', 'user', 'secret', PENDING, 'exact caption') == ('published', '456')


def test_finished_reuses_only_original_container():
    assert reconcile.inspect(Instagram('FINISHED', []), 'https://example', 'user', 'secret',
                             PENDING, 'exact caption') == ('ready', '123')


@pytest.mark.parametrize('status', ['PUBLISHED', 'IN_PROGRESS', 'ERROR', 'EXPIRED', None])
def test_unknown_or_unmatched_post_never_grants_publish(status):
    with pytest.raises(ValueError):
        reconcile.inspect(Instagram(status, []), 'https://example', 'user', 'secret', PENDING, 'exact caption')


def test_ambiguous_caption_and_old_post_are_not_confirmation():
    with pytest.raises(ValueError):
        reconcile.inspect(Instagram('PUBLISHED', [ITEM, ITEM | {'id': '789'}]),
                          'https://example', 'user', 'secret', PENDING, 'exact caption')
    with pytest.raises(ValueError):
        reconcile.inspect(Instagram('PUBLISHED', [ITEM | {'timestamp': '2026-08-01T00:00:00Z'}]),
                          'https://example', 'user', 'secret', PENDING, 'exact caption')


def artifact(tmp_path):
    source = tmp_path / 'download'
    (source / 'slides').mkdir(parents=True)
    (source / 'carousel.md').write_text('exact copy')
    (source / 'slides/checks.json').write_text(json.dumps({'markdown_sha256': hashlib.sha256(b'exact copy').hexdigest()}))
    return source


def test_restore_preserves_publication_records_and_rechecks_export(tmp_path, monkeypatch):
    import post_to_ig
    source = artifact(tmp_path)
    (source / 'published.json').write_text('stale receipt')
    deck = tmp_path / 'carousels/test-deck'
    deck.mkdir(parents=True)
    (deck / 'publication_pending.json').write_text('keep pending request')
    called = []
    monkeypatch.setattr(post_to_ig, 'check_export', lambda *args: called.append(args))
    restore_deck.restore(source, tmp_path, 'test-deck')
    assert called and (deck / 'carousel.md').read_text() == 'exact copy'
    assert not (deck / 'published.json').exists()
    assert (deck / 'publication_pending.json').read_text() == 'keep pending request'


def test_restore_refuses_changed_copy_and_held_decks(tmp_path):
    source = artifact(tmp_path)
    deck = tmp_path / 'carousels/test-deck'
    deck.mkdir(parents=True)
    (deck / 'carousel.md').write_text('changed copy')
    with pytest.raises(ValueError, match='changed'):
        restore_deck.restore(source, tmp_path, 'test-deck')
    (tmp_path / 'state/pending').mkdir(parents=True)
    (tmp_path / 'state/pending/test-deck.json').write_text('{}')
    with pytest.raises(ValueError, match='held'):
        restore_deck.restore(source, tmp_path, 'test-deck')


def test_low_pool_can_refill_without_builds_and_is_bounded():
    now = datetime.now(timezone.utc)
    args = dict(total=10, available=0, decks=0, previous={}, now=now, low_only=True)
    assert concept_topup.due(**args)
    assert not concept_topup.due(**(args | {'total': concept_topup.MAX_POOL}))
    assert not concept_topup.due(**(args | {'available': concept_topup.LOW_POOL}))
    previous = {'attempted_at': now.isoformat(), 'decks': 0}
    assert not concept_topup.due(**(args | {'previous': previous}))
    assert concept_topup.due(**(args | {'previous': previous, 'now': now + concept_topup.COOLDOWN}))


def test_telegram_retries_failed_part_only_and_saves_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'secret')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'chat')
    receipts = tmp_path / 'receipts.jsonl'
    monkeypatch.setenv('NOTIFY_RECEIPTS', str(receipts))
    monkeypatch.setattr(notify.time, 'sleep', lambda _: None)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs['data'])
        if len(calls) == 2:
            response = Response({'ok': False})
            response.ok, response.status_code = False, 500
            return response
        return Response({'ok': True, 'result': {'message_id': len(calls)}})
    monkeypatch.setattr(notify.requests, 'post', post)
    ok, _ = notify._telegram('', 'x' * 5000, None)
    assert ok and len(calls) == 3
    assert calls[1] == calls[2] and calls[0] != calls[1]
    rows = [json.loads(x) for x in receipts.read_text().splitlines()]
    assert [r['accepted'] for r in rows] == [True, False, True]
    assert [r['message_id'] for r in rows] == [1, None, 3]
    assert 'secret' not in receipts.read_text()


def test_telegram_http_success_without_receipt_is_failure(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'secret')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'chat')
    monkeypatch.setattr(notify.requests, 'post', lambda *a, **k: Response({'ok': False}))
    assert not notify._telegram('subject', 'body', None)[0]


def test_workflow_recovery_cannot_generate_after_restore_failure():
    import yaml
    workflow = yaml.safe_load((ROOT / '.github/workflows/auto-post.yml').read_text())
    steps = {s.get('id'): s for s in workflow['jobs']['post']['steps']}
    assert 'always()' not in steps['build']['if']
    assert 'restore_deck.py' in steps['restore']['run']
    assert 'RESUME_SLUG' in steps['build']['run']
    assert "verdict != 'held'" in steps['post']['if']
    independent = yaml.safe_load((ROOT / '.github/workflows/concept-pool.yml').read_text())
    assert 'needs' not in independent['jobs']['topup']
    assert independent['concurrency']['group'] == workflow['concurrency']['group']


def test_recovery_owner_and_remote_are_required(tmp_path):
    _, repo, _ = repos(tmp_path)
    path = repo / 'state/slots' / f'{SLOT}.json'
    value = {'version': 1, 'slot_id': SLOT, 'attempts': [{
        'request_id': 'request', 'run_id': '100', 'created_at': CREATED,
        'resume_slug': 'test-deck', 'result': None}]}
    slots.persist(repo, path, value)
    reconcile.require_owner(repo, 'test-deck', SLOT, '100')
    with pytest.raises(ValueError, match='does not own'):
        reconcile.require_owner(repo, 'other-deck', SLOT, '100')
    with pytest.raises(ValueError, match='does not own'):
        reconcile.require_owner(repo, 'test-deck', SLOT, '101')
    git(repo, 'checkout', '-b', 'codex/unreleased')
    with pytest.raises(ValueError, match='current main'):
        reconcile.require_owner(repo, 'test-deck', SLOT, '100')


@pytest.mark.parametrize('state', ['published', 'ready'])
def test_recovery_main_never_creates_replacement_containers(tmp_path, monkeypatch, state):
    import post_to_ig as post
    import bibliography
    deck = tmp_path / 'deck'
    deck.mkdir()
    (deck / 'carousel.md').write_text('## Caption\nexact caption')
    (deck / 'publication_pending.json').write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['post_to_ig.py', '--carousel', str(deck / 'carousel.md'), '--recover'])
    monkeypatch.setenv('IG_USER_ID', 'user')
    monkeypatch.setenv('IG_ACCESS_TOKEN', 'secret')
    monkeypatch.setattr(post, 'require_posting_allowed', lambda: None)
    monkeypatch.setattr(bibliography, 'require_deck_support', lambda _: None)
    monkeypatch.setattr(post, 'check_export', lambda *a: None)
    monkeypatch.setattr(post, 'check_hosted_images', lambda *a: None)
    monkeypatch.setattr(post, 'list_images', lambda *a: ['https://example/image'] * 9)
    monkeypatch.setattr(reconcile, 'require_owner', lambda *a: None)
    monkeypatch.setattr(reconcile, 'read_pending', lambda *a: PENDING)
    monkeypatch.setattr(reconcile, 'inspect', lambda *a: (state, '123' if state == 'ready' else '456'))
    def forbidden(*a, **k):
        pytest.fail('Recovery created a new container')
    monkeypatch.setattr(post, 'create_image_container', forbidden)
    monkeypatch.setattr(post, 'create_carousel', forbidden)
    calls = []
    def publish(user, token, cid):
        calls.append(cid)
        return '456'
    monkeypatch.setattr(post, 'publish', publish)
    post.main()
    assert calls == (['123'] if state == 'ready' else [])
    assert json.loads((deck / 'published.json').read_text())['media_id'] == '456'
    assert not (deck / 'publication_pending.json').exists()


def test_blocked_message_does_not_offer_force():
    import dashboard
    text = dashboard.build('blocked', None, 'The tests failed. Use recovery after a fix.', None, None)
    assert 'NO NEW WORK STARTED' in text
    assert 'force' not in text and 'Starts a new idea' not in text
    assert 'IF YOU DO NOTHING' in text and 'list' in text


@pytest.mark.parametrize('event,request_id,repeated,attempt,want', [
    ('schedule', 'gh-1', False, 1, False),
    ('workflow_dispatch', 'clock-2026-09-04_0800', False, 1, False),
    ('workflow_dispatch', 'gh-2', False, 1, True),
    ('workflow_dispatch', 'tg-22', False, 1, True),
    ('workflow_dispatch', 'tg-22', True, 1, False),
    ('workflow_dispatch', 'gh-2', True, 2, True),
])
def test_clock_delivery_and_person_requests_have_different_alerts(event, request_id, repeated, attempt, want):
    assert slots.should_alert(event, request_id, repeated, attempt) is want


def test_stopped_build_can_recover_only_after_code_change(tmp_path):
    path=tmp_path/f'{SLOT}.json'
    old=failed(path)
    old['attempts'][0]['result']=final(stage='generation',outcome='stopped',retryable=False,slug='',held=False)
    save(path,old)
    assert slots.reserve(path,SLOT,'new','101',CREATED,False,recover=True,code_revision='old-code')[0] is None
    value,_,decision=recover(path)
    assert decision=='accepted'
    assert value['attempts'][0]==old['attempts'][0]
    for fields in ({'published':True},{'slug':'existing-deck'},{'held':True}):
        altered=json.loads(json.dumps(old));altered['attempts'][0]['result'].update(fields);save(path,altered)
        assert recover(path)[0] is None
