import {resources} from './resource-status.js';
import { ReviewWindow, parseWindowReply } from "./review-window.js";
export { ReviewWindow };
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
  // Also not about a held deck: this builds the deck the gate refused and holds
  // it for you to look at. It cannot post — auto-post only publishes on a
  // schedule or on mode=publish, and this dispatches mode=force — so the picture
  // arrives and then waits for a separate `publish`.
  force: "force", override: "force", build: "force",
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

// Use the trigger's intended time, never the time a delayed handler starts.
// This is the same IST date-and-slot contract as scripts/posting_slots.py.
export function postingSlot(scheduledTime, cron) {
  const hour = { "30 2 * * *": "08", "30 14 * * *": "20" }[cron];
  if (!hour || !Number.isFinite(scheduledTime)) throw new Error("Invalid posting trigger");
  const local = new Date(scheduledTime + 330 * 60 * 1000);
  if (Number.isNaN(local.getTime()) || local.getUTCHours() !== Number(hour) ||
      local.getUTCMinutes() !== 0) throw new Error("Trigger time does not match its slot");
  return `${local.toISOString().slice(0, 10)}_${hour}00`;
}

export function replySlot(messageTime) {
  if (!Number.isSafeInteger(messageTime) || messageTime < 0) throw new Error("Invalid reply time");
  const local = new Date(messageTime * 1000 + 330 * 60 * 1000);
  const hour = local.getUTCHours() >= 20 || local.getUTCHours() < 8 ? 20 : 8;
  if (local.getUTCHours() < 8) local.setUTCDate(local.getUTCDate() - 1);
  local.setUTCHours(hour, 0, 0, 0);
  return postingSlot(local.getTime() - 330 * 60 * 1000, hour === 8 ? "30 2 * * *" : "30 14 * * *");
}

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
      body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: text + '\n\n' + await resources(env) }),
    });
  } catch (e) {
    console.log(`ack failed (ignored): ${e}`);
  }
}

function dispatch(env, cron, mode = "publish", extra = {}) {
  // The auto-post clock. Cron passes no mode, so it publishes; the manual button
  // passes mode explicitly and defaults to a safe build.
  return ghDispatch(env, WORKFLOW, { mode, ...extra }, `cron=${cron ?? "manual"} mode=${mode}`);
}

export default {
  // Cloudflare's clock. event.cron is the expression that fired, kept for the
  // log so the two daily slots are distinguishable.
  async scheduled(event, env, ctx) {
    const slot = postingSlot(event.scheduledTime, event.cron);
    ctx.waitUntil(dispatch(env, event.cron, "publish", { slot_id: slot, request_id: `clock-${slot}` }).then((result) => {
      if (result.status !== 204) throw new Error(`Scheduled dispatch failed (${result.status})`);
    }));
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

    const reviewRoute = /^\/review\/([a-f0-9]{16})\/(register|status|claim|complete)$/.exec(url.pathname);
    if (request.method === "POST" && reviewRoute) {
      if (!env.REVIEW_WINDOW_SECRET || request.headers.get("X-Review-Key") !== env.REVIEW_WINDOW_SECRET) return new Response("forbidden", {status: 403});
      if (!env.REVIEW_WINDOWS) return new Response("Review storage is not configured", {status: 503});
      const stub = env.REVIEW_WINDOWS.get(env.REVIEW_WINDOWS.idFromName(reviewRoute[1]));
      const body = await request.json();
      if (body.token && body.token !== reviewRoute[1]) return new Response("wrong token", {status: 400});
      return stub.fetch(new Request(`https://review/${reviewRoute[2]}`, {method: "POST", body: JSON.stringify({...body, token: reviewRoute[1]})}));
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
    // build is the default and publish is the only word that posts. force builds
    // past a copy-craft gate and HOLDS the result, so it is offered here too —
    // the URL button is the same set of choices as the Telegram reply.
    const asked = url.searchParams.get("mode");
    const mode = asked === "publish" ? "publish" : asked === "force" ? "force" : "build";
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

    const windowCommand = parseWindowReply(message.text, message.reply_to_message?.caption || message.reply_to_message?.text || "");
    if (windowCommand) {
      if (!Number.isSafeInteger(update.update_id) || update.update_id < 0 || !env.REVIEW_WINDOWS) return new Response("Review cannot start", {status: 503});
      const stub = env.REVIEW_WINDOWS.get(env.REVIEW_WINDOWS.idFromName(windowCommand.token));
      const response = await stub.fetch(new Request("https://review/decide", {method: "POST", body: JSON.stringify({...windowCommand, request_id: `tg-${update.update_id}`})}));
      const result = await response.json();
      await ack(env, response.ok ? (result.duplicate ? "This reply was already received." :
        windowCommand.decision === "drop" ? "Cancelled this carousel. Future posts are unchanged." :
        windowCommand.decision === "publish" ? "Approval received. Publication is queued." :
        "Redo received. Automatic posting is paused for this carousel.") : (result.error || "The review action failed."));
      return new Response("ok", {status: response.status >= 500 ? 502 : 200});
    }
    if (env.REVIEW_WINDOWS && (/Review ID:/i.test(message.reply_to_message?.caption || message.reply_to_message?.text || "") ||
        /^\s*(approve|approval|disapprove|disapproval|cancel|reject|redo)(?:\s+[1-9])?\s*$/i.test(message.text || ""))) {
      await ack(env, "Reply to the preview message, or include its Review ID. Use approve, disapprove, redo, or redo 4.");
      return new Response("ok");
    }
    const command = parseReply(message.text);
    if (!command) {
      // Ordinary chatter, or a word that is not a verb. Nothing to do — and that
      // includes "ok"/"yes"/"no"/"sure", which are excluded on purpose.
      console.log("telegram: not a command, ignored");
      return new Response("ok", { status: 200 });
    }
    // Telegram retries the same update_id. Carry it through to the durable
    // reservation instead of treating each delivery as a new human request.
    if (!Number.isSafeInteger(update.update_id) || update.update_id < 0) {
      console.log("telegram: command has no valid delivery id, ignored");
      return new Response("ok", { status: 200 });
    }
    const requestId = `tg-${update.update_id}`;

    // retry and force are the two verbs that are not decisions about a HELD
    // deck, so neither goes to review.yml. A run that stopped on a gate produced
    // nothing to publish or drop; what you want is another attempt at today's
    // slot, which means auto-post. The auto-post run sends its own report when it
    // finishes, which replaces the ack in your reading of the chat.
    //
    // The mode is the whole difference. `retry` draws a fresh moment and every
    // gate applies, so it publishes if it passes. `force` builds the deck the
    // gate refused, and mode=force is NOT mode=publish — auto-post's publish step
    // is gated on that word, so a forced deck is held and cannot go out until you
    // reply publish to the picture.
    if (command.decision === "retry" || command.decision === "force") {
      const forced = command.decision === "force";
      let slot;
      if (!forced) {
        try { slot = replySlot(message.date); }
        catch { return new Response("ignored: missing reply time", {status: 200}); }
      }
      const r = await dispatch(env, null, forced ? "force" : "publish",
        { retry: forced ? "false" : "true", request_id: requestId,
          ...(forced ? {} : {slot_id: slot}) });
      console.log(`telegram: dispatched auto-post ${command.decision} status=${r.status}`);
      if (r.status !== 204) {
        await ack(env, "The request could not start on GitHub. Nothing was confirmed. Telegram will try delivery again.");
        return new Response("dispatch failed", {status: 502});
      }
      await ack(env, forced ? "⏳ on it — building it anyway…" : "⏳ on it — retrying…");
      return new Response("ok", { status: 200 });
    }

    // A reply the instant it is understood, so the ~20-40s of runner spin-up is
    // not silence. The real answer ("Posted …", "Dropped …", the held list) comes
    // from review.yml afterwards and replaces this in your reading of the chat.
    const what = command.slug ? `${command.decision} ${command.slug}` : command.decision;
    const r = await ghDispatch(env, REVIEW_WORKFLOW,
      { decision: command.decision, slug: command.slug, request_id: requestId },
      `telegram ${command.decision} ${command.slug || "(none)"}`);
    console.log(`telegram: dispatched review ${command.decision} ${command.slug || "(none)"} status=${r.status}`);
    if (r.status !== 204) {
      await ack(env, "The request could not start on GitHub. Nothing was confirmed. Telegram will try delivery again.");
      return new Response("dispatch failed", {status: 502});
    }
    await ack(env, `⏳ on it — ${what}…`);
    return new Response("ok", { status: 200 });
  },
};
