# Silly the Donkey — Character Bible

The single source of truth for what Silly looks like. The fenced blocks below go into the prompt
whenever new artwork is made — see `GENERATION_PROMPTS.md`, which is how the current 165-pose
library was produced. Editing prose outside the fences is safe; editing inside a fence changes
every pose made from here on.

> Day to day you do not generate anything. Poses come from `library/`. This file matters when you
> add a sheet, or when a new pose comes back looking off-model.

The file is split deliberately into **identity invariants** (never vary — this is what makes him
the same donkey every time) and **variable slots** (vary every slide — this is where the variety
comes from). Keeping wardrobe and props strictly out of the invariants is what lets Silly wear a
hat without becoming a different character.

---

## 1 · Identity invariants

Sampled directly from the four original style sheets in `style_refs/`.

| Element | Specification |
|---|---|
| Species | Stylised cartoon donkey, flat-vector, short rounded proportions with a large head |
| Build | **Full body**, standing upright: head, torso, two arms, two legs, tail |
| Body fill | Flat medium green `#3C965A`, no gradient, no outline |
| Muzzle | Large rounded warm-cream patch `#FAD2AA` with two dark oval nostrils |
| Belly | A matching cream `#FAD2AA` oval on the chest |
| Eyes | Large white ovals with dark pupils, sitting under the brow bar |
| Brow | **One thick solid black bar** across the forehead — the deadpan signature |
| Mane | Dense black `#141414` corkscrew curls: a rounded tuft on the crown and a wide strip down the back of the neck |
| Ears | Two tall pointed ears, green with a slightly darker green inner |
| Hooves | Small solid black `#141414` shapes on all four limbs |
| Tail | Thin green tail with a black tuft at the tip |
| Aspect | Roughly 0.54 wide to tall. The renderer sizes him by **height**, never width |

```IDENTITY
A stylised cartoon donkey character named Silly, drawn as a flat vector illustration with
short rounded proportions and a large head.

Body and head are flat medium green (#3C965A) with no outline, no gradient and no shading.
The muzzle is a large rounded warm-cream patch (#FAD2AA) with two dark oval nostrils, and a
matching cream oval sits on his chest.
Large white eyes with dark pupils, under one thick solid black bar across the forehead as a
single heavy eyebrow - this deadpan brow is a defining feature.
His mane is dense black (#141414) corkscrew curls: a full rounded tuft on top of the head and
a wide strip of the same curls running down the back of the neck.
Two tall pointed ears, green with a slightly darker green inner.
Small solid black hooves on all four limbs, and a thin green tail with a black tuft at the tip.
```

### The second donkey

Scenes with two characters use a **grey** partner, not a second green one. Identical in every
respect — shape, cream muzzle, cream belly, black curly mane, black brow bar, black hooves —
except the body colour.

| | Body colour |
|---|---|
| Silly | `#3C965A` green |
| The other one | `#757A77` soft neutral grey |

The grey reads apart from Silly at feed size, sits clear of every slide background, and lets a
slide show "you" and "them" without labelling either. The grey donkey is never named and has no
character of his own — he is whoever the slide is about.

### Framing — full body, standing

He is drawn as a complete standing figure. This is what makes posture possible at all: the
previous art was head-and-shoulders only, so every slide looked identical.

```FRAMING
Framing: the complete character standing upright, facing the viewer. Head, torso, both arms
with hooves, both legs and the tail are all fully visible with clear empty margin on every
side. Nothing is cropped by the edge of the frame.
```

### Rendering style

```STYLE
Rendering style: clean flat vector illustration, bold simple shapes, generous negative space,
mid-century modern children's-book aesthetic. Completely flat colour fills with no gradients,
no cast shadows, no drop shadows, no ambient occlusion, no 3D shading, no texture, no outlines
around the body. Crisp hard edges. High-resolution raster artwork.
```

### Negative lock

The guard against the defect that made the previous pipeline unusable — caption text baked into
the artwork. Never weaken this block.

```NEGATIVE
Absolutely no text of any kind anywhere in the image: no letters, no numbers, no words, no
captions, no labels, no titles, no watermarks, no signatures, no logos, and no speech bubbles
or thought bubbles containing writing.
Exactly one single character - never a grid, sheet, row or collage of multiple poses or
variations.
No frame, no border, no panel, no vignette, no drop shadow.
The background must be one completely flat uniform solid magenta (#FF00FF) - never green,
because the character himself is green - filling the
entire canvas edge to edge, with no gradient, no texture, no pattern, no vignette, no
horizon line, no props resting on a ground plane, and no shadow cast onto the background.
```

---

## 2 · Variable slots

Four axes. They describe how to *write a pose* — used when adding a sheet, and used again by
`library.py`, which matches the same four things in a slide's `**Mascot:**` brief against the
poses already on disk. One vocabulary, both ends.

| Slot | What it carries | Examples |
|---|---|---|
| `expression` | The emotional read. Do the eyes and mouth first — they carry the slide. | deadpan and unimpressed · wide-eyed panic with a single sweat drop · eyes closed in a serene smile · eyebrows raised in dawning realisation |
| `posture` | Whole-body stance and gesture. This is what the full-body build exists for. | slumped forward, both hooves over the eyes · one hoof raised mid-point, leaning in · arms crossed, weight on one leg · both hooves thrown up in a shrug · turned away over one shoulder · sitting down, legs out |
| `wardrobe` | Clothing. Optional — plenty of slides want him plain. | rumpled cardigan · tiny round reading glasses · knitted scarf · sweatband · bathrobe |
| `props` | One object, held or adjacent. Keep it to one; two reads as clutter. | a chipped coffee mug · an open yellow book · a tiny clipboard · a wilting houseplant · a phone held face-down |

### Writing a good brief

- **Expression and posture are required. Wardrobe and props are optional** — reach for them when
  the slide has a concrete situation to depict, skip them when the copy is abstract.
- **Describe behaviour, not emotion labels.** "both hooves over the eyes, shoulders collapsed"
  renders; "feeling overwhelmed" does not.
- **One prop maximum**, and it must be nameable as a single object.
- **Stay inside the invariants.** Never specify a body colour, a mane style, an outline, a
  background, or a camera framing — those are locked above and the script appends them itself.
- **The brow bar and the mane are never optional.** They carry the character's identity. A pose
  that hides either one stops reading as Silly.
- **Nothing that implies text.** No newspapers, no signs, no letters, no labelled bottles, no
  laptops showing a screen. This is the most common way text sneaks back into the artwork.

### Default poses by slide role

Used when a slide omits a `**Mascot:**` line. These name real files in `library/`; the live
values are in `poses.json` under `role_default`.

| Role | Pose |
|---|---|
| hook | `deadpan` |
| agitation | `clutching` |
| source | `reading` |
| value | `explaining` |
| script | `palm_out` |
| cheat | `holding_board` |
| cta | `welcoming` |
