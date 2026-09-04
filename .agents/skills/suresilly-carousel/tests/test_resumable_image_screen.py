import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'scripts'))
import resumable_image_screen as screen


@pytest.fixture
def rig(monkeypatch, tmp_path):
    p = tmp_path / 'image.png'; p.write_bytes(b'fixed-image')
    monkeypatch.setattr(screen, 'cases', lambda: [{'id': 'a', 'path': p, 'codes': []}, {'id': 'b', 'path': p, 'codes': []}])
    monkeypatch.setattr(screen, 'specification', lambda _: {'fixed': 'contract'})
    monkeypatch.setattr(screen.review, 'prepare', lambda raw: raw)
    monkeypatch.setattr(screen.llm, 'resolve_keys', lambda _: ['fake'])
    monkeypatch.setattr(screen.llm, '_tally', lambda *a: None)
    monkeypatch.setattr(screen, 'score', lambda body, expected: {'status': json.loads(body)['status']})
    now = [1000.0]
    def sleep(seconds): now[0] += seconds
    def run(send, cap=3):
        return screen.run(tmp_path / 'out', cap, send=send, clock=lambda: now[0], sleep=sleep)
    return run, tmp_path / 'out', now


def success(*a): return {'body': '{"status":"passed"}', 'http_status': 200}

def unavailable(*a):
    return {'error': {'category': 'service_unavailable', 'retryable': True, 'retry_after_seconds': 0}}


def test_503_is_not_rate_limiting():
    result = screen.classify_http(503, '{"error":{"status":"UNAVAILABLE"}}', {}, 0)
    assert result['category'] == 'service_unavailable'
    assert result['retryable']
    assert screen.classify_http(429, '{}', {}, 0)['category'] == 'rate_limited'


def test_daily_quota_overrides_short_retry_hint():
    body = json.dumps({'error': {'details': [{'violations': [{'quotaId': 'RequestsPerDay'}]}, {'retryDelay': '11s'}]}})
    result = screen.classify_http(429, body, {'Retry-After': '5'}, 0)
    assert result['category'] == 'quota_exhausted'
    assert not result['retryable']
    assert result['retry_after_seconds'] == 11


def test_service_retry_then_continue_without_restart(rig):
    run, _, now = rig
    calls = []
    def send(*a):
        calls.append(now[0]); return unavailable() if len(calls) == 1 else success()
    result = run(send)
    assert result['status'] == 'screen_passed_not_qualified'
    assert len(calls) == 3
    assert calls[1]-calls[0] >= screen.MIN_SPACING


def test_resume_skips_finished_cases(rig):
    run, _, _ = rig
    assert run(success, 1)['status'] == 'paused'
    calls = []
    def send(*a): calls.append(1); return success()
    assert run(send)['status'] == 'screen_passed_not_qualified'
    assert len(calls) == 1
    assert run(send)['status'] == 'screen_passed_not_qualified'
    assert len(calls) == 1


def test_attempt_cap_survives_restarts(rig):
    run, _, _ = rig
    for _ in range(2): assert run(unavailable, 1)['status'] == 'paused'
    result = run(unavailable, 1)
    assert result['status'] == 'unavailable'
    assert len(result['cases'][0]['attempts']) == 3
    assert run(lambda *a: pytest.fail('terminal experiment retried'))['status'] == 'unavailable'


@pytest.mark.parametrize('status', ['failed_accuracy', 'unresolved'])
def test_bad_answer_never_retried(rig, status):
    run, _, _ = rig
    result = run(lambda *a: {'body': json.dumps({'status': status})})
    assert result['status'] == status
    assert len(result['cases'][0]['attempts']) == 1
    run(lambda *a: pytest.fail('bad answer retried'))


def test_long_retry_after_pauses_without_early_call(rig):
    run, _, now = rig
    result = run(lambda *a: {'error': {'category': 'rate_limited', 'retryable': True, 'retry_after_seconds': 7200}})
    assert result['status'] == 'waiting_for_service'
    assert now[0] == 1000
    run(lambda *a: pytest.fail('retry deadline bypassed'))


def test_received_answer_replayed_after_interruption(rig):
    run, out, _ = rig
    run(success, 1)
    p = out / 'results.json'; r = json.loads(p.read_text())
    r['cases'][0]['status'] = 'pending'; p.write_text(json.dumps(r))
    calls = []
    def send(*a): calls.append(1); return success()
    assert run(send)['status'] == 'screen_passed_not_qualified'
    assert len(calls) == 1


def test_unknown_request_does_not_repeat(rig):
    run, out, _ = rig
    run(success, 1)
    p = out / 'results.json'; r = json.loads(p.read_text())
    r['cases'][0]['attempts'][0]['state'] = 'sent'; p.write_text(json.dumps(r))
    assert run(lambda *a: pytest.fail('unknown request repeated'))['status'] == 'interrupted'


def test_changed_contract_refuses_resume(rig, monkeypatch):
    run, _, _ = rig
    run(success, 1)
    monkeypatch.setattr(screen, 'specification', lambda _: {'changed': True})
    with pytest.raises(ValueError, match='cannot resume'): run(success)


def test_malformed_reply_is_terminal(rig):
    run, _, _ = rig
    assert run(lambda *a: {'body': 'not json'})['status'] == 'invalid_answer'
    run(lambda *a: pytest.fail('malformed reply retried'))
