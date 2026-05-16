#!/usr/bin/env python3
"""
AU reflector orchestrator for deterministic full-Python outputs.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(pathlib.Path(__file__).resolve().parent))

from reflector_auto_stats import run_stats
from au_review_auto_weighting import run_review


def render_report(meeting_dir: pathlib.Path, results_file: pathlib.Path, baseline: dict, stats: dict) -> str:
    summary = stats.get("summary", {})
    current = baseline.get("current_live", {})
    venue = meeting_dir.name
    lines = [
        f"# AU Reflector Review Report",
        "",
        f"- Meeting: `{venue}`",
        f"- Generated: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        "",
        "## 今場問題",
        f"- 冠軍命中: {summary.get('champion_hit_rates', {}).get('top1_champion', {}).get('count', 0)} / {summary.get('total_races', 0)}",
        f"- 最低門檻達標: {summary.get('position_hit_rates', {}).get('min_threshold', {}).get('count', 0)} / {summary.get('total_races', 0)}",
        f"- 排名逆序: {summary.get('ranking_order', {}).get('pick34_beat_12', {}).get('count', 0)}",
        "",
        "## 可改進候選",
        "- outer weights constrained retune",
        "- intra-matrix feature balance retune",
        "- tie-break / draw micro review",
        "",
        "## 單場改善有冇",
        "- 以 deterministic current_live baseline 作 same-race replay 比對。",
        "- 如候選未能改善 champion / MRR / order issue，視為不通過。",
        "",
        "## 全庫改善有冇",
        f"- current_live Champion: {current.get('Champion', 0)}",
        f"- current_live Gold: {current.get('Gold', 0)}",
        f"- current_live Good: {current.get('Good', 0)}",
        f"- current_live MRR: {current.get('MRR', 0.0)}",
        f"- current_live Order Issue: {current.get('Order Issue', 0)}",
        f"- current_live Avg Top4 Hits: {current.get('Avg Top4 Hits', 0.0)}",
        "",
        "## 建議 embed / 唔 embed",
        "- 只有當候選於 same-race replay + full AU database replay 都清楚改善，先建議 embed。",
        "- 否則維持 current_live。",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="AU Reflector deterministic orchestrator")
    parser.add_argument("meeting_dir")
    parser.add_argument("results_file")
    parser.add_argument("--base-dir", default=str(PROJECT_ROOT / "Archive_Race_Analysis"))
    args = parser.parse_args()

    meeting_dir = pathlib.Path(args.meeting_dir).resolve()
    results_file = pathlib.Path(args.results_file).resolve()
    stats = run_stats(str(meeting_dir), str(results_file))
    baseline = run_review(pathlib.Path(args.base_dir))
    report_text = render_report(meeting_dir, results_file, baseline, stats)
    out_path = meeting_dir / f"{meeting_dir.name}_Reflector_Report.md"
    out_path.write_text(report_text, encoding="utf-8")
    print(f"✅ Reflector report written: {out_path}")


if __name__ == "__main__":
    main()
