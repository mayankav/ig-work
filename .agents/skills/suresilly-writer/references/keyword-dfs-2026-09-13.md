# What people search for, and what the standouts do

Keyword research and a depth-first dig on 2026-09-13, done by ten research agents: one ranked search demand, one checked the hashtag and search rules, seven dug one keyword cluster each, and one checked every proposed change against craft.md and the refused lists. The owner asked for it because "we have a weak hashtag game". The full reports are not in the repo; this is the distilled record. No other page's lines are copied here or into craft.md (rule 1).

## The method

It is adapted from a YouTube research method (Jake Trinder's niche search tree) to Instagram:

1. **Your niche → search terms.** Rank what people type, with a number and a source for each.
2. **Search term → top posts.** Instagram's keyword pages load logged out at `instagram.com/popular/<keyword-slug>/`, and each one lists the top items with view counts.
3. **Top post → its account, and the accounts shown next to it.** These are the channel and its recommendations.
4. **Account → its standout.** A standout is a post with at least 3x the account's usual likes or views, or its most-liked visible post.
5. **Depth first.** Take one branch all the way to its standouts before opening the next. Close a branch when it goes off-niche (memes, hustle, dating advice, sad-quote spam) or only repeats a pattern already logged. Move to the next search term only when every useful branch is exhausted.
6. **Judge every lesson against craft.md.** It is NEW, ALREADY, or CONFLICTS. Drop anything on the refused lists.

Limits we hit: Instagram shows a login wall after about 6 direct fetches from one machine, so give each researcher about 6 and let search snippets, Threads and Pinterest do the rest. Google suggestions from this machine lean Indian. Most accounts' typical numbers were not visible, so "standout" often means the top-ranked post rather than a proven 3x.

## What people search (seen 2026-09-13)

Instagram tag pages now show a reels count, which is far larger than third-party post counts. Compare numbers only within one source.

| Search | Demand seen | Fit |
|---|---|---|
| #childhoodmemories | 37M reels (Instagram); 6.8M posts (best-hashtags) | high, but the tag is mostly 90s-toy meme reels |
| best friend quotes | Google's top suggestion; #friendshipquotes 4.1M reels | high |
| #momquotes | 2.5M reels, against 551K for #mumquotes (4.5x) | high; mostly mothers writing about their kids |
| self love quotes | 3rd Google suggestion; #selflovequotes 2.6M posts | high, crowded with therapy talk |
| relatable quotes | suggested with "deep", "about life", "in english" | high |
| #nostalgia | 22.7M posts | medium |
| #siblings, #sisters | 21.1M and 53.1M posts; #sisters about 7x #grandma by weekly use | high |
| grandma quotes | suggestions for granddaughter, grandkids, "death" | high; much of it is grief |
| #relationshipquotes | 3.45M | medium; crowded by sad-quote pages |
| #dadquotes | 93K reels | high fit, low demand |

Grief runs through the family searches ("mum in heaven", "missing grandma"). "Small things" on Google means a novel, so it is the wrong search for us.

## Hashtags and search, the facts

- **Five is the cap.** @creators announced it on 18 Dec 2025. Hashtags in comments count toward it. `tidy_caption` already keeps five.
- **Hashtags label the topic. They do not grow reach.** Mosseri said so in Feb 2025 and again in Jul 2026. Instagram says a few targeted tags beat many generic ones, and irrelevant tags can hurt distribution.
- **More tags did not mean more reach.** Metricool (Jun 2026, n=24.4M posts) found posts with hashtags got about a third fewer views; that is correlation only. Standouts told the same story. Global English creators used 2 to 5 specific tags. India-style quote mills used 17 to 24 generic ones. The count did not track reach.
- **What search reads.** Instagram's Transparency Center (Jun 2026) lists username, profile name, hashtags and suggested keywords. Mosseri adds captions and comments (Jul 2026). Public posts from professional accounts can appear on Google since 10 Jul 2025, so the caption should name its subject in plain words.
- **Alt text.** The Graph API takes `alt_text` (up to 1000 characters) on each image container, including carousel children, but not on the carousel parent. `instagram.py` does not send it yet.
- **Our old sets were the weak part.** #tinytruths, #tinypoems and #suresilly have almost no posts. #family, #love and #home are catch-alls of 200M to 2B.

## What the dig confirmed we already do

Several lessons came back ALREADY, which is the best news in the dig:
- **Recognition beats recited comfort.** On one kindness account, a line recognising a hidden hard week got 4.7M views; the same account's post of stock comfort phrases got 817K. This is our "name the hard part before the comfort".
- **Big feeling, small sentence.** The grandparent-grief standouts (4.9M, 4.1M, 3.3M views) were a few flat words each. The heaven-and-angel lines sat in the low tier.
- **The line travels without the page.** One sibling text went viral on two accounts: 41.6M views on one, and 23.4M on a credited repost.
- **Send, don't tag.** Friendship standouts had comments at about 0.3% of likes, so they spread by sends. Our named send line is the clean version of "tag your bestie".

## What we took (all in craft.md or write.py)

| Lesson | Evidence | Where |
|---|---|---|
| Letter mode: "you" can be the person the reader sends it to, so the post is their note | about 9 standouts across friendship, siblings and love (the biggest: 41.6M views on a sibling letter) | writer, plus an editor line so the pass keeps it |
| With a partner, sibling or roommate, the second half may be the running joke of sharing a life | the couple-comic accounts (3M and 5.5M followers); numbers per post not visible | writer; no example on purpose, so it can't be copied |
| A hard week gets no promise that it passes | 2 posts in the kindness cluster | writer, next to the grief rule |
| Name the person once in the caption, plainly, never as a dedication | Mosseri says search reads captions (Instagram's own ranking page lists hashtags and names, not captions); Google indexes public posts | caption rule |
| Hashtags: 3 to 5 from the topic's list, never branded or catch-all (first set to 3; the owner asked for more, and no evidence favours 3 over 5) | Instagram's own statements; standouts used 2 to 5 | caption rule, `write.TAGS`, telegram's "hashtags off" note |
| The two example send lines are gone from the caption rule: the send line is written fresh, and one that could sit under any post is not finished. Porch light, spare key and oil join the do-not-reuse objects | the baseline copied "send this to the one who still checks your oil" word for word, and a sample after a "never copy" line still reused "save this for the next hard week" | writer |
| People: a best friend who moved away, a sister | 7.1M views on a 3K-follower account; #sisters about 7x #grandma | `write.PEOPLE` |
| Shapes: last times you didn't know were the last time (replaces "things we lose while growing up"); looking after someone who looked after you; three one-liners | nostalgia and friendship clusters; evenings run 7 one-liners a week on 5 shapes | `write.SHAPES` |

## What we refused, and why

- **Refused for our voice.** The first group was engagement bait: tag your sibling, drop a heart, "double tap if this resonates", "remember this?". The second was voice-breakers:
  - therapy words ("healing journey", "you are enough")
  - dedications ("this one's for all the...")
  - the abstract turn ("we don't miss the thing, we miss the feeling")
  - heaven and angels
  - rhyming couplets
  - 17 to 25 tag boilerplate
- **A countable number** ("eighteen years at home, two visits a year"). Its best evidence was a percentage post, and it invites countdown urgency.
- **A group send line** ("send this to the old class group"). It breaks the one-person send test, and two of its three examples were tag bait.
- **A two-person question and answer.** The editor strikes "a question then its own answer", and the obvious fill is a famous illustrator's own lines (rule 1).
- **Most proposed people:**
  - "a parent or grandparent who has died": about one post in twenty would be a death, and "a grandparent" already reaches grief when it fits
  - "a younger sibling", "your old class", "living alone for the first time", "the one who looks after everyone": thin evidence
- **"The dull win", "the mirror", "opposite habits", "running disagreements".** Close to therapy talk, only fit some people, or repeat the partner rule.
- **Writing for Mother's Day and Father's Day.** A calendar rule is close to the "trend windows" we refused on 2026-09-12, and the next one is months away.

## What the samples showed after the change

`ab_write.py` ran on the same briefs, before and after.

- **Hashtags.** Before, every caption carried branded or catch-all tags: #tinytruths, #suresilly, #family, #home, #love. After, gpt-oss-120b and qwen3.8-27b each wrote 3 tags from the topic's list, and every send line was new and specific.
- **The mum list on gemini-3.7 went wrong twice.** It still copied the brief's example save line, and it found only one fitting tag. Both were fixed: the example send lines came out, the parents list got mother-side and son-side tags, and the rule now fills up to 3 tags.
- **The slide rules are untested on Gemini.** Letter mode, the grin and hard weeks got no Gemini run, because all three Gemini models hit their 20-a-day free quota. Read the next posts with the list below.

## Watch the next five posts

1. **Copying.** Oil, porch light, "hard week" or "tonight" in slides or captions, the same send line twice, or one sentence shape in three of five posts.
2. **Drift to sad.** The new shapes lean toward endings. If more than one in five last slides is about death, absence or a "last time", that is too many. "Far away" must not quietly mean dead.
3. **Search copy in captions.** A dedication, the person's word used twice, a tag from outside the list, or a letter post where "you" switches between the recipient and the reader.

## Open for the owner

- **A parent's side?** The biggest mum and dad searches come from parents watching their own children grow up. PEOPLE has no entry from the parent's side. Adding one widens the audience but fails "a 16-year-old should nod".
- **Keywords in the profile name.** Instagram lists the profile name as a search signal, so it should carry the words people search.
- **Alt text on each slide.** The API supports it and `instagram.py` doesn't send it yet.

## Round 2: the owner's own carousel and image pages

The owner turned down reels and pointed back at the pages they had shared. They post carousels and single images and have big followings, so the dig was run again from those 8 pages: poetsphere, poet.circle, best.memory__, black_thoughtss_, therelatablewall, hugmymind.hmm, hustlingtortoise and me_and_my_old_monk. It found 16 standouts, from 1.5K to 236K likes.

- **Hashtags: 15 of 16 standouts had none.** The one exception, poet.circle's 161K single, had 3. Big pages grow on followers and sends. We have no followers, so tags still label our posts for search, and 3 to 5 stays. Nothing shows more tags helping.
- **Big hits are single images or long carousels.** hustlingtortoise's two 100K+ hits are single images. poetsphere's are 15 to 18 slides. Our cap is 9, because Telegram's `redo images` takes one digit. That is a format question for the owner.
- **Access tip.** `instagram.com/p/<id>/embed/captioned/` shows likes, the full caption and the tags logged out, after `/p/<id>/` hits the login wall.

Taken, after a second contradiction check:
- **One-liners about 15 words, 25 at most.** 3 of 3 black_thoughtss_ singles ran 7 to 12 words.
- **The send line names a habit most readers can pin on one person they know.** This replaces "one thing only they do", which pushed toward private details and contradicted "not private ones only one family would recognise".
- **A list shape: small things you did without thinking as a kid that take nerve now,** told as what you did, never as advice. poetsphere's 236K list spread by saves.

Refused:
- **Asking for both a send and a save.** poetsphere does it on every post, so it is probably a template. Measure it in insights first.
- **A "chain of small chances" shape.** It is strong (124K and 101K), but it fits only a partner or a friend, and `draw()` pairs a shape with any person.
- **"After naming what someone lacked, show what they did alone".** The obvious fill is the circulating text itself, and it drifts sad.
- **The owner's "if you don't know X, you know nothing about Y".** In the hard wording it is a hook formula and a tribal split, both on the refused list. So the shape describes the idea without its words: "an everyday thing everyone thinks they already understand, seen new through one small moment most people have lived". Five test one-liners went through the real writer and editor, one each for mum, a friend who moved away, a sister, a hard week and a grandparent. They opened five different ways, none used a "you don't know X until Y" frame, and each reframed an ordinary thing: a bruised peach, a weather app, an unlocked bedroom door, an early night, a refilled plate. The shape replaced its near-duplicate, "the best version of an everyday thing is a surprisingly small answer", so one-liners still draw from 8 shapes. The shape reaches the model only on the evening it is drawn, and there is no example sentence for it anywhere.

## The format note (for the owner, not the writer)

On every keyword page we walked (about 100 top items), the results were quote reels: text over video and music. Carousels were almost absent from keyword search. That is a format decision, not a writing rule, so it is not in craft.md.
