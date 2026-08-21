#!/usr/bin/env python3
"""抽 L600 timing 欄位（avg / recent / best / entries）落本地 cache。

為咩：`_sectional_breakdown` 個「末段極速（L600 峰值）破標準」獎勵（+15.07）
用 `timing_600m_best_speed` —— 即係**生涯最大值** —— 去同**今仗**路程嘅場地標準比。
一次快段速就變成永久資歷，而唔係「而家有幾快」。Benbulben：生涯最快 35.11s
（→ +15.07），但佢自己嘅 L600 平均係 15.4 m/s = 38.96s，慢過 Geelong 2400m
標準 36.74s。用平均就冇呢個獎勵。

同時抽 `_data.horse_rating`（官方讓磅分）同 trial timing，方便之後比較。

唯讀。輸出 scratch/au_timing_cache.json。
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
)

FIELDS = ("timing_600m_avg_speed", "timing_600m_recent_speed",
          "timing_600m_best_speed", "timing_l600_entries_count",
          "timing_speed_variance", "timing_600m_trend",
          "timing_trial_600m_avg_speed", "horse_rating")


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    out = {}
    total = 0
    have = {f: 0 for f in FIELDS}
    gaps = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            total += 1
            data = r["data"] or {}
            rec = {}
            for f in FIELDS:
                v = data.get(f)
                if v is not None:
                    rec[f] = v
                    have[f] += 1
            if rec:
                out[f"{r['meeting']}|{r['race']}|{r['horse_number']}"] = rec
            avg = rec.get("timing_600m_avg_speed")
            best = rec.get("timing_600m_best_speed")
            if avg and best and avg > 0:
                gaps.append(best / avg)
    dest = Path(__file__).resolve().parent / "au_timing_cache.json"
    dest.write_text(json.dumps(out), encoding="utf-8")
    print(f"runners {total}  有 timing 記錄 {len(out)}")
    print(f"\n{'欄位':32}{'有值':>8}{'佔全體':>9}")
    for f in FIELDS:
        print(f"{f:32}{have[f]:>8}{100*have[f]/max(1,total):>8.1f}%")
    if gaps:
        gaps.sort()
        print(f"\nbest / avg 比率（生涯最快 vs 自己平均），n={len(gaps)}：")
        for q, label in ((0.5, "中位"), (0.75, "P75"), (0.9, "P90"), (0.99, "P99")):
            print(f"   {label:4} {gaps[int(q*len(gaps))-1]:.3f}")
        over = sum(1 for g in gaps if g >= 1.05)
        print(f"   best 高出平均 ≥5% 嘅馬: {over} ({100*over/len(gaps):.1f}%)")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
