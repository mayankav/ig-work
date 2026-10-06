# Hook playbook

Research run on 2026-10-06 (one agent, 39 sources, listed at the end). Use it when you write, judge or tune a cover, or the first 1.5 seconds of a Reel.

**Examples show the shape only.** Every number, clause and law in the examples is a stand-in. A real post takes its facts from `suresilly/facts.json` and nowhere else.

Confidence: **P** primary source or platform document · **K** creator claim, secondhand · **M** marketing blog. Fit: **C** carousel, **R** Reel, **B** both. "Leak" is the way the technique most often breaks the cover rule.

## The rules every hook obeys

1. **Hold back the payoff, never the topic.** The cover has one situation and one concrete anchor (a quote, a ₹ figure, a clause). The answer, the number or the script comes one swipe, or about 5 seconds, later. Too vague and too concrete both lose clicks (LeQuere, Loewenstein).
2. **Keep the promise exactly.** The post must give what the cover promised. A hook that is not paid off costs trust, and YouTube already enforces on it.
3. **Imply the question; skip the question mark.** A statement that leaves a gap beats a question in the large A/B data (22,743 tests). One older study found the opposite, so do not make it a law. The lint accepts either.
4. **Front-load; 14 words at most, two short lines, one idea.** Readers register about the first 11 characters of a line. Our approved covers are 14 words.
5. **Contrast of at least 4.5 to 1, type 90 px or larger on a 1080 px cover.** A grid tile is about 130 pt wide on a phone. Keep all text in the middle 3:4 of a 9:16 cover.
6. **Reels: picture, text and voice make one promise in the first 1.5 to 3 seconds,** and it must work on mute. Instagram now reports a skip rate (left within 3 seconds). Watch time, likes and sends per reach are the top signals.
7. **The cover must be sendable on its own.** People share without opening.
8. **Never fake it.** No invented story, no false alarm, no "comment YES" bait.

## The recipe

Line 1: the situation plus one anchor, 8 words or fewer. Line 2: a promise line, 6 words or fewer: "Here is what is." · "Here is how." · "Check it in 60 seconds." · "This one." · "We checked."

Name the technique in the post's JSON (`hook_technique`). The picker in `suresilly/hooks.py` chooses one per post so that no two posts in a row use the same one.

## The 26 techniques

| # | Technique | How it works | Example cover (payoff held back) | Fit | Leak | Conf |
|---|---|---|---|---|---|---|
| 1 | Calibrated info gap | Reader knows a little and misses the key fact | "Offer ₹6L. Credited ₹41k. / Where did the rest go?" | B | names the cause | P |
| 2 | Forward reference | Points at something it does not name | "Your notice period has one clause HR skips. / This one." | B | pointer with no anchor | P |
| 3 | Open loop | An unfinished goal pulls the viewer on | "Boss texted “Call me.” / Say this first." | B | the loop never closes | P |
| 4 | Payoff one swipe away | Situation and promise on the cover, answer inside | "Probation: 6 months. / What happens on day 181?" | C | verdict printed | P |
| 5 | Redaction | A key word is blacked out; the reader self-tests | "Quit early and you owe ₹____." | B | blank is guessable | M |
| 6 | Myth vs reality | Quote the belief, hold the correction | "“Notice period is a formality.” / Is it?" | B | correction printed | M |
| 7 | Contrarian claim | Challenges advice the reader was given | "Your first appraisal is not about your work. / It is about this." | B | claim has no support | K |
| 8 | Negation | Names a missing promise; each negative word added 2.3% clicks in 105k tests | "“We are like a family” is not in your offer letter. / Here is what is." | B | substitute shown | P |
| 9 | Specific count | A bounded, concrete number | "Your payslip has 9 lines. Only 3 matter." | C | items listed | M |
| 10 | Stakes (loss frame) | Shows the risk, holds the fix | "One missing PF entry costs years. / Check yours." | B | false alarm | P |
| 11 | Audience callout | Who, the condition, the promise | "First six months in? / Check one payslip number." | B | fits everyone | K |
| 12 | Time-boxed promise | "60 seconds" shrinks the effort | "Is your bond valid? / 60-second check." | B | takes longer | K |
| 13 | Cold open | Starts mid-moment, no greeting | Frame 1: phone buzzes, "Call me. Now." | R | an intro before the action | K |
| 14 | Pattern interrupt | An odd picture or sound in frame 1 | Frame 1: a payslip stamped WRONG | R | stunt unrelated to the post | M |
| 15 | Spot the error | A planted mistake the viewer hunts | "What is wrong with this payslip?" | B | too obvious | M |
| 16 | A vs B conflict | Two options in tension | "₹6L fixed or ₹7L “variable”? / Which is richer?" | B | winner named | K |
| 17 | Translation | Exact phrase, meaning held back | "“Per my last email.” / What it really means." | B | “= no” printed | M |
| 18 | Script as promise | Promises a copy-paste message | "The 3-line text to ask for your relieving letter. / Copy it." | C | script on the cover | K |
| 19 | Series cliffhanger | Part 1 ends unfinished | "Notice period, part 1. / Part 2 tomorrow." | B | part 1 is useless alone | P (mixed) |
| 20 | Loop ending | Last line completes frame 1; replays count | Ends "…your settlement arrives" and starts "late." | R | clips the payoff | M |
| 21 | Authority tag | Names the source: Act, clause, practitioner | "A labour-law clause most offer letters ignore. / Which one?" | B | source stays vague | M |
| 22 | Personal story | First-person mini story with a twist | "My first salary came ₹4,000 short. / HR replied in one line." | B | invented anecdote: never use | K |
| 23 | Three-part hook | Picture, text and voice give one promise in 1.5 to 3 s | Circled payslip line, "Line 6 is not salary", voice says it | R | layers disagree | K |
| 24 | Progress markers | Counters shorten the perceived wait | "3 clauses to check before you sign. 1/3" | R | no payoff | K |
| 25 | Awareness match | Unaware readers need the symptom, not the fix | "Your take-home is lower than your offer. / It has a name." | B | uses solution words | M |
| 26 | Second-chance slide 2 | Instagram re-shows an unswiped carousel from slide 2 | Slide 2 stands alone: "Still here? Check line 6." | C | needs slide 1 | P |

Technique 22 is on the list because it is common. We do not use it: it needs a real story, and rule 1 of `AGENTS.md` says our own words only.

## Techniques by area

| Area | Use these |
|---|---|
| Know your rights | 1, 2, 6, 8, 21 |
| Say this | 3, 12, 13, 18 |
| New rule | 1 (with a date), 10, 2 |
| You asked | 11, 6, 17 |
| Office dictionary, A or B | 5, 15, 16, 17 |
| You are not behind | 11, 25, 9 |

The picker uses this table. A technique used in the last 6 posts is skipped.

## What failed on test, and what we do about it

- **The answer sits on the cover.** The cover lint (`lint.cover_problems`) catches the payoffs we list. It cannot catch an answer it was not told about, so every script names its payoff in a `payoff` field.
- **The cover has no gap.** The lint wants a question mark, a blank, a typing indicator, or a promise line.
- **The promise is not kept.** Check by hand: cover says "Here is how." and slide 2 must be the how, with the exact words.
- **Every cover looks the same.** Two lines, a promise line each time, is the recipe. The *anchor* must change: a quote, a ₹ figure, a date, a clause number, a message.

## What we could not verify

- Any controlled study of cover or first frame against grid click-through or reach. Vendor figures (CTR 0.8% to 2.4%, +40% profile visits, "60% three-second hold gives 5 to 10 times reach") have no traceable source. Do not quote them.
- "1.7 seconds to stay or scroll" is a 2016 Facebook feed figure. People misattribute it to Reels.
- Hormozi, Hoyos, Kane and MrBeast came as secondhand summaries. The MrBeast document is leaked and unauthenticated.
- Instagram's recommendation-guidelines wording, and three papers (Nature, Sage, Wiley), were read through summaries.
- Word counts and type sizes (5 to 10 words, 60 to 100 px) come from design blogs, not tests.
- Pattern interrupt, redaction, spot the error and loop endings: no tests found. The mechanism is inferred.
- The evidence is news headlines (Upworthy, WeChat, Blendle), not Indian Instagram covers. Our own sends per reach, per technique, is the only test that counts. The insights job should record `hook_technique` next to each post's numbers.

## Sources

1. Loewenstein, curiosity gap: https://www.cmu.edu/dietrich/sds/docs/loewenstein/PsychofCuriosity.pdf
2. Kang, curiosity and the brain: https://neuroecon.berkeley.edu/public/papers/Psychol%20Sci%202009%20Kang.pdf
3. Ghibellini, Zeigarnik meta-analysis (2025): https://www.nature.com/articles/s41599-025-05000-w
4. LeQuere, too vague and too concrete: https://www.nature.com/articles/s41598-024-81575-9
5. Blom, forward-referring headlines: https://doi.org/10.1016/j.pragma.2014.11.010
6. Facebook, clickbait test: https://about.fb.com/news/2016/08/news-feed-fyi-further-reducing-clickbait-in-feed/
7. Scacco, curiosity wins clicks: https://journals.sagepub.com/doi/10.1177/1461444819863408
8. Qiu: https://onlinelibrary.wiley.com/doi/full/10.1002/acp.4195
9. Fang, question titles (22,743 tests): https://myscp.onlinelibrary.wiley.com/doi/10.1002/jcpy.70031
10. Robertson, negativity in headlines (105k tests): https://www.nature.com/articles/s41562-023-01538-4
11. Munger, null effects of clickbait: https://csmapnyu.org/research/academic-research/the-null-effects-of-clickbait-headlines-on-polarization-trust-and-learning
12. Molyneux, disappointment: https://scholarshare.temple.edu/handle/20.500.12613/393
13. Lai, self-referencing: https://www.researchgate.net/publication/271992279
14. Rothman, framing: https://www.researchgate.net/publication/14207305
15. Gal, loss aversion: https://myscp.onlinelibrary.wiley.com/doi/abs/10.1002/jcpy.1047
16. Wirz, cliffhangers: https://www.researchgate.net/publication/358520938
17. Hahn, cliffhangers: https://www.buffalo.edu/ubnow/stories/2023/06/hahn-cliffhangers.html
18. Ogilvy, headlines: https://swipefile.com/five-times-as-many-people-read-the-headlines-david-ogilvy
19. Schwartz, levels of awareness: https://selzee.com/eugene-schwartz-5-levels-of-awareness
20. Heath, Made to Stick (summary): https://medium.com/@piet.ruthven/summary-of-made-to-stick-by-chip-heath-and-dan-heath-bcfa566cf8db
21. Cialdini, Pre-Suasion (summary): https://growthsummary.com/book-summary/pre-suasion/
22. Hormozi, hooks: https://solopreneurcode.substack.com/p/how-i-write-hooks-that-actually-work
23. Hormozi, value equation: https://youngandprofiting.com/alex-hormozi-the-value-equation-how-to-make-offers-so-good-people-feel-stupid-saying-no-e199/
24. MrBeast notes: https://gigazine.net/gsc_news/en/20240917-mrbeast-youtube-production/
25. Hoyos: https://blog.kdcc.social/make-anything-go-viral-how-to-hook-and-reel-in-your-viewer/
26. Kane, Hook Point: https://sobrief.com/books/hook-point
27. Hook list: https://mustafaalfredji.com/hooks/
28. Mosseri on carousels: https://tech.yahoo.com/social-media/articles/why-instagram-carousels-sometimes-start-200811893.html
29. Instagram Reels guide: https://socialday.live/features/what-instagrams-new-reels-guide-actually-tells-social-marketers-to-do
30. Skip rate: https://www.socialmediatoday.com/news/instagram-adds-retention-insights-reels/758464/
31. Instagram ranking: https://about.instagram.com/blog/announcements/instagram-ranking-explained
32. Mosseri on signals: https://blog.hootsuite.com/instagram-algorithm/
33. YouTube clickbait enforcement: https://blog.google/intl/en-in/products/platforms/strengthening-enforcement-against-egregious-clickbait-on-youtube/
34. WCAG contrast: https://w3c.github.io/wcag21/understanding/contrast-minimum.html
35. NNg, first two words: https://www.nngroup.com/articles/first-2-words-a-signal-for-scanning/
36. Facebook video: https://www.facebook.com/business/news/updated-features-for-video-ads
37. Grid crop: https://nealschaffer.com/instagram-post-size/
38. Sharing without clicking: https://www.nature.com/articles/s41562-024-02067-4
39. Loops and views: https://routenote.com/blog/how-are-views-counted-shorts-tiktok-reels/
