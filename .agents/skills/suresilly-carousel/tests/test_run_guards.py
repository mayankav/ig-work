#!/usr/bin/env python3
"""
Run-guard regression.

Three guards stand between a manual run and a duplicate post, and none of them
is exercised by anything else in the suite.

  KILL SWITCH   stops every run, scheduled or manual, from a file in the repo or
                an environment variable on the workflow.
  STATE CHECK   refuses to run from a copy of state/ that is dirty or behind the
                shared one. A laptop dealing from yesterday's list is how the
                same moment gets used twice.
  ARCHIVE       refuses to write a deck into a folder a post already came out of.
                This one exists because the state check is a heuristic and can be
                wrong: on 2026-09-01 it reported "current" about a stale copy,
                and the run rebuilt a live post's slug on top of the only record
                of it. A guard whose whole job is to catch the case where the
                previous guard was wrong cannot be built out of the same signal,
                so this one reads the folder rather than asking git.

The state check talks to git, so these cases build a real repository with a real
remote rather than mocking it. Slower, but a mock of git would only prove that
the mock behaves the way I assumed git does.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import run as runner  # noqa: E402


def git(repo: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return done.stdout.strip()


def build_pair(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """An origin, and a clone of it that stands in for the laptop."""
    origin = root / "origin"
    origin.mkdir()
    git(origin, "init", "--quiet", "--bare", "--initial-branch=main")

    first = root / "first"
    git(root, "clone", "--quiet", str(origin), str(first))
    git(first, "config", "user.email", "test@test")
    git(first, "config", "user.name", "test")
    (first / "state").mkdir()
    (first / "state" / "used.jsonl").write_text("")
    git(first, "add", "-A")
    git(first, "commit", "--quiet", "-m", "state")
    git(first, "push", "--quiet", "origin", "main")

    laptop = root / "laptop"
    git(root, "clone", "--quiet", str(origin), str(laptop))
    git(laptop, "config", "user.email", "test@test")
    git(laptop, "config", "user.name", "test")
    return first, laptop


def run() -> int:
    failures = []

    # ── kill switch ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        runner.HALT_FILE = tmp / "HALT"

        os.environ.pop("SS_HALT", None)
        try:
            runner.check_halt()
        except runner.Stop:
            failures.append("KILL a clear run was halted")

        os.environ["SS_HALT"] = "1"
        try:
            runner.check_halt()
            failures.append("KILL SS_HALT=1 did not stop the run")
        except runner.Stop:
            pass
        os.environ.pop("SS_HALT")

        runner.HALT_FILE.write_text("reviewing the gates")
        try:
            runner.check_halt()
            failures.append("KILL the HALT file did not stop the run")
        except runner.Stop as stopped:
            if "reviewing the gates" not in str(stopped):
                failures.append("KILL the HALT file's reason was not reported")

    # ── state check ──
    with tempfile.TemporaryDirectory() as tmpdir:
        root = pathlib.Path(tmpdir)
        first, laptop = build_pair(root)

        runner.REPO_ROOT = laptop
        runner.HALT_FILE = laptop / "state" / "HALT"

        # In step with the remote: fine.
        try:
            runner.check_state_is_current(strict=True)
        except runner.Stop as stopped:
            failures.append(f"STATE an up-to-date clone was blocked: {stopped}")

        # HALT is a control file, not dirty state. Setting it must not also
        # trip the staleness guard, or the message would be about the wrong
        # thing at exactly the wrong moment.
        (laptop / "state" / "HALT").write_text("stop")
        try:
            runner.check_state_is_current(strict=True)
        except runner.Stop as stopped:
            failures.append(f"STATE the HALT file was treated as dirty state: {stopped}")
        (laptop / "state" / "HALT").unlink()

        # An uncommitted change under state/ blocks.
        (laptop / "state" / "reserve.json").write_text("[]")
        try:
            runner.check_state_is_current(strict=True)
            failures.append("STATE an uncommitted state file did not block the run")
        except runner.Stop as stopped:
            if "reserve.json" not in str(stopped):
                failures.append(f"STATE the dirty file was not named: {stopped}")
        (laptop / "state" / "reserve.json").unlink()

        # Someone else posts. The laptop is now behind and must refuse.
        (first / "state" / "used.jsonl").write_text('{"id": "m-abc"}\n')
        git(first, "add", "-A")
        git(first, "commit", "--quiet", "-m", "used a moment")
        git(first, "push", "--quiet", "origin", "main")

        try:
            runner.check_state_is_current(strict=True)
            failures.append("STATE a clone behind the remote was allowed to run")
        except runner.Stop as stopped:
            if "behind" not in str(stopped):
                failures.append(f"STATE staleness was reported as something else: {stopped}")

        # After pulling, it may run again.
        git(laptop, "pull", "--quiet", "--ff-only")
        try:
            runner.check_state_is_current(strict=True)
        except runner.Stop as stopped:
            failures.append(f"STATE a freshly pulled clone was still blocked: {stopped}")

    # ── the archive guard ──
    #
    # The state check above is a freshness heuristic, and on 2026-09-01 it said
    # "current" about a copy that was not. So write_deck does not trust it: it
    # looks at the folder it is about to write and refuses if a post already came
    # out of it. Invariant 18 makes these two files the only record of a live
    # deck, and the slug is derived from the moment, so a re-claimed moment aims
    # straight at them.
    with tempfile.TemporaryDirectory() as tmpdir:
        keep = runner.CAROUSELS
        try:
            runner.CAROUSELS = pathlib.Path(tmpdir)

            # A fresh slug writes normally.
            path = runner.write_deck("# Carousel: a new deck\n", "20260901_fresh_aaaa11")
            if not path.is_file() or "a new deck" not in path.read_text():
                failures.append("ARCHIVE a fresh slug did not write")

            # A slug that has already gone out is refused, and the deck that
            # went out is still there afterwards.
            slug = "20260901_posted_bbbb22"
            folder = pathlib.Path(tmpdir) / slug
            folder.mkdir()
            original = "# Carousel: the deck that went out\n"
            (folder / "carousel.md").write_text(original)
            (folder / "published.json").write_text(
                '{"media_id": "17972776875125960", "deck_slug": "%s", '
                '"published_at": "2026-09-01T08:02:38Z"}' % slug)
            try:
                runner.write_deck("# Carousel: a second deck at the same slug\n", slug)
                failures.append("ARCHIVE wrote over a deck that was already published")
            except runner.Stop as stopped:
                if "17972776875125960" not in str(stopped):
                    failures.append(f"ARCHIVE refusal did not name the post: {stopped}")
            if (folder / "carousel.md").read_text() != original:
                failures.append("ARCHIVE the published deck was overwritten anyway")

            # A folder with a corrupt published.json still counts as published.
            # Failing open here would put the guard's reliability on the shape of
            # a file another script writes.
            broken = "20260901_broken_cccc33"
            (pathlib.Path(tmpdir) / broken).mkdir()
            (pathlib.Path(tmpdir) / broken / "published.json").write_text("{not json")
            try:
                runner.write_deck("# Carousel: over a broken marker\n", broken)
                failures.append("ARCHIVE a corrupt published.json was treated as unposted")
            except runner.Stop:
                pass

            # A built-but-never-posted folder has no marker, so a rebuild is
            # allowed. Refusing it would make every held deck unrepeatable.
            held = "20260901_held_dddd44"
            (pathlib.Path(tmpdir) / held).mkdir()
            (pathlib.Path(tmpdir) / held / "carousel.md").write_text("# Carousel: held\n")
            try:
                runner.write_deck("# Carousel: rebuilt after a hold\n", held)
            except runner.Stop as stopped:
                failures.append(f"ARCHIVE refused an unpublished rebuild: {stopped}")
        finally:
            runner.CAROUSELS = keep

    if failures:
        print(f"run guards: {len(failures)} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print("run guards: 14/14 passed (kill switch by env and file, "
          "HALT not counted as dirty, dirty state, behind remote, recovery after pull, "
          "the archive of a published deck refused)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
