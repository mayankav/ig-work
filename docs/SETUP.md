# Build this from scratch

A step-by-step guide to standing up an account like [@suresilly](https://instagram.com/suresilly): a bot that writes and posts Instagram carousels twice a day on its own, holds the weak ones for a one-word reply on Telegram, and runs entirely on free allowances.

This is the **infrastructure** guide — the accounts, keys, and wiring. It is not about the writing engine itself; that lives in [`.agents/skills/suresilly-carousel/SKILL.md`](../.agents/skills/suresilly-carousel/SKILL.md).

Everything below is free. No card, no paid plan, at two posts a day.

---

## The shape of it

```
Cloudflare Worker (the clock) ──dispatch──▶ GitHub Actions (auto-post) ──▶ Instagram
        ▲                                          │
        │                              a weak deck is held
   your reply                                      ▼
   on Telegram ──push──▶ same Worker ──dispatch──▶ GitHub Actions (review) ──▶ reply to you
```

Three services, each doing the one thing it is best at:

| Service | Job | Why this one |
|---|---|---|
| **GitHub Actions** | Runs the code, holds the secrets, does the posting | Free CI, already where the code lives |
| **Cloudflare Worker** | The clock, and the reply inbox | GitHub's own schedule is unreliable (see below); Workers are free and fire on time |
| **Telegram bot** | Alerts you, takes your one-word reply | Free, instant to a phone, no email domain to set up |

**Why not GitHub's own `schedule:`?** It is best-effort. Under load GitHub delivers the event late or drops it and no run is created — we lost a 20:00 post entirely and saw an 08:00 post run five hours late. An independent timer is the only real fix.

---

## Before you start

You'll create accounts on four services. All free:

- [GitHub](https://github.com) — host the repo, run the workflows
- [Cloudflare](https://dash.cloudflare.com/sign-up) — the Worker (clock + reply inbox)
- [Telegram](https://telegram.org) — the alert channel
- A **Meta / Instagram** account set up for the Graph API (the fiddliest part — [Part 5](#part-5--instagram-posting))

Optional, for the writing engine itself (skip if you only want the infra): API keys from [Google AI Studio](https://aistudio.google.com/apikey) (Gemini), [Groq](https://console.groq.com/keys), and Cloudflare Workers AI.

---

## Part 1 — The repo

1. Put your code in a GitHub repo. A workflow lives at `.github/workflows/<name>.yml`; GitHub picks them up automatically.
2. Decide your two daily post times **in UTC** (cron uses UTC). Example: `30 2 * * *` and `30 14 * * *` are 08:00 and 20:00 IST.

That's all for now — the workflows come to life once the secrets exist.

---

## Part 2 — Telegram bot

The bot is how the system reaches your phone and how you reply.

1. In Telegram, open a chat with **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot`, pick a name and username. BotFather replies with a **bot token** (`123456:ABC-…`). Save it.
3. **Get your chat id:** message your new bot once (say "hi"), then visit this in a browser:
   ```
   https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
   ```
   Find `"chat":{"id":123456789}` — that number is your **chat id**. Save it.

You now have `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

> **Why a chat id gate?** Anyone can message a bot. The system obeys **only** your chat id and ignores every other sender — that is the whole security model on the reply path, so it matters that you use your own id.

---

## Part 3 — GitHub secrets and the workflows

### Add the secrets

In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add each one you have:

| Secret | For |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Alerts and replies |
| `TELEGRAM_CHAT_ID` | The one chat allowed to reply |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | Posting to Instagram (Part 5) |
| *(engine keys: `GEMINI_API_KEY`, `GROQ_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, …)* | The writing engine |

### Add the kill switch

**Settings → Secrets and variables → Actions → Variables tab → New variable:** name `SS_HALT`, value `0`. Set it to `1` from your phone to stop everything mid-flight, even a queued run.

### The two workflows

- **`auto-post.yml`** — builds a deck and posts it. It runs on `workflow_dispatch` (a button / the Worker) and reads a `mode` input: `publish` posts, `build` just builds. A weak deck is *held* instead of posted, and a Telegram alert goes out asking what to do.
- **`review.yml`** — takes one decision (`list` / `publish` / `drop`) plus a deck id as inputs, acts on a held deck, and replies to you on Telegram.

Copy the structure from this repo: [auto-post.yml](../.github/workflows/auto-post.yml) and [review.yml](../.github/workflows/review.yml). The key idea is that **both the clock and your reply are just `workflow_dispatch` calls with inputs** — which is exactly what a Cloudflare Worker can trigger over the GitHub API.

---

## Part 4 — The Cloudflare Worker (clock + reply inbox)

One small Worker does both jobs: a **cron** fires the daily posts, and an **HTTP handler** receives your Telegram replies and dispatches the review workflow. Full annotated source: [`ops/dispatch-worker/src/index.js`](../ops/dispatch-worker/src/index.js).

### 4a. A GitHub token for the Worker

The Worker needs permission to press "Run workflow". Least-privilege:

1. github.com → **Settings → Developer settings → [Fine-grained tokens](https://github.com/settings/personal-access-tokens) → Generate new token.**
2. **Resource owner:** you. **Repository access:** Only select repositories → your repo.
3. **Permissions → Repository → Actions: Read and write.** (Metadata: Read is added automatically.)
4. Set an expiry you'll remember to rotate. Generate, copy the `github_pat_…` value.

This becomes the Worker secret `GH_DISPATCH_TOKEN`.

### 4b. A trigger key

Any long random string — it guards the manual "post now" URL so the public address can't publish. Generate one with `openssl rand -hex 24` (or any password generator). This becomes `TRIGGER_KEY`.

### 4c. A webhook secret

Another random string — Telegram sends it back on every push so the Worker knows the request is really from Telegram. Generate with `openssl rand -hex 32`. This becomes `TELEGRAM_WEBHOOK_SECRET`.

### 4d. Deploy the Worker (dashboard, no tooling)

1. [dash.cloudflare.com](https://dash.cloudflare.com) → **Compute (Workers)** → **Create** → **Create Worker.** Name it (e.g. `suresilly-dispatch`), Deploy the starter, then **Edit code**.
2. Delete the starter, paste the contents of [`src/index.js`](../ops/dispatch-worker/src/index.js), **Deploy**.
3. **Settings → Variables and Secrets → Add**, type **Secret**, for each:
   - `GH_DISPATCH_TOKEN` = the GitHub token (4a)
   - `TRIGGER_KEY` = the random string (4b)
   - `TELEGRAM_WEBHOOK_SECRET` = the random string (4c)
   - `TELEGRAM_CHAT_ID` = your chat id (Part 2)
   Then **Deploy** again so the secrets attach.
4. **Settings → Triggers → Cron Triggers → Add**, once each (UTC): your two post times, e.g. `30 2 * * *` and `30 14 * * *`.

> **Deploying is not the same as `git push`.** The Worker runs a copy of the code that Cloudflare holds, *not* your repo. Every time you change `index.js`, you must redeploy (paste + Deploy, or `npx wrangler deploy`) or the live Worker keeps running the old version.

### 4e. Test the clock (no post)

Open in a browser — build only, safe, does not publish:
```
https://<worker-name>.<your-subdomain>.workers.dev/?key=<TRIGGER_KEY>
```
A run should appear in your repo's **Actions** tab within seconds. Add `&mode=publish` to actually post.

---

## Part 5 — Instagram posting

The one part that isn't a five-minute signup. Instagram only allows automated posting through the **Graph API**, which needs:

1. An Instagram account switched to **Professional (Business or Creator)**.
2. A **Facebook Page** linked to that Instagram account.
3. A **Meta developer app** ([developers.facebook.com](https://developers.facebook.com)) with the Instagram Graph API product added.
4. A **long-lived access token** with `instagram_basic`, `instagram_content_publish`, and `pages_show_list` permissions, plus your **Instagram user id**.

These become `IG_ACCESS_TOKEN` and `IG_USER_ID`. Meta's own [Content Publishing guide](https://developers.facebook.com/docs/instagram-api/guides/content-publishing) is the authority and changes often, so follow it rather than any snapshot here.

> **One quirk that shapes the whole design:** Instagram fetches each image *itself*, by URL, at post time — you can't upload bytes directly. So the slides have to be **publicly reachable** before the post exists. This repo publishes them to GitHub Pages (`media.suresilly.com`) first, waits for them to go live, then posts. That's why building and publishing are separate steps.

---

## Part 6 — Turn on instant replies

This connects Telegram → Worker so a reply acts in seconds instead of being polled for.

Paste into a browser, swapping the two `<...>` values:
```
https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<worker-name>.<your-subdomain>.workers.dev/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```
Expect `{"ok":true,"result":true,"description":"Webhook was set"}`.

Confirm:
```
https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```
You want your Worker URL and `"pending_update_count":0`.

> **`setWebhook` and polling are mutually exclusive.** Registering the webhook turns off `getUpdates` at Telegram's end. That's intended — push replaces polling; you don't run both.

Now send `list` in the chat. A **review** run should appear in your repo's Actions within seconds, and the bot should reply.

---

## Part 7 — Retire GitHub's schedule (do this last)

Once — and only once — you've seen a Worker-triggered post succeed, remove any `schedule:` block from `auto-post.yml` so there's exactly one clock. If both fire, you get two posts from two timers.

**Order matters:** verify the Worker *first*. Delete GitHub's schedule before the Worker is proven and nothing posts in the gap.

---

## The daily reality

- **Post now:** `…/?key=<TRIGGER_KEY>&mode=publish` · **test wiring:** drop `&mode=publish`
- **A held deck** reaches Telegram; reply `publish <id>`, `rerun <id>`, or `list`
- **Stop everything:** set repo variable `SS_HALT` to `1`
- **Worker logs:** Cloudflare dashboard → the Worker → **Logs** (`204` = a successful dispatch)
- **Rotate tokens** before they expire; update the matching secret and nothing else changes

---

## Common snags

| Symptom | Cause | Fix |
|---|---|---|
| Reply does nothing, no review run appears | The Worker is running old code | Redeploy the Worker (paste + Deploy). `git push` does not deploy it. |
| `setWebhook` returns `ok:false` | Wrong bot token, or a bad URL | Recheck the token; the URL must be `https` and end in `/telegram` |
| Posts fire twice a day from nowhere | Both GitHub's schedule and the Worker are live | Remove the `schedule:` block (Part 7) |
| Instagram post fails, build is fine | Token expired, or slides not public yet | Refresh `IG_ACCESS_TOKEN`; confirm the Pages URL returns the image |
| A word like "ok" in chat did nothing | By design | Only explicit verbs (`publish`/`rerun`/`list`) act, so casual chat can't post |
