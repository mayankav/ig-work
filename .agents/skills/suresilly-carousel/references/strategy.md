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
| Reddit | **Not used** | Free tier is non-commercial only, and their terms ban automated access by any method, browser automation included. |
| Everything else | **Not used** | Quora, X, YouTube comments, Tumblr, review sites and public datasets are each blocked by terms, licence, or ethics. See the source log at the end. |

Bluesky's terms are silent on bulk reading. That is permission by omission, not permission.
The source is a config value so it can be swapped without touching anything else.

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
| 2 | Shape filter | Rules | Is this a real moment a camera could film? Then rewrite it and discard the original. |
| 3 | Shuffled queue | Rules | Deal the next moment. A dealt moment never returns. |
| 4 | Safety judge | Gemini | May a public post be built on this moment at all? |
| 5 | Writer | Gemini | Plan the argument, check the chain, then write nine slides. |
| 6 | Adversarial critic | Groq | Build the strongest case against publishing. |
| 7 | Rule gates | Rules | Is it new, does it hold together, is the source real. |

Layers 4 and 6 use different companies on purpose. The writer never checks its own work.

### Layer 0 — Source list

The deny list of crisis communities is checked **before** the request is made, not after.

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

Score the anchors. Keep anything at 5 or above with at least one hard anchor. Then rewrite the
moment and throw away the original.

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

We need about 4 calls a day. Every option is over-provisioned by 50 times or more. Choose on
quality and independence, never on headroom.

If Gemini fails, try Groq. If Groq fails, **post nothing**. There is no content bank fallback: a
bank of pre-written variants is recombination, and recombination is the thing we removed.

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
