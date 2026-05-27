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
    parser = argparse.ArgumentParser(description="HKJC reflector orchestrator (unified workflow wrapper)")
    parser.add_argument("meeting_dir", help="HKJC meeting dir or folder name under Archive_Race_Analysis")
    parser.add_argument("--results-file", help="Optional existing HKJC results file")
    parser.add_argument("--results-url", help="Optional HKJC results URL for extraction")
    parser.add_argument("--race", dest="races", action="append", type=int, help="Reflect only specific race numbers")
    parser.add_argument("--report-path", help="Optional output path for markdown report")
    parser.add_argument("--force-extract", action="store_true", help="Force extraction even if results already exist")
    parser.add_argument("--skip-review", action="store_true", help="Skip full archive backtest / candidate testing")
    parser.add_argument("--json", action="store_true", help="Emit final summary JSON")
    args = parser.parse_args()

    summary = run_unified_reflector(
        platform="hkjc",
        meeting_ref=args.meeting_dir,
        results_file=args.results_file,
        results_url=args.results_url,
        target_races=args.races,
        report_path=args.report_path,
        force_extract=args.force_extract,
        skip_backtest=args.skip_review,
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        report_path = args.report_path
        if not report_path:
            report_path = str(default_report_path("hkjc", Path(summary["meeting_dir"])))
        print("\n🏁 HKJC unified reflector complete")
        print(f"- Meeting: {Path(summary['meeting_dir']).name}")
        print(f"- Results: {summary['results_file']}")
        print(f"- Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
