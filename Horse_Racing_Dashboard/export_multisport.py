#!/usr/bin/env python3
"""Export the current NBA / Tennis dashboard feed as versioned JSON."""
import argparse
import json
import sys
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parent
REPO_ROOT = DASHBOARD_DIR.parent
BACKEND_DIR = DASHBOARD_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.multisport_exporter import build_multisport_feed  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Export versioned NBA / Tennis dashboard feed.")
    parser.add_argument("--date", default="", help="Optional YYYY-MM-DD snapshot date.")
    parser.add_argument(
        "--tennis-db",
        default=str(REPO_ROOT / "tennis-wong-choi" / "tennis_wc.db"),
        help="Path to tennis_wc.db.",
    )
    parser.add_argument(
        "--output",
        default=str(DASHBOARD_DIR / "data" / "multisport_feed.json"),
        help="Target JSON path.",
    )
    args = parser.parse_args()

    feed = build_multisport_feed(
        REPO_ROOT,
        target_date=args.date or None,
        tennis_db_path=Path(args.tennis_db),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for sport in ("nba", "tennis"):
        snapshot = feed["sports"][sport]
        print(
            f"{sport.upper()}: {snapshot['validation_status']} · "
            f"{len(snapshot['recommendations'])} recommendations · "
            f"{snapshot['analysis_run_id']}"
        )
        for warning in snapshot.get("warnings", []):
            print(f"  ⚠️ {warning}")
    print(f"Feed: {feed['validation_status']} · {output}")
    if feed["validation_status"] == "blocked":
        for error in feed.get("validation_errors", []):
            print(f"  ❌ {error}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
