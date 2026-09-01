# suresilly-dispatch — an off-GitHub clock for auto-post

A tiny Cloudflare Worker whose only job is to fire the `auto-post` workflow on
time. It exists because GitHub Actions `schedule:` triggers are best-effort:
under load the event is delivered late or dropped and **no run is created**. On
2026-09-01 the 20:00 IST slot never fired, and the 08:00 IST slot ran ~5 hours
late. This Worker is an independent timer — Cloudflare's Cron Triggers call
GitHub's `workflow_dispatch` API — so a backlog in GitHub's own scheduler can
no longer cost a post.

**Cost: nothing.** The Workers Free plan includes 5 Cron Triggers per account
and 100,000 requests/day. This uses 2 triggers and ~2 requests/day. No card,
no paid plan.

---

## What you need (once)

1. **A Cloudflare account** — you already have one (the engine uses Workers AI
   for the critic).
2. **A GitHub token** the Worker uses to press "Run workflow". Least-privilege
   option — a **fine-grained personal access token**:
   - github.com → Settings → Developer settings → **Fine-grained tokens** →
     Generate new token.
   - **Resource owner:** `mayankav`. **Repository access:** Only select
     repositories → `mayankav/ig-work`.
   - **Permissions → Repository permissions → Actions: Read and write.**
     (Metadata: Read is added automatically. Nothing else is needed.)
   - Set an expiry you'll remember to rotate (e.g. 1 year), Generate, copy the
     `github_pat_…` value.
   - Classic-token alternative: a classic PAT with the **`workflow`** scope also
     works, but it is not repo-scoped, so prefer the fine-grained one.
3. **A trigger key** — any long random string, e.g. `openssl rand -hex 24`. It
   guards the manual "post now" URL so the public address can't publish.

---

## Deploy — Route A: dashboard (no local tooling) ← recommended

1. **dash.cloudflare.com → Workers & Pages → Create → Create Worker.** Name it
   `suresilly-dispatch`, Deploy the starter, then **Edit code**.
2. Delete the starter and paste the contents of [`src/index.js`](src/index.js).
   **Deploy.**
3. **Settings → Variables and Secrets → Add**, twice, type **Secret**:
   - `GH_DISPATCH_TOKEN` = the GitHub token from step 2 above
   - `TRIGGER_KEY` = the random string from step 3 above
   Save and **Deploy** again so the secrets attach.
4. **Settings → Triggers → Cron Triggers → Add Cron Trigger**, once each:
   - `30 2 * * *`
   - `30 14 * * *`
   (Both UTC = 08:00 and 20:00 IST.)
5. **Test without waiting for the clock** — open in a browser:
   `https://suresilly-dispatch.<your-subdomain>.workers.dev/?key=<TRIGGER_KEY>`
   That sends a **build** dispatch (safe, does not post). Watch a run appear at
   github.com/mayankav/ig-work/actions/workflows/auto-post.yml within seconds.
   Once you see it, the wiring works.

## Deploy — Route B: Wrangler CLI

```bash
cd ops/dispatch-worker
npm install
npx wrangler login          # or set CLOUDFLARE_API_TOKEN
npx wrangler deploy
npx wrangler secret put GH_DISPATCH_TOKEN   # paste the GitHub token
npx wrangler secret put TRIGGER_KEY         # paste the random string
```

Crons come from `wrangler.toml`, so they're set on deploy. Test locally with
`npm run dev` then visit `http://localhost:8787/__scheduled?cron=30+2+*+*+*`,
or hit the deployed `?key=…` URL as in Route A.

---

## The one required follow-up: stop GitHub's own scheduler

Once — and only once — you've seen a Worker-triggered run succeed, remove the
`schedule:` block from [`.github/workflows/auto-post.yml`](../../.github/workflows/auto-post.yml)
so there is exactly one clock. If both fire, you get two posts a day from two
timers.

Delete these four lines (keep `workflow_dispatch:` and everything else):

```yaml
  schedule:
    - cron: "30 2 * * *"    # 08:00 IST
    - cron: "30 14 * * *"   # 20:00 IST
```

`MODE` in the workflow still resolves correctly afterwards: with no schedule,
`github.event_name` is always `workflow_dispatch`, so `MODE` follows
`inputs.mode` — which this Worker sets to `publish`, and which a manual UI run
leaves at `build`.

**Order matters.** Deploy + verify the Worker *first*. If you delete GitHub's
schedule before the Worker is live, nothing posts in the gap.

---

## Operating it

- **Post now (real):** `…/?key=<TRIGGER_KEY>&mode=publish`
- **Test the wiring (no post):** `…/?key=<TRIGGER_KEY>` (defaults to build)
- **Logs:** dashboard → the Worker → Logs (or `npm run tail`). Each fire prints
  `dispatch cron=… mode=… status=204`. `204` is success; anything else prints
  GitHub's error body (an expired token shows here first).
- **Pause everything:** the engine's kill switch still wins. Set the repo
  variable `SS_HALT=1` (github.com/mayankav/ig-work/settings/variables/actions)
  and the workflow skips no matter who triggered it.
- **Rotate the token:** regenerate the fine-grained PAT before expiry and update
  the `GH_DISPATCH_TOKEN` secret. Nothing else changes.

## Why not just keep retrying GitHub's schedule?

You can't — GitHub decides when (and whether) a `schedule:` event fires; there
is no retry or alert. Moving the clock off GitHub is the only real fix, and an
external dispatcher is the pattern GitHub itself points to. Cloudflare is simply
the free timer you already have an account for.
