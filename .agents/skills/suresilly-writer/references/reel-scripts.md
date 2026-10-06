# Reel scripts: how a model writes one, and how we know it was good enough

Code: `suresilly/script.py` (the spec, the prompt, the check), `suresilly/hooks.py` (hook techniques), `suresilly/lint.py` (two small lints), `suresilly/facts.json` (sourced facts). Tests: `tests/test_script.py`.

## The rule that shapes everything

**No post word is written by hand, and no prompt carries a sample.** A model shown a sample writes copies of it, and every post looks alike. The owner said this on 2026-10-06 and it is why there is no phrase bank, no scenario bank, no stock fallback and no worked example. A test fails if a prompt gains one.

What varies a post instead:

1. The **area** to look in for a topic (`script.AREAS`, picked by `pick_area`): a direction such as "a deadline phrase", never a topic.
2. The **hook technique** (`hooks.pick`): a card with the idea and the shape of line 1, never a line to copy.
3. A **voice** and a **reply shape** (`script.deal`): dry, warm, playful or matter-of-fact; the reply offers a time, asks a question, agrees to part, or says the task back.
4. The **recent-post guard** (`script.similar`): a script that repeats a line, or shares half its word pairs with a recent post, is rejected with the reason.
5. The **topic list**: the last 14 topics are given to the model as "do not repeat".

None of these is content. They are constraints, so a weak model cannot settle into one shape.

## The three Reels

| Template | The viewer sees | The model writes | Python writes |
|---|---|---|---|
| `rights` | HR says, the law says, a source card, a chat | cover, hr_says, law_says, reply_me, caption | the source card, from `facts.json` |
| `saythis` | a message arrives, a chat with the reply, why it works | cover, boss_text, reply_me, why, caption | the sender and time, from the idea |
| `dictionary` | the phrase, its meaning, a chat with the reply, why it works | cover, boss_text, reply_me, why, caption | the phrase and meaning, from the idea |

For `saythis` and `dictionary` the model also proposes the topic (`ideate`): six ideas for one area, and the code keeps those that pass `idea_problems` (right length, no law or money claim, not used lately, a meaning that starts with "=").

## The path of one script

1. Python picks the area, the hook, the voice and the shape.
2. `ideate` asks for six topics. Python keeps the good ones; `rank_ideas` lets a second model put the best first; the first one is taken. (`rights` takes the next fact from `facts.json` instead.)
3. **Step 1, the body.** The model writes only the exchange: what the sender says, the exact reply, why it works. No cover yet.
4. **Step 2, the dress.** The model reads the finished body and writes the cover and the caption for it. There is no teaser: a model cannot know the next post, so a teaser is a promise nobody keeps (the test showed lines like "Coffee break at 14"). Because it can see the body, the cover cannot promise what the body lacks.
5. After each step: `clean` (quotes, spaces, hyphens the font lacks, missing full stops), `check` (the rules below), then a second reader (`judge`) with questions for that step. Each problem goes back to the model in plain words, with the exact field, and the model writes that step again. Two repairs at most.
6. The renderer's own audit runs on the finished script (`extra_check`): does it fit on the screen.
7. If a script still fails a check, **nothing is posted**: the slot is skipped and the owner is told in plain words which check failed. If it fails only the second reader, the owner still gets it, with the reader's notes on the card, and decides.

Why two steps: in one step a weak model fixes one problem and creates another, round and round (measured: the same model failed 4 tries in a row on a single call, and passed in 1 to 2 tries per step when split).

## What `check` rejects

- A missing field, a wrong word count, too many characters for the screen, a chat too long for two bubbles (130 characters in all, measured with the layout audit).
- Banned words and phrases ("many think", "actually", "unlike", "follow", "donkey", and the rest of `BANNED`), emojis, hashtags, links, dashes.
- A number not in the FACT, written as a digit or as a word. Without a FACT: any law, tax or money word.
- An instruction without its exact words ("send a message"), through `lint.incomplete`.
- A cover with no gap, a cover that prints the answer, a cover whose line 2 is not a promise, a cover that promises "3 lines" over a one-line reply.
- A script too close to a recent post (`similar`).

## What the second reader asks

Body: does the reply answer the sender and could the reader send it; is every claim true to the FACT or the plain meaning; would a person in an Indian office write it; could it be sent tomorrow unchanged. Dress: is the cover about this exact topic and does the Reel deliver what it promises. The reader is told never to write a replacement line, because a sample in a repair prompt is a sample to copy.

## Qualifying a model

A model may write for the page only after it passes this run. Run it again when the model or the brief changes.

1. Make 12 posts in calendar order, four of each template, the way production does: each post is dealt its hook, voice and shape, may not resemble the posts before it, and takes its own topic.
2. Count: scripts that passed, scripts that passed on the first try, scripts that needed a repair, and scripts that never passed.
3. Read every finished script as a stranger would. Mechanical passes are not quality: see the next section.
4. Qualify the model only if the owner reads the finished scripts and finds most of them fit to send, and none that looks machine-made.

## What we measured (2026-10-06)

All numbers are from real calls to the free models, with a mix of 12 posts per model.

| Model | Passed `check` (one step, no second reader) | Fit to send, by my read |
|---|---|---|
| gpt-oss-120b | 12 of 12 | about 4 of 12 |
| qwen3.8-27b | 12 of 12 | about 7 of 11 read |
| gpt-oss-20b | 10 of 12 | weak: flat replies, teasers that are not teasers |
| allam-2-7b | 0 of 12 | none: writes marketing talk and invents fields |
| gemini 3.8 and 3.7 flash | every call returned HTTP 503 | not measured |

- **A pass is not quality.** The checks cannot see a reply that is a note to self, a cover about something else, a wrong meaning ("deep dive = look superficially"), or a made-up fact line. About two of every three scripts that passed would not have been sent by a person.
- **The second reader helps and costs.** Against my own read of 24 scripts, gpt-oss-120b as reader caught 11 of 12 bad scripts and wrongly flagged 5 of 12 good ones; qwen caught 12 of 12 but flagged 9 of 12 good ones; gpt-oss-20b caught 7 of 12. With the reader in the loop and the two-step writer, qwen passed 6 of 11 posts and gpt-oss-20b 6 of 8 (gpt-oss-120b could not run: its free rate limit was used up by being writer and reader at once). The passes were better than before; qwen's were mostly fit to send, gpt-oss-20b's still were not. A strict reader means more skipped slots.
- **No samples, still varied.** With no sample in any prompt, the pairwise word-pair overlap between a model's replies was 0.01 to 0.03, and every cover line 2 was different. With samples in the prompt the same models repeated the card's promise lines. The owner's rule (no hand-written content) was right.
- **Topics are the weak point.** Models invent plausible phrases and flat meanings, and a 7B model cannot do it at all. The topic reader (`rank_ideas`) helps; the area deal (`pick_area`) gives variety.

What this means for the pipeline: use the best available model as the writer and a different one as the reader; expect to skip or redo some slots; keep the owner's Telegram approval as the last gate. Do not expect a free model to match a hand-polished post every time.


## Cloudflare and Clef (tested 2026-10-06)

**Clef** (`@cf/cloudflare/clef`, 27B, and `clef-flash`, 9B) is a decision model, not a writer. It reads a state and typed questions (true or false, choice, score) and returns a probability for every answer in one pass. It cannot write a line. It can be the second reader and the topic ranker.

- It works on the Workers Free plan through `POST /accounts/{id}/ai/run/@cf/cloudflare/clef` with `{"state": ..., "questions": {...}}`. It answers `{"answers": {"reply_fits": {"type": "noul", "noul": 0.03}}}`. Price beyond the free allowance: $0.24 per million input tokens (24 scripts with 5 questions each cost about 19,000 tokens, under half a cent).
- Against my read of 24 scripts, flagging any question under 0.4 caught 9 of 12 bad scripts and wrongly flagged 3 of 12 good ones (0.5: 10 and 4). The LLM readers: gpt-oss-120b 11 and 5, qwen 12 and 9, gpt-oss-20b 7 and 6. So Clef is a better trade, one call, no shared rate limit, and the cut-off is a dial (`CLEF_BELOW` in `script.py`). The best single question was "natural" (0.88 area under the curve). Clef-flash was weaker (0.71 against 0.81 overall): do not use it.
- It gives no sentence on what to fix, only a number. The writer is told which question failed and the question's text. The LLM reader gives a sentence. Use Clef as the gate; use an LLM reader only when the writer needs more than the question.
- The test set is 24 scripts and my own labels. Treat the cut-off as a starting point and re-measure with the owner's approvals and rejections once there are some.

**Writers on Workers AI, free plan.** Available: gpt-oss-120b, gpt-oss-20b, qwen3.8-27b, llama-3.3-70b, gemma-4-26b, mistral-small-3.1-24b (and more). Not available on the free plan: kimi, glm, deepseek. Tested with Clef as reader (12 posts each):

| Model | Passed | Notes |
|---|---|---|
| gpt-oss-120b | 12 of 12 | every post needed 1 to 4 repairs; about 6 of 12 fit to send by my read |
| llama-3.3-70b | 6 of 12 | |
| qwen3.8-27b | 0 of 3 run | slow reasoning model, timed out and gave up under the free limit |
| gemma-4-26b | 0 of 6 | never produced a usable topic list |

So Cloudflare's gpt-oss-120b with Clef as reader is the best result so far (about 6 of 12 against about 4 of 12 for Groq's gpt-oss-120b alone). It is an improvement, not a fix. The remaining misses are the same kind: a made-up phrase ("ASAP, but not today"), a reply that does not answer the message, a flat meaning.

## Choosing models (survey of 2026-10-06)

Full survey and sources: `docs/free-model-survey-2026-10-06.md`; raw board lists: `docs/model-boards-2026-10-06.txt`.

- gpt-oss-120b is last or near last on every independent writing board and last as a judge. Do not keep it as the writer or the reader just because it is on every free tier.
- Prefer, in this order, as writers: Gemini 3.8 Flash (20 a day per project, measured), Qwen3.8-27B (Groq), then Kimi K3 or GLM-5.3 if the owner sets up an AIHubMix or NVIDIA account.
- Prefer as readers: Clef as the cheap first pass, then Gemini 3.7 Flash or Gemma 4 31B for nuance.
- The model list in `llm.py` should treat 429 and 503 as "try the next route", never retry the same one.


## The viewer test (2026-10-06)

The owner showed two Reels that passed every check and made no sense: a reply about hiding "my cat tabs" to a boss asking "Can you see my screen" (roles mixed up), and "I will get that to you by 9 pm" to a boss who asked for the draft by end of day (a later deadline, no reason). The reader now sees the Reel as a viewer does (`viewer_text`), writes one sentence on what happens, then answers new questions: `coherent` (does the reply answer the message, are the roles clear), `adds_value` (a move to copy, not agreement or a worse commitment), `consistent` (cover, meaning, reply and why agree).

Measured on 40 scripts I had labelled (18 bad): Gemini 3.5 Flash-Lite as reader caught 14 of 18 bad and wrongly flagged 6 of 22 good; it caught the screen case with the right reason and missed the end-of-day case. Qwen3.8-27B as reader caught only 5 of 18. Clef with the new text was not measured: Cloudflare's 10,000 free neurons a day were used up by our own tests (resets 05:30 IST). Use a reader from a different model than the writer.
