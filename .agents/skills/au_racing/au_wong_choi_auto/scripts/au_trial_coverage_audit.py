#!/usr/bin/env python3
"""Audit what trial evidence actually exists in archived AU pre-race Logic."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
import sys
sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING  # noqa: E402

OUT = AU_RACING / "AU_Trial_Coverage_Audit.md"


def pct(value: int, total: int) -> str:
    return f"{value / total * 100:.1f}%" if total else "0.0%"


def main() -> int:
    counts = Counter()
    scores = Counter()
    by_starts = {"初出（0）": Counter(), "少賽（1-3）": Counter(), "有經驗（4+）": Counter()}
    meetings = sorted(path for path in AU_RACING.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    for index, meeting in enumerate(meetings, 1):
        if index == 1 or index % 20 == 0:
            print(f"auditing Logic {index}/{len(meetings)}", flush=True)
        for path in meeting.glob("Race_*_Logic.json"):
            try:
                logic = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for horse in (logic.get("horses") or {}).values():
                data = horse.get("_data") or {}
                auto = horse.get("python_auto") or {}
                features = auto.get("feature_scores") or {}
                try:
                    starts = int(float(horse.get("career_race_starts") or 0))
                except (TypeError, ValueError):
                    starts = 0
                cohort = "初出（0）" if starts == 0 else ("少賽（1-3）" if starts <= 3 else "有經驗（4+）")
                counts["horses"] += 1
                by_starts[cohort]["horses"] += 1
                trial_count = int(float(data.get("trial_count") or 0))
                if trial_count:
                    counts["trial_rank_available"] += 1
                    by_starts[cohort]["trial_rank_available"] += 1
                if data.get("timing_trial_600m_avg_speed") not in (None, "", 0):
                    counts["formguide_l600_speed"] += 1
                    by_starts[cohort]["formguide_l600_speed"] += 1
                if data.get("timing_trial_total_time") not in (None, "", 0):
                    counts["formguide_total_time"] += 1
                official = data.get("official_trial_shadow") or {}
                if official:
                    counts["official_matched"] += 1
                    by_starts[cohort]["official_matched"] += 1
                    if official.get("official_trial_runner_match_count"):
                        counts["official_runner_finish"] += 1
                    if official.get("official_trial_latest_total_time"):
                        counts["official_heat_total_time"] += 1
                    if official.get("official_trial_latest_l600"):
                        counts["official_heat_l600"] += 1
                    if official.get("official_trial_electronic_count"):
                        counts["official_electronic"] += 1
                # Current output score: this tells whether 60 is a true neutral
                # or simply the generated snapshot's absence/default result.
                score = features.get("trial_score")
                if score is not None:
                    try:
                        score = round(float(score))
                    except (TypeError, ValueError):
                        score = 60
                    scores[score] += 1
                    by_starts[cohort]["scored"] += 1
                    if score == 60:
                        counts["score_60"] += 1
                        by_starts[cohort]["score_60"] += 1
                    if score >= 70:
                        counts["score_70plus"] += 1
                        by_starts[cohort]["score_70plus"] += 1
    total = counts["horses"]
    lines = ["# AU 試閘資料覆蓋 Audit", "", f"- 掃描馬匹：**{total}**。", "", "## 整體覆蓋", "", "| 證據 | 馬匹 | 佔比 |", "|---|---:|---:|"]
    rows = (
        ("有試閘名次／次數", "trial_rank_available"),
        ("Formguide 試閘 L600 平均速度", "formguide_l600_speed"),
        ("Formguide 試閘總時間", "formguide_total_time"),
        ("已配對官方試閘 event", "official_matched"),
        ("官方 runner 名次可用", "official_runner_finish"),
        ("官方 heat 總時間可用", "official_heat_total_time"),
        ("官方 heat L600 可用", "official_heat_l600"),
        ("電子計時標示", "official_electronic"),
        ("現行試閘分＝60", "score_60"),
        ("現行試閘分≥70", "score_70plus"),
    )
    for label, key in rows:
        lines.append(f"| {label} | {counts[key]} | {pct(counts[key], total)} |")
    lines.extend(["", "## 按賽績樣本", "", "| 群組 | 馬匹 | 有名次 | 有 L600 速度 | 官方配對 | 試閘分=60 | 試閘分≥70 |", "|---|---:|---:|---:|---:|---:|---:|"])
    for label, bucket in by_starts.items():
        n = bucket["horses"]
        lines.append(f"| {label} | {n} | {pct(bucket['trial_rank_available'], n)} | {pct(bucket['formguide_l600_speed'], n)} | {pct(bucket['official_matched'], n)} | {pct(bucket['score_60'], n)} | {pct(bucket['score_70plus'], n)} |")
    lines.extend(["", "## 現行試閘分分佈", "", "| 分數 | 馬匹 |", "|---:|---:|"])
    for score, n in sorted(scores.items()):
        lines.append(f"| {score} | {n} |")
    lines.extend(["", "## 解讀", "", "- 官方總時間／L600 屬同一 heat 的 context；除非有逐馬 split，不能當作每匹馬的正式 sectional。", "- Logic 現時沒有標準化的試閘 margin、同組 field size、trial class、場地掛牌欄位；這些缺口不能用 60 分假裝已知。", "- 因此輸出必須分開「中性試閘表現」、「只有排名／時間不足」及「完全無可用試閘」。", ""])
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"horses={total} | {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
