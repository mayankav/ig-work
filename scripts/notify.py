#!/usr/bin/env python3
"""
notify.py — tell the owner what the run did.

In a pipeline nobody supervises, this is the only window into it. If a deck goes
out wrong, this message is how anyone finds out before opening Instagram. So it
carries the contact sheet, not just a line of text: the nine tiles together are
what you actually judge a deck on.

Two channels, both attempted, because they fail differently.

  Telegram  the alert. Free with no cap, arrives on a phone in seconds, no
            sending domain, and nothing to get filtered into spam.
  Resend    the archive. Slower and quieter, but searchable in a year, and it
            survives a messaging app being unavailable.

Sent to both rather than one falling back to the other. At four messages a day
neither costs anything, and a channel that only runs when the other has already
failed is a channel nobody notices is broken.

The old Cloudflare path is gone. It posted to an endpoint that does not exist
and reported success, which is the worst way for a notification path to fail:
silently, while looking fine.

Nothing here fails the workflow. The post has already happened by the time this
runs, so failing the job would be a lie about what went wrong. A failure prints
a GitHub warning instead, which shows up on the run without pretending the run
was bad.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

TIMEOUT = 30
# Telegram caps a media caption at 1024 characters and a plain message at 4096.
# It does NOT truncate an over-long caption — it rejects the whole call with
# "Bad Request: message is too long", so the report would not arrive at all.
# 1000 leaves headroom, and the rest is sent as a follow-up message.
CAPTION_LIMIT = 1000


def split_for_caption(text: str, limit: int = CAPTION_LIMIT) -> tuple[str, str]:
    """Break a report into a caption and a follow-up, AT A LINE BOUNDARY.

    The overflow was always sent on, so nothing was ever lost. What was lost was
    the line the cut landed in. The dashboard reports figures like

        groq       61/1000 requests    ▓░░░░░░░░░  full again in 13.3h

    and a blind cut at character 1000 can end the caption at "61/10", which is
    not a truncated number but a different and wholly believable one. Splitting
    on the last newline that fits means a line is either shown or is in the next
    message, and never both.

    A single line longer than the limit has no boundary to find, so it is cut
    where it must be. That is the one case where there is no better answer.
    """
    if len(text) <= limit:
        return text, ""
    window = text[:limit]
    cut = window.rfind("\n")
    if cut <= 0:
        return window, text[limit:]
    return text[:cut].rstrip(), text[cut:].lstrip("\n")


def _env(name: str) -> str:
    """Read a variable, treating empty as unset.

    A workflow that passes a secret which was never created sets the variable to
    an empty string rather than leaving it out. Without this, an unset EMAIL_FROM
    becomes a sender address of "", which the API rejects with an error that
    looks nothing like the missing secret it actually is.
    """
    return os.environ.get(name, "").strip()


def _telegram(subject: str, body: str, attach: Path | None) -> tuple[bool, str]:
    """Send via a bot.

    sendDocument, not sendPhoto. sendPhoto recompresses, and the contact sheet is
    the thing you squint at to decide whether nine slides read as one deck.
    """
    token = _env("TELEGRAM_BOT_TOKEN")
    chat = _env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False, "not configured"

    text = f"{subject}\n\n{body}".strip()
    base = f"https://api.telegram.org/bot{token}"
    try:
        if attach and attach.is_file():
            caption, rest = split_for_caption(text)
            with attach.open("rb") as handle:
                response = requests.post(
                    f"{base}/sendDocument",
                    data={"chat_id": chat, "caption": caption},
                    files={"document": (attach.name, handle, "image/png")},
                    timeout=TIMEOUT)
            if response.ok and rest:
                requests.post(f"{base}/sendMessage",
                              data={"chat_id": chat, "text": rest[:4000]},
                              timeout=TIMEOUT)
        else:
            response = requests.post(f"{base}/sendMessage",
                                     data={"chat_id": chat, "text": text[:4000]},
                                     timeout=TIMEOUT)
        if response.ok:
            return True, "sent"
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _resend(subject: str, body: str, attach: Path | None, to: str) -> tuple[bool, str]:
    """Send via Resend.

    The default sender needs no domain and no DNS, because it only delivers to
    the account owner. That is normally a limitation and here it is exactly the
    shape of the job: one recipient, who owns the account.
    """
    key = _env("RESEND_API_KEY") or _env("EMAIL_API_KEY")
    if not key:
        return False, "not configured"
    if not key.startswith("re_"):
        return False, "the key is not a Resend key, which is the only email path"

    payload = {
        # The default sender needs no domain and no DNS. It only delivers to the
        # account owner, which is exactly the shape of this job.
        "from": _env("EMAIL_FROM") or "onboarding@resend.dev",
        "to": [to],
        "subject": subject,
        "text": body,
    }
    if attach and attach.is_file():
        payload["attachments"] = [{
            "filename": attach.name,
            "content": base64.b64encode(attach.read_bytes()).decode(),
        }]
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload, timeout=TIMEOUT)
        if response.ok:
            return True, "sent"
        return False, f"HTTP {response.status_code}: {response.text[:160]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def notify(subject: str, body: str, attach: Path | None, to: str) -> int:
    """Send on every configured channel. Returns a process exit code."""
    if requests is None:
        print("::warning::notify: the requests package is missing, nothing was sent")
        return 0

    results = {
        "telegram": _telegram(subject, body, attach),
        "email": _resend(subject, body, attach, to),
    }

    configured = {name: r for name, r in results.items() if r[1] != "not configured"}
    for name, (ok, note) in results.items():
        print(f"  {name:9} {'sent' if ok else note}")

    if not configured:
        # Not an error. It is how this behaves before anything is set up, and it
        # prints the message so a local run still shows what would have gone out.
        print("\n[nothing configured] the message was not sent anywhere\n")
        print(f"subject: {subject}\n{body}")
        if attach and attach.is_file():
            print(f"attachment: {attach}")
        return 0

    if not any(ok for ok, _ in configured.values()):
        # The run itself was fine, so this does not fail the job. It is loud
        # instead, because the alternative is a system nobody is watching and a
        # notification path nobody knows is broken.
        print("::warning::notify: every configured channel failed, so this run went unreported")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Tell the owner what the run did.")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", default="")
    ap.add_argument("--attach", help="usually the contact sheet")
    ap.add_argument("--to", default=_env("EMAIL_TO") or "mayankmacav@gmail.com")
    args = ap.parse_args()

    body = args.body
    if not body and not sys.stdin.isatty():
        body = sys.stdin.read()

    raise SystemExit(notify(args.subject, body, Path(args.attach) if args.attach else None,
                            args.to))


if __name__ == "__main__":
    main()
