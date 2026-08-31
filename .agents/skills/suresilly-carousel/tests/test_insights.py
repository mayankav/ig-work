#!/usr/bin/env python3
"""
Insights regression. No network, no token, no credentials of any kind.

Two things are being protected here and only one of them is about metrics.

The first is the ordinary one: a measurement that cannot be trusted must not be
written down. Instagram will answer with a permission refusal, a renamed metric,
a timeout and a 200 carrying nothing, and every one of those means "we did not
check". If any of them lands in state/insights.jsonl as a zero, the ledger stops
being a record and becomes a rumour, and the whole point of collecting numbers
was to stop making them up — `research/05_hooks_database` already did that once.

The second is the one that matters. AGENTS.md invariant 11: the rules decide,
the model writes. Performance data is for a person to read, and the moment it
can reach a gate, a score or a hook chooser, the page stops being about what the
playbook says and starts being about what the algorithm rewarded. That failure
would arrive as a one-line import in some future refactor and would look like an
improvement. So the last block below is a structural test, not a behavioural
one: nothing in the pipeline may import this module, and this module may not
import the pipeline. It fails loudly the first time somebody wires the loop.

Runs both ways, like the rest of the suite: `python test_insights.py` for CI,
and pytest collects test_insights() for anyone who prefers it.
"""
import io
import json
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
SKILL_SCRIPTS = REPO_ROOT / ".agents" / "skills" / "suresilly-carousel" / "scripts"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import insights  # noqa: E402
import post_to_ig  # noqa: E402

NOW = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, status: int, payload: dict, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text or json.dumps(payload)

    def json(self):
        return self._payload


class Stub:
    """Stands in for requests, and records what would have been asked."""

    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.behaviour(len(self.calls), kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ok(metrics: dict) -> Response:
    return Response(200, {"data": [
        {"name": k, "period": "lifetime", "values": [{"value": v}]} for k, v in metrics.items()
    ]})


def graph_error(status: int, code: int, kind: str, message: str) -> Response:
    return Response(status, {"error": {"code": code, "type": kind, "message": message}})


def make_deck(root: pathlib.Path, slug: str, media_id: str, published: datetime) -> pathlib.Path:
    folder = root / slug
    (folder / "slides").mkdir(parents=True, exist_ok=True)
    if media_id is not None:
        (folder / post_to_ig.PUBLISHED_FILENAME).write_text(json.dumps({
            "media_id": media_id,
            "deck_slug": slug,
            "published_at": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }), encoding="utf-8")
    return folder


def run() -> int:
    failures = []
    real = insights.requests

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = pathlib.Path(tmpdir)
        decks_dir = tmp / "carousels"
        state = tmp / "state" / "insights.jsonl"

        settled = make_deck(decks_dir, "20260901_settled", "media-settled", NOW - timedelta(days=4))
        make_deck(decks_dir, "20260904_fresh", "media-fresh", NOW - timedelta(hours=20))
        make_deck(decks_dir, "20260830_older", "media-older", NOW - timedelta(days=9))
        # Built and never posted — no id, so there is nothing to ask about.
        (decks_dir / "20260902_unposted" / "slides").mkdir(parents=True, exist_ok=True)
        # Posted, but the id came back empty. Must not be treated as a deck.
        (decks_dir / "20260831_blank").mkdir(parents=True, exist_ok=True)
        (decks_dir / "20260831_blank" / post_to_ig.PUBLISHED_FILENAME).write_text(
            json.dumps({"media_id": "", "published_at": "2026-08-31T00:00:00Z"}), encoding="utf-8")
        # Unreadable. A warning, not a crash.
        (decks_dir / "20260829_broken").mkdir(parents=True, exist_ok=True)
        (decks_dir / "20260829_broken" / post_to_ig.PUBLISHED_FILENAME).write_text(
            "{not json", encoding="utf-8")

        held, sys.stderr = sys.stderr, io.StringIO()
        found = insights.published_decks(decks_dir)
        sys.stderr = held

        ids = [d["media_id"] for d in found]
        if ids != ["media-older", "media-settled", "media-fresh"]:
            failures.append(f"published_decks read the wrong set, oldest first: {ids}")

        # ── the delay ──
        pending = insights.due(found, set(), now=NOW, min_age_days=insights.MIN_AGE_DAYS)
        if [d["media_id"] for d in pending] != ["media-older", "media-settled"]:
            failures.append("a deck younger than the delay was collected before it settled")
        if insights.due(found, {"media-older", "media-settled"}, now=NOW):
            failures.append("a deck already in the ledger was queued for a second reading")
        if len(insights.due(found, set(), now=NOW, limit=1)) != 1:
            failures.append("the per-run ceiling was ignored, so a first run would ask about everything")
        if insights.due(found, set(), now=NOW, min_age_days=30):
            failures.append("min_age_days had no effect, so the delay cannot be argued with")

        # ── reading the two shapes Meta answers in ──
        both = insights.parse_metrics({"data": [
            {"name": "reach", "values": [{"value": 812}]},
            {"name": "profile_visits", "total_value": {"value": 12}},
            {"name": "saved", "values": []},
            {"name": "shares", "values": [{"value": True}]},
        ]})
        if both != {"reach": 812, "profile_visits": 12}:
            failures.append(f"metric parsing wrong: {both}")
        if "saved" in both or "shares" in both:
            failures.append("a metric with no usable value was defaulted instead of dropped")

        # ── a good run ──
        insights.requests = Stub(lambda n, kw: ok({
            "reach": 800 + n, "saved": 40, "shares": 9,
            "total_interactions": 130, "profile_visits": 12,
        }))
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        code = insights.collect("EAAtoken", now=NOW, carousels_dir=decks_dir, state_path=state)
        sys.stdout, sys.stderr = held_out, held
        rows = [json.loads(l) for l in state.read_text(encoding="utf-8").splitlines() if l.strip()]
        if code != 0:
            failures.append("a successful collection reported failure")
        if len(rows) != 2:
            failures.append(f"expected one line per settled deck, got {len(rows)}")
        first = rows[0] if rows else {}
        for field in ("media_id", "deck_slug", "published_at", "collected_at", "age_days",
                      "host", "variant", "metrics", "missing"):
            if field not in first:
                failures.append(f"the ledger line is missing {field}")
        if first.get("host") != post_to_ig.GRAPH_FACEBOOK:
            failures.append("the record does not say which host answered")
        if set(first.get("metrics", {})) != set(insights.METRICS):
            failures.append("the five metrics we chose are not what was stored")

        # ── append-only ──
        insights.requests = Stub(lambda n, kw: ok({"reach": 1}))
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        insights.collect("EAAtoken", now=NOW, carousels_dir=decks_dir, state_path=state)
        sys.stdout, sys.stderr = held_out, held
        again = [json.loads(l) for l in state.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(again) != 2 or again[:2] != rows:
            failures.append("a repeat run rewrote or re-collected history")

        # ── fail closed: a refusal writes nothing ──
        fresh = tmp / "state" / "closed.jsonl"
        insights.requests = Stub(lambda n, kw: graph_error(500, 1, "OAuthException", "reduce the amount"))
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        code = insights.collect("EAAtoken", now=NOW, carousels_dir=decks_dir, state_path=fresh)
        sys.stdout, sys.stderr = held_out, held
        if fresh.is_file() and fresh.read_text(encoding="utf-8").strip():
            failures.append("a failed fetch was written down, so 'could not check' now reads as 'checked'")
        if code == 0:
            failures.append("a run that collected nothing reported success")

        # ── a 200 with nothing in it is not a reading ──
        insights.requests = Stub(lambda n, kw: Response(200, {"data": []}))
        try:
            insights.fetch("media-settled", "EAAtoken")
            failures.append("an empty 200 was accepted as a measurement")
        except insights.InsightsError:
            pass
        if len(insights.requests.calls) != 3:
            failures.append("an empty answer did not fall through to the other metric shapes")

        # ── a renamed metric falls through, a refusal does not ──
        insights.requests = Stub(lambda n, kw: (
            graph_error(400, 100, "GraphMethodException", "(#100) metric is not supported")
            if n == 1 else ok({"reach": 5})))
        metrics, _, variant = insights.fetch("media-settled", "EAAtoken")
        if metrics != {"reach": 5} or variant != "full+total_value":
            failures.append("an unsupported metric did not fall back to the next shape")

        insights.requests = Stub(lambda n, kw: graph_error(
            400, 190, "OAuthException", "Insufficient permission: instagram_manage_insights"))
        try:
            insights.fetch("media-settled", "EAAtoken")
            failures.append("a permission refusal was swallowed instead of raised")
        except insights.ScopeError:
            pass
        except insights.InsightsError:
            failures.append("a permission refusal was misread as an ordinary error")
        if len(insights.requests.calls) != 1:
            failures.append("a refusal was retried in another shape, which is still a refusal")

        # ── a timeout is 'we did not check', not 'zero' ──
        insights.requests = Stub(lambda n, kw: TimeoutError("timed out"))
        try:
            insights.fetch("media-settled", "EAAtoken")
            failures.append("a network exception escaped as a successful reading")
        except insights.InsightsError:
            pass

        # ── the missing scope is explained where somebody is looking ──
        insights.requests = Stub(lambda n, kw: graph_error(
            400, 190, "OAuthException", "Insufficient permission"))
        blank = tmp / "state" / "scope.jsonl"
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        code = insights.collect("EAAtoken", now=NOW, carousels_dir=decks_dir, state_path=blank)
        printed = sys.stderr.getvalue()
        sys.stdout, sys.stderr = held_out, held
        if code == 0:
            failures.append("a token with no insights permission reported a clean run")
        if "instagram_manage_insights" not in printed:
            failures.append("the scope failure did not name the permission to add")
        if "IG_ACCESS_TOKEN" not in printed:
            failures.append("the scope failure did not say where the new token goes")
        if len(insights.requests.calls) != 1:
            failures.append("every due deck was asked again after the first refusal")

        # ── the instructions match the host the token selects ──
        fb, ig = insights.scope_help("EAAxxxx"), insights.scope_help("IGAAPxxxx")
        if "instagram_manage_insights" not in fb or "graph.facebook.com" not in fb:
            failures.append("a Facebook Login token was given the wrong scope or host")
        if "instagram_business_manage_insights" not in ig or "graph.instagram.com" not in ig:
            failures.append("an Instagram Login token was given the wrong scope or host")
        if "instagram_business_manage_insights" in fb:
            failures.append("both scopes were offered at once, so neither is the instruction")

        # ── no token: nothing checked, nothing written ──
        insights.requests = Stub(lambda n, kw: ok({"reach": 1}))
        empty = tmp / "state" / "notoken.jsonl"
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        code = insights.collect("", now=NOW, carousels_dir=decks_dir, state_path=empty)
        sys.stdout, sys.stderr = held_out, held
        if code == 0 or empty.is_file() or insights.requests.calls:
            failures.append("an unconfigured token still called out or wrote a line")

        # ── --dry-run calls nothing ──
        insights.requests = Stub(lambda n, kw: ok({"reach": 1}))
        dry = tmp / "state" / "dry.jsonl"
        held, sys.stderr = sys.stderr, io.StringIO()
        held_out, sys.stdout = sys.stdout, io.StringIO()
        code = insights.collect("EAAtoken", now=NOW, carousels_dir=decks_dir,
                                state_path=dry, dry_run=True)
        sys.stdout, sys.stderr = held_out, held
        if code != 0 or dry.is_file() or insights.requests.calls:
            failures.append("--dry-run called the API or wrote a file")

    insights.requests = real

    # ───────────── invariant 11: this can never become an approval path ─────────────
    #
    # Structural, because the behavioural version of this test cannot exist: the
    # defect is a future import, not a wrong answer.
    source = (REPO_ROOT / "scripts" / "insights.py").read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and any(
            name in stripped for name in ("run", "compose", "writer", "critic", "screen",
                                          "novelty", "selection", "discovery", "safety",
                                          "coherence", "memory", "bibliography")
        ):
            # post_to_ig is a repo-root script, not the pipeline, and is allowed.
            if "post_to_ig" not in stripped:
                failures.append(f"insights.py imports the pipeline: {stripped}")

    for path in sorted(SKILL_SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import insights", "from insights")):
                failures.append(f"{path.name} imports insights — that is the feedback loop "
                                "invariant 11 forbids")

    if "MUST NEVER BECOME ONE" not in source:
        failures.append("the module docstring no longer forbids the approval path, so the "
                        "next person has nothing telling them not to build it")

    total = 30
    if failures:
        print(f"insights: {len(failures)} failed of {total}")
        for line in failures:
            print(f"  {line}")
        return 1
    print(f"insights: {total}/{total} passed (deck discovery, the three-day delay, both metric "
          f"shapes, append-only ledger, fail-closed on refusal/timeout/empty 200, scope "
          f"instructions per host, no-token, dry-run, and invariant 11 held structurally)")
    return 0


def test_insights():
    """pytest entry point. Same body, same assertions."""
    assert run() == 0


if __name__ == "__main__":
    raise SystemExit(run())
