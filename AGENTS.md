# @suresilly: easy-going tiny-truth posts

A small green donkey, warm paper, one line worth sending to someone. Two posts a day, and you approve each one on Telegram.

The old gated carousel engine is frozen on the `obsolete/carousel-engine-v1` branch. Don't bring its rules back. The reason for the change is in `docs/pivot/quote-pages-teardown.md`.

## Run it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium
.venv/bin/python -m suresilly.run build --format list        # writes posts/<slug>/
.venv/bin/python -m pytest -q
(cd ops/dispatch-worker && npm test)
```

The writer reads `GEMINI_API_KEY` (or `GROQ_API_KEY`) from the environment or from `.env.local`.

## How a post happens

1. At 08:00 and 20:00 IST the Cloudflare Worker (`ops/dispatch-worker`) dispatches `auto-post.yml` with `mode=publish`.
2. `write.py` writes the post: a draft, then an editor pass. Gemini writes it, with Groq as the backup.
3. `render.py` draws 1080×1350 JPEGs. `mascot.py` picks a donkey pose for each slide's mood.
4. The images go up to `media.suresilly.com` (the `gh-pages` branch). Telegram gets the slides as an album, followed by a card.
5. You reply to the card with `approve`, `disapprove`, `redo all` or `redo images 2,4`. If you stay silent for 1 hour, it posts. Every reply case, including repeated or conflicting replies, is in `docs/telegram-approval.md`.
6. `review-window.yml` carries out your reply, and the Instagram link comes back in Telegram.

Mornings alternate between a **list** (7–9 slides) and a **story** (6–8 slides). Evenings are a **one-liner** (1 image).

## Loose rules

1. **Our own words only.** The writer never sees another page's posts and never quotes anyone.
2. **The donkey comes from `suresilly/assets/mascot/`.** No new art, and no text inside the art.
3. **Every Telegram message says three things:** what happened, what you can reply, and what happens if you stay quiet.
4. **Kill switch:** the repo variable `SS_HALT=1`, or a file at `state/HALT`.
5. **Keep it small.** If a problem looks like it needs a new gate, try a better prompt first.

## The Worker

A commit doesn't change anything live. Deploy with `cd ops/dispatch-worker && npx wrangler deploy`.

The Worker dispatches `auto-post.yml`, `review-window.yml` and `review.yml` by name, with fixed inputs. Keep those names and inputs.

## Layout

```
suresilly/          write · render · mascot · review · instagram · telegram · run · llm
suresilly/assets/   fonts (Fraunces, Inter; both OFL) and 75 donkey poses
posts/<slug>/       post.json · caption.txt · contact_sheet.png · review.json · published.json
                    (slides/ is gitignored; the review artifact and media host keep them)
state/reviews/      the Worker's record of each preview
scripts/insights.py reach, saves and shares after 3 days (insights.yml)
tests/              pytest
```
