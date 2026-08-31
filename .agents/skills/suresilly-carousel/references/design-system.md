# @suresilly — Visual Design System

The executable form of this document is `scripts/render.py`. If the two ever disagree, the code
is what ships — fix the code, then fix this file.

---

## 1 · What we are aiming at

Three reference grids set the bar. We borrow **traits**, never artwork:

| Reference | Trait borrowed |
|---|---|
| Sticker-kit carousel packs | A tight palette applied as **full-bleed colour blocks**, one repeating background motif, one deliberately rotated element per frame |
| Flat-illustration tile sets | The character is a **compositional element** — it shares the frame with the type and sits in the layout, never a corner sticker |
| Single-character comic grids (`_labadessa`) | **One character, endlessly re-posed** plus one owned colour is what makes a nine-up grid read as a single body of work |

The test is the **contact sheet**, not the single slide. `build.py` writes `contact_sheet.png`
next to every deck for exactly this reason. If the nine tiles do not read as one body of work,
the deck is not done.

---

## 2 · Canvas

| Property | Value |
|---|---|
| Size | 1080 × 1350 (4:5 portrait) |
| Side / top margin | 108 px |
| Footer reserve | 150 px |
| Export | PNG, `device_scale_factor: 1` |

---

## 3 · Colour — the block rotation

Each theme is a complete token set, so nothing is ever hardcoded per slide. Fourteen are
selectable — nine saturated grounds and five papers:

| Slot | Themes |
|---|---|
| `bleed` (saturated ground) | `terracotta` `charcoal` `indigo` `ochre` `cobalt` `midnight` `teal` `plum` `wine` |
| `paper` (light ground) | `oatmeal` `cream` `clay` `blush` `mist` |

`sagetint` is defined but out of the rotation — it is the one paper close enough to Silly's green
to be a judgement call, so it ships only when explicitly asked for. `forest` is kept only so old
scripts naming it still parse; it is the retired green ground, and colour words that used to reach
it now resolve to `teal`.

The rotation started as four grounds and three papers. That was too narrow — consecutive decks
kept landing on the same colour, and whole hue families (a blue that reads as blue, purple, wine,
teal) had no theme at all, so asking for them silently resolved to something else. Every theme
added since clears the same contrast bars the originals do, enforced by `tests/test_layout.py`:
body ink ≥ 4.0× on its own ground, accent ≥ 2.8×, and no ground that shares the character's hue
without enough tonal separation to keep him visible.

### Choosing a deck's colour

A deck commits to **one saturated (`bleed`) theme and one light (`paper`) theme** for the whole
carousel — never nine different colours. `scripts/render.py::deck_palette()` picks the pair:

- **The user names a colour.** Write it in the script header as
  `**Palette:** <colour> / <colour>` (either order — bleed and paper are told apart
  automatically). Plain English is fine — `reddish`, `pinkish`, `minty`, `deep blue`, `dark red` —
  not just the technical theme names. Every colour word resolves through `COLOR_ALIASES` in
  `render.py` to one of the vetted themes; nothing invents a new hex value. That is deliberate —
  every theme already has its `ink` chosen for contrast against its `ground`, so a casual colour
  request can never land on a background too harsh, too saturated, or too close to Silly's own
  green for the type (or Silly himself) to read. Naming only one half (`**Palette:** blue`) fills
  the other half by round robin, below.

  Modifiers are read, and the longest known phrase wins: `blue` → `cobalt`, `deep blue`/`navy` →
  `midnight`, `slate blue` → `indigo`, `light blue` → `mist`. Unlisted modifiers degrade to the
  base hue rather than failing, and hex codes in the line are ignored, so the legacy
  `**Palette:** Oatmeal #F5F4F0 / Charcoal #2B2B2B` form still parses.

- **No colour named** (and what `--random-palette` does). Round robin, not random-random: `deck_palette()`
  reads `palette_history.json` (same pattern as `mascot/usage_history.json`) and picks whichever
  bleed/paper option was **least recently used across the whole history**, so a run of unprompted
  decks cycles through every theme before any colour repeats. `build.py` writes the chosen pair
  back to that file after a clean build. Note it is a true LRU, not a fixed-size recent window —
  a window looks equivalent and is not: with a four-deck window and nine themes, the fifth deck
  sees the first theme fall out of the window and picks it again, so themes five through nine
  never ship.

**A `**Palette:**` line that resolves to nothing aborts the build.** It used to fall through to
the round robin, which is how `**Palette:** deep blue` shipped a terracotta deck with no sign
anything was wrong. Asking for a colour and silently getting a different one is worse than a
failed build. A line that resolves *partly* still builds — the half that resolved is honoured —
but prints what it ignored.

Do not hand-pick a hex value or add a theme for a one-off request — extend `COLOR_ALIASES` to
point at an existing theme, or add a theme and let `tests/test_layout.py` prove it clears the
contrast bars, so the legibility guarantee still holds.

| Token | Purpose |
|---|---|
| `bg` | full-bleed slide background |
| `ink` | primary type |
| `soft` | secondary type |
| `accent` | the `[[keyword]]`, badges, bullets, slide number |
| `card` / `cardink` | card fill and the type **inside** a card |
| `rule` | footer hairline |
| `eyebrow` | the small uppercase label |
| `ghost` / `grid` | the oversized slide numeral and the grid ground |

`cardink` exists because a theme's body ink is not automatically legible on that theme's card —
on the charcoal theme the card is cream and its type must flip to dark.

### Assignment (deterministic, by slide role)

| Slide | Theme | Why |
|---|---|---|
| 1 Hook | `terracotta` | Scroll-stopper. This is the tile the feed sees. |
| 2 Agitation | `oatmeal` | Breathe after the shout. |
| 3 Source | `charcoal` | The authority beat. A bright cream quote card on black. |
| 4–7 Value | `oatmeal` / `sagetint`, alternating | Swipe rhythm without noise. |
| 8 Cheat sheet | `sage` | Colour-codes "this is the one you save." |
| 9 CTA | `terracotta` | Bookends slide 1 and closes the loop. |

---

## 4 · Type

Two families, both variable, both embedded as TrueType and both **verified at render time**.

| Role | Family | Size | Notes |
|---|---|---|---|
| H1 (hook) | Fraunces | 102 px | `opsz 144`, weight 700, tracking −0.032em |
| H2 | Fraunces | 74 px | `opsz 144`, weight 700 |
| CTA headline | Fraunces | 78 px | |
| Body | Inter | 36 px | `opsz 32`, line-height 1.52 |
| Sub (under an H1) | Inter | 37 px | `soft` colour |
| Bullets | Inter | 34 px | |
| Card text | Inter | 33 px | uses `cardink` |
| Eyebrow | Inter | 20 px | 0.30em tracking, uppercase |
| Handle / number | Inter / Fraunces | 20 / 25 px | |

Three rules the renderer enforces so they cannot be violated by accident:

1. **`opsz` is set explicitly.** Both fonts are variable with an optical-size axis that defaults
   to its *smallest* value (Fraunces 9, Inter 14). Left alone, headlines render in the text cut —
   muddy, low contrast. Display type pins `opsz 144`, body pins `opsz 32`.
2. **`font-weight: 100 900` is declared** in `@font-face`, otherwise the weight axis is
   unreachable and every bold is a faux-bold smear.
3. **The render aborts if a font did not load.** `document.fonts.check()` runs on every slide.
   A silent fallback to a system sans is a failed deck, not a warning.

### Inline markup

| Syntax | Renders as |
|---|---|
| `[[word]]` | Accent-coloured Fraunces italic with a hand-drawn underline. **One per slide, on the emotional pivot word.** |
| `*text*` | Italic |
| `**text**` | Bold |

Emoji are stripped automatically — the system is type and shape only, and emoji render as tofu.

### Auto-fit

Every text block is measured after layout and shrunk in 3% steps until the column fits its box.
Copy length is therefore a *quality* concern, not a breakage risk. Aim for ≤ 220 characters of
headline + body per slide anyway; auto-fit rescues overflow, it does not make dense slides good.

---

## 5 · The recurring motifs

Exactly three, and no more — restraint is what makes them read as a system.

1. **Grid ground.** A faint 54 px hand-drawn-feeling grid, radially masked toward the top-right.
2. **Raster grain.** A 128 px noise tile generated locally with numpy and embedded as a PNG data
   URI, overlaid at low opacity. Real raster, no SVG filters.
3. **One rotated element per slide.** The badge, a card, or the callout pill — never two. This is
   the "sticker" energy, kept to a single beat.

Plus the oversized ghost numeral bleeding off the top-right corner, which is the page-number
device that ties the deck together.

---

## 6 · Composition

The copy hangs from a fixed top line at 150px — it is not vertically centred. Centring left
about 330px of dead space above the eyebrow and gave the composition nothing to sit on. The CTA
slide is the exception and stays centred, because it has no reading order to establish.

The oversized slide numeral sits top-right at 132px. It used to be 300px, which made decoration
the single loudest element on the slide, louder than both the headline and the character.

### Three mascot modes, chosen automatically

**Stacked** — the default for a tall pose. Copy runs the full measure, the figure stands below
and right of it. This replaced a side-column layout: flanking a 600px figure squeezed the line
to about 34 characters while empty space sat beside it. Comfortable measure is 45 to 75.

**Banner** — a wide pose (lying down, or any two-donkey scene). Copy stacks above, the figure
runs centred along the bottom. Height is capped at 360px, and the canvas reserves the height the
banner *actually* renders at, never an estimate.

**Side column** — only the before/after script template, whose cards are already inset. The
reserved strip is measured from the pose actually chosen.

| Slide role | Figure height | Rotation |
|---|---|---|
| Hook | 680 px | −2° |
| Agitation | 620 px | +3° |
| Value | 600 px | +2° |
| Before/after script | 520 px | −4° |
| Source | 520 px | −3° |
| Cheat sheet | 470 px | +3° |
| CTA | 560 px | 0°, centred |

He sits behind the text and the footer, and his hooves land on the footer rule.

### Filling the lower left

Stacking creates a void under the copy. Two things occupy it deliberately:

- **The grid ground is masked to the lower left**, not the top right where the headline already
  is. Texture goes where the space is.
- **A soft tonal ellipse under the hooves.** Without it the figure floats; with it he is standing
  on the slide. Each theme carries its own `ground` tone, heaviest on charcoal.

`tests/test_layout.py` checks every pose in every slot for overlap, banner height and canvas
overflow. Both layout bugs it now guards against shipped silently and were caught only by eye.

### The pose library

`../mascot/library/` holds **180 poses**, generated as 6-up sheets on a magenta backdrop and cut
out by `scripts/import_poses.py`. See `_contact_sheet.png` for all of them.

The count is not fixed any more. `scripts/poses_flux.py` adds poses for free through
Cloudflare Workers AI, offline, into the same import and matting path. Generated green
drifts washed-out against the palette, so check a new pose on a contact sheet beside the
existing ones before importing — the contact sheet is the judgement, not the slide.

| | Count |
|---|---|
| Single Silly | 135 |
| Two donkeys — green Silly plus a grey partner | 30 |
| Mirrored copies, for the opposite direction | 24 |
| Wide poses, laid out as a banner | 35 |

`library.py` matches a slide's `**Mascot:**` brief to a pose by word overlap, prefers originals
over mirrored copies, and never repeats a pose inside one deck. Two-donkey scenes are only
offered when the brief actually mentions two people.
