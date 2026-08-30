# @suresilly — carousel engine

This repository publishes to Instagram on its own.

Once a day it reads a public feed, invents a small moment of its own from what it
finds, writes a nine-slide carousel about it, checks the deck against about
thirty rules, renders the slides, and posts them.

A deck that clears the bar goes out with nobody looking at it. If you change
something here and it is wrong, the mistake goes out. That is the first thing to
know, because this file used to say "nothing is posted for you", and that has
not been true for a long time.

One deck in some number is held back and sent to you instead — see **When a deck
is held** below. That is the only decision anybody is asked to make.

---

## The one command

```bash
python .agents/skills/suresilly-carousel/scripts/run.py --no-post
```

There is one entry point and one state. The scheduled job and a person at a
laptop run this same script against the same memory of what has been used, so a
manual build cannot quietly repeat a moment the schedule already spent.

| Flag | What it does |
|---|---|
| `--publish` | Build and post. This is what the schedule runs. |
| `--no-post` | Build, render, keep the deck. **Still uses up the moment.** |
| `--dry-run` | Look at the feed and stop. Writes nothing and builds nothing. |

A run that produces a deck consumes its moment whether or not it posts. A deck
sitting on your laptop is still a deck, and if it did not retire its moment the
same evening would come round again weeks later with nobody the wiser.

To stop everything: set the repository variable `SS_HALT` to `1`, or commit a
file at `state/HALT`. Either one refuses the next run before it does anything.

---

## What a run actually does

| # | Step | Decided by |
|---|---|---|
| 0 | Read a public feed for posts that carry a small, ordinary moment | rules |
| 1 | Reject anything matching nine families of harm | rules |
| 2 | Keep what is filmable, rank what has tension in it | rules |
| 3 | Read the post as a SEED and invent our own moment from it | a model |
| 4 | Decide whether that moment may be published at all | a model, then rules |
| 5 | Plan the argument, name the pattern, write nine slides | a model |
| 6 | Argue against publishing it, from a different company's model | a model, then rules |
| 7 | Check it is new, holds together, and cites a real source | rules |
| 8 | Render, post, record | rules |

A model may write, and it may refuse. **It may never approve.** Every yes in
this pipeline comes from code.

---

## The harvested post is a seed, never a source

We read somebody's public post to learn what kind of evening they had. Then we
invent a different one — a different hour, a different room, a different
sentence, carrying the same ordinary trouble. Nothing of theirs is republished
because nothing of theirs is used, and that is checked rather than trusted: no
run of seven words may survive from the post into the moment.

Reading a name is fine. The post is public and we are only looking at it. The
rule is about what we WRITE: the moment we publish names nobody, whether the
name was copied or invented.

This used to be a rewriting step, and rewriting is where most of the trouble
lived. Keeping somebody's evening while dropping their words, their name and
anything identifying is four demands that fight each other, and the step that
hid the name deleted the person with it.

---

## When a deck is held

The reviewer scores every deck out of 100. Above the bar it posts on its own.
Below it, the deck is finished — written, checked and rendered — and it waits
for you. It arrives in Telegram with its score, the reviewer's notes and the
contact sheet.

Answer it either way. In the chat:

```
publish 79262b     post it as it is
rerun 79262b       throw it away, tonight's run builds another
list               what is waiting
```

The last six characters are enough. Or open the **Decide on a held deck**
workflow in Actions and use the dropdown. Both call the same script, because two
code paths that post to Instagram is how you end up with two different ideas of
what has already gone out.

Only the chat id in `TELEGRAM_CHAT_ID` is obeyed. Anybody can message a bot;
every other message is ignored before its text is read. And the words are
deliberately narrow — `ok`, `yes` and `sure` are not commands, because they turn
up in an ordinary chat by accident and one of them would post to Instagram.

**Harm never reaches you.** Advice that could hurt somebody, a fabricated
statistic, a real person named: those stop the deck outright with no approval
path. Not because your judgement is in doubt, but because that decision would
arrive on a phone as one line among many with approve one tap away. Everything
else — thin, preachy, flat, off-voice — is a number, and the number is yours.

---

## What you need

Everything here runs through plain Python command-line scripts, so the repo
behaves the same under Claude Code, Antigravity, a bare shell and CI. Nothing
depends on an MCP server.

| Secret | For | Without it |
|---|---|---|
| `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | reading the feed | no moments, run stops |
| `GEMINI_API_KEY` | writing | falls through to the next vendor |
| `GEMINI_API_KEY_2` … `_5` | more free quota | optional. Only helps if the key is from a **different** Google Cloud project — quota is counted per project |
| `GROQ_API_KEY` | the second vendor | the critic may have nobody independent to review with |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | the third vendor | as above |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | posting | builds but cannot post |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | sending you the deck | you find out by looking |
| `RESEND_API_KEY`, `EMAIL_FROM` | same, by email | as above |

The critic must not be the vendor that wrote the deck — a model recognises its
own work and rates it higher — so at least two vendors have to be configured
for a deck to ship.

**Rendering alone needs nothing.** `build.py` turns a written deck into slides
with no key and no network, using a library of pre-drawn mascot poses.

---

## Rendering a deck by hand

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/build.py carousels/<date>_<slug>/carousel.md
```

First run on a machine: add `--bootstrap` to build the virtualenv and fetch
Chromium.

Silly is drawn ahead of time in 165 poses, stored in `mascot/library/`. Each
slide's brief is matched to a pose, and no pose repeats inside a deck. Thirty of
them are two-donkey scenes. This costs nothing and needs no account.

There is an older path, `--generate`, that draws a fresh picture per slide. It
is **obsolete**: Gemini image generation has no free tier at all, so it fails
unless billing is on. Text generation is a different matter and is nearly free.

---

## Layout

```
.agents/skills/suresilly-carousel/     the engine. Both hosts read this.
├── SKILL.md                           entry point
├── references/strategy.md             how a deck is chosen, written and checked
├── references/                        voice, playbook, design system, citations
├── mascot/                            the poses and the character bible
├── scripts/                           run.py is the only entry point
└── tests/                             17 suites. CI runs every one.

carousels/<date>_<slug>/               one published deck: script, slides, contact sheet
state/                                 what has been used. Shared by every run.
research/                              ⚠ see the warning below
```

---

## ⚠ About `research/`

**Do not build on `research/02_account_database` or `research/05_hooks_database`.
The numbers in them are invented.**

Checked on 2026-08-30. The account table marks `@theattachmentproject` as
`[VERIFIED]` with 1.4M followers; the real account is `@attachmentproject` and
has 84K. It puts `@mindfulmft` at 1.1M against a real figure near 700K. The hook
table attributes a hundred hooks to `@habit.hacker`, `@darkpsych` and
`@shadow.work`, which are not real accounts, under an "Engagement Indicator"
column that nobody could have measured, because Instagram does not publish saves
or shares to anyone but the owner.

Those files were written by a model and labelled as verified, and some of this
engine's copy rules came from them. Evidence that is real, with sources, is in
`references/strategy.md`.

---

## The rules that must not be broken

They are in `AGENTS.md`, and each one is there because it was a shipped defect.
The short version: no text inside mascot artwork, gates abort rather than warn,
a harvested post is a seed and never a source, old decks are a blocklist and
never material, citations come from an allowlist so a model cannot type an
author's name, and there is one entry point with one state.
