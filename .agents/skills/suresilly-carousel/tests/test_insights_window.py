"""Fixed-age reporting, real CLI isolation and no fabricated missing values."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))
import insights
import insights_report

NOW = datetime(2026, 9, 4, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("hours,expected", [(71.999, False), (72, True), (72.999, True), (73, False), (240, False), (-1, False)])
def test_measurement_window_has_exact_boundaries(hours, expected):
    reading = insights.measurement_age(NOW - timedelta(hours=hours), NOW)
    assert reading["comparable"] is expected
    assert reading["age_hours"] == pytest.approx(hours)


@pytest.mark.parametrize("metrics,expected", [
    ({"reach":100,"saved":5,"shares":2}, {"saved_per_reach":.05,"shares_per_reach":.02}),
    ({"reach":100,"saved":0}, {"saved_per_reach":0,"shares_per_reach":None}),
    ({"reach":0,"saved":0,"shares":0}, {"saved_per_reach":None,"shares_per_reach":None}),
    ({"saved":5,"shares":2}, {"saved_per_reach":None,"shares_per_reach":None}),
    ({"reach":100,"saved":True,"shares":float("nan")}, {"saved_per_reach":None,"shares_per_reach":None}),
])
def test_rates_preserve_zero_and_missing(metrics, expected):
    assert insights.rates(metrics) == expected


def test_backlog_cannot_push_timely_reading_out_of_budget():
    decks = [{"media_id":str(n), "published_at":NOW-timedelta(days=10+n)} for n in range(20)]
    decks.append({"media_id":"timely", "published_at":NOW-timedelta(hours=72.5)})
    assert insights.due(decks, set(), now=NOW, limit=1)[0]["media_id"] == "timely"


def test_invalid_numbers_are_missing_not_real_counts():
    data = [{"name":name,"values":[{"value":value}]} for name,value in
            [("reach",100),("saved",-1),("shares",float("inf")),("total_interactions",True)]]
    assert insights.parse_metrics({"data":data}) == {"reach":100}


def test_report_recomputes_age_and_rates_instead_of_trusting_flags(tmp_path):
    path = tmp_path / "readings.jsonl"
    records = [
        {"deck_slug":"timely","published_at":insights._stamp(NOW-timedelta(hours=72.5)),
         "collected_at":insights._stamp(NOW),"comparable":False,
         "metrics":{"reach":100,"saved":5,"shares":0},"rates":{"saved_per_reach":1}},
        {"deck_slug":"late","published_at":insights._stamp(NOW-timedelta(days=10)),
         "collected_at":insights._stamp(NOW),"comparable":True,"metrics":{"reach":100}},
        {"deck_slug":"no time","metrics":{"saved":1}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records))
    before = path.read_bytes()
    rows = insights_report.rows(path)
    assert [r["comparable"] for r in rows] == [True, False, False]
    output = insights_report.report(path)
    assert "| timely | 72.50 | Yes | 100 | 5.00% | 0.00% |" in output
    assert "| late | 240.00 | No | 100 | — | — |" in output
    assert path.read_bytes() == before


def test_fetch_completion_time_decides_window(tmp_path, monkeypatch):
    started = NOW
    finished = NOW + timedelta(minutes=2)
    publication = NOW - timedelta(hours=72, minutes=59)
    path = tmp_path / "state.jsonl"
    monkeypatch.setattr(insights, "published_decks", lambda *a: [
        {"media_id":"1","deck_slug":"one","published_at":publication}])
    monkeypatch.setattr(insights, "fetch", lambda *a: ({"reach":100,"saved":10}, list(insights.METRICS), "test"))
    clock = iter([started, finished])
    monkeypatch.setattr(insights, "_now", lambda: next(clock))
    assert insights.collect("test", state_path=path) == 0
    record = json.loads(path.read_text())
    assert record["comparable"] is False
    assert record["age_hours"] > 73
    assert record["rates"] == {"saved_per_reach":.1,"shares_per_reach":None}
    assert "shares" in record["missing"]


def test_report_imports_no_publisher_or_image_dependencies(tmp_path):
    # -S removes installed packages, matching the reporting job's minimal
    # environment. This catches indirect imports, unlike a source-string test.
    program = """import sys
sys.path.insert(0, sys.argv[1])
import insights_report
blocked = {'post_to_ig','reserve_publication','art_eligibility','numpy','cv2','llm','writer'}
assert not blocked.intersection(sys.modules), blocked.intersection(sys.modules)
print(insights_report.report(__import__('pathlib').Path(sys.argv[2])))
"""
    result = subprocess.run([sys.executable, "-S", "-c", program, str(ROOT / "scripts"),
                             str(tmp_path / "missing.jsonl")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "No saved readings yet" in result.stdout


def test_workflow_collects_hourly_and_reports_separately():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/insights.yml").read_text())
    schedule = workflow.get("on", workflow.get(True))["schedule"]
    assert schedule == [{"cron":"15 * * * *"}]
    report = next(s for s in workflow["jobs"]["collect"]["steps"] if s.get("name") == "Show same-age results")
    assert "insights_report.py" in report["run"]
    for path in (ROOT / ".agents/skills/suresilly-carousel/scripts").glob("*.py"):
        assert "import insights_report" not in path.read_text()


def test_partial_failure_keeps_readings_but_reports_failure(tmp_path, monkeypatch):
    path = tmp_path / "state.jsonl"
    monkeypatch.setattr(insights, "published_decks", lambda *a: [
        {"media_id":str(n),"deck_slug":str(n),"published_at":NOW-timedelta(hours=72.5)}
        for n in range(2)])
    def fetch(media_id, token):
        if media_id == "1": raise insights.InsightsError("test outage")
        return {"reach":10,"saved":1}, list(insights.METRICS), "test"
    monkeypatch.setattr(insights, "fetch", fetch)
    assert insights.collect("test", now=NOW, state_path=path) == 1
    readings = insights._read_jsonl(path)
    assert len(readings) == 1 and readings[0]["media_id"] == "0"
