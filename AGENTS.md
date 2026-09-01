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
  tests/            25 suites, CI runs every one
scripts/            NOT the engine's. Jobs around it, never imported by it:
                    post_to_ig · prune_slides · insights · notify · capacity · dashboard
.github/workflows/  auto-post (08:00, 20:00 IST) · insights · review · telegram-review
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
| 12 | **A citation is proved before it is printed.** Five gates in `bibliography.py`, all fail closed. Shelf whitelist: LC `BF RC RJ HQ HM QP`, Dewey 150–158. Open Library is told who is calling and deliberately not given an email. |
| 13 | **Two channels, one funnel.** Feed or concept, both produce one invented moment with a subject from the closed list. A phrase enters `QUERIES` only after `probe_phrases.py` measures it. |
| 14 | **No condition is ever hardwired.** No OCD topic, no ADHD topic — only a route by which such a term arrives on its own and is ranked. `clinical` is off at the concept layer, replaced by `SEVERE`, `LIFE_EVENT`, `IDENTITY_SPECIFIC`, `NOT_OUR_READER`. |
| 15 | **`discovery.py` never names a book.** It proves a term is real and stops. `bibliography.py` owns citations. A concept's Wikipedia summary is read, never printed. |
| 16 | **One entry point, one state.** Any run that makes a deck uses up its moment. State lives in `state/` and is committed. **`flux_neurons.json` and `vendor_quotas.json` are opposites and must never be merged** — a ledger only rises, a quota snapshot is always replaced. |
| 17 | **What we publish is measured; the measurement never decides.** `insights.py` may import nothing from the pipeline and nothing may import it. A missing metric is recorded as missing, never as zero. |
| 18 | **The host is not the archive.** Host keeps 14 days (`prune_slides.py`, after the post, never before). Repo keeps `carousel.md` and `contact_sheet.png`. `slides/*.png` and `carousels/*/mascot/` are gitignored. Pending decks are protected by name. **Keep `keep_files: true`** — the pruner owns deletion. |
| 19 | **A new seed does not make a new moment.** Four checks in `compose.py`: same words, same opening verb, same room, and copying the worked example. Examples rotate and the answer is measured against the one shown. |
| 20 | **An example in a prompt is a template, and an on-subject example is copy.** Measured: five of seven published decks carried a run of words lifted from the prompt, including a sentence the prompt quotes in order to forbid it. Every example that was set on the page's own ground got copied within a week; the off-subject ones never were. So **every example in `PLAN_SYSTEM` and `DRAFT_SYSTEM` is about dentists, parking tickets, library books and bicycles**, and `writer.check_leak` fails any draft sharing four consecutive words with the prompt. `references/voice-target.md` is the deck the engine is aiming at and **must never be loaded into a prompt** — it is on-subject, so it would be a template. |

## Tests

Two styles, and each is **silent** when run the wrong way. Four suites are pytest-style with no `__main__` — run as scripts they execute nothing and exit 0. The rest are plain scripts — collected by pytest they report success having checked nothing.

```bash
for t in .agents/skills/suresilly-carousel/tests/test_*.py; do
  if grep -q '^import pytest' "$t"; then python -m pytest "$t" -q; else python "$t"; fi
done
```

No test may write to `state/`. CI enforces it.

See `.agents/skills/suresilly-carousel/references/strategy.md` for the layered design.
