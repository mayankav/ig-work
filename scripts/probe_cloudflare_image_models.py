"""Four-request diagnostic. Does not qualify reviewers or approve images."""
import argparse
import base64
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'.agents/skills/suresilly-carousel/scripts'))
import image_single_review as review
import image_qualification as corpus
import llm
import neurons

# Published full context bounds and USD per million tokens. Reserve the full
# input context, not a guessed image token count. $0.011 = 1000 neurons.
MODELS = {
 '@cf/moondream/moondream3.1-9B-A2B': (32768, .30, 1.00),
 '@cf/google/gemma-4-26b-a4b-it': (256000, .10, .30),
}
CASES = ('extra_leg', 'kneeling')
OUTPUT = 8192


def run(output):
 account=llm.resolve_key('CLOUDFLARE_ACCOUNT_ID')
 token=llm.resolve_key('CLOUDFLARE_API_TOKEN')
 if not account or not token: raise ValueError('Cloudflare credentials unavailable')
 ledger=neurons.Ledger()
 reserves={m: math.ceil((context*inp+OUTPUT*out)/11) for m,(context,inp,out) in MODELS.items()}
 # Require the entire four-request screen to fit before starting.
 ledger.check_account(sum(reserves.values())*len(CASES))
 output.mkdir(parents=True,exist_ok=False)
 prompt=review.SYSTEM+'\n\n'+review.USER+'\nReturn JSON matching this schema:\n'+json.dumps(review.SCHEMA)
 record={'purpose':'Diagnostic only; no qualification or image approval',
  'started_at':datetime.now(timezone.utc).isoformat(), 'prompt':prompt,
  'schema':review.SCHEMA,'max_output_tokens':OUTPUT,'temperature':.2,
  'context_and_usd_per_million':MODELS,'reserved_neurons_per_request':reserves,
  'account_ledger_remaining_before':ledger.account_left(),
  'pricing_source':'https://developers.cloudflare.com/workers-ai/platform/pricing/',
  'code_hashes':{str(p.relative_to(ROOT)):review.digest(p.read_bytes()) for p in
   (Path(__file__).resolve(),Path(review.__file__),Path(llm.__file__),Path(neurons.__file__))},
  'http_requests':0,'results':[]}
 def save():
  temp=output/'results.tmp'
  temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(output/'results.json')
 population={c['id']:c for c in corpus.cases()}
 save();last=None
 for model in MODELS:
  trial={'model':model,'observations':[]};record['results'].append(trial)
  for name in CASES:
   raw=population[name]['path'].read_bytes();image=review.prepare(raw)
   item={'case':name,'source_sha256':review.digest(raw),'image_sha256':review.digest(image)}
   trial['observations'].append(item)
   (output/(item['source_sha256']+'.png')).write_bytes(raw)
   (output/(item['image_sha256']+'.jpg')).write_bytes(image)
   uri='data:image/jpeg;base64,'+base64.b64encode(image).decode('ascii')
   if 'moondream' in model:
    payload={'task':'query','question':prompt,'image':uri,'reasoning':True,'stream':False,'temperature':.2,'max_tokens':OUTPUT}
   else:
    payload={'messages':[{'role':'user','content':[{'type':'text','text':prompt},
       {'type':'image_url','image_url':{'url':uri}}]}],
      'stream':False,'temperature':.2,'max_completion_tokens':OUTPUT}
   headers={}
   try:
    if record['http_requests']>=4: raise RuntimeError('Four-request limit reached')
    if last is not None: time.sleep(max(0,4-(time.monotonic()-last)))
    ledger.reserve_text(reserves[model],note='offline comparison '+model)
    record['http_requests']+=1;last=time.monotonic();save()
    print(f'{model}: {name}, request {record["http_requests"]}/4; reserved {reserves[model]} neurons',flush=True)
    response=llm._post(llm.CLOUDFLARE_URL.format(account=account,model=model),payload,
       {'Authorization':'Bearer '+token},capture=headers)
    item['response']=response;save()
    billed=float(headers['cf-ai-neurons']) if 'cf-ai-neurons' in headers else None
    ledger.reconcile_text(reserves[model],billed,note=model)
    item['reported_neurons']=billed
    if response.get('success') is False: raise ValueError(str(response.get('errors'))[:700])
    result=response.get('result') or response
    if 'moondream' in model: text=result.get('answer')
    elif result.get('choices'): text=result['choices'][0].get('message',{}).get('content')
    else: text=result.get('response')
    item['answer']=text if isinstance(text,dict) else llm.extract_json(text or '')
    answer=item['answer'];problems=llm.validate(answer,review.SCHEMA)
    item['schema_faults']=problems
    if not problems:
     # Diagnostic observations remain distinct from production eligibility.
     item['uncertainty']=answer['uncertainty']
     item['assessment']=review.assessment(answer)
     codes=set(item['assessment']['codes'])
     item['observed_codes']=sorted(codes)
     expected=set(population[name]['codes'])
     item['expected_defect_detected']=bool(codes&expected) if expected else None
     item['correct_image_flagged']=bool(codes) if not expected else None
     try:
      review.observed_codes(answer)
      item['current_protocol_usable']=True
     except ValueError as e:
      item['current_protocol_usable']=False;item['current_protocol_reason']=str(e)
    print(json.dumps({k:v for k,v in item.items() if k not in ('response','answer','source_sha256','image_sha256')}),flush=True)
   except Exception as e:
    item['error']={'type':type(e).__name__,'reason':str(e)[:1000]}
    print(json.dumps(item['error']),flush=True)
    save();break # no service retry, changed endpoint, or alternate model fallback
   save()
 record['account_ledger_remaining_after']=ledger.account_left();save()
 return record


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 run(parser.parse_args().output)
