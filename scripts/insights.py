#!/usr/bin/env python3
"""
insights.py — ask Instagram how a deck actually did, and write it down.

The engine published for weeks and learned nothing. There was no measurement
loop at all, and `research/05_hooks_database` filled the hole by inventing an
"Engagement Indicator" column, on the reasoning that Instagram does not publish
saves or shares to anyone but the owner. That is true of other people's
accounts. It is not true of this one. We are the owner, and
`GET /{ig-media-id}/insights` returns the real numbers to the token this repo
already holds.

    THIS IS NOT AN APPROVAL PATH, AND MUST NEVER BECOME ONE.

    Invariant 11 says the rules decide and the model writes: the pipeline picks
    the moment, the angle and the citation, and code decides whether a deck
    ships. Performance data is something a HUMAN reads. It must never feed back
    into hook selection, scoring, screening, novelty, the critic, or any gate.
    Nothing in run.py may import this module, and nothing here may import the
    skill's scripts. tests/test_insights.py locks that in both directions, and
    the reason is not squeamishness about metrics — it is that a loop from
    "this hook got saves" back into "write more of that hook" is exactly the
    loop that turns a page about relational psychology into a page about
    whatever Instagram rewarded last Tuesday, with no person in the decision.

    If you want the numbers to change what gets written: read them, think, and
    edit the playbook by hand. That is the intended path. It has a human in it.

WHAT IT READS
    carousels/<slug>/published.json — written by post_to_ig.py at the moment of
    publication. Decks shipped before that existed carry no media id and are
    invisible here; there is no way to recover one, and no attempt is made to
    guess.

WHAT IT WRITES
    state/insights.jsonl — append-only, one line per successful collection, in
    the same house style as state/used.jsonl (see the skill's memory.py). History
    is never overwritten and never rewritten. A media id already in the file is
    never collected twice, so a missed cron run backfills and a repeated run is
    a no-op.

FAIL CLOSED
    "We could not check" must never come out looking like "we checked". A failed
    or partial fetch writes NOTHING. A metric the API did not return is recorded
    in `missing`, never as a zero — a zero is a real measurement and an absent
    metric is not.

THE SCOPE THE TOKEN DOES NOT HAVE YET
    Media insights need one permission beyond posting, and which one depends on
    which of the two API hosts post_to_ig.graph_base() picks for the token:

      graph.facebook.com  (Facebook Login, token starts EAA)
          → instagram_manage_insights
      graph.instagram.com (Instagram Login, token starts IGAAP)
          → instagram_business_manage_insights

    Until it is added, every call here fails with an OAuth error. That case is
    detected and printed with the exact steps to fix it — see scope_help(). This
    module has therefore never been run end to end against a live token; it is
    built to be honest about that rather than to look like it worked.

Usage:
  python scripts/insights.py                     # collect what is due
  python scripts/insights.py --dry-run           # list what is due, call nothing
  python scripts/insights.py --min-age-days 7    # widen the delay for one run
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover - the workflow installs it
    requests = None

# Share only API identifiers, never import the publisher and its image engine.
# The reporting workflow installs requests alone and must remain independent.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import instagram_api  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CAROUSELS_DIR = REPO_ROOT / "carousels"
STATE_DIR = REPO_ROOT / "state"
INSIGHTS_PATH = STATE_DIR / "insights.jsonl"

# The five the account owner can actually act on.
#
#   reach               how many people saw it at all. The denominator; without
#                       it every other number is unreadable.
#   saved               the one signal this format is built for. A carousel is
#                       read slowly and kept, and a save is the strongest thing
#                       a reader does short of sharing.
#   shares              the only metric that describes reach we did not buy with
#                       the algorithm's goodwill — somebody handed it to someone.
#   total_interactions  likes + comments + saves + shares in one figure, so a
#                       deck can be compared with a deck without adding up four.
# Deliberately not collected: impressions and views (inflated by repeat serving
# and not a decision anybody makes), follows (too sparse per post to read), and
# per-child breakdowns (a slide-level number invites exactly the optimisation
# loop the docstring above forbids).
#
# profile_visits was here and has been removed. Meta documents it as an ACCOUNT
# metric, on /{ig-user-id}/insights, not a media one — it counts visits to the
# profile over a period, and there is no per-post version of it to ask for. The
# ladder below would have swallowed the mistake by falling through to CORE, so
# the numbers would have been right and two requests a deck would have been
# wasted proving it. If the account-level figure is ever wanted it is a second
# endpoint and a different record, not a column on a deck.
METRICS = ("reach", "saved", "shares", "total_interactions")

# What we fall back to if the API refuses the full list. Identical to METRICS
# today, and kept separate on purpose: METRICS is what we would like and CORE is
# what has been a media metric across every recent API version. When the first
# grows again — and it will, Meta keeps moving these — the floor should not move
# with it.
CORE_METRICS = ("reach", "saved", "shares", "total_interactions")

# How long a deck ages before we ask.
#
# Three days is a reporting policy, not a claim that engagement has finished.
# Lifetime counters are sampled in one hourly window; a missed window cannot
# be reconstructed later. Keep late observations but label them honestly.
MIN_AGE_DAYS = 3.0
TARGET_AGE_HOURS = 72
WINDOW_HOURS = 1

# A ceiling on calls per run. The backlog on a first run is every deck ever
# published; there is no hurry, and the next run takes the next batch.
MAX_PER_RUN = 8

TIMEOUT = 30


class InsightsError(Exception):
    """A fetch that did not produce a trustworthy reading."""


class ScopeError(InsightsError):
    """The token is not allowed to read insights. A human has to fix this."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_stamp(text: str) -> datetime | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def measurement_age(published_at: datetime, collected_at: datetime) -> dict:
    hours = (collected_at - published_at).total_seconds() / 3600
    return {"age_hours": hours, "target_age_hours": TARGET_AGE_HOURS,
            "window_hours": WINDOW_HOURS,
            "comparable": TARGET_AGE_HOURS <= hours < TARGET_AGE_HOURS + WINDOW_HOURS}


def number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def rates(metrics: dict) -> dict:
    reach = metrics.get("reach")
    return {f"{name}_per_reach": (metrics[name] / reach
            if number(reach) and reach > 0 and number(metrics.get(name)) else None)
            for name in ("saved", "shares")}


# ─────────────────────────── what has been published ────────────────────────────

def published_decks(carousels_dir: Path | None = None) -> list[dict]:
    """Every deck that recorded a media id, oldest first.

    A folder without published.json is a deck that was built and not posted, or
    was posted before post_to_ig started writing the file. Either way there is
    no id, so there is nothing to ask about.
    """
    root = carousels_dir or CAROUSELS_DIR
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.glob("*/" + instagram_api.PUBLISHED_FILENAME)):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"::warning::unreadable {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(record, dict):
            continue
        media_id = str(record.get("media_id") or "").strip()
        published_at = _parse_stamp(str(record.get("published_at") or ""))
        if not media_id or published_at is None:
            print(f"::warning::{path} has no usable media id or timestamp", file=sys.stderr)
            continue
        out.append({
            "media_id": media_id,
            "deck_slug": str(record.get("deck_slug") or path.parent.name),
            "published_at": published_at,
        })
    out.sort(key=lambda d: d["published_at"])
    return out


# ─────────────────────────── the ledger ────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                record = json.loads(line)
                if isinstance(record, dict):
                    out.append(record)
            except ValueError:
                print(f"::warning::skipping an unparseable line in {path}", file=sys.stderr)
    return out


def collected_ids(path: Path | None = None) -> set[str]:
    """Media ids already in the ledger.

    Only successful collections are ever written, so membership here means the
    numbers exist and there is no reason to spend a call asking again.
    """
    return {r["media_id"] for r in _read_jsonl(path or INSIGHTS_PATH) if r.get("media_id")}


def append_record(record: dict, path: Path | None = None) -> None:
    """Append one line. Never rewrites, never truncates."""
    target = path or INSIGHTS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ─────────────────────────── what is due ────────────────────────────

def due(
    decks: list[dict],
    already: set[str],
    now: datetime | None = None,
    min_age_days: float = MIN_AGE_DAYS,
    limit: int = MAX_PER_RUN,
) -> list[dict]:
    """Decks old enough to have settled and not yet in the ledger.

    Age, not "yesterday's deck": a cron run that never happened must be able to
    catch up, and a run that happens twice must not double-collect.
    """
    when = now or _now()
    out = []
    for deck in decks:
        if deck["media_id"] in already:
            continue
        age = (when - deck["published_at"]).total_seconds() / 86400.0
        if age < min_age_days:
            continue
        deck = dict(deck)
        deck["age_days"] = round(age, 2)
        out.append(deck)
    # Timely readings first. Old backlog must not consume the current window.
    out.sort(key=lambda d: (not measurement_age(d["published_at"], when)["comparable"],
                            d["published_at"]))
    return out[:limit]


# ─────────────────────────── the call ────────────────────────────

def _classify(payload: dict, status: int, body: str) -> InsightsError:
    error = payload.get("error") if isinstance(payload, dict) else None
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    kind = str(error.get("type") or "")
    message = str(error.get("message") or body)[:400]
    blob = f"{kind} {message}".lower()
    permission_words = ("permission", "scope", "not authorized", "not been granted")
    if code in (10, 190, 200, 803) or kind in ("OAuthException", "IGApiException") or any(
        w in blob for w in permission_words
    ):
        return ScopeError(f"HTTP {status} code={code} type={kind}: {message}")
    return InsightsError(f"HTTP {status} code={code} type={kind}: {message}")


def parse_metrics(payload: dict) -> dict:
    """Pull the numbers out of whichever shape the API answered in.

    Graph returns `values: [{value: n}]` for lifetime metrics and
    `total_value: {value: n}` when asked with metric_type=total_value. Both
    shapes are read; a row with neither is dropped rather than defaulted, so it
    lands in `missing` instead of pretending to be a zero.
    """
    out: dict[str, int | float] = {}
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name:
            continue
        value = None
        values = row.get("values")
        if isinstance(values, list) and values and isinstance(values[0], dict):
            value = values[0].get("value")
        if value is None and isinstance(row.get("total_value"), dict):
            value = row["total_value"].get("value")
        if number(value):
            out[str(name)] = value
    return out


def fetch(media_id: str, token: str) -> tuple[dict, list[str], str]:
    """Ask for one deck's numbers. Returns (metrics, requested, variant).

    Three attempts, because Meta has moved these metrics between shapes more
    than once and a run that dies on a renamed field teaches nobody anything.
    A permission error stops the ladder immediately — retrying a refusal in a
    different shape is still a refusal, and it makes the log harder to read.

    Raises InsightsError if nothing came back, so the caller writes nothing.
    """
    if requests is None:
        raise InsightsError("requests is not installed")
    base = instagram_api.graph_base(token)
    attempts = [
        ("full", METRICS, {}),
        ("full+total_value", METRICS, {"metric_type": "total_value"}),
    ]
    # Only worth a third request when CORE is actually narrower than METRICS.
    # They are the same list today, and asking twice for the same thing is how a
    # ladder quietly turns into a retry loop.
    if set(CORE_METRICS) < set(METRICS):
        attempts.append(("core", CORE_METRICS, {}))
    last: InsightsError = InsightsError("no attempt was made")
    for variant, metrics, extra in attempts:
        params = {"metric": ",".join(metrics), "access_token": token, **extra}
        try:
            r = requests.get(f"{base}/{media_id}/insights", params=params, timeout=TIMEOUT)
        except Exception as exc:  # network, DNS, timeout — all mean "we did not check"
            last = InsightsError(f"{type(exc).__name__}: {exc}")
            continue
        try:
            payload = r.json()
        except ValueError:
            payload = {}
        if r.status_code != 200:
            last = _classify(payload, r.status_code, getattr(r, "text", ""))
            if isinstance(last, ScopeError):
                raise last
            continue
        parsed = parse_metrics(payload)
        if not parsed:
            last = InsightsError(f"{variant}: 200 with no readable metric")
            continue
        return parsed, list(metrics), variant
    raise last


# ─────────────────────────── the manual step ────────────────────────────

def scope_help(token: str) -> str:
    """The exact thing the owner has to do, named for the host in use.

    Printed on a permission failure rather than buried in a README, because the
    run that fails is the moment somebody is looking.
    """
    instagram_login = instagram_api.graph_base(token) == instagram_api.GRAPH_INSTAGRAM
    if instagram_login:
        host, scope = "graph.instagram.com", "instagram_business_manage_insights"
        steps = [
            "developers.facebook.com → My Apps → your app → Instagram → "
            "API setup with Instagram business login.",
            "Open step 3, 'Set up Instagram business login' → Business login settings.",
            f"Add {scope} to the list of permissions the login requests, and save.",
            "Back in step 2, 'Generate access tokens', re-generate the token for the "
            "connected Instagram account and accept the new permission when asked.",
            "Copy the new IGAAP… token.",
        ]
    else:
        host, scope = "graph.facebook.com", "instagram_manage_insights"
        steps = [
            "developers.facebook.com → My Apps → your app → Tools → Graph API Explorer.",
            "Select the app, then 'Get User Access Token'.",
            f"Tick {scope} in the permission list alongside the ones already "
            "there (instagram_basic and instagram_content_publish), then Generate Access Token.",
            "Accept the new permission in the dialog, choosing the same Page and "
            "Instagram account the engine posts to.",
            "Exchange the short-lived token for a long-lived one: Tools → Access Token "
            "Debugger → paste it → Debug → Extend Access Token. Copy the extended token.",
        ]
    steps.append(
        "GitHub → this repo → Settings → Secrets and variables → Actions → "
        "update IG_ACCESS_TOKEN with the new token."
    )
    steps.append(
        "Re-run this workflow (Actions → insights → Run workflow). The backlog is "
        "collected by age, so nothing published in the meantime was lost."
    )
    lines = [
        "",
        "─" * 72,
        f"The token cannot read insights yet. It is a {host} token, so it needs:",
        f"    {scope}",
        "",
        "Nothing here can add it — that is a human step in Meta's UI, and this",
        "script will not attempt an authorisation flow. Do this once:",
        "",
    ]
    lines += [f"  {i}. {s}" for i, s in enumerate(steps, 1)]
    lines += [
        "",
        "No permission beyond this one is needed, and posting is unaffected: the",
        "new token carries the publishing scopes it already had.",
        "─" * 72,
        "",
    ]
    return "\n".join(lines)


# ─────────────────────────── the run ────────────────────────────

def collect(
    token: str,
    now: datetime | None = None,
    min_age_days: float = MIN_AGE_DAYS,
    limit: int = MAX_PER_RUN,
    dry_run: bool = False,
    carousels_dir: Path | None = None,
    state_path: Path | None = None,
) -> int:
    """Collect what is due. Returns a process exit code."""
    path = state_path or INSIGHTS_PATH
    decks = published_decks(carousels_dir)
    pending = due(decks, collected_ids(path), now=now, min_age_days=min_age_days, limit=limit)
    print(f"{len(decks)} deck(s) carry a media id, {len(pending)} due at {min_age_days}+ days old")

    if not pending:
        print("nothing due — this is the ordinary outcome most days")
        return 0

    if dry_run:
        for deck in pending:
            print(f"  would ask about {deck['deck_slug']} ({deck['media_id']}, {deck['age_days']}d)")
        return 0

    if not token:
        print("IG_ACCESS_TOKEN is not set — nothing was checked and nothing was written",
              file=sys.stderr)
        return 1

    written = failed = 0
    for deck in pending:
        try:
            metrics, requested, variant = fetch(deck["media_id"], token)
        except ScopeError as exc:
            # One refusal is every refusal. Stop, and say what to do about it.
            print(f"::error::insights refused for {deck['deck_slug']}: {exc}", file=sys.stderr)
            print(scope_help(token), file=sys.stderr)
            return 1
        except InsightsError as exc:
            # Fail closed: no record, no zeros, no guess.
            print(f"::warning::no reading for {deck['deck_slug']}: {exc}", file=sys.stderr)
            failed += 1
            continue
        missing = [m for m in requested if m not in metrics]
        collected_at = now or _now()
        record = {
            "media_id": deck["media_id"],
            "deck_slug": deck["deck_slug"],
            "published_at": _stamp(deck["published_at"]),
            "collected_at": _stamp(collected_at),
            "age_days": (collected_at - deck["published_at"]).total_seconds() / 86400,
            **measurement_age(deck["published_at"], collected_at),
            "rates": rates(metrics),
            "host": instagram_api.graph_base(token),
            "variant": variant,
            "metrics": metrics,
            "missing": missing,
        }
        # Written one at a time, so a failure on the fourth deck cannot lose the
        # three readings before it.
        append_record(record, path)
        written += 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(metrics.items()))
        print(f"  {deck['deck_slug']}: {summary}" + (f"  (missing: {', '.join(missing)})" if missing else ""))

    print(f"wrote {written} record(s) to {path}, {failed} deck(s) had no trustworthy reading")
    return 1 if failed or written == 0 else 0


def check_token(token: str) -> int:
    """Prove the token works and carries the insights permission. Reads nothing
    of ours and writes nothing.

    This exists because the ordinary run cannot tell you. It only looks at decks
    that already carry a media id, so on a fresh install it exits before making
    a single call and reports success — which says nothing at all about whether
    the secret in GitHub is the right string. A permission is added to the app
    in one place and carried by a token minted in another, and a token issued
    before the permission existed does not have it. That gap is invisible until
    the first deck comes due, days later.

    So: ask the account who it is, borrow its newest post, and ask for that
    post's numbers. If all three answer, the loop will work when a deck is due.

    The token is never printed. Neither is anything that could reconstruct it.
    """
    if requests is None:
        print("::error::requests is not installed")
        return 1
    if not token:
        print("::error::IG_ACCESS_TOKEN is not set")
        return 1

    base = instagram_api.graph_base(token)
    kind = ("Instagram login" if base == instagram_api.GRAPH_INSTAGRAM
            else "Facebook login")
    print(f"host {base}  ({kind} token)")

    try:
        r = requests.get(f"{base}/me", params={"fields": "id,username",
                                               "access_token": token}, timeout=30)
        body = r.json() if r.content else {}
    except Exception as exc:                                  # noqa: BLE001
        print(f"::error::could not reach the API: {exc}")
        return 1
    if r.status_code != 200:
        print(f"::error::the token was refused: {_classify(body, r.status_code, r.text)}")
        print(scope_help(token))
        return 1
    print(f"token is valid for @{body.get('username', '?')} (id {body.get('id', '?')})")

    try:
        r = requests.get(f"{base}/me/media",
                         params={"fields": "id,timestamp,media_type", "limit": 1,
                                 "access_token": token}, timeout=30)
        media = (r.json() or {}).get("data", []) if r.status_code == 200 else []
    except Exception as exc:                                  # noqa: BLE001
        print(f"::error::could not list media: {exc}")
        return 1
    if not media:
        print("the account has no posts yet, so the permission cannot be proved "
              "here. It will be proved by the first deck that comes due.")
        return 0

    newest = media[0]
    print(f"newest post {newest.get('media_type', '?')} from {newest.get('timestamp', '?')}")
    try:
        metrics, _, variant = fetch(newest["id"], token)
    except InsightsError as why:
        print(f"::error::the insights permission is missing or not yet live: {why}")
        print(scope_help(token))
        return 1

    got = ", ".join(f"{k}={v}" for k, v in sorted(metrics.items()))
    print(f"insights permission works ({variant}): {got}")
    print("nothing was written. The scheduled run collects a deck three days "
          "after it posts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect Instagram insights for published decks.")
    ap.add_argument("--min-age-days", type=float, default=MIN_AGE_DAYS,
                    help=f"how long a deck ages before we ask (default {MIN_AGE_DAYS})")
    ap.add_argument("--limit", type=int, default=MAX_PER_RUN,
                    help=f"most decks to ask about in one run (default {MAX_PER_RUN})")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what is due and call nothing")
    ap.add_argument("--check-token", action="store_true",
                    help="prove the token works and carries the insights "
                         "permission, using the account's newest post. Writes "
                         "nothing and reads none of our state")
    args = ap.parse_args(argv)
    if args.check_token:
        return check_token(os.getenv("IG_ACCESS_TOKEN", ""))
    return collect(
        token=os.getenv("IG_ACCESS_TOKEN", ""),
        min_age_days=args.min_age_days,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
