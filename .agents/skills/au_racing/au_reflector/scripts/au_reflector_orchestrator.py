#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[5]
SHARED_SCRIPTS = PROJECT_ROOT / ".agents" / "skills" / "shared_racing" / "race_reflector" / "scripts"
QLD_SECTIONALS = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_qld_sectionals_enrich.py"
QLD_SECTIONALS_PARSER = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_qld_sectionals_parse.py"
TRAINER_ROLLING = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_trainer_rolling_database.py"
STRUCTURAL_SHADOW = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_structural_shadow.py"
DUAL_OBJECTIVE_SHADOW = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_dual_objective_shadow.py"
REFLECTOR_SHADOW_STATUS = "Reflector_Shadow_Update_Status.json"
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
    parser.add_argument("--skip-official-sectionals", action="store_true", help="Skip post-race Racing Queensland sectional collection")
    parser.add_argument("--skip-trainer-rolling-sync", action="store_true", help="Skip canonical result/trainer rolling database refresh")
    parser.add_argument("--skip-structural-shadow", action="store_true", help="Skip frozen structural shadow forward review/tracker update")
    parser.add_argument("--json", action="store_true", help="Emit final summary JSON")
    args = parser.parse_args()

    meeting_path = Path(args.meeting_dir).resolve()
    _collect_post_race_qld_sectionals(meeting_path, skip=args.skip_official_sectionals)
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
    shadow_review = _run_structural_shadow_review(
        meeting_path,
        summary.get("results_file"),
        skip=args.skip_structural_shadow,
    )
    dual_shadow_review = _run_dual_objective_shadow_review(
        meeting_path,
        summary.get("results_file"),
        skip=args.skip_structural_shadow,
    )
    shadow_status = _write_shadow_update_status(
        meeting_path,
        summary.get("results_file"),
        structural_review=shadow_review,
        dual_review=dual_shadow_review,
        skipped=args.skip_structural_shadow,
    )
    summary["shadow_updates"] = shadow_status
    _append_shadow_status_to_report(Path(summary["report_path"]), meeting_path, shadow_status)
    _sync_trainer_rolling(skip=args.skip_trainer_rolling_sync)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n🏁 AU unified reflector complete")
        print(f"- Meeting: {meeting_path.name}")
        print(f"- Results: {summary['results_file']}")
        print(f"- Report: {summary['report_path']}")
        if shadow_review:
            print(f"- Structural shadow: {shadow_review}")
        if dual_shadow_review:
            print(f"- Dual-objective shadow: {dual_shadow_review}")
        print(f"- Shadow update status: {meeting_path / REFLECTOR_SHADOW_STATUS}")
        if shadow_status.get("promotion_ready"):
            print(f"🚨 SHADOW PROMOTION GATE PASSED: {shadow_status['promotion_ready']}")
    return 0


def _collect_post_race_qld_sectionals(meeting_path: Path, *, skip: bool) -> None:
    """Fetch only post-race QLD files; no data is collected during pre-race use."""
    if skip or not QLD_SECTIONALS.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(QLD_SECTIONALS), "--meeting-dir", str(meeting_path), "--limit", "1", "--delay", "1.0"],
            check=False,
            timeout=90,
        )
        if result.returncode:
            print("⚠️ QLD 賽後 sectional 未完成；reflector 照常繼續", file=sys.stderr)
            return
        if QLD_SECTIONALS_PARSER.exists():
            parsed = subprocess.run(
                [sys.executable, str(QLD_SECTIONALS_PARSER)],
                check=False,
                timeout=60,
            )
            if parsed.returncode:
                print("⚠️ QLD sectional 已下載但 runner-level 正規化未完成", file=sys.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ QLD 賽後 sectional 略過：{type(exc).__name__}", file=sys.stderr)


def _sync_trainer_rolling(*, skip: bool) -> None:
    """After results are available, refresh canonical trainer/date history."""
    if skip or not TRAINER_ROLLING.exists():
        return
    try:
        result = subprocess.run(
            [sys.executable, str(TRAINER_ROLLING), "--sync-results"],
            check=False,
            timeout=90,
        )
        if result.returncode:
            print("⚠️ trainer rolling database sync 未完成；不影響本次覆盤", file=sys.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ trainer rolling database sync 略過：{type(exc).__name__}", file=sys.stderr)


def _run_structural_shadow_review(meeting_path: Path, results_file, *, skip: bool) -> Optional[str]:
    """Best-effort post-race shadow review; official reflector output is unaffected."""
    if skip or not STRUCTURAL_SHADOW.exists():
        return None
    result_path = _resolve_markdown_results(meeting_path, results_file)
    if not result_path or not result_path.exists():
        print("⚠️ structural shadow 未搵到 markdown 賽果；tracker 暫不更新", file=sys.stderr)
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(STRUCTURAL_SHADOW), str(meeting_path), "--results-md", str(result_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode:
            message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
            print(f"⚠️ structural shadow forward review 未完成：{message}", file=sys.stderr)
            return None
        return str(meeting_path / "Structural_Shadow_Forward_Review.md")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ structural shadow forward review 略過：{type(exc).__name__}", file=sys.stderr)
        return None


def _resolve_markdown_results(meeting_path: Path, results_file) -> Optional[Path]:
    result_path = Path(results_file).resolve() if results_file else None
    if result_path and result_path.suffix.lower() == ".md" and result_path.exists():
        return result_path
    candidates = [
        path for path in sorted(meeting_path.glob("Race_Results_*.md"))
        if "reflector" not in path.name.lower()
    ]
    return candidates[0] if candidates else None


def _run_dual_objective_shadow_review(meeting_path: Path, results_file, *, skip: bool) -> Optional[str]:
    """Update the frozen dual-objective tracker without touching official ranks."""
    if skip or not DUAL_OBJECTIVE_SHADOW.exists():
        return None
    result_path = _resolve_markdown_results(meeting_path, results_file)
    if not result_path:
        print("⚠️ dual-objective shadow 未搞到 markdown 賽果；tracker 暫不更新", file=sys.stderr)
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(DUAL_OBJECTIVE_SHADOW), str(meeting_path), "--results-md", str(result_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode:
            message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
            print(f"⚠️ dual-objective shadow forward review 未完成：{message}", file=sys.stderr)
            return None
        return str(meeting_path / "Dual_Objective_Shadow_Forward_Review.md")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"⚠️ dual-objective shadow forward review 略過：{type(exc).__name__}", file=sys.stderr)
        return None


def _write_shadow_update_status(
    meeting_path: Path,
    results_file,
    *,
    structural_review: Optional[str],
    dual_review: Optional[str],
    skipped: bool,
) -> dict:
    dual_status_path = meeting_path / "Dual_Objective_Shadow_Update_Status.json"
    dual_status = {}
    if dual_status_path.exists():
        try:
            dual_status = json.loads(dual_status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            dual_status = {"status": "invalid_status_file"}
    status = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "meeting": str(meeting_path),
        "results_file": str(results_file or ""),
        "skipped_by_flag": skipped,
        "structural_shadow": {
            "status": "skipped_by_flag" if skipped else ("updated" if structural_review else "not_updated"),
            "review": structural_review,
        },
        "dual_objective_shadow": {
            "status": "skipped_by_flag" if skipped else ("updated" if dual_review else "not_updated"),
            "review": dual_review,
            "detail_status": str(dual_status_path) if dual_status_path.exists() else None,
        },
        "promotion_ready": dual_status.get("promotion_ready") if dual_review and not skipped else None,
        "official_model_changed": False,
    }
    (meeting_path / REFLECTOR_SHADOW_STATUS).write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return status


def _append_shadow_status_to_report(report_path: Path, meeting_path: Path, status: dict) -> None:
    """Keep the main reflector report self-contained and rerun-safe."""
    if not report_path.exists():
        return
    tracker_path = meeting_path.parent / "AU_Dual_Objective_Shadow_Tracker.json"
    tracker = {}
    if tracker_path.exists():
        try:
            tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            tracker = {}
    lines = [
        "<!-- AU_SHADOW_STATUS_START -->",
        "## Shadow Automation Status",
        "",
        f"- Structural shadow: **{status['structural_shadow']['status']}**.",
        f"- Dual-objective shadow: **{status['dual_objective_shadow']['status']}**.",
        "- Official model changed: **NO**.",
    ]
    if tracker:
        minimum = tracker.get("promotion_gate", {}).get("minimum_forward_races", 150)
        lines.append(f"- Forward progress: **{tracker.get('forward_races', 0)}/{minimum} races**; tracks: **{len(tracker.get('tracks', []))}/3**.")
        distance = tracker.get("distance_family_counts") or {}
        if distance:
            lines.append("- Distance coverage: " + ", ".join(f"{name} {count}/30" for name, count in distance.items()) + ".")
        lines.extend(["", "| Candidate | Top1 Δ | Top2 Δ | Top4 coverage Δ | Top4 exact Δ | Status |", "|---|---:|---:|---:|---:|---|"])
        for candidate, item in (tracker.get("candidates") or {}).items():
            deltas = item.get("deltas") or {}
            lines.append(
                f"| {candidate} | {100 * deltas.get('top1_win', 0):+.2f}pp | "
                f"{100 * deltas.get('top2_place_strike', 0):+.2f}pp | "
                f"{100 * deltas.get('top4_place_coverage', 0):+.2f}pp | "
                f"{100 * deltas.get('top4_trifecta', 0):+.2f}pp | "
                f"{'READY FOR APPROVAL' if item.get('promotion_eligible') else 'NOT YET'} |"
            )
    if status.get("promotion_ready"):
        lines.extend(["", f"🚨 Promotion/canary action required: `{status['promotion_ready']}`"])
    lines.extend(["", "<!-- AU_SHADOW_STATUS_END -->"])
    block = "\n".join(lines)
    text = report_path.read_text(encoding="utf-8")
    pattern = re.compile(r"\n?<!-- AU_SHADOW_STATUS_START -->.*?<!-- AU_SHADOW_STATUS_END -->\n?", re.S)
    text = pattern.sub("\n", text).rstrip() + "\n\n" + block + "\n"
    report_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
