#!/usr/bin/env python3
"""
Notification regression. No network.

This is the only window into a pipeline nobody supervises, so the cases here are
about the ways a window quietly stops being one.

The important one is that a failure must be loud but must not fail the job. By
the time this runs the post has already happened, so a red run would be a lie
about what went wrong; and a silent failure would leave a system running
unwatched with nobody aware the watching had stopped. So it warns and exits
clean.

The `requests` calls are replaced with a stub, so these run anywhere and cannot
send anything by accident.
"""
import io
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"))
import notify  # noqa: E402


class Response:
    def __init__(self, ok: bool, status: int = 200, text: str = ""):
        self.ok, self.status_code, self.text = ok, status, text


class Stub:
    """Stands in for requests, and records what would have been sent."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.behaviour(url)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def run() -> int:
    failures = []
    real = notify.requests

    with tempfile.TemporaryDirectory() as tmpdir:
        sheet = pathlib.Path(tmpdir) / "contact_sheet.png"
        sheet.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 200)

        def with_env(**env):
            import os
            for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "EMAIL_API_KEY", "EMAIL_FROM"):
                os.environ.pop(key, None)
            os.environ.update({k: v for k, v in env.items() if v})

        # ── nothing configured ──
        with_env()
        notify.requests = Stub(lambda url: Response(True))
        captured = io.StringIO()
        held, sys.stdout = sys.stdout, captured
        code = notify.notify("subject", "body", sheet, "someone@example.com")
        sys.stdout = held
        if code != 0:
            failures.append("an unconfigured run returned a failure code")
        if "nothing configured" not in captured.getvalue():
            failures.append("an unconfigured run did not say so")
        if "subject" not in captured.getvalue():
            failures.append("an unconfigured run did not print what it would have sent")
        if notify.requests.calls:
            failures.append("an unconfigured run still tried to send something")

        # ── telegram, with the sheet ──
        with_env(TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="c")
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "body", sheet, "someone@example.com")
        urls = [url for url, _ in notify.requests.calls]
        if not any("sendDocument" in u for u in urls):
            failures.append("the contact sheet was not sent as a document")
        if any("sendPhoto" in u for u in urls):
            failures.append("sendPhoto was used, which recompresses the contact sheet")
        if not any("document" in kwargs.get("files", {}) for _, kwargs in notify.requests.calls):
            failures.append("the file never reached the request")

        # ── telegram, no attachment ──
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "body", None, "someone@example.com")
        if not any("sendMessage" in u for u, _ in notify.requests.calls):
            failures.append("a message with no attachment was not sent as a message")

        # ── a long body is not silently truncated away ──
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "x" * 3000, sheet, "someone@example.com")
        urls = [url for url, _ in notify.requests.calls]
        if not any("sendMessage" in u for u in urls):
            failures.append("the part of a long body past the caption limit was dropped")

        # ── email ──
        with_env(EMAIL_API_KEY="re_test", EMAIL_FROM="onboarding@resend.dev")
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "body", sheet, "someone@example.com")
        sent = [kwargs for url, kwargs in notify.requests.calls if "resend" in url]
        if not sent:
            failures.append("nothing was sent to Resend")
        elif not sent[0]["json"].get("attachments"):
            failures.append("the email went without the contact sheet")

        # A key for a provider we do not speak to is refused rather than
        # attempted, because the old code posted a Cloudflare token at a
        # non-existent endpoint and called that success.
        with_env(EMAIL_API_KEY="cloudflare-token-shaped")
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "body", None, "someone@example.com")
        if notify.requests.calls:
            failures.append("a key that is not a Resend key was still used to send")

        # ── both configured, both attempted ──
        with_env(TELEGRAM_BOT_TOKEN="t", TELEGRAM_CHAT_ID="c", EMAIL_API_KEY="re_test")
        notify.requests = Stub(lambda url: Response(True))
        notify.notify("subject", "body", sheet, "someone@example.com")
        urls = " ".join(u for u, _ in notify.requests.calls)
        if "telegram" not in urls or "resend" not in urls:
            failures.append("with both configured, only one was used")

        # ── every channel failing is loud, and still not a job failure ──
        notify.requests = Stub(lambda url: Response(False, 500, "server error"))
        captured = io.StringIO()
        held, sys.stdout = sys.stdout, captured
        code = notify.notify("subject", "body", sheet, "someone@example.com")
        sys.stdout = held
        if code != 0:
            failures.append("a failed notification failed the job, which blames the wrong step")
        if "::warning::" not in captured.getvalue():
            failures.append("a total failure was silent, so nobody would know we stopped watching")

        # ── an exception is handled like any other failure ──
        notify.requests = Stub(lambda url: TimeoutError("timed out"))
        if notify.notify("subject", "body", sheet, "someone@example.com") != 0:
            failures.append("a network exception escaped and failed the job")

        with_env()

    notify.requests = real

    total = 16
    if failures:
        print(f"notify: {len(failures)}/{total} failed")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"notify: {total}/{total} passed (unconfigured, telegram document, long body, "
          f"email attachment, wrong key refused, both channels, loud failure)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
