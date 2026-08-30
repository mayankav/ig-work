---
name: suresilly-carousel
description: >
  End-to-end Instagram carousel engine for @suresilly, a relational-psychology page with a
  playful, self-aware, group-chat voice. Writes the slide copy, caption, hashtags and alt text,
  then renders publication-ready 1080x1350 PNG slides with the Silly the Donkey mascot placed
  on every slide. Use when asked to create, write, draft or render a @suresilly carousel,
  Instagram carousel, psychology carousel or slide deck for the page, or to work on the
  pipeline that publishes one every day.
version: "3.0.0"
author: "@suresilly"
user-invocable: true
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
| `mascot/GENERATION_PROMPTS.md` | Adding poses — 24 sheet prompts, and the rules that keep Silly on-model. |

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
| `--generate` | Obsolete paid path. Needs billing; fails otherwise. |
| `--model pro` | only meaningful alongside `--generate` — uses Gemini Pro. |
| `--model empero` | alongside `--generate` — uses Empero community models (`glm-5.3-flash` or `qwen3.8-flash`) via `https://free.empero.org/v1`. Free tier with fair usage limits. API key `free` is accepted by default. |
| `--bootstrap` | Create the venv and install Chromium. Run once per machine. |

### Which mascot path

**The library is the default — no flag needed.** 165 full-body poses live in `mascot/library/`, generated
as 6-up sheets and cut out by `scripts/import_poses.py`. `library.py` picks one per slide by
matching words in the `**Mascot:**` brief, never repeating within a deck. Costs nothing, needs
no key. 30 of them are two-donkey scenes for relationship slides.

`--generate` makes a fresh pose per slide instead. It is **obsolete and not in use**: Gemini image
generation has no free tier at all, so it fails unless billing is switched on. It stays wired for
the day you want a pose the library does not hold. Both paths read the same brief field.

To grow the library instead, see `mascot/GENERATION_PROMPTS.md` — write a 6-up sheet, then
`scripts/import_poses.py`.

Runs the same under Claude Code, Antigravity, a bare shell and CI. It calls the Gemini REST API
directly and never depends on an MCP server.

---

## Generation protocol — utility-first, hook-last (from scratch, 2026-08-28)

Why rearranged: Old was `Topic → Hook → Source → Value → Humanize → Check`. Hook-first optimizes for swipe, value becomes 3× why + 1 vague how (`set two timers`) — feels useful for 90 seconds, useless at 11:47pm. Research (Gottman, Walker, Porges, Maté, Clear/Gollwitzer 91% vs 35%) shows useful = `I will [behavior] at [time] in [location]` + copy-paste words, not insight. New is `JTBD → Moment → Research → Utility → Hook` — hook distills utility, not invents promise.

### Starting a deck: two modes

> **The "I'm feeling lucky" mode below is superseded and no longer runs.** The pipeline picks
> its own moment: it harvests a public post, uses it as a seed, and invents the moment itself.
> See `references/strategy.md`. What follows is kept because the topic and pattern reasoning
> is still sound if you are writing a deck BY HAND — but nothing here is executed by `run.py`,
> and `topic-bank.md` is no longer read by any script.

**"I'm feeling lucky" (superseded)** — pick via two scored layers, then run the full 10-step protocol.

**Layer 1 — Suggestion — SURGE: 70%+ Relational / Attachment (for follower surge).** Per `brand-voice.md` niche #1 (9.8 shareability, 9.5 virality) + `topic-ranking.md`. Pull 12-15 candidates as:
* **70% Relational / Attachment** — Bowlby/Ainsworth/Johnson/Tatkin/Gottman/Perel/Levine&Heller: `reread-okay` (scanning), `family-15-again` (reunion), `apologies-reflex`/`say-yes-resent` (fawn), `burden-feel`/`burden-boundaries`, `inbox-reread-boss` (bids) — all `sends` intent, `Visual Comparison` or `Script / Template` pattern, filmable domestic scene. This is the DM-share engine for surge.
* **20% Emerging arbitrage** (functional freeze, waiting mode, RSD) — keep 1-2 max, not as lead, to avoid `brain did it` monotony.
* **10% Community / Trend** — CPTSD, doomscroll only as support.
Breakdown: 7-8 from `topic-bank.md` where `Niche pillar` contains `People-pleasing, Hypervigilance, Family, Boundaries, Self-worth` (filter `Last used == -`), 3 from VOC verbatims relational, 2 from pattern gaps. Superseded: `run.py` picks the moment and the angle. This step is a record of the manual process and the script it named has been deleted.

**Layer 2 — Selection (score, then qualify).** 1-5 on: Scene filmable? / Self-blame invertibility? / Stealability? (one sentence survives DM) / Freshness (+1 emerging Rank 5-6, -1 oversaturated per HireInfluence) / Intent fit (sends ≤8w Unspoken Reality vs saves 9-12w Absolution per SocialInsider). Total 25, ship ≥18, <15 for all = bank stale → mine 10 new VOC. Winner goes through Step 0 three questions as final gate.

- Do not pause to confirm. Build and show contact sheet — user reacts to result.
- Leave `**Palette:**` out unless user named colour — round robin picks.

**The user gives a topic or brief** — follow the 10-step protocol using what they gave you. Ask only if genuinely ambiguous — never to confirm plan.

0. **Job Diagnosis (what will they hire this to do? — before topic).** Choose primary Job from 4: (1) Give words when none, (2) Give tiny next step before motivation dies, (3) Give proof to send, (4) Give way to act *while* anxious (not after calm). Also name Anti-Job (what we are NOT doing). Prevents Generic Topic Trap — `attachment styles` becomes `give words to send to avoidant at 11pm without sounding needy`.
1. **Moment Lock (one clock-time, location, body).** Crystallize `When [11:47pm bed phone chest tight after left on read] + Who + What happened + What you want to say/do but can't`. If it works for every moment, it works for no moment. Specificity is what makes them send `this is me`.
2. **Topic Confirm + Pattern (now informed).** Qualify via `content-playbook.md` 3Qs: (a) Scene filmable? (body/number/time/place — `127 unread at 11:47pm` beats `burnout`) (b) Self-blame? (laziness, too much) (c) Stealable one-liner? If concept or no (b), pick different topic. Pick pattern + intent: sends ≤8w scene-heavy vs saves 9-12w list. Must differ from last 5 decks.
3. **Sniper Research (one mechanism + one boundary).** Pull ONE mechanism + ONE limit for *that* Moment, not a lit review. E.g., Waiting mode = Barkley time blindness, Gottman bid = 86% turn toward, Walker fawn as 4th response. Plain English + Source. Prevents research-theater.
4. **Protocol Forge — cheat sheet FIRST (the Save).** Build utility *before* any slide copy. Tiny Protocol: (a) Script (<20w copy-paste with `[name][day]`), (b) Implementation Intention `I will [behavior] at [time] in [location]`, (c) Habit Stack `After I [existing habit], I will...`, (d) If-Then `If [trigger at place/time], then [2-min response]` — must be doable while anxious, no googling, <2 min, one behavior. If you can't make it, kill idea here. This is the entire reason to save.
5. **Voice-First Draft (humanize inline).** Write full deck IN group-chat voice from line one — no formal → humanize pass. Contractions, fragments, sensory detail from Moment. If you can't say it like a friend, you don't understand it.
6. **Hook Distillation LAST.** Reverse-engineer cover from Protocol. Hook = compression of Protocol's payoff, makes promise only Protocol can keep. H1 Mirror (filmable behavior ≤8/12) + H2 Absolution (peer reframe ≤7w). 3 variants max keep VOC detail verbatim, 4 checks (No second-person DSM? Filmable? One breath? You=hero?). Log in `HOOK_LEDGER.md`. Prevents swipe-bait + retention crash.
7. **Retention Architecture.** Pace for watch time > sends > saves: Slide 1 Hook → 2 Validation (`if this is you`) → 3-4 Mechanism (one slide, not three) → 5-7 Tools (one script/pact per slide) → 8 If-Then for when it fails → 9 Loop back to slide 1 (sendable proof). Re-hooks on 4 & 6 (6-10w, body copy).
8. **Anxious-State Stress Test.** Simulate using Protocol while dysregulated: <18w/slide, giant type, one action/slide, no calm required. Blurry vision test.
9. **Usefulness Gate (Gate 1 of 2) — abort if fail.** PASS if 28yo could do it in next 24h without googling, <2 min, no new apps, while anxious. Checks: 24-hour without googling / Words not why (≥2 copy-paste slides) / One-moment (H1+7+8 same scene with body/number/place) / Screenshot save (slide 8 self-contained tool). Fail → back to 4.
10. **Truth Gate (Gate 2 of 2) + Double-check.** Fact-check after usefulness: no overclaim, mechanism matches source, boundary stated, no diagnosing. Then run `audit_copy.py` (hook gate + No second-person DSM + sliding length + AI-pattern) + `HOOK_LEDGER.md` + second pair eyes (H1/H2+slide2). Only then save to `carousels/<YYYYMMDD>_<slug>/carousel.md` and `build.py`. Read contact sheet as set.

### Slide arc — utility-first (ratio flipped)

```
1  HOOK        H1 Mirror (≤8 sends / ≤12 saves) + H2 Absolution (≤7). Filmable. No second-person diagnosis. Distilled from Protocol.
2  AGITATION   Validation — "if this is you" — ≤25w, own [[accent]], promises the tool — second cover if re-served
3  SOURCE      ONE mechanism in plain language + ONE boundary/limit, with Source — not name-drop
4  VALUE-ONE-WHY One insight: 3-6w headline + 2-3 sentences — the only why (mechanism)
5  VALUE-TOOL1 Script — copy-paste words with [brackets] — <20w
6  VALUE-TOOL2 If-Then / Habit Stack — I will [behavior] at [time] in [location] — re-hook
7  VALUE-TOOL3 Menu of 3 tiny options (no invention) — pick 1
8  CHEAT SHEET Self-contained tool (scripts + if-then + menu) — screenshot save — no new decisions
9  CTA         Proof to send — relational DM to specific person + handle — loops to H1
```
Ratio: old 3 why :1 vague how → new 1 why :3 tools. Each tool slide ends with re-hook, cheat is built first.

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

Templates: **A** clean statement · **B** numbered insight (add `- **Badge:** 01`) ·
**C** before/after script · **D** cheat sheet (`- **Callout:**` + `• ` bullets) ·
**E** CTA · **F** source anchor.

Never write slide numbers, the `@suresilly` footer or the swipe cue into copy — the renderer adds
them. Never use emoji; they are stripped.

> **The three `[placeholder]` lines above are deliberately not real briefs — do not adapt or
> paraphrase them into a deck.** Selection scoring is deterministic: the same brief text always
> produces the same pose, so a template sentence copied into two carousels guarantees the same
> donkey on both. This already happened — four of the first five decks shipped with
> near-identical hook/source/cheat/CTA briefs traced straight back to an earlier version of this
> example, and it is why so many carousels ended up looking alike. If you want to see what a real
> brief for these slide types looks like, read a finished `carousels/*/carousel.md` for a
> **different** topic than the one you're writing — never this file.

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

**Content** — Slide 1 lands in 1.5s · slide 3 cites something specific · the source actually
grounds slides 4–7 · one idea per slide · the cheat sheet works as a standalone screenshot ·
the CTA asks for a DM-share to a *specific person*, not a like · no mascot brief is copied from
this file or from another deck — run `grep -h "Mascot:" carousels/*/carousel.md | sort | uniq -d`
and confirm nothing repeats verbatim before calling a deck done.

**Topic** — Slides 1–2 name a **scene**, not a concept; no diagnosis vocabulary before slide 3 · the deck reattributes something the reader blames themselves for · **at least one line could be sent alone in a DM and still land** · it is general psychology (anxiety, burnout, sleep, self-worth etc.), not productivity or a book summary · the pattern differs from the last few decks · **if lucky:** topic came from `topic-bank.md` Layer 1+2, scored ≥18/25, and passes Step 0's three questions — not invented.

**Hook tension** — the hook leaves a gap it does not close · it stages a scene instead of
announcing a lesson · it carries one odd, specific, true detail rather than a general statement
(*"put your phone face-down"*, not *"feel anxious about replies"*) · nothing in it sounds like a
guru. If the hook could be the title of a self-help chapter, rewrite it. · winner is a verbatim
VOC behavior trimmed to intent length (≤8 sends / ≤12 saves) + H2 absolution · `HOOK_LEDGER.md`
updated with VOC list + checks + winner.

**Hook gate (MUST pass before build)** — Slide 1: intent declared (sends ≤8w or saves 9-12w), no second-person diagnosis (`you have/are *attachment/trauma/dysregulation*` banned; noun form `waiting mode` allowed), filmable (body/number/place), H2 ≤7w absolution, passes 4 checks (No second-person DSM / Filmable / One breath / You=hero) · slide 2 works as second cover (≤25 words, own `[[accent]]`, not "Let me explain") · slides 4 and 6 end with re-hook · deck does not repeat previous pattern — check ledger.

**Voice** — Would a 30-year-old screenshot this and text it at midnight with "omg this is us"? No DSM-as-diagnosis left untranslated. Compassionate, not preachy. Rigorous, not platitude-level. Absolution first.

**Technical** — **Slide 1 H1 ≤8 sends / ≤12 saves hard max** (count; intent must be declared) ·
H2 ≤7w · ≤220 characters per body slide · 8–10 slides · one `[[accent]]` per slide, on pivot word · US spelling · every slide has alt text.

**DOUBLE-CHECK BEFORE BUILD — non-negotiable:**
1. Content audit: `audit_copy.py` must pass (hook gate + no second-person diagnosis + sliding length).
2. Hook audit: the hook gate in `audit_copy.py` (human > score — if the screenshot test fails, rewrite anyway).
3. Ledger: `HOOK_LEDGER.md` entry with 10 mined verbatims, 3 variants, 4 checks, winner, intent, slide 2 second-cover line, re-hooks.
4. Second pair of eyes: re-read H1/H2 + slide 2 alone — does H1 mirror a behavior you did this week, and does slide 2 pay it in one sentence? If no, do not run `build.py`.
Only then: save to `carousels/<YYYYMMDD>_<slug>/carousel.md` and run build. A carousel that skipped the double-check is not done.

**Visual** — Open `contact_sheet.png`. Zero text baked into any mascot. Nine distinct
expression/posture combinations. Colour rotation reads as rhythm, not randomness. Nothing
clipped, nothing colliding.
