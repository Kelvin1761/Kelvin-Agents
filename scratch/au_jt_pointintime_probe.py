#!/usr/bin/env python3
"""騎師／練馬師特徵：自己由結果 CSV 計 point-in-time，值唔值得？

用戶提出 Racenet profile 頁有 per-track、per-combo、season win/place %、ROI，
可以救返而家好弱嘅 jockey/trainer 分（19.4% 權重只交付 12.6% 影響力）。
但 Racenet API host 硬 403（GET/POST/Playwright 全部），只有 www HTML 頁
穿到（成功率約 1/3）而且**只得摘要**，冇 per-track / per-combo。

所以先問：我哋自己嘅 `AU_Historical_Raw_Race_Results.csv`（7,916 行、63 賽日、
SP 98.3%）夠唔夠自己計？呢個 script 量兩樣：

  A. **point-in-time 樣本深度** —— 每個特徵喺落注嗰刻實際有幾多場歷史
  B. **預測力** —— 場內 Spearman ρ vs 實際名次、五分位前三率

嚴格 point-in-time：每一場只用**之前日期**嘅資料，冇前視偏差。
唯讀。
"""
from __future__ import annotations

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / ".agents/skills/au_racing/au_wong_choi_auto/scripts"))

from au_archive_calibrator import (  # noqa: E402
    HISTORICAL_RESULTS_CSV, normalize_track_name, parse_float, parse_int)

PRIOR_W, PRIOR_P = 4.0, 0.30      # 收縮偽計數：先驗勝率 ~ 1/場均馬數


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2.0
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
    return num / (dx * dy) ** 0.5 if dx > 0 and dy > 0 else None


def main():
    rows = []
    with HISTORICAL_RESULTS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            pos, race = parse_int(r.get("Pos")), parse_int(r.get("Race"))
            if not pos or not race:
                continue
            rows.append({
                "date": str(r.get("Date") or "").strip(),
                "track": normalize_track_name(r.get("Track") or ""),
                "race": race, "pos": pos,
                "jockey": str(r.get("Jockey") or "").strip().lower(),
                "trainer": str(r.get("Trainer") or "").strip().lower(),
                "sp": parse_float(r.get("SP")),
            })
    rows.sort(key=lambda r: (r["date"], r["track"], r["race"]))

    # 累計器：key -> [runs, wins, places, profit]
    acc = {k: defaultdict(lambda: [0, 0, 0, 0.0])
           for k in ("jockey", "trainer", "combo", "jockey_track", "trainer_track")}

    def keys(r):
        return {"jockey": r["jockey"], "trainer": r["trainer"],
                "combo": (r["jockey"], r["trainer"]),
                "jockey_track": (r["jockey"], r["track"]),
                "trainer_track": (r["trainer"], r["track"])}

    depth = defaultdict(list)
    rho = defaultdict(list)
    quint = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    # 逐場處理：先讀（point-in-time），後寫
    by_race = defaultdict(list)
    for r in rows:
        by_race[(r["date"], r["track"], r["race"])].append(r)

    for key in sorted(by_race):
        field = by_race[key]
        if len(field) < 6:
            for r in field:
                ks = keys(r)
                for name, k in ks.items():
                    a = acc[name][k]
                    a[0] += 1
                    a[1] += 1 if r["pos"] == 1 else 0
                    a[2] += 1 if r["pos"] <= 3 else 0
                    a[3] += (r["sp"] - 1.0) if (r["pos"] == 1 and r["sp"]) else -1.0
            continue
        pos = [r["pos"] for r in field]
        for name in acc:
            vals, keep, ns = [], [], []
            for i, r in enumerate(field):
                a = acc[name].get(keys(r)[name])
                if not a or a[0] == 0:
                    continue
                runs, wins = a[0], a[1]
                # 收縮勝率，避免 1 場 1 勝 = 100%
                vals.append((wins + PRIOR_W * PRIOR_P) / (runs + PRIOR_W))
                keep.append(i)
                ns.append(runs)
            if len(vals) >= 4:
                depth[name].extend(ns)
                sub = [pos[i] for i in keep]
                r_ = spearman(vals, sub)
                if r_ is not None:
                    rho[name].append(-r_)
                order = sorted(range(len(vals)), key=lambda i: -vals[i])
                for slot, idx in enumerate(order):
                    q = min(4, slot * 5 // len(order))
                    quint[name][q][0] += 1
                    quint[name][q][1] += 1 if sub[idx] <= 3 else 0
        for r in field:
            ks = keys(r)
            for name, k in ks.items():
                a = acc[name][k]
                a[0] += 1
                a[1] += 1 if r["pos"] == 1 else 0
                a[2] += 1 if r["pos"] <= 3 else 0
                a[3] += (r["sp"] - 1.0) if (r["pos"] == 1 and r["sp"]) else -1.0

    print(f"{'特徵':16}{'可用場數':>9}{'樣本深度中位':>13}{'P25':>7}{'≥10場%':>9}"
          f"{'場內 ρ':>9}{'Q1前三%':>9}{'Q5前三%':>9}")
    for name in ("jockey", "trainer", "combo", "jockey_track", "trainer_track"):
        d = depth[name]
        if not d or not rho[name]:
            continue
        q = quint[name]
        q1 = 100 * q[0][1] / q[0][0] if q[0][0] else 0
        q5 = 100 * q[4][1] / q[4][0] if q[4][0] else 0
        d_sorted = sorted(d)
        print(f"{name:16}{len(rho[name]):>9}{d_sorted[len(d)//2]:>13}"
              f"{d_sorted[len(d)//4]:>7}{100*sum(1 for x in d if x>=10)/len(d):>8.0f}%"
              f"{statistics.mean(rho[name]):>9.3f}{q1:>9.1f}{q5:>9.1f}")

    print("\n對照（已量過嘅現行 leaf）：")
    print("  form_score 0.214 / consistency 0.193 / pace_figure 0.173 /"
          " jockey_score 0.163 / trainer_score 0.156 / jockey_horse_fit 0.071")


if __name__ == "__main__":
    main()
