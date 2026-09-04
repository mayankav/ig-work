"""Read-only resource report. Counts are not invented remaining allowances."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo('Asia/Kolkata')


def read(path):
    try: return json.loads(path.read_text())
    except (OSError, ValueError): return {}


def stamp(value):
    try:
        date = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
        return date.astimezone(IST).strftime('%d %b %Y %H:%M IST')
    except (TypeError, ValueError, AttributeError): return 'unknown'


def refresh_api():
    """Read Instagram's account limit; missing access is not a zero balance."""
    key, user = os.environ.get('IG_ACCESS_TOKEN'), os.environ.get('IG_USER_ID')
    if not key or not user: return {}
    import requests
    from instagram_api import graph_base
    result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'instagram': {}}
    try:
        response = requests.get(f'{graph_base(key)}/{user}/content_publishing_limit',
            params={'fields':'quota_usage,config','access_token':key}, timeout=5)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data: result['instagram'] = {k:data[0].get(k) for k in ('quota_usage','config')}
        else: result['status'] = 'API reading unavailable'
    except Exception: result['status'] = 'API reading unavailable'
    return result


def save_api():
    data = refresh_api()
    if data: (ROOT/'state/api_quotas.json').write_text(json.dumps(data,indent=2)+'\n')
    return data


def report(vendors=None, ledger=None, now=None, apis=None):
    now = now or datetime.now(timezone.utc)
    vendors = read(ROOT/'state/vendor_quotas.json') if vendors is None else vendors
    ledger = read(ROOT/'state/flux_neurons.json') if ledger is None else ledger
    day = now.astimezone(timezone.utc).date().isoformat()
    cf = ledger.get(day)
    lines = ['Resources — '+stamp(now)]
    if isinstance(cf,dict):
        spent = cf.get('neurons',0)+cf.get('text_neurons',0)
        lines.append(f'Cloudflare AI: {spent:,.2f}/10,000 units used; {max(0,10000-spent):,.2f} left (recorded use).')
    else: lines.append('Cloudflare AI: no usage record for '+day+'; remaining unknown.')
    lines.append('Cloudflare reset: '+stamp((now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0))+'.')
    gem = vendors.get('gemini',{})
    lines.append('Gemini data: '+stamp(gem.get('observed_at'))+'.')
    for model,record in gem.get('models',{}).items():
        lines.append(f"  {model}: {record.get('made','unknown')} requests recorded"+('; limit reached' if record.get('out_of_quota_at') else '')+'.')
    lines.append('Gemini remaining: unknown; no account ceiling reported.')
    pacific=now.astimezone(ZoneInfo('America/Los_Angeles'))
    lines.append('Gemini daily reset: '+stamp((pacific+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0))+'.')
    groq=vendors.get('groq',{})
    lines.append('Groq '+groq.get('model','model unknown')+' — data: '+stamp(groq.get('observed_at'))+'.')
    for key in ('requests','tokens'):
        reading=groq.get(key,{})
        lines.append(f"  {key}: {reading.get('remaining','unknown')}/{reading.get('limit','unknown')} left at that reading.")
        try:
            refill=datetime.fromisoformat(groq['observed_at'].replace('Z','+00:00'))+timedelta(seconds=reading['reset_seconds'])
            lines.append('  Full refill if unused: '+stamp(refill)+'.')
        except (KeyError,ValueError,TypeError): lines.append('  Refill time: unknown.')
    apis = read(ROOT/'state/api_quotas.json') if apis is None else apis
    ig = apis.get('instagram', {}); config = ig.get('config') or {}
    used, total = ig.get('quota_usage'), config.get('quota_total')
    if isinstance(used, (int,float)) and isinstance(total, (int,float)):
        lines.append(f'Instagram: {used}/{total} posts used; {max(0,total-used)} left. Data: '+stamp(apis.get('observed_at'))+'.')
        lines.append(f"Instagram window: {config.get('quota_duration','unknown')} seconds; rolling refill, no fixed daily reset.")
    else: lines.append('Instagram API allowance: remaining and reset unknown; no reading available.')
    lines.append('Telegram API: daily remaining not reported; any retry delay is handled from its response.')
    lines.append('Old readings are not live balances; other use may reduce what remains.')
    return '\n'.join(lines)

if __name__=='__main__': print(report())
