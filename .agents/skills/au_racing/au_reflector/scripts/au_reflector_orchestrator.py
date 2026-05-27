#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[5]
SHARED_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "race_reflector" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from unified_reflector_core import default_report_path, run_unified_reflector


def main() -> int:
    parser = argparse.ArgumentParser(description="AU reflector orchestrator (unified workflow wrapper)")
    parser.add_argument("meeting_dir", help="AU meeting directory")
    parser.add_argument("results_file", nargs="?", help="Optional existing results file")
    parser.add_argument("--results-url", help="Optional AU results URL for extraction")
    parser.add_argument("--race", dest="races", action="append", type=int, help="Reflect only specific race numbers")
    parser.add_argument("--report-path", help="Optional output path for markdown report")
    parser.add_argument("--force-extract", action="store_true", help="Force extraction even if results already exist")
    parser.add_argument("--skip-backtest", action="store_true", help="Skip archive backtest")
    parser.add_argument("--json", action="store_true", help="Emit final summary JSON")
    args = parser.parse_args()

    meeting_path = Path(args.meeting_dir).resolve()
    summary = run_unified_reflector(
        platform="au",
        meeting_dir=meeting_path,
        results_file=args.results_file,
        results_url=args.results_url,
        target_races=args.races,
        report_path=args.report_path or str(default_report_path("au", meeting_path)),
        force_extract=args.force_extract,
        skip_backtest=args.skip_backtest,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n🏁 AU unified reflector complete")
        print(f"- Meeting: {meeting_path.name}")
        print(f"- Results: {summary['results_file']}")
        print(f"- Report: {summary['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
