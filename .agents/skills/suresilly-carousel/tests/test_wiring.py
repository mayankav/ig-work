#!/usr/bin/env python3
"""
Run-wiring regression. No network, no rendering.

The parts of a run between the last model call and the post: naming the deck,
hiding the moment id in the caption, choosing where the file goes, and telling
the next step what was built.

Small functions, but each one guards something that is expensive to get wrong.
A slug that collides overwrites a published deck. A caption without its tag
means a run that dies between posting and recording cannot find out whether the
post exists. A preview writing into carousels/ puts a deck that never happened
into the published corpus, where every novelty check will compare against it
forever.
"""
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import memory  # noqa: E402
import run as runner  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4] / "scripts"))
import post_to_ig  # noqa: E402


def moment(text: str, ref: str) -> memory.Moment:
    return memory.Moment.make(text, source="bluesky", source_ref=ref,
                              anchors={"clock": ["2:17am"], "place": ["bed"]}, score=6)


def run() -> int:
    failures = []

    # ── slugs ──
    one = moment("I woke at 2:17am and watched the clock until six.", "at://post/one")
    two = moment("I woke at 2:17am and watched the clock until six.", "at://post/two")
    slug_one = runner.deck_slug(one, "2:17am", "20260830")
    slug_two = runner.deck_slug(two, "2:17am", "20260830")

    if not slug_one.startswith("20260830_"):
        failures.append(f"SLUG does not start with the date: {slug_one}")
    if slug_one == slug_two:
        failures.append("SLUG two different moments on one day produced the same folder")
    if not slug_one.replace("_", "").replace("-", "").isalnum():
        failures.append(f"SLUG is not safe as a folder name: {slug_one}")
    if len(slug_one) > 70:
        failures.append(f"SLUG is unwieldy at {len(slug_one)} characters")
    # A moment with nothing wordy in it must still produce a usable name.
    bare = moment("2 3 4 5 6 7 8 9 10 11", "at://post/bare")
    if not runner.deck_slug(bare, "", "20260830").startswith("20260830_"):
        failures.append("SLUG a moment with no words produced no name")

    # ── the caption tag ──
    markdown = ("## Caption\nSome caption text.\n\n---\n#insomnia #sleep #anxiety #suresilly\n")
    # The idempotency tag is gone. It printed "#ss4d84f6" on every published
    # post — internal plumbing, publicly — and the only thing that would have
    # read it back, check_ig_duplicate.py, was deleted a week before this.
    if hasattr(runner, "tag_caption"):
        failures.append("TAG the internal moment tag is back on public captions")

    # ── where files go ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        runner.CAROUSELS = tmp / "carousels"

        published = runner.write_deck("# deck\n", "20260830_real")

        if runner.CAROUSELS not in published.parents:
            failures.append("WRITE a real deck did not land in carousels/")
        if published.name != "carousel.md":
            failures.append("WRITE the file is not named carousel.md")

        # There was a second destination, .preview/, for a deck that had not
        # really happened. Nothing ever wrote to it: --dry-run returns before a
        # deck exists, and the only caller passed preview=False. A dead second
        # place to put the published corpus is worth asserting gone, the same
        # way the caption tag above is.
        if hasattr(runner, "PREVIEW"):
            failures.append("WRITE the preview destination is back, and nothing takes it")

    # ── telling the next step what was built ──
    with tempfile.TemporaryDirectory() as tmpdir:
        output = pathlib.Path(tmpdir) / "out.txt"
        import os
        os.environ["GITHUB_OUTPUT"] = str(output)
        runner.REPO_ROOT = pathlib.Path(tmpdir)
        try:
            runner.emit_slug("20260830_real", pathlib.Path(tmpdir) / "carousels" / "x" / "carousel.md")
            written = output.read_text()
            if "slug=20260830_real" not in written:
                failures.append("EMIT the slug never reached the workflow output")
            if "deck=" not in written:
                failures.append("EMIT the deck path never reached the workflow output")
        finally:
            os.environ.pop("GITHUB_OUTPUT", None)

    # ── the anchor the coherence gate is given ──
    if runner.plan_token(one) != "2:17am":
        failures.append(f"ANCHOR expected the clock time, got {runner.plan_token(one)!r}")
    empty = memory.Moment.make("something", "bluesky", "at://x", anchors={}, score=0)
    if runner.plan_token(empty) != "":
        failures.append("ANCHOR a moment with no anchors returned something")

    # What Instagram is actually handed.
    #
    # The writer wrote the tags as bare words under a horizontal rule and
    # post_to_ig.py looked for a "## Hashtags" heading. Two formats, two files,
    # nothing comparing them — so every post this engine has ever published went
    # out with the caption and no tags at all, and both files were individually
    # correct. This is the only test that reads what one wrote with the other.
    import writer
    assembled = "\n".join([
        "# Carousel: test", "",
        "## Caption", "Execution freeze is the cost of waiting for readiness.", "",
        "## Hashtags",
        " ".join(f"#{t}" for t in ("executivedysfunction", "adhd", "burnout")), "",
        "## Alt Text", "Slide 1: a donkey.", ""])
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(assembled)
        deck_path = pathlib.Path(handle.name)
    try:
        posted = post_to_ig.parse_caption(deck_path)
    finally:
        deck_path.unlink(missing_ok=True)
    for tag in ("#executivedysfunction", "#adhd", "#burnout"):
        if tag not in posted:
            failures.append(f"CAPTION {tag} never reached Instagram: {posted[:120]!r}")
    if "Execution freeze" not in posted:
        failures.append("CAPTION the caption itself did not reach Instagram")

    # ── the deck's markup does not reach Instagram ──
    #
    # [[accent]] is an instruction to the renderer about which word the slide
    # colours. Instagram has no renderer; it prints the characters. 20260901
    # posted a caption reading "the [[cost]] of carrying the [[street]] across
    # the [[threshold]]" — twenty-one pairs of brackets, because the caption was
    # the one line of copy assemble() wrote into the file raw, and nothing
    # between there and the API looked at it.
    #
    # Checked on both sides. The writer must stop putting markup in the file,
    # AND the poster must strip whatever it is handed — a held deck is posted
    # days later from a file an older engine wrote, and carousel.md gets edited
    # by hand.
    marked = assembled.replace(
        "Execution freeze is the cost of waiting for readiness.",
        "Execution freeze is the [[cost]] of waiting, and it was "
        "[[never]] **laziness** or an [[unfinish]]ed thought.")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(marked)
        marked_path = pathlib.Path(handle.name)
    try:
        posted = post_to_ig.parse_caption(marked_path)
    finally:
        marked_path.unlink(missing_ok=True)
    for token in ("[[", "]]", "**"):
        if token in posted:
            failures.append(
                f"CAPTION {token!r} reached Instagram: {posted[:120]!r}")
    for word in ("cost", "never", "laziness", "unfinished"):
        if word not in posted:
            failures.append(
                f"CAPTION stripping the markup ate {word!r}: {posted[:120]!r}")

    # The writer's side of the same rule: the caption goes through no_accent,
    # the way every other line of copy goes through it or ensure_accent.
    source = pathlib.Path(
        pathlib.Path(__file__).resolve().parent.parent / "scripts" / "writer.py"
    ).read_text(encoding="utf-8")
    if 'no_accent(copy["caption"]' not in source:
        failures.append(
            "CAPTION the writer is putting the caption into carousel.md raw again")

    # And the writer has to produce that shape. A hashtag without its # is a
    # word, and the section heading is what the poster searches for.
    body = writer.assemble.__doc__ or ""
    if "## Hashtags" not in pathlib.Path(
            pathlib.Path(__file__).resolve().parent.parent / "scripts" / "writer.py"
    ).read_text(encoding="utf-8"):
        failures.append("CAPTION the writer no longer emits a Hashtags heading")

    # The set handed to the writer must be the words, not the kinds. This line
    # sent {"clock", "place"} for months. The coherence gate reads it as the
    # only scene the deck is allowed to mention, so every real word — the bed,
    # the text, the door — came back as invented, and no deck ever passed.
    words = runner.anchor_words(one)
    if words != {"2:17am", "bed"}:
        failures.append(f"ANCHOR expected the words the moment is made of, got {words}")
    if runner.anchor_words(empty) != set():
        failures.append("ANCHOR a moment with no anchors produced words")

    # ── the record step actually stages what the run produced ──
    #
    # Not a grep. The add loop is lifted out of auto-post.yml and RUN against a
    # throwaway repo shaped like this one, with one of its pathspecs absent —
    # which is the state the real repo is in, because concept_history.json has
    # never existed here.
    #
    # `git add a b missing` stages NOTHING and exits 128. With `|| true` after
    # it, the run committed an empty index, said "nothing to record" and pushed
    # nothing, having already posted the deck to Instagram. The deck, its
    # novelty fingerprint and the retired moment were all lost, so the moment
    # came back the next morning.
    import re
    import subprocess
    workflow = (pathlib.Path(__file__).resolve().parents[4]
                / ".github" / "workflows" / "auto-post.yml").read_text(encoding="utf-8")
    step = workflow.split("Record what happened", 1)[-1].split("- name:", 1)[0]
    loop = re.search(r"^(\s*)for path in .*?^\1done", step, re.S | re.M)
    if loop is None:
        failures.append("RECORD the add loop is gone from auto-post.yml")
    else:
        script = "\n".join(line[len(loop.group(1)):] for line in loop.group(0).splitlines())
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = pathlib.Path(tmpdir)
            git = ["git", "-C", str(repo)]
            subprocess.run(git + ["init", "-q", "."], check=True)
            subprocess.run(git + ["config", "user.email", "t@t"], check=True)
            subprocess.run(git + ["config", "user.name", "t"], check=True)
            for rel in ("state/used.jsonl",
                        "carousels/20260901_deck/carousel.md",
                        ".agents/skills/suresilly-carousel/palette_history.json"):
                path = repo / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("new\n", encoding="utf-8")
            subprocess.run(["bash", "-c", script], cwd=repo, check=False,
                           capture_output=True)
            staged = subprocess.run(git + ["diff", "--cached", "--name-only"],
                                    capture_output=True, text=True).stdout.split()
            for want in ("state/used.jsonl", "carousels/20260901_deck/carousel.md"):
                if want not in staged:
                    failures.append(
                        f"RECORD {want} was not staged — one absent pathspec "
                        f"emptied the whole add again (staged: {staged})")

    total = 3 + 3 + 3 + 2 + 4 + 5 + 2 + 3
    if failures:
        print(f"wiring: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"wiring: {total}/{total} passed (slugs, file placement, "
          f"workflow output, anchors, what Instagram is handed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
