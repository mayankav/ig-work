// Latest recorded usage; never infer a live balance from an old reading.
const stamp = value => {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(date)+' IST' : 'unknown';
};
function midnight(now, zone) {
  const base = Math.floor(now/3600000)*3600000;
  for (let hour=1; hour<=36; hour++) {
    const next=base+hour*3600000;
    if (new Intl.DateTimeFormat('en-GB',{timeZone:zone,hour:'2-digit',hourCycle:'h23'}).format(next)==='00') return next;
  }
  return NaN;
}
export function formatResources(vendors={}, ledger={}, now=Date.now(), apis={}) {
  const lines=['Resources — '+stamp(now)], day=new Date(now).toISOString().slice(0,10), cf=ledger[day];
  if (cf) { const used=(cf.neurons||0)+(cf.text_neurons||0); lines.push(`Cloudflare AI: ${used.toFixed(2)}/10,000 units used; ${Math.max(0,10000-used).toFixed(2)} left (recorded use).`); }
  else lines.push(`Cloudflare AI: no usage record for ${day}; remaining unknown.`);
  lines.push('Cloudflare reset: '+stamp(midnight(now,'UTC'))+'.');
  const gem=vendors.gemini||{};
  lines.push('Gemini data: '+stamp(gem.observed_at)+'.');
  for (const [model, record] of Object.entries(gem.models||{})) lines.push(`  ${model}: ${record.made??'unknown'} requests recorded${record.out_of_quota_at?'; limit reached':''}.`);
  lines.push('Gemini remaining: unknown; no account ceiling reported.','Gemini daily reset: '+stamp(midnight(now,'America/Los_Angeles'))+'.');
  const groq=vendors.groq||{};
  lines.push(`Groq ${groq.model||'model unknown'} — data: ${stamp(groq.observed_at)}.`);
  for (const key of ['requests','tokens']) {
    const reading=groq[key]||{};
    lines.push(`  ${key}: ${reading.remaining??'unknown'}/${reading.limit??'unknown'} left at that reading.`);
    lines.push('  Full refill if unused: '+stamp(reading.reset_seconds==null?NaN:new Date(groq.observed_at).getTime()+reading.reset_seconds*1000)+'.');
  }
  const ig=apis.instagram||{}, cfg=ig.config||{};
  if (typeof ig.quota_usage==='number' && typeof cfg.quota_total==='number') {
    lines.push(`Instagram: ${ig.quota_usage}/${cfg.quota_total} posts used; ${Math.max(0,cfg.quota_total-ig.quota_usage)} left. Data: ${stamp(apis.observed_at)}.`);
    lines.push(`Instagram window: ${cfg.quota_duration??'unknown'} seconds; rolling refill, no fixed daily reset.`);
  } else lines.push('Instagram API allowance: remaining and reset unknown; no reading available.');
  lines.push('Telegram API: daily remaining not reported; retry delays come from its response.','Old readings are not live balances; other use may reduce what remains.');
  return lines.join('\n');
}
export async function resources(env) {
  if (!env.GH_DISPATCH_TOKEN) return formatResources();
  try {
    const values = await Promise.all(['vendor_quotas.json','flux_neurons.json','api_quotas.json'].map(async name => {
      const response=await fetch(`https://api.github.com/repos/mayankav/ig-work/contents/state/${name}?ref=main`,{headers:{Authorization:`Bearer ${env.GH_DISPATCH_TOKEN}`,Accept:'application/vnd.github.raw+json','User-Agent':'suresilly-resources'},signal:AbortSignal.timeout(4000)});
      if (!response.ok) return {};
      return response.json();
    }));
    return formatResources(values[0],values[1],Date.now(),values[2]);
  } catch { return formatResources()+'\nLatest saved data could not be read.'; }
}
