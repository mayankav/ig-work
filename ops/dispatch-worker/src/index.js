// Off-GitHub timer for the @suresilly auto-post workflow.
//
// GitHub Actions `schedule:` triggers are best-effort: under load the event is
// delivered late or dropped and no run is created. On 2026-09-01 the 20:00 IST
// slot never fired at all, and the 08:00 IST slot ran ~5h late. This Worker is
// an independent clock — its Cron Triggers fire on Cloudflare's schedule and
// call GitHub's workflow_dispatch API, so a backlog in GitHub's own scheduler
// can no longer cost a post.
//
// It PUBLISHES: the dispatch body sets inputs.mode = "publish". auto-post.yml
// only publishes when the event is a schedule OR inputs.mode == "publish", and
// a workflow_dispatch is not a schedule — so the mode input is required here,
// not optional. A human pressing "Run workflow" in the GitHub UI still defaults
// to build, which is the point of that button.

const OWNER = "mayankav";
const REPO = "ig-work";
const WORKFLOW = "auto-post.yml";
const REVIEW_WORKFLOW = "review.yml";
const REF = "main";

// The verbs a Telegram reply may carry, and what each maps to. This is a copy of
// telegram_review.VERBS on purpose: the reply now arrives here, at the webhook,
// instead of being polled by a GitHub runner, so the parse has to live here too.
// Deliberately no "ok", "yes", "no" or "sure" — those turn up in ordinary chat by
// accident and one of them would publish. Every verb is one somebody had to mean.
//
// NOTE "rerun" means DROP, and always has. It reads like "run it again" and does
// the opposite, which is why "retry" is spelled out separately below rather than
// folded into the obvious synonym set. Do not add "rerun"/"again"/"redo" to retry.
const VERBS = {
  publish: "publish", post: "publish", approve: "publish", ship: "publish",
  rerun: "drop", drop: "drop", reject: "drop", discard: "drop",
  list: "list", held: "list", pending: "list", status: "list",
  // The only verb that does not go to review.yml. A run that stopped on a gate
  // has no held deck to act on — there is nothing to publish or drop — so this
  // starts a fresh auto-post instead. See telegram() below.
  retry: "retry", tryagain: "retry",
};
// One known word, then an optional deck id, and nothing else. Anything that is
// not this shape is not a command and is ignored — the message text is data.
const COMMAND = /^\s*([a-z]+)\s*([\w-]*)\s*$/i;

function parseReply(text) {
  const match = COMMAND.exec(text || "");
  if (!match) return null;
  const decision = VERBS[match[1].toLowerCase()];
  if (!decision) return null;
  return { decision, slug: match[2].trim() };
}

// Named alongside the default export purely so test/parse-reply.test.mjs can
// reach them. Cloudflare loads the default export and ignores these; a Worker is
// allowed other named exports (that is how Durable Objects are declared).
export { parseReply, VERBS };

async function ghDispatch(env, workflow, inputs, label) {
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        // GitHub refuses an API request with no User-Agent (403). Any string
        // works; this one names the caller so it is legible in the audit log.
        "User-Agent": "suresilly-dispatch-worker",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: REF, inputs }),
    },
  );
  // A successful dispatch is 204 No Content. Anything else carries a body that
  // explains the refusal — bad/expired token, wrong ref, workflow not found.
  const body = res.status === 204 ? "" : await res.text();
  console.log(
    `dispatch ${label} workflow=${workflow} status=${res.status} ${body}`.trim(),
  );
  return { status: res.status, body };
}

// A quick "on it…" so a reply is not met with silence while the runner spins up
// (~20-40s before review.yml can answer). Best-effort and fire-and-forget: if the
// token is missing or the call fails, the real answer still lands later, so this
// must never block or throw. Telegram's own typing indicator expires in ~5s and
// the Worker returns immediately, so a real message is the only honest signal.
async function ack(env, text) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return;
  try {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text }),
    });
  } catch (e) {
    console.log(`ack failed (ignored): ${e}`);
  }
}

function dispatch(env, cron, mode = "publish") {
  // The auto-post clock. Cron passes no mode, so it publishes; the manual button
  // passes mode explicitly and defaults to a safe build.
  return ghDispatch(env, WORKFLOW, { mode }, `cron=${cron ?? "manual"} mode=${mode}`);
}

export default {
  // Cloudflare's clock. event.cron is the expression that fired, kept for the
  // log so the two daily slots are distinguishable.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env, event.cron));
  },

  // Two doors, and only two.
  //
  //   POST /telegram  — Telegram pushes a reply here the instant you send it.
  //                     This replaces the every-20-minutes GitHub poll: the
  //                     Worker authenticates the push, reads the command, and
  //                     dispatches review.yml, which acts and replies. Instant,
  //                     and no runner wakes up unless there is actually a reply.
  //
  //   GET  /?key=…     — the manual "post now" button, unchanged. A valid key
  //                     defaults to a safe BUILD; add &mode=publish to post.
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/telegram") {
      return this.telegram(request, env);
    }

    const key = url.searchParams.get("key");
    if (!env.TRIGGER_KEY || key !== env.TRIGGER_KEY) {
      return new Response(
        "suresilly-dispatch is running. Cron fires 02:30 and 14:30 UTC " +
          "(08:00 and 20:00 IST).\nAdd ?key=<TRIGGER_KEY> to build now, " +
          "or ?key=<TRIGGER_KEY>&mode=publish to publish now.\n",
        { status: key ? 403 : 200 },
      );
    }
    const mode = url.searchParams.get("mode") === "publish" ? "publish" : "build";
    const r = await dispatch(env, null, mode);
    const ok = r.status === 204;
    return new Response(
      ok
        ? `dispatched (mode=${mode}): auto-post is now running on GitHub.\n`
        : `dispatch failed (${r.status}):\n${r.body}\n`,
      { status: ok ? 200 : 502 },
    );
  },

  // A Telegram webhook update. The security model is exactly the runner's, moved
  // here: a shared secret proves the request is really from Telegram, and the
  // chat id proves it is really from the owner. The message text is DATA — two
  // verbs and an id are read out of it and nothing else is.
  async telegram(request, env) {
    // 1. Is this really Telegram? The secret_token set at setWebhook time comes
    //    back on every push in this header. Without it, anyone who learns the URL
    //    could POST a command. Always 200 so Telegram does not retry a rejected
    //    push forever.
    if (!env.TELEGRAM_WEBHOOK_SECRET ||
        request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.TELEGRAM_WEBHOOK_SECRET) {
      console.log("telegram: bad or missing secret token, ignored");
      return new Response("ignored", { status: 200 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("ok", { status: 200 });
    }

    const message = update.message || update.channel_post || {};
    const chatId = String((message.chat || {}).id ?? "");
    // 2. Is this really the owner? The whole security gate, before the text is
    //    read. Every other chat is ignored.
    if (!env.TELEGRAM_CHAT_ID || chatId !== String(env.TELEGRAM_CHAT_ID)) {
      console.log(`telegram: chat ${chatId || "(none)"} is not the owner, ignored`);
      return new Response("ok", { status: 200 });
    }

    const command = parseReply(message.text);
    if (!command) {
      // Ordinary chatter, or a word that is not a verb. Nothing to do — and that
      // includes "ok"/"yes"/"no"/"sure", which are excluded on purpose.
      console.log("telegram: not a command, ignored");
      return new Response("ok", { status: 200 });
    }

    // retry is the one verb that is not a decision about a HELD deck, so it does
    // not go to review.yml. A run that stopped on a gate produced nothing to
    // publish or drop; what you want is another attempt at today's slot, which
    // means auto-post with mode=publish. The auto-post run sends its own report
    // when it finishes, which replaces the ack in your reading of the chat.
    if (command.decision === "retry") {
      await ack(env, "⏳ on it — retrying…");
      const r = await dispatch(env, null, "publish");
      console.log(`telegram: dispatched auto-post retry status=${r.status}`);
      return new Response("ok", { status: 200 });
    }

    // A reply the instant it is understood, so the ~20-40s of runner spin-up is
    // not silence. The real answer ("Posted …", "Dropped …", the held list) comes
    // from review.yml afterwards and replaces this in your reading of the chat.
    const what = command.slug ? `${command.decision} ${command.slug}` : command.decision;
    await ack(env, `⏳ on it — ${what}…`);

    const r = await ghDispatch(env, REVIEW_WORKFLOW,
      { decision: command.decision, slug: command.slug },
      `telegram ${command.decision} ${command.slug || "(none)"}`);
    // Either way Telegram gets a 200: the command was accepted for dispatch. The
    // friendly reply ("Posted …", "Dropped …") comes from review.yml once the
    // runner has actually done it, on the same Telegram chat.
    console.log(`telegram: dispatched review ${command.decision} ${command.slug || "(none)"} status=${r.status}`);
    return new Response("ok", { status: 200 });
  },
};
