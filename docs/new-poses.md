# Adding donkey poses

Generate new poses with ChatGPT, save the transparent PNGs in one folder, and tell Claude the folder. Claude crops and shrinks them, adds each one to a group in `mascot.GROUPS` with a one-line note, and the tests confirm every file has a note. On 2026-09-12, 22 were generated and 13 kept. The 9 dropped wore trousers or shoes, which made them look like a different character. Rule for new poses: green legs and hooves must show. A jacket, apron or hat is fine.

## ChatGPT setup

1. Start a new chat. Attach these four files from `suresilly/assets/mascot/`: `sitting.png`, `holding_heart.png`, `walking.png`, `presenting.png`.
2. Paste the prompt below. Change only the line after **POSE:**.
3. One image per request. Download as PNG.

## The prompt

```
The four attached images show one mascot: a small cartoon donkey. Draw the same
character in a new pose. Copy him exactly:

- body: flat green #429d5f, no gradients, no outlines, no shading
- muzzle and round belly patch: cream #fad8a6
- mane (short black curls), hooves, eyebrows, tail tip: near black #0e0e0b
- one thick straight unibrow, two white oval eyes side by side, each with one
  round black pupil, both eyes visible and level
- tall pointed ears, short round body, stubby legs, small tail
- same proportions as the references: head about half the total height
- soft painterly edges like the references, not crisp vector lines
- NO CLOTHES: no trousers, no shoes, no jacket, no hoodie, no scarf. bare green
  body with green legs and black hooves showing, exactly like the references.
  the only exception is a single item the POSE line names (an apron, a hat)

POSE: standing, holding a small flashlight pointed forward

Rules:
- full body, whole character visible, nothing cut off by the edge
- every element is drawn whole or not at all. no partial furniture, walls
  or floor. if an object cannot fit completely, leave it out
- only the donkey and at most one small object he holds. no scene, no
  background objects, no ground shadow
- no text, no letters, no logo
- transparent background, PNG
```

If ChatGPT will not do a transparent background, ask for "a flat solid background #ff00ff magenta" instead. Claude can cut that out.

## Checks before you keep an image

Keep it only if all five are true. Otherwise regenerate.

1. Two eyes, each with a pupil, pointing the same way.
2. Two front hooves, two back hooves, one tail.
3. One of the object, not two.
4. Nothing cropped by the edge.
5. Same green as the references, not greyer.

## Batch 1 (done 2026-09-12)

Save each as the file name shown.

| File name | POSE line |
|---|---|
| `flashlight.png` | standing, holding a small flashlight pointed forward |
| `wiping_hands.png` | standing, wiping his front hooves on a small yellow rag |
| `phone_call.png` | standing, holding a phone to his ear, listening |
| `holding_note.png` | standing, reading a small folded paper note held in both hooves |
| `hugging_pillow.png` | sitting, hugging a pillow to his chest, eyes half closed |

## Batch 2 (done 2026-09-12: 9 added, plus covering_ears, lunchbox, sneaking_cookie, holding_hands_out_rain)

`waving_from_car` was skipped: the body is cut off at the waist. A pose must show the whole donkey.

| Save as | POSE line |
|---|---|
| `carrying_bags.png` | walking, carrying two paper grocery bags, one in each hoof |
| `gift_box.png` | holding out a small wrapped gift box with both hooves, eyes closed, pleased |
| `hands_behind_back.png` | standing, both hooves behind the back, looking down, shy |
| `photo_frame.png` | looking down at a small photo frame held in both hooves |
| `tying_lace.png` | crouched, tying the lace of one small shoe on the ground in front of him |
| `umbrella.png` | standing under a small open yellow umbrella held in one hoof, looking up |
| `hugging_pillow_happy.png` | sitting, hugging a pillow to the chest, eyes closed, content |
| `hugging_pillow_sad.png` | sitting, hugging a pillow to the chest, flat tired eyes |
| `arms_crossed_casual.png` | standing, arms loosely crossed, small easy smile |

## Later batches (ideas for the next batch)

- `waving_goodbye_big.png`: standing, one arm stretched high, waving goodbye with a big smile
- `holding_letter.png`: holding an envelope with both hooves, looking at it
- `blowing_on_soup.png`: holding a small bowl with both hooves, blowing on it
- `looking_in_mirror.png`: holding a small hand mirror, looking into it
- `tucking_in.png`: bending over, pulling a small blanket up over nothing

Done in the first batch:

- `stirring_pot.png`: standing, stirring a small cooking pot with a wooden spoon
- `umbrella.png`: standing under a small open umbrella, looking up
- `carrying_bags.png`: walking, carrying two grocery bags
- `gift_box.png`: holding out a small wrapped gift box with both hooves
- `photo_frame.png`: looking down at a small photo frame held in both hooves
- `hands_in_pockets.png` and `shy_hands_tucked.png`: casual in a suit; shy in a hoodie
- `facepalm.png`: standing, one hoof over his face
- `hands_over_mouth.png`: standing, both hooves over his mouth, eyes wide
- `asleep_on_desk.png`: sitting, head down on folded arms, asleep
- `looking_at_watch.png`: standing, looking at a small watch on his wrist
- `tying_lace.png`: kneeling, tying a small shoelace
- `holding_plant.png` (asked for blowing on food, got a plant; kept)
- `arms_crossed_waiting.png`: standing, arms crossed, tapping one hoof
- `holding_key.png`: holding up a single small key, looking at it
