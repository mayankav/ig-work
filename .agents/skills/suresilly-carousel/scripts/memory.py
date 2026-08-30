#!/usr/bin/env python3
"""
memory.py — what the pipeline remembers.

There is exactly one list worth keeping: the moments we have already used.
Everything else about a moment is disposable, because moments are fetched live
and there are thousands more every day.

We do NOT keep a queue of moments waiting to be used. An earlier design did,
back when the topic bank held 24 fixed rows that had to be rationed. With a live
source there is nothing to ration, and a stockpile only creates a second place
where staleness can hide.

Three files, all under state/ at the repo root, all committed:

  used.jsonl    append-only, one record per moment we consumed. Forever.
  reserve.json  a handful of pre-screened spares, used only when the live fetch
                fails. A safety net, not a stock.
  claim.json    the moment the current run is working on. Written BEFORE any
                generation, so a crashed or repeated run cannot post twice.

Nothing here reads a past carousel. Past decks are compared against by
fingerprint only — see novelty.py — and their text is never loaded back in.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
STATE_DIR = REPO_ROOT / "state"
USED_PATH = STATE_DIR / "used.jsonl"
RESERVE_PATH = STATE_DIR / "reserve.json"
CLAIM_PATH = STATE_DIR / "claim.json"

# How long a claim stays valid. A run that dies mid-way leaves its claim behind;
# the next run past this window treats it as abandoned and moves on. Long enough
# that a slow render never looks dead, short enough that one crash does not block
# the following scheduled run.
CLAIM_TTL_SECONDS = 90 * 60

# How many spares we hold for the case where the live fetch fails. Deliberately
# small: this is a safety net for one missed fetch, not a buffer to draw from.
RESERVE_TARGET = 3


def _now() -> float:
    return time.time()


def normalise(text: str) -> str:
    """Reduce a moment to the form we compare on.

    Two people describing the same 2am waking will not match here, and should
    not — they are different moments. What this catches is the same post reaching
    us twice, and the near-identical reposts that any public feed produces.
    """
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def moment_id(source_ref: str) -> str:
    """Content-addressed id, derived from WHERE the moment came from.

    It is keyed on the source post rather than on the text for one practical
    reason: we need to know whether a candidate is already used BEFORE we spend
    a model call rewriting it, and the rewritten text does not exist yet at that
    point.
    """
    return "m-" + hashlib.sha256(source_ref.encode()).hexdigest()[:16]


def raw_hash(text: str) -> str:
    """A hash of the original wording, so the same post reposted by a different
    account is still recognised as used.

    We keep the hash and never the words. That is the whole point: it lets us
    honour a removal request and catch a repost without holding anything the
    author wrote.
    """
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:24]


@dataclass
class Moment:
    """One screened moment, ready to build a deck from.

    `text` is the moment we invented, never the post it was seeded from.
    `source_hash` is a salted hash of the seed, so a removal request can be
    honoured without us storing the URL or anybody's words.
    """
    id: str
    text: str
    source: str
    source_hash: str
    raw_hash: str
    anchors: dict = field(default_factory=dict)
    score: int = 0
    screened_at: float = field(default_factory=_now)

    @staticmethod
    def make(text: str, source: str, source_ref: str, anchors: dict, score: int) -> "Moment":
        """Build a moment record.

        `text` must already be the rewritten, abstracted version by the time this
        is persisted. Before that step it holds the candidate as fetched, and
        such a record is never written to disk.
        """
        salt = os.environ.get("SS_SOURCE_SALT", "suresilly")
        return Moment(
            id=moment_id(source_ref),
            text=text.strip(),
            source=source,
            source_hash=hashlib.sha256((salt + source_ref).encode()).hexdigest()[:32],
            raw_hash=raw_hash(text),
            anchors=anchors,
            score=score,
        )


# ─────────────────────────── used memory ────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def used_ids() -> set[str]:
    """Every moment id we have ever consumed.

    Loaded as a set of short strings, so this stays cheap no matter how many
    posts we have shipped. At two posts a day for ten years this file is under a
    megabyte.
    """
    return {r["id"] for r in _read_jsonl(USED_PATH)}


def used_raw_hashes() -> set[str]:
    """Hashes of the original wording behind every used moment.

    Catches the same post reaching us again from a different account, which any
    public feed produces constantly.
    """
    return {r["raw_hash"] for r in _read_jsonl(USED_PATH) if r.get("raw_hash")}


def is_used(mid: str) -> bool:
    return mid in used_ids()


def mark_used(moment: Moment, deck_slug: str, mode: str) -> None:
    """Retire a moment.

    Called when a deck is RENDERED, not when it is posted. A deck that was built
    and never published still consumes its moment — otherwise a manual build
    could be repeated later and nobody would notice.

    The record stores the MODE the run was asked for, not whether a post exists.
    It used to store "published", written here, one step before the post was
    attempted — so a --publish run from a laptop, where the slides are not on
    the public host yet and Instagram refuses, left a record claiming the deck
    had gone out. Mode is the honest thing this line actually knows.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "id": moment.id,
        "text": moment.text,
        "raw_hash": moment.raw_hash,
        "source": moment.source,
        "source_hash": moment.source_hash,
        "deck_slug": deck_slug,
        "mode": mode,
        "used_at": _now(),
    }
    with USED_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def used_count() -> int:
    return len(_read_jsonl(USED_PATH))


# ─────────────────────────── reserve ────────────────────────────

def load_reserve() -> list[Moment]:
    if not RESERVE_PATH.is_file():
        return []
    raw = json.loads(RESERVE_PATH.read_text(encoding="utf-8"))
    return [Moment(**r) for r in raw]


def save_reserve(moments: list[Moment]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RESERVE_PATH.write_text(
        json.dumps([asdict(m) for m in moments], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def take_from_reserve() -> Moment | None:
    """Pop one spare, skipping any that were used since it was stored.

    The reserve can go stale: a moment sitting here might get consumed by another
    run that fetched it live. So every spare is re-checked against used memory on
    the way out.
    """
    reserve = load_reserve()
    seen = used_ids()
    while reserve:
        candidate = reserve.pop(0)
        if candidate.id not in seen:
            save_reserve(reserve)
            return candidate
    save_reserve([])
    return None


def top_up_reserve(candidates: list[Moment]) -> int:
    """Fill the reserve back to RESERVE_TARGET from this run's leftovers.

    Costs nothing — these moments were already fetched and screened for this run.
    Returns how many were added.
    """
    reserve = load_reserve()
    have = {m.id for m in reserve} | used_ids()
    added = 0
    for cand in candidates:
        if len(reserve) >= RESERVE_TARGET:
            break
        if cand.id in have:
            continue
        reserve.append(cand)
        have.add(cand.id)
        added += 1
    if added:
        save_reserve(reserve)
    return added


# ─────────────────────────── claim ────────────────────────────

class ClaimHeld(Exception):
    """Another run is working on a moment and its claim has not expired."""


def read_claim() -> dict | None:
    if not CLAIM_PATH.is_file():
        return None
    try:
        return json.loads(CLAIM_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A half-written claim is treated as no claim rather than crashing the
        # run. The worst case is one duplicated attempt, which the used list then
        # rejects.
        return None


def claim(moment: Moment, run_id: str) -> dict:
    """Take the moment for this run.

    Written before a single word is generated. If the run dies after this, the
    claim is what tells the next run that work was in flight, and the used list
    is what stops the moment being consumed twice.
    """
    held = read_claim()
    if held and held.get("expires_at", 0) > _now() and held.get("run_id") != run_id:
        raise ClaimHeld(
            f"moment {held.get('moment_id')} is claimed by run {held.get('run_id')} "
            f"for another {int(held['expires_at'] - _now())}s"
        )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "moment_id": moment.id,
        "run_id": run_id,
        "claimed_at": _now(),
        "expires_at": _now() + CLAIM_TTL_SECONDS,
    }
    CLAIM_PATH.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def release_claim(run_id: str) -> bool:
    """Give the moment back. Called when a run stops without producing a deck.

    A run only releases its own claim, so a slow run cannot have its claim
    cleared by a later one that gave up.
    """
    held = read_claim()
    if not held or held.get("run_id") != run_id:
        return False
    CLAIM_PATH.unlink(missing_ok=True)
    return True
