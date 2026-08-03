#!/usr/bin/env python3
"""L600 應該用邊個口徑？生涯最快 / 平均 / 最近 —— 直接比預測力。

`_sectional_breakdown` 個「末段極速破標準」（+15.07）用 `timing_600m_best_speed`
即係**生涯最大值**。一次快段速就變成永久資歷。量到 best/avg 中位數 1.035、
P99 1.101，26.7% 嘅馬 best 高出自己平均 ≥5%（Benbulben 1.110，P99 以上）。

呢個測試唔需要場地標準時間：直接喺場內用三個口徑排名，同實際名次比 Spearman ρ。
邊個口徑 ρ 高，邊個就係更好嘅 ability 訊號。

同時測「班次代理」：獎金（100% 密度）。

唯讀，本地 cache。
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


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
    if len(xs) < 4:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx)
    dy = sum((b - my) ** 2 for b in ry)
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy) ** 0.5


def main():
    races = json.loads((HERE / "au_leaf_cache.json").read_text(encoding="utf-8"))["races"]
    timing = json.loads((HERE / "au_timing_cache.json").read_text(encoding="utf-8"))
    prize = json.loads((HERE / "au_prize_cache.json").read_text(encoding="utf-8"))

    rho = defaultdict(list)
    quint = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for race in races:
        rows = race["rows"]
        if len(rows) < 6:
            continue
        pos = [h["pos"] for h in rows]

        def collect(name, getter):
            vals, keep = [], []
            for i, h in enumerate(rows):
                v = getter(h)
                if v is None:
                    continue
                vals.append(v)
                keep.append(i)
            if len(vals) < 4:
                return
            sub = [pos[i] for i in keep]
            r = spearman(vals, sub)
            if r is not None:
                rho[name].append(-r)
            order = sorted(range(len(vals)), key=lambda i: -vals[i])
            n = len(order)
            for slot, idx in enumerate(order):
                q = min(4, slot * 5 // n)
                quint[name][q][0] += 1
                quint[name][q][1] += 1 if sub[idx] <= 3 else 0

        def tkey(h):
            return timing.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}

        def pkey(h):
            return prize.get(f"{race['meeting']}|{race['race']}|{h['n']}") or {}

        collect("L600 生涯最快 (現行)", lambda h: tkey(h).get("timing_600m_best_speed"))
        collect("L600 平均", lambda h: tkey(h).get("timing_600m_avg_speed"))
        collect("L600 最近", lambda h: tkey(h).get("timing_600m_recent_speed"))

        def capped(h):
            t = tkey(h)
            b, a = t.get("timing_600m_best_speed"), t.get("timing_600m_avg_speed")
            if b is None or a is None:
                return None
            return min(b, a * 1.05)
        collect("L600 最快但封頂 avg×1.05", capped)

        collect("官方讓磅分 horse_rating", lambda h: tkey(h).get("horse_rating"))

        # 班次代理：近仗獎金（log10），decay 加權
        def prize_level(h):
            runs = [r for r in (pkey(h).get("runs") or []) if not r.get("is_trial")]
            if not runs:
                return None
            weights = (1.0, 0.8, 0.6, 0.4)
            num = den = 0.0
            for r, w in zip(runs[:4], weights):
                if r.get("prize"):
                    num += math.log10(max(1000, r["prize"])) * w
                    den += w
            return num / den if den else None
        collect("近仗獎金水平 (班次代理)", prize_level)

        # 對照：現行 form / sectional / pace_figure
        collect("form_score (對照)", lambda h: h["features"].get("form_score"))
        collect("sectional_score (對照)", lambda h: h["features"].get("sectional_score"))
        collect("pace_figure_score (對照)", lambda h: h["features"].get("pace_figure_score"))

    print(f"{'口徑':34}{'場數':>7}{'場內 ρ':>9}{'Q1 前三%':>10}{'Q5 前三%':>10}{'差':>8}")
    out = []
    for name, vals in rho.items():
        if len(vals) < 50:
            continue
        q = quint[name]
        q1 = 100 * q[0][1] / q[0][0] if q[0][0] else 0
        q5 = 100 * q[4][1] / q[4][0] if q[4][0] else 0
        out.append((name, len(vals), statistics.mean(vals), q1, q5))
    for name, n, r, q1, q5 in sorted(out, key=lambda x: -x[2]):
        print(f"{name:34}{n:>7}{r:>9.3f}{q1:>10.1f}{q5:>10.1f}{q1-q5:>8.1f}")


if __name__ == "__main__":
    main()
