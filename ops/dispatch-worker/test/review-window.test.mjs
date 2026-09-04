import assert from 'node:assert/strict';
import {ReviewWindow, REVIEW_HOUR, parseWindowReply} from '../src/review-window.js';
const token = 'a'.repeat(16), manifest = 'b'.repeat(64);
let now = 100000, deliveries = 0, dispatches = 0, telegramFails = false, githubFails = false;
Date.now = () => now;
globalThis.fetch = async url => {
  if (url.includes('telegram.org')) { deliveries++; return Response.json(telegramFails ? {ok:false} : {ok:true,result:{message_id:42}}); }
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
}
{
 const {obj,storage}=await setup();await call(obj,'decide',decision(8));const r=await call(obj,'status');
 await call(obj,'claim',{manifest,action_id:r.action.id});now+=40*60*1000;await obj.alarm();
 assert.equal((await call(obj,'status')).state,'held');assert.equal(storage.alarm,null);
 assert.equal((await call(obj,'complete',{action_id:r.action.id,state:'published',media_id:'12'})).status,409);
}
{
 const {obj}=await setup();await call(obj,'decide',decision(9));const first=await call(obj,'status');
 now+=10*60*1000;const calls=dispatches;await obj.alarm();const second=await call(obj,'status');
 assert.equal(dispatches,calls+1);assert.equal(second.action.id,first.action.id);
 assert.equal((await call(obj,'claim',{manifest,action_id:first.action.id})).state,'working');
}
console.log('review-window: all transition, receipt, timeout and stale-action checks passed');
