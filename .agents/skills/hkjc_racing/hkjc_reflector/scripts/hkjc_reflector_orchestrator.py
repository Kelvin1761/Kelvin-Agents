#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[5]
SHARED_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "race_reflector" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

from unified_reflector_core import default_report_path, run_unified_reflector


STRUCTURAL_SHADOW = Path(__file__).resolve().parent / "hkjc_class4_structural_shadow.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC reflector orchestrator (unified workflow wrapper)")
    parser.add_argument("meeting_dir", help="HKJC meeting dir or folder name under Wong Choi Horse Race Analysis")
    parser.add_argument("--results-file", help="Optional existing HKJC results file")
    parser.add_argument("--results-url", help="Optional HKJC results URL for extraction")
    parser.add_argument("--race", dest="races", action="append", type=int, help="Reflect only specific race numbers")
    parser.add_argument("--report-path", help="Optional output path for markdown report")
    parser.add_argument("--force-extract", action="store_true", help="Force extraction even if results already exist")
    parser.add_argument(
        "--sync-results-database",
        action="store_true",
        help="Also copy extracted HKJC results into the shared results database",
    )
    parser.add_argument("--skip-review", action="store_true", help="Skip full archive backtest / candidate testing")
    parser.add_argument(
        "--skip-structural-shadow",
        action="store_true",
        help="Skip frozen Class 4 structural shadow review/tracker update",
    )
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
        sync_hkjc_results_database=args.sync_results_database,
    )
    shadow_summary = _run_structural_shadow(
        Path(summary["meeting_dir"]),
        Path(summary["results_file"]),
        Path(summary["report_path"]),
        target_races=args.races,
        skip=args.skip_structural_shadow,
    )
    if shadow_summary:
        summary["structural_shadow"] = shadow_summary

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
        if shadow_summary:
            print(f"- Class 4 shadow: {shadow_summary['review_path']}")
    return 0


def _run_structural_shadow(
    meeting_dir: Path,
    results_file: Path,
    reflector_report: Path,
    *,
    target_races: list[int] | None,
    skip: bool,
) -> dict[str, Any] | None:
    """Run the frozen shadow as a best-effort, non-production post-race step."""
    if skip or not STRUCTURAL_SHADOW.exists():
        return None
    if results_file.suffix.lower() != ".json":
        print("⚠️ Class 4 shadow 只接受 structured JSON 賽果；tracker 暫不更新", file=sys.stderr)
        return None
    command = [
        sys.executable,
        str(STRUCTURAL_SHADOW),
        str(meeting_dir),
        "--results-file",
        str(results_file),
        "--reflector-report",
        str(reflector_report),
    ]
    if target_races:
        # Partial reflector runs are useful diagnostically but must not affect
        # the central prospective promotion ledger.
        command.append("--no-ledger")
        for race_number in target_races:
            command.extend(["--race", str(race_number)])
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ Class 4 shadow 略過：{type(exc).__name__}", file=sys.stderr)
        return None
    if result.returncode:
        message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
        print(f"⚠️ Class 4 shadow 未完成；正式 reflector 不受影響：{message}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print("⚠️ Class 4 shadow 完成但 JSON summary 無法解析；正式 reflector 不受影響", file=sys.stderr)
        return None


if __name__ == "__main__":
    raise SystemExit(main())
