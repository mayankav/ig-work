# Where the craft rules come from

Deep read on 2026-09-12: about 90 public skills, plugins and prompt packs, cloned and read in full by three researchers, one each for writing craft, automated pipelines, and named experts' methods. The full reports are not in the repo; this is the distilled record.

## The verdict

No public skill reaches 5 of 5 for this page, and none should be installed. Nobody has written the skill for this genre: a 4:5 text-on-image post, two-half lines under 30 words, warmth without sentiment, a send test instead of a call to action.

Owner's correction, 2026-09-13: the goal is growth (saves, sends, likes), not originality. The "byline test" (could ten other pages have posted this) that several of these skills and our first draft used was dropped. Our own teardown shows the biggest hits are plain universal lines. What survived from the craft skills is what raises recognition and sendability: one shared detail, a warm picture ending, no preaching, no bait.

Every anti-AI-writing skill was built for essays or LinkedIn and thinks good prose is cold. Every carousel skill is a marketing funnel. Every poetry skill named "poetry" is something else (a Python package manager, a Tang-poetry quiz, haiku git commits). Anthropic has published no prose-craft skill.

Nothing public runs a whole content loop either. The full-pipeline plugins (socialforge, OpenNolan, claude-ig) are agency-scale, gate-heavy and lean on paid image APIs. Our publish, approval, render and editor pass are smaller than any of them, and ours is the only publisher found with an idempotency record.

## What scored 4 of 5, and what we took

| Source | Who | Taken into craft.md |
|---|---|---|
| [EveryInc/draft-review-kit](https://github.com/EveryInc/draft-review-kit): `sedaris`, `vonnegut`, `hemingway`, `mom`, `guardrails` | Every's editors | replace every generic noun with the actual thing; don't signal the feeling; write to one person and name them (Vonnegut 7); start as close to the end as possible (Vonnegut 5); the mom read; the aphoristic balance close as a tell |
| [jwynia/agent-skills](https://github.com/jwynia/agent-skills): `flash-fiction`, `endings`, `cliche-transcendence`, `joke-engineering`, `lyric-diagnostic` | J Wynia, runs a novel on these skills | (list-the-defaults-then-refuse-them was dropped on 2026-09-13: shared examples raise recognition); first and last image are a pair; never "realised" in a last line; weak endings named; end slightly before full articulation; "what would someone who hates this genre never say" |
| [haowjy/creative-writing-skills](https://github.com/haowjy/creative-writing-skills): `failure-modes.md` | Jimmy Yao, cites craft sources | big feeling, small sentence; no stock gestures; no sentence after the moment saying how heavy it was; no comforting realisation in the same post as a grief; two details beat five senses |
| [lyndonkl/claude](https://github.com/lyndonkl/claude): `ladder-of-abstraction` | Roy Peter Clark's ladder via Hayakawa | no particular, no slide; the close descends through an object the reader already met; never jump from the cold cup to "love is showing up" in one step |
| [blader/humanizer](https://github.com/blader/humanizer) v3 (also installed locally) | most-used writing skill | a tell counts in proportion to how rarely a careful writer would do it on purpose; re-scan the rewrite for the tells that survive rewrites |
| [sergebulaev/instagram-skills](https://github.com/sergebulaev/instagram-skills): `ig-humanizer` V3 | Creative Content Crafts | the over-correction guard: did the edit create fragments, flatten the voice, or add a fact; edit in proportion |
| [Nanako0129/sepia](https://github.com/Nanako0129/sepia) `narrative-pass` §1, §3, §5 | measured against StoryScope (arXiv 2604.03136) | the machine ending is agency plus acceptance plus growth, end one beat earlier; cut narrator generalisations; a character may name a feeling plainly, the narrator may not |
| [artemnovitckii/content-skills](https://github.com/artemnovitckii/content-skills) `anti-ai-writing` | no credentials | the ladder vague, specific, concrete, lived, as an aim, not a gate (the "refuse under concrete" line was dropped on 2026-09-13) |

Also worth a look but not taken: `murage/poetry-writing` ("if the last line could appear on an inspirational poster, rewrite it"; a machine-generated library, so sentences only), `croeder/prose_lint` (names "the bow" and "a sentence shaped for a plaque"), `stop-slop` (17K stars; its "cut quotables" rule would delete the line our page exists to produce).

## Methods with no skill yet

The experts researcher found no SKILL.md for Klinkenborg, Roy Peter Clark's 55 tools, Stephen King, McPhee, Lamott, Didion, poetry craft (line break, the turn, concrete image), greeting-card writing, or Bernbach. The rules from them that fit one line per slide are already paraphrased into craft.md: one thought per line; the strongest word at the end of the line; second draft is first draft minus a tenth; the one-inch picture frame; report the room and let the reader supply the grief; the volta one or two slides before the end, never on the last; greeting-card "me-to-you" sendability and the ban on superlatives.

## Where public advice disagrees with our bar

- **Quotable lines.** Three skills say cut them. Our page exists to produce one screenshot line. The reconciliation: a quotable line on abstract nouns is the tell; a quotable line with a cold coffee in it is the post.
- **Adverbs and adjectives.** Hemingway-style skills ban them wholesale; our strong examples depend on "cold, standing up". Keep the narrower rule.
- **"It's not X, it's Y".** Four skills ban the shape; the genre runs on it. Ours: only with a concrete Y.
- **Show, don't tell.** Sepia's data: humans plainly name a feeling 29% of the time, models 8%. A plain "she was scared" mid-story is human. Telling the reader how to feel is not.
- **The opening.** Essay skills say no hook; carousel skills say open loop. Ours is a promise under 12 words.

## What we refused, again

Hook and title formulas, power words, urgency, contrarian-as-strategy, tribal splits, comment-for-DM tricks, withholding to farm comments, self-seeded comments, watermark stripping, competitor scraping (claude-ig `ig-competitor`, sergebulaev `ig-hook-extractor` via Apify), embedded product plugs (the Vyral skills, a "star this repo" line in sergebulaev's root skill), 100-point rubrics and zero-tolerance gates, browser automation of Instagram's web UI, paid image generation for new mascot art.

## Two things worth doing later, not now

1. **Honest win-ranking in insights.** socialforge's `ingest_performance.py` is the only public "insights improve the next post" loop that is honest about noise: a sample floor, a margin of 1.5x the median, `no clear wins` when nothing clears it, and every win labelled measured or anecdotal. About twenty lines in `scripts/insights_report.py`. The owner reads the report by hand first; the seed does not.
2. **A prompt eval loop.** Anthropic's `skill-creator` runs with-skill and baseline on the same prompts and grades them. Our `ab_write.py` is the small version. If brief changes become weekly, a fixed set of ten seeds and a side-by-side read is enough.
