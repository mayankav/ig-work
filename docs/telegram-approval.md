# Approving posts on Telegram

## The short version

1. At 08:00 and 20:00 IST the bot sends the slides as an album, then a **card**.
2. **Swipe left on the card** and reply with one word from the table below. You can also send the word plus the card's Review ID as a normal message.
3. **If you don't reply for 1 hour, the post goes out by itself.** A preview made with `force` waits for you instead.

## Replies to a preview card

| Reply | What it does |
|---|---|
| `approve` | Posts it now. The Instagram link comes back in Telegram. |
| `disapprove` | Cancels it. `cancel` and `reject` work too. |
| `redo all` | Writes a completely new post. A new card arrives in about 3 minutes. |
| `redo images 2,4` | Draws a new donkey on those slides and keeps the words. Use numbers 1–9, separated by commas. A new card arrives. |

## Replies sent as a plain message

Send these as a normal message, not as a reply to a card. As a reply to a card, the bot only answers "No change made".

| Reply | What it does |
|---|---|
| `retry` | Makes a fresh post and preview now. |
| `list` | Shows the previews still waiting, with the exact reply for each. |

## How you reply

| You send | How | What happens |
|---|---|---|
| `approve` | Swipe-reply to the **card** | ✅ Posts |
| `approve 1a2b3c4d5e6f7a8b` | Plain message, no swipe needed | ✅ Posts. The 16-character ID is at the bottom of the card |
| `approve` | Plain message, no ID | 🤔 The bot says "No change made". Nothing posts |
| `approve` | Swipe-reply to a **photo** in the album | 🤔 "No change made". Only the card carries the ID |
| `Approve` or ` approve ` | Reply to the card | ✅ Works. Capitals and spaces don't matter |
| `approved`, `approve!`, `approve ✅` | Reply to the card | 🤔 "No change made". It has to be the exact word |
| `ok`, `yes`, `approved` | Plain message | 🔇 Ignored, with no answer at all |

The words are strict on purpose, so that ordinary chat can never post something by accident.

## Replying more than once to the same preview

| First reply | Then you send | Result |
|---|---|---|
| `approve` | `approve` again, within ~1–2 min | ✅ Still only 1 post. The newest reply wins |
| `approve` | Anything, after posting has started | ⚠️ "No change made". It posts once |
| `approve` | `disapprove`, within ~1–2 min | 🗑 Cancelled. Nothing posts |
| `disapprove` | Anything | ⚠️ "No change made". Cancelling is final |
| `redo all` / `redo images 2,4` | Anything on the **old** card | ⚠️ "No change made". Reply to the new card instead |
| No reply for 1 hour | `disapprove`, within ~1–2 min of the hour ending | 🗑 Cancelled. Any later reply is too late, and it posts |
| Telegram delivers the same reply twice | — | 👍 "Already got that reply". It counts once |

The ~1–2 minutes is the time between your reply and the GitHub job starting to post. Once it starts, only the first reply counts. Instagram never gets the same post twice.

## Where this lives in the code

| Piece | File |
|---|---|
| Reading your reply | `ops/dispatch-worker/src/review-window.js` (`parseWindowReply`) and `src/index.js` |
| Remembering the decision and the 1-hour timer | the `ReviewWindow` Durable Object in `src/review-window.js` |
| Acting on it (post, cancel, redo) | `.github/workflows/review-window.yml` → `python -m suresilly.run act` |
| The card's wording | `suresilly/telegram.py` |

Changing the Worker needs `npx wrangler deploy` in `ops/dispatch-worker`. A commit alone changes nothing live.
