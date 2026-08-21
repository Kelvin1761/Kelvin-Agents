#!/usr/bin/env python3
"""抽 `_data.last_finish_line`（格式 `名次/馬群 @ 場地 路程`）落本地 cache。

呢個欄位全 archive 100% 有值，即係**每匹馬最近一仗嘅馬群大細一直都喺度**，
唔需要向 Racenet 發任何請求（Racenet ~50-60% 機率性 403，唔值得為呢個去壓）。
而最近一仗喺 `_form_score` 嘅 decay = 1.0，係四場之中權重最高嗰場。

注意：`last_finish_line` 可能指向**試閘**（例：Benbulben `4/6 @ Coleraine 2800m`
係試閘，唔係佢最近嘅正式仗）。所以下游 join 必須同時比對 場地 + 路程 + 名次，
唔可以只比名次。

唯讀。輸出 scratch/au_lastfinish_cache.json。
"""
from __future__ import annotations

import json
import re
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

LINE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*@\s*(.+?)\s+(\d+)m\s*$")


def main():
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    out = {}
    total = parsed = 0
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, results):
        for r in race_rows:
            total += 1
            raw = str((r["data"] or {}).get("last_finish_line") or "").strip()
            m = LINE.match(raw)
            if not m:
                continue
            parsed += 1
            out[f"{r['meeting']}|{r['race']}|{r['horse_number']}"] = {
                "place": int(m.group(1)),
                "field": int(m.group(2)),
                "venue": m.group(3).strip(),
                "distance": int(m.group(4)),
                "raw": raw,
            }
    dest = Path(__file__).resolve().parent / "au_lastfinish_cache.json"
    dest.write_text(json.dumps(out), encoding="utf-8")
    print(f"runners {total}  parsed last_finish_line {parsed}"
          f" = {100*parsed/max(1,total):.1f}%")
    fields = [v["field"] for v in out.values()]
    if fields:
        import statistics
        print(f"馬群大細分佈: min {min(fields)} / median {statistics.median(fields)}"
              f" / max {max(fields)}")
    print(f"→ {dest}")


if __name__ == "__main__":
    main()
