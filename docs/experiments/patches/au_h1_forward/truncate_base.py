#!/usr/bin/env python3
"""功效預估用：由 BASE 取 2026-08-05 起首 20 個 warm-up 賽日 + 跟住 K 個計分賽日（模擬 forward 樣本量）。

    python3 truncate_base.py BASE.json K OUT.json
"""
import json
import sys

src, k, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
races = [r for r in json.load(open(src))["races"] if r["date"] >= "2026-08-05"]
days = sorted({r["date"] for r in races})[: 20 + k]
keep = [r for r in races if r["date"] in set(days)]
scored = [r for r in keep if r["date"] > days[19]]
json.dump({"races": keep}, open(out, "w"))
print(f"days {len(days)} races {len(keep)} scored_days {k} scored_races {len(scored)}")
