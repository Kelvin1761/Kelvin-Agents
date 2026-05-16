#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from hkjc_results_db import (
    ROOT,
    find_meeting_results_file,
    get_analysis_archive_root,
    get_season_csvs,
    get_season_results_roots,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable
REPORT_NAME = "HKJC_Reflection_Report.md"


def run(cmd: list[str], label: str, ok_codes: tuple[int, ...] = (0,)) -> str:
    print(f"\n{'=' * 72}")
    print(f"🔍 {label}")
    print(" ".join(str(part) for part in cmd))
    print(f"{'=' * 72}")
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode not in ok_codes:
        raise SystemExit(result.returncode)
    return result.stdout


def resolve_meeting_dir(target: str) -> Path:
    raw = Path(target)
    if raw.is_dir():
        return raw.resolve()
    archive_candidate = get_analysis_archive_root() / target
    if archive_candidate.is_dir():
        return archive_candidate.resolve()
    raise SystemExit(f"❌ Invalid HKJC meeting dir: {target}")


def _fmt_delta(value: float, digits: int = 0) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value:.{digits}f}"


def _metric_delta(candidate: dict, baseline: dict, key: str) -> float:
    return float(candidate.get(key, 0.0) or 0.0) - float(baseline.get(key, 0.0) or 0.0)


def _candidate_sort_key(item: dict) -> tuple[float, ...]:
    global_delta = item["global_delta"]
    meeting_delta = item["meeting_delta"]
    return (
        global_delta["champion"],
        global_delta["min_threshold"],
        global_delta["mrr"],
        -global_delta["order_issue"],
        global_delta["avg_top4_hits"],
        meeting_delta["champion"],
        meeting_delta["min_threshold"],
        meeting_delta["mrr"],
        -meeting_delta["order_issue"],
    )


def _collect_candidate_comparisons(review_payload: dict, meeting_name: str) -> list[dict]:
    model_summary = review_payload.get("model_summary") or {}
    meeting_summary = (review_payload.get("meeting_summary") or {}).get(meeting_name) or {}
    meeting_models = meeting_summary.get("models") or {}
    baseline_global = model_summary.get("current_live") or {}
    baseline_meeting = meeting_models.get("current_live") or {}
    candidates: list[dict] = []
    excluded = {"current_live", "previous_calibrated"}

    for model_name, global_stats in model_summary.items():
        if model_name in excluded or not global_stats:
            continue
        meeting_stats = meeting_models.get(model_name)
        if not meeting_stats:
            continue
        global_delta = {
            "champion": _metric_delta(global_stats, baseline_global, "champion"),
            "min_threshold": _metric_delta(global_stats, baseline_global, "min_threshold"),
            "good": _metric_delta(global_stats, baseline_global, "good"),
            "gold": _metric_delta(global_stats, baseline_global, "gold"),
            "order_issue": _metric_delta(global_stats, baseline_global, "order_issue"),
            "mrr": _metric_delta(global_stats, baseline_global, "mrr"),
            "avg_top4_hits": _metric_delta(global_stats, baseline_global, "avg_top4_hits"),
        }
        meeting_delta = {
            "champion": _metric_delta(meeting_stats, baseline_meeting, "champion"),
            "min_threshold": _metric_delta(meeting_stats, baseline_meeting, "min_threshold"),
            "good": _metric_delta(meeting_stats, baseline_meeting, "good"),
            "gold": _metric_delta(meeting_stats, baseline_meeting, "gold"),
            "order_issue": _metric_delta(meeting_stats, baseline_meeting, "order_issue"),
            "mrr": _metric_delta(meeting_stats, baseline_meeting, "mrr"),
            "avg_top4_hits": _metric_delta(meeting_stats, baseline_meeting, "avg_top4_hits"),
        }
        if not any(
            abs(value) > 1e-9
            for value in (
                *global_delta.values(),
                *meeting_delta.values(),
            )
        ):
            continue
        candidates.append(
            {
                "model": model_name,
                "global": global_stats,
                "meeting": meeting_stats,
                "global_delta": global_delta,
                "meeting_delta": meeting_delta,
            }
        )

    candidates.sort(key=_candidate_sort_key, reverse=True)
    return candidates


def _recommendation_label(item: dict) -> tuple[str, str]:
    global_delta = item["global_delta"]
    meeting_delta = item["meeting_delta"]
    global_improved = (
        global_delta["champion"] >= 0
        and global_delta["min_threshold"] >= 0
        and global_delta["mrr"] >= 0
        and global_delta["order_issue"] <= 0
    )
    strong_global = global_delta["champion"] > 0 or (
        global_delta["min_threshold"] > 0 and global_delta["order_issue"] < 0 and global_delta["mrr"] >= 0.003
    )
    meeting_improved = (
        meeting_delta["champion"] >= 0
        and meeting_delta["min_threshold"] >= 0
        and meeting_delta["order_issue"] <= 0
    )
    if strong_global and meeting_improved:
        return ("建議 embed", "同場無明顯轉差，全庫核心 KPI 有進步。")
    if global_improved and meeting_improved:
        return ("可保留觀察", "方向正面，但改善幅度未算大。")
    if (
        global_delta["champion"] > 0
        or global_delta["min_threshold"] > 0
        or global_delta["mrr"] > 0
        or global_delta["order_issue"] < 0
    ):
        return ("只作觀察", "全庫有亮點，但今場未同步改善。")
    return ("唔建議 embed", "改善未夠一致，或者有明顯 trade-off。")


def _summarize_meeting_problems(meeting_stats: dict) -> list[str]:
    summary = meeting_stats.get("summary") or {}
    total = int(summary.get("total_races") or 0)
    issues: list[str] = []
    position = summary.get("position_hit_rates") or {}
    ranking = summary.get("ranking_order") or {}
    false_pos = summary.get("false_positives") or []
    false_neg = summary.get("false_negatives") or []

    min_threshold = (position.get("min_threshold") or {}).get("rate")
    if min_threshold is not None and min_threshold < 60:
        issues.append(f"最低門檻命中率只得 {min_threshold}%（{total} 場樣本），未過 60% 目標。")
    good_rate = (position.get("good_result") or {}).get("rate")
    if good_rate is not None and good_rate < 40:
        issues.append(f"良好結果率 {good_rate}% 偏低，代表前二選排序仲有改善空間。")
    order_rate = (ranking.get("pick34_beat_12") or {}).get("rate")
    if order_rate is not None and order_rate > 30:
        issues.append(f"Pick 3/4 反超 Pick 1/2 比率去到 {order_rate}%，排序穩定性不足。")
    if false_pos:
        sample = "；".join(
            f"R{item['race']} #{item['horse_num']} {item.get('name', '')}[{item.get('grade', '')}] 跑第{item.get('actual_pos')}"
            for item in false_pos[:3]
        )
        issues.append(f"False Positive 偏多，代表高評級馬有落空例子：{sample}。")
    if false_neg:
        sample = "；".join(
            f"R{item['race']} #{item['horse_num']} {item.get('name', '')}[{item.get('grade', '')}] 跑第{item.get('actual_pos')}"
            for item in false_neg[:3]
        )
        issues.append(f"False Negative 仍存在，代表部分低評級馬被低估：{sample}。")
    if not issues:
        issues.append("今個 meeting 未見明顯結構性失誤，主要係微調排序與取捨。")
    return issues


def _render_report(
    meeting_dir: Path,
    meeting_stats: dict,
    review_payload: dict | None,
) -> str:
    summary = meeting_stats.get("summary") or {}
    meeting_name = meeting_dir.name
    lines = [
        f"# HKJC Reflector Report - {meeting_name}",
        "",
        "## 已驗證範圍",
        f"- 目標 meeting: `{meeting_name}`",
        f"- 今場覆盤樣本: {summary.get('total_races', 0)} 場",
    ]

    if review_payload:
        coverage = review_payload.get("coverage") or {}
        coverage_races = coverage.get("races", 0)
        coverage_meetings = coverage.get("meetings", 0)
        coverage_horses = coverage.get("horses", 0)
        lines.extend(
            [
                f"- 全庫 walk-forward: {coverage_meetings} meetings / {coverage_races} races / {coverage_horses} horses",
                "- 候選改動已先用同一 meeting + 全庫樣本比較，先至出 embed 建議。",
            ]
        )

    lines.extend(["", "## 今場問題"])
    for item in _summarize_meeting_problems(meeting_stats):
        lines.append(f"- {item}")

    if not review_payload:
        lines.extend(["", "## 建議", "- 今次未跑全庫 review，所以只可做單場覆盤，未適合判斷 embed。"])
        return "\n".join(lines)

    meeting_summary = (review_payload.get("meeting_summary") or {}).get(meeting_name) or {}
    meeting_models = meeting_summary.get("models") or {}
    current_meeting = meeting_models.get("current_live") or {}
    current_global = (review_payload.get("model_summary") or {}).get("current_live") or {}
    candidates = _collect_candidate_comparisons(review_payload, meeting_name)

    lines.extend(
        [
            "",
            "## Current Live 基線",
            f"- 今場: Champion {current_meeting.get('champion', 0)} / MinThreshold {current_meeting.get('min_threshold', 0)} / OrderIssue {current_meeting.get('order_issue', 0)} / MRR {current_meeting.get('mrr', 0)}",
            f"- 全庫: Champion {current_global.get('champion', 0)} / Good {current_global.get('good', 0)} / MinThreshold {current_global.get('min_threshold', 0)} / OrderIssue {current_global.get('order_issue', 0)} / MRR {current_global.get('mrr', 0)} / AvgTop4Hits {current_global.get('avg_top4_hits', 0)}",
            "",
            "## 可改進候選",
        ]
    )

    if not candidates:
        lines.append("- 今次 review 未搵到可直接比較嘅候選模型。")
    else:
        for item in candidates[:5]:
            label, rationale = _recommendation_label(item)
            lines.append(
                f"- `{item['model']}`: {label}。"
                f" 全庫 Champion {_fmt_delta(item['global_delta']['champion'])} / Min {_fmt_delta(item['global_delta']['min_threshold'])} / "
                f"OrderIssue {_fmt_delta(item['global_delta']['order_issue'])} / MRR {_fmt_delta(item['global_delta']['mrr'], 4)}；"
                f" 今場 Champion {_fmt_delta(item['meeting_delta']['champion'])} / Min {_fmt_delta(item['meeting_delta']['min_threshold'])} / "
                f"OrderIssue {_fmt_delta(item['meeting_delta']['order_issue'])} / MRR {_fmt_delta(item['meeting_delta']['mrr'], 4)}。{rationale}"
            )

    lines.extend(["", "## 單場改善有冇"])
    if not candidates:
        lines.append("- 冇 candidate comparison 可用。")
    else:
        top_meeting = candidates[0]
        lines.append(
            f"- 最接近有感改善嘅候選係 `{top_meeting['model']}`："
            f" 今場 Champion {_fmt_delta(top_meeting['meeting_delta']['champion'])}、"
            f" MinThreshold {_fmt_delta(top_meeting['meeting_delta']['min_threshold'])}、"
            f" OrderIssue {_fmt_delta(top_meeting['meeting_delta']['order_issue'])}、"
            f" MRR {_fmt_delta(top_meeting['meeting_delta']['mrr'], 4)}。"
        )
        if all(value == 0 for value in top_meeting["meeting_delta"].values()):
            lines.append("- 不過今場其實係完全持平，代表佢主要亮點來自全庫，而唔係單場即時修正。")

    lines.extend(["", "## 全庫改善有冇"])
    if not candidates:
        lines.append("- 冇全庫 candidate comparison 可用。")
    else:
        top_global = candidates[0]
        lines.append(
            f"- `{top_global['model']}` 對 {review_payload.get('coverage', {}).get('races', 0)} 場樣本最有參考價值："
            f" Champion {_fmt_delta(top_global['global_delta']['champion'])}、"
            f" Good {_fmt_delta(top_global['global_delta']['good'])}、"
            f" MinThreshold {_fmt_delta(top_global['global_delta']['min_threshold'])}、"
            f" OrderIssue {_fmt_delta(top_global['global_delta']['order_issue'])}、"
            f" MRR {_fmt_delta(top_global['global_delta']['mrr'], 4)}、"
            f" AvgTop4Hits {_fmt_delta(top_global['global_delta']['avg_top4_hits'], 3)}。"
        )
        if "candidate_outer_weights_retune" in {item["model"] for item in candidates[:5]}:
            best_outer = review_payload.get("best_outer_weights") or {}
            if best_outer:
                parts = ", ".join(f"{key}={value:.2f}" for key, value in best_outer.items())
                lines.append(f"- outer weights retune 候選使用：{parts}")

    lines.extend(["", "## 建議 embed / 唔 embed"])
    if not candidates:
        lines.append("- 未有足夠候選比較，暫時唔好 embed 新改動。")
    else:
        best = candidates[0]
        label, rationale = _recommendation_label(best)
        lines.append(f"- 結論：**{label} `{best['model']}`**。{rationale}")
        if label == "建議 embed":
            lines.append("- 理由係佢唔只係單場補救，而係全庫核心 KPI 都有同步提升或至少無明顯退步。")
        elif label == "可保留觀察":
            lines.append("- 可以先放入 review/watchlist，等更多新 meeting 再確認泛化。")
        else:
            lines.append("- 目前更似 observation candidate，多睇幾個 meeting 先值得動 live。")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC Reflector orchestrator: sync results db + meeting stats + full database validation")
    parser.add_argument("meeting_dir", help="HKJC meeting dir or folder name under Archive_Race_Analysis")
    parser.add_argument("--skip-sync", action="store_true", help="Skip syncing meeting results into canonical results database")
    parser.add_argument("--skip-review", action="store_true", help="Skip full database validation review")
    parser.add_argument("--report-path", help=f"Optional output path for markdown report (default: <meeting_dir>/{REPORT_NAME})")
    parser.add_argument("--json", action="store_true", help="Emit final summary JSON")
    args = parser.parse_args()

    meeting_dir = resolve_meeting_dir(args.meeting_dir)
    if not args.skip_sync:
        run(
            [PYTHON, str(SCRIPT_DIR / "sync_hkjc_results_database.py"), "--meeting-dir", str(meeting_dir)],
            "Sync HKJC Results Database",
        )

    results_file = find_meeting_results_file(meeting_dir, get_season_results_roots())
    if not results_file:
        raise SystemExit(f"❌ Unable to locate results file for {meeting_dir}")

    stats_output = run(
        [PYTHON, str(SCRIPT_DIR / "reflector_auto_stats.py"), str(meeting_dir), str(results_file), "--json"],
        "Meeting Reflection Stats",
        ok_codes=(0, 1),
    )
    meeting_stats = json.loads(stats_output)

    review_payload = None
    if not args.skip_review:
        review_output = run(
            [
                PYTHON,
                str(SCRIPT_DIR / "review_auto_weighting.py"),
                "--meeting-root",
                str(get_analysis_archive_root()),
                "--results-root",
                str(get_season_results_roots()[0]),
                "--results-root",
                str(get_season_results_roots()[1]),
                "--season-csv",
                str(get_season_csvs()[0]),
                "--season-csv",
                str(get_season_csvs()[1]),
                "--json",
            ],
            "Full Database Validation Review",
        )
        review_payload = json.loads(review_output)

    summary = {
        "meeting_dir": str(meeting_dir),
        "results_file": str(results_file),
        "meeting_stats": meeting_stats,
        "database_review": review_payload,
    }
    report_markdown = _render_report(meeting_dir, meeting_stats, review_payload)
    report_path = Path(args.report_path).resolve() if args.report_path else meeting_dir / REPORT_NAME
    report_path.write_text(report_markdown, encoding="utf-8")
    summary["report_path"] = str(report_path)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\n🏁 HKJC Reflector orchestration complete")
        print(f"- Meeting: {meeting_dir.name}")
        print(f"- Results file: {results_file}")
        print(f"- Report: {report_path}")
        print(f"- Meeting races reviewed: {meeting_stats.get('summary', {}).get('total_races')}")
        if review_payload:
            coverage = review_payload.get("coverage", {})
            print(f"- Database meetings reviewed: {coverage.get('meetings')}")
            print(f"- Database races reviewed: {coverage.get('races')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
