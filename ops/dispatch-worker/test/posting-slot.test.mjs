// No network: exercise real scheduled dispatch and stable event time.
import assert from "node:assert/strict";
import worker, { postingSlot, replySlot } from "../src/index.js";

const cases = [
  ["2026-09-04T02:30:00Z", "30 2 * * *", "2026-09-04_0800"],
  ["2026-09-04T14:30:00Z", "30 14 * * *", "2026-09-04_2000"],
  ["2026-12-31T14:30:00Z", "30 14 * * *", "2026-12-31_2000"],
];
for (const [time, cron, want] of cases) {
  assert.equal(postingSlot(Date.parse(time), cron), want);
}
for (const [time, cron] of [[NaN, "30 2 * * *"], [0, "bad"],
  [Date.parse("2026-09-04T04:30:00Z"), "30 2 * * *"]]) {
  assert.throws(() => postingSlot(time, cron));
}
assert.equal(replySlot(Date.parse("2026-09-04T02:29:59Z") / 1000), "2026-09-03_2000");
assert.equal(replySlot(Date.parse("2026-09-04T14:30:00Z") / 1000), "2026-09-04_2000");
assert.equal(replySlot(Date.parse("2026-09-04T08:30:00Z") / 1000), "2026-09-04_0800");
assert.throws(() => replySlot(undefined));

const realFetch = globalThis.fetch;
const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push({url, ...JSON.parse(init.body)});
  return new Response(null, {status: 204});
};
try {
  const event = {scheduledTime: Date.parse(cases[0][0]), cron: cases[0][1]};
  const pending = [];
  const ctx = {waitUntil(promise) { pending.push(promise); }};
  // Same trigger delivered twice, long after its intended date.
  await worker.scheduled(event, {GH_DISPATCH_TOKEN: "test"}, ctx);
  await worker.scheduled(event, {GH_DISPATCH_TOKEN: "test"}, ctx);
  await Promise.all(pending);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].inputs, {mode: "publish", slot_id: cases[0][2]});
  assert.deepEqual(calls[1].inputs, calls[0].inputs);
  assert.equal(calls[0].ref, "main");
  globalThis.fetch = async () => new Response(null, {status: 503});
  let failed;
  await worker.scheduled(event, {GH_DISPATCH_TOKEN: "test"}, {waitUntil(promise) { failed = promise; }});
  await assert.rejects(failed, /Scheduled dispatch failed \(503\)/);
} finally {
  globalThis.fetch = realFetch;
}
console.log("posting-slot: 15/15 passed (stable scheduled/reply time, duplicate delivery, failed dispatch)");
