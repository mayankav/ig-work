---
name: suresilly-carousel
description: >
  End-to-end Instagram carousel engine for @suresilly, a relational-psychology page with a
  playful, self-aware, group-chat voice. Writes the slide copy, caption, hashtags and alt text,
  then renders publication-ready 1080x1350 PNG slides with the Silly the Donkey mascot placed
  on every slide. Use when asked to create, write, draft or render a @suresilly carousel,
  Instagram carousel, psychology carousel or slide deck for the page, or to work on the
  pipeline that publishes two every day.
metadata:
  version: "3.0.0"
  author: "@suresilly"
---

# @suresilly Carousel Creator

Given a topic, hook or brief, produce a complete carousel: a markdown script **and** the rendered
slide PNGs. A script without rendered slides is an incomplete deliverable.

## Load on demand

Read these only when you need them — do not pull them all in up front.

| File | Read it when |
|---|---|
| `references/strategy.md` | **Read first for any pipeline work.** How a deck is chosen, written, checked and shipped. The eight layers, what the model may and may not decide, and why manual and scheduled runs behave identically. |
| `references/brand-voice.md` | Writing any copy. Voice dials, positioning, audience, what we are not. |
| `references/content-playbook.md` | Qualifying a topic, choosing a pattern, a hook, or the slide-3 source anchor — always, before writing a word. |
| `references/topic-bank.md` | **Superseded by `strategy.md`.** Kept as a record of the original VOC mining. Moments now come from the live queue, not this table. |
| `references/design-system.md` | Changing layout, colour, type or mascot placement. |
| `mascot/CHARACTER.md` | Writing mascot briefs, or if Silly looks off-model. |
| `mascot/GENERATION_PROMPTS.md` | Adding poses — 29 sheet prompts, and the rules that keep Silly on-model. |

---

## The one entry point

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/run.py --no-post
```

`run.py` is the whole pipeline and the only way a post is made: harvest, compose, judge, write,
critique, render, publish, record. The scheduled job and a person at a laptop run this same
script against the same state, so a manual build cannot repeat a moment the schedule spent.
`--publish` posts, `--no-post` builds and still uses the moment up, `--dry-run` writes nothing.
`--no-fresh` skips drawing new mascot art and takes every pose from the library instead —
generation is ON by default on this path (invariant 2), so leave the flag off unless you are
building to read the copy.

Read `references/strategy.md` before changing any of it.

## Rendering a written deck

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/build.py carousels/<YYYYMMDD>_<slug>/carousel.md
```

Parses the script, picks a mascot pose per slide from the library, renders the slides, and
writes a `contact_sheet.png` for review. Needs no key and no network. `run.py` calls this
itself; run it by hand only to re-render a deck you have edited.

| Flag | Use |
|---|---|
| *(none)* | **Default. Uses the pose library. Free, instant, no key.** |
| `--no-mascot` | Fast copy and layout iteration. |
| `--generate` / `--model` | Removed. Both stop before any request or write. Use `--fresh` for the checked free path. |
| `--fresh` | Generate a pose per slide from that slide's own brief, via `fresh_poses.py`. Free, never load-bearing — every failure hands the slide back its library pose. `run.py` passes this on every run; on `build.py` it is opt-in. See invariant 2. |
| `--fresh-budget N` | Cap what `--fresh` may spend, in neurons. Only meaningful with `--fresh`. |
| `--random-palette` | Ignore the round-robin and roll a theme. |
| `--bootstrap` | Create the venv and install Chromium. Run once per machine. |

### Which mascot path

| Path | When | Cost |
|---|---|---|
| **Draw fresh** | Default on `run.py`. One pose per slide from that slide's own brief. Requires a qualified image reviewer before drawing; a key alone is not enough. | Free allowance, bounded by the run's ledger |
| **Library** | The fallback. Every failure lands here, and `--no-fresh` picks it outright. | nothing, no key, no network |
| `poses_flux.py` | Offline tool to grow the library in bulk. | free |
| `--generate` / `--model` | Removed from the builder. No code path reaches the obsolete mascot module. | no request |

A drawn pose is checked before it reaches a slide, then inspected in groups of
at most three poses. Each inspection includes full-body and enlarged detail views
plus a known defective control. There are at most three review requests per deck.
The model may only veto; missing coverage, uncertainty, a missed control or an
unreadable reply rejects the group. The exact model must first pass the fixed
qualification set. No qualified model means no fresh generation.

The library candidate is the exact reviewed PNG, not the raw frame. Import uses
`--exact`: all pixel gates still run, but cropping, matting, mirroring, colour
changes and overrides are forbidden. Candidate hashes must match before import.
In `run.py`, novelty is checked before fresh generation; new art is imported only
after the complete render passes.

`art_eligibility.py` is mandatory for fresh art, imports, library selection and
generation references. It stores exact group images, the inspection sheet hash,
the model response and check version. A saved flag cannot establish eligibility:
the sheet, coverage, control and vetoes are replayed. Changed image bytes, check
code or model qualification require a new usable check. The renderer freezes the
checked image bytes and retains the evidence references with all nine slides.
Publishing checks that evidence again, including for held decks.

Offline library audit (maximum nine PNGs and three model requests per invocation):

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/art_eligibility.py path/to/final.png
```

This requires an already qualified free model; it does not qualify a model or
promote an image. For transformed imports, use `import_poses.py --preview DIR`
first, audit the staged PNGs, then import those files with `--exact`. Evidence
lives in `mascot/checks/` and is committed with the run. The existing library
still needs this audit. See `docs/reliable-posts-status.md` before enabling posting.

The library holds about 190 poses, 32 of them two-donkey scenes, matched to a slide by the words in its brief and never repeated inside a deck. **Do not quote a count from this file** — every run imports new poses, up to 18 a day. Count them:

```bash
python3 -c "import json;print(len(json.load(open('mascot/poses.json'))['poses']))"
```

**Three cautions on generating.** The flux **9B** model is non-commercial and the code refuses it. Generated green drifts washed-out against `#3C965A`, so judge new poses on a contact sheet beside old ones. The allowance is shared with the Cloudflare text vendor — `state/flux_neurons.json` is the ledger.

Hand-drawn 6-up sheets still work: `mascot/GENERATION_PROMPTS.md`, then `scripts/import_poses.py`.

Text vendors are called over plain REST, in order: Gemini → Groq → Cloudflare.
No MCP. **Two must be configured**, because the critic may not be the vendor that
wrote the deck. Production image review uses `image_review.py` and an exact model
with current qualification evidence. `probe_vision.py` is an offline diagnostic;
accepting an image request does not qualify a model to review production art.

---

## Writing a deck

**Order: job → moment → research → tools → hook last.** The hook is squeezed out of the tools at the end; it never invents a promise the deck cannot keep.

| Step | Do |
|---|---|
| 1 | **Pick the job.** One of: give words when they have none · give a tiny next step · give proof to send · give a way to act *while* anxious. |
| 2 | **Lock the moment.** One clock time, one room, one body. If it fits every evening it fits none. |
| 3 | **One mechanism, one limit.** For *that* moment. Not a literature review. |
| 4 | **Build the cheat sheet first.** A script under 20 words with `[brackets]`, and an if-then doable in 2 minutes while anxious, no googling. **If you cannot write it, kill the idea here.** |
| 5 | **Draft in voice.** Group-chat, from line one. No formal draft, no humanising pass. |
| 6 | **Hook last.** H1 mirrors a filmable behaviour, H2 reframes it as human, not broken. |

### The nine slides

| # | Slide | Carries |
|---|---|---|
| 1 | Hook | H1 ≤8w sends / ≤12w saves + H2 ≤7w. Filmable. No diagnosis. |
| 2 | Agitation | "if this is you" ≤25w. Works as a second cover. |
| 3 | Source | One mechanism in plain words + one limit, with the citation. |
| 4 | Why | 3–6w headline + 2–3 sentences. The only "why" in the deck. |
| 5 | Script | Copy-paste words with `[brackets]`, <20w. |
| 6 | Action | `I will [do X] at [time] in [place]`. Re-hook here. |
| 7 | Menu | Three tiny options. Pick one. |
| 8 | Cheat sheet | Self-contained. Survives as a screenshot alone. |
| 9 | CTA | Something to send one specific person. Loops to slide 1. |

One "why", three tools. Re-hook on slides 4 and 6.

### Before you build — all must pass

| Check | Fails if |
|---|---|
| Scene, not concept | Slides 1–2 name a concept, or use diagnosis words before slide 3 |
| Self-blame inverted | Nothing the reader privately blames themselves for is reattributed |
| Relational | It could run on a general anxiety page with no other person in it |
| Usable in 24h | It needs googling, a new app, motivation, or inventing anything |
| Words, not why | Fewer than 2 slides are copy-paste scripts |
| Stealable | No single line could be sent alone in a DM and still land |
| Simple words | Any line a reader sees carries a four-syllable word, or the deck grades above 6 |
| The h2 has a job | The subtitle neither absolves nor promises, or adds fewer than 2 words to the h1 |
| `audit_copy.py` | Any hook-gate, length, readability or AI-pattern failure |

### Script format

```markdown
# Carousel: [Internal Title]

**Pattern:** · **Content Pillar:** · **Core Emotion:**
**Palette:** [optional — plain-English colours like `reddish / pinkish`, or leave out entirely.
See "Choosing a deck's colour" in `references/design-system.md`.]

### Slide 1 · Hook
- **Layout:** Template A
- **H1:** Why calm people make your nervous system [[panic]].
- **H2:** (and why you confuse chaos with "chemistry")
- **Mascot:** [placeholder — this is the fictional doorbell-anxiety example below, not a real
  brief. See the warning after this block before writing your own.]

### Slide 3 · Source Anchor
- **Layout:** Template F
- **Body:** ...
- **Source:** — Stephen Porges & Deb Dana, *Polyvagal Theory in Therapy* (2018)
- **Mascot:** [placeholder — same warning applies]

### Slide 5 · Value Step 2
- **Layout:** Template C
- **❌ Old Reaction:** "..."
- **✅ Regulated Response:** "..."
- **Mascot:** [placeholder — same warning applies]
```

| Template | Use |
|---|---|
| A | clean statement |
| B | numbered insight (add `- **Badge:** 01`) |
| C | before/after script |
| D | cheat sheet (`- **Callout:**` + `• ` bullets) |
| E | CTA |
| F | source anchor |

Never write slide numbers, the `@suresilly` footer, the swipe cue or emoji into copy — the renderer adds or strips them.

> **Never copy a `**Mascot:**` line from this file.** Pose selection is deterministic: the same brief text always picks the same donkey. To see a real brief, open a finished `carousels/*/carousel.md` on a **different** topic.

### Writing mascot briefs

`- **Mascot:**` takes **plain English**, not a pose code. Describe expression and posture (both
required), plus wardrobe and a single prop when the slide has a concrete situation. Omit the line
and the renderer falls back to a sensible default for that slide role.

Full guidance and the four variable slots: `mascot/CHARACTER.md`.

Three hard rules: describe **behaviour, not emotion labels** ("both hooves over the eyes,
shoulders collapsed", not "feeling overwhelmed"); **never imply text** in a prop — no signs,
newspapers, labelled bottles or screens, since text in the artwork is the one defect that makes a
slide unpostable; and **never reuse a brief verbatim** between slides or between decks — if two
slides could share a brief, the brief is too generic and needs a specific behaviour, object, or
beat pulled from that slide's own copy.

---

## Quality checklist

**Hard limits — code enforces these**

| | Limit |
|---|---|
| Slides | exactly 9, in the fixed role order |
| H1 | ≤8 words (sends) / ≤12 (saves) |
| H2 | ≤7 words |
| Body | ≤220 characters |
| Accent | exactly one `[[word]]` per slide, on the pivot |
| Spelling | US. Alt text on every slide. |

**Judgement — yours**

| Ask | Fail if |
|---|---|
| Slide 1 | It takes longer than 1.5s, or reads like a self-help chapter title |
| The hook | It closes its own loop, announces a lesson, or sounds like a guru |
| Specificity | It says "feel anxious about replies" instead of "put your phone face-down" |
| Slide 3 | The source does not actually ground slides 4–7 |
| Slide 8 | It does not survive alone as a screenshot |
| Slide 9 | It asks for a like, not a send to one specific person |
| Voice | A 28-year-old would not text it at midnight with "omg this is us" |
| Mascot briefs | Any repeat. Check: `grep -h "Mascot:" carousels/*/carousel.md \| sort \| uniq -d` |

**Then look at `contact_sheet.png`.** Zero text baked into any mascot. Nine distinct poses. Colour reads as rhythm, not randomness. Nothing clipped or colliding.

A deck that skipped `audit_copy.py` is not done.
