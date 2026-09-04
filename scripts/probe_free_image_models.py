"""Offline first screen for two free Gemini image candidates. Never approves art."""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/suresilly-carousel/scripts'))
import image_single_review as review
import image_qualification as corpus
import llm

MODELS = ('gemini-robotics-er-2-preview', 'gemini-2.5-pro')
CASES = ('extra_leg', 'blank_profile_eye', 'malformed_eyelids', 'kneeling', 'far_apart', 'on_back')
MAX_REQUESTS = len(MODELS) * len(CASES)


def run(output):
    keys = llm.resolve_keys('GEMINI_API_KEY') or llm.resolve_keys('GOOGLE_API_KEY')
    if not keys:
        raise ValueError('No Google key configured')
    output.mkdir(parents=True, exist_ok=False)
    record = {'purpose': 'Initial screen only; cannot qualify models or approve artwork',
              'started_at': datetime.now(timezone.utc).isoformat(),
              'system': review.SYSTEM, 'user': review.USER, 'schema': review.SCHEMA,
              'temperature': 0.2, 'max_output_tokens': 8192,
              'models': list(MODELS), 'cases': list(CASES),
              'source_hashes': {str(p.relative_to(ROOT)): review.digest(p.read_bytes()) for p in
                  (Path(__file__).resolve(), Path(review.__file__), Path(llm.__file__), Path(corpus.__file__))},
              'http_requests': 0, 'results': []}
    def save():
        temp = output / 'results.tmp'
        temp.write_text(json.dumps(record, indent=2)+'\n')
        temp.replace(output / 'results.json')
    population = {c['id']: c for c in corpus.cases()}
    last = None
    save()
    for model in MODELS:
        trial = {'model': model, 'status': 'running', 'observations': []}
        record['results'].append(trial)
        for name in CASES:
            case = population[name]
            raw = case['path'].read_bytes()
            image = review.prepare(raw)
            item = {'case': name, 'source_sha256': review.digest(raw), 'image_sha256': review.digest(image)}
            trial['observations'].append(item)
            (output / (item['source_sha256']+'.png')).write_bytes(raw)
            (output / (item['image_sha256']+'.jpg')).write_bytes(image)
            payload = {'systemInstruction': {'parts': [{'text': review.SYSTEM}]},
                       'contents': [{'role': 'user', 'parts': [{'text': review.USER},
                           {'inline_data': {'mime_type': 'image/jpeg', 'data': base64.b64encode(image).decode('ascii')}}]}],
                       'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 8192,
                           'responseMimeType': 'application/json', 'responseSchema': llm._gemini_schema(review.SCHEMA)}}
            try:
                if record['http_requests'] >= MAX_REQUESTS:
                    raise RuntimeError('Screen request limit reached')
                if last is not None:
                    time.sleep(max(0, 40 - (time.monotonic()-last)))
                last = time.monotonic()
                record['http_requests'] += 1
                save()
                print(f'{model}: {name}; request {record["http_requests"]}/{MAX_REQUESTS}', flush=True)
                llm._tally('count', 'gemini', model)
                response = llm._post(llm.GEMINI_URL.format(model=model), payload, {'x-goog-api-key': keys[0]})
                item['response'] = response
                save()
                if response.get('modelVersion') and not response['modelVersion'].startswith(model.removesuffix('-preview')):
                    raise ValueError('Different model version returned')
                candidates = response.get('candidates') or []
                if not candidates:
                    raise ValueError('No image answer returned')
                parts = candidates[0].get('content', {}).get('parts') or []
                text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
                item['answer'] = llm.extract_json(text)
                save()
                item['assessment'] = review.assessment(item['answer'])
                save()
                found = review.observed_codes(item['answer'])
                item['codes'] = sorted(found)
                if case['codes'] and not found.intersection(case['codes']):
                    trial['status'] = 'failed'
                    raise ValueError('Missed known defect: '+name)
                if not case['codes'] and found:
                    trial['status'] = 'failed'
                    raise ValueError('Rejected correct image: '+name)
                item['passed'] = True
                print('Passed initial case:', name, flush=True)
            except Exception as exc:
                item['error'] = {'type': type(exc).__name__, 'reason': str(exc)[:1000]}
                if isinstance(exc, llm.RateLimited):
                    item['error'].update(quota=exc.quota, retry_after_seconds=exc.wait)
                    if exc.daily:
                        llm._tally('mark_exhausted', 'gemini', model)
                if trial['status'] != 'failed':
                    trial['status'] = 'incomplete'
                print(json.dumps({'model': model, 'status': trial['status'], 'error': item['error']}), flush=True)
                save()
                break
            save()
        else:
            trial['status'] = 'screen_passed_not_qualified'
        save()
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
