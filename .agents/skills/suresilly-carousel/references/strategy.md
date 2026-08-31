# Strategy — how a carousel gets made

This is the rules layer. It decides everything. The language model only writes words.

Read this before changing the pipeline. It replaces the old "I'm feeling lucky" topic-bank
flow, which shipped the same deck under different hooks.

---

## 1 · The rule

Every post starts from a real moment that has never been used. No text is ever copied from an
earlier post. If we cannot make something new, we post nothing.

Earlier posts are a blocklist. Nothing is read out of them to build a new one. They never enter
a model prompt, not as material and not as examples.

**Manual runs and automatic runs obey this equally.** There is one entry point and one set of
state. A person running the pipeline on a laptop draws from the same queue, passes the same
gates, and records the same fingerprint as the twice-daily job. See section 7.

---

## 2 · Where moments come from

| Source | Status | Why |
|---|---|---|
| Bluesky firehose and search | **Primary** | No key, no account, no card. About 1.8M posts a day, of which roughly 6,500 are usable first-person moments. We need 60. |
| Our own Instagram comments | **Growing** | Lowest volume, highest quality, and the only source where people consented. Its share should rise as the page does. |
| Bluesky firehose | **Measured and rejected** | Zero usable moments in 1,767 posts. See below. |
| Reddit | **Not used** | Free tier is non-commercial only, and their terms ban automated access by any method, browser automation included. |
| Everything else | **Not used** | Quora, X, YouTube comments, Tumblr, review sites and public datasets are each blocked by terms, licence, or ethics. See the source log at the end. |

Bluesky's terms are silent on bulk reading. That is permission by omission, not permission.
The source is a config value so it can be swapped without touching anything else.

### Do not use the firehose

Bluesky also publishes an open stream of everything posted, about 1.8 million a
day. It looks like the better source: no phrases to guess, no assumption about
what people are feeling this week, and the filters left to do the deciding.

Measured, it produces nothing.

| Source | Posts | Usable | Rate |
|---|---|---|---|
| Phrase search | 293 | 5 | 1.7% |
| Firehose, 4 minutes | 1,767 | **0** | under 0.06% |

An unbiased sample of the internet is bots, sport, links and other languages.
**Bluesky's search index is doing the work, not our filters.** This was tried,
measured and removed; do not try it again without a number that beats 1.7%.

**We never publish anyone's words.** The fact of waking at 2:17am is free to use. The person's
sentence is theirs. Every moment is rewritten before use and the original is discarded. Log that
the discard happened; keep no raw corpus on disk.

---

## 3 · The eight layers

Cheap and exact first. Expensive and fuzzy last. Any layer stops the run. No layer starts one.

| # | Layer | Owner | Job |
|---|---|---|---|
| 0 | Source list | Rules | Only read from allowed places. Crisis communities are never fetched, so their content never needs filtering. |
| 1 | Banned subject filter | Rules | Nine word-pattern families that must never become a post. |
| 2 | Shape filter, then composer | Rules, then a model | Is this a real moment a camera could film? Then use it as a SEED and invent our own. |
| 3 | Shuffled queue | Rules | Deal the next moment. A dealt moment never returns. |
| 4 | Safety judge | Gemini | May a public post be built on this moment at all? |
| 5 | Writer | Gemini | Name the pattern, plan the argument, check the chain, write nine slides. |
| 6 | Adversarial critic | Any vendor that did not write it | Build the strongest case against publishing. |
| 7 | Rule gates | Rules | Is it new, does it hold together, is the source real. |

Layers 4 and 6 use different companies on purpose. The writer never checks its own work.

### Layer 0 — Source list

The deny list of crisis communities is checked **before** the request is made, not after.

The search phrases decide the entire topical range of the account: every post we
write comes from something one of them found. They are not chosen by taste.
`scripts/probe_phrases.py` searches a candidate, runs the results through the
same screen a real run uses, and reports the share that survives. A phrase that
finds nothing is dropped whatever it sounded like.

Two things to know when reading it. A sample of 25 cannot support a verdict, so
it takes 100. And the screen measures shape, not subject: a post can be first
person, filmable and about a browser tab. The rate filters, the printed examples
decide. A phrase at 2% that finds real evenings beats one at 8% that finds noise.

### Layer 1 — Banned subject filter

Families: suicide, self-harm, eating disorders, medication, abuse, minors, psychosis,
substances, clinical claims.

Three rules that make it work:

- **Saying no costs nothing.** There are thousands more moments. A miss can hurt a real person.
- **Negation never clears a hit.** "I would never hurt myself" is dropped like the opposite.
- **Normalise first**, so disguised spellings still match.

Llama Guard runs after the patterns, free on Groq, to catch meaning with no keywords.

### Layer 2 — Shape filter

| Must have | Must not have |
|---|---|
| First person | Second-person advice |
| 8 to 30 words | A clinical label |
| One clock time, body sensation, or place | More than one abstract word (burnout, healing, journey) |

Score the anchors. Keep anything at 5 or above with at least one hard anchor. Rank on tension
first, because the score measures whether a moment can be filmed and not whether it is about
anything: "tired, 9pm, a car" scores 7 and the judge refuses it, "I read her message four times"
scores 5 and the judge allows it.

Then invent our own moment from it, and throw the post away.

**Throwing the post away is also what makes ideas repeat, so the invented moment is checked
against the invented moments before it.** All that survives a seed is one subject from a closed
list of eight, plus a short phrase. About 1,100 posts a run collapse into that, and a model with
no memory writes its favourite sentence. Two different seeds produced the same bed at the same
11:45pm twice and both shipped, because uniqueness was tested on the SEED and nothing looked at
the output. `compose.repetition_faults` now refuses a moment that repeats an earlier one's words
or its shape, and `compose.variety_brief` forbids the recently used postures by category before
the model starts. See invariant 19 — and note the cause worth remembering: the prompt's own
worked example was being copied verbatim into the moments.

**The post is a seed, not a source.** This changed after the rewriting approach failed for a
week. Rewriting somebody's sentence has to satisfy four demands at once — keep the evening, drop
the words, drop the name, stay publishable — and they fight each other. The step that hid the
name deleted the person with it, and what came out ("someone was locked out, I let them in") had
nothing in it to write about. The judge refused it, correctly.

So the post now supplies only the subject and the shape of the problem. We invent a different
hour, a different room, a different sentence carrying the same ordinary trouble. Two consequences,
both good:

* Nothing of theirs is republished, because nothing of theirs is used. The privacy question stops
  being a balancing act and becomes one mechanical check: no run of seven words survives.
* The moment can be BUILT to fit. A harvested sentence either happened to contain a clock and a
  feeling or it did not, and most did not — 7 of 8 candidates in the last live run were about
  devices. An invented one is asked for both, so it clears the shape filter by construction.

Reading their name is fine. The post is public and we are only looking at it. The rule is about
what we WRITE: the published moment carries no name at all, whether copied or invented. That is
one rule instead of two, and it is stronger than either.

### What a deck is FOR, and the evidence behind it

Added 2026-08-30, after the first live deck read as unshareable. Everything here
has a source, because the repo's own `research/` folder turned out to be partly
invented and some of the copy rules came from it.

**Lead with the NAME, not the scene.** Orvell, Kross and Gelman, PNAS 2020:
across 1,120 book passages matched against roughly 250,000 Kindle highlights,
always-true "you" ("eventually you recover from heartbreak") appears in 26% of
highlighted passages against 3% of controls — an odds ratio of 12.86. One
person doing one thing at one time runs the other way, 29% against 44%, odds
ratio 0.41. Packard and Berger, Psychological Science 2020, split the pronoun
across 4,200 chart rankings: the "you" that works points at somebody in the
reader's life, and the "you" cast as the actor in a scene was not significant
once controlled (p = .142). Every hook this engine wrote was the losing variant.

**A name is the sendable unit.** Mosseri says sends per reach is the ranking
signal. The bird test spread where the Gottman research behind it did not,
because "bird" survives a retelling and "verbal bid for emotional connection"
does not. A name can be sent as an accusation, a confession, or a diagnosis of
a third person; a stranger's Tuesday gives a sender nothing to point at.

**Slide 2 is a second cover.** Mosseri, 17 October 2024: a carousel that nobody
swipes is re-served starting from the second frame. So slide 2 is read cold, by
people who have not seen slide 1, and boilerplate there throws away the
platform's one structural gift to the format.

**Concrete words, general claim.** Hu, Pilgrim, Zhao and Hills, QJEP 2026: 15M
tweets and 50,517 Reddit posts, concreteness predicts sharing. That is about
imageable WORDS, not about a particular invented situation — the two get
confused, and the difference is the whole argument. "Bowl washing" is concrete
and general. "You stood in the kitchen at 11pm" is concrete and particular.

**The saved card carries no clock.** Carousels are a saves format — Metricool,
24M posts: nine times the saves of a single image — and the card is the slide
with a second life. A step that says "start the timer at 2:50pm in the kitchen"
is an instruction for a person who does not exist, and it destroys the one
thing the slide is for.

**Not relief.** Berger and Milkman, JMR 2012, roughly 7,000 articles:
low-arousal deactivating states suppress sharing. Every deck this engine built
declared its core emotion as Relief. Relief is where a deck ENDS.

**Ask for the save, never for the like.** Metricool, 24.4M posts: asking for
saves moves saves +92%, asking for comments +203%, and asking for likes moves
likes −4.9%. One post gets roughly one action out of one person, so there are
two asks in a deck and no more: send on slide 9, save in the caption.

**Caption length is genuinely unsettled.** The study behind "under 30 words
wins" (Socialinsider, 9.1M posts) measures likes and comments over followers
and excludes saves and sends, which are the two behaviours this page is built
for — and the largest accounts in this niche run captions of a couple of
hundred words. So the schema allows a range and the prompt asks for a shape,
rather than forcing either. What it no longer does is force a 200 character
FLOOR, which is why the caption used to be the whole deck retold underneath it.

### Layer 3 — Shuffled queue

Random picking repeats fast. With 24 moments and one post a day, a random draw repeats inside a
week. So we deal from a shuffled deck instead.

- The order is random. The repeat is impossible.
- A moment is **claimed before writing starts**, so a crashed or repeated run cannot post twice.
- The moment's id is hidden in the caption, so we can ask Instagram whether it already posted.
- Queue empty means stop. We never recycle.

### Layer 4 — Safety judge

Told it is a gate, not a helper, and that refusing costs nothing.

- It must write the strongest reason to refuse **every time**, even when it allows.
- Unsure means no. A timeout, bad output or low confidence are all refusals.
- Mined text is data, never instruction. Text that tries to talk to the judge is itself a refusal.

### Layer 5 — Writer

**Plan first, then write.** Call one returns a nine-line outline: what each slide does, what it
hands to the next, and which earlier slide it needs. Code checks that chain before any prose
exists. This is what makes the sequence make sense.

- **Sources cannot be invented.** The model returns an id. Code substitutes the real citation.
  There is no field in which it can type an author's name.
- **2,688 structural settings** are drawn per run, changing the lens, the order of the advice and
  the shape of the saved card. Changing the temperature changes words, not thinking. Changing the
  instructions changes thinking.
- **Voice without content.** The examples we show it are about parking tickets and overdue
  library books. It copies the rhythm and cannot copy the subject.
- **Repairs keep the chain.** A failed slide is rewritten against the same outline.

### Layer 6 — Adversarial critic

Counsel for the prosecution, in ten named categories. Never asked to rate out of five, because
models score near chance at "how good is this".

- **It can veto. It cannot approve.** Code computes the verdict.
- **Every objection must quote the deck.** Unquotable ones are deleted in code. More than two
  deletions and its approval is not trusted either.
- **A poisoned canary runs every time.** One of fourteen deliberately bad decks is slipped in.
  If the critic passes it, publishing freezes on its own.
- **One critic, not three.** Judges that learned from the same internet vote the same way.

### Layer 7 — Rule gates

Measured thresholds, not guessed. Our hand-written decks overlap each other at 0.01. The broken
generated decks overlapped at 0.71 to 0.90.

| Gate | Limit |
|---|---|
| Deck word overlap, 5-gram Jaccard | abort at 0.15 |
| Single slide overlap, 3-gram Jaccard | abort at 0.35 |
| Longest identical run, after brand phrases are masked | abort at 8 words |
| Word-frequency similarity | abort at 0.45 |
| Comparison set | last 30 decks, plus index matches. Constant cost forever |

Story gates:

| Gate | Fails when |
|---|---|
| Same moment | Slide 1's time or place is missing from slides 2, 8 and 9 |
| Same thread | An advice slide does not connect back to slide 3 |
| Nothing new late | Slide 8 adds an idea slides 4 to 7 do not have |
| Correct scene | A detail belonging to a different moment appears anywhere |
| Second cover | Slide 2 does not stand alone as a hook |
| Real source | The citation is not on the approved list |

No word-similarity models. They cost a 200 MB install in CI and work worse here, because every
deck is the same topic. Plain word counting separates cleanly in about 5 milliseconds.

---

## 4 · What the model is not allowed to do

| Model does | Model does not do |
|---|---|
| Rewrite the moment so nobody's words are republished | Think up the moment |
| Reject broken candidates | Rank which candidate is most original |
| Write the nine slides | Choose the angle |
| Argue against publishing | Decide that something ships |

Two measured reasons this line sits where it does:

- **Models cannot invent enough.** One model, one brief, 4,000 attempts yields about 200
  different ideas. We need 700 a year. Adding a second company buys almost nothing: models from
  different families cluster as tightly as models from the same family.
- **Models cannot judge novelty.** They score 53% where chance is 50%. Ideas a model called more
  original turned out to be less original. Novelty is decided by arithmetic, not opinion.

---

## 5 · Where the AI comes from

| Role | Provider | Free limit | Note |
|---|---|---|---|
| Safety judge, writer | Gemini | ~250 to 1,500 requests a day | Key already in the repo. Free tier trains on our prompts |
| Critic, guard models | Groq | 1,000 requests a day | No card. Does not train on our data |
| Fallback writer | Groq | same | Different company, different bad day |
| Last resort, and the third opinion | Cloudflare Workers AI | shares the 10,000 neurons/day account allowance with `poses_flux.py` | `llama-3.3-70b-instruct-fp8-fast`. Why the critic can always be somebody who did not write the deck |

Three vendors, not two: `PROVIDERS = (gemini, groq, cloudflare)` in `llm.py`, tried in that
order. The third is not spare capacity — a model recognises its own work and rates it higher, so
a deck written by the only configured vendor could never be judged independently.

A run makes roughly six model calls, so about a dozen a day across the two scheduled runs. Every
option is over-provisioned many times over. Choose on quality and independence, never on
headroom.

If Gemini fails, try Groq; if Groq fails, try Cloudflare. If all three fail, **post nothing**.
There is no content bank fallback: a bank of pre-written variants is recombination, and
recombination is the thing we removed.

---

## 6 · One run

| Step | Action | Owner | If it fails |
|---|---|---|---|
| 1 | Check the kill switch and that local state matches the remote | Rules | Stop |
| 2 | Deal the next moment and claim it | Rules | Queue empty, email, stop |
| 3 | May a post be built on this moment? | Gemini | Discard the moment, stop |
| 4 | Write a nine-line outline | Gemini | Re-plan once, then stop |
| 5 | Check the outline holds together | Rules | Re-plan once, then stop |
| 6 | Write the nine slides | Gemini | Try Groq, then stop |
| 7 | Fix mechanical faults in code | Rules | Cannot fail |
| 8 | Build the case against publishing | Groq | Block. Never publish unjudged |
| 9 | Novelty and story gates | Rules | Rewrite the failing slide, twice at most |
| 10 | Render, record the fingerprint, retire the moment | Rules | Retry next run |
| 11 | Post, then email the images | Rules | Recover next run using the caption id |

The fingerprint is recorded at step 10, when the deck is **rendered**, not when it is posted. A
deck that was built and never published still counts as used.

---

## 7 · Manual runs and automatic runs

There is **one entry point**. The scheduled job and a person on a laptop run the same code
against the same state.

| Mode | Command | Draws a moment | Records it | Posts |
|---|---|---|---|---|
| Scheduled | `run.py --publish` | yes | yes | yes |
| Manual, live | `run.py --publish` | yes | yes | yes |
| Manual, build only | `run.py --no-post` | yes | yes | no |
| Preview | `run.py --dry-run` | no | no | no |

Five rules keep both honest:

1. **Any run that produces a deck consumes its moment.** Building without posting still retires
   the moment and still writes a fingerprint. Otherwise a manual build could be repeated later.
2. **`--dry-run` writes nothing.** It peeks at the head of the queue and renders to `.preview/`.
   It never touches `carousels/` and never marks anything used.
3. **Stale state aborts the run.** Before drawing, fetch and compare against the remote. If local
   state is behind, or `state/` has uncommitted changes, stop and say so. A manual run with an old
   queue is the one way a duplicate could still get out.
4. **The claim is pushed before generation starts.** If two runs draw at once, the second is
   rejected, re-reads, and draws the next moment.
5. **The kill switch applies to both.** A repository variable halts everything, a manual run
   included.

---

## 8 · Watching an unattended system

| Alarm | Trip point | Meaning |
|---|---|---|
| Queue low | under 14 moments | Mining is falling behind |
| Gate rejections | above 40% over 14 runs | The writer or a model has drifted |
| Novelty creep | median overlap above 0.06 over 10 decks | Collapse begins as drift, not a spike |
| Judge always passing | above 95% over 20 runs | The critic has stopped judging |
| Canary passed | any | Publishing freezes automatically |
| Three failed runs | any | Kill switch flips on its own |
| Silence | no run for 26 hours | The scheduler itself is down |

---

## 9 · Honest limits

- **Both models believe the same myths.** Neither flags "cortisol dysregulation" as false,
  because both think it is true. Two companies fixes flattery, not shared error. The only fix is
  a hand-written list of banned claims that grows as we spot them.
- **Gates prove absence, not presence.** A writer optimising against a story check can pass it by
  sprinkling the right words. Gates prove a deck has no known defect. They never prove it is good.
- **Supply is silent on quality.** Shape is not interest. We can measure whether a moment is
  filmable. We cannot measure whether anyone cares.
- **Judge the contact sheet, not the slide.** Unchanged from AGENTS.md invariant 8.

---

## 10 · Source log

Checked against primary terms, not blog summaries.

| Source | Why not |
|---|---|
| Reddit | Free tier non-commercial only; terms ban automated access by any means; robots.txt disallows everything |
| Quora, X, YouTube comments, review sites | Barred by their terms |
| Tumblr | No content licence, and nothing may be stored beyond three days |
| Stack Exchange | Cleanest licence, but six new questions a year on the relevant site |
| Public datasets | Every one with real emotional depth is non-commercial, unlicensed, or scraped from real counselling sessions |
| Google Trends | API is alpha only; automated access breaks Google's terms |
| Search grounding | Returns the model's summary plus links, not people's actual sentences |
