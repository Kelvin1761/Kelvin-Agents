#!/usr/bin/env python3
"""AU 負磅物理效應（同 HKJC EXP-20261112-06 同一問題）：同一匹馬多負 1kg，輸多幾多秒？

    au_weight_effect_panel_20261113.py BEFORE_DATE

只用 BEFORE_DATE 之前嘅正式賽往績（唔掂判決窗）。Formguide 每行：日期、路程、獎金、負磅、輸距、L600 Delta。
y = 輸距 × 0.17 秒（= 本駒 L600 估算 − 賽事 L600，即 AU 個體化嗰部分）。
模型：y ~ 馬匹固定效應 + 負磅 + log 獎金（班次代理）+ 路程組，逐路程組分開報。bootstrap 以馬匹做單位。
"""
import glob
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

W = Path(__file__).resolve().parents[1]
ROOT = open(W / ".wongchoi_au_data_root").read().strip()
HDR = re.compile(r"^#+\s*\[?(\d+)\]?\.?\s*(.+?)\s*(?:\(|$)", re.M)
LINE = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(\d{3,4})m\s+cond:\S*\s+\$(\d+)\s.*?\)\s*([\d.]+)kg.*?margin:\s*(-?[\d.]+)L?")


def runs(before):
    seen = {}
    for f in glob.glob(ROOT + "/**/*Formguide.md", recursive=True):
        text = open(f, encoding="utf-8", errors="ignore").read()
        horse = None
        for line in text.splitlines():
            h = re.match(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", line)
            if h:
                horse = h.group(2).strip().lower()
                continue
            if "TRIAL" in line or "cond:" not in line or horse is None:
                continue
            m = LINE.search(line)
            if not m:
                continue
            date, dist, prize, kg, margin = m.groups()
            if date >= before or float(prize) <= 0:
                continue
            seen[(horse, date)] = (horse, int(dist), math.log10(float(prize)), float(kg), float(margin) * 0.17)
    return list(seen.values())


def fit(rows):
    by = defaultdict(list)
    for r in rows:
        by[r[0]].append(r)
    xs, ys, zs = [], [], []
    for h, rr in by.items():
        if len(rr) < 3:
            continue
        mk = sum(r[3] for r in rr) / len(rr)
        mp = sum(r[2] for r in rr) / len(rr)
        my = sum(r[4] for r in rr) / len(rr)
        for r in rr:
            xs.append(r[3] - mk); zs.append(r[2] - mp); ys.append(r[4] - my)
    # 兩個 regressor（負磅、log 獎金）OLS，冇常數（已 demean）
    sxx = sum(x * x for x in xs); szz = sum(z * z for z in zs); sxz = sum(x * z for x, z in zip(xs, zs))
    sxy = sum(x * y for x, y in zip(xs, ys)); szy = sum(z * y for z, y in zip(zs, ys))
    det = sxx * szz - sxz * sxz
    return ((szz * sxy - sxz * szy) / det if det else float("nan")), len(xs), len(by)


def main():
    rows = runs(sys.argv[1])
    print("runs", len(rows))
    buckets = {"≤1200m": lambda d: d <= 1200, "1201–1600m": lambda d: 1200 < d <= 1600, ">1600m": lambda d: d > 1600, "全部": lambda d: True}
    for name, fn in buckets.items():
        sub = [r for r in rows if fn(r[1])]
        b, n, horses = fit(sub)
        hs = sorted({r[0] for r in sub})
        by = defaultdict(list)
        for r in sub:
            by[r[0]].append(r)
        rng = random.Random(7); bs = []
        for _ in range(300):
            pick = [hs[rng.randrange(len(hs))] for _ in hs]
            bs.append(fit([r for h in pick for r in by[h]])[0])
        bs.sort()
        print(f"{name:10s} 每 kg 多輸 {b:+.4f} 秒  [{bs[7]:+.4f}, {bs[292]:+.4f}]  runs {n}  horses {horses}")


if __name__ == "__main__":
    main()
