#!/usr/bin/env python3
"""抽 `jockey_ly` / `trainer_ly`（去年官方場數 / 冠亞季）落本地 cache。

為咗砌一個**統一上名率**特徵：Racenet profile 嘅 `placePercentage` 同
`*_ly` 嘅 places/rides 量緊同一樣嘢（上名率），只係生涯 vs 去年。
有 profile 就用生涯（樣本大、穩），冇就用 LY —— 同一把標尺、100% 覆蓋、
零額外 Racenet 請求，避開「同場撈亂兩把標尺」嘅問題。

（實測：抓 150 個 profile 只令 0 場達到 ≥90% 覆蓋；要全覆蓋要 1,041 個
profile ≈ 3,100 個請求，唔值得。）

唯讀。輸出 scratch/au_ly_cache.json。
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
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, iter_logic_rows, load_historical_results)


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    out = {}
    total = have = {"jockey_ly": 0, "trainer_ly": 0}
    total = 0
    have = {"jockey_ly": 0, "trainer_ly": 0}
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            total += 1
            data = r["data"] or {}
            rec = {}
            for key in ("jockey_ly", "trainer_ly"):
                val = data.get(key)
                if isinstance(val, dict) and val.get("rides"):
                    rec[key] = {"name": val.get("name"),
                                "rides": val.get("rides"),
                                "wins": val.get("wins"),
                                "places": val.get("places")}
                    have[key] += 1
            if rec:
                out[f"{r['meeting']}|{r['race']}|{r['horse_number']}"] = rec
    dest = Path(__file__).resolve().parent / "au_ly_cache.json"
    dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"runners {total}  有記錄 {len(out)}")
    for key, n in have.items():
        print(f"  {key:12} {n:>6} ({100*n/max(1,total):.1f}%)")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
