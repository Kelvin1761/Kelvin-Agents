#!/usr/bin/env python3
"""每個 leaf 單獨嘅預測力 —— 修改任何嘢之前必須知道邊個 leaf 真係有訊號。

之前八個 candidate 全部係喺已調好嘅公式上加補丁，而 matrix 權重本來就係圍住
舊分佈調出嚟，所以次次同權重打架。呢次先量基本事實：

  1. 場內 Spearman ρ（leaf 排名 vs 實際名次）—— 單一 leaf 嘅排序能力
  2. 場內五分位嘅實際前三率 —— 睇單調性同幅度
  3. leaf 之間嘅場內相關 —— 睇邊幾個 leaf 其實量同一樣嘢（冗餘）

唯讀，本地 cache。
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine"))

from au_racing_engine.matrix_mapper import MATRIX_FORMULAS  # noqa: E402
from au_racing_engine.scoring import MATRIX_WEIGHTS  # noqa: E402

HERE = Path(__file__).resolve().parent
LEAVES = ("form_score", "consistency_score", "pace_figure_score", "sectional_score",
          "trial_score", "pace_map_score", "jockey_score", "trainer_score",
          "jockey_horse_fit_score", "class_score", "rating_score", "weight_score",
          "track_score", "formline_score", "health_score", "confidence_score",
          "distance_score")


def eff_weights():
    eff = {}
    for mk, comps in MATRIX_FORMULAS.items():
        for leaf, w in comps:
            eff[leaf] = eff.get(leaf, 0.0) + MATRIX_WEIGHTS[mk] * w
    return eff


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs, ys):
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def main():
    races = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))["races"]
    eff = eff_weights()

    rho = defaultdict(list)
    quintile = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # leaf -> q -> [n, top3]
    pair_rho = defaultdict(list)

    for race in races:
        rows = race["rows"]
        if len(rows) < 6:
            continue
        pos = [h["pos"] for h in rows]
        vals = {leaf: [h["features"].get(leaf, 60.0) for h in rows] for leaf in LEAVES}
        for leaf in LEAVES:
            # 高分應該對應細名次 → 取負號令 ρ>0 代表有預測力
            r = spearman(vals[leaf], pos)
            if r is not None:
                rho[leaf].append(-r)
            # 場內五分位
            order = sorted(range(len(rows)), key=lambda i: -vals[leaf][i])
            n = len(order)
            for slot, idx in enumerate(order):
                q = min(4, slot * 5 // n)
                quintile[leaf][q][0] += 1
                quintile[leaf][q][1] += 1 if pos[idx] <= 3 else 0
        for i, a in enumerate(LEAVES):
            for b in LEAVES[i + 1:]:
                r = spearman(vals[a], vals[b])
                if r is not None:
                    pair_rho[(a, b)].append(r)

    print(f"races used {len(rho['form_score'])}\n")
    print(f"{'leaf':26}{'有效權重':>10}{'場內 ρ':>9}"
          f"{'Q1 前三%':>10}{'Q5 前三%':>10}{'Q1−Q5':>9}")
    rows_out = []
    for leaf in LEAVES:
        if not rho[leaf]:
            continue
        mean_rho = statistics.mean(rho[leaf])
        q = quintile[leaf]
        q1 = 100 * q[0][1] / q[0][0] if q[0][0] else 0
        q5 = 100 * q[4][1] / q[4][0] if q[4][0] else 0
        rows_out.append((leaf, eff.get(leaf, 0.0), mean_rho, q1, q5))
    for leaf, w, r, q1, q5 in sorted(rows_out, key=lambda x: -x[2]):
        print(f"{leaf:26}{w:>10.4f}{r:>9.3f}{q1:>10.1f}{q5:>10.1f}{q1-q5:>9.1f}")

    print("\n最高冗餘（場內相關 |ρ| ≥ 0.30）：")
    reds = [(abs(statistics.mean(v)), a, b, statistics.mean(v))
            for (a, b), v in pair_rho.items() if v and abs(statistics.mean(v)) >= 0.30]
    for _, a, b, r in sorted(reds, reverse=True)[:15]:
        print(f"   {a:26} ↔ {b:26} ρ {r:+.3f}")

    print("\n狀態與穩定性 兩個 leaf 之間：")
    key = ("form_score", "consistency_score")
    if pair_rho.get(key):
        print(f"   form_score ↔ consistency_score ρ = "
              f"{statistics.mean(pair_rho[key]):+.3f}")


if __name__ == "__main__":
    main()
