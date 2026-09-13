import assert from 'node:assert/strict';
import {ReviewWindow, REVIEW_HOUR, parseWindowReply} from '../src/review-window.js';
const token = 'a'.repeat(16), manifest = 'b'.repeat(64);
let now = 100000, deliveries = 0, dispatches = 0, telegramFails = false, githubFails = false;
Date.now = () => now;
const said = [];
globalThis.fetch = async (url, init) => {
  if (url.includes('telegram.org')) { deliveries++; said.push(JSON.parse(init?.body || '{}').text || ''); return Response.json(telegramFails ? {ok:false} : {ok:true,result:{message_id:42}}); }
  dispatches++; return new Response(null, {status:githubFails ? 503 : 204});
};
function object() {
  const values = new Map();
  const storage = {get:async k=>structuredClone(values.get(k)), put:async(k,v)=>values.set(k,structuredClone(v)),
    setAlarm:async at=>{storage.alarm=at;},deleteAlarm:async()=>{storage.alarm=null;}};
  return {obj:new ReviewWindow({storage,blockConcurrencyWhile:fn=>fn()},{}),storage};
}
async function call(obj, route, body={}) { const r=await obj.fetch(new Request('https://test/'+route,{method:'POST',body:JSON.stringify(body)})); return {status:r.status,...await r.json()}; }
const preview={token,manifest,slug:'a-deck',run_id:'123',caption:`Review ID: ${token}`,sheet_url:`https://media.suresilly.com/slides/a-deck/reviews/${token}/contact_sheet.png`};
const decision=(id,verb='publish',slide=0)=>({request_id:`tg-${id}`,decision:verb,slide});
const setup=async()=>{const x=object(); await call(x.obj,'register',preview);return x;};
for(const [text,reply,expected] of [
 ['approve',`Review ID: ${token}`,'publish'],['redo 4',`Review ID: ${token}`,'redo_slide'],
 [`redo ${token} all`,'','redo'],[`disapproval ${token}`,'','drop']]) assert.equal(parseWindowReply(text,reply).decision,expected);
assert.equal(parseWindowReply('approve'),null);
assert.equal(parseWindowReply('redo 10',preview.caption),null);
assert.equal(parseWindowReply('approve 4',preview.caption),null);
{
 const {obj,storage}=await setup(); const sent=deliveries;
 assert.equal(storage.alarm,now+REVIEW_HOUR);
 await call(obj,'register',preview); assert.equal(deliveries,sent);
 await obj.alarm(); assert.equal((await call(obj,'status')).state,'waiting');
 now+=REVIEW_HOUR; const old=dispatches; await obj.alarm(); await obj.alarm();
 assert.equal(dispatches,old+1); const r=await call(obj,'status');assert.equal(r.action.decision,'publish');
 assert.equal((await call(obj,'claim',{manifest:'wrong',action_id:r.action.id})).status,409);
 assert.equal((await call(obj,'claim',{manifest,action_id:r.action.id})).state,'working');
 assert.equal((await call(obj,'decide',decision(1,'redo'))).status,409);
 assert.equal((await call(obj,'claim',{manifest,action_id:r.action.id})).status,409);
 assert.equal((await call(obj,'complete',{action_id:r.action.id,state:'published'})).status,400);
 assert.equal((await call(obj,'complete',{action_id:r.action.id,state:'published',media_id:'1234'})).state,'published');
 assert.equal((await call(obj,'decide',decision(2,'drop'))).status,409);
}
{
 const {obj,storage}=await setup();now+=REVIEW_HOUR;await obj.alarm();const old=await call(obj,'status');
 await call(obj,'decide',decision(3,'redo_slide',4));assert.equal(storage.alarm,now+10*60*1000);
 assert.equal((await call(obj,'claim',{manifest,action_id:old.action.id})).status,409);
 const r=await call(obj,'status');assert.equal(r.action.slide,4);
 const calls=dispatches;assert.equal((await call(obj,'decide',decision(3,'redo_slide',4))).duplicate,true);assert.equal(dispatches,calls);
 await call(obj,'claim',{manifest,action_id:r.action.id});
 await call(obj,'complete',{action_id:r.action.id,state:'held'});assert.equal(storage.alarm,null);
 assert.equal((await call(obj,'decide',decision(4,'redo'))).accepted,true);
}
{
 const {obj,storage}=await setup();await call(obj,'decide',decision(5,'drop'));now+=REVIEW_HOUR;
 const calls=dispatches;await obj.alarm();assert.equal(dispatches,calls+1);assert.equal((await call(obj,'status')).state,'cancelled');
 assert.equal((await call(obj,'decide',decision(6))).status,409);
}
{
 telegramFails=true;const {obj,storage}=object();assert.equal((await call(obj,'register',preview)).status,502);
 assert.equal(storage.alarm,undefined);now+=REVIEW_HOUR;await obj.alarm();assert.equal((await call(obj,'status')).state,'delivery_failed');telegramFails=false;
 assert.equal((await call(obj,'register',preview)).state,'waiting');
}
{
 const {obj,storage}=await setup();githubFails=true;await call(obj,'decide',decision(7));
 assert.equal(storage.alarm,now+60000);await obj.alarm();await obj.alarm();const calls=dispatches;await obj.alarm();
 assert.equal(dispatches,calls);assert.equal((await call(obj,'status')).state,'dispatch_failed');githubFails=false;
 assert.equal(said.filter(s=>s.includes("GitHub didn't accept our request")).length,1);
 assert.match(said.at(-1),/stuck[\s\S]*What you can do:[\s\S]*If you do nothing:/);
 await obj.alarm();assert.equal(said.filter(s=>s.includes("GitHub didn't accept our request")).length,1); // said once
}
{
 const {obj,storage}=await setup();await call(obj,'decide',decision(8));const r=await call(obj,'status');
 await call(obj,'claim',{manifest,action_id:r.action.id});now+=40*60*1000;await obj.alarm();
 assert.equal((await call(obj,'status')).state,'held');assert.equal(storage.alarm,null);
 assert.match(said.at(-1),/stopped without finishing/);
 assert.equal((await call(obj,'complete',{action_id:r.action.id,state:'published',media_id:'12'})).status,409);
}
{
 const {obj}=await setup();await call(obj,'decide',decision(9));const first=await call(obj,'status');
 now+=10*60*1000;const calls=dispatches;await obj.alarm();const second=await call(obj,'status');
 assert.equal(dispatches,calls+1);assert.equal(second.action.id,first.action.id);
 assert.equal((await call(obj,'claim',{manifest,action_id:first.action.id})).state,'working');
}
console.log('review-window: all transition, receipt, timeout and stale-action checks passed');

// Multi-image decisions are unambiguous; an invalid reply changes nothing.
assert.deepEqual(parseWindowReply(`redo ${token} images 7,2,4`).slides,[2,4,7]);
assert.deepEqual(parseWindowReply('redo images all',preview.caption).slides,[1,2,3,4,5,6,7,8,9]);
for (const tail of ['images 0','images 10','images 2,2','images 2-4','images 2,','images 2 approve','all images'])
 assert.equal(parseWindowReply(`redo ${token} ${tail}`),null);
{
 const {obj,storage}=object();
 await call(obj,'register',{...preview,manual_required:true,issue_pages:['All findings']});
 assert.equal(storage.alarm,null); now+=REVIEW_HOUR*2;await obj.alarm();
 assert.equal((await call(obj,'status')).state,'waiting');
 await call(obj,'decide',{request_id:'tg-100',decision:'redo_slide',slides:[2,4,7]});
 assert.deepEqual((await call(obj,'status')).action.slides,[2,4,7]);
}
{
 const original=globalThis.fetch;
 globalThis.fetch=async(url,...args)=>url.endsWith('/sendMessage')?Response.json({ok:false}):original(url,...args);
 const {obj,storage}=object();
 assert.equal((await call(obj,'register',{...preview,issue_pages:['one issue']})).status,502);
 assert.equal(storage.alarm,undefined);
 assert.equal((await call(obj,'decide',decision(101))).status,409);
 globalThis.fetch=original;
}
{
 // The album preview: the real slides first, then an HTML card that carries the
 // Review ID, and no quota message when resources is ''.
 const original=globalThis.fetch, sent=[];
 globalThis.fetch=async(url,init)=>{
  if(!url.includes('telegram.org')) return original(url,init);
  sent.push({method:url.split('/').pop(),body:JSON.parse(init.body)});
  return Response.json({ok:true,result:url.endsWith('/sendMediaGroup')?[{message_id:7},{message_id:8}]:{message_id:43}});
 };
 const photos=[1,2].map(n=>`https://media.suresilly.com/slides/a-deck/reviews/${token}/slides/0${n}.jpg`);
 const card=`<b>New post ready</b>\nReview ID: <code>${token}</code>`;
 const {obj,storage}=object();
 const r=await call(obj,'register',{...preview,caption:card,html:true,photos,resources:''});
 assert.equal(r.state,'waiting'); assert.equal(r.message_id,43); assert.equal(storage.alarm,now+REVIEW_HOUR);
 assert.deepEqual(sent.map(x=>x.method),['sendMediaGroup','sendMessage']);
 assert.equal(sent[1].body.parse_mode,'HTML'); assert.equal(sent[1].body.text,card);
 assert.equal(parseWindowReply('approve',card.replace(/<[^>]+>/g,'')).decision,'publish');
 sent.length=0;
 const one=object();
 await call(one.obj,'register',{...preview,caption:card,html:true,photos:photos.slice(0,1),resources:''});
 assert.deepEqual(sent.map(x=>x.method),['sendPhoto','sendMessage']);
 for (const bad of [['https://evil.example/01.jpg'],photos.map(u=>u.replace('/01.jpg','/1.jpg')),[],Array(10).fill(photos[0])]) {
  assert.equal((await call(object().obj,'register',{...preview,caption:card,photos:bad})).status,400);
 }
 globalThis.fetch=original;
 console.log('review-window: album preview, HTML card and photo checks passed');
}
