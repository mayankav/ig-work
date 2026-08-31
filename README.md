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
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/run.py --no-post
```

There is one entry point and one state. The scheduled job and a person at a
laptop run this same script against the same memory of what has been used, so a
manual build cannot quietly repeat a moment the schedule already spent.

| Flag | What it does |
|---|---|
| `--publish` | Build and post. This is what the schedule runs. |
| `--no-post` | Build, render, keep the deck. **Still uses up the moment.** |
| `--dry-run` | Look at the feed and stop. Writes nothing and builds nothing. |
| `--source feed` | Where the idea comes from: a harvested post. The default. |
| `--source concept` | Where the idea comes from: a proved concept from the vocabulary. |

A run that produces a deck consumes its moment whether or not it posts. A deck
sitting on your laptop is still a deck, and if it did not retire its moment the
same evening would come round again weeks later with nobody the wiser.

To stop everything: set the repository variable `SS_HALT` to `1`, or commit a
file at `state/HALT`. Either one refuses the next run before it does anything.

### Two channels, one funnel

An idea reaches a deck one of two ways, and both end in the same place: one
invented moment with a subject from the closed list.

**The feed** knows what people are actually doing this week and the words they
use for it. It is 46 measured search phrases. It was 18, and those turned out
to be the account's entire subject range — five about a phone, five about the
night, and three of the first seven decks set on a bed. The 28 added on
2026-08-31 were each measured with `probe_phrases.py` before being trusted.

**The vocabulary** knows what any of it is called. `references/concepts.json`
holds terms of art discovered from public category listings, each proved to
appear in at least two scanned books, each ranked on measured demand. It names
no book: `bibliography.py` finds and proves the citation for every deck, as it
always has.

```bash
# grow the vocabulary — safe to stop and rerun, it saves as it goes
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/discovery.py --refresh

# see what is in it, and what the next concept run would use
.agents/skills/suresilly-carousel/scripts/discovery.py --list
.agents/skills/suresilly-carousel/scripts/discovery.py --pick
```

No condition is ever hardwired. There is no OCD topic and no ADHD topic. What
there is, is a route by which such a term can arrive on its own, with measured
demand behind it, and be ranked against everything else. The harm and scope
families reject a concept exactly as they reject a moment.

---

## What a run actually does

| # | Step | Decided by |
|---|---|---|
| 0 | Read a public feed, OR take the best unused concept from the vocabulary | rules |
| 1 | Reject anything matching nine families of harm | rules |
| 2 | Keep what is filmable, rank what has tension in it | rules |
| 3 | Invent our own moment — from the seed, or from what the concept means | a model |
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

### How much of each is free

Everything runs on free allowances. **[CREDITS.md](CREDITS.md)** says how much we
get, when it comes back, and what happens when it runs out.

The short version: pictures are the only thing that ever runs out. We can make
about **31 mascot pictures a day**, which is three full decks. When that is gone
a slide takes a pose from the library instead and nothing breaks.

To see what is left right now:

```bash
.agents/skills/suresilly-carousel/.venv/bin/python scripts/capacity.py
```

Add `--notify` to send the same thing to Telegram.

---

## Rendering a deck by hand

```bash
.agents/skills/suresilly-carousel/.venv/bin/python \
  .agents/skills/suresilly-carousel/scripts/build.py carousels/<date>_<slug>/carousel.md
```

First run on a machine: add `--bootstrap` to build the virtualenv and fetch
Chromium.

Silly is drawn ahead of time in 180 poses, stored in `mascot/library/`. Each
slide's brief is matched to a pose, and no pose repeats inside a deck. Thirty of
them are two-donkey scenes. This costs nothing and needs no account.

The library is no longer frozen. `scripts/poses_flux.py` adds poses to it for
nothing, through Cloudflare Workers AI — the same account the third text vendor
already uses, so there is no new signup and no card. It uses FLUX.2 klein **4B**,
which is Apache-2.0 and may be used commercially, and it takes four reference
images so it can be shown the character instead of told about him. The 9B model
beside it is better and is non-commercial; the code refuses it and two tests say
so.

It is an offline tool. It writes frames for the existing import and matting path
and is never called at build time, because a build that needs a network is a
build that can fail at 8am with nobody watching. Expect the generated green to
come out washed out against `#3C965A`, and judge new poses on a contact sheet
next to old ones before importing them.

There is an older path, `--generate`, that draws a fresh picture per slide. It
is **obsolete**: Gemini image generation has no free tier at all, so it fails
unless billing is on. Text generation is a different matter and is nearly free.

---

## Running the gates

```bash
for t in .agents/skills/suresilly-carousel/tests/test_*.py; do
  .agents/skills/suresilly-carousel/.venv/bin/python "$t" || echo "FAILED $t"
done
```

Every suite in the directory, which is exactly what CI does — a hand-kept list
drifted once and left six suites nobody ran. `pytest` is not the runner: these
are plain scripts with a `run()`, so pytest collects the files, finds no test
functions, and reports success without having checked anything. That is worse
than no test run, because it is believed.

Needs no key and no network.

---

## Layout

```
.agents/skills/suresilly-carousel/     the engine. Both hosts read this.
├── SKILL.md                           entry point
├── references/strategy.md             how a deck is chosen, written and checked
├── references/                        voice, playbook, design system, citations
├── mascot/                            the poses and the character bible
├── scripts/                           run.py is the only entry point
└── tests/                             22 suites. CI runs every one.

scripts/                               posting and the jobs around it:
                                       post_to_ig · notify · insights · prune_slides
carousels/<date>_<slug>/               one deck: carousel.md, contact_sheet.png,
                                       published.json. slides/*.png are rendered
                                       but not committed — see below.
state/                                 what has been used. Shared by every run.
research/                              ⚠ see the warning below
```

---

## Where the slides live, and for how long

Instagram fetches each slide **once**, when the post is being assembled, and
serves the carousel from its own servers after that. The public URL only has to
answer for about a minute.

So the two places a slide is kept have different jobs:

| | what it is for | how long |
|---|---|---|
| `gh-pages` → `media.suresilly.com` | the address Instagram reads from | 14 days |
| the repo | the archive you look back at | forever |

`scripts/prune_slides.py` runs **after** the post and takes down decks past the
window. The repo keeps `carousel.md` and `contact_sheet.png`, which is what a
deck is judged by; the nine full-size PNGs are gitignored. That is about 1.2 MB
a deck instead of 6.8 MB.

This was not tidying. Nothing removed anything, so the host grew ~14 MB a day
against a 1 GB GitHub Pages limit, and the same PNGs went into git history as
well. Both ceilings were about nine weeks out.

**A held deck is the exception to watch.** It is posted days later from that same
host, so decks waiting in `state/pending/` are protected by name and their slides
stay in git until somebody answers. If a held deck's slides are already gone, the
prune says so loudly and carries on — stopping would jam every later run.

## What happened to a deck after it went out

`state/insights.jsonl`, written by `scripts/insights.py` on its own daily
schedule. Three days after a deck posts it records reach, saves, shares and
interactions, keyed on the media id kept in the deck folder.

It reads. It never decides. Nothing in the pipeline may import it and it may
import nothing from the pipeline — `tests/test_insights.py` enforces both, because
a number that quietly starts choosing hooks is how invariant 11 stops being true.

It needs one permission added to `IG_ACCESS_TOKEN` that posting does not need
(`instagram_manage_insights`, or `instagram_business_manage_insights` on an
Instagram-login token). Until then the job fails daily and prints the steps.
Decks published before this existed carry no media id and cannot be measured.

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
or shares for somebody else's account.

For **this** account it does, and that is worth saying plainly so the warning
above is not read as "the number is unobtainable". @suresilly is the owner of
its own posts, and `scripts/insights.py` now reads the real saves, shares, reach
and interactions three days after each deck goes out, into
`state/insights.jsonl`. The metric a model invented is free from a token this
repo already holds. It is a ledger to read, never an input to a gate — see
invariant 17.

Those files were written by a model and labelled as verified, and some of this
engine's copy rules came from them. Evidence that is real, with sources, is in
`references/strategy.md`.

---

## The rules that must not be broken

They are in `AGENTS.md`, and each one is there because it was a shipped defect.
The short version: no text inside mascot artwork, gates abort rather than warn,
a harvested post is a seed and never a source, old decks are a blocklist and
never material, a citation is proved against a library catalogue before a model
can put an author's name on a slide, and there is one entry point with one state.
Two more since: what we publish is measured and the measurement never decides,
and the public host is not the archive.
