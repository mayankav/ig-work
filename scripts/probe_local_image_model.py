"""Six-image offline local screen. Stops on a miss or service/format error."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/suresilly-carousel/scripts'))
import image_single_review as review
import image_qualification as corpus
import llm

CASES = ('extra_leg', 'blank_profile_eye', 'malformed_eyelids', 'kneeling', 'far_apart', 'on_back')
MODEL = 'qwen3.5:9b'
BASE = 'http://127.0.0.1:11439'


def request(route, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + route, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    record = {'purpose': 'Initial screen only; cannot qualify models or approve artwork',
              'started_at': datetime.now(timezone.utc).isoformat(), 'version': review.VERSION,
              'model': MODEL, 'runtime': request('/api/version'), 'installed_models': request('/api/tags'),
              'system': review.SYSTEM, 'user': review.USER, 'schema': review.SCHEMA,
              'settings': {'temperature': .2, 'num_predict': 8192, 'num_ctx': 16384, 'seed': 42},
              'thinking': False, 'timeout_seconds': 300, 'cases': list(CASES),
              'source_hashes': {str(p.relative_to(ROOT)): review.digest(p.read_bytes()) for p in
                  (Path(__file__).resolve(), Path(review.__file__), Path(llm.__file__), Path(corpus.__file__))},
              'requests': 0, 'observations': [], 'status': 'running'}

    def save():
        temporary = output / 'results.tmp'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'results.json')

    population = {c['id']: c for c in corpus.cases()}
    save()
    for name in CASES:
        case = population[name]
        raw = case['path'].read_bytes()
        frame = review.prepare(raw)
        item = {'case': name, 'source_sha256': review.digest(raw), 'image_sha256': review.digest(frame)}
        record['observations'].append(item)
        (output / (item['source_sha256'] + '.png')).write_bytes(raw)
        (output / (item['image_sha256'] + '.jpg')).write_bytes(frame)
        payload = {'model': MODEL, 'messages': [{'role': 'system', 'content': review.SYSTEM},
                   {'role': 'user', 'content': review.USER, 'images': [base64.b64encode(frame).decode()]}],
                   'format': review.SCHEMA, 'stream': False, 'think': False,
                   'options': record['settings'], 'keep_alive': '10m'}
        started = time.monotonic()
        try:
            if record['requests'] >= len(CASES):
                raise RuntimeError('Six-request cap reached')
            record['requests'] += 1
            save()
            print(f'{MODEL}: {name}; request {record["requests"]}/6', flush=True)
            response = request('/api/chat', payload)
            item['elapsed_seconds'] = round(time.monotonic() - started, 3)
            item['response'] = response
            save()
            if response.get('model') != MODEL or not response.get('done') or response.get('done_reason') != 'stop':
                raise ValueError('Wrong model or unfinished response')
            item['answer'] = llm.extract_json(response['message']['content'])
            save()
            item['assessment'] = review.assessment(item['answer'])
            save()
            codes = review.observed_codes(item['answer'])
            item['expected_defect_detected'] = bool(codes.intersection(case['codes'])) if case['codes'] else None
            item['correct_image_flagged'] = bool(codes) if not case['codes'] else None
            if case['codes'] and not item['expected_defect_detected']:
                record['status'] = 'failed'
                raise ValueError('Missed known defect: ' + name)
            if not case['codes'] and codes:
                record['status'] = 'failed'
                raise ValueError('Rejected correct image: ' + name)
            item['passed'] = True
            item['memory_snapshot'] = request('/api/ps')
            print('Passed initial case: ' + name, flush=True)
        except Exception as exc:
            item['elapsed_seconds'] = round(time.monotonic() - started, 3)
            item['error'] = {'type': type(exc).__name__, 'reason': str(exc)[:1000]}
            if record['status'] != 'failed':
                record['status'] = 'incomplete'
            print(json.dumps({'status': record['status'], 'error': item['error']}), flush=True)
            save()
            break
        save()
    else:
        record['status'] = 'screen_passed_not_qualified'
    save()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
