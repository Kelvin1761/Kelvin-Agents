"""J3 改咗頭二嘅場次：被推上頭二 vs 被擠出頭二，入頭三率；推上去嘅主要訊號。只用 dev（2020-09～2024-07）揀方向。"""
import json, sys
from collections import defaultdict
import numpy as np
V = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history"
B = {(x["meeting"], x["race"]): x for x in map(json.loads, open(f"{V}/analysis/replay_all/v4/cons/base_live_20261122.jsonl")) if "horses" in x}
C = {(x["meeting"], x["race"]): x for x in map(json.loads, open(f"{V}/scratch/joint_plus/jl_J3.jsonl")) if "horses" in x}
win = sys.argv[1] if len(sys.argv) > 1 else "dev"
lo, hi = {"dev": ("2020-09-01", "2024-07-31"), "hold": ("2024-09-01", "2026-07-31")}[win]
up, down, n_races, changed = [], [], 0, 0
gain = defaultdict(list)
for k, b in B.items():
    if not (lo <= b["date"] <= hi) or k not in C: continue
    c = C[k]; n_races += 1
    pos = {h["n"]: h["pos"] for h in b["horses"]}
    b2, c2 = set(b["picks"][:2]), set(c["picks"][:2])
    if b2 == c2: continue
    changed += 1
    bh = {h["n"]: h["raw"] for h in b["horses"]}; ch = {h["n"]: h["raw"] for h in c["horses"]}
    dd = {n: ch[n] - bh[n] for n in bh}; mean = np.mean(list(dd.values()))
    for n in c2 - b2: up.append((int(bool(pos[n]) and pos[n] <= 3), dd[n] - mean, pos[n]))
    for n in b2 - c2: down.append((int(bool(pos[n]) and pos[n] <= 3), dd[n] - mean, pos[n]))
u, d = np.array(up, dtype=float), np.array(down, dtype=float)
print(f"[{win}] {n_races} 場，J3 改咗頭二 {changed} 場（{100*changed/n_races:.0f}%）")
print(f"  被推上頭二：{len(u)} 匹，入頭三 {100*u[:,0].mean():.1f}%，贏 {100*np.mean(u[:,2]==1):.1f}%，J3 淨加 {u[:,1].mean():+.2f}")
print(f"  被擠出頭二：{len(d)} 匹，入頭三 {100*d[:,0].mean():.1f}%，贏 {100*np.mean(d[:,2]==1):.1f}%，J3 淨加 {d[:,1].mean():+.2f}")
rng = np.random.default_rng(0)
diff = [rng.choice(u[:,0], len(u)).mean() - rng.choice(d[:,0], len(d)).mean() for _ in range(2000)]
print(f"  差（上 − 落）{100*(u[:,0].mean()-d[:,0].mean()):+.1f}pp [{100*np.percentile(diff,2.5):+.1f},{100*np.percentile(diff,97.5):+.1f}]")
