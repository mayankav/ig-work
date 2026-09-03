# Deploy the new alert template and the `force` reply

Five steps. Do them in this order. The order matters — step 2 sends a word to
GitHub that only exists after step 1.

Total time: about 10 minutes, plus one carousel build.

---

## Step 1 — Send the code to GitHub

Your machine has one commit that GitHub does not have. GitHub has one commit that
your machine does not have (the deck that posted this evening). They touch
different files, so this joins cleanly.

**Do this first.** The Worker in step 2 tells GitHub to run in `force` mode.
GitHub only accepts that word after this push.

```bash
cd /Users/mayankav/Documents/writing/ig-work && git pull --rebase && git push
```

Then check nothing broke in the join:

```bash
cd /Users/mayankav/Documents/writing/ig-work && for t in .agents/skills/suresilly-carousel/tests/test_*.py; do if grep -q '^import pytest\|^from pytest' "$t"; then .agents/skills/suresilly-carousel/.venv/bin/python -m pytest "$t" -q >/dev/null || echo "FAILED $t"; else .agents/skills/suresilly-carousel/.venv/bin/python "$t" >/dev/null || echo "FAILED $t"; fi; done; echo "done — no FAILED lines above means all 30 suites pass"
```

---

## Step 2 — Deploy the Worker

The Worker reads your Telegram replies. It does not know the word `force` yet.
A commit does not change it. You must deploy it.

```bash
cd /Users/mayankav/Documents/writing/ig-work/ops/dispatch-worker && npx wrangler deploy
```

If it asks you to log in, run `npx wrangler login` first.

Do not set the secrets again. They are already there.

Check it worked: <https://dash.cloudflare.com/> → Workers → `suresilly-dispatch`
→ the "Last deployed" time is now.

---

## Step 3 — See the new message. This costs nothing.

This sends you the real Telegram message. It does not build a deck. It does not
use an idea. You can run it as many times as you like.

```bash
cd /Users/mayankav/Documents/writing/ig-work && set -a && . ./.env.local && set +a && .agents/skills/suresilly-carousel/.venv/bin/python scripts/dashboard.py --status stopped --note "slide 9 must name a kind of person, not 'anyone'; slide 4 uses 'emotional', which is 4 syllables or more [faults per attempt: 13, 5, 4, 3, 3, 3, 3]" --run-url "https://github.com/mayankav/ig-work/actions" --no-retry --format html > "$TMPDIR/msg.html" && .agents/skills/suresilly-carousel/.venv/bin/python scripts/notify.py --subject "@suresilly — test of the new message" --body "test" --telegram-html "$(cat "$TMPDIR/msg.html")"
```

**Read the message on your phone.** Ask yourself one question: after one read, do
you know what to do? If any line is unclear, tell me the line.

`set -a && . ./.env.local` is needed. Without it the send fails silently. That is
the likely cause of the two `every configured channel failed` warnings you saw.

---

## Step 4 — Prove `force` works

Two ways. Pick one.

### The cheap way — wait

Do nothing. The next time a check refuses a deck, you get the red message. Reply:

```
force
```

The Worker starts a build that ignores the style checks. You get the picture. It
does **not** post.

### The now way — build one immediately

Open <https://github.com/mayankav/ig-work/actions/workflows/auto-post.yml> →
**Run workflow** → set **mode** to `force` → **Run workflow**.

⚠️ This uses up one idea, the same as a real run. Only do it if you want to see
`force` work today.

Expect: an orange message, the contact sheet, and a list of the checks it ignored.
Nothing is posted.

---

## Step 5 — Publish the held deck

The orange message ends with a line like `publish a1b2c3`. Reply with exactly
that:

```
publish a1b2c3
```

Now it posts. This second reply is the only thing that can post a forced deck.

To throw it away instead, reply `rerun a1b2c3`.

---

## The words the bot understands

| Reply | What it does |
|---|---|
| `publish <id>` | Post the held deck now |
| `rerun <id>` | Throw the held deck away |
| `force` | Build the refused deck and hold it. Does not post. |
| `retry` | Start again with a new idea |
| `list` | Show what is waiting for you |

`ok`, `yes` and `no` do nothing. That is on purpose — they arrive in chat by
accident and one of them would post.

⚠️ `rerun` means **throw away**. It does not mean "run again". Use `retry` for
that.

---

## If something goes wrong

| What you see | What to do |
|---|---|
| `git pull` reports a conflict | Stop. Send me the file name. |
| `wrangler deploy` asks for a login | Run `npx wrangler login`, then deploy again. |
| Step 3 sends nothing | You missed `set -a && . ./.env.local`. Run the whole line again. |
| You reply `force` and nothing happens | Step 2 did not finish. Deploy the Worker again. |
| A message looks cut off | Tell me. The caption limit is measured, so this is a bug, not a setting. |
