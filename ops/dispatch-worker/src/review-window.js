// V1 owner review: one Durable Object per immutable preview token.
// The alarm and owner replies share the same serialized decision record.
export const REVIEW_HOUR = 60 * 60 * 1000;
export const REVIEW_TOKEN = /^[a-f0-9]{16}$/;
const SLUG = /^[a-zA-Z0-9_-]{1,140}$/;
const json = (value, status = 200) => Response.json(value, { status });

export function parseWindowReply(text, replyText = '') {
  const match = /^\s*(approve|approval|publish|disapprove|disapproval|cancel|reject|redo)\s*(?:([a-f0-9]{16}))?(?:\s+(all|[1-9]))?\s*$/i.exec(text || '');
  if (!match) return null;
  const token = match[2] || /Review ID:\s*([a-f0-9]{16})/i.exec(replyText)?.[1];
  if (!token) return null;
  const verb = match[1].toLowerCase();
  if (verb !== 'redo' && match[3]) return null;
  return {token, decision: verb === 'redo' ? (match[3] && match[3] !== 'all' ? 'redo_slide' : 'redo')
    : ['approve', 'approval', 'publish'].includes(verb) ? 'publish' : 'drop',
    slide: verb === 'redo' && /^[1-9]$/.test(match[3] || '') ? Number(match[3]) : 0};
}

export class ReviewWindow {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; }
  async fetch(request) {
    return this.ctx.blockConcurrencyWhile(async () => {
      try { return await this.handle(new URL(request.url).pathname, await request.json()); }
      catch (error) { console.log('review window error:', error.message); return json({error: 'Review action failed'}, 500); }
    });
  }
  async handle(route, input) {
    let record = await this.ctx.storage.get('review');
    if (route === '/register') {
      if (!REVIEW_TOKEN.test(input.token || '') || !SLUG.test(input.slug || '') ||
          !/^[0-9]+$/.test(String(input.run_id || '')) || !/^[a-f0-9]{64}$/.test(input.manifest || '') ||
          typeof input.caption !== 'string' || input.caption.length > 1000 ||
          !input.caption.includes(`Review ID: ${input.token}`)) return json({error: 'Invalid preview'}, 400);
      const url = new URL(input.sheet_url);
      if (url.origin !== 'https://media.suresilly.com' || url.search || url.hash ||
          url.pathname !== `/slides/${input.slug}/reviews/${input.token}/contact_sheet.png`) return json({error: 'Invalid preview URL'}, 400);
      if (record) {
        if (record.manifest !== input.manifest || record.slug !== input.slug) return json({error: 'Token already used'}, 409);
        if (!['preparing', 'delivery_failed'].includes(record.state)) return json(record);
        if (record.delivery_attempts >= 3) return json({error: 'Preview delivery exhausted'}, 409);
      } else record = {...input, state: 'preparing', delivery_attempts: 0, history: [], seen: {}};
      record.delivery_attempts++;
      await this.ctx.storage.put('review', record);
      let receipt;
      try {
        const response = await fetch(`https://api.telegram.org/bot${this.env.TELEGRAM_BOT_TOKEN}/sendDocument`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, signal: AbortSignal.timeout(15000),
          body: JSON.stringify({chat_id: this.env.TELEGRAM_CHAT_ID, document: input.sheet_url, caption: input.caption})});
        receipt = await response.json();
        if (!response.ok || receipt.ok !== true || !Number.isSafeInteger(receipt.result?.message_id)) throw new Error('No Telegram receipt');
      } catch {
        record.state = 'delivery_failed'; await this.ctx.storage.put('review', record);
        return json({error: 'Telegram did not confirm the preview. No automatic posting.'}, 502);
      }
      record.message_id = receipt.result.message_id;
      record.delivered_at = Date.now(); record.deadline = record.delivered_at + REVIEW_HOUR;
      record.state = 'waiting';
      await this.ctx.storage.put('review', record);
      await this.ctx.storage.setAlarm(record.deadline);
      return json(record);
    }
    if (!record) return json({error: 'Unknown review'}, 404);
    if (route === '/status') return json(record);
    if (route === '/decide') {
      if (!/^tg-[0-9]+$/.test(input.request_id || '') || !['publish', 'drop', 'redo', 'redo_slide'].includes(input.decision) ||
          (input.decision === 'redo_slide' && (!Number.isInteger(input.slide) || input.slide < 1 || input.slide > 9))) return json({error: 'Invalid decision'}, 400);
      if (record.seen[input.request_id]) return json({state: record.state, duplicate: true});
      if (!['waiting', 'queued', 'held', 'dispatch_failed'].includes(record.state)) return json({error: 'This preview is closed or work has started', state: record.state}, 409);
      if (Object.keys(record.seen).length >= 100) return json({error: 'Too many decisions for one preview'}, 409);
      record.seen[input.request_id] = true;
      record.history.push({at: Date.now(), decision: input.decision, request_id: input.request_id});
      record.state = input.decision === 'drop' ? 'cancelled' : 'queued';
      record.action = {id: `rv-${record.token}-${input.request_id}`, decision: input.decision, slide: input.slide || 0, attempts: 0};
      await this.ctx.storage.deleteAlarm();
      await this.ctx.storage.put('review', record); // A redo/cancel stops timeout posting before dispatch.
      return json(await this.dispatch(record));
    }
    if (route === '/claim') {
      if (record.claimed || !record.action || input.action_id !== record.action.id || input.manifest !== record.manifest ||
          !['queued', 'cancelled'].includes(record.state)) return json({error: 'Action was replaced or already claimed'}, 409);
      if (record.state === 'cancelled' && record.action.decision !== 'drop') return json({error: 'Cancelled'}, 409);
      record.state = record.action.decision === 'drop' ? 'cancelled' : 'working';
      record.claimed = true; record.claim_expires = Date.now() + 40 * 60 * 1000;
      await this.ctx.storage.put('review', record);
      await this.ctx.storage.setAlarm(record.claim_expires);
      return json(record);
    }
    if (route === '/complete') {
      if (!record.claimed || input.action_id !== record.action?.id) return json({error: 'Unclaimed action'}, 409);
      if (!['published', 'cancelled', 'replaced', 'held'].includes(input.state)) return json({error: 'Invalid result'}, 400);
      if ((input.state === 'published' && record.action.decision !== 'publish') ||
          (input.state === 'cancelled' && record.action.decision !== 'drop') ||
          (input.state === 'replaced' && !['redo', 'redo_slide'].includes(record.action.decision))) return json({error: 'Result does not match the action'}, 400);
      if (input.state === 'published' && !/^[0-9]+$/.test(input.media_id || '')) return json({error: 'Missing post receipt'}, 400);
      record.state = input.state; record.result = input; record.claimed = false;
      await this.ctx.storage.put('review', record); await this.ctx.storage.deleteAlarm();
      return json(record);
    }
    return json({error: 'Unknown review operation'}, 404);
  }
  async dispatch(record) {
    record.action.attempts++;
    await this.ctx.storage.put('review', record); // Persist intent before GitHub can receive it.
    try {
      const response = await fetch('https://api.github.com/repos/mayankav/ig-work/actions/workflows/review-window.yml/dispatches', {
        method: 'POST', signal: AbortSignal.timeout(5000), headers: {
          Authorization: `Bearer ${this.env.GH_DISPATCH_TOKEN}`, Accept: 'application/vnd.github+json',
          'User-Agent': 'suresilly-review-window', 'Content-Type': 'application/json'},
        body: JSON.stringify({ref: 'main', inputs: {token: record.token, action_id: record.action.id}})});
      if (response.status !== 204) throw new Error('Dispatch not accepted');
      record.action.dispatched = true;
      await this.ctx.storage.put('review', record);
      return {state: record.state, accepted: true};
    } catch {
      if (record.action.attempts < 3) await this.ctx.storage.setAlarm(Date.now() + 60000);
      else { record.state = record.state === 'cancelled' ? 'cancelled' : 'dispatch_failed'; await this.ctx.storage.put('review', record); }
      return {state: record.state, accepted: true, dispatch_pending: true};
    }
  }
  async alarm() {
    return this.ctx.blockConcurrencyWhile(async () => {
      const record = await this.ctx.storage.get('review');
      if (!record) return;
      if (record.state === 'working' && record.claimed && Date.now() >= record.claim_expires) {
        record.state = 'held'; record.claimed = false;
        await this.ctx.storage.put('review', record);
        await this.ctx.storage.deleteAlarm();
        return;
      }
      if (record.state === 'waiting') {
        if (Date.now() < record.deadline) { await this.ctx.storage.setAlarm(record.deadline); return; }
        record.state = 'queued';
        record.action = {id: `rv-${record.token}-timeout`, decision: 'publish', slide: 0, attempts: 0};
        record.history.push({at: Date.now(), decision: 'timeout_publish'});
        await this.ctx.storage.put('review', record);
      }
      if (['queued', 'cancelled'].includes(record.state) && record.action && !record.action.dispatched && record.action.attempts < 3) await this.dispatch(record);
    });
  }
}
