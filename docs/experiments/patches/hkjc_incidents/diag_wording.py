"""用字審計跟進：淨係新增字眼（現行 regex 冇捉）嘅馬，下一仗殘差（live I1 dump）。另報相隔日數。"""
import json
import re
import sys

import numpy as np

from diag import season
from diag_full import calibrate, load_runs
from build_wording import BLEED, CARRIED, INJ, MED, WIDE

runs = load_runs(sys.argv[2])
code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
cal = calibrate(rows)
G = {"氣管出血（只此）": lambda s: re.search(BLEED, s) and not re.search(MED, s),
     "現行醫療": lambda s: re.search(MED, s),
     "被帶出外疊（只此）": lambda s: re.search(CARRIED, s) and not re.search(WIDE, s),
     "割傷擦傷受傷（只此）": lambda s: re.search(INJ, s) and not re.search(f"{MED}|{BLEED}", s)}
recs = {k: [] for k in G}
from datetime import date
for x in rows:
    s = season(x["date"])
    if s < 2020:
        continue
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); z = r - r.mean(); a, b = cal[s]
    for h, zz in zip(hs, z):
        c = code_of.get((x["date"], x["race"], str(h["n"])))
        prev = [v for v in runs[c] if v[0] < x["date"]] if c else []
        if not prev or not prev[-1][2]:
            continue
        gap = (date.fromisoformat(x["date"]) - date.fromisoformat(prev[-1][0])).days
        for k, f in G.items():
            if f(prev[-1][2]):
                recs[k].append((s, int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * zz))), gap))
rng = np.random.default_rng(0)
for k, v in recs.items():
    for lab, lo, hi in (("dev", 2020, 2023), ("holdout", 2024, 2026)):
        y = np.array([e for s, e, g in v if lo <= s <= hi]); gaps = [g for s, e, g in v if lo <= s <= hi]
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(400)]
        print(f"{k} {lab} n={len(y)} 殘差 {100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 相隔中位 {np.median(gaps):.0f} 日")
