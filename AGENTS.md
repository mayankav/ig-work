# @suresilly: easy-going tiny-truth posts

Silly, a small green mascot, warm paper, one line worth sending to someone. Written for readers in India, 18 to 30, in English with a little Hinglish. Two posts a day, and you approve each one on Telegram.

The old gated carousel engine is frozen on the `obsolete/carousel-engine-v1` branch. Don't bring its rules back. The reason for the change is in `docs/pivot/quote-pages-teardown.md`.

## Run it locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m playwright install chromium
brew install ffmpeg                                           # Reels; the workflows apt-get it
.venv/bin/python -m suresilly.run build --format list        # writes posts/<slug>/
.venv/bin/python -m pytest -q
(cd ops/dispatch-worker && npm test)
```

The writer reads `GEMINI_API_KEY` (or `GROQ_API_KEY`) from the environment or from `.env.local`.

## How a post happens

1. At 08:00 and 20:00 IST the Cloudflare Worker (`ops/dispatch-worker`) dispatches `auto-post.yml` with `mode=publish`.
2. `write.py` writes the post: a draft, then an editor pass. Gemini writes it, with Groq as the backup.
3. `render.py` draws 1080×1350 JPEGs. Only a carousel's cover (slide 1) has a donkey: big, with the pose chosen for the hook's expression. The evening Reel is an **A or B** quiz made by `abreel.py`: a phrase one kind of friend says, "which friend are you?" with a 3-2-1 count, a reveal where the donkey is A, and one line to send to the friend who says it. It is drawn on one spacing system inside Instagram's safe area, and its timing follows reading speed (`READ_WPS`). `sfx.py` picks its sounds for what is on screen: effects and a quiet background bed from Freesound (Creative Commons 0 only, fetched on the fly), with built-in sounds as the fallback (`synth.py`). The tune is ours (`music.py`). Setup is in `docs/freesound.md`.
4. The images go up to `media.suresilly.com` (the `gh-pages` branch). Telegram gets the whole Reel as a video with sound (or the slides as an album), followed by a card. A Reel is never approved unseen and unheard.
5. You reply to the card with `approve`, `disapprove`, `redo all` or `redo images 1`. If you stay silent for 1 hour, it posts. Every reply case, including repeated or conflicting replies, is in `docs/telegram-approval.md`.
6. `review-window.yml` carries out your reply, and the Instagram link comes back in Telegram. A one-liner then goes to Threads too (`threads.py`; setup in `docs/threads.md`). A Threads failure never touches the Instagram post. The 08:00 and 20:00 runs renew the Instagram and Threads tokens weekly (`tokens.py`; needs the `SECRETS_PAT` secret).

Mornings alternate between a **list** (7–9 slides) and a **story** (6–8 slides). Evenings are an **A or B** Reel. The older two-beat one-liner (`--format oneliner`) is kept for manual runs.

## Loose rules

1. **Our own words only.** The writer never sees another page's posts and never quotes anyone.
2. **Silly comes from `suresilly/assets/mascot/`.** Never call Silly a donkey in anything the audience or the owner reads. No new art, and no text inside the art. It shows on a carousel's cover only, and on three screens of the A or B Reel.
3. **Every Telegram message says three things:** what happened, what you can reply, and what happens if you stay quiet. Errors are in plain words (`telegram.PLAIN`); the raw error goes underneath, folded, as "Details for Claude". Every workflow and the Worker message the owner when something fails or gets stuck. Posted! and failure messages end with what is left of today's free writing AI (`state/usage.json`).
4. **Kill switch:** the repo variable `SS_HALT=1`, or a file at `state/HALT`.
5. **Keep it small.** If a problem looks like it needs a new gate, try a better prompt first.

## The Worker

A commit doesn't change anything live. Deploy with `cd ops/dispatch-worker && npx wrangler deploy`.

The Worker dispatches `auto-post.yml`, `review-window.yml` and `review.yml` by name, with fixed inputs. Keep those names and inputs.

## Layout

```
suresilly/          write · render · abreel · sfx · synth · mascot · reel · music · review · instagram · threads · telegram · run · llm
suresilly/assets/   fonts (Fraunces, Inter; both OFL) and 75 poses of Silly
posts/<slug>/       post.json · caption.txt · contact_sheet.png · review.json · published.json
                    (slides/ and reel.mp4 are gitignored; the review artifact and media host keep them)
state/reviews/      the Worker's record of each preview
state/usage.json    writer calls counted today, for the ⛽ line on Telegram
scripts/insights.py reach, saves and shares after 3 days (insights.yml)
tests/              pytest
```
