---
name: suresilly-writer
description: Write, judge and tune the @suresilly tiny-truth posts (lowercase relatable lines about family, friendship, growing up and love, with a small green donkey). Use when reviewing a post or a Telegram card, when a post reads weak, when changing the writer prompt, or when comparing writer models. The craft rules live in suresilly/craft.md and this skill says how to use them.
---

# suresilly-writer

One page, two posts a day, one line worth sending to someone. The writer is a model behind `suresilly/write.py`; its brief is `suresilly/craft.md`. This skill is for the human or agent who judges the output and tunes the brief.

Read `AGENTS.md` first. Rule 1 (our own words only), rule 5 (a better prompt before a new gate) and the Telegram approval flow all bind here.

## The goal

Growth: saves, sends, likes, followers. Not originality. We never copy another page's words (rule 1), but a true line that most people recognise is the whole point, even if ten pages could have said it. The evidence is in `docs/pivot/quote-pages-teardown.md`: the biggest hit measured, 364K likes, was a plain line about a school friend who lasted. The 2026-09-13 dig (`references/keyword-dfs-2026-09-13.md`) corrected one claim. The relatable wall's pinned 100K post is a different image, and its text could not be read logged out. Its "not everyone has a family that checks in" carousel got 1.5K likes on Instagram and 2.1K shares as a copy on Facebook.

What each metric comes from:

- **Sends and shares:** the reader thinks of one person. Validation lines ("not everyone had...") and "send this to the one who..." endings.
- **Saves:** lists worth coming back to, and lines worth screenshotting. Slide 1 must promise the list is worth keeping.
- **Likes and reach:** one-read recognition. Nothing to decode, nothing private.
- **What loses reach:** engagement bait (Meta penalises it), preaching, therapy talk, anything that needs a second read.
- **Search:** hashtags and the caption only tell Instagram what the post is about. They bring no reach on their own (Mosseri, 2025 and 2026). Three to five specific tags from the topic's list in `write.TAGS`, and the person named once, plainly, in the caption.

## The bar

A post passes when all five are true. Judge slides in order, then the caption.

1. **Slide 1 is a promise, not a label.** Under 12 words, 9 is better, no full stop, and a stranger needs to see what follows.
2. **The recognition test.** Would most readers see their own life in each line on one read? A line only one family would recognise is too narrow. A line with no detail at all is forgettable. One shared detail per line.
3. **The send test.** Name the one person the reader would send it to. If you cannot, the post has no target.
4. **The save test, for lists.** Would a reader keep this for a bad day or to send later? If the items are pleasant but disposable, the list will get likes and no saves.
5. **The end is warm, not preachy.** A picture or one plain warm sentence a reader would screenshot. Never a lesson, never a question, never a follow ask.

Things that fail on sight: "tag a friend", "comment yes", "let that sink in"; a lecture in the last line; therapy words; a private detail most readers cannot picture; a line that needs a second read; a donkey holding a mug under a line with no mug in it; a made-up or branded hashtag (#tinytruths) or a catch-all one (#love, #family); a send line that could sit under any post.

Three lenses for when a post passes and still feels off:

- **The mum read.** Someone smart, sixty, not on Instagram much. Which line would she nod at without getting it? Which one would she forward?
- **The screenshot test.** Which single slide would someone crop and post to their story? If none, the post has no peak.
- **The one-person test, again.** Say the name of the person the last slide is for. If it is "everyone", rewrite it for one.

## Judging a Telegram card

The card shows the slides and asks for `approve`, `disapprove`, `redo all` or `redo images 2,4`. Silence for an hour posts it.

- Words weak, pictures fine: `redo all`. A redo rewrites the words and picks new poses.
- Words fine, one donkey wrong: `redo images N`. The words stay.
- Both fine but not ours: `disapprove`, then fix the brief (below) before the next slot.

## Turning rejections into rules

Do not guess why a post was rejected. After `disapprove` or `redo all` the bot asks "Why did this one go?" in two taps: the area (hook, a line, the ending, topic, format, tone, caption, donkey, the whole thing, nothing to learn), then the exact cause inside it, then the slide when that matters. Every cause carries one sentence the writer is told next time (`telegram.AREAS`), so a rejection is never interpreted. `why: your own words` is always allowed and kept verbatim. Each answer is one line in `docs/craft-watchlist.md`, committed by the workflow. `redo images` records "donkey" by itself.

The count decides what happens:

1. First time: it sits on the watchlist. Nothing changes.
2. Second time the same reason: add it to the editor's strike list in `craft.md`, with the two offending lines as the weak examples.
3. Third time: add the word to `BANNED` in `write.py` or the shape to the writer's rules.

"Nothing to learn" is a real answer and counts for nothing. The brief grows only from what the owner rejected twice, or from research the owner asked for (below).

The next post already sees it: `write.py` puts the last two weeks of answers into the brief as "recent notes from the owner", each as its one instruction with the rule "change that one thing and nothing else", and the last two weeks of our own posts as a do-not-reuse list (objects, openings, people, sentence shapes). That is how one rejection changes tomorrow morning without a rule, and how the examples in the brief cannot turn into a template.

## Tuning the brief

The brief is `suresilly/craft.md`. Above `## editor` is the writer's; below it is the editor's second pass. `write.py` reads the file at import and fills `{{BANNED}}` from the Python list.

1. Write the rule as a sentence a writer would obey. Add a weak and a strong example only if the rule is about a line, and pick the example from a topic and an object the page rarely uses, so the model cannot echo it. After a change, read five posts in a row and check that no object, topic or sentence shape from the examples appears in them. Examples that get copied are worse than no examples.
2. Run the comparison script (below) on the three formats. Read the slides, not the JSON.
3. Watch for the model copying the rule's shape on every line. That happened with "they did X, so I could Y"; the variety rule in the brief is the fix.
4. Run `python -m pytest -q`. Commit the brief change on its own.

Never add a check to `write.py` for something a sentence in the brief can do.

## Comparing writers

```bash
.venv/bin/python .agents/skills/suresilly-writer/scripts/ab_write.py --models gemini-3.8-flash gemini-3.5-flash --formats list story
```

It writes one post per model per format through the real writer and editor, prints the slides, and saves the JSON under `.agents/skills/suresilly-writer/out/`. The free tier gives each Gemini model 20 requests a day. The 429 body names the quota: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, measured on 2026-09-13. The count resets at 12:30 IST, and production draws on the same count. One job is 2 requests, so run a few jobs one at a time, not the full matrix. Keys come from `.env.local`. Groq models work too (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`). Delete `out/` before committing; it is scratch.

Measured on 2026-09-12: Gemini 3.5, 3.6, 3.7 and 3.8 Flash all write to the bar with the current brief; 3.8 is a little sharper and fails with "high demand" often, so `llm.py` tries 3.8, then 3.7, then 3.5. Groq's gpt-oss-120b copies formulas and writes clock times on every line; it is the backup, not the writer.

## Researching what people search

Run this when the owner wants to know what works in a topic, or before adding a person, a shape or a hashtag list. The last run is `references/keyword-dfs-2026-09-13.md`.

1. **Rank the searches.** Give every term a number and its source: an Instagram tag page (a reels count), a hashtag site (a post count), or Google and YouTube suggestions. Never write down a number you did not see.
2. **Dig one term at a time, depth first.** Start with the top posts for it; `instagram.com/popular/<keyword-slug>/` loads logged out. From a strong post, go to the account behind it and the accounts beside it. In each account, find its standout: 3x its usual likes, or its most-liked post. Finish a branch before opening the next, and move to the next term only when every useful branch is done.
3. **Write down mechanisms, never lines.** Rule 1 holds for research too: nothing another page wrote goes into craft.md.
4. **Mark every lesson** NEW, ALREADY or CONFLICTS against craft.md, and drop anything on the refused lists.
5. **Get the edits checked.** Give the proposed edits to someone who did not write them and ask for contradictions first. On 2026-09-13 that check cut about half the proposals, and it was right to.
6. **Tune as above:** run `ab_write.py`, and read both the slides and the captions.

Each researcher gets about six direct Instagram fetches before the login wall. Search snippets, Threads and Pinterest can do the rest.

## What we learned from other skills, and from search

Three reference files:

- `references/skill-teardown-2026-09-12.md`: four public "viral content" skills read in full and compared. None is for our genre, all are unsourced, and about a dozen rules transferred.
- `references/craft-sources-2026-09-12.md`: about 90 skills, plugins and prompt packs read by three researchers. No public skill reaches 5 of 5 for this page. The eight that reached 4 are listed with what we took from each, where public advice disagrees with our bar, and what we refused.
- `references/keyword-dfs-2026-09-13.md`: what people search in our topics, the facts about hashtags and search, and a depth-first dig through seven keyword clusters. It records what we took, what we refused, and what to watch in the next posts.

Do not install any of them. Two carry embedded product plugs, several scrape other accounts, and rule 1 forbids feeding another page's posts to the writer. The sentences worth having are already in `craft.md`.

## Adding donkey poses

`docs/new-poses.md` has the ChatGPT prompt, the keep-or-redo checks, and the import steps. Every pose needs a one-line note in `mascot.GROUPS`; the tests check that every file has one.
