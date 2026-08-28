# Silly the Donkey — Carousel Maker

This tool makes Instagram carousels for **@suresilly**. @suresilly is a page about
relationships and feelings. It talks like a smart friend, not like a textbook.

The tool does two jobs:
- It writes the words for each slide.
- It draws the finished slide images, with the mascot, Silly the Donkey, on each one.

You do not need to know how to code. You talk to the assistant in plain words. The assistant
does the rest.

---

## ⭐ How to make a carousel

There are two ways to start. Pick one.

### Way 1 — "I'm feeling lucky"

Use this when you do not have a topic yet.

Say this to the assistant:

> **I'm feeling lucky. Make me a carousel.**

The assistant will then:
1. Pick a topic on its own.
2. Write all the words.
3. Draw all the slides.
4. Show you the finished carousel.

You do nothing else. You only look at the result and say if you like it.

### Way 2 — You pick the topic

Use this when you already know what the carousel should say.

Copy the box below. Fill in your own words. Send it to the assistant.

> **Write a @suresilly carousel about:** [your topic]
> **The one point I want to make:** [one sentence]
> **Who this is for:** [the kind of person reading it — e.g. "people who overthink every text"]
> **Tone (optional):** [e.g. "playful", "validating", "a bit blunt"]

The assistant uses your answers to write and draw the carousel.

---

## What you get back

When a carousel is done, you get:

- A set of finished slide images, ready to post.
- One extra image called a **contact sheet** — all the slides shown together in a grid, so you
  can check the whole set at a glance before you post.
- A caption, hashtags, and alt text to go with the post.

Nothing is posted for you. You still choose when and where to share it.

---

## Running it yourself (for developers)

You do not need this section to make a carousel — the assistant handles it. Read this only if
you want to run the commands by hand.

**Setup, once per machine:**

```bash
.agents/skills/suresilly-carousel/scripts/build.py --bootstrap
```

**To build one carousel:**

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/build.py carousels/20260822_my_topic/carousel.md
```

This reads the script file, picks a mascot picture for each slide, draws every slide, and saves
a contact sheet.

**What you need:** Python 3.11 or newer. Nothing else — no account, no key, no internet
connection.

There is one unused, paid path (the `--generate` flag) that needs a paid Google account and a
network call. It does not work on a free account. You will not need it.

---

## How the files are organized

```
.agents/skills/suresilly-carousel/     the tool itself
├── SKILL.md                           start here to understand how it writes and builds
├── references/                        voice rules, hook ideas, source ideas, design rules
├── mascot/                            the mascot's pictures and the rules for drawing him
├── scripts/                           the code that writes the words and draws the slides
└── tests/                             checks that catch broken output before you see it

carousels/<date>_<topic-name>/
├── carousel.md                        the script for this one carousel
├── slides/                            the finished slide images
└── contact_sheet.png                  all the slides together, in one grid

research/                              the market research this page's topic was chosen from
```

---

## How the mascot's pictures are chosen

Silly is drawn once, ahead of time, in many different poses and moods — over 180 of them,
stored in `mascot/library/`. For each slide, the tool reads what that slide is about and picks
the pose that best matches. No two slides in the same carousel repeat the same pose.

This costs nothing and needs no internet connection or account.

There is also an older, unused way to draw a brand new picture for every single slide instead
of picking from the stored ones. It needs a paid account and does not work on a free one, so it
is switched off by default. You will not need it.

---

## Where the topic and style came from

Before building this, we researched 25 possible page topics and scored each one on how likely
it was to spread, get saved, and make money. Relationships and attachment came out on top — that
is why this page exists. That research, plus 100+ real hook examples and 15 competitor page
designs, lives in `research/` if you want to see the reasoning.
