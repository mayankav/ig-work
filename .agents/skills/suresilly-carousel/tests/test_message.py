#!/usr/bin/env python3
"""
One template, the real reason, and the verb that overrides a gate.

On 2026-09-03 both slots produced nothing and the owner was told, twice:

    No deck was built. A gate refused, which is the system working.
    Reply retry to try again now with a fresh moment.

Every word of that was a constant in auto-post.yml. The real reason existed the
whole time — run.py printed it — and the report step never read stdout. So the
owner could not tell a stuck check from an unlucky draft, and replied `retry`,
which ran seven minutes and hit the identical wall.

Four things are tested here and they are different questions.

  THE TRAJECTORY  can the engine tell a gate it cannot satisfy from a draft that
                  was nearly there. This is the measurement behind invariant
                  27's promise that `retry` is offered only when it could work.
  THE MESSAGE     does every message answer the same five questions, in plain
                  words, in one colour key. A message is only as good as its
                  worst morning, so this checks the ones nobody reads carefully.
  THE OVERRIDE    `force` may stand in for a matter of taste and may NOT stand
                  in for the two hard faults. Invariant 4's narrowing is only
                  as narrow as this test.
  THE TWO TABLES  index.js and telegram_review.py both parse a reply, and a verb
                  known to one and not the other is silently dropped. Nothing
                  caught that drift before this.

No network, and nothing here writes to state/.
"""
import html
import json
import os
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent.parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(REPO / "scripts"))
import dashboard  # noqa: E402
import outcomes  # noqa: E402
import readability  # noqa: E402
import telegram_review  # noqa: E402
import writer  # noqa: E402

STATUSES = ("ok", "held", "stopped", "error")

# The refusal reason exactly as writer.write_deck shapes it: the faults joined
# with semicolons, then the per-attempt trail in brackets. Both halves have to
# survive the trip through $GITHUB_OUTPUT into the workflow and back out here.
STUCK_REASON = (
    "slide 9 must name a kind of person, not 'anyone'; "
    "slide 4 uses 'emotional', which is 4 syllables or more "
    "[faults per attempt: 13, 5, 4, 3, 3, 3, 3]"
)

# Every emoji the colour key knows about, from both tables. A message may print
# these and nothing else — see the colour-key case below for why.
def known_emoji() -> set[str]:
    marks = set(dashboard.MARK.values())
    for rows in dashboard.REPLIES.values():
        marks |= {emoji for emoji, _verb, _what in rows}
    return marks


# The pictograph blocks, and only those. Box drawing (U+2500–U+257F) and arrows
# (U+2190–U+21FF) are deliberately outside every range here: `━` is the section
# divider and `→` joins the fault trail, and both are LAYOUT. They carry no
# colour and belong to no key — asking them to be in MARK would put a horizontal
# rule in a table of meanings.
PICTOGRAPH = re.compile(
    "[ℹ☀-➿⬀-⯿"
    "\U0001F000-\U0001FAFF]️?"
)


def emoji_in(text: str) -> set[str]:
    found = set()
    for run in PICTOGRAPH.findall(text):
        # A run may be one emoji plus its variation selector, or two side by
        # side. Both forms are compared against the key as whole runs first,
        # then character by character, so 🔴 and ⚠️ both resolve.
        found.add(run)
    return found


def run() -> int:
    failures = []

    # ── the trajectory ──
    #
    # Three real trails. Two of them converged and ended one attempt short of
    # clean, so a rule that calls either stuck withholds a retry from a run that
    # was about to finish. The third is the one that could not be satisfied.
    for history, want, why in [
        ([13, 5, 4, 3, 3, 3, 3], "stuck",
         "local-1788395662: the same fault stood for four attempts"),
        ([6, 2, 1], "converging", "a CI run that was one attempt from clean"),
        ([4, 4, 4, 2, 1], "converging",
         "three identical counts and then it moved — STUCK_AFTER=2 would fail here"),
        ([7], "one-shot", "one try is nothing to compare against"),
        ([], "one-shot", "no trail at all"),
    ]:
        shape, sentence = outcomes.trajectory(history)
        if shape != want:
            failures.append(f"TRAIL {history} read as {shape}, wanted {want} — {why}")
        if not sentence.strip():
            failures.append(f"TRAIL {history} came back with no sentence for the owner")

    if outcomes.arrow([13, 5, 4]) != "13 → 5 → 4":
        failures.append("TRAIL the arrow line is not the scannable shape")
    if outcomes.arrow([]) != "—":
        failures.append("TRAIL an empty trail printed something other than a dash")

    # STUCK_AFTER, pinned from BOTH sides.
    #
    # The cases above are finished trails and every one of them reads the same at
    # 2, 3 and 4 — a mutation of the constant walks straight past them. What a run
    # actually sees is a PREFIX, because the loop asks after each attempt, and the
    # boundary lives there:
    #
    #   [4, 4]     must be converging — it is the third attempt of 4,4,4,2,1, a
    #              run that went on to finish. STUCK_AFTER=2 calls it stuck and
    #              withholds a retry from a run that was two attempts from clean.
    #   [4, 4, 4]  must be stuck — three identical counts is the rule. At
    #              STUCK_AFTER=4 nothing fires until the sixth attempt of a
    #              seven-attempt loop, which is too late to be worth saying.
    #
    # A rule that only ever subtracts is as wrong as one that never does, so both
    # halves are pinned and neither may be relaxed to make the other pass.
    if outcomes.trajectory([4, 4])[0] != "converging":
        failures.append("STUCK two identical counts read as stuck — a run two "
                        "attempts from clean would be told to give up")
    if outcomes.trajectory([4, 4, 4])[0] != "stuck":
        failures.append("STUCK three identical counts did not read as stuck — the "
                        "rule now fires too late to be worth saying")

    # A trail read back out of the reason string, which is the only form that
    # survives $GITHUB_OUTPUT. If this breaks, the message silently claims one
    # attempt was made when there were seven.
    if dashboard.read_trail(STUCK_REASON) != [13, 5, 4, 3, 3, 3, 3]:
        failures.append("TRAIL the fault trail did not survive the reason string")
    if len(dashboard.split_faults(STUCK_REASON)) != 2:
        failures.append("TRAIL the faults did not split back out of the reason")
    # A single blocking check is the common case and the one a naive split drops.
    if dashboard.split_faults("one fault and no trail") != ["one fault and no trail"]:
        failures.append("TRAIL a reason with no semicolon came back as zero faults")

    # ── a retry that cannot work is not offered ──
    stuck = dashboard.build("stopped", None, STUCK_REASON, None, None, retry=False)
    if "🚫" not in stuck:
        failures.append("RETRY a withheld retry was not marked 🚫")
    if "retry" not in stuck:
        failures.append("RETRY the word was hidden instead of marked — the owner "
                        "will go looking for it")
    if "Start again with a new idea." in stuck:
        failures.append("RETRY a withheld retry still carried its ordinary blurb")
    offered = dashboard.build("stopped", None, STUCK_REASON, None, None, retry=True)
    if "🚫" in offered:
        failures.append("RETRY a workable retry was marked 🚫")

    # The exception carries the same fact, and carries it as a field rather than
    # only inside its message. That field is what run.py hands the workflow.
    refused = outcomes.Refused("no unused concept left", retry=False, history=[3, 3, 3])
    if refused.retry is not False or refused.history != [3, 3, 3]:
        failures.append("RETRY Refused dropped the retry flag or the history")

    # ── every message renders, and answers the five questions ──
    for status in STATUSES:
        text = dashboard.build(status, "20260903_kitchen_a1b2c3", STUCK_REASON,
                               "62", "http://run/1")
        if not text.strip():
            failures.append(f"RENDER {status} produced nothing")
            continue
        if "REPLY WITH ONE WORD" not in text:
            failures.append(f"RENDER {status} listed no replies at all")
        if "IF YOU DO NOTHING" not in text:
            failures.append(f"RENDER {status} never says what silence does")
        if dashboard.RULE not in text:
            failures.append(f"RENDER {status} has no section dividers")
        # A gap above a divider makes the message look like it has holes in it.
        if f"\n\n{dashboard.RULE}" in text:
            failures.append(f"RENDER {status} left a blank line above a divider")
        # Every verb it offers must be one the parser knows. A message naming a
        # word the Worker drops is a message that teaches the owner a dead verb.
        for _emoji, verb, _what in dashboard.REPLIES[status]:
            word = verb.split()[0]
            if word not in telegram_review.VERBS:
                failures.append(f"RENDER {status} offers {word!r}, which no parser knows")

    # The one that must never be two messages: a held deck carries the contact
    # sheet, so it is a caption, and Telegram REJECTS an over-long caption rather
    # than trimming it.
    #
    # Measured against the WORST case, not a comfortable one. A cap of six
    # objections was written into the code and was never right: with a two-line
    # reviewer note the message is 922 characters before a single objection and
    # each one costs 30 to 55 more, so two long ones already overflowed while six
    # short ones fitted. What fits depends on wrapping, on HTML escaping and on
    # the note — none of which a fixed count can see.
    long_note = ("the critic wanted a sharper last slide and a clearer "
                 "second cover")
    # A realistic critic paragraph. This is the case that found the second lever:
    # it rendered at 1101 characters and the objection fitter could not help,
    # because dropping every objection still leaves the note behind.
    paragraph = ("the critic wanted a sharper last slide and a clearer second "
                 "cover, said slide four leans on a word the reader has to stop "
                 "at, and asked whether the pattern name belongs on slide two or "
                 "slide three because it reads as two ideas fighting for the "
                 "same line")
    many = ["Last slide says 'anyone', not a person",
            "Slide 4 has a hard word",
            "Slide 2 repeats the headline",
            "Slide 7 has no accent",
            "The hook and the handle share three words",
            "Slide 5 names the pattern twice"]
    for note, objs, label in [
        ("", [], "nothing at all"),
        ("the critic was unsure", many[:2], "short note, two objections"),
        (long_note, many[:2], "long note, two objections"),
        (long_note, many, "long note, six objections"),
        ("", many, "no note, six objections"),
        (paragraph, many[:2], "critic paragraph, two objections"),
        (paragraph, many, "critic paragraph, six objections"),
        # A note far past anything the engine writes. Nothing bounds what a
        # reviewer types, and the message still has to arrive.
        ("x " * 600, many[:2], "a 1200-character note"),
        # One objection long enough to blow the budget on its own. The floor that
        # matters is the reply list, so this must drop to the summary line rather
        # than protect a line nobody can read.
        (long_note, ["x" * 300, "y" * 300, "z" * 300], "three 300-char objections"),
    ]:
        held = dashboard.build("held", "20260903_kitchen_a1b2c3", note, "62",
                               "http://run/1", "html", objections=objs)
        if len(held) > dashboard.CAPTION_BUDGET:
            failures.append(f"CAPTION {label}: {len(held)} chars, over the "
                            f"{dashboard.CAPTION_BUDGET} budget — notify.py would "
                            f"cut the reply list into a second message")
        # Whatever else is dropped, these two survive. The reply list is the only
        # part of a held message that has to be read.
        if "publish a1b2c3" not in held or "rerun a1b2c3" not in held:
            failures.append(f"CAPTION {label}: the reply list did not survive fitting")
        shown = held.count(dashboard.MARK["fail"])
        if shown < len(objs) and "more — see the full log" not in held:
            failures.append(f"CAPTION {label}: {len(objs) - shown} objection(s) were "
                            f"dropped silently")
        if shown > len(objs):
            failures.append(f"CAPTION {label}: printed more objections than it was given")

    # NOTE_BUDGET, pinned from both sides. It is the trimmer's only number and a
    # trimmer that only ever subtracts is as wrong as one that never does: at 140
    # the note goes out whole, at 141 it is cut and marked.
    at_cap = dashboard.build("held", "20260903_kitchen_a1b2c3",
                             "y" * dashboard.NOTE_BUDGET, "62", "http://run/1",
                             "html", objections=many[:2])
    if "…" in at_cap:
        failures.append(f"NOTE a note of exactly {dashboard.NOTE_BUDGET} characters "
                        f"was trimmed — the cap is meant to be inclusive")
    over_cap = dashboard.build("held", "20260903_kitchen_a1b2c3",
                               "y" * (dashboard.NOTE_BUDGET + 1), "62",
                               "http://run/1", "html", objections=many[:2])
    if "…" not in over_cap:
        failures.append("NOTE a note one character over the cap was printed whole")
    # And the budget has to be a number the message can actually afford: the
    # shortest held message that still says something was dropped, carrying a
    # note of exactly NOTE_BUDGET, must fit. Measured at 145 fitting and 153 over,
    # so a later edit raising this silently is caught here rather than in Telegram.
    floor = dashboard._assemble("held", "20260903_kitchen_a1b2c3",
                                "y " * (dashboard.NOTE_BUDGET // 2), "62",
                                "http://run/1", "html",
                                objections=["and 2 more — see the full log"])
    if len(floor) > dashboard.CAPTION_BUDGET:
        failures.append(f"NOTE NOTE_BUDGET={dashboard.NOTE_BUDGET} is too generous: "
                        f"the shortest held message carrying one is {len(floor)} "
                        f"chars, over the {dashboard.CAPTION_BUDGET} budget")
    # The engine's own objections are capped at 90 by run.py._shorten, so a note
    # budget below that would trim a reason shorter than a single objection.
    if dashboard.NOTE_BUDGET < 90:
        failures.append(f"NOTE NOTE_BUDGET={dashboard.NOTE_BUDGET} is below the "
                        f"90-character cap run.py already puts on one objection")

    held = dashboard.build("held", "20260903_kitchen_a1b2c3", "the critic was unsure",
                           "62", "http://run/1", "html",
                           objections=["Last slide says 'anyone', not a person",
                                       "Slide 4 has a hard word"])
    if "the critic was unsure" not in held:
        failures.append("CAPTION the held message dropped its reason — the same "
                        "defect this whole change exists to fix")
    # The budget may never exceed what the splitter actually cuts at.
    sys.path.insert(0, str(REPO / "scripts"))
    import notify
    if dashboard.CAPTION_BUDGET > notify.CAPTION_LIMIT:
        failures.append(f"CAPTION the budget ({dashboard.CAPTION_BUDGET}) is above "
                        f"notify.CAPTION_LIMIT ({notify.CAPTION_LIMIT}), so a message "
                        f"that 'fits' still gets split")

    # ── the colour key holds ──
    #
    # An emoji is only colour if it means one thing. A stray one makes the key
    # mean less, and a key that is only a convention is one edit from wrong.
    key = known_emoji()
    for status in STATUSES:
        text = dashboard.build(status, "20260903_kitchen_a1b2c3", STUCK_REASON,
                               "62", "http://run/1", retry=False,
                               objections=["Slide 4 has a hard word"])
        for run_of in emoji_in(text):
            if run_of in key:
                continue
            if all(ch in "".join(key) for ch in run_of):
                continue
            failures.append(f"COLOUR {status} printed {run_of!r}, which is not in "
                            f"MARK or REPLIES")

    # ── the message stays plain English ──
    #
    # readability already refuses any four-syllable word a reader can see, and
    # already names the word. Pointing it at this file's own wording is how the
    # plain writing survives the next person to edit it (invariant 25: a rule
    # enforced only by a habit fires one commit too late).
    speech = []
    speech += list(dashboard.TITLE.values())
    speech += list(dashboard.IDLE.values())
    speech += [what for rows in dashboard.REPLIES.values() for _e, _v, what in rows]
    # PLAIN position 2 is the deliberately BAD example — quoting the refused word
    # is how the owner learns which word, so it is a quotation, not our writing.
    for what, good, _bad, why in dashboard.PLAIN.values():
        speech += [what, good, why]
    for _shape, sentence in (outcomes.trajectory(h) for h in
                             ([13, 5, 4, 3, 3, 3, 3], [6, 2, 1], [7])):
        speech.append(sentence)
    for line in speech:
        for fault in readability.line_faults(line.replace("{next}", "at 20:00")
                                                 .replace("{id}", "a1b2c3")):
            failures.append(f"PLAIN {fault}")

    # ── the HTML is safe to send, and safe to split ──
    #
    # notify.py cuts a long caption at a newline and sends both halves. That is
    # only safe because no tag spans one. And an unescaped < or & makes Telegram
    # reject the whole message with a 400 — the message is then not shortened,
    # it is simply never delivered.
    nasty = ("slide 9 says <b>anyone</b> & not a person; "
             "slide 4 uses 'it's' [faults per attempt: 5, 5, 5]")
    marked = dashboard.build("stopped", "20260903_x_a1b2c3", nasty, None,
                             "http://run/1?a=1&b=2", "html")
    for line in marked.splitlines():
        opened = len(re.findall(r"<(b|i|code|a)\b", line))
        closed = len(re.findall(r"</(b|i|code|a)>", line))
        if opened != closed:
            failures.append(f"HTML a tag spans a newline, which breaks the caption "
                            f"split: {line!r}")
    # The vendor text must arrive escaped. Unescaping what we built has to give
    # back the original, and the raw < must not be sitting in the output.
    if "<b>anyone</b>" in marked:
        failures.append("HTML the reason went out with its own tags unescaped")
    if "&amp;" not in marked:
        failures.append("HTML an ampersand in the reason was not escaped")
    if "&amp;b=2" not in marked:
        failures.append("HTML the log URL was not escaped inside href")
    # Text mode is for email and the run log, and must carry no markup at all.
    plain = dashboard.build("stopped", "20260903_x_a1b2c3", nasty, None,
                            "http://run/1", "text")
    if "<b>" in plain.replace("<b>anyone</b>", ""):
        failures.append("TEXT the plain-text message carried HTML tags")

    # ── the override may not reach the two hard faults ──
    #
    # The corpus is the two briefs that shipped on 2026-09-02 — the two that most
    # plainly ask for lettering, and the two MASCOT_TEXT could not read.
    for brief in ("A small donkey saying 'I'm out' with one hoof raised",
                  "A small donkey holding a card with the words 'Exit Block'"):
        markdown = f"## Slide 1\n\n- **Mascot:** {brief}\n"
        if not writer.hard_faults(markdown):
            failures.append(f"FORCE hard_faults let a lettering brief through: {brief!r}")

    # A copy-craft fault is NOT hard. If it were, force could override nothing
    # and the verb would be decoration.
    clean = "## Slide 1\n\n- **Mascot:** A small donkey looking at a closed door\n"
    if writer.hard_faults(clean):
        failures.append("FORCE hard_faults fired on an ordinary brief, so force "
                        "can never override anything")

    # Posture wording and repeated scene wording are visible review issues. They
    # do not request unsafe artwork and must not stop an owner review preview.
    reviewable = "\n".join(
        f"## Slide {number}\n\n- **Mascot:** A small donkey looks relaxed beside a chair"
        for number in range(1, 10)
    )
    if writer.hard_faults(reviewable):
        failures.append("FORCE hard_faults blocked reviewable mascot wording")

    # And the flag itself is opt-in: an ordinary run is byte-identical to before.
    import inspect
    signature = inspect.signature(writer.write_deck)
    if signature.parameters["allow_faults"].default is not False:
        failures.append("FORCE allow_faults defaults to True, so every unattended "
                        "run now overrides its own gates")
    if len(inspect.signature(writer.write_deck).return_annotation.split(",")) < 5:
        failures.append("FORCE write_deck no longer returns the overridden faults")

    # ── the two verb tables may not drift ──
    #
    # index.js is the live parser and telegram_review.py is review.yml's. A word
    # known to one and not the other is silently ignored or silently unhandled,
    # and nothing caught that before this.
    source = (REPO / "ops" / "dispatch-worker" / "src" / "index.js").read_text(
        encoding="utf-8")
    block = re.search(r"const VERBS = \{(.*?)\n\};", source, re.S)
    if not block:
        failures.append("VERBS could not find the VERBS table in index.js")
    else:
        js = {}
        for name, value in re.findall(r"(\w+):\s*\"(\w+)\"", block.group(1)):
            js[name] = value
        if js != telegram_review.VERBS:
            only_js = set(js) - set(telegram_review.VERBS)
            only_py = set(telegram_review.VERBS) - set(js)
            differ = {k for k in set(js) & set(telegram_review.VERBS)
                      if js[k] != telegram_review.VERBS[k]}
            failures.append(f"VERBS the two tables have drifted — only in JS: "
                            f"{sorted(only_js)}, only in Python: {sorted(only_py)}, "
                            f"disagreeing: {sorted(differ)}")
        # The one pair that must never be folded together, in both tables.
        if js.get("rerun") != "drop" or telegram_review.VERBS.get("rerun") != "drop":
            failures.append("VERBS `rerun` no longer means drop — it reads like "
                            "'run it again' and has always done the opposite")
        if js.get("force") != "force" or telegram_review.VERBS.get("force") != "force":
            failures.append("VERBS `force` is not wired in both tables")
        if js.get("retry") != "retry":
            failures.append("VERBS `retry` is not wired in the live parser")

    # review.yml's half knows the word and must decline to act on it — a build is
    # a workflow dispatch and only the Worker holds that token. This is the guard
    # that stops `force` falling through to the unguarded drop that used to be
    # the last statement in act().
    for verb in ("retry", "force"):
        answer = telegram_review.act(verb, "a1b2c3")
        if "don't act on" not in answer:
            failures.append(f"VERBS telegram_review.act({verb!r}) did not decline")

    # ── the ledger records and never decides ──
    with tempfile.TemporaryDirectory() as tmp:
        ledger = pathlib.Path(tmp) / "gate_faults.jsonl"
        rows = [{"at": "2026-09-03T08:00:00Z", "run": "1",
                 "faults": ["slide 9 must name a kind of person, not 'anyone'"],
                 "history": [3, 3, 3], "shape": "stuck"},
                {"at": "2026-09-03T20:00:00Z", "run": "2",
                 "faults": ["slide 9 must name a kind of person, not 'anyone'"],
                 "history": [3, 3, 3], "shape": "stuck"}]
        ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        keep = dashboard.STATE
        try:
            dashboard.STATE = pathlib.Path(tmp)
            seen = dashboard.blocked_runs("slide 9 must name a kind of person")
            if seen != 2:
                failures.append(f"LEDGER counted {seen} blocked runs, wanted 2")
            # A missing ledger is "nobody has counted", never "this is new".
            dashboard.STATE = pathlib.Path(tmp) / "not-here"
            if dashboard.blocked_runs("anything") != 0:
                failures.append("LEDGER a missing file did not read as zero")
            # A corrupt one must not take the message down. The run is over by
            # the time this is called and the report is all there is.
            bad = pathlib.Path(tmp) / "bad"
            bad.mkdir()
            (bad / "gate_faults.jsonl").write_text("{not json\n", encoding="utf-8")
            dashboard.STATE = bad
            if dashboard.blocked_runs("anything") != 0:
                failures.append("LEDGER a corrupt file did not degrade to zero")
        finally:
            dashboard.STATE = keep

    # Invariant 17, applied to gates: the ledger is written by run.py and read by
    # nothing that decides. dashboard.py is a job, not the engine.
    engine = HERE.parent / "scripts"
    for module in sorted(engine.glob("*.py")):
        if module.name == "run.py":
            continue
        if "gate_faults" in module.read_text(encoding="utf-8"):
            failures.append(f"LEDGER {module.name} reads the fault ledger; only "
                            f"run.py writes it and only the report reads it")

    total = 7 + 5 + 6 + 4 + 42 + 4 + 4 + 6 + 4 + 5 + 4
    if failures:
        print(f"message: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"message: {total}/{total} passed (3 real fault trails, the retry offer, "
          f"4 messages rendered, the caption limit, the colour key, plain English, "
          f"safe HTML, the two hard faults, both verb tables, the ledger)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
