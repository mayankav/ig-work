"""Shared receipt validation and complete, exclusive writes for post records."""
import json
import os
from pathlib import Path
import tempfile


def valid(value, slug):
    return (isinstance(value, dict) and isinstance(value.get("media_id"), str)
            and value["media_id"].isascii() and value["media_id"].isdigit()
            and bool(slug) and value.get("deck_slug") == slug)


def read(path, slug):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("The publication record is missing or unreadable.") from exc
    if not valid(value, slug):
        raise ValueError("The publication record has an invalid id or names a different deck.")
    return value


def write_new(path, value):
    """Never expose a partial JSON file or overwrite an earlier post record."""
    path = Path(path)
    encoded = json.dumps(value, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".publication-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        # Same-directory hard link is atomic and refuses an existing target,
        # including a broken symlink. rename/replace would overwrite it.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
