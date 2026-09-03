# @suresilly — Instagram carousel engine

Writes and renders 9-slide carousels, 1080×1350, with a donkey mascot. Posts twice a day on its own.

**Read `.agents/skills/suresilly-carousel/SKILL.md` before any carousel work.**

## Run

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/run.py --no-post
```

`--publish` posts · `--no-post` builds and still uses the idea up · `--dry-run` writes nothing · `--no-fresh` skips drawing new art.
Kill switch: `SS_HALT=1` or a file at `state/HALT`.

## Layout

```
.agents/skills/suresilly-carousel/   the engine
  SKILL.md          entry point
  references/       voice · voice-target ⚠ never prompted · playbook · design system
  mascot/           poses + CHARACTER.md
  scripts/          run.py · compose · safety · writer · critic · render · build
                    readability · bibliography · discovery · coherence · memory
                    outcomes (green/amber/red) · probe_vision ⚠ offline only
  tests/            28 suites, CI runs every one
scripts/            NOT the engine's. Jobs around it, never imported by it:
                    post_to_ig · prune_slides · insights · notify · capacity · dashboard
.github/workflows/  auto-post (08:00, 20:00 IST) · insights · review
                    (Telegram replies push to the Cloudflare Worker, which
                    dispatches review — no polling workflow anymore)
ops/dispatch-worker/  the Cloudflare Worker: the clock, and the Telegram webhook.
                    Deploying it is `wrangler deploy` — a commit alone changes
                    nothing. `test/parse-reply.test.mjs` runs in CI under node.
carousels/          carousel.md + contact_sheet.png per deck
state/              what has been used. Committed.
research/           ⚠ 02_account_database and 05_hooks_database hold invented numbers
```

**Two directories are called `scripts/`.** Check which you are in before deciding a file is missing.

## Invariants

Every one of these is here because it already broke in production. Do not relax one to make a build pass. The reason behind each is in `git log`.

| # | Rule |
|---|---|
| 1 | **No SVG for artwork.** Mascot is raster PNG. Textures are CSS or local raster. |
| 2 | **Poses: draw fresh, fall back to the library.** `run.py` generates one per slide; any failure silently uses the library instead. `--no-fresh` opts out. `poses_flux.py` and `--generate` are offline-only and uncallable from `build.py`. Never use the flux **9B** model — non-commercial licence. |
| 3 | **No text inside mascot artwork.** Not a letter. Three gates live in `cutout.py`, the module both paths import: `assert_no_text`, `assert_on_palette` (`#3C965A`), `assert_has_pupils`. Gates belong in the shared module, not whichever one needed it first. |
| 4 | **Gates abort, never warn.** If a gate fails, nothing is written. Reword the brief instead. |
| 5 | **No MCP dependency.** Plain Python CLIs only. |
| 6 | **No live code in a file marked obsolete.** Nothing load-bearing in `scripts/mascot.py`. |
| 7 | **Fonts verified at render time.** A face that did not load aborts the render. |
| 8 | **Judge the contact sheet, not the slide.** Nine tiles must read as one body of work. |
| 9 | **A harvested post is a seed, never a source.** No run of 7 words survives into what we publish. Reading a name is fine; writing one is not. |
| 10 | **Old decks are a blocklist, never a source.** Never shown to a model, not even as an example. Novelty is enforced against fingerprints. |
| 11 | **The rules decide, the model writes.** A model may write and may veto. **It may never approve**, pick its own angle, or name an unproved source. |
| 12 | **A citation is proved before it is printed.** Six gates in `bibliography.py`, all fail closed. Shelf whitelist: LC `BF RC RJ HQ HM QP`, Dewey 150–158. A claim must also be sayable — `readability.jargon_words` refuses paper words before the claim is written, not after. Open Library is told who is calling and deliberately not given an email. |
| 13 | **Two channels, one funnel.** Feed or concept, both produce one invented moment with a subject from the closed list. A phrase enters `QUERIES` only after `probe_phrases.py` measures it. |
| 14 | **No condition is ever hardwired.** No OCD topic, no ADHD topic — only a route by which such a term arrives on its own and is ranked. `clinical` is off at the concept layer, replaced by `SEVERE`, `LIFE_EVENT`, `IDENTITY_SPECIFIC`, `NOT_OUR_READER`. |
| 15 | **`discovery.py` never names a book.** It proves a term is real and stops. `bibliography.py` owns citations. A concept's Wikipedia summary is read, never printed. |
| 16 | **One entry point, one state.** Any run that makes a deck uses up its moment. State lives in `state/` and is committed. **`flux_neurons.json` and `vendor_quotas.json` are opposites and must never be merged** — a ledger only rises, a quota snapshot is always replaced. |
| 17 | **What we publish is measured; the measurement never decides.** `insights.py` may import nothing from the pipeline and nothing may import it. A missing metric is recorded as missing, never as zero. |
| 18 | **The host is not the archive.** Host keeps 14 days (`prune_slides.py`, after the post, never before). Repo keeps `carousel.md` and `contact_sheet.png`. `slides/*.png` and `carousels/*/mascot/` are gitignored. Pending decks are protected by name. **Keep `keep_files: true`** — the pruner owns deletion. |
| 19 | **A new seed does not make a new moment.** Four checks in `compose.py`: same words, same opening verb, same room, and copying the worked example. Examples rotate and the answer is measured against the one shown. |
| 20 | **An example in a prompt is a template, and an on-subject example is copy.** Measured: five of seven published decks carried a run of words lifted from the prompt, including a sentence the prompt quotes in order to forbid it. Every example that was set on the page's own ground got copied within a week; the off-subject ones never were. So **every example in `PLAN_SYSTEM` and `DRAFT_SYSTEM` is about dentists, parking tickets, library books and bicycles**, and `writer.check_leak` fails any draft sharing four consecutive words with the prompt. `references/voice-target.md` is the deck the engine is aiming at and **must never be loaded into a prompt** — it is on-subject, so it would be a template. |
| 21 | **Simple words, sharp idea.** Never simplify the thinking; always simplify the words. `readability.py` refuses any four-syllable word a reader can see, on a hook, a handle or a slide — all seven decks published before this fail it, one to five lines each, and every offending word had a plain replacement. **Three-syllable words are counted and never faulted**: rationing them added twenty to thirty-two faults across the same seven decks and every one asked for the thinking to be simplified. A fault always names the word, because a gate that says "too hard to read" gets a rewrite that is differently hard. `[[accents]]` are ours and counted; a `[blank]` is the reader's and a `#tag` is a routing label, so neither is. Counting tags asked four decks to find a shorter word for `#anxiousattachment`, and **a fault nothing can answer is a stopped engine, not a strict gate**. That test applies to the gate's own arithmetic: `-ed` is a beat only after `t` or `d`, so `unfinished` is three beats and the heuristic said four. Run `local-1788240340` was told seven times to shorten it — faults `5, 3, 2, 2, 2, 2, 2` — while it also had to keep the pattern name on the same line, so every rewrite that chased the phantom dropped the name. `remembered`, `considered` and `unnoticed` sat over the cap for the same missing rule. Measured across the seven published decks, the fix frees exactly one word — `overwhelmed` — and still refuses all seventeen paper words. **A heuristic that only ever subtracts is as wrong as one that never does**, so `test_readability.py` pins both halves: `unfinished` at three and `wanted` at two. |
| 22 | **Variation is drawn by code, not asked for in a prompt.** The way to get thirteen shapes without handing the model thirteen samples is to hand it a **job** and let `draw_axes` pick which: 34,944 starting positions, and **not one axis value contains a line of copy** — `test_readability.py` fails the build if one ever does. Every axis hashes its own name, so inserting a seventh never replans a moment that already exists, and the formula axis additionally refuses to repeat inside eight decks. That window is reconstructed by replaying the draw over `memory.used_texts()` — **no new state field**, because invariant 16 already says where state lives. |
| 23 | **The h2 absolves or promises, and it is not the h1 again.** Those are the only two jobs; the drawn formula says which. Measured on the reference account: 18 of 42 covers run a how-to or list shape and **none of them run it in the headline** — the h1 is a flat human claim and the shape sits in the subtitle. So `How to` is banned in an h1 opener and allowed in an h2. A subtitle must bring **two content words** the headline did not have, function words excluded: across the seven published decks the one that posted the same sentence twice scores zero and every other scores three or four. |
| 24 | **A gate measures content, never grammar, and never contradicts its own prompt.** The intention check searched for the literal words `at` and `in` while the prompt asked for "a real time **or** a real place" — so a model that obeyed the instruction was faulted for it, with a message naming nothing. Run `local-1788236906` spent four attempts there, faults `2, 1, 1, 1`, and posted nothing. Measured on the eight intentions this engine has published: **one passed**, and it was the filled-in-template shape the prompt forbids, while `at 6am by the [[bed]]` was refused for missing an `in`. Prepositions are not places. `coherence.when_in` and `coherence.place_in` replace it and take 6 of 8, refusing only the two that name neither. |
| 25 | **A rule enforced only by a test fires one commit too late.** `PAPER_WORDS` lived in `test_writer.py`, so on 2026-09-01 a run verified van der Kolk, wrote a claim using `appease`, saved it, and turned the suite red on data no gate had refused. The list is `readability.JARGON` now — syllables cannot catch it, since `schema` is two beats — `bibliography` asks before it writes, and the test imports the same tuple. **A test may confirm a gate; it may not be the gate.** |
| 26 | **A guard for the case where another guard was wrong cannot read the same signal.** `check_state_is_current` asks git whether `state/` is dirty or behind. On 2026-09-01 it answered `current` about a stale copy, so `pick_moment` filtered against a ledger missing a line and run `local-1788242062` re-claimed `m-572b219023b990a8` — already live as media `17972776875125960`, posted `08:02:38Z`. The slug comes from the moment (`moment_id` hashes the source post, not the composed text), so the second deck was written straight onto the `carousel.md` and `contact_sheet.png` of a real post. Invariant 18 makes those two files the only surviving record of it; it survived because an unrelated merge happened to prefer the remote side. **Luck is not a guard.** Two locks now, and neither asks git: `memory.claim` refuses any id in `used.jsonl` — that check was already promised in its own docstring while `is_used` sat with zero callers, which is invariant 25 again — and `write_deck` refuses a folder holding `published.json`, failing closed even when that file is corrupt, because the guard's reliability must not depend on the shape of a file another script writes. An already-used moment exits **0**, like the halt switch: declining to duplicate a live post is not a failure. A folder with no marker is still rebuildable, or every held deck would be unrepeatable. |
| 27 | **A gate refusing is the engine working, and it exits 0.** Three endings, not two: **green** a deck went out, **amber** nothing shipped and nothing broke, **red** something is broken. A gate that refused every draft and a vendor nobody could reach were both `llm.ModelRefused` and both exited 1, so run `33583495343` sat red in the actions list while its own Telegram message read "a gate refusing, which is the system working". **A red that fires for the ordinary case is a red that stops being read**, which is the state a real outage slips through. `outcomes.Refused` is amber and `outcomes.Stop` stays red; they live in `outcomes.py` because `writer.py` raises the first and cannot import `run.py`, which is invariant 3 again. The two are told apart by type alone while travelling the same path out of the writer loop, so **neither may ever subclass the other** — `test_outcomes.py` pins that, both raise sites, and all five exit codes. In CI only an explicit `success` claims amber: a suite failing above skips the build, and `skipped` is red, because a build that never ran is not a gate saying no. `retry` is the Telegram verb that starts a fresh run — **never `rerun`, which has always meant drop** — and it is offered only when trying again could work (`retry=False` on an empty concept pool). |
| 28 | **A gate must be able to see the shape the fault arrives in.** Every slop defect on 2026-09-02 walked past a gate that existed and reported `passed`. `MASCOT_TEXT` matched `\bsays?\b` and `\bword\b`, so `saying 'I'm out'` and `a card with the words 'Exit Block'` — the two briefs that most plainly ask for lettering — were the two it could not read, and both shipped. `glyph_runs` counts a mark only as *a separate piece of picture*, so letters inside a speech bubble are holes in one component and score **zero** on frames whose subject fills 89.7% and 92.2% of them; `enclosed_runs` finds them and `INK_DROP=40` is measured, not chosen — 720 positives caught from drop 0 through 45, false rejects clearing at 30, across all 194 library poses at two scales. `door` was an **object** while `doorway` was a **place**, so a door moment reported no setting at all and three door decks posted in a row under two tokens; `PLACE_SYNONYM` folds them and the replay over all seven used moments goes from refusing 2 to 4, unchanged at the other windows. The duplicate-brief check compared raw words at 0.6 and **never once fired**, because `"A small donkey"` opens every brief the engine has ever written and boilerplate shared by all nine drags every pair up from below: on content words the acceptable decks score 0.11–0.20 and the slop decks 0.33–0.40, so the cap sits at 0.27, in the middle of the gap. Slide 9's CTA and closing thought were byte-identical and `check_repeats` could not see it — `Primary CTA` was not in its field list, so the pair was watched from one side only. **Measure the threshold against the corpus before the gate lands**, and put the number in the module as a named constant the test imports (invariant 25). A limb count was measured and *rejected*: 25 library poses have three or more silhouette runs because two-donkey poses are correct, so no threshold exists and the check is a vision **veto** instead — which may only take a pose away, never approve one (invariant 11), and fails closed to the library when no vendor answers. |

## Tests

Two styles, and each is **silent** when run the wrong way. Four suites are pytest-style with no `__main__` — run as scripts they execute nothing and exit 0. The rest are plain scripts — collected by pytest they report success having checked nothing.

```bash
for t in .agents/skills/suresilly-carousel/tests/test_*.py; do
  if grep -q '^import pytest' "$t"; then python -m pytest "$t" -q; else python "$t"; fi
done
```

The Worker is JavaScript and that loop cannot see it. It decides what a Telegram
reply does, and `rerun` means **drop** while `retry` means **build again**:

```bash
node ops/dispatch-worker/test/parse-reply.test.mjs
```

No test may write to `state/`. CI enforces it.

See `.agents/skills/suresilly-carousel/references/strategy.md` for the layered design.
