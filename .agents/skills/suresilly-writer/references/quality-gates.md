# Quality gates: what must be true before a post reaches Telegram

Written 2026-10-06 from the owner's reviews of the first-job samples. Each gate has a cause: something that went wrong in a sample.

## 1. Accurate
- A fact is stated only if it comes from the fact bank (`memory/india-first-job-facts-2026-10-05.md`, to become `suresilly/facts.md`) or from a dated source packet. The model never states a fact from its own memory.
- Every factual slide or scene shows its source and date. Unconfirmed items say "Reported".
- Why: on 2026-10-05 the free model, given 12 checked facts, wrote 8 ideas and at least 6 added claims (48 hours for "two working days", a pension benefit, salary mixed up with CTC, "unlike many states"). A same-model verifier caught only 3 of 6. So: a different-model check, Python copies numbers and units from the source, banned phrases ("many think", "unlike"), and the owner approves with a claim-to-quote table.

## 2. Complete
- Every instruction carries its exact words in the same slide or scene. "Ask for the notice period in writing" is not finished. The finished version is the sentence: "Can I shorten it if I pay for the extra days?"
- The failure that taught this: a Reel ended on "Set a reminder for 3 days. Send one line." Which line, to whom, saying what? The owner: "we can't generate incomplete information."
- Lint (`copy_lint.py` in the prototype): a scene or slide tagged YOUR MOVE, CHECK THIS, ASK THIS, SAY THIS, SEND THIS or SO may not contain an imperative sentence of 9 words or fewer without a quotation or a colon, and may not contain "one line", "a line", "a message", "something", "stuff", "etc".
- Jargon is explained where it first appears ("buyout" becomes "pay to shorten the notice").
- The lint cannot judge meaning. The second check (a different model, one question): "Could a stranger do what this says using only this scene?"

## 3. The cover is a hook
- A cover raises a question or a conflict and withholds the payoff. The payoff (the number, the answer, the script) appears inside, by slide 2 or scene 2.
- Approved: "'We are like a family' is not in your offer letter. / Here is what is." and "Your PF may not be reaching you. Check in 60 seconds. / Here is how."
- Rejected, because the cover contained its own answer: "Resigned? Your wages are due in 2 working days." and "'Let's circle back.' = no." and the 10 pm cover that printed the reply itself.
- Test: can a stranger answer the cover's question without opening the post? If yes, rewrite.
- Lint (`cover_lint.py`): the post names its payoffs; none may appear in the cover text; the cover must contain a gap marker (a question, a blank or "= ?", "typing...", "Here is ...", "We checked.").
- A Reel has two hooks: the cover image (9:16, content inside the central 3:4, sent as `cover_url`) and the first 1.5 seconds (a claim or conflict plus a sound hit). The hook techniques are in `hook-playbook.md`.

## 4. Laid out like a designer would
- One set of tokens for every Reel scene: left edge 100, right edge 940 (the app's buttons sit to the right), tag row at y 250, safe bottom 1490, gaps 32/48/64/96, minimum gap 32, type scale 240/200/168/140/120/100/84, corner radius 40, source text at least 32 px.
- Line breaks are optimal, so no stub lines (a lone "days." or "wage").
- `audit_reel` measures every scene's finished state (overlaps, gaps under 32, outside the safe area). `dom_audit` measures carousel slides in the browser (margins 80, gap 24). Zero findings is the bar. The audit cannot judge taste: look at the frames too.
- Silly is a still sticker that appears. He never moves.

## 5. Varied
- A calendar picks the pillar; the pillar picks the template, colour, voice and hook technique; the model fills words. Never the same pillar or colour twice in a row. Every post has one specific (a number, a date, a named form, a source). A similarity check compares each post with the last 14.

## 6. Sounds right
- Tune "min" (bass plus a marimba note on every word that appears), quirky effects on every cut, no club beat, no room tone. Loudness -15 LUFS, peak under -2 dBFS. The owner listens: an agent cannot.
