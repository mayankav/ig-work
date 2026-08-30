#!/usr/bin/env python3
"""
Run-guard regression.

Two guards stand between a manual run and a duplicate post, and neither is
exercised by anything else in the suite.

  KILL SWITCH   stops every run, scheduled or manual, from a file in the repo or
                an environment variable on the workflow.
  STATE CHECK   refuses to run from a copy of state/ that is dirty or behind the
                shared one. This is the guard that matters: a laptop dealing from
                yesterday's list is the one remaining way the same moment gets
                used twice.

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

    if failures:
        print(f"run guards: {len(failures)} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print("run guards: 8/8 passed (kill switch by env and file, "
          "HALT not counted as dirty, dirty state, behind remote, recovery after pull)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
