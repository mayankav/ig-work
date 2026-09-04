"""Offline Gemini screen with durable progress and bounded transport retries.

No approval, generation, key rotation or publishing. A completed answer is final.
"""
import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/suresilly-carousel/scripts'))
import image_single_review as review
import image_qualification as corpus
import llm

CASES = ('extra_leg', 'blank_profile_eye', 'malformed_eyelids', 'kneeling', 'far_apart', 'on_back')
MODEL = 'gemini-3.8-flash'
MAX_ATTEMPTS = 3
MAX_TOTAL = len(CASES) * MAX_ATTEMPTS
MIN_SPACING = 40
LIFETIME = 86400
TERMINAL = {'failed_accuracy', 'invalid_answer', 'unresolved', 'unavailable',
            'access_error', 'quota_exhausted', 'interrupted', 'screen_passed_not_qualified', 'expired'}


def classify_http(code, body, headers, now):
    try:
        error = json.loads(body).get('error', {})
    except (ValueError, AttributeError):
        error = {}
    if not isinstance(error, dict): error = {}
    details = error.get('details', [])
    if not isinstance(details, list): details = []
    quota_ids = [v.get('quotaId', '') for d in details if isinstance(d, dict)
                 for v in d.get('violations', []) if isinstance(v, dict)]
    delay = 0
    header = headers.get('Retry-After') or headers.get('retry-after')
    if header:
        try: delay = max(0, float(header))
        except ValueError:
            try: delay = max(0, parsedate_to_datetime(header).timestamp() - now)
            except (ValueError, TypeError, OverflowError): pass
    for detail in details:
        if isinstance(detail, dict) and 'retryDelay' in detail:
            try: delay = max(delay, float(str(detail['retryDelay']).removesuffix('s')))
            except ValueError: pass
    daily = any('perday' in q.lower() for q in quota_ids)
    category = ('quota_exhausted' if daily and code == 429 else 'rate_limited' if code == 429
                else 'service_unavailable' if code in (500, 502, 503, 504, 408)
                else 'access_error')
    return {'category': category, 'http_status': code,
            'provider_status': error.get('status'), 'message': error.get('message', '')[:1000],
            'quota_ids': quota_ids, 'retry_after_seconds': delay,
            'retryable': category in ('rate_limited', 'service_unavailable')}


def transport(payload, key):
    request = urllib.request.Request(llm.GEMINI_URL.format(model=MODEL),
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json',
        'User-Agent': 'suresilly-offline-screen/1', 'x-goog-api-key': key})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode('utf-8', 'replace')
            return {'http_status': response.status, 'body': body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', 'replace')
        return {'http_status': exc.code, 'body': body,
                'error': classify_http(exc.code, body, dict(exc.headers or {}), time.time())}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return {'error': {'category': 'network_error', 'retryable': True,
                         'message': type(exc).__name__, 'retry_after_seconds': 0}}


def cases():
    population = {c['id']: c for c in corpus.cases()}
    return [population[name] for name in CASES]


def specification(population):
    return {'model': MODEL, 'system': review.SYSTEM, 'user': review.USER, 'schema': review.SCHEMA,
            'temperature': .2, 'max_output_tokens': 8192,
            'limits': {'per_case': MAX_ATTEMPTS, 'total': MAX_TOTAL, 'spacing': MIN_SPACING, 'lifetime': LIFETIME},
            'sources': {str(p.relative_to(ROOT)): review.digest(p.read_bytes()) for p in
                        (Path(__file__), Path(review.__file__), Path(corpus.__file__), Path(llm.__file__))},
            'cases': [{'id': c['id'], 'codes': c['codes'], 'sha256': review.digest(c['path'].read_bytes()),
                       'submitted_sha256': review.digest(review.prepare(c['path'].read_bytes()))} for c in population]}


def score(body, expected):
    response = json.loads(body)
    actual = response.get('modelVersion', '')
    if not actual.startswith(MODEL): raise ValueError('Missing or different model version')
    candidate = response['candidates'][0]
    if candidate.get('finishReason') != 'STOP': raise ValueError('Incomplete or blocked answer')
    text = ''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought'))
    answer = llm.extract_json(text)
    assessment = review.assessment(answer)
    found = set(assessment['codes'])
    if assessment['disposition'] == 'unresolved': status = 'unresolved'
    elif (expected and not found.intersection(expected)) or (not expected and found): status = 'failed_accuracy'
    else: status = 'passed'
    return {'answer': answer, 'assessment': assessment, 'actual_model': actual, 'status': status}


def run(output, max_calls=3, *, send=transport, clock=time.time, sleep=time.sleep):
    if not 1 <= max_calls <= MAX_TOTAL: raise ValueError('Invalid invocation request limit')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        population = cases()
        spec = specification(population)
        contract = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
        path = output / 'results.json'
        if path.exists():
            record = json.loads(path.read_text())
            if record['contract'] != contract: raise ValueError('Code, settings or images changed; cannot resume this experiment')
        else:
            record = {'purpose': 'Offline initial screen only; cannot approve artwork', 'contract': contract,
                      'specification': spec, 'started_at': clock(), 'next_request_at': 0,
                      'status': 'pending', 'cases': [{'id': c['id'], 'status': 'pending', 'attempts': []} for c in population]}
        def save():
            temp = output / 'results.tmp'
            temp.write_text(json.dumps(record, indent=2) + '\n')
            temp.replace(path)
        def finish(status):
            record['status'] = status
            save()
            return record
        if record['status'] in TERMINAL: return record
        if not 0 <= clock() - record['started_at'] <= LIFETIME: return finish('expired')
        for row in record['cases']:
            if any(a['state'] == 'sent' for a in row['attempts']): return finish('interrupted')
        keys = llm.resolve_keys('GEMINI_API_KEY') or llm.resolve_keys('GOOGLE_API_KEY')
        if not keys: return finish('access_error')
        issued = 0
        for case, row in zip(population, record['cases']):
            if row['id'] != case['id']: raise ValueError('Case order changed')
            if row['status'] == 'passed': continue
            # Replay a response saved before an interrupted scoring step. Never
            # ask again merely because a reply was not yet marked as scored.
            if row['attempts'] and row['attempts'][-1]['state'] == 'received':
                previous = row['attempts'][-1]
                result = previous['response']
                if 'error' not in result:
                    try: row.update(score(result['body'], case['codes']))
                    except Exception as exc:
                        row.update(status='invalid_answer', score_error=str(exc)[:1000])
                        return finish('invalid_answer')
                    save()
                    if row['status'] != 'passed': return finish(row['status'])
                else:
                    error = result['error']
                    if not error['retryable']: return finish(error['category'])
                    delay = max(MIN_SPACING, 30 * 2 ** (len(row['attempts'])-1), error['retry_after_seconds'])
                    retry_at = previous['started_at'] + previous['elapsed_seconds'] + delay + int(contract[:4], 16) % 6
                    record['next_request_at'] = max(record['next_request_at'], retry_at)
                    save()
            while row['status'] != 'passed':
                total = sum(len(r['attempts']) for r in record['cases'])
                if len(row['attempts']) >= MAX_ATTEMPTS or total >= MAX_TOTAL: return finish('unavailable')
                if issued >= max_calls: return finish('paused')
                remaining = record['next_request_at'] - clock()
                # Long quotas pause on disk; no tight polling or sleeping through a day.
                if remaining > 180: return finish('waiting_for_service')
                while remaining > 0:
                    sleep(min(10, remaining)); remaining = record['next_request_at'] - clock()
                if clock() - record['started_at'] > LIFETIME: return finish('expired')
                raw = case['path'].read_bytes(); image = review.prepare(raw)
                (output / (review.digest(raw) + '.png')).write_bytes(raw)
                (output / (review.digest(image) + '.jpg')).write_bytes(image)
                payload = {'systemInstruction': {'parts': [{'text': review.SYSTEM}]},
                           'contents': [{'role': 'user', 'parts': [{'text': review.USER},
                             {'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(image).decode()}}]}],
                           'generationConfig': {'temperature': .2, 'maxOutputTokens': 8192,
                             'responseMimeType': 'application/json', 'responseSchema': llm._gemini_schema(review.SCHEMA)}}
                attempt = {'state': 'sent', 'started_at': clock()}
                row['attempts'].append(attempt); issued += 1
                record['next_request_at'] = clock() + MIN_SPACING
                save() # Count and checkpoint before sending, including unknown crash outcomes.
                llm._tally('count', 'gemini', MODEL)
                print(f'{case["id"]}: attempt {len(row["attempts"])}/{MAX_ATTEMPTS}; total {total+1}/{MAX_TOTAL}', flush=True)
                try: result = send(payload, keys[0])
                except Exception as exc:
                    attempt.update(state='interrupted', error_type=type(exc).__name__)
                    return finish('interrupted')
                attempt.update(state='received', elapsed_seconds=clock()-attempt['started_at'], response=result)
                save() # Raw response survives scoring or a later process failure.
                if 'error' in result:
                    error = result['error']
                    if not error['retryable']: return finish(error['category'])
                    delay = max(MIN_SPACING, 30 * 2 ** (len(row['attempts'])-1), error['retry_after_seconds'])
                    # Stable per-case jitter; preserved deadline prevents a restart from bypassing it.
                    jitter = int(contract[:4], 16) % 6
                    record['next_request_at'] = clock() + delay + jitter
                    save()
                    continue
                try: row.update(score(result['body'], case['codes']))
                except Exception as exc:
                    row.update(status='invalid_answer', score_error=str(exc)[:1000])
                    return finish('invalid_answer')
                save()
                if row['status'] != 'passed': return finish(row['status'])
        return finish('screen_passed_not_qualified')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-calls', type=int, default=3)
    args = parser.parse_args()
    result = run(args.output, args.max_calls)
    print(json.dumps({'status': result['status'], 'requests': sum(len(c['attempts']) for c in result['cases']),
                      'next_request_at': result['next_request_at']}))
