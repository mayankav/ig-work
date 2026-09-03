#!/usr/bin/env python3
"""
What colour a run ends. No network, no state written.

The engine had two endings and needed three. A coherence gate refusing every
draft and a vendor that could not be reached both raised llm.ModelRefused, both
exited 1, and both turned CI red. Run 33583495343 was the first kind and read as
the second: the Telegram message said "a gate refusing, which is the system
working" while the run sat red in the actions list.

    green   a deck went out                                       exit 0
    amber   nothing shipped and nothing broke — a gate did its job exit 0
    red     something is broken, and a retry will not fix it       exit 1

Two things are worth testing and they are different questions.

  THE HANDLER   given an exception, what does run() exit with. Driven by
                stubbing check_halt, the first call inside the try block, so no
                vendor is reached and nothing is claimed or written.
  THE SITE      does the code that used to raise the red exception now raise
                the amber one. The handler being right is worth nothing if
                plan_deck still raises ModelRefused when its gates simply would
                not pass — which is invariant 25: a rule enforced somewhere
                other than where it fires is a rule that fires too late.

The most important case here is the one that must stay RED: a vendor failure
inside llm.ask() propagates out of the very same writer loop that raises the
amber exception, so the two travel the same path and are told apart only by
type. If Refused ever became a parent or a child of ModelRefused, one of these
would silently swallow the other and the split would be over.
"""
import contextlib
import copy as copymod
import io
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))
import critic  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import outcomes  # noqa: E402
import run as runner  # noqa: E402
import writer  # noqa: E402
# The one plan in this repo that is known to pass every gate, so a mutation of
# it is known to fail for exactly one reason. Restating it here would leave two
# copies to keep in step, and the second would rot.
from test_writer import MOMENT, good_plan  # noqa: E402


def ending(raised: Exception) -> tuple[int, str]:
    """Run the pipeline until check_halt, throw, and report code and output.

    dry-run mode on purpose: it is the one mode that skips the state check, and
    the exception lands before anything else is reached anyway. Nothing is
    claimed, so the finally block releases nothing and state/ is untouched.
    """
    def boom() -> None:
        raise raised

    keep = runner.check_halt
    buffer = io.StringIO()
    try:
        runner.check_halt = boom
        with contextlib.redirect_stdout(buffer):
            code = runner.run("dry-run")
    finally:
        runner.check_halt = keep
    return code, buffer.getvalue()


def run() -> int:
    failures = []

    # ── the handler ──
    #
    # (what was raised, the exit code it must produce, why)
    for raised, want, why in [
        (outcomes.Refused("every draft failed the same gate"), 0,
         "a gate refusing is the engine working"),
        (llm.ModelRefused("no vendor answered"), 1,
         "a vendor nobody could reach is a real outage"),
        (critic.NoReview("no critic could be reached"), 1,
         "a deck written and never reviewed needs a person"),
        (outcomes.Stop("the renderer refused"), 1,
         "the red stops stayed red"),
        (memory.AlreadyUsed("m-572b219023b990a8 is already live"), 0,
         "declining to duplicate a live post is not a failure"),
    ]:
        code, _ = ending(raised)
        if code != want:
            failures.append(f"EXIT {type(raised).__name__} exited {code}, wanted "
                            f"{want} — {why}")

    # The amber message has one job beyond the exit code: telling the owner that
    # trying again could work. That line is the whole point of the Telegram verb.
    _, said = ending(outcomes.Refused("every draft failed the same gate"))
    if "retry" not in said:
        failures.append("AMBER the stopped message never offered the retry verb")
    if "no vendor problem" not in said.lower():
        failures.append("AMBER the stopped message did not say nothing was broken")

    # And it must not offer one that cannot work. An empty concept pool does not
    # refill because somebody asked twice.
    _, empty = ending(outcomes.Refused("no unused concept left", retry=False))
    if "reply `retry`" in empty:
        failures.append("AMBER a retry was offered for a pool only topup can refill")

    # ── the two exceptions may not be relatives ──
    #
    # They are raised from the same writer loop and are told apart by type
    # alone. A subclass either way and the earlier handler eats both.
    if issubclass(outcomes.Refused, llm.ModelRefused):
        failures.append("TYPE Refused inherits ModelRefused, so every vendor outage is amber")
    if issubclass(llm.ModelRefused, outcomes.Refused):
        failures.append("TYPE ModelRefused inherits Refused, so every gate refusal is red")
    if issubclass(outcomes.Refused, outcomes.Stop) or issubclass(outcomes.Stop, outcomes.Refused):
        failures.append("TYPE Stop and Refused are relatives, so one handler catches both")
    # run.Stop is the name three other suites and write_deck already use.
    if runner.Stop is not outcomes.Stop:
        failures.append("TYPE run.Stop is no longer outcomes.Stop, so the two halves of the "
                        "codebase are raising and catching different exceptions")
    if writer.Refused is not outcomes.Refused:
        failures.append("TYPE writer.Refused is no longer outcomes.Refused")

    # ── the raise site, not just the handler ──
    #
    # plan_deck asks four times and then gives up. Which exception it gives up
    # with is the entire fix: it used to be ModelRefused, identical to a vendor
    # being down. The model here always answers, and always answers badly.
    keep_ask = llm.ask
    keep_discover = writer.bibliography.discover
    # A real plan, well-formed and schema-valid, with the pattern name changed so
    # it no longer appears on slides 1 and 4. An ordinary gate failure of the
    # kind the live model produces several times a week — not malformed JSON,
    # which would prove something else entirely.
    stubborn = copymod.deepcopy(good_plan())
    stubborn["pattern_name"] = "Doorway Delay"
    try:
        # No new book survives the shelf gates. That is the ordinary case — the
        # gates are strict — and it keeps this test off the network entirely.
        writer.bibliography.discover = lambda *a, **k: (None, [])
        llm.ask = lambda *a, **k: (copymod.deepcopy(stubborn), "stub")
        try:
            writer.plan_deck(MOMENT, "sleep")
            failures.append("SITE plan_deck accepted a plan that fails every gate")
        except outcomes.Refused as refused:
            # The faults-per-attempt trail is how the owner reads what happened,
            # and it is the difference between "a gate said no" and "no idea".
            if "faults per attempt" not in str(refused):
                failures.append(f"SITE the amber message dropped the fault trail: {refused}")
        except llm.ModelRefused:
            failures.append("SITE plan_deck still reports exhausted gates as a vendor failure")

        # Same loop, same call, vendor down. This one must stay red, and it is
        # the case a careless `except ModelRefused: raise Refused` would break.
        def unreachable(*a, **k):
            raise llm.ModelRefused("all three vendors refused")

        llm.ask = unreachable
        try:
            writer.plan_deck(MOMENT, "sleep")
            failures.append("SITE an unreachable vendor produced a plan")
        except outcomes.Refused:
            failures.append("SITE a vendor outage inside the writer loop was reported as amber")
        except llm.ModelRefused:
            pass
    finally:
        llm.ask = keep_ask
        writer.bibliography.discover = keep_discover

    total = 5 + 3 + 5 + 2
    if failures:
        print(f"outcomes: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"outcomes: {total}/{total} passed (5 exit codes, the amber message and its "
          f"retry offer, 5 type checks, both raise sites)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
