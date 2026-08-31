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
| Text | Groq | Per day | Rolling | Second opinion on copy |
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

A full day of posting costs a few thousand tokens. Text has never been the
limit. Pictures are.

---

## What is NOT free

| Thing | Why we do not use it |
|---|---|
| Gemini image generation | The free limit is zero. Every call fails unless billing is on. |
| FLUX 9B and FLUX dev | Better pictures, but the licence forbids commercial use. @suresilly is commercial, so every pose would be unusable. |

The 9B model sits one row below the one we use in Cloudflare's own price list.
That is the trap. Do not switch to it.

---

## Where the numbers live

| Number | File |
|---|---|
| What we spent today | `state/flux_neurons.json` |
| Free limit, our share, cost per picture | `.agents/skills/suresilly-carousel/scripts/poses_flux.py` |
| Which models we call | `.agents/skills/suresilly-carousel/scripts/llm.py` |

`capacity.py` reads the first two and does the arithmetic. It makes no network
call, so it costs nothing and cannot fail.

**Its one blind spot:** it counts what this repo spent through its own ledger. A
call made by hand, or anything else on the same Cloudflare account, is invisible
to it.
