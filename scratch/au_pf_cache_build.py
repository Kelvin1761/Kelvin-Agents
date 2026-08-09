#!/usr/bin/env python3
"""抽 `pf_metrics.pf_aggregates` 全部欄位落本地 cache。

背景：`_pace_figure_score`（有效權重 0.1430，第三高）只用 `l600_delta_avg`。
`race_time_diff`（全程時間 vs 賽事基準）同 `tempo_qrank`（賽事節奏百分位）
兩個欄位 parse 咗、aggregate 咗、印咗，但**完全冇入任何分**。

Benbulben 個案：l600_delta −1.71（末段快 1.71s）→ 段速實速分 73.7，
但同一場 race_time_diff = **+8.95**（全程慢 8.95 秒）、tempo_qrank = **0.99**
（節奏慢到 99 百分位，全場人末段都快）。即係「慢速爬行賽事嘅快尾段」被當成速度證據。

唯讀。輸出 scratch/au_pf_cache.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    iter_logic_rows,
    load_historical_results,
)

FIELDS = ("l600_delta_avg", "l600_delta_best", "race_time_diff_avg",
          "race_time_diff_best", "tempo_qrank_avg", "l800_delta_avg",
          "l400_delta_avg", "l200_delta_avg", "pf_run_count",
          "latest_early_race_pace", "latest_early_runner_pace")


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    out = {}
    total = 0
    have = {f: 0 for f in FIELDS}
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            total += 1
            agg = ((r["data"] or {}).get("pf_metrics") or {}).get("pf_aggregates") or {}
            if not agg:
                continue
            rec = {}
            for f in FIELDS:
                v = agg.get(f)
                if v is not None:
                    rec[f] = v
                    have[f] += 1
            # 逐場 runs 亦保留（tempo 逐場睇比平均有用）
            runs = ((r["data"] or {}).get("pf_metrics") or {}).get("pf_runs") or []
            rec["runs"] = [
                {k: run.get(k) for k in ("l600_delta", "race_time_diff",
                                         "tempo_qrank", "early_race_pace")}
                for run in runs if isinstance(run, dict)
            ]
            out[f"{r['meeting']}|{r['race']}|{r['horse_number']}"] = rec
    dest = Path(__file__).resolve().parent / "au_pf_cache.json"
    dest.write_text(json.dumps(out), encoding="utf-8")
    print(f"runners {total}  有 pf_aggregates {len(out)}"
          f" = {100*len(out)/max(1,total):.1f}%")
    print(f"\n{'欄位':26}{'有值':>8}{'佔全體':>9}")
    for f in FIELDS:
        print(f"{f:26}{have[f]:>8}{100*have[f]/max(1,total):>8.1f}%")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
