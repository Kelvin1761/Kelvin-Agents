"""Kelvin Q9：直路 1000 檔位分要唔要重新設計？live I1 dump（已含三級檔位分＋檔位×跑法＋逐檔曲線）殘差按檔位分組。
殘差 ≈ 0 = 現行設計已經食晒檔位效應；系統性偏差 = 要重新設計。"""
import json
import sys

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
import hkjc_history_replay_build as b  # noqa: E402
from diag import calibrate, season  # noqa: E402

idx = b.load_index()
rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
cal = calibrate(rows)
recs = []
for x in rows:
    s = season(x["date"])
    if s < 2020 or x["distance"] != 1000 or x["venue"] != "沙田" or x.get("awt"):
        continue
    res = {str(r.get("horse_no")): r for r in (idx["results"].get((x["date"], x["race"])) or {}).get("results", [])}
    hs = [h for h in x["horses"] if h["pos"]]
    r = np.array([h["raw"] for h in hs]); z = r - r.mean(); a, bb = cal[s]
    for h, zz in zip(hs, z):
        try:
            d = int((res.get(str(h["n"])) or {}).get("draw"))
        except (TypeError, ValueError):
            continue
        recs.append(dict(s=s, y=int(h["pos"] <= 3), w=int(h["pos"] == 1), p=1 / (1 + np.exp(-(a + bb * zz))), d=d,
                         ds=h["f"].get("draw_score"), F=len(hs)))
print("直路馬次", len(recs), "場", len({(r['s'], ) for r in recs}))
rng = np.random.default_rng(0)
for lab, lo, hi in (("dev 2020-23", 2020, 2023), ("holdout 2024-26", 2024, 2026)):
    for name, f in (("1–3", lambda r: r["d"] <= 3), ("4–6", lambda r: 4 <= r["d"] <= 6), ("7–9", lambda r: 7 <= r["d"] <= 9),
                    ("10–11", lambda r: 10 <= r["d"] <= 11), ("12–14", lambda r: r["d"] >= 12)):
        sub = [r for r in recs if lo <= r["s"] <= hi and f(r)]
        y = np.array([r["y"] - r["p"] for r in sub])
        bt = [y[rng.integers(0, len(y), len(y))].mean() for _ in range(400)]
        raw = np.mean([r["y"] for r in sub])
        print(f"{lab} 檔{name} n={len(y)} 入三率 {100*raw:.1f}% 殘差 {100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] 檔位分均 {np.mean([r['ds'] for r in sub if r['ds'] is not None]):.1f}")
