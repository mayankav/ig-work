"""The shared local/workflow pause. Reading or dropping held work is allowed."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


class PostingPaused(RuntimeError):
    pass


def pause_reason(halt_file: Path | None = None) -> str | None:
    value = os.environ.get("SS_HALT", "").strip().lower()
    if value not in ("", "0", "false", "no"):
        return "Posting is paused by SS_HALT. Nothing will be posted."
    path = halt_file if halt_file is not None else ROOT / "state/HALT"
    try:
        # Even an unreadable marker or broken symlink is a pause, not permission.
        if path.exists() or path.is_symlink():
            try:
                reason = path.read_text(encoding="utf-8").strip()[:300]
            except (OSError, UnicodeError):
                reason = "the pause marker cannot be read"
            return "Posting is paused by state/HALT: " + (reason or "no reason given")
    except OSError:
        return "Posting is paused because state/HALT cannot be checked."
    return None


def require_posting_allowed(halt_file: Path | None = None) -> None:
    reason = pause_reason(halt_file)
    if reason:
        raise PostingPaused(reason)
