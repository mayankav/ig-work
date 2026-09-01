#!/usr/bin/env python3
"""
The prompt is not a source of copy. No network.

Every failure this guards against is one that shipped. Of the seven decks on
disk when this was written, five carried a run of words lifted straight out of
the prompt that produced them:

  hallway              the filler in the example intention, in three decks,
                       including one set in a kitchen and one set on a bed
  cup to the sink      the example script, verbatim, in a deck about a bed
  action you can take  a question the prompt quotes IN ORDER TO FORBID IT
  found that leaving   a sentence the prompt quotes as a thing no person says,
                       printed inside a line the reader was told to say
  save this for the    the example caption ask
  phone face down      the example mascot prop

The three VOICE examples have always been about dentists, parking tickets and
library books, and not one word of them ever reached a deck. That is the whole
finding: an example set on the page's own ground IS a template, and an
off-subject one is not. The gate exists because a model cannot be asked to tell
the difference and counting can.
"""
import glob
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import writer  # noqa: E402

REPO = ROOT.parent.parent.parent

DECK = """### Slide 1 · Hook
- **Layout:** Template A
- **H1:** Bowl washing. You cannot sit down while the counter is [[full]].
- **Mascot:** A small donkey standing beside a low table.

### Slide 5 · Value Step 2
- **Layout:** Template C
- **H2:** The [[script]]
- **✅ Regulated Response:** "{line}"

## Caption
{caption}
"""


def run() -> int:
    failures: list[str] = []
    total = 7
    shown = writer.prompt_ngrams()

    # 1. A line lifted out of the prompt is refused. This exact sentence is in
    #    DRAFT_SYSTEM, as the example of an accent done right.
    lifted = DECK.format(line="The renewal has been open in a tab since Tuesday.",
                         caption="Nothing borrowed here at all.")
    if not writer.check_leak(lifted, shown):
        failures.append("LIFTED a line copied out of the prompt was allowed")

    # 2. Copy of its own is not.
    clean = DECK.format(line="The bowl is [[done]] and the night is finished.",
                        caption="Some words that appear in no example anywhere.")
    if writer.check_leak(clean, shown):
        failures.append(f"CLEAN original copy was called a leak: {writer.check_leak(clean, shown)}")

    # 3. The CTA shape is dictated by the prompt, so it has to be allowed back.
    cta = ("### Slide 9 · CTA\n- **Primary CTA:** Send this to the friend who "
           "waits by the [[door]].\n")
    if writer.check_leak(cta, shown):
        failures.append("CTA the mandated CTA shape was refused as a leak")

    # 4. The citation line is written by code, never by the model, so it is not
    #    the model's borrowing and must not be counted as it.
    source = ("### Slide 3 · Source Anchor\n"
              "- **Source:** — Sophie Leroy, *Why Is It So Hard to Do My Work?* (2009)\n"
              "- **Source Claim:** Leroy found that an unfinished job keeps taking a "
              "piece of your [[attention]].\n")
    if writer.check_leak(source, shown):
        failures.append("SOURCE the code-written citation line was counted as a leak")

    # 5. THE ONE THAT MATTERS. Every deck we have ever published, against the
    #    prompt as it stands right now. A prompt edit that spells out a phrase
    #    concrete enough to be copied will collide with something already on
    #    disk, and this is where that is found — before it ships, not after.
    for path in sorted(glob.glob(str(REPO / "carousels" / "*" / "carousel.md"))):
        hits = writer.check_leak(pathlib.Path(path).read_text(encoding="utf-8"), shown)
        if hits:
            failures.append(f"PROMPT {pathlib.Path(path).parent.name} now collides with the "
                            f"prompt: {hits[0][:120]}")

    # 6. An accent has to wrap a whole word. "[[decide]]d" shipped, and the
    #    contact sheet printed it as one word coloured in two halves.
    half = ("### Slide 4 · Value Step 1\n- **Body:** You wait until it is "
            "[[decide]]d for you.\n")
    if not any("half a word" in p for p in writer.check_accents(half)):
        failures.append("HALFWORD an accent wrapping part of a word was allowed")
    whole = "### Slide 4 · Value Step 1\n- **Body:** You wait until it is [[decided]].\n"
    if writer.check_accents(whole):
        failures.append(f"HALFWORD a whole-word accent was refused: {writer.check_accents(whole)}")

    # 7. Slide 3 may no longer be a sentence whose subject is the name. The
    #    published version of this rule produced "doorway pause explains why the
    #    outside stays in the hallway", which passed every gate and means
    #    nothing. The prompt must not be asking for that shape any more.
    if "MUST BEGIN with the pattern name" in writer.DRAFT_SCHEMA["properties"]["explains"]["description"]:
        failures.append("EXPLAINS the schema still orders the name to open the sentence")

    if failures:
        print(f"leak: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"leak: {total}/{total} passed ({len(shown)} prompt n-grams, "
          f"{len(glob.glob(str(REPO / 'carousels' / '*' / 'carousel.md')))} decks clean)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
