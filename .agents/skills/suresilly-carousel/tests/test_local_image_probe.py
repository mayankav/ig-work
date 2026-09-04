"""Local comparison must stop on a failed check without calling another service."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
import probe_local_image_model as probe


@pytest.fixture
def rig(monkeypatch, tmp_path):
    path = tmp_path / 'art.png'
    path.write_bytes(b'exact-image')
    population = [{'id': name, 'path': path, 'codes': ['extra_limb'] if i < 3 else []}
                  for i, name in enumerate(probe.CASES)]
    monkeypatch.setattr(probe.corpus, 'cases', lambda: population)
    monkeypatch.setattr(probe.review, 'prepare', lambda raw: raw)
    calls = []
    def request(route, payload=None, timeout=300):
        if route != '/api/chat':
            return {}
        calls.append(payload)
        return {'model': probe.MODEL, 'done': True, 'done_reason': 'stop',
                'message': {'content': '{}'}}
    monkeypatch.setattr(probe, 'request', request)
    monkeypatch.setattr(probe.review, 'assessment', lambda _: {'codes': [], 'disposition': 'no_fault_reported'})
    monkeypatch.setattr(probe.review, 'observed_codes', lambda _: {'extra_limb'} if len(calls) <= 3 else set())
    return calls, tmp_path / 'result'


def test_same_images_and_six_call_cap(rig):
    calls, output = rig
    result = probe.run(output)
    assert result['status'] == 'screen_passed_not_qualified'
    assert len(calls) == result['requests'] == 6
    assert all(c['model'] == probe.MODEL and c['stream'] is False for c in calls)
    assert all(c['format'] == probe.review.SCHEMA for c in calls)
    with pytest.raises(FileExistsError):
        probe.run(output)


def test_miss_stops_after_first_call(rig, monkeypatch):
    calls, output = rig
    monkeypatch.setattr(probe.review, 'observed_codes', lambda _: set())
    result = probe.run(output)
    assert result['status'] == 'failed'
    assert len(calls) == result['requests'] == 1
    assert 'response' in result['observations'][0]


@pytest.mark.parametrize('kind', ['service', 'format', 'unresolved'])
def test_incomplete_stops_and_preserves_result(rig, monkeypatch, kind):
    calls, output = rig
    def fail(*a, **kw):
        raise ValueError(kind)
    if kind == 'service':
        original = probe.request
        def request(route, payload=None, timeout=300):
            if route == '/api/chat':
                calls.append(payload)
                fail()
            return original(route, payload, timeout)
        monkeypatch.setattr(probe, 'request', request)
    elif kind == 'format':
        monkeypatch.setattr(probe.review, 'assessment', fail)
    else:
        monkeypatch.setattr(probe.review, 'observed_codes', fail)
    result = probe.run(output)
    assert result['status'] == 'incomplete'
    assert len(calls) == result['requests'] == 1
    assert (output / 'results.json').exists()
