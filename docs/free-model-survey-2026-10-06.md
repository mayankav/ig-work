# Free model survey, 2026-10-06

Four research agents read official pages, raw leaderboard files and provider model lists on 2026-10-06. Two things were measured by us with our own keys (marked **MEASURED**). Everything else is from a page, with its confidence. The raw top-25 lists from each board are in `docs/model-boards-2026-10-06.txt`.

Re-check any limit before relying on it: free tiers changed in the last six weeks (see "Gone or restricted").

## The headline

**Our writer, gpt-oss-120b, is last or near last on every independent writing board, and last as a judge.** That matches our own test (about 4 of 12 scripts fit to send). Better free models exist.

| Board (snapshot) | gpt-oss-120b | Best free-route model |
|---|---|---|
| EQ-Bench Creative Writing v3 (2026-09-24, 140 models) | 961, rank 118 | Kimi K3 2082 (#5), GLM-5.3 2075 (#6), Gemini 3.8 Flash 1748, Nemotron 3 Ultra 1692, Qwen3.8-27B 1671 |
| Arena creative writing (2026-10-02) | rank 264 (1278) | Gemini 3.7 Flash #5, Gemini 3.8 Flash #7 (1485) |
| Arena instruction following | rank 230 (1323) | Kimi K3 #14, Gemini 3.8 Flash #15, DeepSeek V4.1 Flash #21 |
| Lech Mazur story benchmark (2026-09-26, 56 models) | rank 53 | GLM-5.3 #6, Kimi K3 #9, MiMo V2.6 Pro #16, Gemini 3.8 Flash #26, Qwen3.8-27B #34 |
| EQ-Bench Judgemark v4 (judging, 42 judges) | 0.155, last | Gemini 3.7 Flash 0.834, GLM-5.3 0.726, Gemma 4 31B 0.723, Qwen3.8-27B 0.674 |

No board tests 60-word fields, strict JSON or Hinglish. Treat all of this as indirect evidence and test on our own prompts.

## Writers, ranked by evidence, with the free route

1. **Gemini 3.8 Flash**, Google free key. **MEASURED today:** the free quota is 20 requests a day per project per model (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quotaValue 20). Each model has its own pool: 3.7, 3.6 and 3.5 Flash and Flash-Lite are separate. Slop score 22.6 (higher is worse). Free-tier content is used to improve Google's products, with human review: we send no personal data. 503 errors may burn quota (forum reports, unconfirmed by Google).
2. **Qwen3.8-27B**, Groq free (30 requests a minute, 1,000 a day, 8K tokens a minute, 200K tokens a day) or Cloudflare (about 24 to 55 calls a day). Slop score 12.1, the lowest of the free ones. Our own best Groq writer.
3. **Kimi K3 and GLM-5.3**, the strongest open models on the writing boards (slop 9.7 and 8.4). Free routes seen, none verified by us:
   - AIHubMix (third-party relay): `coding-kimi-k3-free`, `coding-glm-5.3-free`, `xiaomi-mimo-v2.6-pro-free`. 5 requests a minute, 100 a day, 1M tokens a day. Email or OAuth sign-up, no card. The `coding-` prefix may limit use to coding tools (unconfirmed). It can vanish.
   - NVIDIA build: lists kimi-k3, glm-5.3, glm-5.3-flash, deepseek-v4.1-flash. About 40 requests a minute (forum). Phone verification; Indian numbers reported "exceeded limits" on 2026-03-18 and 2026-07-26. Free trial inputs and outputs are used to improve NVIDIA models.
   - Tencent TokenHub: 1M tokens per model for 90 days until 2026-12-31 (DeepSeek, GLM-5.2, Kimi-K2.6, MiniMax-M3; not K3 or GLM-5.3). Reportedly needs $1 frozen per model.
4. **Alibaba Model Studio, Singapore:** 1M free tokens per model for 90 days, including Qwen3.8-Max (index 45.4) and DeepSeek V4.1 Flash and V4 Pro. Needs account details and payment verification. One user report says India cannot be selected as the country (unconfirmed).
5. **MiMo V2.6 Pro (Xiaomi)**: top open model on the Artificial Analysis index (46). Free only through AIHubMix (see above).
6. **Nemotron 3 Ultra**, OpenRouter `:free`: 50 requests a day without credits. Slop 18.4. Free models there vanish within days and several free hosts train on prompts.

Official free APIs from Chinese labs are weak: Z.ai gives GLM-4.7-Flash (EQ-Bench rank 110) and nothing better. Moonshot's free voucher needs a mainland China number. DeepSeek, MiniMax and StepFun have no free tier.

### AIHubMix, measured with the owner's key (2026-10-06)

The model pages say "free API access for evaluation, no credit card required" and "5 requests per minute, 100 requests per day, 1 million tokens per day". **The live API says otherwise.** After about ten calls every free model, including the free decision model, answered with this text instead of a result: "accounts that have not been recharged can only try 10 times. You can increase the free quota after recharging" (console.aihubmix.com/topup). So an account that has not been topped up gets about 10 tries in total, which is useless for a pipeline.

What the first calls showed, before the cap:
- `coding-kimi-k3-free`: HTTP 400 `no_available_channel` (not served).
- `coding-glm-5.3-free`: HTTP 500, upstream "Unauthorized". `coding-glm-5.2-free`: 404, now paid.
- `xiaomi-mimo-v2.6-pro-free` and `-flash-free`: HTTP 429 "rate limited by provider" on the first try; later only the cap message.
- `hy3-free`, `qwen3.6-plus-preview-free`, `union-alpha-free`: `no_available_channel`.
- Worked: `nemotron-3-ultra-550b-a55b-free` (clean JSON, 6 s), `coding-minimax-m3-free` (answer inside a `<think>` block), `glm-4.7-flash-free` (JSON in a code fence).
- Decision Model Preview (Alibaba, $0, 64K, called through `/v1/systemone`) is behind the same cap.

Unlocking needs a top-up (the owner's money, not ours). Paid prices there are small: GLM-5.3-Flash $0.15 in and $0.50 out per million tokens, DeepSeek V4.1 Flash $0.15 to $0.30 in and $0.60 to $1.20 out, Kimi K3 $3 in and $15 out (official platform prices; AIHubMix may differ). At two posts a day, about 25,000 tokens a post, that is under a cent a day for GLM-5.3-Flash and about 30 cents a day for Kimi K3.

### One creator's review of MiMo V2.6 (pasted by the owner, a summary of a YouTube video, 2026-10-06)

Tested Pro (over 1T parameters) and Flash (about 300B) on website generation, C++, 3D and games. Verdict: "consistently inconsistent". Both showed promise but looped on tool calls. The creator preferred **Flash** (it copied a long design file for a racing game better than other open models) and called Pro "a work in progress", with bugs and looping. This is second-hand, coding and agent work only, one tester: it says nothing about short Hinglish copy. It matches the boards: Pro leads on reasoning indices but is middling on creative writing (Arena creative #47), and Flash is the better value. If AIHubMix is topped up, test Flash first (its page shows $0.08 in and $0.16 out per million tokens), then Pro. Both have 10 s first-token delay and about 34 tokens a second per the AIHubMix pages, which is fine for two posts a day.

## Judges

Judgemark scores creative samples from 0 to 10, so it only hints at true or false skill.

1. **Gemini 3.7 Flash** (0.834, Google free, its own 20 a day pool).
2. **Gemma 4 31B** (0.723). **MEASURED:** free on the Gemini API (answered 200 today; the 31B took 30 s once, the 26B 2 s). 30 requests a minute in its own pool (a GitHub PR, unconfirmed). JSON pass rate is the lowest of the top (94.3%), so keep a retry.
3. **Qwen3.8-27B** on Groq (0.674). Same base as Clef, so errors can be correlated.
4. **Clef**, first pass (our test: caught 9 of 12 bad scripts at 0.4). No independent board entry; its published scores are Cloudflare's own. One outside test of Clef-flash agreed 83% with a paid decision API on 42 cases. A paper (JevOut, arXiv 2609.30243) found short added context flipped 61% of decisions in decision models: do not trust the probabilities alone.

Do not use gpt-oss-120b as a judge.

## Measured by us today (Gemini key)

- gemini-3.8-flash and 3.7-flash: HTTP 429, free quota used up by our tests (3.8: 20 a day).
- gemini-3.5-flash, gemini-3.5-flash-lite, gemma-4-31b-it, gemma-4-26b-a4b-it: HTTP 200.
- gemini-3.6-flash and 3.1-flash-lite: HTTP 503 ("high demand").
- gemini-3.1-pro-preview: HTTP 429 with no free quota: not free.

## Gone or restricted since September

- Gemini 2.5 models: past users only (changelog 2026-09-18).
- Groq: Llama 3.3 70B and 3.1 8B (2026-08-16), qwen3.6-27b (2026-09-14).
- Cerebras: permanent free tier replaced by a $5, 30-day trial needing a card.
- Hyperbolic serverless: gone. GitHub Models: retired 2026-07-30. Vercel: a card is now required.
- OpenRouter free removals: MiniMax M2.7 and M3, DeepSeek V4 Flash (free for three days), GLM 5.2 and 5.3 Flash (404 now), others.
- Sarvam: free credit cut from ₹1,000 to ₹100 (date unconfirmed).

## Traps

- **LLM7.io** lists Claude Opus 5.5, GPT-6 and Kimi K3 as free. **MEASURED:** an anonymous call returned 401 "invalid API key" for every model tried. Free access to the most expensive closed models is a sign of a reseller. Do not use.
- **KiosAPI, WusRouter:** resold accounts. Avoid. **B.AI:** needs a crypto wallet.
- **Free Harvard-hosted and Token Harbor gateways** log prompts. **AI Horde:** workers can read prompts. **Puter.js:** browser only.
- Stale guides still advertise Cerebras at 1M tokens a day and Groq Llama.
- India: no provider's page confirmed or blocked India. Test a real call from India before relying on any route.

## What to test next

On the same 12-post harness, with Clef as a first-pass reader and a second model as the reader for nuance:

1. Gemini 3.8 Flash (after the quota resets), as writer.
2. Qwen3.8-27B on Groq, as writer.
3. Gemma 4 31B, as reader and as backup writer.
4. If the owner makes an account, Kimi K3 and GLM-5.3 through AIHubMix or NVIDIA build, as writers.
5. Score Clef, Gemini 3.7 Flash, Gemma 4 31B and Qwen3.8-27B as judges against 50 scripts the owner has labelled true or false; pick the judge by agreement with the owner, not by Judgemark.

## Free runs, 2026-10-06 (two-step writer, Clef as first reader, no samples, nine posts each)

| Writer | Passed checks and Clef | Calls per passed post | Fit to send, my read | Notes |
|---|---|---|---|---|
| Gemini 3.5 Flash-Lite (Google free) | 8 of 9 | 3.0 | about 6 of 8 | Funniest meanings and the most natural replies ("= Your evening is officially cancelled now."). One post had no usable topic. Free quota reported as 500 a day (not measured). |
| Qwen3.8 27B (Groq free) | 8 of 9 | 3.5 | about 5 of 9 | Sound and plain; replies a little stiff; one cover contradicted its own body. |
| Gemma 4 31B (Google free) | 1 of 2 so far | 7 | not judged | 440 s for one post and HTTP 500 errors: too slow and flaky as a writer. |
| Gemini 3.8 Flash | waiting for quota | | | A background job probes every 10 minutes and runs three posts when its free 20 a day returns. |

Compare with the earlier gpt-oss-120b runs (about 4 of 12 fit to send; 8 of 12 on Cloudflare with Clef about 6 of 12). The two-step writer with Clef as reader cut the calls per post from about 7 to about 3. At two posts a day that is 6 to 7 calls a day, far inside every free limit.

What both still do badly: a cover that repeats the sender's line instead of raising a question, a reply that agrees to the vague ask without pinning anything down, and captions that sound like a poster ("Protect your weekend"). Those need the second reader with a sentence of feedback, or the owner's rejection notes.
