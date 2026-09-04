"""Read-only, fixed-age performance report. Never consumed by generation."""
import argparse
from pathlib import Path

import insights


def rows(path: Path) -> list[dict]:
    result = []
    for record in insights._read_jsonl(path):
        published = insights._parse_stamp(str(record.get("published_at") or ""))
        collected = insights._parse_stamp(str(record.get("collected_at") or ""))
        age = insights.measurement_age(published, collected) if published and collected else {}
        metrics = record.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}
        result.append({"deck": str(record.get("deck_slug") or record.get("media_id") or "unknown"),
                       "age_hours": age.get("age_hours"),
                       "comparable": age.get("comparable", False),
                       "metrics": {name: metrics.get(name) if insights.number(metrics.get(name)) else None
                                   for name in insights.METRICS},
                       "rates": insights.rates(metrics)})
    return result


def report(path: Path) -> str:
    records = rows(path)
    if not records:
        return "# Post results\n\nNo saved readings yet. No performance claim can be made.\n"
    lines = ["# Post results", "", "Compare only readings taken from 72 to under 73 hours after posting.",
             "Late readings are retained, not treated as three-day results. — means unavailable.", "",
             "| Post | Age (hours) | Same-age reading | Reach | Saves / reach | Shares / reach |",
             "|---|---:|---|---:|---:|---:|"]
    for row in records:
        age = "—" if row["age_hours"] is None else f"{row['age_hours']:.2f}"
        reach = "—" if row["metrics"]["reach"] is None else str(row["metrics"]["reach"])
        fractions = ["—" if value is None else f"{100*value:.2f}%" for value in row["rates"].values()]
        # A table cell cannot inject another row or column.
        deck = row["deck"].replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(f"| {deck} | {age} | {'Yes' if row['comparable'] else 'No'} | {reach} | {' | '.join(fractions)} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=insights.INSIGHTS_PATH)
    args = parser.parse_args()
    print(report(args.state), end="")


if __name__ == "__main__":
    main()
