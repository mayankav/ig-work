# What we can use for free, and how much is left

Everything this engine runs on is free. This page says how much of each thing we
get, when it comes back, and what happens when it runs out.

To see the picture budget right now:

```bash
.agents/skills/suresilly-carousel/.venv/bin/python scripts/capacity.py
```

---

## The short version

| What | Who gives it | How much per day | When it resets | What we use it for |
|---|---|---|---|---|
| Pictures | Cloudflare Workers AI | 10,000 neurons | Midnight UTC | Mascot poses |
| Text | Google Gemini | Per model, per day | Midnight Pacific | Copy and the critic |
| Text | Groq | Per model, shared org-wide (1,000/day on the model we call) | Drips back, ~86.4s per request | Second opinion on copy |
| Text | Cloudflare Workers AI | Same 10,000 as above | Midnight UTC | Third opinion on copy |

**Important:** pictures and the Cloudflare text model come out of the **same**
10,000. If we spend it on pictures, the text model has less.

---

## Pictures

| Item | Number |
|---|---|
| Free per day | 10,000 neurons |
| We allow ourselves | 6,000 (60%) |
| Cost of one picture | 188 neurons |
| Pictures per day at our limit | 31 |
| Pictures for one 9-slide deck | 9 (1,692 neurons) |
| Full decks per day | 3 |
| Measured time per picture | 11 to 18 seconds |
| Measured time for 6 pictures | 84 seconds |

We keep 40% back on purpose. The text model draws on the same pot, and a day
that spends it all on pictures leaves the writer with nothing.

**We book the expensive price.** Cloudflare's own response says a picture costs
about 21 neurons. Their price list says 188. The two disagree by nine times and
we cannot tell which is right, so we count the big number. If we are wrong we
lose some speed. If we counted the small number and were wrong, we would go past
the free limit and start paying.

### When pictures run out

Nothing breaks. The slide uses a pose from the library instead. The library has
186 poses today and grows every time we generate a new one.

You will see this in the build log:

```
[7] fell back to thumbjack_back (BudgetExceeded)
```

---

## Text

Gemini gives a free allowance **per model, per day**. We use five model names,
so we get five separate allowances. Groq and Cloudflare are the second and third
opinions. The critic must never be the same vendor as the writer.

### Writing is never refused to protect pictures

The Cloudflare text model draws on the **same 10,000** as the pictures. We keep
**4,000 back for it** and never spend that on pictures.

Writing is recorded but never blocked. A deck that cannot be written is a day
with no post, so text always gets what it asks for. Pictures are the only thing
that gets turned away.

Every run reports it:

```
PICTURES   14 pictures left (3384/6000 used, resets in 9.1h)
WRITING    all vendors have room
```

The writing line stays one line until a vendor is actually near an edge, and
then it expands to a row per vendor, each in its OWN unit:

```
WRITING    ⚠ groq near the end of its share
  gemini     not counted         ?   no quota reported by the vendor
  groq       61/1000 requests    ▓░░░░░░░░░  full again in 13.3h
  cloudflare 570/4000 neurons    ▓░░░░░░░░░  of the writing share, resets 00:00 UTC
```

Nothing is converted into anything else. There is no exchange rate between a
neuron and a request, and inventing one would put a figure in the report that
no vendor could account for. Gemini gets words where the others get a bar,
because a bar there would be a guess with the shape of a measurement.

A row expands when a vendor drops below 20% of its own allowance, or when
Cloudflare's writing share passes 85%. Three vendor lines every morning is
three lines you learn to skip, and the morning they matter you skip them too.

**This was not measured until now.** The response header that says what a call
cost was being thrown away, so only pictures were counted and the 4,000 for
writing was an assumption nobody could check.

### Gemini and Groq

One of these reports what it has left. The other reports nothing. Until it was
checked, this page said neither did.

**Groq reports its own remaining, on every successful call.** Measured on
2026-08-31 against `openai/gpt-oss-120b`:

```
x-ratelimit-limit-requests: 1000        x-ratelimit-remaining-requests: 999
x-ratelimit-limit-tokens:   8000        x-ratelimit-remaining-tokens:   7922
x-ratelimit-reset-requests: 1m26.4s     x-ratelimit-reset-tokens:       585ms
```

That is better than what Cloudflare gives us. The Cloudflare header says what
one call cost and leaves the running total to us; Groq says what is LEFT, so
there is nothing to reconstruct and nothing to reconcile.

It is also not a daily reset. One request bought back 86.4 seconds of refill,
and 86.4 x 1000 is 86,400 — exactly a day. The allowance drips back
continuously rather than returning at a boundary, so there is no midnight to
wait for, and no moment when it is full again unless nothing has been spent.

Limits are per organisation, not per key. A second Groq key buys nothing.

`llm.py` reads it now. It used to capture response headers for the Cloudflare
call only and throw Groq's away, which is how this page came to say Groq could
not be counted: the number was arriving on every call and going in the bin.

It is recorded in a `finally`, so a refused call still leaves a true number
behind — a 429 is the one response that proves the allowance is gone, and
dropping its headers meant the report could only ever show a vendor with room
to spare. The reading lands in `state/vendor_quotas.json`, and the limit is
read from the header, never hardcoded.

**Gemini reports nothing.** A successful call carries no quota header at all —
checked, not assumed. It returns `usageMetadata` token counts, so tokens are
measurable, but requests-per-day can only be counted on this side, and the only
place the limit is ever named is the text of a 429.

Its allowance is per model, per project, and it returns at midnight Pacific —
07:00 UTC in summer, 08:00 in winter, never 00:00. A Gemini counter keyed on
the UTC date would zero itself the best part of a day early, every day, so the
reset boundary has to belong to the vendor and not to the ledger.

Neither has been the limit so far. That is a measurement, not a promise.

---

## What is NOT free

| Thing | Why we do not use it |
|---|---|
| Gemini image generation | The free limit is zero. Every call fails unless billing is on. |
| Groq image generation | There is no image model on Groq. Text and speech only. |
| FLUX 9B and FLUX dev | Better pictures, but the licence forbids commercial use. @suresilly is commercial, so every pose would be unusable. |

The 9B model sits one row below the one we use in Cloudflare's own price list.
That is the trap. Do not switch to it.

Re-checked 2026-08-31 against this project's own key, because 2026 write-ups
claim a free image tier of 500 requests a day. It is not true here:
`gemini-3.1-flash-lite-image` and `gemini-2.5-flash-image` both answered 429
with `generate_content_free_tier_requests, limit: 0`. Any future image vendor
has to take about four reference images — a text prompt alone draws a
different donkey every time — which is what rules out the free text-to-image
endpoints, not their price.

---

## Where the numbers live

| Number | File |
|---|---|
| What we spent today | `state/flux_neurons.json` |
| What a vendor said it had left | `state/vendor_quotas.json` |
| Free limit, our share, cost per picture | `.agents/skills/suresilly-carousel/scripts/poses_flux.py` |
| Which models we call | `.agents/skills/suresilly-carousel/scripts/llm.py` |

`capacity.py` reads the first two and does the arithmetic. It makes no network
call, so it costs nothing and cannot fail.

**Its one blind spot:** it counts what this repo spent through its own ledger. A
call made by hand, or anything else on the same Cloudflare account, is invisible
to it.
