"""Kelvin 2026-11-19 逐場覆盤（11-18 跑馬地）：每個維度按場內貢獻（權重 × (維度分 − 場均)）分五組，量入頭三 − live 校準 p。
高貢獻組負、低貢獻組正 = 該維度太重／太散；相反 = 太輕。只做診斷。用法：python3 diag_dim_calibration.py <live dump>
"""
import json, sys
import numpy as np
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_incidents")
from diag import season  # noqa: E402
from diag_full import calibrate  # noqa: E402
W = {"stability": .2451, "trainer_signal": .3296, "sectional": .1285, "race_shape": .1925, "horse_health": .0344, "form_line": .07, "distance_fit": .02}
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
calib = calibrate(rows); recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020: continue
    hs = [h for h in x["horses"] if h["pos"] and not h.get("debut")]
    if len(hs) < 6: continue
    r = np.array([h["raw"] for h in hs]); rc = r - r.mean(); a, bb = calib[s]
    m = {k: np.array([float(h["m"].get(k) or 60) for h in hs]) for k in W}
    c = {k: W[k] * (m[k] - m[k].mean()) for k in W}
    for i, (h, z) in enumerate(zip(hs, rc)):
        recs.append((s, int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + bb * z))), {k: c[k][i] for k in W}))
print("馬次（非初出）", len(recs))
rng = np.random.default_rng(0)
for k in W:
    allc = np.array([r[2][k] for r in recs]); qs = np.quantile(allc, [.2, .4, .6, .8])
    line = []
    for lo, hi, lab in ((2020, 2023, "dev"), (2024, 2025, "ho")):
        sub = [r for r in recs if lo <= r[0] <= hi]
        cells = []
        for qi in range(5):
            y = np.array([r[1] for r in sub if np.searchsorted(qs, r[2][k]) == qi])
            cells.append(f"{100*y.mean():+.1f}")
        top = np.array([r[1] for r in sub if np.searchsorted(qs, r[2][k]) == 4]); bot = np.array([r[1] for r in sub if np.searchsorted(qs, r[2][k]) == 0])
        bt = [top[rng.integers(0, len(top), len(top))].mean() - bot[rng.integers(0, len(bot), len(bot))].mean() for _ in range(500)]
        d = top.mean() - bot.mean()
        line.append(f"{lab} 低→高 [{' '.join(cells)}] 高−低 {100*d:+.1f} [{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}]")
    print(f"{k:15s} " + " ｜ ".join(line))
