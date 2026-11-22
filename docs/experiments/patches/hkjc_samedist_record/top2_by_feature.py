"""J3 改頭二嘅場：按「邊個訊號主導推上去」分組，推上 vs 擠出嘅入頭三率。dev 揀方向；holdout 只報。"""
import json, pickle
from collections import defaultdict
import numpy as np
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
NAMES = ["ride_q", "wide2", "blocked2", "slow", "rb_placed", "rb_any", "drop_rb", "old_won", "gear_off", "gear_on", "dist_down",
         "class_pos", "backup10", "sd_worse", "sd_hicls", "sd_locls", "sd_rate"]
BETA = np.array([1.65, 0.95, 0.66, 0.63, 1.13, 0.47, 2.89, -3.62, 0.75, -0.41, 0.39, -0.54, 0.20, -2.51, 0.56, -0.91, 1.44])
GROUP = {"ride_q": "藉口類", "wide2": "藉口類", "blocked2": "藉口類", "slow": "藉口類", "rb_placed": "評分跌返類", "rb_any": "評分跌返類",
         "drop_rb": "評分跌返類", "old_won": "老馬贏後", "gear_off": "配備", "gear_on": "配備", "dist_down": "其他", "class_pos": "班內位置",
         "backup10": "其他", "sd_worse": "同程類", "sd_hicls": "同程類", "sd_locls": "同程類", "sd_rate": "同程類"}
X = pickle.load(open(f"{V}/scratch/joint_plus/X_live.pkl", "rb"))
B = {(x["meeting"], x["race"]): x for x in map(json.loads, open(f"{V}/analysis/replay_all/v4/cons/base_live_20261122.jsonl")) if "horses" in x}
C = {(x["meeting"], x["race"]): x for x in map(json.loads, open(f"{V}/scratch/joint_plus/jl_J3.jsonl")) if "horses" in x}
for win, (lo, hi) in (("dev", ("2020-09-01", "2024-07-31")), ("holdout（只報）", ("2024-09-01", "2026-07-31"))):
    res = defaultdict(lambda: [[], []])
    for k, b in B.items():
        if not (lo <= b["date"] <= hi) or k not in C or k not in X: continue
        c = C[k]; b2, c2 = set(b["picks"][:2]), set(c["picks"][:2])
        if b2 == c2: continue
        idx = {h["n"]: i for i, h in enumerate(b["horses"])}; pos = {h["n"]: h["pos"] for h in b["horses"]}
        contrib = X[k] * BETA
        ups, downs = list(c2 - b2), list(b2 - c2)
        for u, d in zip(ups, downs):
            delta = contrib[idx[u]] - contrib[idx[d]]
            grp = GROUP[NAMES[int(np.argmax(delta))]]
            res[grp][0].append(int(bool(pos[u]) and pos[u] <= 3)); res[grp][1].append(int(bool(pos[d]) and pos[d] <= 3))
    print(f"== {win}")
    for g, (u, d) in sorted(res.items(), key=lambda kv: -len(kv[1][0])):
        u, d = np.array(u), np.array(d)
        print(f"  主導 {g}：{len(u)} 對｜推上 入頭三 {100*u.mean():.1f}%｜擠出 {100*d.mean():.1f}%｜差 {100*(u.mean()-d.mean()):+.1f}pp")
