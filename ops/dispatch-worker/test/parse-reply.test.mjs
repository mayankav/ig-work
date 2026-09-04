// What a Telegram reply does. Run it directly — there is no test harness here:
//
//     node ops/dispatch-worker/test/parse-reply.test.mjs
//
// The Worker has no framework, no wrangler test runner and no dependencies, and
// adding one to check a nine-line regex would be the larger change. So this is a
// plain node script in the house style: a list of failures, a count, exit 0 or 1.
// The engine's own suites are run two different ways for the same reason — see
// AGENTS.md on suites that are silent when run the wrong way.
//
// Two questions, and the second is the one that matters.
//
//   THE PARSE    which words are commands, and which decision each carries.
//                The trap is `rerun`: it reads like "run it again" and has always
//                meant DROP. Folding it into the retry synonyms would turn a
//                request for another attempt into a discard of a held deck.
//
//   THE ROUTE    where `retry` is sent. Every other verb is a decision about a
//                deck that is already built and waiting, so it goes to review.yml.
//                A run that stopped on a gate built nothing — there is no deck to
//                publish or drop — so retry has to start a fresh auto-post.yml
//                instead. parseReply returning "retry" proves nothing on its own;
//                the dispatch URL is the claim. globalThis.fetch is stubbed, so
//                no network is touched and no workflow is really dispatched.

import worker, { parseReply, VERBS } from "../src/index.js";

const ENV = {
  TELEGRAM_WEBHOOK_SECRET: "shh",
  TELEGRAM_CHAT_ID: "12345",
  TELEGRAM_BOT_TOKEN: "bot-token",
  GH_DISPATCH_TOKEN: "gh-token",
};

/** Push one Telegram update through the real handler and report every URL hit. */
async function reply(text, { chatId = ENV.TELEGRAM_CHAT_ID, secret = "shh", ghStatus = 204 } = {}) {
  const seen = [];
  const realFetch = globalThis.fetch;
  const realLog = console.log;
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : null });
    // 204 is what a successful workflow_dispatch answers, and ghDispatch branches
    // on it. `null` body, not "": node's Response constructor refuses a body on a
    // 204 outright, which is a truer stub than a 200 would be.
    return new Response(null, { status: String(url).includes("api.github.com") ? ghStatus : 204 });
  };
  console.log = () => {};                       // the Worker narrates; not our output
  try {
    const request = new Request("https://w.example/telegram", {
      method: "POST",
      headers: {
        "X-Telegram-Bot-Api-Secret-Token": secret,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ update_id: 123, message: { chat: { id: chatId }, text,
        date: Date.parse("2026-09-04T02:35:00Z") / 1000 } }),
    });
    const response = await worker.fetch(request, ENV);
    return { status: response.status, seen };
  } finally {
    globalThis.fetch = realFetch;
    console.log = realLog;
  }
}

const dispatches = (seen) => seen.filter((c) => c.url.includes("api.github.com"));

async function run() {
  const failures = [];

  // ── the parse ──
  //
  // (what was typed, what it must decide, why this one is on the list)
  const words = [
    ["retry", "retry", "the new verb, the whole point of the change"],
    ["tryagain", "retry", "the one synonym that cannot be misread"],
    ["Retry", "retry", "case is not a command"],
    ["  retry  ", "retry", "a thumb-typed reply carries whitespace"],
    ["rerun", "drop", "READ THIS TWICE: rerun has always meant drop"],
    ["drop", "drop", "unchanged by this edit"],
    ["publish", "publish", "unchanged by this edit"],
    ["list", "list", "unchanged by this edit"],
    ["again", null, "not a verb — it would read as retry and is not one"],
    ["redo", null, "same"],
    ["ok", null, "ordinary chat, excluded on purpose"],
    ["yes", null, "same"],
    ["sure", null, "same"],
    ["no", null, "same — and it would read as a drop"],
    ["retry the deck please", null, "a sentence is not a command"],
    ["", null, "an empty message"],
    [undefined, null, "a photo or a sticker has no text at all"],
  ];
  for (const [text, want, why] of words) {
    const got = parseReply(text)?.decision ?? null;
    if (got !== want) {
      failures.push(`PARSE ${JSON.stringify(text)} decided ${JSON.stringify(got)}, ` +
                    `wanted ${JSON.stringify(want)} — ${why}`);
    }
  }

  // The slug rides along for the verbs that act on a named deck.
  const named = parseReply("publish 20260902_6pm-picked-up_068b42");
  if (named?.slug !== "20260902_6pm-picked-up_068b42") {
    failures.push(`PARSE the deck id was lost: ${JSON.stringify(named)}`);
  }
  if (parseReply("retry")?.slug !== "") {
    failures.push("PARSE a bare verb should carry an empty slug, not undefined");
  }

  // Belt and braces on the one mapping a future edit is most likely to break by
  // tidying the synonym lists together.
  if (VERBS.rerun !== "drop") {
    failures.push(`PARSE VERBS.rerun is now ${VERBS.rerun} — it has always been drop, ` +
                  "and a deck would be discarded by somebody asking for another run");
  }

  // ── the route ──
  //
  // retry starts a new build; every other verb acts on a deck that already exists.
  const r = await reply("retry");
  const hits = dispatches(r.seen);
  if (hits.length !== 1) {
    failures.push(`ROUTE retry made ${hits.length} GitHub calls, wanted exactly 1`);
  } else {
    if (!hits[0].url.includes("auto-post.yml")) {
      failures.push(`ROUTE retry went to ${hits[0].url} — it must build a fresh deck, ` +
                    "and a stopped run has no held deck for review.yml to act on");
    }
    if (hits[0].body?.inputs?.mode !== "publish") {
      failures.push("ROUTE retry dispatched auto-post without mode=publish, so the " +
                    "retried run would build and not post");
    }
    if (hits[0].body?.inputs?.retry !== "true" || hits[0].body?.inputs?.request_id !== "tg-123") {
      failures.push("ROUTE retry lost its intent or stable delivery id");
    }
    if (hits[0].body?.inputs?.slot_id !== "2026-09-04_0800") {
      failures.push("ROUTE retry lost the slot at the time the owner sent the message");
    }
  }
  if (!r.seen.some((c) => c.url.includes("api.telegram.org"))) {
    failures.push("ROUTE retry sent no acknowledgment, so the reply meets silence " +
                  "while the runner spins up");
  }

  const held = dispatches((await reply("publish 20260902_6pm-picked-up_068b42")).seen);
  if (held.length !== 1 || !held[0].url.includes("review.yml")) {
    failures.push(`ROUTE publish <slug> went to ${held[0]?.url ?? "nowhere"}, ` +
                  "wanted review.yml");
  }
  if (held[0]?.body?.inputs?.decision !== "publish") {
    failures.push("ROUTE publish lost its decision on the way to review.yml");
  }
  if (held[0]?.body?.inputs?.request_id !== "tg-123") {
    failures.push("ROUTE publish lost its stable delivery id");
  }

  // rerun must reach review.yml as a drop, not auto-post as a retry. Same
  // assertion as the parse table, made where it would actually cost something.
  const rerun = dispatches((await reply("rerun 20260902_6pm-picked-up_068b42")).seen);
  if (rerun[0]?.url?.includes("auto-post.yml")) {
    failures.push("ROUTE rerun dispatched a new build — it means drop");
  }

  // The security gate is the reason a public URL is safe to have. Both refusals
  // answer 200 so Telegram stops retrying, which makes the dispatch count the
  // only readable evidence that nothing happened.
  for (const [label, opts] of [
    ["a stranger's chat", { chatId: "999" }],
    ["a forged push", { secret: "wrong" }],
  ]) {
    const bad = await reply("retry", opts);
    if (dispatches(bad.seen).length) {
      failures.push(`GATE ${label} dispatched a workflow`);
    }
    if (bad.status !== 200) {
      failures.push(`GATE ${label} answered ${bad.status}; Telegram retries anything else`);
    }
  }

  for (const text of ["retry", "publish", "force"]) {
    const failed = await reply(text, {ghStatus: 503});
    if (failed.status !== 502 || failed.seen.some(c => c.body?.text?.includes("on it"))) {
      failures.push(`DISPATCH ${text} hid GitHub failure or falsely acknowledged success`);
    }
    if (!failed.seen.some(c => c.body?.text?.includes("could not start"))) {
      failures.push(`DISPATCH ${text} gave no failure notice`);
    }
  }

  const total = words.length + 3 + 7 + 3 + 1 + 4 + 6;
  if (failures.length) {
    console.log(`parse-reply: ${failures.length}/${total} failed`);
    for (const line of failures) console.log(`  ${line}`);
    return 1;
  }
  console.log(`parse-reply: ${total}/${total} passed (${words.length} verbs, the deck id, ` +
              "retry to auto-post and publish to review, the owner gate)");
  return 0;
}

process.exit(await run());
