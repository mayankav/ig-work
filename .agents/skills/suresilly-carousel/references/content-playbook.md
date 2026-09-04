# @suresilly — Content specification

This is the target for both manual and automatic posts. It replaces the old
ranked hooks and claimed viral results. Those claims had no adequate evidence.
Do not use old decks or on-topic examples as material for a model prompt.

## 1. Start with a real moment

Choose a familiar action or tension involving another person. Describe what
a camera could see. A subject such as anxiety or habits is not a scene.
The scene must have a clear relational purpose: words to use with someone,
a choice about a relationship, or an action that helps that interaction.
Do not add an unrelated person merely to pass this rule.

Keep the scene specific. Do not claim to know the reader's childhood, motives,
condition or diagnosis. A possible explanation must remain a possibility unless
the source supports a stronger claim.

The cover shows the action or tension. The subtitle adds a useful promise or a
clear reframe, with at least two content words the headline did not use.
Pattern names are optional. If a plain label helps, explain it on slide 4 as
our shorthand. Do not put it on the cover or present an invented label as a
medical fact. A proved field term and an invented label are not the same thing.

## 2. Build the useful part before the cover

Before drafting nine slides, require:

1. A short line the reader can say or send, under 20 words.
2. One small action that works without an app, a search or a purchase.
3. A save card that makes sense without the other slides.

Use a fill-in bracket only where the reader needs to supply a detail. The
instruction must work at the reader's own time and place. A specific scene is
not a reason to force the reader to act at the writer's chosen hour.
If the tools have no clear use, reject the idea before drafting a cover.

## 3. Give each slide one job

| Slide | Job | Required content |
|---|---|---|
| 1 | Recognition | Familiar action or tension; useful subtitle |
| 2 | Cost | What this costs; understandable without slide 1 |
| 3 | Supported explanation | Source-backed finding and its application; no repeated claim |
| 4 | Meaning | What the finding means here; optional plain shorthand |
| 5 | Words to use | A condition under When; actual speech under Say |
| 6 | Action | One small move with a usable trigger and setting |
| 7 | Choices | Three small options; choose one |
| 8 | Save card | Standalone words and action from earlier slides; no new claim |
| 9 | Recipient | One specific kind of person to send it to |

Say contains speech, not directions to the reader or a researcher's explanation.
Do not insert a citation into words the reader is told to say. Print the source
finding once. Later slides apply it rather than repeat it.

The internal name and sustain field names remain for file compatibility.
They do not require a named pattern or a different slide order.

## 4. Evidence and repair

bibliography.py owns citation selection and source text. The writer returns
the supplied citation ID; it never invents an author, title or year.
The claim cap is 18 words, shared by prompts, production checks and tests.

A real book and a matching term are not proof of the full claim. Each claim
needs a support record identifying the source passage and what it supports.
If support is missing, reject the claim or use an already-supported alternative.
Do not make a general finding into a diagnosis of the reader.

Repair failed fields, keep clean work, and run every check again. Three unchanged
fault signatures stop repair. Equal fault counts alone do not show that the
same problem persists. No style override may bypass image or safety checks.

## 5. Variation and measurement

Code chooses variation through writer.draw_axes; the model writes within it.
Do not ask a model to choose a proven viral hook or to rank its own ideas.
Do not load old decks into prompts. They are only a blocklist for copied work.
Prompt examples must stay off-topic: parking, dentists, library books or bikes.

Useful enough to save or send is a product aim, not a reach guarantee.
Do not claim that a format, label or emotion guarantees engagement.
Report actual saves/reach and shares/reach at a consistent post age. Missing
data remains missing. insights.py stays separate from generation; results do
not choose the next post.

## Release status

This specification is not evidence that every rule is implemented.
See docs/reliable-posts-status.md for the current implementation and test gaps.
Source support, full tool validation and failed-field-only repair still need
release proof. Passing a cover check does not establish content quality.
